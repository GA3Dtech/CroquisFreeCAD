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
"""

from ..qt import QtCore, QtGui
from .. import model
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

    def __init__(self, sheet, scale=None, paper=True):
        self.sheet = sheet
        self.scale = scale or sheet.scale
        self.paper = paper
        self.w = max(1, int(round(sheet.width * self.scale)))
        self.h = max(1, int(round(sheet.height * self.scale)))
        self.bounds = QtCore.QRect(0, 0, self.w, self.h)
        self.layers = {}
        self.underlay = None    # QImage stretched over the sheet (v0.3)
        self.image = new_image(self.w, self.h)
        self.rebuild()

    # --- layers
    def _layer(self, key):
        img = self.layers.get(key)
        if img is None:
            img = self.layers[key] = new_image(self.w, self.h)
        return img

    def _paint_stroke(self, stroke):
        """Lay one stroke on its layer. Returns the covered QRect or None."""
        res = brushes.render_stroke(stroke, self.scale, self.bounds)
        if res is None:
            return None
        img, pos = res
        painter = QtGui.QPainter(self._layer(stroke.layer))
        try:
            painter.setOpacity(stroke.opacity)
            painter.setCompositionMode(blend_mode(model.layer_blend(stroke.layer)))
            painter.drawImage(pos, img)
        finally:
            painter.end()
        return QtCore.QRect(pos, img.size())

    def rebuild_layer(self, key):
        self.layers.pop(key, None)
        for s in self.sheet.layer_strokes(key):
            self._paint_stroke(s)

    def rebuild(self):
        self.layers = {}
        for s in self.sheet.strokes:
            self._paint_stroke(s)
        self.compose()

    # --- edits
    def add_stroke(self, stroke):
        """The stroke was appended to the sheet: paint it, recompose its
        area. Returns the dirty QRect (or None)."""
        r = self._paint_stroke(stroke)
        if r is not None:
            self.compose(r)
        return r

    def remove_stroke(self, stroke):
        """The stroke was removed from the sheet: repaint its layer."""
        r = brushes.stroke_pixel_rect(stroke, self.scale, self.bounds)
        self.rebuild_layer(stroke.layer)
        if r is not None:
            self.compose(r)
        return r

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
            if self.underlay is not None and self.sheet.layers["underlay"]["visible"]:
                painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
                painter.setOpacity(self.sheet.layers["underlay"]["opacity"])
                painter.drawImage(QtCore.QRectF(self.bounds), self.underlay)
            for key, _label, blend in model.LAYERS:
                img = self.layers.get(key)
                info = self.sheet.layers[key]
                if img is None or not info["visible"]:
                    continue
                painter.setCompositionMode(blend_mode(blend))
                painter.setOpacity(info["opacity"])
                painter.drawImage(0, 0, img)
        finally:
            painter.end()
        return rect


def render_sheet(sheet, dpi=None, paper=True):
    """Final image of a sheet (QImage), at its own resolution or `dpi`."""
    comp = Compositor(sheet, scale=(dpi / 25.4) if dpi else None, paper=paper)
    return comp.image


def save_png(sheet, path, dpi=None, paper=True):
    """Write the sheet as a PNG (alpha where the paper is transparent),
    with its resolution recorded in the file. Returns True on success."""
    img = render_sheet(sheet, dpi, paper)
    dots_per_metre = int(round((dpi or sheet.dpi) / 0.0254))
    img.setDotsPerMeterX(dots_per_metre)
    img.setDotsPerMeterY(dots_per_metre)
    return bool(img.save(path, "PNG"))
