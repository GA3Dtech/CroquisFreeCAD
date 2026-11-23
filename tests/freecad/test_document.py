# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sheets in a FreeCAD document: creation, image plane, PNG inside the
.FCStd, save / reopen, undo, export, legacy files."""

import json
import os
import zipfile

import FreeCAD as App
import pytest
from helpers import legacy_fcstd_files
from imaging import compare, load, qt, to_array

from freecad.croquis import model, sheet

pytestmark = pytest.mark.freecad


def strokes_for(w, h):
    t = model.TOOLS
    return [
        model.Stroke("marker", t["marker"]["color"], 8, 0.6, "marker",
                     [(w * 0.1, h * 0.5, 1.0), (w * 0.9, h * 0.5, 1.0)]),
        model.Stroke("pencil", "#202020", 0.5, 0.9, "construction",
                     [(w * 0.1, h * 0.2, 0.5), (w * 0.9, h * 0.3, 1.0)]),
    ]


def png_in_zip(path, name):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert name in names, names
        return z.read(name)


@pytest.mark.parametrize("plane", sheet.PLANES)
def test_create_sheet(doc, plane):
    obj = sheet.create_sheet(doc, "A5L", 100, "white", plane, "S")
    doc.recompute()
    assert sheet.is_sheet(obj) and obj.Proxy.Type == "Croquis::Sheet"
    img = obj.ImagePlane
    assert img.TypeId == "Image::ImagePlane"
    assert img.XSize.Value == pytest.approx(210) and img.YSize.Value == pytest.approx(148)
    assert obj.SheetWidth.Value == 210 and obj.SheetHeight.Value == 148
    rot = img.Placement.Rotation
    # image X and image up (Y) in the document
    ix, iy = rot.multVec(App.Vector(1, 0, 0)), rot.multVec(App.Vector(0, 1, 0))
    expected = {"XY": ((1, 0, 0), (0, 1, 0)), "XZ": ((1, 0, 0), (0, 0, 1)),
                "YZ": ((0, 1, 0), (0, 0, 1))}[plane]
    for v, e in ((ix, expected[0]), (iy, expected[1])):
        assert (v - App.Vector(*e)).Length < 1e-9
    assert os.path.isfile(img.ImageFile)


def test_store_regenerates_png(doc, tmp_path):
    obj = sheet.create_sheet(doc, "A5L", 100, "transparent", "XZ", "S")
    before = to_array(load(obj.ImagePlane.ImageFile))
    assert before[:, :, 3].max() == 0
    data = sheet.sheet_data(obj)
    data.strokes = strokes_for(210, 148)
    sheet.store(obj, data)
    after = to_array(load(obj.ImagePlane.ImageFile))
    assert after[:, :, 3].max() > 200
    assert after.shape[:2] == (round(148 * 100 / 25.4), round(210 * 100 / 25.4))
    path = str(tmp_path / "s.FCStd")
    doc.saveAs(path)
    blob = png_in_zip(path, os.path.basename(obj.ImagePlane.ImageFile))
    _core, QtGui = qt()
    img = QtGui.QImage.fromData(blob)
    assert to_array(img)[:, :, 3].max() > 200


def test_save_close_reopen(doc, output_dir):
    obj = sheet.create_sheet(doc, "A4P", 72, "kraft", "YZ", "Round trip")
    data = sheet.sheet_data(obj)
    data.strokes = strokes_for(210, 297)
    data.layers["marker"]["opacity"] = 0.5
    sheet.store(obj, data)
    doc.recompute()
    path = os.path.join(output_dir, "round_trip.FCStd")
    text, placement = obj.SheetData, obj.ImagePlane.Placement
    sizes = (obj.ImagePlane.XSize.Value, obj.ImagePlane.YSize.Value)
    pixels = to_array(load(obj.ImagePlane.ImageFile))
    doc.saveAs(path)
    App.closeDocument(doc.Name)
    d = App.openDocument(path)
    try:
        o = d.getObject("Croquis")
        assert sheet.is_sheet(o)
        assert json.loads(o.SheetData) == json.loads(text)
        assert o.Paper == "kraft" and o.Resolution == 72
        assert o.ImagePlane.Placement.isSame(placement, 1e-9)
        assert (o.ImagePlane.XSize.Value, o.ImagePlane.YSize.Value) == sizes
        assert (to_array(load(o.ImagePlane.ImageFile)) == pixels).all()
    finally:
        App.closeDocument(d.Name)


def test_one_undo_step_per_action(doc):
    doc.openTransaction("create")
    obj = sheet.create_sheet(doc, "A5L", 72, "white", "XY", "U")
    doc.commitTransaction()
    n = doc.UndoCount
    data = sheet.sheet_data(obj)
    data.strokes = strokes_for(210, 148)
    sheet.store(obj, data)
    assert doc.UndoCount == n + 1
    data.strokes = data.strokes[:1]
    sheet.store(obj, data)
    assert doc.UndoCount == n + 2
    doc.undo()
    assert len(sheet.sheet_data(obj).strokes) == 2
    doc.undo()
    assert sheet.sheet_data(obj).strokes == []


def test_export_png(doc, tmp_path):
    from freecad.croquis.render import compositor
    obj = sheet.create_sheet(doc, "A5L", 100, "transparent", "XY", "E")
    data = sheet.sheet_data(obj)
    data.strokes = strokes_for(210, 148)
    path = str(tmp_path / "e.png")
    assert compositor.save_png(data, path)
    arr = to_array(load(path))
    assert arr[0, 0, 3] == 0 and arr[:, :, 3].max() > 200


# ----------------------------------------------------------------------
#  Legacy files
# ----------------------------------------------------------------------
@pytest.mark.parametrize("path", legacy_fcstd_files(), ids=lambda p: p.split("legacy/")[-1])
def test_legacy_file(path, tmp_path, artifacts_dir):
    import shutil
    copy = str(tmp_path / os.path.basename(path))
    shutil.copy(path, copy)     # never touch the frozen file
    d = App.openDocument(copy)
    try:
        sheets = [o for o in d.Objects if sheet.is_sheet(o)]
        assert sheets
        for o in sheets:
            stored = load(o.ImagePlane.ImageFile)       # rendered by v0.2.0
            data = sheet.sheet_data(o)
            assert data.version == model.FORMAT_VERSION and data.strokes
            sheet.update_image(o, data)                 # regenerate today
            again = load(o.ImagePlane.ImageFile)
            ref = str(tmp_path / ("ref_%s.png" % o.Name))
            stored.save(ref, "PNG")
            name = "legacy_%s_%s" % (os.path.basename(path)[:-6], o.Label)
            ok, msg = compare(again, ref, name, artifacts_dir)
            assert ok, "%s: %s" % (o.Label, msg)
        assert d.recompute() >= 0
    finally:
        App.closeDocument(d.Name)
