# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
specs.py (Croquis tests) - deterministic description of the fixture
documents, independent of the addon code: strokes are written directly in
the sheet JSON format v1 ("t" tool, "c" colour, "s" size mm, "o" opacity,
"l" layer, "p" flat [x, y, pressure, ...] in mm, "q" params).

Used by build_fixtures.py (inside FreeCAD) and by the pure unit tests.
"""

import math

FORMATS = [("A5L", 210.0, 148.0), ("A5P", 148.0, 210.0), ("A4L", 297.0, 210.0),
           ("A4P", 210.0, 297.0), ("A3L", 420.0, 297.0), ("A3P", 297.0, 420.0),
           ("SQ", 200.0, 200.0)]
DPIS = [72, 100, 150, 200, 300]
PAPERS = ["transparent", "white", "layout", "grey", "kraft"]
PLANES = ["XY", "XZ", "YZ"]


def _flat(points):
    out = []
    for x, y, p in points:
        out.extend((round(x, 2), round(y, 2), round(p, 3)))
    return out


def raster(tool, color, size, opacity, layer, points):
    return {"t": tool, "c": color, "s": size, "o": opacity, "l": layer, "p": _flat(points)}


def vector(tool, color, size, opacity, chain, params):
    return {"t": tool, "c": color, "s": size, "o": opacity, "l": "lines",
            "p": _flat([(x, y, 1.0) for x, y in chain]), "q": params}


def wave(x0, y0, length, amp, n=60, p0=0.3, p1=1.0, periods=1.5):
    """Sine path from (x0, y0), pressure ramping from p0 to p1."""
    return [(x0 + length * i / (n - 1),
             y0 + amp * math.sin(2 * math.pi * periods * i / (n - 1)),
             p0 + (p1 - p0) * i / (n - 1)) for i in range(n)]


def line_chain(x0, y0, x1, y1):
    return [(x0, y0), (x0 + (x1 - x0) / 3, y0 + (y1 - y0) / 3),
            (x0 + 2 * (x1 - x0) / 3, y0 + 2 * (y1 - y0) / 3), (x1, y1)]


def anchors_chain(anchors):
    """Catmull-Rom tangents -> Bezier chain (same rule as the addon)."""
    out = [anchors[0]]
    n = len(anchors)
    for i in range(n - 1):
        p0, p1 = anchors[max(i - 1, 0)], anchors[i]
        p2, p3 = anchors[i + 1], anchors[min(i + 2, n - 1)]
        out.append((p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6))
        out.append((p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6))
        out.append(p2)
    return out


def default_layers():
    return {k: {"opacity": 1.0, "visible": True}
            for k in ("underlay", "construction", "marker", "lines", "highlights")}


def sheet(label, fmt="A5L", dpi=100, paper="white", plane="XZ", strokes=None, layers=None):
    w, h = dict((k, (a, b)) for k, a, b in FORMATS)[fmt]
    lay = default_layers()
    for k, v in (layers or {}).items():
        lay[k].update(v)
    return {"label": label, "format": fmt, "dpi": dpi, "paper": paper, "plane": plane,
            "data": {"version": 1, "width": w, "height": h, "dpi": dpi, "paper": paper,
                     "layers": lay, "strokes": strokes or []}}


def basic_strokes(w, h):
    """A marker band, a pencil wave and a spline, scaled to the sheet."""
    return [
        raster("marker", "#9b9fa5", 6.0, 0.45, "marker", wave(w * 0.1, h * 0.55, w * 0.8, h * 0.1)),
        raster("pencil", "#262626", 0.45, 0.85, "construction",
               wave(w * 0.1, h * 0.3, w * 0.8, h * 0.08, periods=1.0)),
        vector("spline", "#1b1b1d", 1.2, 1.0,
               anchors_chain([(w * 0.1, h * 0.8), (w * 0.4, h * 0.65), (w * 0.9, h * 0.85)]),
               {"peak": 0.45, "tin": 1.0, "tout": 1.0}),
    ]


def tool_strokes():
    """One stroke of every tool on an A5 landscape sheet."""
    return [
        raster("marker", "#b7bcc0", 12.0, 0.45, "marker", wave(20, 70, 170, 12)),
        raster("marker", "#868b91", 8.0, 0.45, "marker", wave(20, 80, 170, -10, periods=1.0)),
        raster("pencil", "#262626", 0.45, 0.85, "construction", wave(20, 20, 170, 0, p0=0.1)),
        raster("grease", "#1b1b1b", 1.3, 0.95, "lines", wave(20, 32, 170, 0, p0=0.05)),
        raster("highlight", "#ffffff", 1.2, 0.9, "highlights", wave(30, 66, 120, 3, p0=0.9)),
        vector("line", "#1b1b1d", 0.9, 1.0, line_chain(25, 130, 185, 105),
               {"peak": 0.45, "tin": 0.6, "tout": 1.0}),
        vector("spline", "#1b1b1d", 1.6, 1.0,
               anchors_chain([(20, 115), (60, 95), (110, 125), (180, 100)]),
               {"peak": 0.35, "tin": 1.0, "tout": 1.0}),
    ]


def documents():
    """{document name: [sheet spec, ...]}"""
    docs = {}
    docs["formats"] = [
        sheet("fmt_%s_%d" % (fmt, DPIS[i % len(DPIS)]), fmt, DPIS[i % len(DPIS)], "white",
              strokes=basic_strokes(w, h))
        for i, (fmt, w, h) in enumerate(FORMATS)]
    docs["papers"] = [sheet("paper_%s" % p, "A5L", 100, p, strokes=basic_strokes(210, 148))
                      for p in PAPERS]
    tools = tool_strokes()
    docs["tools"] = [
        sheet("tools", "A5L", 150, "layout", strokes=tools),
        sheet("eraser_soft_all", "A5L", 150, "layout", strokes=tools + [
            raster("eraser", "#000000", 5.0, 1.0, "*", [(60, 10, 1.0), (75, 140, 1.0)])]),
        sheet("eraser_soft_marker", "A5L", 150, "layout", strokes=tools + [
            raster("eraser", "#000000", 6.0, 1.0, "marker", [(120, 10, 1.0), (130, 140, 0.5)])]),
        # a whole-stroke eraser deletes strokes: the sheet simply lacks them
        sheet("eraser_whole", "A5L", 150, "layout", strokes=[tools[0], tools[2], tools[6]]),
        sheet("layers_hidden_opacity", "A5L", 150, "white", strokes=tools,
              layers={"construction": {"visible": False}, "marker": {"opacity": 0.4},
                      "lines": {"opacity": 0.7}}),
    ]
    docs["planes"] = [sheet("plane_%s" % p, "A5L", 72, "transparent", p,
                            strokes=basic_strokes(210, 148)) for p in PLANES]
    return docs
