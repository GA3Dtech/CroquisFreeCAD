# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - PDF export
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
pdf.py (Croquis) - sheets to PDF, one page per sheet at its size in mm.

Vector where it is faithful: line, spline and arrow strokes (and vector
shapes) and text boxes of the "lines" and "highlights" layers are written
as vector graphics. Everything else is a high resolution picture: the
paper, pictures, pencil / marker layers (the marker's multiply has no PDF
equivalent: those layers are composited as on screen), raster strokes, and
any layer an eraser works on. The 3D view guide is never exported.
"""

from .. import model
from ..qt import QtCore, QtGui
from . import brushes, compositor, text

VECTOR_LAYERS = ("lines", "highlights")


def _vector_layer(sheet, key):
    """Can this layer be written item by item (no eraser on it)?"""
    return key in VECTOR_LAYERS and not any(
        s.kind == "eraser" and key in model.eraser_targets(s) for s in sheet.strokes)


def paint_sheet(painter, sheet, dpi):
    """Paint one sheet; painter unit = pixel at `dpi`."""
    scale = dpi / 25.4
    vector = [k for k in model.LAYER_KEYS if _vector_layer(sheet, k)]
    # base picture: paper and every layer that is not written as vectors
    hidden = dict((k, sheet.layers[k]["visible"]) for k in vector)
    for k in vector:
        sheet.layers[k]["visible"] = False
    try:
        base = compositor.Compositor(sheet, scale, paper=True, export=True, underlay=False)
        painter.drawImage(QtCore.QRectF(0, 0, base.w, base.h), base.image)
    finally:
        for k, v in hidden.items():
            sheet.layers[k]["visible"] = v
    for key in vector:
        info = sheet.layers[key]
        if not info["visible"]:
            continue
        for s in sheet.layer_strokes(key):
            if s.kind == "unknown":
                continue
            painter.setOpacity(info["opacity"] * s.opacity)
            if s.kind == "vector":
                brushes.paint_vector_stroke(painter, s, scale)
            else:
                res = brushes.render_stroke(s, scale)
                if res is not None:
                    img, pos = res
                    painter.drawImage(QtCore.QPointF(pos), img)
        for e in sheet.elements:
            if getattr(e, "kind", None) == "text" and e.layer == key:
                painter.setOpacity(info["opacity"])
                text.draw(painter, e, scale)
        painter.setOpacity(1.0)


def save_pdf(sheets, path, dpi=300):
    """Write sheets (SheetData, one page each) to a PDF file."""
    writer = QtGui.QPdfWriter(path)
    writer.setResolution(int(dpi))
    writer.setCreator("Croquis (FreeCAD)")
    painter = None
    try:
        for i, sheet in enumerate(sheets):
            size = QtGui.QPageSize(QtCore.QSizeF(sheet.width, sheet.height),
                                   QtGui.QPageSize.Millimeter, "", QtGui.QPageSize.ExactMatch)
            writer.setPageSize(size)
            writer.setPageMargins(QtCore.QMarginsF(0, 0, 0, 0))
            if painter is None:
                painter = QtGui.QPainter(writer)
            else:
                writer.newPage()
            paint_sheet(painter, sheet, dpi)
    finally:
        if painter is not None:
            painter.end()
    return path
