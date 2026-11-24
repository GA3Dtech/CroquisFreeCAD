# SPDX-License-Identifier: LGPL-2.1-or-later
"""render/stroke_geom.py: pure geometry."""

import math

import pytest

from freecad.croquis.render import stroke_geom as g

pytestmark = pytest.mark.unit


def max_dev(points, chain):
    samples = g.sample_chain(chain, 0.05)
    return max(g.distance_to_polyline(samples, p[0], p[1]) for p in points)


# ----------------------------------------------------------------------
#  Input filtering
# ----------------------------------------------------------------------
def test_stabilizer_level0_is_raw():
    st = g.Stabilizer(0)
    for x, y in [(0, 0), (5, 3), (10, -2)]:
        assert st.feed(x, y) == (x, y)


def test_stabilizer_converges_and_smooths():
    st = g.Stabilizer(6)
    out = [st.feed(10.0, 0.0) for _ in range(200)]
    assert out[0] == (10.0, 0.0)
    st = g.Stabilizer(6)
    st.feed(0, 0)
    jitter = [st.feed(i, (1 if i % 2 else -1)) for i in range(1, 50)]
    assert max(abs(y) for _x, y in jitter[10:]) < 0.5      # jitter flattened
    st2 = g.Stabilizer(6)
    st2.feed(0, 0)
    for _ in range(200):
        last = st2.feed(10, 10)
    assert last == pytest.approx((10, 10), abs=1e-6)


def test_speed_pressure_monotonic():
    def pressure_at(speed_mm_s):
        sp = g.SpeedPressure()
        p = None
        for i in range(60):
            p = sp.feed(i * speed_mm_s * 0.01, 0, i * 0.01)
        return p
    values = [pressure_at(v) for v in (5, 50, 150, 300, 600, 2000)]
    assert all(a >= b for a, b in zip(values, values[1:]))
    assert values[0] == pytest.approx(1.0, abs=0.02)
    assert values[-1] == pytest.approx(g.SpeedPressure.LIGHTEST, abs=0.02)


def test_pressure_curve():
    assert g.pressure_curve(0.5, 1.0) == 0.5
    assert g.pressure_curve(0.5, 2.0) == pytest.approx(0.25)
    assert g.pressure_curve(1.5, 2.0) == 1.0 and g.pressure_curve(-1, 2.0) == 0.0


def test_taper_ends():
    pts = [(i, 0, 1.0) for i in range(51)]
    out = g.taper_ends(pts, 10, 10, lowest=0.1)
    assert out[0][2] == pytest.approx(0.1) and out[-1][2] == pytest.approx(0.1)
    assert out[25][2] == pytest.approx(1.0)
    assert [p[:2] for p in out] == [p[:2] for p in pts]
    assert g.taper_ends(pts[:2], 10, 10) == pts[:2]


# ----------------------------------------------------------------------
#  Interpolation
# ----------------------------------------------------------------------
def test_catmull_rom_passes_through_points():
    pts = [(0, 0, 0.2), (10, 5, 0.4), (20, 0, 0.6), (30, 8, 1.0)]
    poly = g.smooth_polyline(pts, 0.5)
    for p in pts:
        assert min(math.hypot(q[0] - p[0], q[1] - p[1]) for q in poly) < 1e-9
    span = g.catmull_rom_span(pts, 1, 0.5)
    assert span[0] == pts[1]
    assert all(0.4 <= q[2] <= 0.6 for q in span)


def test_smooth_polyline_degenerate():
    assert g.smooth_polyline([], 1) == []
    assert g.smooth_polyline([(1, 1, 1)], 1) == [(1, 1, 1)]


def test_anchors_to_chain_passes_through_anchors():
    anchors = [(0, 0), (10, 10), (20, 0), (30, 5)]
    chain = g.anchors_to_chain(anchors)
    assert len(chain) == 3 * (len(anchors) - 1) + 1
    assert chain[::3] == anchors
    assert g.anchors_to_chain([]) == []
    assert g.anchors_to_chain([(1, 2)]) == [(1, 2)] * 4


def test_line_chain_is_straight():
    chain = g.line_chain(0, 0, 30, 15)
    for x, y in chain:
        assert y == pytest.approx(x / 2)


def test_sample_chain_abscissa():
    s = g.sample_chain(g.line_chain(0, 0, 100, 0), 1.0)
    assert s[0][2] == 0 and s[-1][2] == pytest.approx(1)
    assert all(b[2] >= a[2] for a, b in zip(s, s[1:]))
    assert s[50][2] == pytest.approx(s[50][0] / 100, abs=0.02)


# ----------------------------------------------------------------------
#  Schneider fitting
# ----------------------------------------------------------------------
@pytest.mark.parametrize("tol", [0.05, 0.2, 0.5])
def test_fit_line(tol):
    pts = [(i * 0.5, i * 0.25) for i in range(100)]
    chain = g.fit_chain(pts, tol)
    assert len(chain) == 4
    assert max_dev(pts, chain) < tol


@pytest.mark.parametrize("tol", [0.05, 0.2, 0.5])
def test_fit_arc(tol):
    pts = [(50 * math.cos(a), 50 * math.sin(a)) for a in [i * math.pi / 200 for i in range(201)]]
    chain = g.fit_chain(pts, tol)
    assert (len(chain) - 1) % 3 == 0
    assert max_dev(pts, chain) < tol * 1.05


@pytest.mark.parametrize("tol", [0.1, 0.3])
def test_fit_s_curve(tol):
    pts = [(i * 0.5, 20 * math.sin(i * 0.5 / 15.0)) for i in range(200)]
    chain = g.fit_chain(pts, tol)
    assert max_dev(pts, chain) < tol * 1.05
    assert chain[0] == pts[0] and chain[-1] == pts[-1]


def test_fit_degenerate():
    assert g.fit_chain([], 0.1) == []
    assert g.fit_chain([(1, 1)], 0.1) == [(1, 1)] * 4
    assert g.fit_chain([(1, 1), (1, 1), (1, 1)], 0.1) == [(1, 1)] * 4
    assert len(g.fit_chain([(0, 0), (5, 5)], 0.1)) == 4


# ----------------------------------------------------------------------
#  Width profile, angles, hit testing
# ----------------------------------------------------------------------
def test_profile_width():
    assert g.profile_width(0) == pytest.approx(0) and g.profile_width(1) == pytest.approx(0)
    assert g.profile_width(0.5) == pytest.approx(1)
    assert g.profile_width(0.3, peak=0.3) == pytest.approx(1)
    assert g.profile_width(0, tin=0) == pytest.approx(1)      # blunt start
    assert g.profile_width(1, tout=0.5) == pytest.approx(0.5)
    vals = [g.profile_width(t / 20, peak=0.5) for t in range(11)]
    assert all(b >= a for a, b in zip(vals, vals[1:]))


def test_snap_angle():
    x, y = g.snap_angle(0, 0, 10, 1)
    assert y == pytest.approx(0) and x == pytest.approx(math.hypot(10, 1))
    x, y = g.snap_angle(0, 0, 10, 9)
    assert x == pytest.approx(y)
    assert g.snap_angle(3, 3, 3, 3) == (3, 3)


def test_straight_points():
    pts = g.straight_points(0, 0, 10, 0, 0.2, 1.0, 1.0)
    assert pts[0] == (0, 0, 0.2) and pts[-1] == (10, 0, 1.0) and len(pts) == 11


def test_distance_to_polyline():
    poly = [(0, 0), (10, 0), (10, 10)]
    assert g.distance_to_polyline(poly, 5, 0) == 0           # on the edge
    assert g.distance_to_polyline(poly, 5, 3) == pytest.approx(3)
    assert g.distance_to_polyline(poly, 13, 5) == pytest.approx(3)
    assert g.distance_to_polyline(poly, -4, -3) == pytest.approx(5)   # beyond the end
    assert g.distance_to_polyline([], 0, 0) == float("inf")
    assert g.distance_to_polyline([(1, 1)], 4, 5) == pytest.approx(5)
    assert g.distance_to_polyline([(1, 1), (1, 1)], 1, 2) == pytest.approx(1)


# ----------------------------------------------------------------------
#  Arrow heads
# ----------------------------------------------------------------------
def test_chain_end_direction():
    chain = g.line_chain(0, 0, 10, 0)
    assert g.chain_end_direction(chain, True) == pytest.approx((1, 0))
    assert g.chain_end_direction(chain, False) == pytest.approx((-1, 0))
    curved = g.anchors_to_chain([(0, 0), (10, 10), (20, 0)])
    dx, dy = g.chain_end_direction(curved, True)
    assert dx > 0 and dy < 0                     # arriving downwards-right... (y down)
    assert g.chain_end_direction([(1, 1), (1, 1)], True) == (1.0, 0.0)


@pytest.mark.parametrize("direction", [(1, 0), (0, 1), (-0.6, 0.8)])
def test_arrow_head_open_and_filled(direction):
    tip = (50.0, 20.0)
    kind, (left, t, right) = g.arrow_head(tip, direction, 6.0, "open")
    assert kind == "lines" and t == tip
    for p in (left, right):
        assert math.hypot(p[0] - tip[0], p[1] - tip[1]) == pytest.approx(6.0)
        # the barbs point back along the direction
        assert (p[0] - tip[0]) * direction[0] + (p[1] - tip[1]) * direction[1] < 0
    mid = ((left[0] + right[0]) / 2 - tip[0], (left[1] + right[1]) / 2 - tip[1])
    n = math.hypot(*mid)
    assert (mid[0] / n, mid[1] / n) == pytest.approx((-direction[0], -direction[1]), abs=1e-9)
    kind, poly = g.arrow_head(tip, direction, 6.0, "filled")
    assert kind == "polygon" and poly[0] == tip and len(poly) == 3
    kind, (centre, radius) = g.arrow_head(tip, direction, 6.0, "dot")
    assert kind == "dot" and centre == tip and radius == pytest.approx(2.0)


# ----------------------------------------------------------------------
#  Styled shapes
# ----------------------------------------------------------------------
def chain_points(chain):
    return g.sample_chain(chain, 0.2)


def test_circle_and_ellipse():
    chain = g.shape_chain("circle", 10, 10, 50, 30)        # circle: equal sides
    pts = chain_points(chain)
    cx, cy, r = 30, 30, 20
    assert max(abs(math.hypot(x - cx, y - cy) - r) for x, y, _t in pts) < 0.03
    assert pts[0][:2] == pytest.approx((30, 10))           # starts at the top
    e = chain_points(g.shape_chain("ellipse", 0, 0, 40, 20))
    assert max(abs(((x - 20) / 20) ** 2 + ((y - 10) / 10) ** 2 - 1) for x, y, _t in e) < 0.01
    sq = g.shape_chain("ellipse", 0, 0, 40, 20, constrain=True)
    assert max(p[1] for p in chain_points(sq)) == pytest.approx(40, abs=0.05)


def test_rect_and_square():
    chain = g.shape_chain("rect", 5, 5, 25, 15)
    assert chain[0] == (5, 5) and chain[-1] == (5, 5)
    assert len(chain) == 13                                  # four straight segments
    xs, ys = [p[0] for p in chain], [p[1] for p in chain]
    assert (min(xs), max(xs), min(ys), max(ys)) == (5, 25, 5, 15)
    sq = g.shape_chain("rect", 5, 5, 25, 15, constrain=True)
    assert max(p[1] for p in sq) == 25


def test_arc():
    chain = g.shape_chain("arc", 0, 0, 40, 0)
    assert chain[0] == pytest.approx((0, 0)) and chain[-1] == pytest.approx((40, 0))
    pts = chain_points(chain)
    assert min(y for _x, y, _t in pts) == pytest.approx(-40 / 3, abs=0.05)   # bulge
    half = chain_points(g.shape_chain("arc", 0, 0, 40, 0, constrain=True))
    assert min(y for _x, y, _t in half) == pytest.approx(-20, abs=0.05)


def test_hand_drawn_is_small_deterministic_and_overshoots():
    chain = g.shape_chain("circle", 0, 0, 40, 40)
    a = g.hand_drawn(chain, True, seed=3)
    assert a == g.hand_drawn(chain, True, seed=3)
    assert len(a) == len(chain) + 3                          # overshoot past the start
    for p, q in zip(chain, a):
        assert math.hypot(p[0] - q[0], p[1] - q[1]) < 0.012 * 40 * 3
    assert g.hand_drawn(chain, True, amount=0) == chain
