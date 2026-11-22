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
transform, only inside the region Qt asks to repaint.

While the pen moves, the stroke grows in a "live" buffer the size of the
sheet (brushes.StrokeRaster, span by span, one input point behind so the
curve can be interpolated). On release, the live buffer is cleared and the
stroke is pushed on the undo stack, which paints its final version (with
grain and end tapers) through the compositor.
"""

import math
import time

from ..qt import (QtCore, QtGui, QtWidgets, QUndoStack, QAction, QActionGroup,
                  event_pos)
from .. import model, prefs, icon
from ..i18n import tr, tr_data
from ..render import compositor as comp_mod
from ..render import brushes
from ..render import stroke_geom as geom
from . import undo

ZOOM_MIN = 0.03
ZOOM_MAX = 16.0
SIZE_MIN = 0.05     # mm
SIZE_MAX = 60.0
BACKGROUND = QtGui.QColor(88, 90, 94)

# Keys handled by the canvas even if FreeCAD has a shortcut on them
_OWN_KEYS = set(int(k) for k in (
    QtCore.Qt.Key_P, QtCore.Qt.Key_M, QtCore.Qt.Key_F, QtCore.Qt.Key_Space,
    QtCore.Qt.Key_BracketLeft, QtCore.Qt.Key_BracketRight,
    QtCore.Qt.Key_Z, QtCore.Qt.Key_Y))


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


class SheetCanvas(QtWidgets.QWidget):
    """Zoomable drawing surface of one sheet."""

    toolChanged = QtCore.Signal(str)
    settingsChanged = QtCore.Signal()
    zoomChanged = QtCore.Signal(float)

    def __init__(self, sheet, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.sheet = sheet
        self.compositor = comp_mod.Compositor(sheet)
        self.undo_stack = QUndoStack(self)
        self.tool_settings = dict(
            (k, {"color": t["color"], "size": t["size"], "opacity": t["opacity"]})
            for k, t in model.TOOLS.items())
        self.tool = "pencil"
        self.zoom = 1.0
        self.offset = QtCore.QPointF(0, 0)
        self._fitted = False
        self._checker = _checker_brush()
        # stroke in progress
        self._stroke = None
        self._raster = None
        self._live_img = None
        self._input = None          # "tablet" / "mouse" while drawing
        self._stab = None
        self._speed = None
        self._curve = 1.0
        self._raw_last = None
        # navigation
        self._pan = None
        self._space = False
        self._hover = None

        self.setMouseTracking(True)
        if hasattr(self, "setTabletTracking"):
            self.setTabletTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
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

    # ------------------------------------------------------------------
    #  Tool settings
    # ------------------------------------------------------------------
    def current(self):
        return self.tool_settings[self.tool]

    def set_tool(self, key):
        if key not in self.tool_settings or key == self.tool:
            return
        self.tool = key
        self.toolChanged.emit(key)
        self.settingsChanged.emit()
        self._update_hover(self._hover)

    def set_color(self, color):
        self.current()["color"] = color
        self.settingsChanged.emit()

    def set_size(self, size):
        size = min(max(float(size), SIZE_MIN), SIZE_MAX)
        if abs(size - self.current()["size"]) > 1e-9:
            self.current()["size"] = size
            self.settingsChanged.emit()
            self._update_hover(self._hover)

    def set_opacity(self, opacity):
        self.current()["opacity"] = min(max(float(opacity), 0.01), 1.0)
        self.settingsChanged.emit()

    # ------------------------------------------------------------------
    #  Repaint hook (undo commands)
    # ------------------------------------------------------------------
    def sheet_changed(self, rect):
        if rect is None:
            self.update()
        else:
            self.update(self.to_widget_rect(rect))

    def clear_sheet(self):
        if self.sheet.strokes:
            self.undo_stack.push(undo.ClearSheet(self))

    # ------------------------------------------------------------------
    #  Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        try:
            region = QtCore.QRectF(event.rect())
            p.fillRect(region, BACKGROUND)
            target = self.sheet_rect_widget()
            visible = region.intersected(target)
            if not visible.isEmpty():
                if model.paper_color(self.sheet.paper) is None:
                    p.fillRect(visible, self._checker)
                # source rectangle in sheet pixels of the visible part
                z = self.zoom
                src = QtCore.QRectF((visible.x() - self.offset.x()) / z,
                                    (visible.y() - self.offset.y()) / z,
                                    visible.width() / z, visible.height() / z)
                p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, z < 2.0)
                p.drawImage(visible, self.compositor.image, src)
                if self._stroke is not None and self._live_img is not None:
                    p.setOpacity(self._stroke.opacity)
                    p.setCompositionMode(comp_mod.blend_mode(
                        model.layer_blend(self._stroke.layer)))
                    p.drawImage(visible, self._live_img, src)
                    p.setOpacity(1.0)
                    p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
            p.setPen(QtGui.QPen(QtGui.QColor(30, 30, 30), 1))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawRect(target.adjusted(-0.5, -0.5, 0.5, 0.5))
            self._paint_hover(p)
        finally:
            p.end()

    def _hover_radius(self):
        return max(1.5, self.current()["size"] * self.scale * self.zoom / 2.0)

    def _hover_rect(self, pos):
        r = self._hover_radius() + 3
        return QtCore.QRectF(pos.x() - r, pos.y() - r, 2 * r, 2 * r).toAlignedRect()

    def _paint_hover(self, p):
        if self._hover is None or self._pan is not None or self._space:
            return
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        r = self._hover_radius()
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
    #  Strokes
    # ------------------------------------------------------------------
    def _begin(self, pos, pressure, kind):
        st = self.current()
        self._stroke = model.Stroke(self.tool, st["color"], st["size"], st["opacity"],
                                    model.TOOLS[self.tool]["layer"], [])
        c = self.compositor
        if self._live_img is None or self._live_img.width() != c.w \
                or self._live_img.height() != c.h:
            self._live_img = comp_mod.new_image(c.w, c.h)
        self._raster = brushes.StrokeRaster(self._live_img, (0, 0), self._stroke, self.scale)
        self._stab = geom.Stabilizer(prefs.get("Smoothing"))
        self._speed = geom.SpeedPressure() \
            if kind == "mouse" and prefs.get("MouseSpeedPressure") else None
        self._input = kind
        self._raw_last = None
        self._add_point(pos, pressure)

    def _add_point(self, pos, pressure):
        s = self.to_sheet_px(pos)
        x, y = s.x() / self.scale, s.y() / self.scale
        self._raw_last = (x, y, pressure)
        x, y = self._stab.feed(x, y)
        if self._speed is not None:
            pressure = self._speed.feed(x, y, time.monotonic())
        pts = self._stroke.points
        if pts and math.hypot(x - pts[-1][0], y - pts[-1][1]) < 0.4 / self.scale:
            return
        pts.append((x, y, pressure))
        # spans with one point of look-ahead are final
        r = self._raster.draw_to(len(pts) - 2)
        if r is not None:
            self.update(self.to_widget_rect(r))

    def _end(self):
        stroke = self._stroke
        pts = stroke.points
        if self._raw_last is not None and pts:
            x, y, p = self._raw_last
            if self._speed is not None:
                p = pts[-1][2]
            if math.hypot(x - pts[-1][0], y - pts[-1][1]) >= 0.4 / self.scale:
                pts.append((x, y, p))
        if self._speed is not None and len(pts) > 2:
            # the mouse has no pressure: give the thrown-line ends by hand
            stroke.points = geom.taper_ends(pts, 3.0 + stroke.size, 5.0 + stroke.size)
        self._live_img.fill(0)
        self._stroke = None
        self._raster = None
        self._input = None
        if stroke.points:
            self.undo_stack.push(undo.AddStroke(self, stroke))
        else:
            self.update()

    def cancel_stroke(self):
        if self._stroke is not None:
            self._live_img.fill(0)
            self._stroke = None
            self._raster = None
            self._input = None
            self.update()

    # ------------------------------------------------------------------
    #  Tablet
    # ------------------------------------------------------------------
    def tabletEvent(self, event):
        t = event.type()
        pos = event_pos(event)
        if t == QtCore.QEvent.TabletPress:
            if self._space or (event.buttons() & QtCore.Qt.MiddleButton):
                self._pan = pos
            elif self._stroke is None:
                self._curve = prefs.get("PressureCurve")
                self._begin(pos, geom.pressure_curve(event.pressure(), self._curve), "tablet")
        elif t == QtCore.QEvent.TabletMove:
            if self._pan is not None:
                self._pan_to(pos)
            elif self._input == "tablet":
                self._add_point(pos, geom.pressure_curve(event.pressure(), self._curve))
            else:
                self._update_hover(pos)
        elif t == QtCore.QEvent.TabletRelease:
            if self._pan is not None:
                self._pan = None
            elif self._input == "tablet":
                self._end()
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
        elif b == QtCore.Qt.LeftButton and self._stroke is None:
            self._begin(pos, 1.0, "mouse")
        elif b == QtCore.Qt.RightButton and self._stroke is not None:
            self.cancel_stroke()

    def mouseMoveEvent(self, event):
        pos = event_pos(event)
        if self._pan is not None:
            self._pan_to(pos)
        elif self._input == "mouse":
            self._add_point(pos, 1.0)
        elif self._input is None:
            self._update_hover(pos)

    def mouseReleaseEvent(self, event):
        if self._pan is not None and event.button() in (QtCore.Qt.MiddleButton,
                                                        QtCore.Qt.LeftButton):
            self._pan = None
            self.setCursor(QtCore.Qt.OpenHandCursor if self._space else QtCore.Qt.CrossCursor)
        elif self._input == "mouse" and event.button() == QtCore.Qt.LeftButton:
            self._end()

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
        # Take our keys before FreeCAD's global shortcuts (Ctrl+Z is
        # Std_Undo, which would undo in the 3D document instead)
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
            if shift:
                self.undo_stack.redo()
            else:
                self.undo_stack.undo()
        elif k == int(QtCore.Qt.Key_Y) and ctrl:
            self.undo_stack.redo()
        elif ctrl:
            QtWidgets.QWidget.keyPressEvent(self, event)
        elif k == int(QtCore.Qt.Key_P):
            self.set_tool("pencil")
        elif k == int(QtCore.Qt.Key_M):
            self.set_tool("marker")
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
#  Board (MDI tab content)
# ----------------------------------------------------------------------
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
    """Toolbar + canvas + status line. `on_apply(board)` writes the sheet
    into the document (button "Update 3D" and closing); `export_path` is
    the default file name of the PNG export."""

    def __init__(self, sheet, title, on_apply=None, export_path="", parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.on_apply = on_apply
        self.export_path = export_path
        self.setWindowTitle(title)
        self.setWindowIcon(QtGui.QIcon(icon("Croquis.svg")))

        self.canvas = SheetCanvas(sheet, self)
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setIconSize(QtCore.QSize(22, 22))
        self._build_toolbar()
        self.status = QtWidgets.QLabel()
        self.status.setContentsMargins(6, 2, 6, 2)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.toolbar)
        lay.addWidget(self.canvas, 1)
        lay.addWidget(self.status)

        self.canvas.toolChanged.connect(self._sync_tool)
        self.canvas.settingsChanged.connect(self._sync_settings)
        self.canvas.zoomChanged.connect(lambda _z: self._sync_status())
        self.canvas.undo_stack.indexChanged.connect(lambda _i: self._sync_status())
        self._sync_tool(self.canvas.tool)
        self._sync_settings()
        self._sync_status()
        self.canvas.setFocus()

    @property
    def sheet(self):
        return self.canvas.sheet

    def is_modified(self):
        return not self.canvas.undo_stack.isClean()

    def mark_saved(self):
        self.canvas.undo_stack.setClean()

    # --- toolbar
    def _build_toolbar(self):
        tb = self.toolbar
        c = self.canvas
        self.tool_actions = {}
        group = QActionGroup(self)
        group.setExclusive(True)
        for key, icon_file, shortcut in (("pencil", "Pencil.svg", "P"),
                                         ("marker", "Marker.svg", "M")):
            a = QAction(QtGui.QIcon(icon(icon_file)),
                        tr_data(model.TOOLS[key]["label"]), self)
            a.setToolTip("%s (%s)" % (tr_data(model.TOOLS[key]["label"]), shortcut))
            a.setCheckable(True)
            a.triggered.connect(lambda _c=False, k=key: c.set_tool(k))
            group.addAction(a)
            tb.addAction(a)
            self.tool_actions[key] = a
        tb.addSeparator()

        self.color_btn = QtWidgets.QToolButton()
        self.color_btn.setToolTip(tr("Other colour…"))
        self.color_btn.clicked.connect(self._pick_color)
        tb.addWidget(self.color_btn)
        self.swatches = SwatchBar()
        self.swatches.colorPicked.connect(c.set_color)
        tb.addWidget(self.swatches)
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

    def _sync_settings(self):
        st = self.canvas.current()
        self.color_btn.setIcon(color_icon(st["color"], 18))
        for w, v in ((self.size_spin, st["size"]),
                     (self.opacity_spin, int(round(st["opacity"] * 100)))):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)

    def _sync_status(self):
        s = self.sheet
        w, h = s.pixel_size()
        self.status.setText(
            tr("{w:g} × {h:g} mm, {dpi} dpi ({pw} × {ph} px)   |   zoom {zoom} %   |   "
               "{n} stroke(s)").format(w=s.width, h=s.height, dpi=s.dpi, pw=w, ph=h,
                                       zoom=int(round(self.canvas.zoom * 100)),
                                       n=len(s.strokes)))

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
