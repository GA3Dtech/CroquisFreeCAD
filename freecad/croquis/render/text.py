# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - text boxes
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
text.py (Croquis) - layout and drawing of text boxes (model.TextElement):
the font size is a length in mm on the sheet, so a text has the same size
whatever the resolution. Fonts vary between systems: the requested family
is stored, Qt falls back on a close one when it is missing.
"""

from ..qt import QtCore, QtGui
from . import stroke_geom as geom

MEASURE_SCALE = 20.0        # px per mm used to measure (resolution independent)


def font_for(e, scale):
    f = QtGui.QFont(e.font)
    f.setStyleHint(QtGui.QFont.SansSerif)
    f.setPixelSize(max(1, int(round(e.size * scale))))
    f.setBold(e.bold)
    f.setItalic(e.italic)
    return f


def flags(e):
    a = {"center": QtCore.Qt.AlignHCenter, "right": QtCore.Qt.AlignRight}.get(
        e.align, QtCore.Qt.AlignLeft)
    f = a | QtCore.Qt.AlignTop
    return f | QtCore.Qt.TextWordWrap if e.w > 0 else f


def measure(e):
    """(width, height) in mm of the text laid out in its box (width is the
    natural width when the box does not wrap)."""
    s = MEASURE_SCALE
    fm = QtGui.QFontMetricsF(font_for(e, s))
    text = e.text if e.text else " "
    if e.w > 0:
        r = fm.boundingRect(QtCore.QRectF(0, 0, e.w * s, 1e7), int(flags(e)), text)
        return e.w, max(r.height(), fm.height()) / s
    r = fm.boundingRect(QtCore.QRectF(0, 0, 1e7, 1e7), int(flags(e)), text)
    return max(r.width(), 1.0) / s, max(r.height(), fm.height()) / s


def fit(e):
    """Update e.h, and the natural width e.aw of a box that does not wrap
    (with a little room for italic overhangs)."""
    w, h = measure(e)
    e.aw = w + e.size * 0.15 if e.w <= 0 else 0.0
    e.h = h
    return e


def draw(painter, e, scale):
    """Draw a text element with a painter whose unit is the sheet pixel."""
    painter.save()
    try:
        painter.setOpacity(e.opacity)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        color = QtGui.QColor(e.color)
        x0, y0, x1, y1 = e.box()
        box = QtCore.QRectF(x0 * scale, y0 * scale, (x1 - x0) * scale, (y1 - y0) * scale)
        pen = QtGui.QPen(color, max(1.0, e.size * 0.08 * scale))
        if e.leader:
            sx, sy = e.leader_start()
            tx, ty = e.leader
            painter.setPen(pen)
            painter.drawLine(QtCore.QPointF(sx * scale, sy * scale),
                             QtCore.QPointF(tx * scale, ty * scale))
            d = (tx - sx, ty - sy)
            n = (d[0] ** 2 + d[1] ** 2) ** 0.5
            if n > 1e-6:
                _k, tri = geom.arrow_head((tx, ty), (d[0] / n, d[1] / n), e.size * 0.9,
                                          "filled")
                painter.setBrush(color)
                painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(px * scale, py * scale)
                                                     for px, py in tri]))
        if e.background:
            painter.fillRect(box, QtGui.QColor(255, 255, 255))
        if e.frame:
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(box)
        painter.setPen(color)
        painter.setFont(font_for(e, scale))
        rect = QtCore.QRectF(e.x * scale, e.y * scale,
                             (e.w if e.w > 0 else 1e5) * scale, 1e7)
        painter.drawText(rect, int(flags(e)), e.text)
    finally:
        painter.restore()


def available_fonts():
    """Families offered in the text panel: generic ones, then common ones
    installed on this system."""
    try:
        installed = set(QtGui.QFontDatabase.families())
    except TypeError:
        installed = set(QtGui.QFontDatabase().families())
    wanted = ["DejaVu Sans", "Liberation Sans", "Noto Sans", "Ubuntu", "Arial", "Helvetica",
              "Segoe UI", "Roboto", "Open Sans", "Comic Sans MS", "Caveat", "Permanent Marker",
              "Architects Daughter", "Liberation Serif", "Times New Roman",
              "DejaVu Sans Mono", "Courier New"]
    return ["Sans Serif", "Serif", "Monospace"] + [f for f in wanted if f in installed]
