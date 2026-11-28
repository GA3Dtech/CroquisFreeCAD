# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sketch on a face: a transparent sheet laid on a picked face of the
model, framed on it, facing out, board open."""

import FreeCAD as App
import FreeCADGui as Gui
import pytest
from conftest import process

from freecad.croquis import api, commands, sheet

pytestmark = pytest.mark.gui


@pytest.fixture
def box(doc):
    b = doc.addObject("Part::Box", "Box")
    b.Length, b.Width, b.Height = 100, 60, 40
    doc.recompute()
    yield b
    commands._picker.stop()
    sheet.close_all_boards()


def _sheets(doc):
    return [o for o in doc.Objects if sheet.is_sheet(o)]


def _check_on_top_face(obj):
    img = obj.ImagePlane
    n = img.Placement.Rotation.multVec(App.Vector(0, 0, 1))
    assert (n - App.Vector(0, 0, 1)).Length < 1e-6
    assert img.Placement.Base.z == pytest.approx(40, abs=0.5) and img.Placement.Base.z > 40
    assert img.XSize.Value > 100 and img.YSize.Value > 60 and img.XSize.Value < 130
    assert obj.Paper == "transparent"


def test_selected_face(doc, box):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, box.Name, "Face6", 50, 30, 40)
    commands.sheet_on_face()
    process()
    (obj,) = _sheets(doc)
    _check_on_top_face(obj)
    assert sheet.board_of(obj) is not None
    info = api.get_sheet(obj.Name, doc=doc)
    assert info["paper"] == "transparent"
    assert info["underlay"]["style"] == "shaded"     # the face under the strokes


def test_face_guide_preference(doc, box):
    from freecad.croquis import prefs
    prefs.put("FaceGuide", "none")
    try:
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, box.Name, "Face6", 50, 30, 40)
        commands.sheet_on_face()
        process()
        (obj,) = _sheets(doc)
        assert api.get_sheet(obj.Name, doc=doc)["underlay"] is None
    finally:
        prefs.put("FaceGuide", "shaded")


def test_pick_mode(doc, box):
    Gui.Selection.clearSelection()
    commands.sheet_on_face()                    # nothing selected: waits for a face
    assert commands._picker.active and not _sheets(doc)
    Gui.Selection.addSelection(doc.Name, box.Name, "Edge1")    # not a face: ignored
    process()
    assert commands._picker.active and not _sheets(doc)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, box.Name, "Face6", 20, 10, 40)
    process()
    assert not commands._picker.active
    (obj,) = _sheets(doc)
    _check_on_top_face(obj)
    commands.sheet_on_face()                    # again, then again: cancelled
    commands.sheet_on_face()
    assert not commands._picker.active
