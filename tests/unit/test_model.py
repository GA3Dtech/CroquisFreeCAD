# SPDX-License-Identifier: LGPL-2.1-or-later
"""model.py: tables, JSON round trips, migration, tolerance to newer files."""

import json

import pytest
import specs
from helpers import legacy_json_files

from freecad.croquis import model

pytestmark = pytest.mark.unit


def all_spec_sheets():
    return [(doc, s) for doc, sheets in specs.documents().items() for s in sheets]


# ----------------------------------------------------------------------
#  Tables
# ----------------------------------------------------------------------
def test_tool_layers_exist():
    for key, t in model.TOOLS.items():
        if t["kind"] == "eraser":
            assert t["layer"] == model.ALL_LAYERS
        else:
            assert t["layer"] in model.LAYER_KEYS, key


def test_tool_keys_and_kinds():
    assert set(model.TOOL_KEYS) == set(model.TOOLS)
    for key in model.TOOL_KEYS:
        assert model.tool_kind(key) in ("raster", "vector", "eraser")
        for field in ("label", "color", "size", "opacity", "pressure_width",
                      "pressure_alpha", "grain"):
            assert field in model.TOOLS[key], (key, field)
    assert model.tool_kind("no-such-tool") == "unknown"


def test_layers_and_erasable():
    assert set(model.ERASABLE_LAYERS) <= set(model.LAYER_KEYS)
    assert "underlay" not in model.ERASABLE_LAYERS and "images" not in model.ERASABLE_LAYERS
    assert model.LAYER_KEYS[:3] == ["underlay", "images", "construction"]
    blends = set(b for _k, _l, b in model.LAYERS)
    assert blends <= {"normal", "multiply"}


def test_formats_and_papers():
    keys = [k for k, _l, _w, _h in model.FORMATS]
    assert len(keys) == len(set(keys))
    for k, _label, w, h in model.FORMATS:
        assert model.format_size(k) == (w, h) and w > 0 and h > 0
    assert model.format_size("nope") == (297.0, 210.0)
    for k, _label, color in model.PAPERS:
        assert model.paper_color(k) == color
        assert color is None or (color.startswith("#") and len(color) == 7)


def test_eraser_targets():
    all_ = model.Stroke("eraser", "#000000", 5, 1, "*", [(0, 0, 1)])
    one = model.Stroke("eraser", "#000000", 5, 1, "marker", [(0, 0, 1)])
    assert model.eraser_targets(all_) == model.ERASABLE_LAYERS
    assert model.eraser_targets(one) == ["marker"]
    sheet = model.SheetData()
    pen = model.Stroke("pencil", "#000000", 1, 1, "construction", [(0, 0, 1)])
    sheet.strokes = [pen, all_, one]
    assert sheet.layer_strokes("construction") == [pen, all_]
    assert sheet.layer_strokes("marker") == [all_, one]
    assert sheet.layer_strokes("underlay") == []


# ----------------------------------------------------------------------
#  JSON
# ----------------------------------------------------------------------
@pytest.mark.parametrize("doc,spec", all_spec_sheets(),
                         ids=[s["label"] for _d, s in all_spec_sheets()])
def test_round_trip_specs(doc, spec):
    sheet = model.SheetData.from_dict(spec["data"])
    again = model.SheetData.from_json(sheet.to_json())
    assert json.loads(again.to_json()) == json.loads(sheet.to_json())
    assert len(again.strokes) == len(spec["data"]["strokes"])
    assert again.width == spec["data"]["width"] and again.dpi == spec["dpi"]


@pytest.mark.parametrize("path", legacy_json_files(),
                         ids=lambda p: p.split("legacy/")[-1])
def test_legacy_json(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    sheet = model.SheetData.from_json(text)
    assert sheet.version == model.FORMAT_VERSION       # migrated on read
    assert sheet.strokes, "legacy sheets all have strokes"
    for s in sheet.strokes:
        assert s.kind in ("raster", "vector", "eraser")
    # writing back changes nothing but what the migrations add
    old, new = json.loads(text), json.loads(sheet.to_json())
    assert new["strokes"] == old["strokes"]
    for k in ("width", "height", "dpi", "paper"):
        assert new[k] == old[k]
    for k, v in old["layers"].items():
        assert new["layers"][k] == v
    assert new["elements"] == [] and new["layers"]["images"] == {"opacity": 1.0,
                                                                 "visible": True}


def test_stroke_params_and_profile():
    s = model.Stroke("spline", "#000000", 1, 1, "lines", [(0, 0, 1)] * 4, {"peak": 0.3})
    d = s.to_dict()
    assert d["q"] == {"peak": 0.3}
    back = model.Stroke.from_dict(d)
    assert back.profile() == {"peak": 0.3, "tin": 1.0, "tout": 1.0}
    assert "q" not in model.Stroke("pencil", "#000000", 1, 1, "construction").to_dict()


def test_empty_and_degenerate():
    assert model.SheetData.from_json("").strokes == []
    s = model.Stroke.from_dict({"p": [1, 2]})      # incomplete triple dropped
    assert s.points == [] and s.bounds() is None
    s = model.Stroke.from_dict({"p": [1, 2, 0.5]})
    assert s.bounds() == (0.0, 1.0, 2.0, 3.0)


# ----------------------------------------------------------------------
#  Migration and newer files
# ----------------------------------------------------------------------
def test_migrate_v1_to_v2():
    v1 = {"version": 1, "width": 10, "height": 20, "dpi": 72, "paper": "white",
          "layers": {"lines": {"opacity": 0.5, "visible": False}},
          "strokes": [{"t": "pencil", "c": "#000000", "s": 1, "o": 1, "l": "construction",
                       "p": [1, 2, 1]}]}
    v2 = model.migrate(v1)
    assert v2["version"] == 2 and v2["elements"] == []
    assert v2["layers"]["lines"] == {"opacity": 0.5, "visible": False}
    assert v2["layers"]["images"] == {"opacity": 1.0, "visible": True}
    assert v2["strokes"] == v1["strokes"]
    assert model.migrate(v2) == v2                      # idempotent


def test_v2_round_trip_with_elements():
    sheet = model.SheetData(100, 50, 72, "white")
    img = model.ImageElement("img1", "Image_img1", 10, 5, 40, 30, rotation=15, opacity=0.8,
                             camera={"type": "ortho"}, source_px=[400, 300])
    sheet.elements = [img, model.UnknownElement({"kind": "hologram", "z": 1})]
    again = model.SheetData.from_json(sheet.to_json())
    assert again.version == 2
    e = again.elements[0]
    assert (e.kind, e.id, e.file, e.x, e.w, e.rotation, e.opacity, e.camera, e.source_px) == \
        ("image", "img1", "Image_img1", 10, 40, 15, 0.8, {"type": "ortho"}, [400, 300])
    assert again.elements[1].to_dict() == {"kind": "hologram", "z": 1}
    assert sheet.new_id() == "img2"
    assert [x.id for x in again.images()] == ["img1"]


def test_image_element_geometry():
    e = model.ImageElement("i", "f", 10, 10, 40, 20)
    assert e.bounds() == (10, 10, 50, 30)
    assert e.contains(30, 20) and not e.contains(5, 20)
    e.rotation = 90
    b = e.bounds()
    assert b == pytest.approx((20, 0, 40, 40))
    assert e.contains(30, 2) and not e.contains(12, 20)


@pytest.mark.parametrize("img", [(1600, 900), (900, 1600), (1000, 1000)])
@pytest.mark.parametrize("fmt", [f[0] for f in model.FORMATS])
def test_fit_rect(img, fmt):
    aw, ah = model.format_size(fmt)
    x, y, w, h = model.fit_rect(img[0], img[1], aw, ah)
    assert w / h == pytest.approx(img[0] / img[1])           # proportions kept
    assert x == pytest.approx(aw - x - w) and y == pytest.approx(ah - y - h)   # centred
    assert w <= aw * 0.9 + 1e-9 and h <= ah * 0.9 + 1e-9
    assert w == pytest.approx(aw * 0.9) or h == pytest.approx(ah * 0.9)       # fills one side
    x, y, w, h = model.fit_rect(img[0], img[1], aw, ah, margin=0)
    assert w == pytest.approx(aw) or h == pytest.approx(ah)
    with pytest.raises(ValueError):
        model.fit_rect(0, 10, aw, ah)


def test_migrate_without_version():
    d = model.migrate({"width": 10, "height": 20})
    assert d["version"] == model.FORMAT_VERSION
    sheet = model.SheetData.from_dict({"width": 10, "height": 20, "strokes": []})
    assert sheet.version == model.FORMAT_VERSION and sheet.width == 10


def test_migrate_is_a_copy():
    src = {"version": 1, "strokes": []}
    model.migrate(src)
    assert src == {"version": 1, "strokes": []}


def test_every_migration_step_is_registered():
    for v in range(1, model.FORMAT_VERSION):
        assert v in model.MIGRATIONS


def test_newer_file_is_kept_intact():
    newer = {
        "version": model.FORMAT_VERSION + 5,
        "width": 100, "height": 50, "dpi": 72, "paper": "white",
        "layers": {"lines": {"opacity": 0.5, "visible": True},
                   "future": {"opacity": 1.0, "visible": True}},
        "elements": [{"kind": "hologram", "x": 1}],
        "strokes": [
            {"t": "pencil", "c": "#111111", "s": 1, "o": 1, "l": "construction",
             "p": [1, 2, 0.5], "z": "unknown stroke field"},
            {"t": "laser", "c": "#ff0000", "s": 2, "o": 1, "l": "future", "p": [3, 4, 1]},
        ],
    }
    sheet = model.SheetData.from_dict(newer)
    assert sheet.version == newer["version"]
    assert sheet.strokes[1].kind == "unknown"
    out = json.loads(sheet.to_json())
    assert out["version"] == newer["version"]
    assert out["elements"] == newer["elements"]
    assert out["layers"]["future"] == newer["layers"]["future"]
    assert out["strokes"][0]["z"] == "unknown stroke field"
    assert out["strokes"][1]["t"] == "laser"


def test_scale_and_pixel_size():
    for dpi in specs.DPIS:
        sheet = model.SheetData(210, 148, dpi)
        assert sheet.scale == pytest.approx(dpi / 25.4)
        w, h = sheet.pixel_size()
        assert w == round(210 * dpi / 25.4) and h == round(148 * dpi / 25.4)


def test_palettes():
    pals = model.load_palettes()
    assert [n for n, _c in pals][:3] == ["Cool greys", "Warm greys", "Neutral greys"]
    for _name, colors in pals:
        for _label, c in colors:
            assert c.startswith("#") and len(c) == 7


def test_arrow_stroke_params_and_bounds():
    s = model.Stroke("arrow", "#000000", 1.0, 1, "lines",
                     [(0, 0, 1), (3, 0, 1), (6, 0, 1), (10, 0, 1)],
                     {"head_start": True, "head_style": "filled"})
    prof = s.profile()
    assert prof["head_start"] and prof["head_end"] and prof["head_style"] == "filled"
    assert prof["tin"] == 0.0                    # arrows: constant width by default
    head = model.arrow_head_size(1.0, 0)
    assert s.bounds()[2] == pytest.approx(10 + 1.0 + head)
    again = model.Stroke.from_dict(s.to_dict())
    assert again.profile() == prof


def test_text_element():
    e = model.TextElement("t1", "Hello\nworld", 10, 20, w=40, h=12, size=5, frame=True,
                          leader=[0, 60], bold=True)
    assert e.pad == pytest.approx(1.75)
    assert e.box() == pytest.approx((8.25, 18.25, 51.75, 33.75))
    assert e.contains(30, 25) and not e.contains(60, 25)
    b = e.bounds()
    assert b[0] <= -5 and b[3] >= 65                      # callout target included
    assert e.leader_start() == pytest.approx((30.0, 33.75))   # bottom side faces the target
    nowrap = model.TextElement("t2", "x", 0, 0, w=0)
    nowrap.aw, nowrap.h = 25, 5
    assert nowrap.width == 25 and nowrap.box()[2] == 25
    again = model.element_from_dict(e.to_dict())
    assert again.to_dict() == e.to_dict() and again.kind == "text"
    sheet = model.SheetData()
    sheet.elements = [e]
    assert model.SheetData.from_json(sheet.to_json()).texts()[0].text == "Hello\nworld"


def test_grey_families_visibly_different():
    pals = dict(model.load_palettes())

    def rgb(c):
        return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    for (_lc, c), (_lw, w), (_ln, n) in zip(pals["Cool greys"], pals["Warm greys"],
                                            pals["Neutral greys"]):
        cr, cg, cb = rgb(c)
        wr, wg, wb = rgb(w)
        nr, ng, nb = rgb(n)
        assert nr == ng == nb                                  # neutral: no tint
        assert cb - cr >= 10 and wr - wb >= 10                 # cool blue, warm yellow
        assert abs((cr + cg + cb) / 3 - nr) < 12               # same lightness family
    for name in ("Cool greys", "Warm greys", "Neutral greys"):
        assert name in model.PALETTE_TIPS
