# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - drawing tools of the board
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
tools.py (Croquis) - what each tool does with the pen.

The canvas (view.SheetCanvas) handles navigation and input devices, then
hands every gesture to the active Tool:

    press(pos, pressure, mods)   pressure is None for a mouse
    move(pos, pressure, mods)
    release(pos, pressure, mods)
    key(k, mods) -> bool         Delete, Backspace, Escape, Return...
    cancel()
    paint_sheet(painter)         live images, through canvas.draw_image()
    paint_overlay(painter)       handles, rubber bands (widget coordinates)

pos is in widget coordinates; canvas.to_mm() converts it. Finished strokes
go through the canvas undo stack (undo.py), never straight into the sheet.
"""

import math
import time

from .. import model, prefs
from ..qt import QtCore, QtGui
from ..render import brushes
from ..render import stroke_geom as geom
from . import undo

SHIFT = QtCore.Qt.ShiftModifier
HANDLE_PX = 7.0         # pick radius of control points, screen pixels
PICK_PX = 6.0           # pick distance of strokes, screen pixels


def _shift(mods):
    return bool(mods & SHIFT)


class Tool(object):
    """Base class: no gesture."""

    show_size = True    # the canvas draws the brush outline under the pen

    def __init__(self, canvas, key):
        self.c = canvas
        self.name = key

    @property
    def busy(self):
        return False

    @property
    def settings(self):
        return self.c.tool_settings[self.name]

    def press(self, pos, pressure, mods):
        pass

    def move(self, pos, pressure, mods):
        pass

    def release(self, pos, pressure, mods):
        pass

    def key(self, k, mods):
        return False

    def cancel(self):
        pass

    def paint_sheet(self, painter):
        pass

    def paint_overlay(self, painter):
        pass

    def new_stroke(self, points=None):
        st = self.settings
        t = model.TOOLS[self.name]
        params = None
        if t["kind"] == "vector":
            keys = model.DEFAULT_ARROW if self.name == "arrow" else model.DEFAULT_PROFILE
            params = dict((k, st[k]) for k in keys)
        layer = st.get("target", t["layer"]) if t["kind"] == "eraser" else t["layer"]
        return model.Stroke(self.name, st["color"], st["size"], st["opacity"], layer,
                            points or [], params)


# ----------------------------------------------------------------------
#  Raster brushes and the soft eraser
# ----------------------------------------------------------------------
class BrushTool(Tool):
    """Pencil, grease pencil, marker, highlight and soft eraser. Shift at
    the press draws a straight line from there.

    The stroke grows in the canvas live buffer span by span. For the
    eraser the live buffer is applied at once on the layers it works on
    (restored from a snapshot first, so a span is never erased twice),
    which shows the exact result while erasing; the layers are put back
    on release and the eraser stroke goes through the undo stack."""

    def __init__(self, canvas, key):
        Tool.__init__(self, canvas, key)
        self.stroke = None

    @property
    def busy(self):
        return self.stroke is not None

    @property
    def erasing(self):
        return model.tool_kind(self.name) == "eraser"

    def press(self, pos, pressure, mods):
        c = self.c
        self.stroke = self.new_stroke()
        self.live = c.live_buffer()
        self.raster = brushes.StrokeRaster(self.live, (0, 0), self.stroke, c.scale)
        self.stab = geom.Stabilizer(prefs.get("Smoothing"))
        self.speed = geom.SpeedPressure() \
            if pressure is None and prefs.get("MouseSpeedPressure") else None
        self.raw_last = None
        self.dirty = None           # union of the live area, sheet pixels
        self.straight = None
        if _shift(mods):
            x, y = c.to_mm(pos)
            self.straight = (x, y, 1.0 if pressure is None else pressure)
        self.snapshots = {}
        if self.erasing:
            for k in model.eraser_targets(self.stroke):
                img = c.compositor.layers.get(k)
                if img is not None:
                    self.snapshots[k] = img.copy()
        self.move(pos, pressure, mods)

    def move(self, pos, pressure, mods):
        if self.stroke is None:
            return
        c = self.c
        x, y = c.to_mm(pos)
        if self.straight is not None:
            x0, y0, p0 = self.straight
            p = 1.0 if pressure is None else pressure
            pts = geom.straight_points(x0, y0, x, y, p0, p, 2.0 / c.scale)
            if self.speed is not None and len(pts) > 2:
                pts = geom.taper_ends(pts, 3.0 + self.stroke.size, 5.0 + self.stroke.size)
            self.stroke.points = pts
            old = self.dirty
            self._clear_live(old)
            self.raster = brushes.StrokeRaster(self.live, (0, 0), self.stroke, c.scale)
            r = self.raster.draw_to(len(pts) - 1) if len(pts) > 1 else self.raster.draw_dot()
            self._show(r, old)
            return
        self.raw_last = (x, y, pressure)
        x, y = self.stab.feed(x, y)
        p = 1.0 if pressure is None else pressure
        if self.speed is not None:
            p = self.speed.feed(x, y, time.monotonic())
        pts = self.stroke.points
        if pts and math.hypot(x - pts[-1][0], y - pts[-1][1]) < 0.4 / c.scale:
            return
        pts.append((x, y, p))
        # spans with one point of look-ahead are final
        self._show(self.raster.draw_to(len(pts) - 2))

    def release(self, pos, pressure, mods):
        if self.stroke is None:
            return
        stroke = self.stroke
        pts = stroke.points
        if self.straight is None:
            if self.raw_last is not None and pts:
                x, y, p = self.raw_last
                p = pts[-1][2] if (self.speed is not None or p is None) else p
                if math.hypot(x - pts[-1][0], y - pts[-1][1]) >= 0.4 / self.c.scale:
                    pts.append((x, y, p))
            if self.speed is not None and len(pts) > 2:
                # the mouse has no pressure: give the thrown-line ends by hand
                stroke.points = geom.taper_ends(pts, 3.0 + stroke.size, 5.0 + stroke.size)
        self._finish()
        if stroke.points:
            self.c.undo_stack.push(undo.AddStroke(self.c, stroke))

    def cancel(self):
        if self.stroke is not None:
            self._finish()

    def _finish(self):
        c = self.c
        if self.snapshots:
            for k, img in self.snapshots.items():
                c.compositor.layers[k] = img
            if self.dirty is not None:
                c.compositor.compose(self.dirty.toAlignedRect())
        self.snapshots = {}
        self.live.fill(0)
        if self.dirty is not None:
            c.sheet_changed(self.dirty.toAlignedRect())
        self.stroke = None

    def _clear_live(self, rect):
        if rect is None:
            return
        p = QtGui.QPainter(self.live)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_Clear)
        p.fillRect(rect, QtCore.Qt.transparent)
        p.end()

    def _show(self, r, old=None):
        """Repaint the area `r` (QRectF, sheet pixels) of the live stroke;
        `old` is the area of a previous version of it."""
        if old is not None:
            r = old if r is None else r.united(old)
        if r is None:
            return
        self.dirty = r if self.dirty is None else self.dirty.united(r)
        if self.erasing:
            c = self.c
            ir = r.toAlignedRect().intersected(c.compositor.bounds)
            for k, snap in self.snapshots.items():
                layer = c.compositor.layers[k]
                p = QtGui.QPainter(layer)
                p.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
                p.drawImage(ir.topLeft(), snap, ir)
                p.end()
                c.compositor.erase(k, self.live, QtCore.QPointF(ir.topLeft()),
                                   self.stroke.opacity, QtCore.QRectF(ir))
            c.compositor.compose(ir)
        self.c.sheet_changed(r)

    def paint_sheet(self, painter):
        if self.stroke is not None and not self.erasing:
            self.c.draw_image(painter, self.live, QtCore.QPoint(0, 0), self.stroke.opacity,
                              model.layer_blend(self.stroke.layer))


# ----------------------------------------------------------------------
#  Stroke eraser
# ----------------------------------------------------------------------
class StrokeEraserTool(Tool):
    """Removes whole strokes touched by the eraser circle (all kinds)."""

    def __init__(self, canvas, key):
        Tool.__init__(self, canvas, key)
        self.hits = None

    @property
    def busy(self):
        return self.hits is not None

    def press(self, pos, pressure, mods):
        self.hits = []
        self.move(pos, pressure, mods)

    def move(self, pos, pressure, mods):
        if self.hits is None:
            return
        x, y = self.c.to_mm(pos)
        radius = self.settings["size"] / 2.0
        target = self.settings.get("target", model.ALL_LAYERS)
        found = []
        for s in self.c.sheet.strokes:
            if s in self.hits or s.kind == "eraser":
                continue
            if target != model.ALL_LAYERS and s.layer != target:
                continue
            if not self.c.sheet.layers[s.layer]["visible"]:
                continue
            b = s.bounds()
            if b is None or x < b[0] - radius or x > b[2] + radius \
                    or y < b[1] - radius or y > b[3] + radius:
                continue
            d = geom.distance_to_polyline(brushes.stroke_polyline(s), x, y)
            if d <= radius + s.size / 2.0:
                found.append(s)
        if found:
            self.hits.extend(found)
            comp = self.c.compositor
            for s in found:
                comp.hidden.add(id(s))
            self.c.sheet_changed(comp.refresh_strokes(found))

    def release(self, pos, pressure, mods):
        hits = self.hits or []
        self.hits = None
        comp = self.c.compositor
        for s in hits:
            comp.hidden.discard(id(s))
        if hits:
            self.c.undo_stack.push(undo.RemoveStrokes(self.c, hits))

    def cancel(self):
        hits = self.hits or []
        self.hits = None
        for s in hits:
            self.c.compositor.hidden.discard(id(s))
        if hits:
            self.c.sheet_changed(self.c.compositor.refresh_strokes(hits))


# ----------------------------------------------------------------------
#  Vector strokes
# ----------------------------------------------------------------------
class VectorPreview(object):
    """Live rendering of a vector stroke (rendered whole at each change,
    which is cheap: one stroke)."""

    def __init__(self, canvas):
        self.c = canvas
        self.stroke = None
        self.img = None
        self.pos = None

    def set(self, stroke):
        old = self.rect()
        self.stroke = stroke
        self.img = self.pos = None
        if stroke is not None and len(stroke.points) >= 4:
            res = brushes.render_stroke(stroke, self.c.scale, self.c.compositor.bounds)
            if res is not None:
                self.img, self.pos = res
        new = self.rect()
        for r in (old, new):
            if r is not None:
                self.c.sheet_changed(r)

    def rect(self):
        if self.img is None:
            return None
        return QtCore.QRect(self.pos, self.img.size())

    def paint(self, painter):
        if self.img is not None:
            self.c.draw_image(painter, self.img, self.pos, self.stroke.opacity,
                              model.layer_blend(self.stroke.layer))


class LineTool(Tool):
    """Straight tapered line: press at one end, release at the other.
    Shift snaps the angle to 15° steps."""

    def __init__(self, canvas, key):
        Tool.__init__(self, canvas, key)
        self.start = None
        self.preview = VectorPreview(canvas)

    @property
    def busy(self):
        return self.start is not None

    def press(self, pos, pressure, mods):
        self.start = self.c.to_mm(pos)

    def move(self, pos, pressure, mods):
        if self.start is None:
            return
        x0, y0 = self.start
        x, y = self.c.to_mm(pos)
        if _shift(mods):
            x, y = geom.snap_angle(x0, y0, x, y)
        chain = geom.line_chain(x0, y0, x, y)
        self.preview.set(self.new_stroke([(px, py, 1.0) for px, py in chain]))

    def release(self, pos, pressure, mods):
        self.move(pos, pressure, mods)
        stroke = self.preview.stroke
        self.cancel()
        if stroke is not None:
            a, b = stroke.points[0], stroke.points[-1]
            if math.hypot(b[0] - a[0], b[1] - a[1]) > 0.3:
                self.c.undo_stack.push(undo.AddStroke(self.c, stroke))

    def cancel(self):
        self.start = None
        self.preview.set(None)

    def paint_sheet(self, painter):
        self.preview.paint(painter)


class SplineTool(Tool):
    """Tapered spline stroke, in two modes (settings["mode"]):

    freehand: draw freely; on release the path is fitted with Bezier
        curves (Schneider), smooth and editable afterwards;
    points:   click the points the curve goes through; click the last
        point again (or double-click, Enter, right-click) to finish,
        Backspace removes the last point, Escape cancels."""

    def __init__(self, canvas, key):
        Tool.__init__(self, canvas, key)
        self.raw = None         # freehand: input points (mm)
        self.anchors = []       # points mode
        self.hover = None
        self.preview = VectorPreview(canvas)

    @property
    def busy(self):
        return self.raw is not None or bool(self.anchors)

    @property
    def mode(self):
        mode = self.settings.get("mode", "freehand")
        return "freehand" if mode == "straight" else mode

    # --- freehand
    def press(self, pos, pressure, mods):
        x, y = self.c.to_mm(pos)
        if self.mode == "points":
            if self.anchors and self._near_last(pos):
                self.finish()
                return
            self.anchors.append((x, y))
            self._update_points()
            return
        self.stab = geom.Stabilizer(prefs.get("Smoothing"))
        self.raw = [self.stab.feed(x, y)]

    def move(self, pos, pressure, mods):
        x, y = self.c.to_mm(pos)
        if self.mode == "points":
            self.hover = (x, y)
            if self.anchors:
                self._update_points()
            return
        if self.raw is None:
            return
        x, y = self.stab.feed(x, y)
        last = self.raw[-1]
        if math.hypot(x - last[0], y - last[1]) < 0.3 / self.c.scale:
            return
        self.raw.append((x, y))
        self.c.sheet_changed(self._segment_rect(last, (x, y)))

    def release(self, pos, pressure, mods):
        if self.mode == "points" or self.raw is None:
            return
        x, y = self.c.to_mm(pos)
        raw = self.raw + [(x, y)]
        self._clear_raw()
        if len(raw) < 2:
            return
        # tolerance: about two screen pixels, at least 0.15 mm
        tol = max(0.15, 2.0 / (self.c.scale * self.c.zoom))
        chain = geom.fit_chain(raw, tol)
        if len(chain) >= 4:
            self.c.undo_stack.push(undo.AddStroke(
                self.c, self.new_stroke([(px, py, 1.0) for px, py in chain])))

    def _clear_raw(self):
        raw = self.raw
        self.raw = None
        if raw:
            xs = [p[0] for p in raw]
            ys = [p[1] for p in raw]
            s = self.c.scale
            self.c.sheet_changed(QtCore.QRectF(min(xs) * s, min(ys) * s,
                                               (max(xs) - min(xs)) * s + 1,
                                               (max(ys) - min(ys)) * s + 1).adjusted(-4, -4, 4, 4))

    def _segment_rect(self, a, b):
        s = self.c.scale
        return QtCore.QRectF(min(a[0], b[0]) * s, min(a[1], b[1]) * s,
                             abs(a[0] - b[0]) * s + 1, abs(a[1] - b[1]) * s + 1) \
            .adjusted(-4, -4, 4, 4)

    # --- points
    def _near_last(self, pos):
        last = self.c.to_widget(self.anchors[-1])
        return math.hypot(pos.x() - last.x(), pos.y() - last.y()) < HANDLE_PX

    def _update_points(self):
        pts = list(self.anchors)
        if self.hover is not None and math.hypot(
                self.hover[0] - pts[-1][0], self.hover[1] - pts[-1][1]) > 1e-6:
            pts.append(self.hover)
        if len(pts) >= 2:
            chain = geom.anchors_to_chain(pts)
            self.preview.set(self.new_stroke([(x, y, 1.0) for x, y in chain]))
        else:
            self.preview.set(None)
        self.c.update()

    def finish(self):
        anchors = self.anchors
        self.anchors = []
        self.preview.set(None)
        self.c.update()
        if len(anchors) >= 2:
            chain = geom.anchors_to_chain(anchors)
            self.c.undo_stack.push(undo.AddStroke(
                self.c, self.new_stroke([(x, y, 1.0) for x, y in chain])))

    def double_click(self, pos):
        if self.mode == "points" and self.anchors:
            self.finish()

    def right_click(self, pos):
        if self.mode == "points" and self.anchors:
            self.finish()
            return True
        return False

    def key(self, k, mods):
        if self.mode != "points" or not self.anchors:
            return False
        if k in (int(QtCore.Qt.Key_Return), int(QtCore.Qt.Key_Enter)):
            self.finish()
        elif k == int(QtCore.Qt.Key_Backspace):
            self.anchors.pop()
            self._update_points()
        elif k == int(QtCore.Qt.Key_Escape):
            self.cancel()
        else:
            return False
        return True

    def cancel(self):
        self._clear_raw()
        self.anchors = []
        self.preview.set(None)
        self.c.update()

    def paint_sheet(self, painter):
        self.preview.paint(painter)

    def paint_overlay(self, painter):
        if self.raw and len(self.raw) > 1:
            pen = QtGui.QPen(QtGui.QColor(self.settings["color"]), 1.5)
            painter.setPen(pen)
            painter.drawPolyline(QtGui.QPolygonF([self.c.to_widget(p) for p in self.raw]))
        if self.anchors:
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1))
            painter.setBrush(QtGui.QColor(45, 123, 229))
            for a in self.anchors:
                w = self.c.to_widget(a)
                painter.drawRect(QtCore.QRectF(w.x() - 3.5, w.y() - 3.5, 7, 7))


# ----------------------------------------------------------------------
#  Editing vector strokes
# ----------------------------------------------------------------------
def image_handles(e, handle_mm):
    """Corner points (TL, TR, BR, BL) and rotation handle of an image
    element, in sheet mm."""
    cx, cy = e.x + e.w / 2.0, e.y + e.h / 2.0
    a = math.radians(e.rotation)
    ca, sa = math.cos(a), math.sin(a)

    def world(lx, ly):
        return (cx + lx * ca - ly * sa, cy + lx * sa + ly * ca)
    hw, hh = e.w / 2.0, e.h / 2.0
    corners = [world(-hw, -hh), world(hw, -hh), world(hw, hh), world(-hw, hh)]
    return corners, world(0, -hh - handle_mm), world(0, -hh)


class EditTool(Tool):
    """Select a line or spline stroke and reshape it: drag an anchor (its
    handles follow), a handle (the opposite one stays aligned) or the
    stroke itself (moves it). Colour, size, opacity and width profile
    changes in the toolbar apply to the selection; Delete removes it.

    Pictures (image elements) are selected too: drag to move, corners to
    resize keeping the proportions (Shift: free), the round handle to
    rotate (Shift: 15° steps); Delete removes; locked ones are skipped."""

    show_size = False
    ROTATE_PX = 26.0            # rotation handle above the top edge

    def __init__(self, canvas, key):
        Tool.__init__(self, canvas, key)
        self.selection = None
        self.drag = None        # (index or "all", start mm, original points)
        self.idrag = None       # image: (mode, start mm, original element)
        self.preview = VectorPreview(canvas)
        self.ipreview = None    # image element being dragged

    @property
    def busy(self):
        return self.drag is not None or self.idrag is not None

    def _is_image(self, obj=None):
        obj = self.selection if obj is None else obj
        return getattr(obj, "kind", None) in ("image", "text")

    def _is_text(self, obj=None):
        obj = self.selection if obj is None else obj
        return getattr(obj, "kind", None) == "text"

    def _text_handles(self, e):
        """Wrap width handle (right side) and callout target, in mm."""
        x0, y0, x1, y1 = e.box()
        out = [("wrap", (x1, (y0 + y1) / 2.0))]
        if e.leader:
            out.append(("leader", tuple(e.leader)))
        return out

    # --- images
    def _handle_mm(self):
        return self.ROTATE_PX / (self.c.scale * self.c.zoom)

    def _pick_image_handle(self, pos):
        if not self._is_image():
            return None
        if self._is_text():
            for mode, p in self._text_handles(self.selection):
                w = self.c.to_widget(p)
                if math.hypot(pos.x() - w.x(), pos.y() - w.y()) <= HANDLE_PX:
                    return mode
            return None
        corners, rot, _top = image_handles(self.selection, self._handle_mm())
        for mode, p in [("rotate", rot)] + list(enumerate(corners)):
            w = self.c.to_widget(p)
            if math.hypot(pos.x() - w.x(), pos.y() - w.y()) <= HANDLE_PX:
                return mode
        return None

    def _start_image_drag(self, mode, pos):
        c = self.c
        e = self.selection
        self.idrag = (mode, c.to_mm(pos), e.copy())
        self.ipreview = e.copy()
        c.compositor.hidden.add(id(e))
        c.sheet_changed(c.compositor.refresh_elements([e]))

    def _move_image(self, pos, mods):
        mode, (x0, y0), orig = self.idrag
        x, y = self.c.to_mm(pos)
        e = orig.copy()
        if mode == "move":
            e.x, e.y = orig.x + x - x0, orig.y + y - y0
        elif mode == "wrap":
            from ..render import text as text_mod
            e.w = max(5.0, x - e.x)         # dragging the width handle starts wrapping
            text_mod.fit(e)
        elif mode == "leader":
            e.leader = [x, y]
        elif mode == "rotate":
            cx, cy = orig.x + orig.w / 2.0, orig.y + orig.h / 2.0
            ang = math.degrees(math.atan2(y - cy, x - cx)) + 90.0
            if _shift(mods):
                ang = round(ang / 15.0) * 15.0
            e.rotation = ((ang + 180.0) % 360.0) - 180.0
        else:
            corners, _r, _t = image_handles(orig, 0)
            fx, fy = corners[(mode + 2) % 4]            # opposite corner stays
            a = math.radians(orig.rotation)
            ca, sa = math.cos(a), math.sin(a)
            dx, dy = x - fx, y - fy
            lx, ly = dx * ca + dy * sa, -dx * sa + dy * ca     # local frame
            sx = 1.0 if mode in (1, 2) else -1.0
            sy = 1.0 if mode in (2, 3) else -1.0
            w, h = max(abs(lx), 1.0), max(abs(ly), 1.0)
            if not _shift(mods):
                k = max(w / orig.w, h / orig.h)
                w, h = orig.w * k, orig.h * k
            lcx, lcy = sx * w / 2.0, sy * h / 2.0
            cx, cy = fx + lcx * ca - lcy * sa, fy + lcx * sa + lcy * ca
            e.w, e.h = w, h
            e.x, e.y = cx - w / 2.0, cy - h / 2.0
        self.ipreview = e
        self.c.update()

    def _release_image(self, pos, mods):
        self._move_image(pos, mods)
        old, new = self.selection, self.ipreview
        self._end_image_drag()
        changed = old.to_dict() != new.to_dict()
        if changed:
            self.c.undo_stack.push(undo.ReplaceElement(self.c, old, new))
        else:
            self.c.sheet_changed(self.c.compositor.refresh_elements([old]))

    def _end_image_drag(self):
        if self.selection is not None:
            self.c.compositor.hidden.discard(id(self.selection))
        self.idrag = None
        self.ipreview = None

    def select(self, stroke):
        if stroke is not self.selection:
            self.selection = stroke
            self.c.selection_changed()
        self.c.update()

    def _pick_handle(self, pos):
        if self.selection is None:
            return None
        best, best_d = None, HANDLE_PX
        for i, p in enumerate(self.selection.points):
            w = self.c.to_widget(p)
            d = math.hypot(pos.x() - w.x(), pos.y() - w.y())
            if d <= best_d:
                best, best_d = i, d
        return best

    def press(self, pos, pressure, mods):
        c = self.c
        if self._is_image():
            mode = self._pick_image_handle(pos)
            if mode is None and self.selection.contains(*c.to_mm(pos)):
                mode = "move"
            if mode is not None:
                self._start_image_drag(mode, pos)
                return
        index = self._pick_handle(pos) if not self._is_image() else None
        if index is None:
            txt = c.pick_text(pos)
            if txt is not None:
                self.select(txt)
                self._start_image_drag("move", pos)
                return
            hit = c.pick_stroke(pos, kinds=("vector",))
            if hit is None:
                img = c.pick_image(pos)
                self.select(img)
                if img is not None:
                    self._start_image_drag("move", pos)
                return
            self.select(hit)
            index = "all"
        sel = self.selection
        self.drag = (index, c.to_mm(pos), list(sel.points))
        c.compositor.hidden.add(id(sel))
        c.sheet_changed(c.compositor.refresh_strokes([sel]))
        self.preview.set(sel.copy())

    def move(self, pos, pressure, mods):
        if self.idrag is not None:
            self._move_image(pos, mods)
            return
        if self.drag is None:
            return
        index, (x0, y0), orig = self.drag
        x, y = self.c.to_mm(pos)
        dx, dy = x - x0, y - y0
        pts = list(orig)
        n = len(pts)

        def moved(i):
            return (orig[i][0] + dx, orig[i][1] + dy, orig[i][2])

        if index == "all":
            pts = [moved(i) for i in range(n)]
        elif index % 3 == 0:            # anchor: its handles follow
            for i in (index - 1, index, index + 1):
                if 0 <= i < n:
                    pts[i] = moved(i)
        else:                           # handle: opposite one stays aligned
            pts[index] = moved(index)
            a = index - 1 if index % 3 == 1 else index + 1
            o = 2 * a - index
            if 0 <= o < n:
                ax, ay = orig[a][0], orig[a][1]
                length = math.hypot(orig[o][0] - ax, orig[o][1] - ay)
                ux, uy = pts[index][0] - ax, pts[index][1] - ay
                ul = math.hypot(ux, uy)
                if ul > 1e-9:
                    pts[o] = (ax - ux / ul * length, ay - uy / ul * length, orig[o][2])
        new = self.selection.copy()
        new.points = pts
        self.preview.set(new)
        self.c.update()

    def release(self, pos, pressure, mods):
        if self.idrag is not None:
            self._release_image(pos, mods)
            return
        if self.drag is None:
            return
        self.move(pos, pressure, mods)
        sel = self.selection
        new = self.preview.stroke
        moved = new is not None and any(
            abs(a[0] - b[0]) > 1e-6 or abs(a[1] - b[1]) > 1e-6
            for a, b in zip(new.points, sel.points))
        self._end_drag()
        if moved:
            self.c.undo_stack.push(undo.ReplaceStroke(self.c, sel, new))
        else:
            self.c.sheet_changed(self.c.compositor.refresh_strokes([sel]))

    def _end_drag(self):
        if self.selection is not None:
            self.c.compositor.hidden.discard(id(self.selection))
        self.drag = None
        self.preview.set(None)

    def cancel(self):
        if self.idrag is not None:
            sel = self.selection
            self._end_image_drag()
            self.c.sheet_changed(self.c.compositor.refresh_elements([sel]))
        if self.drag is not None:
            sel = self.selection
            self._end_drag()
            self.c.sheet_changed(self.c.compositor.refresh_strokes([sel]))

    def key(self, k, mods):
        if self.selection is None:
            return False
        if k in (int(QtCore.Qt.Key_Delete), int(QtCore.Qt.Key_Backspace)):
            sel = self.selection
            self.cancel()
            if self._is_image(sel):
                self.c.undo_stack.push(undo.RemoveElements(self.c, [sel]))
            else:
                self.c.undo_stack.push(undo.RemoveStrokes(self.c, [sel]))
            return True
        if k == int(QtCore.Qt.Key_Escape):
            self.cancel()
            self.select(None)
            return True
        return False

    def paint_sheet(self, painter):
        self.preview.paint(painter)
        if self.ipreview is not None:
            self.c.draw_element(painter, self.ipreview)

    def paint_overlay(self, painter):
        if self._is_text():
            e = self.ipreview if self.ipreview is not None else self.selection
            x0, y0, x1, y1 = e.box()
            a, b = self.c.to_widget((x0, y0)), self.c.to_widget((x1, y1))
            blue = QtGui.QColor(45, 123, 229)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(blue, 1.2, QtCore.Qt.DashLine))
            painter.drawRect(QtCore.QRectF(a, b))
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1))
            painter.setBrush(blue)
            for mode, p in self._text_handles(e):
                w = self.c.to_widget(p)
                if mode == "wrap":
                    painter.drawRect(QtCore.QRectF(w.x() - 3, w.y() - 6, 6, 12))
                else:
                    painter.drawEllipse(w, 5.0, 5.0)
            return
        if self._is_image():
            e = self.ipreview if self.ipreview is not None else self.selection
            corners, rot, top = image_handles(e, self._handle_mm())
            w = [self.c.to_widget(p) for p in corners]
            blue = QtGui.QColor(45, 123, 229)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(blue, 1.5))
            painter.drawPolygon(QtGui.QPolygonF(w))
            painter.drawLine(self.c.to_widget(top), self.c.to_widget(rot))
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1))
            painter.setBrush(blue)
            for p in w:
                painter.drawRect(QtCore.QRectF(p.x() - 4, p.y() - 4, 8, 8))
            painter.drawEllipse(self.c.to_widget(rot), 5.0, 5.0)
            return
        stroke = self.preview.stroke if self.drag is not None else self.selection
        if stroke is None:
            return
        w = [self.c.to_widget(p) for p in stroke.points]
        blue = QtGui.QColor(45, 123, 229)
        painter.setPen(QtGui.QPen(blue, 1))
        for i in range(0, len(w) - 3, 3):
            painter.drawLine(w[i], w[i + 1])
            painter.drawLine(w[i + 2], w[i + 3])
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1))
        for i, p in enumerate(w):
            painter.setBrush(blue)
            if i % 3 == 0:
                painter.drawRect(QtCore.QRectF(p.x() - 3.5, p.y() - 3.5, 7, 7))
            else:
                painter.drawEllipse(p, 3.0, 3.0)


# ----------------------------------------------------------------------
#  Styled shapes
# ----------------------------------------------------------------------
class ShapeTool(Tool):
    """Circle, ellipse, rectangle or arc, drawn with the last drawing tool
    (its colour, size, opacity, pressure look) with a slight hand-drawn
    look: drag to draw, Shift for a circle / square / half circle, Escape
    cancels. The result is an ordinary stroke (undo, erasers, exports)."""

    show_size = False

    def __init__(self, canvas, key):
        Tool.__init__(self, canvas, key)
        self.start = None
        self.preview = VectorPreview(canvas)

    @property
    def busy(self):
        return self.start is not None

    def press(self, pos, pressure, mods):
        self.start = self.c.to_mm(pos)
        self.seed = int(time.monotonic() * 1000) % 100000

    def stroke_for(self, x0, y0, x1, y1, constrain):
        c = self.c
        st = c.tool_settings["shape"]
        brush = c.last_brush
        bs = c.tool_settings[brush]
        t = model.TOOLS[brush]
        kind = st["kind"]
        chain = geom.shape_chain(kind, x0, y0, x1, y1, constrain)
        if st["hand"]:
            chain = geom.hand_drawn(chain, kind != "arc", seed=self.seed)
        if t["kind"] == "vector":
            keys = model.DEFAULT_ARROW if brush == "arrow" else model.DEFAULT_PROFILE
            return model.Stroke(brush, bs["color"], bs["size"], bs["opacity"], t["layer"],
                                [(x, y, 1.0) for x, y in chain],
                                dict((k, bs[k]) for k in keys))
        pts = [(x, y, 0.85) for x, y, _t in geom.sample_chain(chain, 0.5)]
        if st["hand"] and len(pts) > 2:
            pts = geom.taper_ends(pts, 2.0 + bs["size"], 3.0 + bs["size"], lowest=0.35)
        return model.Stroke(brush, bs["color"], bs["size"], bs["opacity"], t["layer"], pts)

    def move(self, pos, pressure, mods):
        if self.start is None:
            return
        x, y = self.c.to_mm(pos)
        self.preview.set(self.stroke_for(self.start[0], self.start[1], x, y, _shift(mods)))

    def release(self, pos, pressure, mods):
        if self.start is None:
            return
        self.move(pos, pressure, mods)
        stroke = self.preview.stroke
        (x0, y0), (x1, y1) = self.start, self.c.to_mm(pos)
        self.cancel()
        if stroke is not None and math.hypot(x1 - x0, y1 - y0) > 0.5:
            self.c.undo_stack.push(undo.AddStroke(self.c, stroke))

    def key(self, k, mods):
        if k == int(QtCore.Qt.Key_Escape) and self.start is not None:
            self.cancel()
            return True
        return False

    def cancel(self):
        self.start = None
        self.preview.set(None)

    def paint_sheet(self, painter):
        self.preview.paint(painter)


# ----------------------------------------------------------------------
#  Text boxes
# ----------------------------------------------------------------------
class TextTool(Tool):
    """Click to write a text box there (click a text to edit it). While
    typing every key goes to the text; Escape, Ctrl+Return or a click
    elsewhere validates. Font, size, style, colour, frame and callout
    arrow come from the text panel."""

    show_size = False

    def press(self, pos, pressure, mods):
        c = self.c
        hit = c.pick_text(pos)
        if hit is not None:
            c.edit_text(hit)
        else:
            c.edit_text(c.new_text(*c.to_mm(pos)), new=True)


# ----------------------------------------------------------------------
#  Scale (calibration)
# ----------------------------------------------------------------------
class ScaleTool(Tool):
    """Give the real size of something drawn or pasted: drag a segment over
    a known length, type that length; the sheet's scale (the size of its
    image plane in 3D) follows. Shift snaps the angle."""

    show_size = False

    def __init__(self, canvas, key):
        Tool.__init__(self, canvas, key)
        self.a = self.b = None

    @property
    def busy(self):
        return self.a is not None

    def press(self, pos, pressure, mods):
        self.a = self.b = self.c.to_mm(pos)

    def move(self, pos, pressure, mods):
        if self.a is None:
            return
        x, y = self.c.to_mm(pos)
        if _shift(mods):
            x, y = geom.snap_angle(self.a[0], self.a[1], x, y)
        self.b = (x, y)
        self.c.update()

    def release(self, pos, pressure, mods):
        if self.a is None:
            return
        self.move(pos, pressure, mods)
        a, b = self.a, self.b
        self.a = self.b = None
        self.c.update()
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length > 0.5:
            self.c.ask_scale(length)

    def cancel(self):
        self.a = self.b = None
        self.c.update()

    def paint_overlay(self, painter):
        if self.a is None or self.b is None:
            return
        pa, pb = self.c.to_widget(self.a), self.c.to_widget(self.b)
        painter.setPen(QtGui.QPen(QtGui.QColor(214, 69, 61), 2))
        painter.drawLine(pa, pb)
        for p in (pa, pb):
            painter.drawLine(QtCore.QPointF(p.x() - 5, p.y()), QtCore.QPointF(p.x() + 5, p.y()))
            painter.drawLine(QtCore.QPointF(p.x(), p.y() - 5), QtCore.QPointF(p.x(), p.y() + 5))
        mm = math.hypot(self.b[0] - self.a[0], self.b[1] - self.a[1]) * self.c.sheet.plane_scale
        mid = QtCore.QPointF((pa.x() + pb.x()) / 2 + 8, (pa.y() + pb.y()) / 2 - 8)
        painter.drawText(mid, "%.1f mm" % mm)


def make_tool(canvas, key):
    """Tool object for a tool key (and its current mode)."""
    if key == "edit":
        return EditTool(canvas, key)
    if key == "scale":
        return ScaleTool(canvas, key)
    if key == "text":
        return TextTool(canvas, key)
    if key == "shape":
        return ShapeTool(canvas, key)
    kind = model.tool_kind(key)
    if kind == "vector":
        straight = key == "line" or (key == "arrow" and
                                     canvas.tool_settings[key].get("mode") == "straight")
        return LineTool(canvas, key) if straight else SplineTool(canvas, key)
    if kind == "eraser" and canvas.tool_settings[key].get("mode") == "strokes":
        return StrokeEraserTool(canvas, key)
    return BrushTool(canvas, key)
