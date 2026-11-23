# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - brushes
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
brushes.py (Croquis) - draws one stroke into its own image.

Every stroke is drawn in a separate buffer with CompositionMode_Source:
each short segment REPLACES the pixels under it instead of blending with
them, so a stroke never darkens where it crosses itself or where its round
caps overlap. The stroke opacity and the blend mode (multiply for markers)
are applied only when the finished buffer is laid on its layer
(compositor.py): two marker strokes darken each other, one stroke does not.
That is the difference between an alcohol marker and a transparent brush.

Pressure drives the width and the opacity of each segment, in the share
given by the tool preset (model.TOOLS). Graphite tools then get a paper
grain anchored to the sheet; a hard press fills the grain (grain_pressure),
a light one only catches the top of the paper fibres.

Vector strokes (line, spline) are sampled along their Bezier chain into a
dense pseudo stroke whose "pressure" is the width profile, then drawn by
the same segment code at the target resolution: sharp at any scale.
"""

import math
import random

from .. import model
from ..qt import QtCore, QtGui
from . import stroke_geom as geom

# Grain texture size in pixels, and the resolution it was designed for
# (it is scaled so the grain keeps the same size in millimetres)
GRAIN_SIZE = 256
GRAIN_DPI = 150.0

_grain_cache = {}


def tool_params(tool):
    return model.TOOLS.get(tool, model.TOOLS["pencil"])


def point_style(pressure, size_px, params):
    """(width px, alpha 0..1) of the stroke at a point."""
    pw = params["pressure_width"]
    pa = params["pressure_alpha"]
    w = size_px * (1.0 - pw + pw * pressure)
    a = 1.0 - pa + pa * pressure
    return max(w, 0.5), geom.clamp(a)


class StrokeRaster(object):
    """Draws a stroke span by span (one span = between two input points)
    into `image`, whose pixel (0, 0) is at sheet pixel `origin`. Used live
    while the pen moves (draw_to() with the spans already complete) and for
    the final render (all spans)."""

    def __init__(self, image, origin, stroke, scale):
        self.image = image
        self.ox, self.oy = origin
        self.stroke = stroke
        self.scale = scale
        self.params = tool_params(stroke.tool)
        self.size_px = stroke.size * scale
        self.color = QtGui.QColor(stroke.color)
        # Sampling step: about one pixel, coarser for wide markers
        self.step_mm = max(0.8, self.size_px / 10.0) / scale
        self.done = 0           # spans already drawn
        self.last = None        # last sample drawn (px, py, w, a)

    def _sample(self, p):
        x = p[0] * self.scale - self.ox
        y = p[1] * self.scale - self.oy
        w, a = point_style(p[2], self.size_px, self.params)
        return x, y, w, a

    def _painter(self):
        painter = QtGui.QPainter(self.image)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
        return painter

    def _segment(self, painter, s0, s1, rect):
        w = 0.5 * (s0[2] + s1[2])
        a = 0.5 * (s0[3] + s1[3])
        c = QtGui.QColor(self.color)
        c.setAlphaF(a)
        pen = QtGui.QPen(c, w, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap,
                         QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(s0[0], s0[1]), QtCore.QPointF(s1[0], s1[1]))
        m = w * 0.5 + 2.0
        r = QtCore.QRectF(min(s0[0], s1[0]) - m, min(s0[1], s1[1]) - m,
                          abs(s1[0] - s0[0]) + 2 * m, abs(s1[1] - s0[1]) + 2 * m)
        return r if rect is None else rect.united(r)

    def draw_to(self, spans):
        """Draw spans self.done .. spans-1. Returns the dirty rectangle in
        image pixels (QRectF) or None."""
        pts = self.stroke.points
        spans = min(spans, len(pts) - 1)
        if spans <= self.done:
            return None
        rect = None
        painter = self._painter()
        try:
            for i in range(self.done, spans):
                for p in geom.catmull_rom_span(pts, i, self.step_mm):
                    s = self._sample(p)
                    if self.last is not None:
                        rect = self._segment(painter, self.last, s, rect)
                    self.last = s
            self.done = spans
            if spans == len(pts) - 1:
                # stroke complete: close it on its true last point
                s = self._sample(pts[-1])
                if self.last is not None:
                    rect = self._segment(painter, self.last, s, rect)
                self.last = s
        finally:
            painter.end()
        return rect

    def draw_dot(self):
        """A single click: one round dot."""
        s = self._sample(self.stroke.points[0])
        painter = self._painter()
        try:
            c = QtGui.QColor(self.color)
            c.setAlphaF(s[3])
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(c)
            painter.drawEllipse(QtCore.QPointF(s[0], s[1]), s[2] * 0.5, s[2] * 0.5)
        finally:
            painter.end()
        m = s[2] * 0.5 + 2.0
        return QtCore.QRectF(s[0] - m, s[1] - m, 2 * m, 2 * m)


# ----------------------------------------------------------------------
#  Grain
# ----------------------------------------------------------------------
_noise = []


def _noise_array():
    """Tileable noise (numpy, GRAIN_SIZE², values 0..1), or None without
    numpy."""
    if _noise:
        return _noise[0]
    try:
        import numpy as np
    except ImportError:
        _noise.append(None)
        return None
    n = GRAIN_SIZE
    rng = np.random.default_rng(7)
    v = rng.random((n, n))
    # light tileable blur, then more contrast: graphite catches the top of
    # the paper fibres
    v = (v + np.roll(v, 1, 0) + np.roll(v, -1, 0)
         + np.roll(v, 1, 1) + np.roll(v, -1, 1)) / 5.0
    v = (v - v.min()) / max(v.max() - v.min(), 1e-6)
    _noise.append(v ** 1.6)
    return _noise[0]


def grain_texture(strength):
    """Tileable image whose alpha is 1 - strength * noise (cached); used
    when numpy is missing."""
    key = round(strength, 2)
    img = _grain_cache.get(key)
    if img is not None:
        return img
    n = GRAIN_SIZE
    rnd = random.Random(7)
    data = bytearray()
    for _ in range(n * n):
        a = int(255 * (1.0 - strength * rnd.random() ** 1.6))
        data.extend((a, a, a, a))
    img = QtGui.QImage(bytes(data), n, n, 4 * n,
                       QtGui.QImage.Format_ARGB32_Premultiplied).copy()
    _grain_cache[key] = img
    return img


def _image_array(img):
    """Copy of an ARGB32 QImage as a numpy array (h, w, 4), or None."""
    import numpy as np
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    ptr = img.constBits()
    if hasattr(ptr, "setsize"):
        ptr.setsize(h * bpl)
    buf = np.frombuffer(ptr, np.uint8, count=h * bpl)
    return buf.reshape(h, bpl)[:, :w * 4].reshape(h, w, 4).copy()


def apply_grain(image, origin, strength, scale, pressure_fill=0.0):
    """Paper grain on a stroke image, anchored to the sheet (not to the
    stroke) so overlapping strokes share the same paper. Where the stroke
    is dense (alpha near 1) `pressure_fill` closes the grain. Returns the
    resulting image (may be a new one)."""
    if strength <= 0:
        return image
    k = scale / (GRAIN_DPI / 25.4)
    noise = _noise_array()
    if noise is not None:
        try:
            import numpy as np
            arr = _image_array(image).astype(np.float32)
            h, w = arr.shape[:2]
            n = noise.shape[0]
            ty = (np.floor((np.arange(h) + origin[1]) / k).astype(np.int64)) % n
            tx = (np.floor((np.arange(w) + origin[0]) / k).astype(np.int64)) % n
            nz = noise[np.ix_(ty, tx)]
            a = arr[:, :, 3] / 255.0
            f = 1.0 - strength * nz * (1.0 - pressure_fill * a * a)
            arr *= f[:, :, None]
            data = np.clip(arr, 0, 255).astype(np.uint8).tobytes()
            return QtGui.QImage(data, w, h, 4 * w,
                                QtGui.QImage.Format_ARGB32_Premultiplied).copy()
        except Exception:
            pass        # fall back on the Qt path below
    brush = QtGui.QBrush(grain_texture(strength))
    t = QtGui.QTransform()
    t.translate(-origin[0], -origin[1])
    t.scale(k, k)
    brush.setTransform(t)
    painter = QtGui.QPainter(image)
    try:
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_DestinationIn)
        painter.fillRect(image.rect(), brush)
    finally:
        painter.end()
    return image


# ----------------------------------------------------------------------
#  Vector strokes
# ----------------------------------------------------------------------
def chain_of(stroke):
    return [(p[0], p[1]) for p in stroke.points]


def vector_pseudo_stroke(stroke, scale):
    """Raster stroke equivalent to a vector stroke at a resolution: points
    about one pixel apart, "pressure" = width profile."""
    prof = stroke.profile()
    step = max(0.6, stroke.size * scale / 12.0) / scale
    pts = [(x, y, geom.profile_width(t, prof["peak"], prof["tin"], prof["tout"]))
           for x, y, t in geom.sample_chain(chain_of(stroke), step)]
    return model.Stroke(stroke.tool, stroke.color, stroke.size, stroke.opacity,
                        stroke.layer, pts)


def stroke_polyline(stroke, scale=10.0):
    """Points along the visible path of any stroke (for hit testing), in mm."""
    if stroke.kind == "vector":
        return geom.sample_chain(chain_of(stroke), 1.0 / scale * 4)
    return stroke.points


# ----------------------------------------------------------------------
#  Whole stroke
# ----------------------------------------------------------------------
def stroke_pixel_rect(stroke, scale, limit=None):
    """Integer pixel rectangle covering the stroke (QRect), clipped to
    `limit` (QRect) when given. None when empty."""
    b = stroke.bounds()
    if b is None:
        return None
    x0 = int(math.floor(b[0] * scale)) - 2
    y0 = int(math.floor(b[1] * scale)) - 2
    x1 = int(math.ceil(b[2] * scale)) + 2
    y1 = int(math.ceil(b[3] * scale)) + 2
    r = QtCore.QRect(x0, y0, x1 - x0, y1 - y0)
    if limit is not None:
        r = r.intersected(limit)
    return r if r.isValid() and not r.isEmpty() else None


def render_stroke(stroke, scale, limit=None):
    """(QImage, QPoint) of the finished stroke at full opacity, the point
    being its position in sheet pixels; None when nothing is visible."""
    r = stroke_pixel_rect(stroke, scale, limit)
    if r is None:
        return None
    img = QtGui.QImage(r.width(), r.height(), QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    origin = (r.x(), r.y())
    drawn = vector_pseudo_stroke(stroke, scale) if stroke.kind == "vector" else stroke
    raster = StrokeRaster(img, origin, drawn, scale)
    if len(drawn.points) == 1:
        raster.draw_dot()
    else:
        raster.draw_to(len(drawn.points) - 1)
    if stroke.tool == "arrow":
        draw_arrow_heads(img, origin, stroke, scale)
    params = raster.params
    img = apply_grain(img, origin, params["grain"], scale, params.get("grain_pressure", 0.0))
    return img, r.topLeft()


def draw_arrow_heads(img, origin, stroke, scale):
    """Heads of an arrow stroke, in the stroke's own buffer (full alpha:
    the stroke opacity is applied when the buffer is composited)."""
    prof = stroke.profile()
    chain = chain_of(stroke)
    if len(chain) < 2:
        return
    length = model.arrow_head_size(stroke.size, prof["head_size"])
    color = QtGui.QColor(stroke.color)
    painter = QtGui.QPainter(img)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
        painter.translate(-origin[0], -origin[1])
        painter.scale(scale, scale)         # geometry in mm
        pen = QtGui.QPen(color, stroke.size, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap,
                         QtCore.Qt.RoundJoin)
        for at_end, wanted in ((True, prof["head_end"]), (False, prof["head_start"])):
            if not wanted:
                continue
            tip = chain[-1] if at_end else chain[0]
            kind, g = geom.arrow_head(tip, geom.chain_end_direction(chain, at_end), length,
                                      prof["head_style"])
            if kind == "lines":
                painter.setPen(pen)
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(*p) for p in g]))
            elif kind == "polygon":
                painter.setPen(pen)
                painter.setBrush(color)
                painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(*p) for p in g]))
            else:
                (cx, cy), radius = g
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QtCore.QPointF(cx, cy), radius, radius)
    finally:
        painter.end()
