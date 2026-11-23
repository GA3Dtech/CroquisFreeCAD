# SPDX-License-Identifier: LGPL-2.1-or-later
"""model.py: tables, JSON round trips, migration, tolerance to newer files."""

import json

import pytest
import specs
from conftest import legacy_json_files

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
    assert "underlay" not in model.ERASABLE_LAYERS
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
    assert sheet.version == 1
    assert sheet.strokes, "legacy sheets all have strokes"
    for s in sheet.strokes:
        assert s.kind in ("raster", "vector", "eraser")
    # writing back changes nothing but the separators
    assert json.loads(sheet.to_json()) == json.loads(text)


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
