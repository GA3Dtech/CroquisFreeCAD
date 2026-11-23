# SPDX-License-Identifier: LGPL-2.1-or-later
"""Content images (B1): placement, storage in the .FCStd, round trip,
reduction, rendering under the strokes, render flag, erasers, API."""

import os
import zipfile

import FreeCAD as App
import numpy as np
import pytest
from imaging import load, qt, to_array

from freecad.croquis import api, errors, images, sheet

pytestmark = pytest.mark.freecad


def picture(path, w, h, color=(200, 40, 40), noise=False):
    _c, QtGui = qt()
    if noise:
        rng = np.random.default_rng(1)
        arr = rng.integers(0, 255, (h, w, 4), dtype=np.uint8)
        arr[:, :, 3] = 255
        img = QtGui.QImage(arr.tobytes(), w, h, 4 * w, QtGui.QImage.Format_RGBA8888).copy()
    else:
        img = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
        img.fill(QtGui.QColor(*color))
    assert img.save(path)
    return path


@pytest.fixture
def sheet_info(doc):
    return api.create_sheet(doc, "A5L", 72, "white", "XZ", label="Img")


@pytest.mark.parametrize("size", [(1600, 900), (900, 1600), (1000, 1000)])
def test_default_placement(doc, sheet_info, tmp_path, size):
    path = picture(str(tmp_path / "p.png"), *size)
    e = api.add_image(sheet_info["name"], path, doc=doc)
    assert e["w"] / e["h"] == pytest.approx(size[0] / size[1], rel=1e-3)
    assert e["x"] == pytest.approx(210 - e["x"] - e["w"], abs=1e-2)
    assert e["y"] == pytest.approx(148 - e["y"] - e["h"], abs=1e-2)
    assert e["w"] <= 210 * 0.9 + 0.01 and e["h"] <= 148 * 0.9 + 0.01
    assert e["layer"] == "images" and e["render"] is True


def test_stored_in_fcstd_and_round_trip(doc, sheet_info, tmp_path, output_dir):
    path = picture(str(tmp_path / "p.png"), 800, 600, (30, 120, 220))
    e = api.add_image(sheet_info["name"], path, width_mm=100, x_mm=5, y_mm=7, doc=doc)
    assert (e["x"], e["y"], e["w"]) == (5, 7, 100) and e["h"] == pytest.approx(75)
    obj = doc.getObject(sheet_info["name"])
    prop = "Image_" + e["id"]
    assert hasattr(obj, prop)
    assert '"file":"%s"' % prop in obj.SheetData and "base64" not in obj.SheetData
    api.add_strokes(obj, [{"tool": "marker", "points": [[0, 40], [210, 40]], "size": 10,
                           "color": "#ffff00", "opacity": 1}], doc=doc)
    out = os.path.join(output_dir, "images.FCStd")
    doc.saveAs(out)
    with zipfile.ZipFile(out) as z:
        assert any(n.startswith(os.path.basename(getattr(obj, prop))) for n in z.namelist())
    App.closeDocument(doc.Name)
    d = App.openDocument(out)
    try:
        o = d.getObject(sheet_info["name"])
        imgs = api.list_images(o, doc=d)
        assert imgs[0]["id"] == e["id"] and imgs[0]["w"] == 100
        assert not load(getattr(o, prop)).isNull()
        # the image plane shows the picture, under the stroke
        arr = to_array(load(o.ImagePlane.ImageFile))
        px = lambda x, y: arr[int(y * 72 / 25.4), int(x * 72 / 25.4)]  # noqa: E731
        assert tuple(px(50, 60)[:3]) == (30, 120, 220)
        under = px(50, 40)                       # marker (multiply) over the blue picture
        assert under[2] < 60 and under[0] < 60   # yellow * blue: dark, not plain yellow
    finally:
        App.closeDocument(d.Name)


def test_reduced_by_default(doc, sheet_info, tmp_path):
    path = picture(str(tmp_path / "big.png"), 4000, 3000, noise=True)
    e = api.add_image(sheet_info["name"], path, doc=doc)
    max_w, max_h = images.useful_size(e["w"], e["h"], 72)
    assert e["source_px"][0] <= max_w and e["source_px"][1] <= max_h
    stored = getattr(doc.getObject(sheet_info["name"]), "Image_" + e["id"])
    assert os.path.getsize(stored) < os.path.getsize(path) / 4
    e2 = api.add_image(sheet_info["name"], path, keep_original=True, doc=doc)
    assert e2["source_px"] == [4000, 3000]


def test_render_flag_and_erasers(doc, sheet_info, tmp_path):
    path = picture(str(tmp_path / "p.png"), 400, 300, (0, 160, 0))
    e = api.add_image(sheet_info["name"], path, doc=doc)
    api.add_strokes(sheet_info["name"], [{"tool": "eraser", "points": [[105, 0], [105, 148]],
                                          "size": 30}], doc=doc)
    plane = doc.getObject(sheet_info["image_plane"])
    arr = to_array(load(plane.ImageFile))
    c = arr[int(74 * 72 / 25.4), int(105 * 72 / 25.4)]
    assert tuple(c[:3]) == (0, 160, 0)          # the eraser never erases pictures
    api.update_image_element(sheet_info["name"], e["id"], render=False, doc=doc)
    arr = to_array(load(plane.ImageFile))
    assert tuple(arr[int(74 * 72 / 25.4), int(105 * 72 / 25.4)][:3]) == (255, 255, 255)


def test_update_delete_and_undo(doc, sheet_info, tmp_path):
    path = picture(str(tmp_path / "p.png"), 400, 300)
    n = doc.UndoCount
    e = api.add_image(sheet_info["name"], path, doc=doc)
    assert doc.UndoCount == n + 1
    u = api.update_image_element(sheet_info["name"], e["id"], rotation=30, opacity=0.5,
                                 locked=True, doc=doc)
    assert (u["rotation"], u["opacity"], u["locked"]) == (30, 0.5, True)
    with pytest.raises(errors.InvalidArgumentError):
        api.update_image_element(sheet_info["name"], e["id"], colour="red", doc=doc)
    with pytest.raises(errors.InvalidArgumentError):
        api.update_image_element(sheet_info["name"], "nope", x=1, doc=doc)
    with pytest.raises(errors.InvalidArgumentError):
        api.add_image(sheet_info["name"], str(tmp_path / "missing.png"), doc=doc)
    api.delete_image_element(sheet_info["name"], e["id"], doc=doc)
    obj = doc.getObject(sheet_info["name"])
    assert api.list_images(obj, doc=doc) == [] and not hasattr(obj, "Image_" + e["id"])
    doc.undo()
    assert api.list_images(obj, doc=doc)[0]["id"] == e["id"]


def test_new_sheet_from_image(doc, tmp_path):
    path = picture(str(tmp_path / "p.png"), 1200, 800, (10, 10, 200))
    res = api.new_sheet_from_image(doc, path, plane="XY", dpi=72)
    s, e = res["sheet"], res["image"]
    assert s["format"] == "custom" and s["width_mm"] == 297 and s["height_mm"] == 198
    assert (e["x"], e["y"], e["w"], e["h"]) == (0, 0, 297, 198)
    arr = to_array(load(doc.getObject(s["image_plane"]).ImageFile))
    assert tuple(arr[10, 10][:3]) == (10, 10, 200)


def test_v1_sheet_written_as_v2(doc):
    obj = sheet.create_sheet(doc, "A5L", 72, "white", "XY", "Old")
    obj.SheetData = '{"version":1,"width":210,"height":148,"dpi":72,"paper":"white",' \
                    '"layers":{},"strokes":[]}'
    data = sheet.sheet_data(obj)
    assert data.version == 2 and data.elements == []
    sheet.store(obj, data)
    assert '"version":2' in obj.SheetData and '"elements":[]' in obj.SheetData
