# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - drawing board
# Copyright (C) 2026 GA3Dtech
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or (at
# your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <https://www.gnu.org/licenses/>.
"""
view.py (Croquis) - the drawing board: a flat 2D canvas in a FreeCAD tab,
so sketching does not fight with the 3D camera.

SheetCanvas is a plain QWidget (not a QGraphicsView): it gets tablet events
directly, and paints the compositor image through its own zoom / pan
transform, only inside the region Qt asks to repaint. It owns navigation
(zoom, pan, fit), the input devices and the shortcuts; what the pen does is
up to the active tool (tools.py).

SheetBoard wraps the canvas with the toolbar, the tool options and the
paper / layers panel.
"""

import os

from .. import icon, model, prefs
from ..i18n import tr, tr_data
from ..qt import QAction, QActionGroup, QtCore, QtGui, QtWidgets, QUndoStack, event_pos
from ..render import brushes
from ..render import compositor as comp_mod
from ..render import stroke_geom as geom
from . import tools, undo

ZOOM_MIN = 0.03
ZOOM_MAX = 16.0
SIZE_MIN = 0.05     # mm
SIZE_MAX = 60.0
BACKGROUND = QtGui.QColor(88, 90, 94)

# Tool keys of the board, toolbar order: key, icon, shortcut
BOARD_TOOLS = [
    ("pencil", "Pencil.svg", QtCore.Qt.Key_P),
    ("grease", "Grease.svg", QtCore.Qt.Key_G),
    ("marker", "Marker.svg", QtCore.Qt.Key_M),
    ("highlight", "Highlight.svg", QtCore.Qt.Key_W),
    ("line", "Line.svg", QtCore.Qt.Key_L),
    ("spline", "Spline.svg", QtCore.Qt.Key_S),
    ("arrow", "Arrow.svg", QtCore.Qt.Key_A),
    ("eraser", "Eraser.svg", QtCore.Qt.Key_E),
    ("edit", "EditStroke.svg", QtCore.Qt.Key_V),
    ("scale", "Scale.svg", QtCore.Qt.Key_K),
]
_TOOL_KEYS = dict((int(k), t) for t, _i, k in BOARD_TOOLS)

# Keys handled by the canvas even if FreeCAD has a shortcut on them
# (Delete would delete the selected document objects, Ctrl+Z undo in 3D,
# Ctrl+C / Ctrl+V copy and paste document objects)
_OWN_KEYS = set(_TOOL_KEYS) | set(int(k) for k in (
    QtCore.Qt.Key_F, QtCore.Qt.Key_Space, QtCore.Qt.Key_C,
    QtCore.Qt.Key_BracketLeft, QtCore.Qt.Key_BracketRight,
    QtCore.Qt.Key_Z, QtCore.Qt.Key_Y, QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace,
    QtCore.Qt.Key_Escape, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter))


def _checker_brush():
    pix = QtGui.QPixmap(16, 16)
    pix.fill(QtGui.QColor(255, 255, 255))
    p = QtGui.QPainter(pix)
    c = QtGui.QColor(214, 214, 214)
    p.fillRect(0, 0, 8, 8, c)
    p.fillRect(8, 8, 8, 8, c)
    p.end()
    return QtGui.QBrush(pix)


def _key_code(event):
    """Key code as a plain int (PySide6 returns enums, PySide2 ints)."""
    return int(event.key())


def tool_label(key):
    if key == "edit":
        return tr("Edit vector strokes")
    if key == "scale":
        return tr("Scale: give a real length")
    return tr_data(model.TOOLS[key]["label"])


def default_settings():
    """Initial settings of every board tool."""
    out = {}
    for k, t in model.TOOLS.items():
        st = {"color": t["color"], "size": t["size"], "opacity": t["opacity"]}
        if t["kind"] == "vector":
            st.update(model.DEFAULT_PROFILE)
        out[k] = st
    out["line"]["tin"] = 0.6
    out["arrow"].update(model.DEFAULT_ARROW)
    out["arrow"]["mode"] = "straight"
    out["spline"]["mode"] = "freehand"
    out["eraser"]["mode"] = "soft"
    out["eraser"]["target"] = model.ALL_LAYERS
    return out


class SheetCanvas(QtWidgets.QWidget):
    """Zoomable drawing surface of one sheet."""

    toolChanged = QtCore.Signal(str)
    settingsChanged = QtCore.Signal()
    zoomChanged = QtCore.Signal(float)
    sheetEdited = QtCore.Signal()       # paper / layer settings (not undoable)

    def __init__(self, sheet, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.sheet = sheet
        self.compositor = comp_mod.Compositor(sheet)
        self.undo_stack = QUndoStack(self)
        self.tool_settings = default_settings()
        self.tool = "pencil"
        self.doc_name = None        # set by sheet.open_board
        self.handler = tools.make_tool(self, self.tool)
        self.zoom = 1.0
        self.offset = QtCore.QPointF(0, 0)
        self._fitted = False
        self._checker = _checker_brush()
        self._live_img = None
        self._region = None         # repaint region of the paint in progress
        self._input = None          # "tablet" / "mouse" while a button is down
        self._curve = 1.0
        # navigation
        self._pan = None
        self._space = False
        self._hover = None

        self.setMouseTracking(True)
        if hasattr(self, "setTabletTracking"):
            self.setTabletTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        self.setAcceptDrops(True)
        self.setCursor(QtCore.Qt.CrossCursor)
        self.setMinimumSize(200, 150)

    # ------------------------------------------------------------------
    #  Coordinates
    # ------------------------------------------------------------------
    @property
    def scale(self):
        """Sheet pixels per millimetre."""
        return self.compositor.scale

    def to_sheet_px(self, pos):
        return QtCore.QPointF((pos.x() - self.offset.x()) / self.zoom,
                              (pos.y() - self.offset.y()) / self.zoom)

    def to_mm(self, pos):
        """Widget position -> sheet millimetres (x, y)."""
        s = self.to_sheet_px(pos)
        return s.x() / self.scale, s.y() / self.scale

    def to_widget(self, p):
        """Sheet millimetres (x, y, ...) -> widget position (QPointF)."""
        k = self.scale * self.zoom
        return QtCore.QPointF(p[0] * k + self.offset.x(), p[1] * k + self.offset.y())

    def to_widget_rect(self, r):
        """Sheet pixel rectangle -> widget rectangle (QRect, grown a bit)."""
        z = self.zoom
        rf = QtCore.QRectF(r.x() * z + self.offset.x(), r.y() * z + self.offset.y(),
                           r.width() * z, r.height() * z)
        return rf.toAlignedRect().adjusted(-2, -2, 2, 2)

    def sheet_rect_widget(self):
        return QtCore.QRectF(self.offset.x(), self.offset.y(),
                             self.compositor.w * self.zoom, self.compositor.h * self.zoom)

    def fit(self):
        """Whole sheet in the window, centred."""
        margin = 24
        w, h = self.compositor.w, self.compositor.h
        z = min((self.width() - 2 * margin) / float(w),
                (self.height() - 2 * margin) / float(h))
        self.zoom = min(max(z, ZOOM_MIN), ZOOM_MAX)
        self.offset = QtCore.QPointF((self.width() - w * self.zoom) / 2.0,
                                     (self.height() - h * self.zoom) / 2.0)
        self.update()
        self.zoomChanged.emit(self.zoom)

    def set_zoom(self, z, anchor=None):
        """Zoom keeping the sheet point under `anchor` (widget pos) fixed."""
        if anchor is None:
            anchor = QtCore.QPointF(self.width() / 2.0, self.height() / 2.0)
        z = min(max(z, ZOOM_MIN), ZOOM_MAX)
        sp = self.to_sheet_px(anchor)
        self.zoom = z
        self.offset = QtCore.QPointF(anchor.x() - sp.x() * z, anchor.y() - sp.y() * z)
        self.update()
        self.zoomChanged.emit(self.zoom)

    def live_buffer(self):
        """Sheet-sized transparent image the raster tools draw into."""
        c = self.compositor
        if self._live_img is None or self._live_img.width() != c.w \
                or self._live_img.height() != c.h:
            self._live_img = comp_mod.new_image(c.w, c.h)
        return self._live_img

    # ------------------------------------------------------------------
    #  Tools and their settings
    # ------------------------------------------------------------------
    def set_tool(self, key):
        if key == self.tool:
            return
        self.handler.cancel()
        self.tool = key
        self.handler = tools.make_tool(self, key)
        self.toolChanged.emit(key)
        self.settingsChanged.emit()
        self.update()

    def reset_tool(self):
        """Rebuild the tool object after a mode change (eraser)."""
        self.handler.cancel()
        self.handler = tools.make_tool(self, self.tool)
        self.update()

    def selection(self):
        return getattr(self.handler, "selection", None)

    def selected_image(self):
        sel = self.selection()
        return sel if getattr(sel, "kind", None) == "image" else None

    def current(self):
        """Settings shown in the toolbar: those of the selected stroke in
        the edit tool, else those of the tool."""
        sel = self.selection()
        if sel is not None and getattr(sel, "kind", None) == "image":
            d = dict(self.tool_settings["spline"])
            d["opacity"] = sel.opacity
            return d
        if sel is not None:
            d = {"color": sel.color, "size": sel.size, "opacity": sel.opacity}
            d.update(sel.profile())
            return d
        if self.tool not in self.tool_settings:      # edit, scale
            return dict(self.tool_settings["spline"])
        return self.tool_settings[self.tool]

    def _set(self, name, value):
        sel = self.selection()
        if self.selected_image() is not None:
            if name == "opacity":
                self.set_image(opacity=value, merge_key="opacity")
            return
        if sel is not None:
            new = sel.copy()
            if name in model.DEFAULT_PROFILE or name in model.DEFAULT_ARROW:
                new.params[name] = value
            else:
                setattr(new, name, value)
            self.undo_stack.push(undo.ReplaceStroke(self, sel, new, merge_key=name))
        elif self.tool in self.tool_settings:
            self.tool_settings[self.tool][name] = value
        self.settingsChanged.emit()
        self._update_hover(self._hover)

    def set_color(self, color):
        self._set("color", color)

    def set_size(self, size):
        size = min(max(float(size), SIZE_MIN), SIZE_MAX)
        if abs(size - self.current()["size"]) > 1e-9:
            self._set("size", size)

    def set_opacity(self, opacity):
        self._set("opacity", min(max(float(opacity), 0.01), 1.0))

    def set_profile(self, name, value):
        self._set(name, float(value))

    def set_param(self, name, value):
        """Stroke parameter that is not a number (arrow heads...)."""
        self._set(name, value)

    def set_option(self, name, value):
        """Tool option that is not a stroke property (spline mode, eraser
        mode and target)."""
        self.tool_settings[self.tool][name] = value
        if name == "mode":
            self.reset_tool()

    # --- paper and layers (saved with the sheet, not undoable)
    def set_paper(self, key):
        self.sheet.paper = key
        self.compositor.compose()
        self.update()
        self.sheetEdited.emit()

    def set_layer(self, key, visible=None, opacity=None):
        info = self.sheet.layers[key]
        if visible is not None:
            info["visible"] = bool(visible)
        if opacity is not None:
            info["opacity"] = float(opacity)
        self.compositor.compose()
        self.update()
        self.sheetEdited.emit()

    # ------------------------------------------------------------------
    #  Hooks for undo commands and tools
    # ------------------------------------------------------------------
    def sheet_changed(self, rect):
        if rect is None:
            self.update()
        else:
            self.update(self.to_widget_rect(rect))

    def strokes_removed(self, strokes):
        if self.selection() in strokes:
            self.handler.select(None)

    def stroke_replaced(self, old, new):
        if self.selection() is old:
            self.handler.selection = new
            self.update()

    def selection_changed(self):
        self.settingsChanged.emit()

    def clear_sheet(self):
        if self.sheet.strokes:
            self.handler.cancel()
            if self.selection() is not None:
                self.handler.select(None)
            self.undo_stack.push(undo.ClearSheet(self))

    def cancel_stroke(self):
        self.handler.cancel()

    def copy_render(self):
        """Copy the rendered sheet to the clipboard (paste it into a mail,
        a report...)."""
        QtWidgets.QApplication.clipboard().setImage(self.compositor.image.copy())

    # ------------------------------------------------------------------
    #  Images
    # ------------------------------------------------------------------
    def pick_image(self, pos):
        """Topmost unlocked visible image element under the position."""
        x, y = self.to_mm(pos)
        for e in reversed(self.sheet.elements):
            if getattr(e, "kind", None) != "image" or e.locked:
                continue
            if not self.sheet.layers.get(e.layer, {}).get("visible", True):
                continue
            if e.contains(x, y):
                return e
        return None

    def draw_element(self, p, e):
        """Paint an image element through the view transform (preview)."""
        img = self.compositor.picture(e)
        if img is None:
            return
        k = self.scale * self.zoom
        p.save()
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        p.setOpacity(e.opacity)
        p.translate(self.offset.x() + (e.x + e.w / 2.0) * k,
                    self.offset.y() + (e.y + e.h / 2.0) * k)
        p.rotate(e.rotation)
        p.drawImage(QtCore.QRectF(-e.w * k / 2.0, -e.h * k / 2.0, e.w * k, e.h * k), img)
        p.restore()

    def set_image(self, merge_key=None, index=None, **changes):
        """Change the selected image element (one undo step, consecutive
        changes of one setting merged)."""
        e = self.selected_image()
        if e is None:
            return
        new = e.copy()
        for k, v in changes.items():
            setattr(new, k, v)
        self.undo_stack.push(undo.ReplaceElement(self, e, new, merge_key, index))
        self.settingsChanged.emit()

    def document(self):
        """FreeCAD document of the sheet being drawn (set by the board)."""
        import FreeCAD as App
        return App.getDocument(self.doc_name)

    def add_picture(self, img, path=None, centre_mm=None, camera=None):
        """New image element from a QImage (paste, drop, capture): fitted
        in the sheet, or centred on centre_mm. Returns the element."""
        from .. import api
        e = api.image_element(self.sheet, img, path, camera=camera)
        if centre_mm is not None:
            e.x, e.y = centre_mm[0] - e.w / 2.0, centre_mm[1] - e.h / 2.0
        self.undo_stack.push(undo.AddElement(self, e))
        return e

    def paste(self, centre_mm=None, mime=None):
        """Ctrl+V: a picture from the clipboard (screenshot, image copied
        from a browser...) or image files copied in a file manager. The
        active tool does not change. Returns the new elements."""
        from .. import images
        if mime is None:
            mime = QtWidgets.QApplication.clipboard().mimeData()
        img, paths = images.from_mime(mime)
        added = []
        if img is not None and not paths:
            added.append(self.add_picture(img, centre_mm=centre_mm))
        for path in paths:
            try:
                added.append(self.add_picture(images.read(path), path, centre_mm))
            except ValueError:
                pass
        return added

    def set_plane_scale(self, scale):
        """Scale of the sheet's image plane (3D mm per sheet mm); saved
        with the sheet."""
        if scale > 0:
            self.sheet.plane_scale = float(scale)
            self.sheetEdited.emit()

    def ask_scale(self, length_mm):
        """Scale tool: the real length of a segment of `length_mm` on the
        sheet. A one-off question: a classic input dialog."""
        real, ok = QtWidgets.QInputDialog.getDouble(
            self, tr("Scale"), tr("Real length of this segment (mm):"),
            length_mm * self.sheet.plane_scale, 0.001, 1e7, 2)
        if ok and real > 0:
            self.set_plane_scale(real / length_mm)

    def set_guide(self, img, settings):
        """Show a captured 3D view guide (or remove it with None). Saved
        with the sheet when the board closes."""
        from .. import images
        key = model.SheetData.UNDERLAY_FILE
        if img is None:
            self.sheet.underlay = None
            self.sheet.files.pop(key, None)
        else:
            self.sheet.underlay = settings
            self.sheet.files[key] = images.save_temp(img, "croquis_underlay")
            self.sheet.layers["underlay"]["visible"] = True
        self.compositor.load_underlay()
        self.compositor.compose()
        self.update()
        self.sheetEdited.emit()

    def dragEnterEvent(self, event):
        from .. import images
        img, paths = images.from_mime(event.mimeData())
        if img is not None or paths:
            event.acceptProposedAction()
        else:
            event.ignore()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        pos = event_pos(event)
        added = self.paste(self.to_mm(pos), event.mimeData())
        if added:
            event.acceptProposedAction()
        else:
            event.ignore()

    def pick_stroke(self, pos, kinds=None):
        """Topmost visible stroke under the widget position (or None)."""
        x, y = self.to_mm(pos)
        tol = tools.PICK_PX / (self.scale * self.zoom)
        for s in reversed(self.sheet.strokes):
            if kinds is not None and s.kind not in kinds:
                continue
            if s.kind == "eraser" or not self.sheet.layers[s.layer]["visible"]:
                continue
            b = s.bounds()
            if b is None or not (b[0] - tol <= x <= b[2] + tol and b[1] - tol <= y <= b[3] + tol):
                continue
            if geom.distance_to_polyline(brushes.stroke_polyline(s), x, y) \
                    <= max(s.size / 2.0, tol):
                return s
        return None

    # ------------------------------------------------------------------
    #  Painting
    # ------------------------------------------------------------------
    def draw_image(self, p, img, pos, opacity=1.0, blend="normal"):
        """Paint an image placed at sheet pixel `pos` (QPoint), only its
        part inside the region being repainted."""
        z = self.zoom
        target = QtCore.QRectF(pos.x() * z + self.offset.x(), pos.y() * z + self.offset.y(),
                               img.width() * z, img.height() * z)
        visible = target.intersected(self._region) if self._region is not None else target
        if visible.isEmpty():
            return
        src = QtCore.QRectF((visible.x() - target.x()) / z, (visible.y() - target.y()) / z,
                            visible.width() / z, visible.height() / z)
        p.setOpacity(opacity)
        p.setCompositionMode(comp_mod.blend_mode(blend))
        p.drawImage(visible, img, src)
        p.setOpacity(1.0)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        try:
            region = QtCore.QRectF(event.rect())
            p.fillRect(region, BACKGROUND)
            target = self.sheet_rect_widget()
            self._region = region.intersected(target)
            if not self._region.isEmpty():
                if model.paper_color(self.sheet.paper) is None:
                    p.fillRect(self._region, self._checker)
                p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, self.zoom < 2.0)
                self.draw_image(p, self.compositor.image, QtCore.QPoint(0, 0))
                self.handler.paint_sheet(p)
            self._region = None
            p.setPen(QtGui.QPen(QtGui.QColor(30, 30, 30), 1))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawRect(target.adjusted(-0.5, -0.5, 0.5, 0.5))
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            self.handler.paint_overlay(p)
            self._paint_hover(p)
        finally:
            p.end()

    def _hover_radius(self):
        return max(1.5, self.current()["size"] * self.scale * self.zoom / 2.0)

    def _hover_rect(self, pos):
        r = self._hover_radius() + 3
        return QtCore.QRectF(pos.x() - r, pos.y() - r, 2 * r, 2 * r).toAlignedRect()

    def _paint_hover(self, p):
        if self._hover is None or self._pan is not None or self._space \
                or not self.handler.show_size:
            return
        r = self._hover_radius()
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1.0))
        p.drawEllipse(self._hover, r + 0.5, r + 0.5)
        p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 160), 1.0))
        p.drawEllipse(self._hover, r - 0.5, r - 0.5)

    def _update_hover(self, pos):
        old = self._hover
        self._hover = pos
        if old is not None:
            self.update(self._hover_rect(old))
        if pos is not None:
            self.update(self._hover_rect(pos))

    def resizeEvent(self, event):
        QtWidgets.QWidget.resizeEvent(self, event)
        if not self._fitted and self.width() > 50 and self.height() > 50:
            self._fitted = True
            self.fit()

    # ------------------------------------------------------------------
    #  Tablet
    # ------------------------------------------------------------------
    def tabletEvent(self, event):
        t = event.type()
        pos = event_pos(event)
        mods = event.modifiers()
        if t == QtCore.QEvent.TabletPress:
            if self._space or (event.buttons() & QtCore.Qt.MiddleButton):
                self._pan = pos
            elif self._input is None:
                self._curve = prefs.get("PressureCurve")
                self._input = "tablet"
                self.handler.press(pos, geom.pressure_curve(event.pressure(), self._curve),
                                   mods)
        elif t == QtCore.QEvent.TabletMove:
            if self._pan is not None:
                self._pan_to(pos)
            elif self._input == "tablet":
                self.handler.move(pos, geom.pressure_curve(event.pressure(), self._curve),
                                  mods)
            else:
                self.handler.move(pos, None, mods)
                self._update_hover(pos)
        elif t == QtCore.QEvent.TabletRelease:
            if self._pan is not None:
                self._pan = None
            elif self._input == "tablet":
                self._input = None
                self.handler.release(pos, geom.pressure_curve(event.pressure(), self._curve),
                                     mods)
        event.accept()

    # ------------------------------------------------------------------
    #  Mouse
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if self._input == "tablet":
            return
        pos = event_pos(event)
        b = event.button()
        if b == QtCore.Qt.MiddleButton or (b == QtCore.Qt.LeftButton and self._space):
            self._pan = pos
            self.setCursor(QtCore.Qt.ClosedHandCursor)
        elif b == QtCore.Qt.LeftButton and self._input is None:
            self._input = "mouse"
            self.handler.press(pos, None, event.modifiers())
        elif b == QtCore.Qt.RightButton:
            right = getattr(self.handler, "right_click", None)
            if not (right and right(pos)):
                self.handler.cancel()
                self._input = None

    def mouseMoveEvent(self, event):
        pos = event_pos(event)
        if self._pan is not None:
            self._pan_to(pos)
            return
        if self._input == "tablet":
            return
        self.handler.move(pos, None, event.modifiers())
        if self._input is None:
            self._update_hover(pos)

    def mouseReleaseEvent(self, event):
        if self._pan is not None and event.button() in (QtCore.Qt.MiddleButton,
                                                        QtCore.Qt.LeftButton):
            self._pan = None
            self.setCursor(QtCore.Qt.OpenHandCursor if self._space else QtCore.Qt.CrossCursor)
        elif self._input == "mouse" and event.button() == QtCore.Qt.LeftButton:
            self._input = None
            self.handler.release(event_pos(event), None, event.modifiers())

    def mouseDoubleClickEvent(self, event):
        dbl = getattr(self.handler, "double_click", None)
        if dbl is not None and event.button() == QtCore.Qt.LeftButton:
            dbl(event_pos(event))
        else:
            self.mousePressEvent(event)

    def leaveEvent(self, event):
        self._update_hover(None)

    def _pan_to(self, pos):
        d = pos - self._pan
        self._pan = pos
        self.offset = self.offset + d
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self.set_zoom(self.zoom * (1.0015 ** delta), event_pos(event))
        event.accept()

    # ------------------------------------------------------------------
    #  Keyboard
    # ------------------------------------------------------------------
    def event(self, event):
        # Take our keys before FreeCAD's global shortcuts
        if event.type() == QtCore.QEvent.ShortcutOverride and _key_code(event) in _OWN_KEYS:
            event.accept()
            return True
        return QtWidgets.QWidget.event(self, event)

    def keyPressEvent(self, event):
        k = _key_code(event)
        mods = event.modifiers()
        ctrl = bool(mods & QtCore.Qt.ControlModifier)
        shift = bool(mods & QtCore.Qt.ShiftModifier)
        if k == int(QtCore.Qt.Key_Z) and ctrl:
            self.handler.cancel()
            if shift:
                self.undo_stack.redo()
            else:
                self.undo_stack.undo()
        elif k == int(QtCore.Qt.Key_Y) and ctrl:
            self.handler.cancel()
            self.undo_stack.redo()
        elif k == int(QtCore.Qt.Key_C) and ctrl:
            self.copy_render()
        elif k == int(QtCore.Qt.Key_V) and ctrl:
            self.handler.cancel()
            self.paste()
        elif ctrl:
            QtWidgets.QWidget.keyPressEvent(self, event)
        elif self.handler.key(k, mods):
            pass
        elif k in _TOOL_KEYS and self._input is None:
            self.set_tool(_TOOL_KEYS[k])
        elif k == int(QtCore.Qt.Key_BracketLeft):
            self.set_size(self.current()["size"] / 1.2)
        elif k == int(QtCore.Qt.Key_BracketRight):
            self.set_size(self.current()["size"] * 1.2)
        elif k == int(QtCore.Qt.Key_F):
            self.fit()
        elif k == int(QtCore.Qt.Key_Space):
            if not event.isAutoRepeat():
                self._space = True
                self.setCursor(QtCore.Qt.OpenHandCursor)
                self._update_hover(self._hover)
        else:
            QtWidgets.QWidget.keyPressEvent(self, event)

    def keyReleaseEvent(self, event):
        if _key_code(event) == int(QtCore.Qt.Key_Space) and not event.isAutoRepeat():
            self._space = False
            if self._pan is None:
                self.setCursor(QtCore.Qt.CrossCursor)
            self._update_hover(self._hover)
        else:
            QtWidgets.QWidget.keyReleaseEvent(self, event)


# ----------------------------------------------------------------------
#  Colour swatches
# ----------------------------------------------------------------------
def color_icon(color, size=16):
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtGui.QColor(color))
    p = QtGui.QPainter(pix)
    p.setPen(QtGui.QColor(60, 60, 60))
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return QtGui.QIcon(pix)


class SwatchBar(QtWidgets.QWidget):
    """Palette selector and a row of colour swatches."""

    colorPicked = QtCore.Signal(str)

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.palettes = model.load_palettes()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.combo = QtWidgets.QComboBox()
        for name, _colors in self.palettes:
            self.combo.addItem(tr_data(name))
        lay.addWidget(self.combo)
        self.row = QtWidgets.QHBoxLayout()
        self.row.setSpacing(1)
        lay.addLayout(self.row)
        self.combo.currentIndexChanged.connect(self._fill)
        self._fill(0)

    def _fill(self, index):
        while self.row.count():
            w = self.row.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        if not (0 <= index < len(self.palettes)):
            return
        for label, color in self.palettes[index][1]:
            b = QtWidgets.QToolButton()
            b.setAutoRaise(True)
            b.setIcon(color_icon(color, 14))
            b.setIconSize(QtCore.QSize(14, 14))
            b.setToolTip("%s  %s" % (label, color))
            b.clicked.connect(lambda _c=False, col=color: self.colorPicked.emit(col))
            self.row.addWidget(b)


# ----------------------------------------------------------------------
#  Paper / layers panel
# ----------------------------------------------------------------------
class LayersPanel(QtWidgets.QWidget):
    """Paper of the sheet and visibility / opacity of each layer: the
    widget fallback of resources/qml/LayersPanel.qml (custom QML, rule 2)."""

    def __init__(self, canvas, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.canvas = canvas
        sheet = canvas.sheet
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        g = QtWidgets.QGroupBox(tr("Paper"))
        gl = QtWidgets.QVBoxLayout(g)
        self.paper = QtWidgets.QComboBox()
        for key, label, _color in model.PAPERS:
            self.paper.addItem(tr_data(label), key)
        self.paper.setCurrentIndex(max(0, self.paper.findData(sheet.paper)))
        self.paper.currentIndexChanged.connect(
            lambda _i: canvas.set_paper(self.paper.currentData()))
        gl.addWidget(self.paper)
        lay.addWidget(g)

        g = QtWidgets.QGroupBox(tr("Layers"))
        grid = QtWidgets.QGridLayout(g)
        users = {}
        for key in model.TOOL_KEYS:
            t = model.TOOLS[key]
            if t["kind"] != "eraser":
                users.setdefault(t["layer"], []).append(tr_data(t["label"]))
        row = 0
        for key, label, _blend in reversed(model.LAYERS):    # top layer first
            if key not in model.PANEL_LAYERS:
                continue
            info = sheet.layers[key]
            check = QtWidgets.QCheckBox(tr_data(label))
            check.setChecked(info["visible"])
            check.setToolTip(", ".join(users.get(key, [])))
            check.toggled.connect(lambda on, k=key: canvas.set_layer(k, visible=on))
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(int(round(info["opacity"] * 100)))
            slider.setToolTip(tr("Layer opacity"))
            slider.valueChanged.connect(
                lambda v, k=key: canvas.set_layer(k, opacity=v / 100.0))
            grid.addWidget(check, row, 0)
            grid.addWidget(slider, row, 1)
            row += 1
        lay.addWidget(g)
        lay.addStretch(1)


# ----------------------------------------------------------------------
#  Board (MDI tab content)
# ----------------------------------------------------------------------
def image_filter():
    """File dialog filter of every picture format Qt reads."""
    exts = sorted(set("*." + bytes(f).decode().lower()
                      for f in QtGui.QImageReader.supportedImageFormats()))
    return tr("Images ({patterns})").format(patterns=" ".join(exts))


def export_png_dialog(parent, sheet, default_path):
    """Ask for a file name and write the sheet as PNG. Returns the path or
    None."""
    path, _flt = QtWidgets.QFileDialog.getSaveFileName(
        parent, tr("Export sheet as PNG"), default_path, tr("PNG image (*.png)"))
    if not path:
        return None
    if not path.lower().endswith(".png"):
        path += ".png"
    if not comp_mod.save_png(sheet, path):
        QtWidgets.QMessageBox.warning(parent, "Croquis",
                                      tr("Could not write {path}.").format(path=path))
        return None
    return path


class SheetBoard(QtWidgets.QWidget):
    """Toolbar + tool options + canvas + paper / layers panel + status
    line. `on_apply(board)` writes the sheet into the document (button
    "Update 3D" and closing); `export_path` is the default file name of the
    PNG export."""

    def __init__(self, sheet, title, on_apply=None, export_path="", parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.on_apply = on_apply
        self.export_path = export_path
        self._edited = False        # paper / layer changes (not in the undo stack)
        self.setWindowTitle(title)
        self.setWindowIcon(QtGui.QIcon(icon("Croquis.svg")))

        self.canvas = SheetCanvas(sheet, self)
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setIconSize(QtCore.QSize(22, 22))
        self._build_toolbar()
        # side panel: tool options (generic panel model) above paper / layers
        from .. import panels, qml_host
        self.side = QtWidgets.QWidget(self)
        side = QtWidgets.QVBoxLayout(self.side)
        side.setContentsMargins(0, 0, 0, 0)
        self.options, self.options_bridge, self.options_kind = qml_host.build_panel(
            panels.tool_options_model(self.canvas), self.side)
        side.addWidget(self.options)
        self.image_panel, self.image_bridge, self.image_kind = qml_host.build_panel(
            panels.image_model(self.canvas), self.side)
        side.addWidget(self.image_panel)
        self.layers, self.layers_kind = self._layers_panel()
        side.addWidget(self.layers, 1)
        self.status = QtWidgets.QLabel()
        self.status.setContentsMargins(6, 2, 6, 2)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        split.addWidget(self.canvas)
        split.addWidget(self.side)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setCollapsible(0, False)
        split.setSizes([1000, 240])

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.toolbar)
        lay.addWidget(split, 1)
        lay.addWidget(self.status)

        c = self.canvas
        c.toolChanged.connect(self._sync_tool)
        c.settingsChanged.connect(self._sync_settings)
        c.zoomChanged.connect(lambda _z: self._sync_status())
        c.undo_stack.indexChanged.connect(lambda _i: self._sync_status())
        c.sheetEdited.connect(self._on_edited)
        self._sync_tool(c.tool)
        self._sync_settings()
        self._sync_status()
        c.setFocus()

    def _layers_panel(self):
        """Custom QML paper / layers palette, else the widget panel."""
        from .. import qml_host
        from ..bridge import I18n, LayersBridge, make_theme
        if qml_host.quick_usable():
            try:
                bridge = LayersBridge(self.canvas, theme=make_theme(self))
                view = qml_host.make_view("LayersPanel.qml",
                                          {"layers": bridge, "i18n": I18n(bridge)}, self.side)
                bridge.setParent(view)      # outlives the QML scene
                self.layers_bridge = bridge
                return view, "qml"
            except Exception as exc:
                import FreeCAD as App
                App.Console.PrintWarning("Croquis: QML layers panel unavailable (%s)\n" % exc)
        return LayersPanel(self.canvas, self.side), "widgets"

    @property
    def sheet(self):
        return self.canvas.sheet

    def is_modified(self):
        return self._edited or not self.canvas.undo_stack.isClean()

    def mark_saved(self):
        self._edited = False
        self.canvas.undo_stack.setClean()

    def _on_edited(self):
        self._edited = True
        self._sync_status()

    # --- toolbar
    def _build_toolbar(self):
        tb = self.toolbar
        c = self.canvas
        self.tool_actions = {}
        group = QActionGroup(self)
        group.setExclusive(True)
        for key, icon_file, shortcut in BOARD_TOOLS:
            text = tool_label(key)
            a = QAction(QtGui.QIcon(icon(icon_file)), text, self)
            a.setToolTip("%s (%s)" % (text, QtGui.QKeySequence(int(shortcut)).toString()))
            a.setCheckable(True)
            a.triggered.connect(lambda _c=False, k=key: c.set_tool(k))
            group.addAction(a)
            tb.addAction(a)
            self.tool_actions[key] = a
        tb.addSeparator()

        self.color_btn = QtWidgets.QToolButton()
        self.color_btn.setToolTip(tr("Other colour…"))
        self.color_btn.clicked.connect(self._pick_color)
        self.color_action = tb.addWidget(self.color_btn)
        self.swatches = SwatchBar()
        self.swatches.colorPicked.connect(c.set_color)
        self.swatch_action = tb.addWidget(self.swatches)
        tb.addSeparator()

        tb.addWidget(QtWidgets.QLabel(" " + tr("Size:") + " "))
        self.size_spin = QtWidgets.QDoubleSpinBox()
        self.size_spin.setRange(SIZE_MIN, SIZE_MAX)
        self.size_spin.setDecimals(2)
        self.size_spin.setSingleStep(0.1)
        self.size_spin.setSuffix(" mm")
        self.size_spin.setToolTip(tr("Tool size ([ and ] keys)"))
        self.size_spin.valueChanged.connect(c.set_size)
        tb.addWidget(self.size_spin)
        tb.addWidget(QtWidgets.QLabel(" " + tr("Opacity:") + " "))
        self.opacity_spin = QtWidgets.QSpinBox()
        self.opacity_spin.setRange(1, 100)
        self.opacity_spin.setSuffix(" %")
        self.opacity_spin.valueChanged.connect(lambda v: c.set_opacity(v / 100.0))
        tb.addWidget(self.opacity_spin)
        tb.addSeparator()

        undo_a = c.undo_stack.createUndoAction(self, tr("Undo"))
        undo_a.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowBack))
        undo_a.setToolTip(tr("Undo the last stroke (Ctrl+Z)"))
        redo_a = c.undo_stack.createRedoAction(self, tr("Redo"))
        redo_a.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowForward))
        redo_a.setToolTip(tr("Redo (Ctrl+Shift+Z)"))
        tb.addAction(undo_a)
        tb.addAction(redo_a)
        a = tb.addAction(tr("Fit"))
        a.setToolTip(tr("Fit the sheet in the window (F)"))
        a.triggered.connect(c.fit)
        a = tb.addAction(tr("Clear"))
        a.setToolTip(tr("Erase every stroke of the sheet (can be undone)"))
        a.triggered.connect(self._clear)
        tb.addSeparator()
        a = tb.addAction(QtGui.QIcon(icon("InsertImage.svg")), tr("Insert image…"))
        a.setToolTip(tr("Put a picture on the sheet (also Ctrl+V or drag and drop)"))
        a.triggered.connect(self.insert_image)
        a = tb.addAction(QtGui.QIcon(icon("Capture3D.svg")), tr("Capture 3D view"))
        a.setToolTip(tr("Put a picture of the document's 3D view on the sheet, to draw on it"))
        a.triggered.connect(self.capture_3d)
        a = tb.addAction(QtGui.QIcon(icon("Guide3D.svg")), tr("3D guide…"))
        a.setToolTip(tr("Trace over the model: a true-size view along the sheet's normal, "
                        "under the strokes, never exported"))
        a.triggered.connect(self.guide_3d)
        a = tb.addAction(QtGui.QIcon(icon("ExportPng.svg")), tr("Export PNG…"))
        a.setToolTip(tr("Save the sheet as a PNG image"))
        a.triggered.connect(lambda: export_png_dialog(self, self.sheet, self.export_path))
        if self.on_apply is not None:
            a = tb.addAction(tr("Update 3D"))
            a.setToolTip(tr("Write the strokes into the document and refresh the "
                            "image plane (also done when the board closes)"))
            a.triggered.connect(self.apply)

    def _sync_tool(self, key):
        a = self.tool_actions.get(key)
        if a is not None:
            a.setChecked(True)
        self._sync_settings()

    def _sync_settings(self):
        c = self.canvas
        st = c.current()
        erasing = c.tool == "eraser"
        editing_nothing = c.tool == "edit" and c.selection() is None
        self.color_action.setVisible(not erasing)
        self.swatch_action.setVisible(not erasing)
        for w in (self.color_btn, self.swatches, self.size_spin, self.opacity_spin):
            w.setEnabled(not editing_nothing)
        self.color_btn.setIcon(color_icon(st["color"], 18))
        for w, v in ((self.size_spin, st["size"]),
                     (self.opacity_spin, int(round(st["opacity"] * 100)))):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self.options_bridge.refresh()
        image = c.selected_image() is not None
        self.image_panel.setVisible(image)
        if image:
            self.image_bridge.refresh()
        for w in (self.color_btn, self.swatches, self.size_spin):
            w.setEnabled(not editing_nothing and not image)

    def _sync_status(self):
        s = self.sheet
        w, h = s.pixel_size()
        text = tr("{w:g} × {h:g} mm, {dpi} dpi ({pw} × {ph} px)   |   zoom {zoom} %   |   "
                  "{n} stroke(s)").format(w=s.width, h=s.height, dpi=s.dpi, pw=w, ph=h,
                                          zoom=int(round(self.canvas.zoom * 100)),
                                          n=len(s.strokes))
        k = s.plane_scale
        if abs(k - 1.0) > 1e-9:
            ratio = ("1:%g" % round(k, 3)) if k >= 1 else ("%g:1" % round(1 / k, 3))
            text += "   |   " + tr("3D scale {ratio}").format(ratio=ratio)
        self.status.setText(text)

    def guide_3d(self):
        from .. import panels, qml_host
        qml_host.run_dialog(panels.guide_model(self), parent=self)

    def capture_3d(self):
        from .. import panels, qml_host
        qml_host.run_dialog(panels.capture_model(self.canvas.document(), self), parent=self)

    def insert_image(self):
        from .. import images
        path, _flt = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("Insert image"), self.export_path and os.path.dirname(self.export_path),
            image_filter())
        if not path:
            return
        try:
            self.canvas.add_picture(images.read(path), path)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Croquis", str(exc))

    def _pick_color(self):
        col = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.canvas.current()["color"]),
                                              self, tr("Stroke colour"))
        if col.isValid():
            self.canvas.set_color(col.name())

    def _clear(self):
        if not self.sheet.strokes:
            return
        r = QtWidgets.QMessageBox.question(
            self, "Croquis", tr("Erase every stroke of the sheet? (Undo brings them back.)"))
        if r == QtWidgets.QMessageBox.Yes:
            self.canvas.clear_sheet()

    # --- document
    def apply(self):
        """Write the sheet into the document through on_apply."""
        if self.on_apply is None:
            return
        self.canvas.cancel_stroke()
        self.on_apply(self)
        self.mark_saved()

    def closeEvent(self, event):
        if self.is_modified():
            try:
                self.apply()
            except Exception as exc:
                import FreeCAD as App
                App.Console.PrintError("Croquis: sheet not saved (%s)\n" % exc)
        event.accept()
