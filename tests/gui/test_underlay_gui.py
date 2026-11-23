# SPDX-License-Identifier: LGPL-2.1-or-later
"""3D view guide aligned on the sheet plane (B3): true size, exact
framing, round trip sheet <-> 3D, kept out of the image plane."""

import FreeCAD as App
import FreeCADGui as Gui
import numpy as np
import pytest
from conftest import process
from imaging import load, to_array

from freecad.croquis import api, capture, model, sheet

pytestmark = pytest.mark.gui

W, H, DPI = 297.0, 210.0, 100
# plane -> (box base, function giving the plane coordinates (u, v) of a 3D point)
CASES = {
    "XY": ((30, 10, 5), lambda p: (p[0], p[1])),
    "XZ": ((30, 5, 10), lambda p: (p[0], p[2])),
    "YZ": ((5, 30, 10), lambda p: (p[1], p[2])),
}


def camera_core(text):
    """Numbers of the camera text without the clipping planes FreeCAD
    recomputes itself, rounded (the text round trip is not exact)."""
    import re
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith(("nearDistance", "farDistance")):
            out += [round(float(v), 4) for v in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", ln)]
    return out


def guide_array(doc, info):
    obj = doc.getObject(info["name"])
    return to_array(load(getattr(obj, model.SheetData.UNDERLAY_FILE)))


@pytest.mark.parametrize("plane", list(CASES))
def test_guide_alignment_round_trip(doc, plane):
    base, uv = CASES[plane]
    box = doc.addObject("Part::Box", "Box")
    box.Length = box.Width = box.Height = 20
    box.Placement.Base = App.Vector(*base)
    doc.recompute()
    Gui.setActiveDocument(doc.Name)
    view = capture.view_3d(doc)
    view.viewIsometric()
    before = view.getCamera()
    info = api.create_sheet(doc, "A4L", DPI, "white", plane)
    res = api.capture_underlay(info["name"], style="edges", doc=doc)
    assert res["underlay"]["mode"] == "plane"
    assert camera_core(view.getCamera()) == camera_core(before)    # user camera restored
    arr = guide_array(doc, info)
    s = DPI / 25.4
    assert arr.shape[:2] == (round(H * s), round(W * s))    # sheet proportions
    dark = arr[:, :, 0] < 110
    ys, xs = np.nonzero(dark)
    assert len(xs) > 100, "no edge captured"
    # the box footprint covers u in [30, 50], v in [10, 30] on the plane
    u0, v0 = uv(base)
    exp = {"x0": (W / 2 + u0) * s, "x1": (W / 2 + u0 + 20) * s,
           "y0": (H / 2 - v0 - 20) * s, "y1": (H / 2 - v0) * s}
    got = {"x0": xs.min(), "x1": xs.max(), "y0": ys.min(), "y1": ys.max()}
    for k in exp:
        assert abs(got[k] - exp[k]) <= 3, (plane, k, got[k], exp[k])
    # back to 3D through the image plane placement: the corner of the box
    plc = doc.getObject(info["image_plane"]).Placement
    sx, sy = got["x0"] / s, got["y1"] / s                   # sheet mm of the corner
    p3 = plc.multVec(App.Vector(sx - W / 2, H / 2 - sy, 0))
    assert uv(p3) == pytest.approx((u0, v0), abs=0.5)


def test_guide_never_in_image_plane(doc):
    box = doc.addObject("Part::Box", "Box")
    box.Placement.Base = App.Vector(30, 10, 0)
    doc.recompute()
    Gui.setActiveDocument(doc.Name)
    info = api.create_sheet(doc, "A5L", 72, "white", "XY")
    api.capture_underlay(info["name"], style="edges", opacity=0.5, doc=doc)
    plane_png = to_array(load(doc.getObject(info["image_plane"]).ImageFile))
    assert (plane_png[:, :, :3] == 255).all()                # only the paper
    with_guide = to_array(load(api.render_png(info["name"], include_underlay=True, doc=doc)))
    assert (with_guide[:, :, 0] < 200).sum() > 50
    meta = api.get_sheet(info["name"], doc=doc)
    lay = dict((x["key"], x) for x in meta["layers"])
    assert lay["underlay"]["opacity"] == 0.5
    # the board shows it (compositor with the guide)
    b = sheet.open_board(doc.getObject(info["name"]))
    process()
    assert b.canvas.compositor.underlay is not None
    sheet.close_board(doc.getObject(info["name"]))
    api.refresh_underlay(info["name"], doc=doc)
    api.clear_underlay(info["name"], doc=doc)
    obj = doc.getObject(info["name"])
    assert not hasattr(obj, model.SheetData.UNDERLAY_FILE)
    assert api.get_sheet(obj, doc=doc)["underlay"] is None


def test_board_guide_dialog(doc):
    from freecad.croquis import panels
    box = doc.addObject("Part::Box", "Box")
    box.Placement.Base = App.Vector(10, 10, 0)
    doc.recompute()
    Gui.setActiveDocument(doc.Name)
    obj = sheet.create_sheet(doc, "A5L", 72, "white", "XY", "G")
    b = sheet.open_board(obj)
    process()
    m = panels.guide_model(b)
    assert m.accept(), m.error
    assert b.sheet.underlay["style"] == "edges" and b.canvas.compositor.underlay is not None
    assert b.is_modified()
    sheet.close_board(obj)                                   # saved with the sheet
    assert api.get_sheet(obj, doc=doc)["underlay"]["mode"] == "plane"
    assert hasattr(obj, model.SheetData.UNDERLAY_FILE)
    b = sheet.open_board(obj)
    process()
    assert b.canvas.compositor.underlay is not None          # shown again
    assert panels.guide_model(b).trigger("clear") == "close"
    sheet.close_board(obj)
    assert not hasattr(obj, model.SheetData.UNDERLAY_FILE)
