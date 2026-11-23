# SPDX-License-Identifier: LGPL-2.1-or-later
"""Public API (api.py): every function, input validation, JSON results,
one undo step per call."""

import json
import os

import FreeCAD as App
import pytest
from imaging import load, to_array

from freecad.croquis import api, errors

pytestmark = pytest.mark.freecad

ALL_TOOLS = [
    {"tool": "pencil", "points": [[10, 10, 0.5], [100, 20]]},
    {"tool": "grease", "points": [[10, 30, 1], [100, 40, 0.2]], "size": 1.5},
    {"tool": "marker", "points": [[10, 60], [190, 60]], "color": "#868B91", "opacity": 0.5},
    {"tool": "highlight", "points": [[20, 58], [120, 58]]},
    {"tool": "line", "points": [[20, 130], [180, 100]], "profile": {"tin": 0.0}},
    {"tool": "spline", "points": [[20, 110], [80, 90], [180, 120]], "size": 2},
    {"tool": "spline", "bezier": [[10, 140], [50, 120], [90, 140], [130, 120]]},
    {"tool": "eraser", "points": [[60, 0], [60, 148]], "size": 4},
    {"tool": "eraser", "points": [[150, 0], [150, 148]], "layer": "marker"},
]


@pytest.fixture
def sheet(doc):
    return api.create_sheet(doc, format="A5L", dpi=72, paper="white", plane="XZ", label="Api")


def test_describe_covers_everything():
    d = api.describe()
    json.dumps(d)
    assert d["api_version"] == api.API_VERSION
    assert set(d["functions"]) == set(api.PUBLIC)
    for name in api.PUBLIC:
        assert callable(getattr(api, name))
        assert d["functions"][name]["summary"]
    assert set(d["tools"]) == set(api.model.TOOLS)


def test_create_list_get(doc, sheet):
    json.dumps(sheet)
    assert sheet["format"] == "A5L" and sheet["plane"] == "XZ" and sheet["dpi"] == 72
    assert sheet["width_mm"] == 210 and sheet["strokes"] == 0
    sheets = api.list_sheets(doc)
    assert [s["name"] for s in sheets] == [sheet["name"]]
    for ref in (sheet["name"], "Api", sheet["image_plane"]):
        assert api.get_sheet(ref, doc=doc)["name"] == sheet["name"]
    assert api.get_sheet(sheet["name"], doc=doc.Name)["label"] == "Api"
    placed = api.create_sheet(doc, "SQ", 72, "kraft", "XY",
                              placement=App.Placement(App.Vector(5, 0, 0), App.Rotation()))
    assert placed["plane"] == "XY"
    assert doc.getObject(placed["image_plane"]).Placement.Base.x == 5


def test_add_and_list_every_tool(doc, sheet):
    res = api.add_strokes(sheet["name"], ALL_TOOLS, doc=doc)
    json.dumps(res)
    assert res["indices"] == list(range(len(ALL_TOOLS)))
    listed = api.list_strokes(sheet["name"], doc=doc)
    json.dumps(listed)
    assert [s["tool"] for s in listed] == [s["tool"] for s in ALL_TOOLS]
    assert listed[0]["points"][1] == [100.0, 20.0, 1.0]
    assert listed[2]["color"] == "#868b91" and listed[2]["layer"] == "marker"
    assert len(listed[4]["bezier"]) == 4 and listed[4]["profile"]["tin"] == 0.0
    assert len(listed[5]["bezier"]) == 7
    assert listed[7]["layer"] == "*"
    assert [s["index"] for s in api.list_strokes(sheet["name"], "marker", doc=doc)] == [2, 8]
    img = load(doc.getObject(sheet["image_plane"]).ImageFile)
    assert to_array(img)[:, :, :3].min() < 100       # strokes rendered


@pytest.mark.parametrize("bad", [
    "not a dict",
    {"tool": "brush", "points": [[0, 0]]},
    {"tool": "pencil"},
    {"tool": "pencil", "points": []},
    {"tool": "pencil", "points": [[0]]},
    {"tool": "pencil", "points": [[0, 0, 2]]},
    {"tool": "pencil", "points": [["a", 0]]},
    {"tool": "pencil", "points": [[0, 0]], "color": "red"},
    {"tool": "pencil", "points": [[0, 0]], "size": 0},
    {"tool": "pencil", "points": [[0, 0]], "opacity": 1.5},
    {"tool": "pencil", "points": [[0, 0]], "layer": "underlay"},
    {"tool": "pencil", "points": [[0, 0]], "layer": "*"},
    {"tool": "pencil", "points": [[0, 0]], "speed": 3},
    {"tool": "pencil", "points": [[0, 0]], "profile": {"peak": 0.5}},
    {"tool": "eraser", "points": [[0, 0]], "layer": "underlay"},
    {"tool": "line", "points": [[0, 0], [1, 1], [2, 2]]},
    {"tool": "spline", "points": [[0, 0]]},
    {"tool": "spline", "bezier": [[0, 0], [1, 1], [2, 2]]},
    {"tool": "spline", "points": [[0, 0], [1, 1]], "bezier": [[0, 0]] * 4},
    {"tool": "spline", "points": [[0, 0], [1, 1]], "profile": {"peak": 2}},
    {"tool": "spline", "points": [[0, 0], [1, 1]], "profile": {"width": 1}},
])
def test_invalid_strokes(doc, sheet, bad):
    with pytest.raises(errors.InvalidStrokeError):
        api.add_strokes(sheet["name"], [ALL_TOOLS[0], bad], doc=doc)
    assert api.get_sheet(sheet["name"], doc=doc)["strokes"] == 0     # nothing added


def test_invalid_arguments(doc, sheet):
    n = sheet["name"]
    with pytest.raises(errors.NoDocumentError):
        api.list_sheets("no such document")
    with pytest.raises(errors.SheetNotFoundError):
        api.get_sheet("Nothing", doc=doc)
    box = doc.addObject("App::FeaturePython", "NotASheet")
    with pytest.raises(errors.SheetNotFoundError):
        api.get_sheet(box.Name, doc=doc)
    for kw in ({"format": "A9"}, {"dpi": 5}, {"dpi": 150.0}, {"paper": "gold"},
               {"plane": "XYZ"}, {"placement": "here"}):
        with pytest.raises(errors.InvalidArgumentError):
            api.create_sheet(doc, **kw)
    with pytest.raises(errors.InvalidArgumentError):
        api.set_layer(n, "nope", visible=True, doc=doc)
    with pytest.raises(errors.InvalidArgumentError):
        api.set_layer(n, "marker", opacity=3, doc=doc)
    with pytest.raises(errors.InvalidArgumentError):
        api.set_paper(n, "gold", doc=doc)
    with pytest.raises(errors.InvalidArgumentError):
        api.delete_strokes(n, [0], doc=doc)
    with pytest.raises(errors.InvalidStrokeError):
        api.add_strokes(n, [], doc=doc)
    assert issubclass(errors.InvalidArgumentError, ValueError)
    for cls in (errors.NoDocumentError, errors.SheetNotFoundError, errors.InvalidStrokeError,
                errors.InvalidArgumentError, errors.GuiRequiredError):
        assert issubclass(cls, errors.CroquisError)


def test_layers_paper_delete_regenerate(doc, sheet):
    n = sheet["name"]
    api.add_strokes(n, ALL_TOOLS[:3], doc=doc)
    info = api.set_layer(n, "marker", visible=False, opacity=0.3, doc=doc)
    lay = dict((x["key"], x) for x in info["layers"])
    assert lay["marker"] == {"key": "marker", "label": "Marker", "blend": "multiply",
                             "visible": False, "opacity": 0.3, "erasable": True}
    assert api.set_paper(n, "grey", doc=doc)["paper"] == "grey"
    assert doc.getObject(n).Paper == "grey"
    info = api.delete_strokes(n, [0, 2], doc=doc)
    assert info["strokes"] == 1
    assert api.list_strokes(n, doc=doc)[0]["tool"] == "grease"
    assert api.regenerate(n, doc=doc)["strokes"] == 1


def test_one_undo_step_per_call(doc, sheet):
    n = sheet["name"]
    count = doc.UndoCount
    api.add_strokes(n, ALL_TOOLS[:2], doc=doc)
    api.set_paper(n, "kraft", doc=doc)
    api.set_layer(n, "lines", opacity=0.5, doc=doc)
    api.delete_strokes(n, [0], doc=doc)
    assert doc.UndoCount == count + 4
    doc.undo()
    assert api.get_sheet(n, doc=doc)["strokes"] == 2
    doc.undo()
    doc.undo()
    assert api.get_sheet(n, doc=doc)["paper"] == "white"
    doc.undo()
    assert api.get_sheet(n, doc=doc)["strokes"] == 0


def test_render_and_export(doc, sheet, tmp_path):
    n = sheet["name"]
    api.add_strokes(n, ALL_TOOLS[:3], doc=doc)
    count = doc.UndoCount
    tmp = api.render_png(n, doc=doc)
    try:
        assert os.path.isfile(tmp) and load(tmp).width() == round(210 * 72 / 25.4)
    finally:
        os.remove(tmp)
    path = api.export_png(n, str(tmp_path / "x.png"), dpi=50, doc=doc)
    assert load(path).width() == round(210 * 50 / 25.4)
    assert doc.UndoCount == count       # rendering changes nothing
    with pytest.raises(errors.InvalidArgumentError):
        api.export_png(n, "", doc=doc)


def test_api_file_for_vanilla(doc, sheet, output_dir):
    """A file built only through the API, reopened by the vanilla tests."""
    api.add_strokes(sheet["name"], ALL_TOOLS, doc=doc)
    api.set_layer(sheet["name"], "marker", opacity=0.6, doc=doc)
    doc.saveAs(os.path.join(output_dir, "api_sheet.FCStd"))


def test_active_document_default(doc, sheet):
    App.setActiveDocument(doc.Name)
    assert api.list_sheets()[0]["name"] == sheet["name"]


def test_gui_functions_refuse_headless(doc, sheet):
    if App.GuiUp:
        pytest.skip("headless check")
    with pytest.raises(errors.GuiRequiredError):
        api.capture_3d_view(doc)
    with pytest.raises(errors.GuiRequiredError):
        api.restore_image_view(sheet["name"], "img1", doc=doc)
    assert api.describe()["functions"]["capture_3d_view"]["gui"] is True
