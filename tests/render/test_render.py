# SPDX-License-Identifier: LGPL-2.1-or-later
"""Rendering: the marker rule at pixel level, erasers, layers, paper,
millimetre-to-pixel mapping, reference images of every fixture sheet."""

import math
import os

import numpy as np
import pytest
import specs
from helpers import TESTS
from imaging import compare, load, to_array

from freecad.croquis import model
from freecad.croquis.render import compositor

pytestmark = pytest.mark.render

GOLDEN = os.path.join(TESTS, "expected", "render")
GOLDEN_DPI = 50


def stroke(tool, pts, layer=None, size=None, color=None, opacity=None, params=None):
    t = model.TOOLS[tool]
    return model.Stroke(tool, color or t["color"], size or t["size"],
                        t["opacity"] if opacity is None else opacity,
                        layer or t["layer"], pts, params)


def render(sheet, dpi=None, paper=True):
    return to_array(compositor.render_sheet(sheet, dpi, paper))


def px(sheet, x, y):
    s = sheet.scale
    return int(round(x * s)), int(round(y * s))


# ----------------------------------------------------------------------
#  Marker rule
# ----------------------------------------------------------------------
def figure_eight(cx, cy, r, n=200):
    return [(cx + r * math.sin(2 * math.pi * i / n), cy + 0.5 * r * math.sin(4 * math.pi * i / n),
             1.0) for i in range(n + 1)]


def test_marker_does_not_darken_itself():
    sheet = model.SheetData(100, 60, 150, "white")
    sheet.strokes = [stroke("marker", figure_eight(50, 30, 30), size=6, opacity=0.5)]
    arr = render(sheet)
    cross = arr[px(sheet, 50, 30)[1], px(sheet, 50, 30)[0]]
    single = arr[px(sheet, 80, 30)[1] - 0, px(sheet, 79.6, 30)[0]]
    # the crossing point equals a single-layer point of the same stroke
    assert np.abs(cross[:3].astype(int) - single[:3].astype(int)).max() <= 3, (cross, single)
    assert cross[0] < 250       # the stroke is there


def test_two_markers_darken_each_other():
    sheet = model.SheetData(100, 60, 150, "white")
    sheet.strokes = [
        stroke("marker", [(10, 30, 1), (90, 30, 1)], size=6, opacity=0.5),
        stroke("marker", [(50, 5, 1), (50, 55, 1)], size=6, opacity=0.5),
    ]
    arr = render(sheet)
    x, y = px(sheet, 50, 30)
    sx, sy = px(sheet, 20, 30)
    assert int(arr[y, x, 0]) < int(arr[sy, sx, 0]) - 15


# ----------------------------------------------------------------------
#  Erasers, layers, paper
# ----------------------------------------------------------------------
def band_sheet(paper="transparent"):
    sheet = model.SheetData(100, 40, 100, paper)
    sheet.strokes = [stroke("marker", [(10, 20, 1), (90, 20, 1)], size=8, opacity=0.8),
                     stroke("grease", [(10, 20, 1), (90, 20, 1)], size=2)]
    return sheet


def test_soft_eraser_removes_alpha():
    sheet = band_sheet()
    x, y = px(sheet, 50, 20)
    assert render(sheet)[y, x, 3] > 200
    sheet.strokes.append(stroke("eraser", [(50, 0, 1), (50, 40, 1)], size=6, opacity=1.0))
    assert render(sheet)[y, x, 3] == 0
    # still drawn away from the eraser
    x2, _ = px(sheet, 20, 20)
    assert render(sheet)[y, x2, 3] > 200


def test_eraser_on_one_layer_only():
    sheet = band_sheet()
    sheet.strokes.append(stroke("eraser", [(50, 0, 1), (50, 40, 1)], layer="marker", size=6))
    comp = compositor.Compositor(sheet)
    lines = to_array(comp.layers["lines"])
    marker = to_array(comp.layers["marker"])
    x, y = px(sheet, 50, 20)
    assert marker[y, x, 3] == 0 and lines[y, x, 3] > 200


def test_whole_stroke_removal():
    sheet = band_sheet()
    comp = compositor.Compositor(sheet)
    removed = sheet.strokes.pop(1)
    comp.remove_stroke(removed)
    assert comp.layers.get("lines") is None
    assert to_array(comp.image)[px(sheet, 50, 20)[1], px(sheet, 50, 20)[0], 3] > 0


def test_hidden_layer_and_opacity():
    sheet = band_sheet()
    x, y = px(sheet, 50, 20)
    sheet.layers["lines"]["visible"] = False
    sheet.layers["marker"]["visible"] = False
    assert render(sheet)[y, x, 3] == 0
    sheet.layers["marker"]["visible"] = True
    full = int(render(sheet)[y, x, 3])
    sheet.layers["marker"]["opacity"] = 0.5
    half = int(render(sheet)[y, x, 3])
    assert abs(half - full * 0.5) <= 3


def test_transparent_paper_png(tmp_path):
    sheet = band_sheet("transparent")
    path = str(tmp_path / "t.png")
    assert compositor.save_png(sheet, path)
    arr = to_array(load(path))
    assert arr[2, 2, 3] == 0 and arr[-3, -3, 3] == 0
    x, y = px(sheet, 50, 20)
    assert arr[y, x, 3] > 200
    sheet.paper = "kraft"
    assert compositor.save_png(sheet, path)
    arr = to_array(load(path))
    assert (arr[:, :, 3] == 255).all()
    assert tuple(arr[2, 2, :3]) == (0xc3, 0xa2, 0x7a)


def test_png_resolution_recorded(tmp_path):
    sheet = band_sheet()
    path = str(tmp_path / "r.png")
    compositor.save_png(sheet, path, dpi=200)
    img = load(path)
    assert abs(img.dotsPerMeterX() * 0.0254 - 200) < 1
    assert img.width() == round(100 * 200 / 25.4)


@pytest.mark.parametrize("dpi", specs.DPIS)
def test_mm_to_pixel(dpi):
    sheet = model.SheetData(100, 80, dpi, "transparent")
    sheet.strokes = [stroke("marker", [(37.0, 21.0, 1.0)], size=3, opacity=1.0)]
    arr = render(sheet)
    ys, xs = np.nonzero(arr[:, :, 3] > 128)
    cx, cy = xs.mean(), ys.mean()
    assert abs(cx - 37.0 * dpi / 25.4) <= 1.0 and abs(cy - 21.0 * dpi / 25.4) <= 1.0


def test_unknown_tool_not_drawn():
    sheet = model.SheetData(50, 50, 72, "transparent")
    s = stroke("pencil", [(10, 10, 1), (40, 40, 1)])
    s.tool = "laser"
    sheet.strokes = [s]
    assert render(sheet)[:, :, 3].max() == 0


# ----------------------------------------------------------------------
#  Reference images
# ----------------------------------------------------------------------
def spec_sheets():
    return [s for _doc, sheets in specs.documents().items() for s in sheets]


@pytest.mark.parametrize("spec", spec_sheets(), ids=[s["label"] for s in spec_sheets()])
def test_reference_image(spec, update_golden, artifacts_dir):
    sheet = model.SheetData.from_dict(spec["data"])
    img = compositor.render_sheet(sheet, dpi=GOLDEN_DPI)
    ok, msg = compare(img, os.path.join(GOLDEN, spec["label"] + ".png"), spec["label"],
                      artifacts_dir, update=update_golden)
    assert ok, msg
