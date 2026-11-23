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


FORMAT_VERSION = 2


# ----------------------------------------------------------------------
#  Format migrations
#
#  Sheet JSON carries "version". Each entry of MIGRATIONS turns a dict of
#  version n into version n + 1 (returns a new dict). A file without
#  version is version 1 (v0.1 / v0.2 wrote it, but stay tolerant). A file
#  NEWER than FORMAT_VERSION is read as is: unknown fields and strokes are
#  kept untouched and written back, so an old addon never destroys data it
#  does not understand.
# ----------------------------------------------------------------------
def _v1_to_v2(d):
    """v2 (Croquis 0.3): content images and annotations. Adds the "images"
    layer and the "elements" list; strokes are unchanged."""
    d = dict(d)
    layers = dict(d.get("layers") or {})
    layers.setdefault("images", {"opacity": 1.0, "visible": True})
    d["layers"] = layers
    d.setdefault("elements", [])
    return d


MIGRATIONS = {1: _v1_to_v2}


def migrate(data):
    """Sheet dict brought to FORMAT_VERSION (or left as is when newer)."""
    d = dict(data)
    v = d.get("version")
    if not isinstance(v, int) or v < 1:
        v = 1
    d["version"] = v
    while v < FORMAT_VERSION:
        d = MIGRATIONS[v](d)
        v += 1
        d["version"] = v
    return d

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
    ("underlay", N_("Underlay"), "normal"),     # 3D view guide, not exported
    ("images", N_("Images"), "normal"),         # pasted / captured pictures
    ("construction", N_("Construction"), "normal"),
    ("marker", N_("Marker"), "multiply"),
    ("lines", N_("Lines"), "normal"),
    ("highlights", N_("Highlights"), "normal"),
]
LAYER_KEYS = [k for k, _l, _b in LAYERS]

# Layers the eraser can work on (layer "*" of an eraser stroke = all of them)
ERASABLE_LAYERS = ["construction", "marker", "lines", "highlights"]
# Layers shown in the board's layer panel (the guide has its own controls)
PANEL_LAYERS = ["underlay", "images"] + ERASABLE_LAYERS
ALL_LAYERS = "*"

# Drawing tools and their defaults. Sizes in mm.
#   kind: "raster" (pressure brush), "vector" (tapered Bezier stroke whose
#         width follows a profile), "eraser" (raster, removes pixels)
#   pressure_width: share of the width driven by pressure (0 = constant)
#   pressure_alpha: share of the opacity driven by pressure
#   grain: strength of the paper grain showing through (0 = solid)
#   grain_pressure: how much a hard press fills the grain (0 = never)
TOOLS = {
    "pencil": {
        "label": N_("Mechanical pencil"),
        "kind": "raster",
        "layer": "construction",
        "color": "#262626",
        "size": 0.45,
        "opacity": 0.85,
        "pressure_width": 0.3,
        "pressure_alpha": 0.85,
        "grain": 0.45,
        "grain_pressure": 0.3,
    },
    "grease": {
        "label": N_("Grease pencil"),
        "kind": "raster",
        "layer": "lines",
        "color": "#1b1b1b",
        "size": 1.3,
        "opacity": 0.95,
        "pressure_width": 0.6,
        "pressure_alpha": 0.5,
        "grain": 0.9,
        "grain_pressure": 0.85,
    },
    "marker": {
        "label": N_("Alcohol marker"),
        "kind": "raster",
        "layer": "marker",
        "color": "#b7bcc0",
        "size": 4.0,
        "opacity": 0.45,
        "pressure_width": 0.35,
        "pressure_alpha": 0.0,
        "grain": 0.0,
        "grain_pressure": 0.0,
    },
    "highlight": {
        "label": N_("White highlight"),
        "kind": "raster",
        "layer": "highlights",
        "color": "#ffffff",
        "size": 1.2,
        "opacity": 0.9,
        "pressure_width": 0.4,
        "pressure_alpha": 0.7,
        "grain": 0.35,
        "grain_pressure": 0.6,
    },
    "line": {
        "label": N_("Straight line"),
        "kind": "vector",
        "layer": "lines",
        "color": "#1b1b1d",
        "size": 0.9,
        "opacity": 1.0,
        "pressure_width": 1.0,
        "pressure_alpha": 0.0,
        "grain": 0.0,
        "grain_pressure": 0.0,
    },
    "spline": {
        "label": N_("Spline stroke"),
        "kind": "vector",
        "layer": "lines",
        "color": "#1b1b1d",
        "size": 1.2,
        "opacity": 1.0,
        "pressure_width": 1.0,
        "pressure_alpha": 0.0,
        "grain": 0.0,
        "grain_pressure": 0.0,
    },
    "arrow": {
        "label": N_("Arrow"),
        "kind": "vector",
        "layer": "lines",
        "color": "#1b1b1d",
        "size": 0.8,
        "opacity": 1.0,
        "pressure_width": 1.0,
        "pressure_alpha": 0.0,
        "grain": 0.0,
        "grain_pressure": 0.0,
    },
    "eraser": {
        "label": N_("Eraser"),
        "kind": "eraser",
        "layer": ALL_LAYERS,
        "color": "#000000",
        "size": 5.0,
        "opacity": 1.0,
        "pressure_width": 0.5,
        "pressure_alpha": 0.3,
        "grain": 0.0,
        "grain_pressure": 0.0,
    },
}
TOOL_KEYS = ["pencil", "grease", "marker", "highlight", "line", "spline", "arrow", "eraser"]

# Width profile of vector strokes (stroke.params):
#   peak: position of the widest point along the stroke (0..1)
#   tin / tout: taper at the start / end (0 = blunt, 1 = pointed)
DEFAULT_PROFILE = {"peak": 0.45, "tin": 1.0, "tout": 1.0}

# Arrow heads (params of "arrow" strokes): at the start / end, style
# open / filled / dot, size in mm (0 = from the stroke width)
ARROW_STYLES = ["open", "filled", "dot"]
DEFAULT_ARROW = {"head_start": False, "head_end": True, "head_style": "open",
                 "head_size": 0.0, "peak": 0.5, "tin": 0.0, "tout": 0.0}


def arrow_head_size(size, head_size):
    """Head length in mm: given, or from the stroke width."""
    return head_size if head_size and head_size > 0 else 2.5 + 4.0 * size


def tool_kind(tool):
    """Kind of a tool; "unknown" for a tool written by a newer version of
    the addon (such strokes are kept in the file but not drawn)."""
    t = TOOLS.get(tool)
    return t["kind"] if t is not None else "unknown"


def eraser_targets(stroke):
    """Layers an eraser stroke works on."""
    return list(ERASABLE_LAYERS) if stroke.layer == ALL_LAYERS else [stroke.layer]


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


def fit_rect(img_w, img_h, area_w, area_h, margin=0.05):
    """(x, y, w, h) of a picture of img_w x img_h pixels fitted inside an
    area of area_w x area_h mm, centred, proportions kept, leaving `margin`
    (share of the area) free on each side."""
    if img_w <= 0 or img_h <= 0:
        raise ValueError("empty image")
    aw, ah = area_w * (1 - 2 * margin), area_h * (1 - 2 * margin)
    k = min(aw / img_w, ah / img_h)
    w, h = img_w * k, img_h * k
    return (area_w - w) / 2.0, (area_h - h) / 2.0, w, h


# ----------------------------------------------------------------------
#  Elements (format v2): items that are not strokes
# ----------------------------------------------------------------------
class ImageElement(object):
    """A content picture on the sheet (pasted, imported or captured).
    Position (top left corner before rotation), size in mm, rotation in
    degrees (clockwise, around the centre), opacity, layer; `render`: drawn
    in the image plane and the exports; `locked`: not selectable. `file`
    names the document property holding the picture (never base64 in the
    JSON); `camera` keeps the 3D view of a capture (or None)."""

    kind = "image"
    KEYS = ("kind", "id", "file", "x", "y", "w", "h", "rotation", "opacity", "layer",
            "render", "locked", "camera", "source_px")

    def __init__(self, id, file, x, y, w, h, rotation=0.0, opacity=1.0, layer="images",
                 render=True, locked=False, camera=None, source_px=None):
        self.id = id
        self.file = file
        self.x, self.y, self.w, self.h = float(x), float(y), float(w), float(h)
        self.rotation = float(rotation)
        self.opacity = float(opacity)
        self.layer = layer
        self.render = bool(render)
        self.locked = bool(locked)
        self.camera = camera
        self.source_px = source_px      # [w, h] of the stored picture
        self.extra = {}

    def copy(self):
        e = ImageElement.from_dict(self.to_dict())
        return e

    def bounds(self):
        """(xmin, ymin, xmax, ymax) in mm of the rotated rectangle."""
        import math
        cx, cy = self.x + self.w / 2.0, self.y + self.h / 2.0
        a = math.radians(self.rotation)
        hw = abs(self.w / 2.0 * math.cos(a)) + abs(self.h / 2.0 * math.sin(a))
        hh = abs(self.w / 2.0 * math.sin(a)) + abs(self.h / 2.0 * math.cos(a))
        return cx - hw, cy - hh, cx + hw, cy + hh

    def contains(self, px, py):
        """Is the sheet point (mm) inside the rotated rectangle?"""
        import math
        cx, cy = self.x + self.w / 2.0, self.y + self.h / 2.0
        a = -math.radians(self.rotation)
        dx, dy = px - cx, py - cy
        lx = dx * math.cos(a) - dy * math.sin(a)
        ly = dx * math.sin(a) + dy * math.cos(a)
        return abs(lx) <= self.w / 2.0 and abs(ly) <= self.h / 2.0

    def to_dict(self):
        d = dict(self.extra)
        d.update({"kind": "image", "id": self.id, "file": self.file,
                  "x": round(self.x, 3), "y": round(self.y, 3),
                  "w": round(self.w, 3), "h": round(self.h, 3),
                  "rotation": round(self.rotation, 3), "opacity": round(self.opacity, 3),
                  "layer": self.layer, "render": self.render, "locked": self.locked})
        if self.camera is not None:
            d["camera"] = self.camera
        if self.source_px is not None:
            d["source_px"] = list(self.source_px)
        return d

    @classmethod
    def from_dict(cls, d):
        e = cls(d.get("id", ""), d.get("file", ""), d.get("x", 0), d.get("y", 0),
                d.get("w", 10), d.get("h", 10), d.get("rotation", 0), d.get("opacity", 1),
                d.get("layer", "images"), d.get("render", True), d.get("locked", False),
                d.get("camera"), d.get("source_px"))
        e.extra = dict((k, v) for k, v in d.items() if k not in cls.KEYS)
        return e


class UnknownElement(object):
    """An element of a kind this version does not know: kept as is."""

    def __init__(self, data):
        self.data = dict(data)
        self.kind = data.get("kind", "?")

    def copy(self):
        return UnknownElement(self.data)

    def to_dict(self):
        return dict(self.data)


ELEMENT_KINDS = {"image": ImageElement}


def element_from_dict(d):
    cls = ELEMENT_KINDS.get(d.get("kind"))
    return cls.from_dict(d) if cls is not None else UnknownElement(d)


# ----------------------------------------------------------------------
#  Strokes and sheet
# ----------------------------------------------------------------------
class Stroke(object):
    """One gesture: a tool, its settings at the time, and the input points
    (x mm, y mm, pressure 0..1)."""

    __slots__ = ("tool", "color", "size", "opacity", "layer", "points", "params", "extra")

    # keys of the JSON form; anything else is kept in `extra`
    KEYS = ("t", "c", "s", "o", "l", "p", "q")

    def __init__(self, tool, color, size, opacity, layer, points=None, params=None):
        self.tool = tool
        self.color = color
        self.size = float(size)
        self.opacity = float(opacity)
        self.layer = layer
        # vector strokes: Bezier control points P0 C1 C2 P1 C1 C2 P2 ...
        # (pressure unused), raster strokes: input points
        self.points = points if points is not None else []
        self.params = dict(params) if params else {}
        self.extra = {}         # unknown JSON keys, written back unchanged

    @property
    def kind(self):
        return tool_kind(self.tool)

    def copy(self):
        s = Stroke(self.tool, self.color, self.size, self.opacity, self.layer,
                   list(self.points), self.params)
        s.extra = dict(self.extra)
        return s

    def profile(self):
        p = dict(DEFAULT_ARROW if self.tool == "arrow" else DEFAULT_PROFILE)
        p.update(self.params)
        return p

    def bounds(self):
        """(xmin, ymin, xmax, ymax) in mm, grown by the stroke width."""
        if not self.points:
            return None
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        m = self.size
        if self.tool == "arrow":
            m += arrow_head_size(self.size, self.profile()["head_size"])
        return min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m

    def to_dict(self):
        flat = []
        for x, y, p in self.points:
            flat.extend((round(x, 2), round(y, 2), round(p, 3)))
        d = dict(self.extra)
        d.update({"t": self.tool, "c": self.color, "s": round(self.size, 3),
                  "o": round(self.opacity, 3), "l": self.layer, "p": flat})
        if self.params:
            d["q"] = self.params
        return d

    @classmethod
    def from_dict(cls, d):
        flat = d.get("p", [])
        pts = [(flat[i], flat[i + 1], flat[i + 2]) for i in range(0, len(flat) - 2, 3)]
        s = cls(d.get("t", "pencil"), d.get("c", "#000000"), d.get("s", 1.0),
                d.get("o", 1.0), d.get("l", "lines"), pts, d.get("q"))
        s.extra = dict((k, v) for k, v in d.items() if k not in cls.KEYS)
        return s


class SheetData(object):
    """A drawing sheet: size, resolution, paper, layer settings, strokes."""

    def __init__(self, width=297.0, height=210.0, dpi=150, paper="transparent"):
        self.width = float(width)
        self.height = float(height)
        self.dpi = int(dpi)
        self.paper = paper
        self.layers = {k: {"opacity": 1.0, "visible": True} for k in LAYER_KEYS}
        self.strokes = []
        self.version = FORMAT_VERSION   # version read (kept when newer)
        self.extra = {}                 # unknown top-level keys, kept as is
        self.elements = []              # images, texts... (format v2)
        self.underlay = None            # guide capture settings (format v2) or None
        # image plane scale (3D mm per sheet mm): runtime copy of the sheet's
        # Scale property, not in the JSON
        self.plane_scale = self.plane_scale_read = 1.0
        self.files = {}                 # element file name -> local path (runtime)

    # --- size in pixels at the sheet resolution
    @property
    def scale(self):
        """Pixels per millimetre."""
        return self.dpi / 25.4

    def pixel_size(self):
        s = self.scale
        return max(1, int(round(self.width * s))), max(1, int(round(self.height * s)))

    def images(self):
        return [e for e in self.elements if e.kind == "image"]

    def new_id(self, prefix="img"):
        used = set(getattr(e, "id", None) for e in self.elements)
        n = 1
        while "%s%d" % (prefix, n) in used:
            n += 1
        return "%s%d" % (prefix, n)

    def layer_strokes(self, layer):
        """Strokes painted on a layer, in order, erasers working on it
        included."""
        return [s for s in self.strokes
                if s.layer == layer or (s.layer == ALL_LAYERS and layer in ERASABLE_LAYERS)]

    # --- serialization
    KEYS = ("version", "width", "height", "dpi", "paper", "layers", "strokes", "elements",
            "underlay")
    UNDERLAY_FILE = "UnderlayImage"     # file property holding the guide picture

    def to_dict(self):
        d = dict(self.extra)
        d.update({
            "version": max(FORMAT_VERSION, self.version),
            "width": self.width, "height": self.height,
            "dpi": self.dpi, "paper": self.paper,
            "layers": self.layers,
            "strokes": [s.to_dict() for s in self.strokes],
            "elements": [e.to_dict() for e in self.elements],
        })
        if self.underlay is not None:
            d["underlay"] = self.underlay
        return d

    def to_json(self):
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_json(cls, text):
        if not text:
            return cls()
        return cls.from_dict(json.loads(text))

    @classmethod
    def from_dict(cls, data):
        sheet = cls()
        d = migrate(data)
        sheet.version = d["version"]
        sheet.extra = dict((k, v) for k, v in d.items() if k not in cls.KEYS)
        sheet.width = float(d.get("width", sheet.width))
        sheet.height = float(d.get("height", sheet.height))
        sheet.dpi = int(d.get("dpi", sheet.dpi))
        sheet.paper = d.get("paper", sheet.paper)
        for k, v in d.get("layers", {}).items():
            # unknown layers (newer files) are kept but never drawn
            sheet.layers.setdefault(k, {}).update(v)
        sheet.strokes = [Stroke.from_dict(s) for s in d.get("strokes", [])]
        sheet.elements = [element_from_dict(e) for e in d.get("elements", [])]
        sheet.underlay = d.get("underlay")
        return sheet
