# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - sheet data model
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
model.py (Croquis) - what a sheet is made of, independent of Qt and FreeCAD
so it can be tested anywhere and stored in a document as JSON.

All lengths are in millimetres on the sheet (origin top left, y down, like
an image). The resolution (dpi) only matters when rendering, so a sheet can
be re-rendered at another resolution without touching its strokes.

The labels below are English literals marked with N_(): tools/i18n.py
collects them like tr() texts, and the GUI translates them with tr(label)
when it shows them.
"""

import json
import os


def N_(text):
    """Mark a text for translation without translating it (done at display)."""
    return text


FORMAT_VERSION = 1

# key, label, width mm, height mm
FORMATS = [
    ("A5L", N_("A5 landscape"), 210.0, 148.0),
    ("A5P", N_("A5 portrait"), 148.0, 210.0),
    ("A4L", N_("A4 landscape"), 297.0, 210.0),
    ("A4P", N_("A4 portrait"), 210.0, 297.0),
    ("A3L", N_("A3 landscape"), 420.0, 297.0),
    ("A3P", N_("A3 portrait"), 297.0, 420.0),
    ("SQ", N_("Square 200 mm"), 200.0, 200.0),
]

DPIS = [72, 100, 150, 200, 300]

# key, label, colour (None = transparent)
PAPERS = [
    ("transparent", N_("Transparent"), None),
    ("white", N_("White"), "#ffffff"),
    ("layout", N_("Layout pad"), "#f4f3ec"),
    ("grey", N_("Tinted grey"), "#bcbdb9"),
    ("kraft", N_("Kraft"), "#c3a27a"),
]

# Layers from bottom to top: key, label, blend mode
LAYERS = [
    ("underlay", N_("Underlay"), "normal"),
    ("construction", N_("Construction"), "normal"),
    ("marker", N_("Marker"), "multiply"),
    ("lines", N_("Lines"), "normal"),
    ("highlights", N_("Highlights"), "normal"),
]
LAYER_KEYS = [k for k, _l, _b in LAYERS]

# Drawing tools and their defaults. Sizes in mm.
#   pressure_width: share of the width driven by pressure (0 = constant)
#   pressure_alpha: share of the opacity driven by pressure
#   grain: strength of the paper grain showing through (0 = solid)
TOOLS = {
    "pencil": {
        "label": N_("Mechanical pencil"),
        "layer": "construction",
        "color": "#262626",
        "size": 0.45,
        "opacity": 0.85,
        "pressure_width": 0.3,
        "pressure_alpha": 0.85,
        "grain": 0.45,
    },
    "marker": {
        "label": N_("Alcohol marker"),
        "layer": "marker",
        "color": "#b7bcc0",
        "size": 4.0,
        "opacity": 0.45,
        "pressure_width": 0.35,
        "pressure_alpha": 0.0,
        "grain": 0.0,
    },
}
TOOL_KEYS = ["pencil", "marker"]


def format_size(key):
    """(width, height) in mm of a sheet format, A4 landscape if unknown."""
    for k, _label, w, h in FORMATS:
        if k == key:
            return w, h
    return 297.0, 210.0


def paper_color(key):
    for k, _label, color in PAPERS:
        if k == key:
            return color
    return None


def layer_blend(key):
    for k, _label, blend in LAYERS:
        if k == key:
            return blend
    return "normal"


# ----------------------------------------------------------------------
#  Palettes (resources/palettes/*.json)
# ----------------------------------------------------------------------
# Names of the built-in palettes, for translation
PALETTE_NAMES = [N_("Cool greys"), N_("Warm greys"), N_("Neutral greys"), N_("Accents")]

PALETTE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "resources", "palettes")


def load_palettes():
    """[(name, [(label, "#rrggbb"), ...]), ...] from the palette files,
    sorted by their "order" field."""
    out = []
    try:
        names = sorted(n for n in os.listdir(PALETTE_DIR) if n.endswith(".json"))
    except OSError:
        return out
    for name in names:
        try:
            with open(os.path.join(PALETTE_DIR, name), "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        for pal in data.get("palettes", []):
            out.append((pal.get("order", 99), pal["name"],
                        [(c[0], c[1]) for c in pal.get("colors", [])]))
    out.sort(key=lambda p: p[0])
    return [(name, colors) for _o, name, colors in out]


# ----------------------------------------------------------------------
#  Strokes and sheet
# ----------------------------------------------------------------------
class Stroke(object):
    """One gesture: a tool, its settings at the time, and the input points
    (x mm, y mm, pressure 0..1)."""

    __slots__ = ("tool", "color", "size", "opacity", "layer", "points")

    def __init__(self, tool, color, size, opacity, layer, points=None):
        self.tool = tool
        self.color = color
        self.size = float(size)
        self.opacity = float(opacity)
        self.layer = layer
        self.points = points if points is not None else []

    def bounds(self):
        """(xmin, ymin, xmax, ymax) in mm, grown by the stroke width."""
        if not self.points:
            return None
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        m = self.size
        return min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m

    def to_dict(self):
        flat = []
        for x, y, p in self.points:
            flat.extend((round(x, 2), round(y, 2), round(p, 3)))
        return {"t": self.tool, "c": self.color, "s": round(self.size, 3),
                "o": round(self.opacity, 3), "l": self.layer, "p": flat}

    @classmethod
    def from_dict(cls, d):
        flat = d.get("p", [])
        pts = [(flat[i], flat[i + 1], flat[i + 2]) for i in range(0, len(flat) - 2, 3)]
        return cls(d.get("t", "pencil"), d.get("c", "#000000"), d.get("s", 1.0),
                   d.get("o", 1.0), d.get("l", "lines"), pts)


class SheetData(object):
    """A drawing sheet: size, resolution, paper, layer settings, strokes."""

    def __init__(self, width=297.0, height=210.0, dpi=150, paper="transparent"):
        self.width = float(width)
        self.height = float(height)
        self.dpi = int(dpi)
        self.paper = paper
        self.layers = {k: {"opacity": 1.0, "visible": True} for k in LAYER_KEYS}
        self.strokes = []

    # --- size in pixels at the sheet resolution
    @property
    def scale(self):
        """Pixels per millimetre."""
        return self.dpi / 25.4

    def pixel_size(self):
        s = self.scale
        return max(1, int(round(self.width * s))), max(1, int(round(self.height * s)))

    def layer_strokes(self, layer):
        return [s for s in self.strokes if s.layer == layer]

    # --- serialization
    def to_json(self):
        return json.dumps({
            "version": FORMAT_VERSION,
            "width": self.width, "height": self.height,
            "dpi": self.dpi, "paper": self.paper,
            "layers": self.layers,
            "strokes": [s.to_dict() for s in self.strokes],
        }, separators=(",", ":"))

    @classmethod
    def from_json(cls, text):
        sheet = cls()
        if not text:
            return sheet
        d = json.loads(text)
        sheet.width = float(d.get("width", sheet.width))
        sheet.height = float(d.get("height", sheet.height))
        sheet.dpi = int(d.get("dpi", sheet.dpi))
        sheet.paper = d.get("paper", sheet.paper)
        for k, v in d.get("layers", {}).items():
            if k in sheet.layers:
                sheet.layers[k].update(v)
        sheet.strokes = [Stroke.from_dict(s) for s in d.get("strokes", [])]
        return sheet
