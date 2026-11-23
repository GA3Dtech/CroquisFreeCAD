# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - layer compositor
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
compositor.py (Croquis) - turns a SheetData into an image.

Each layer keeps its own image, allocated only once it holds a stroke (an
A3 sheet at 300 dpi is 70 MB per layer). Adding a stroke paints it on its
layer and recomposes only the rectangle it covers, so drawing stays fluid
on large sheets; removing one (undo) repaints its layer.

Composition, bottom to top: paper colour (nothing for a transparent sheet),
then every visible layer with its opacity and blend mode (model.LAYERS).

Eraser strokes are painted with DestinationOut on the layers they work on,
in stroke order: they remove what was drawn before them, not after.
`hidden` holds strokes and elements left out while the board edits them.

Image elements (format v2) are drawn on their layer (normally "images")
before the strokes of that layer. `export=True` (image plane, PNG export)
leaves out the images whose `render` flag is off and the underlay guide.
"""

from .. import model
from ..qt import QtCore, QtGui
from . import brushes

FORMAT = QtGui.QImage.Format_ARGB32_Premultiplied


def blend_mode(name):
    if name == "multiply":
        return QtGui.QPainter.CompositionMode_Multiply
    return QtGui.QPainter.CompositionMode_SourceOver


def new_image(w, h):
    img = QtGui.QImage(w, h, FORMAT)
    img.fill(0)
    return img


class Compositor(object):
    """Layer caches and composite image of a sheet at a given resolution
    (pixels per mm, the sheet's own by default)."""

    def __init__(self, sheet, scale=None, paper=True, export=False):
        self.sheet = sheet
        self.export = export
        self._pictures = {}     # path -> QImage
        self.scale = scale or sheet.scale
        self.paper = paper
        self.w = max(1, int(round(sheet.width * self.scale)))
        self.h = max(1, int(round(sheet.height * self.scale)))
        self.bounds = QtCore.QRect(0, 0, self.w, self.h)
        self.layers = {}
        self.hidden = set()     # id() of strokes not painted
        self.underlay = None    # QImage stretched over the sheet (v0.3)
        self.image = new_image(self.w, self.h)
        self.rebuild()

    # --- layers
    def _layer(self, key):
        img = self.layers.get(key)
        if img is None:
            img = self.layers[key] = new_image(self.w, self.h)
        return img

    def stroke_layers(self, stroke):
        if stroke.kind == "eraser":
            return model.eraser_targets(stroke)
        return [stroke.layer]

    def _paint_stroke(self, stroke, only=None):
        """Lay one stroke on its layer(s) (`only`: that layer only).
        Returns the covered QRect or None."""
        if id(stroke) in self.hidden or stroke.kind == "unknown":
            return None
        if stroke.kind != "eraser" and stroke.layer not in model.LAYER_KEYS:
            return None     # layer of a newer version: kept, not drawn
        if stroke.kind == "eraser":
            targets = [k for k in model.eraser_targets(stroke)
                       if self.layers.get(k) is not None and (only is None or k == only)]
            if not targets:
                return None
        res = brushes.render_stroke(stroke, self.scale, self.bounds)
        if res is None:
            return None
        img, pos = res
        if stroke.kind == "eraser":
            for k in targets:
                self.erase(k, img, pos, stroke.opacity)
        else:
            painter = QtGui.QPainter(self._layer(stroke.layer))
            try:
                painter.setOpacity(stroke.opacity)
                painter.setCompositionMode(blend_mode(model.layer_blend(stroke.layer)))
                painter.drawImage(pos, img)
            finally:
                painter.end()
        return QtCore.QRect(pos, img.size())

    def erase(self, key, img, pos, opacity=1.0, source_rect=None):
        """Remove the alpha of `img` (placed at `pos`) from a layer."""
        layer = self.layers.get(key)
        if layer is None:
            return
        painter = QtGui.QPainter(layer)
        try:
            painter.setOpacity(opacity)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_DestinationOut)
            if source_rect is None:
                painter.drawImage(pos, img)
            else:
                painter.drawImage(pos, img, source_rect)
        finally:
            painter.end()

    # --- images
    def picture(self, element):
        """QImage of an image element (cached), None when missing."""
        path = self.sheet.files.get(element.file)
        if not path:
            return None
        img = self._pictures.get(path)
        if img is None:
            reader = QtGui.QImageReader(path)
            reader.setAutoTransform(True)       # EXIF orientation
            img = reader.read()
            if img.isNull():
                return None
            self._pictures[path] = img
        return img

    def _paint_element(self, e):
        if e.kind != "image" or id(e) in self.hidden or e.layer not in model.LAYER_KEYS:
            return None
        if self.export and not e.render:
            return None
        img = self.picture(e)
        if img is None:
            return None
        s = self.scale
        painter = QtGui.QPainter(self._layer(e.layer))
        try:
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            painter.setOpacity(e.opacity)
            painter.translate((e.x + e.w / 2.0) * s, (e.y + e.h / 2.0) * s)
            painter.rotate(e.rotation)
            painter.drawImage(QtCore.QRectF(-e.w * s / 2.0, -e.h * s / 2.0, e.w * s, e.h * s),
                              img)
        finally:
            painter.end()
        return self.element_rect(e)

    def element_rect(self, e):
        b = e.bounds()
        s = self.scale
        r = QtCore.QRect(int(b[0] * s) - 2, int(b[1] * s) - 2,
                         int((b[2] - b[0]) * s) + 5, int((b[3] - b[1]) * s) + 5)
        return r.intersected(self.bounds)

    def rebuild_layer(self, key):
        self.layers.pop(key, None)
        for e in self.sheet.elements:
            if getattr(e, "layer", None) == key:
                self._paint_element(e)
        for s in self.sheet.layer_strokes(key):
            self._paint_stroke(s, only=key)

    def rebuild(self):
        self.layers = {}
        for key in model.LAYER_KEYS:
            self.rebuild_layer(key)
        self.compose()

    def refresh_elements(self, elements):
        """Repaint the layers of elements (added, removed, hidden or
        changed) and recompose their area. Returns the dirty QRect."""
        keys, rect = [], None
        for e in elements:
            if getattr(e, "layer", None) in model.LAYER_KEYS and e.layer not in keys:
                keys.append(e.layer)
            if hasattr(e, "bounds"):
                r = self.element_rect(e)
                rect = r if rect is None else rect.united(r)
        for k in keys:
            self.rebuild_layer(k)
        if rect is not None:
            self.compose(rect)
        return rect

    def refresh_strokes(self, strokes):
        """Repaint the layers of `strokes` (added, removed, hidden or
        changed) and recompose their area. Returns the dirty QRect."""
        keys = []
        rect = None
        for st in strokes:
            for k in self.stroke_layers(st):
                if k not in keys:
                    keys.append(k)
            r = brushes.stroke_pixel_rect(st, self.scale, self.bounds)
            if r is not None:
                rect = r if rect is None else rect.united(r)
        for k in keys:
            self.rebuild_layer(k)
        if rect is not None:
            self.compose(rect)
        return rect

    # --- edits
    def add_stroke(self, stroke):
        """The stroke was appended to the sheet: paint it, recompose its
        area. Returns the dirty QRect (or None)."""
        r = self._paint_stroke(stroke)
        if r is not None:
            self.compose(r)
        return r

    def remove_stroke(self, stroke):
        """The stroke was removed from the sheet: repaint its layer(s)."""
        return self.refresh_strokes([stroke])

    # --- composition
    def compose(self, rect=None):
        """Recompose the whole image, or only `rect` (QRect)."""
        painter = QtGui.QPainter(self.image)
        try:
            if rect is not None:
                painter.setClipRect(rect)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
            color = model.paper_color(self.sheet.paper) if self.paper else None
            painter.fillRect(self.bounds, QtGui.QColor(color) if color
                             else QtGui.QColor(0, 0, 0, 0))
            if self.underlay is not None and not self.export \
                    and self.sheet.layers["underlay"]["visible"]:
                painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
                painter.setOpacity(self.sheet.layers["underlay"]["opacity"])
                painter.drawImage(QtCore.QRectF(self.bounds), self.underlay)
            for key, _label, blend in model.LAYERS:
                img = self.layers.get(key)
                info = self.sheet.layers.get(key, {"visible": True, "opacity": 1.0})
                if img is None or not info["visible"]:
                    continue
                painter.setCompositionMode(blend_mode(blend))
                painter.setOpacity(info["opacity"])
                painter.drawImage(0, 0, img)
        finally:
            painter.end()
        return rect


def render_sheet(sheet, dpi=None, paper=True, export=True):
    """Final image of a sheet (QImage), at its own resolution or `dpi`.
    export=True: as in the image plane (no guide, only rendered images)."""
    comp = Compositor(sheet, scale=(dpi / 25.4) if dpi else None, paper=paper, export=export)
    return comp.image


def save_png(sheet, path, dpi=None, paper=True, export=True):
    """Write the sheet as a PNG (alpha where the paper is transparent),
    with its resolution recorded in the file. Returns True on success."""
    img = render_sheet(sheet, dpi, paper, export)
    dots_per_metre = int(round((dpi or sheet.dpi) / 0.0254))
    img.setDotsPerMeterX(dots_per_metre)
    img.setDotsPerMeterY(dots_per_metre)
    return bool(img.save(path, "PNG"))
