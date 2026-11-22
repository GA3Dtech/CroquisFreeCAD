# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - stroke geometry
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
stroke_geom.py (Croquis) - pure geometry on input points, no Qt: steadying
the hand, pressure from mouse speed, tapering, and the Catmull-Rom
interpolation used to draw smooth curves from sparse input.

Points are (x, y, pressure) tuples in millimetres.
"""

import math


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def pressure_curve(p, exponent):
    """Tablet pressure through the user's curve (exponent > 1 = harder)."""
    p = clamp(p)
    if exponent == 1.0 or p == 0.0:
        return p
    return p ** exponent


# ----------------------------------------------------------------------
#  Input filtering
# ----------------------------------------------------------------------
class Stabilizer(object):
    """Exponential smoothing of the pen position. Level 0 keeps the raw
    input; each level adds lag, which flattens the hand's jitter. The caller
    appends the raw last point when the pen lifts, so the stroke still ends
    where it should."""

    def __init__(self, level):
        self.k = 1.0 / (1.0 + 0.7 * max(0, level))
        self.x = self.y = None

    def feed(self, x, y):
        if self.x is None:
            self.x, self.y = x, y
        else:
            self.x += (x - self.x) * self.k
            self.y += (y - self.y) * self.k
        return self.x, self.y


class SpeedPressure(object):
    """Pressure simulated from the mouse speed: a fast stroke is thinner and
    lighter, like a pen thrown across the paper. Smoothed so the width does
    not flicker with the event rate."""

    SLOW = 20.0     # mm/s and below: full pressure
    FAST = 600.0    # mm/s and above: lightest pressure
    LIGHTEST = 0.25

    def __init__(self):
        self.p = 0.6
        self.last = None

    def feed(self, x, y, t):
        """t in seconds. Returns the pressure for this point."""
        if self.last is not None:
            lx, ly, lt = self.last
            dt = max(t - lt, 1e-3)
            v = math.hypot(x - lx, y - ly) / dt
            f = clamp((v - self.SLOW) / (self.FAST - self.SLOW))
            target = 1.0 - (1.0 - self.LIGHTEST) * math.sqrt(f)
            self.p += (target - self.p) * 0.25
        self.last = (x, y, t)
        return self.p


def taper_ends(points, start_mm, end_mm, lowest=0.15):
    """Fade the pressure in over the first `start_mm` and out over the last
    `end_mm` of the stroke: the designer's thrown line, thin at both ends.
    Returns a new list."""
    n = len(points)
    if n < 3:
        return list(points)
    dist = [0.0]
    for i in range(1, n):
        dist.append(dist[-1] + math.hypot(points[i][0] - points[i - 1][0],
                                          points[i][1] - points[i - 1][1]))
    total = dist[-1]
    if total <= 0:
        return list(points)
    # short strokes: keep both tapers inside the stroke
    s = min(start_mm, total * 0.4)
    e = min(end_mm, total * 0.4)
    out = []
    for (x, y, p), d in zip(points, dist):
        f = 1.0
        if s > 0 and d < s:
            f = min(f, lowest + (1.0 - lowest) * _ease(d / s))
        if e > 0 and total - d < e:
            f = min(f, lowest + (1.0 - lowest) * _ease((total - d) / e))
        out.append((x, y, p * f))
    return out


def _ease(t):
    """Smooth 0..1 ramp (sine ease-out): fast at first, then levels off."""
    return math.sin(clamp(t) * math.pi / 2.0)


# ----------------------------------------------------------------------
#  Interpolation
# ----------------------------------------------------------------------
def catmull_rom_span(points, i, step):
    """Points interpolating the span points[i] -> points[i+1] with a
    uniform Catmull-Rom (neighbours clamped at the ends),
    spaced about `step` apart (same unit as the points). The first point of
    the span is included, the last one is not (it starts the next span).
    Pressure is interpolated linearly."""
    n = len(points)
    p0 = points[max(i - 1, 0)]
    p1 = points[i]
    p2 = points[min(i + 1, n - 1)]
    p3 = points[min(i + 2, n - 1)]
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    count = max(1, int(math.ceil(length / step))) if step > 0 else 1
    out = []
    for k in range(count):
        t = k / float(count)
        t2 = t * t
        t3 = t2 * t
        x = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t
                   + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                   + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
        y = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t
                   + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                   + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
        out.append((x, y, p1[2] + (p2[2] - p1[2]) * t))
    return out


def smooth_polyline(points, step):
    """Whole stroke interpolated with catmull_rom_span, last point added."""
    if len(points) < 2:
        return list(points)
    out = []
    for i in range(len(points) - 1):
        out.extend(catmull_rom_span(points, i, step))
    out.append(points[-1])
    return out
