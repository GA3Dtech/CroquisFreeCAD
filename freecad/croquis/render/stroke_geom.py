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


def straight_points(x0, y0, x1, y1, p0, p1, step):
    """Points every `step` along a straight segment, pressure from p0 to p1
    (raster brushes drawn with Shift)."""
    n = max(1, int(math.ceil(math.hypot(x1 - x0, y1 - y0) / step)))
    return [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n, p0 + (p1 - p0) * k / n)
            for k in range(n + 1)]


def snap_angle(x0, y0, x1, y1, step_deg=15.0):
    """End point moved so the segment angle is a multiple of `step_deg`."""
    d = math.hypot(x1 - x0, y1 - y0)
    if d == 0:
        return x1, y1
    step = math.radians(step_deg)
    a = round(math.atan2(y1 - y0, x1 - x0) / step) * step
    return x0 + d * math.cos(a), y0 + d * math.sin(a)


def distance_to_polyline(pts, x, y):
    """Smallest distance from (x, y) to the polyline through pts[i][:2]."""
    if not pts:
        return float("inf")
    if len(pts) == 1:
        return math.hypot(x - pts[0][0], y - pts[0][1])
    best = float("inf")
    for i in range(len(pts) - 1):
        ax, ay = pts[i][0], pts[i][1]
        bx, by = pts[i + 1][0], pts[i + 1][1]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else clamp(((x - ax) * dx + (y - ay) * dy) / L)
        d = math.hypot(x - ax - t * dx, y - ay - t * dy)
        if d < best:
            best = d
    return best


# ----------------------------------------------------------------------
#  Bezier chains (vector strokes)
#
#  A chain is a flat list of control points P0 C1 C2 P1 C1 C2 P2 ...
#  (3n + 1 points for n cubic segments). Anchors are at indices 0, 3, 6...
# ----------------------------------------------------------------------
def _bez(p0, p1, p2, p3, t):
    mt = 1.0 - t
    a, b, c, d = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def _bez_d1(p0, p1, p2, p3, t):
    mt = 1.0 - t
    a, b, c = 3 * mt * mt, 6 * mt * t, 3 * t * t
    return (a * (p1[0] - p0[0]) + b * (p2[0] - p1[0]) + c * (p3[0] - p2[0]),
            a * (p1[1] - p0[1]) + b * (p2[1] - p1[1]) + c * (p3[1] - p2[1]))


def _bez_d2(p0, p1, p2, p3, t):
    mt = 1.0 - t
    return (6 * mt * (p2[0] - 2 * p1[0] + p0[0]) + 6 * t * (p3[0] - 2 * p2[0] + p1[0]),
            6 * mt * (p2[1] - 2 * p1[1] + p0[1]) + 6 * t * (p3[1] - 2 * p2[1] + p1[1]))


def line_chain(x0, y0, x1, y1):
    """Bezier chain of a straight segment."""
    return [(x0, y0), (x0 + (x1 - x0) / 3.0, y0 + (y1 - y0) / 3.0),
            (x0 + 2 * (x1 - x0) / 3.0, y0 + 2 * (y1 - y0) / 3.0), (x1, y1)]


def anchors_to_chain(anchors):
    """Smooth Bezier chain through the anchors (Catmull-Rom tangents), for
    strokes built point by point."""
    n = len(anchors)
    if n == 0:
        return []
    if n == 1:
        a = anchors[0]
        return [a, a, a, a]
    out = [anchors[0]]
    for i in range(n - 1):
        p0 = anchors[max(i - 1, 0)]
        p1 = anchors[i]
        p2 = anchors[i + 1]
        p3 = anchors[min(i + 2, n - 1)]
        out.append((p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0))
        out.append((p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0))
        out.append(p2)
    return out


def sample_chain(chain, step):
    """Points about `step` apart along a Bezier chain, with the curvilinear
    abscissa of each one normalized to 0..1: [(x, y, t), ...]."""
    if len(chain) < 4:
        return [(p[0], p[1], 0.0) for p in chain[:1]]
    pts = []
    for i in range(0, len(chain) - 3, 3):
        p0, p1, p2, p3 = chain[i], chain[i + 1], chain[i + 2], chain[i + 3]
        poly = (math.hypot(p1[0] - p0[0], p1[1] - p0[1])
                + math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                + math.hypot(p3[0] - p2[0], p3[1] - p2[1]))
        n = max(1, int(math.ceil(poly / step)))
        for k in range(n):
            pts.append(_bez(p0, p1, p2, p3, k / float(n)))
    pts.append((chain[-1][0], chain[-1][1]))
    dist = [0.0]
    for i in range(1, len(pts)):
        dist.append(dist[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    total = dist[-1] or 1.0
    return [(x, y, d / total) for (x, y), d in zip(pts, dist)]


def profile_width(t, peak=0.5, tin=1.0, tout=1.0, k=0.7):
    """Width factor 0..1 of a vector stroke at abscissa t: the designer's
    thrown line, thin at the start, widest at `peak`, pointed at the end.
    Each half is a quarter sine raised to k; tin / tout blend it with a
    blunt (constant) end."""
    peak = clamp(peak, 0.05, 0.95)
    t = clamp(t)
    if t < peak:
        u = math.sin(0.5 * math.pi * t / peak) ** k
        return (1.0 - tin) + tin * u
    u = math.sin(0.5 * math.pi * (1.0 - t) / (1.0 - peak)) ** k
    return (1.0 - tout) + tout * u


# --- Schneider's curve fitting ("An algorithm for automatically fitting
#     digitized curves", Graphics Gems, 1990)
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(a, s):
    return (a[0] * s, a[1] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _unit(a):
    n = math.hypot(a[0], a[1])
    return (a[0] / n, a[1] / n) if n > 1e-12 else (0.0, 0.0)


def fit_chain(points, error):
    """Bezier chain approximating the points (x, y, ...) within `error`
    (same unit), split where the error is largest."""
    pts = []
    for p in points:
        q = (p[0], p[1])
        if not pts or math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) > 1e-6:
            pts.append(q)
    if len(pts) < 2:
        return [pts[0]] * 4 if pts else []
    if len(pts) == 2:
        return line_chain(pts[0][0], pts[0][1], pts[1][0], pts[1][1])
    t1 = _unit(_sub(pts[1], pts[0]))
    t2 = _unit(_sub(pts[-2], pts[-1]))
    out = [pts[0]]
    _fit_cubic(pts, 0, len(pts) - 1, t1, t2, error, out, 0)
    return out


def _fit_cubic(d, first, last, t1, t2, error, out, depth):
    if last - first == 1 or depth > 40:
        dist = math.hypot(d[last][0] - d[first][0], d[last][1] - d[first][1]) / 3.0
        out.extend([_add(d[first], _mul(t1, dist)), _add(d[last], _mul(t2, dist)), d[last]])
        return
    u = _chord_params(d, first, last)
    bez = _generate(d, first, last, u, t1, t2)
    err, split = _max_error(d, first, last, bez, u)
    if err < error * error:
        out.extend(bez[1:])
        return
    if err < (2 * error) ** 2:
        for _ in range(12):
            u = _reparameterize(d, first, last, u, bez)
            bez = _generate(d, first, last, u, t1, t2)
            err, split = _max_error(d, first, last, bez, u)
            if err < error * error:
                out.extend(bez[1:])
                return
    tc = _unit(_sub(d[split - 1], d[split + 1]))
    if tc == (0.0, 0.0):
        tc = _unit(_sub(d[split - 1], d[split]))
    _fit_cubic(d, first, split, t1, tc, error, out, depth + 1)
    _fit_cubic(d, split, last, _mul(tc, -1.0), t2, error, out, depth + 1)


def _chord_params(d, first, last):
    u = [0.0]
    for i in range(first + 1, last + 1):
        u.append(u[-1] + math.hypot(d[i][0] - d[i - 1][0], d[i][1] - d[i - 1][1]))
    total = u[-1] or 1.0
    return [v / total for v in u]


def _generate(d, first, last, u, t1, t2):
    p0, p3 = d[first], d[last]
    c00 = c01 = c11 = x0 = x1 = 0.0
    for i, t in enumerate(u):
        mt = 1.0 - t
        b0, b1, b2, b3 = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
        a0 = _mul(t1, b1)
        a1 = _mul(t2, b2)
        c00 += _dot(a0, a0)
        c01 += _dot(a0, a1)
        c11 += _dot(a1, a1)
        tmp = _sub(d[first + i], _add(_mul(p0, b0 + b1), _mul(p3, b2 + b3)))
        x0 += _dot(a0, tmp)
        x1 += _dot(a1, tmp)
    det = c00 * c11 - c01 * c01
    al = (x0 * c11 - c01 * x1) / det if abs(det) > 1e-12 else 0.0
    ar = (c00 * x1 - c01 * x0) / det if abs(det) > 1e-12 else 0.0
    seg = math.hypot(p3[0] - p0[0], p3[1] - p0[1])
    eps = 1e-6 * seg
    if al < eps or ar < eps:
        al = ar = seg / 3.0
    return [p0, _add(p0, _mul(t1, al)), _add(p3, _mul(t2, ar)), p3]


def _max_error(d, first, last, bez, u):
    split = (last - first + 1) // 2 + first
    worst = 0.0
    for i in range(first + 1, last):
        p = _bez(bez[0], bez[1], bez[2], bez[3], u[i - first])
        e = (p[0] - d[i][0]) ** 2 + (p[1] - d[i][1]) ** 2
        if e >= worst:
            worst = e
            split = i
    return worst, split


def _reparameterize(d, first, last, u, bez):
    out = []
    for i, t in enumerate(u):
        q = _bez(bez[0], bez[1], bez[2], bez[3], t)
        q1 = _bez_d1(bez[0], bez[1], bez[2], bez[3], t)
        q2 = _bez_d2(bez[0], bez[1], bez[2], bez[3], t)
        diff = _sub(q, d[first + i])
        den = _dot(q1, q1) + _dot(diff, q2)
        out.append(clamp(t - _dot(diff, q1) / den) if abs(den) > 1e-12 else t)
    return out


# ----------------------------------------------------------------------
#  Arrow heads
# ----------------------------------------------------------------------
def chain_end_direction(chain, at_end=True):
    """Unit direction of a Bezier chain leaving its start (at_end=False,
    pointing backwards, away from the curve) or arriving at its end."""
    pts = chain if at_end else list(reversed(chain))
    tip = pts[-1]
    for p in reversed(pts[:-1]):
        dx, dy = tip[0] - p[0], tip[1] - p[1]
        d = math.hypot(dx, dy)
        if d > 1e-9:
            return dx / d, dy / d
    return 1.0, 0.0


def arrow_head(tip, direction, length, style="open", spread_deg=24.0):
    """Geometry of an arrow head at `tip` pointing along `direction`:
    ("lines", [left, tip, right]) for open heads, ("polygon", [tip, left,
    right]) for filled ones, ("dot", (centre, radius))."""
    ux, uy = direction
    if style == "dot":
        return "dot", ((tip[0], tip[1]), length / 3.0)
    a = math.radians(spread_deg)
    ca, sa = math.cos(a), math.sin(a)
    # the two barbs: direction reversed, turned by +/- spread
    bx, by = -ux, -uy
    left = (tip[0] + length * (bx * ca - by * sa), tip[1] + length * (bx * sa + by * ca))
    right = (tip[0] + length * (bx * ca + by * sa), tip[1] + length * (-bx * sa + by * ca))
    if style == "filled":
        return "polygon", [tuple(tip[:2]), left, right]
    return "lines", [left, tuple(tip[:2]), right]


# ----------------------------------------------------------------------
#  Styled shapes (circle, ellipse, rectangle, arc)
# ----------------------------------------------------------------------
SHAPES = ("circle", "ellipse", "rect", "arc")
_K = 0.5522847498            # Bezier handle length of a quarter circle


def shape_box(kind, x0, y0, x1, y1, constrain):
    """Box (x0, y0, x1, y1) of a dragged shape: a circle (and a square or
    a constrained ellipse) keeps equal sides."""
    if kind == "circle" or (constrain and kind in ("rect", "ellipse")):
        side = max(abs(x1 - x0), abs(y1 - y0))
        x1 = x0 + math.copysign(side, (x1 - x0) or 1.0)
        y1 = y0 + math.copysign(side, (y1 - y0) or 1.0)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def shape_chain(kind, x0, y0, x1, y1, constrain=False):
    """Bezier chain of a shape dragged from (x0, y0) to (x1, y1):
    circle / ellipse / rect inscribed in the box (closed, starting at the
    top), arc from the press to the release point, bulging by a third of
    the chord (constrain: a half circle)."""
    if kind == "arc":
        dx, dy = x1 - x0, y1 - y0
        chord = math.hypot(dx, dy)
        if chord < 1e-9:
            return line_chain(x0, y0, x1, y1)
        nx, ny = dy / chord, -dx / chord             # left of the chord, upwards on screen
        sag = chord / 2.0 if constrain else chord / 3.0
        r = (chord * chord / 4.0 + sag * sag) / (2.0 * sag)
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        cx, cy = mx + nx * (sag - r), my + ny * (sag - r)
        a0 = math.atan2(y0 - cy, x0 - cx)
        a1 = math.atan2(y1 - cy, x1 - cx)
        sweep = a1 - a0
        # the arc goes through the bulge point (mid + n * sag)
        bx, by = mx + nx * sag, my + ny * sag
        ab = math.atan2(by - cy, bx - cx)
        if not _between(a0, ab, sweep):
            sweep = sweep - math.copysign(2 * math.pi, sweep)
        return arc_chain(cx, cy, r, r, a0, sweep)
    bx0, by0, bx1, by1 = shape_box(kind, x0, y0, x1, y1, constrain)
    if kind == "rect":
        corners = [(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1), (bx0, by0)]
        out = [corners[0]]
        for a, b in zip(corners, corners[1:]):
            out.extend(line_chain(a[0], a[1], b[0], b[1])[1:])
        return out
    cx, cy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
    return arc_chain(cx, cy, (bx1 - bx0) / 2.0, (by1 - by0) / 2.0, -math.pi / 2, 2 * math.pi)


def _between(a0, a, sweep):
    d = (a - a0) % (2 * math.pi)
    return d <= sweep if sweep >= 0 else (2 * math.pi - d) <= -sweep


def arc_chain(cx, cy, rx, ry, a0, sweep):
    """Bezier chain of an elliptic arc (angle a0, signed sweep, radians)."""
    n = max(1, int(math.ceil(abs(sweep) / (math.pi / 2) - 1e-9)))
    step = sweep / n
    k = 4.0 / 3.0 * math.tan(step / 4.0)
    out = [(cx + rx * math.cos(a0), cy + ry * math.sin(a0))]
    a = a0
    for _i in range(n):
        b = a + step
        out.append((cx + rx * (math.cos(a) - k * math.sin(a)),
                    cy + ry * (math.sin(a) + k * math.cos(a))))
        out.append((cx + rx * (math.cos(b) + k * math.sin(b)),
                    cy + ry * (math.sin(b) - k * math.cos(b))))
        out.append((cx + rx * math.cos(b), cy + ry * math.sin(b)))
        a = b
    return out


def hand_drawn(chain, closed, amount=1.0, seed=1):
    """A chain made to look drawn by hand: anchors moved a little (smooth,
    deterministic for a given seed and shape) and, for a closed shape, an
    overshoot past the start. amount 0 returns the chain unchanged."""
    if amount <= 0 or len(chain) < 4:
        return list(chain)
    import random
    rnd = random.Random(seed)
    xs = [p[0] for p in chain]
    ys = [p[1] for p in chain]
    size = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    jit = 0.012 * size * amount
    out = list(chain)
    for i in range(0, len(out), 3):
        dx, dy = rnd.uniform(-jit, jit), rnd.uniform(-jit, jit)
        if closed and i == len(out) - 1:
            dx, dy = dx * 0.5, dy * 0.5
        for j in (i - 1, i, i + 1):         # an anchor and its handles move together
            if 0 <= j < len(out):
                out[j] = (out[j][0] + dx, out[j][1] + dy)
    if closed:
        # overshoot: continue a little along the first segment
        p0, p1, p2, p3 = out[0], out[1], out[2], out[3]
        t = 0.25 * amount
        q1 = _lerp(p0, p1, t)
        q2 = _lerp(q1, _lerp(p1, p2, t), t)
        q3 = _bez(p0, p1, p2, p3, t)
        out.extend([_lerp(out[-1], q1, 0.33), q2, q3])
    return out


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
