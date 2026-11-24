# SPDX-License-Identifier: LGPL-2.1-or-later
"""Manual 3D view capture (B2): picture of the 3D view (never the board),
sheets hidden during the capture, camera kept and restored."""

import FreeCAD as App
import FreeCADGui as Gui
import numpy as np
import pytest
from conftest import process
from imaging import load, to_array

from freecad.croquis import api, capture, panels, sheet

pytestmark = pytest.mark.gui


@pytest.fixture
def scene(doc):
    box = doc.addObject("Part::Box", "Box")
    box.Placement.Base = App.Vector(200, 0, 0)
    box.ViewObject.ShapeColor = (0.1, 0.2, 0.9)
    doc.recompute()
    Gui.setActiveDocument(doc.Name)
    view = capture.view_3d(doc)
    view.viewIsometric()
    view.fitAll()
    capture.stop_animation(view)        # under xvfb the views animate
    process()
    return doc, view


def blue_pixels(arr):
    r, g, b = (arr[:, :, i].astype(int) for i in range(3))
    return int(((b - r > 60) & (b - g > 40)).sum())


def kraft_pixels(arr):
    r, g, b = (arr[:, :, i].astype(int) for i in range(3))
    return int(((r - b > 45) & (r > 120) & (g > 90) & (np.abs(r - g) < 50)).sum())


def picture_of(doc, res):
    obj = doc.getObject(res["sheet"]["name"])
    return to_array(load(getattr(obj, "Image_" + res["image"]["id"])))


def test_capture_on_new_sheet(scene):
    doc, view = scene
    w, h = capture.view_size(view)
    n = doc.UndoCount
    res = api.capture_3d_view(doc, background="white")
    assert doc.UndoCount == n + 1                    # one undo step
    s, e = res["sheet"], res["image"]
    assert s["width_mm"] / s["height_mm"] == pytest.approx(w / h, rel=0.01)
    assert e["camera"]["inventor"] and e["camera"]["type"] in ("ortho", "perspective")
    assert e["source_px"][0] <= w * 2
    assert blue_pixels(picture_of(doc, res)) > 50


def test_sheets_hidden_during_capture(scene):
    doc, view = scene
    info = api.create_sheet(doc, "A4L", 72, "kraft", "XY")
    view.fitAll()
    process()
    shown = api.capture_3d_view(doc, background="white", hide_sheets=False)
    hidden = api.capture_3d_view(doc, background="white", hide_sheets=True)
    assert kraft_pixels(picture_of(doc, shown)) > 200
    assert kraft_pixels(picture_of(doc, hidden)) == 0
    assert doc.getObject(info["image_plane"]).ViewObject.Visibility    # restored


def same_rotation(a, b, tol=1e-4):
    qa, qb = a.Q, b.Q
    return max(abs(x - y) for x, y in zip(qa, qb)) < tol or \
        max(abs(x + y) for x, y in zip(qa, qb)) < tol


def test_camera_restored(scene):
    doc, view = scene
    res = api.capture_3d_view(doc)
    before = view.getCameraOrientation()
    import re
    text = re.sub(r"orientation [^\n]*", "orientation 1 0 0 1.5707963", view.getCamera())
    capture.stop_animation(view)
    view.setCamera(text)          # immediate (orientation changes are animated)
    process()
    assert not same_rotation(view.getCameraOrientation(), before)
    api.restore_image_view(res["sheet"]["name"], res["image"]["id"], doc=doc)
    assert same_rotation(view.getCameraOrientation(), before)


def test_capture_with_board_open_targets_the_3d_view(scene):
    doc, view = scene
    obj = sheet.create_sheet(doc, "A5L", 72, "kraft", "XY", "Board")
    board = sheet.open_board(obj)
    process()
    assert sheet.active_board() is board
    m = panels.capture_model(doc, board)
    assert m.v["target"] == "board" and "target" not in m.hidden()
    m.set("background", "white")
    assert m.accept(), m.error
    e = m.result["element"]
    assert board.sheet.images() == [e] and e.camera
    arr = to_array(load(board.sheet.files[e.file]))
    assert blue_pixels(arr) > 50                      # the 3D view, not the board
    assert kraft_pixels(arr) == 0                     # sheets hidden, no board pixels


@pytest.mark.parametrize("camera_type", ["Orthographic", "Perspective"])
def test_new_sheet_lies_on_the_captured_view(scene, camera_type):
    doc, view = scene
    view.setCameraType(camera_type)
    view.viewIsometric()
    view.fitAll()
    capture.stop_animation(view)
    process()
    res = api.capture_3d_view(doc, background="white")
    obj = doc.getObject(res["sheet"]["name"])
    plc = obj.ImagePlane.Placement
    cam = view.getCameraOrientation()
    assert max(abs(a - b) for a, b in zip(plc.Rotation.Q, cam.Q)) < 1e-6 or \
        max(abs(a + b) for a, b in zip(plc.Rotation.Q, cam.Q)) < 1e-6
    w, h = res["sheet"]["width_mm"], res["sheet"]["height_mm"]
    k = obj.Scale
    assert obj.ImagePlane.XSize.Value == pytest.approx(w * k)
    # the box centre, seen along the view, falls on the box in the picture
    box = doc.getObject("Box")
    centre = box.Shape.BoundBox.Center
    d = view.getViewDirection()
    # project the centre on the sheet plane along the view direction
    n = plc.Rotation.multVec(App.Vector(0, 0, 1))
    t = (plc.Base - centre).dot(n) / d.dot(n)
    hit = centre + d * t if camera_type == "Orthographic" else None
    if hit is None:                                      # perspective: through the eye
        eye = App.Vector(*[float(v) for v in __import__("re").search(
            r"position\s+(\S+)\s+(\S+)\s+(\S+)", view.getCamera()).groups()])
        ray = centre - eye
        hit = eye + ray * ((plc.Base - eye).dot(n) / ray.dot(n))
    local = plc.Rotation.inverted().multVec(hit - plc.Base)
    sx, sy = local.x / k + w / 2, h / 2 - local.y / k
    arr = picture_of(doc, res)
    ph, pw = arr.shape[:2]
    X, Y = int(sx / w * pw), int(sy / h * ph)
    patch = arr[max(0, Y - 3):Y + 4, max(0, X - 3):X + 4]
    assert blue_pixels(patch) > 0, (X, Y)


def test_new_sheet_defaults_camera_view_guide(scene):
    """The unified New sheet: size of the view, camera plane at scale,
    transparent paper, wireframe guide."""
    doc, view = scene
    m = panels.NewSheetModel(doc)
    for k, v in (("format", "view"), ("plane", "camera"), ("paper", "transparent"),
                 ("background", "guide"), ("dpi", "72")):
        assert m.set(k, v), m.error
    assert m.accept(), m.error
    info = m.created
    obj = doc.getObject(info["name"])
    w, h = capture.view_size(view)
    assert info["width_mm"] / info["height_mm"] == pytest.approx(w / h, rel=0.01)
    cam = view.getCameraOrientation()
    q = obj.ImagePlane.Placement.Rotation.Q
    assert max(abs(a - b) for a, b in zip(q, cam.Q)) < 1e-6 or \
        max(abs(a + b) for a, b in zip(q, cam.Q)) < 1e-6
    assert obj.Scale != 1.0 and info["underlay"]["mode"] == "plane"
    guide = to_array(load(getattr(obj, "UnderlayImage")))
    assert (guide[:, :, 0] < 110).sum() > 50                   # edges drawn
    assert blue_pixels(guide) == 0                              # wireframe: no shaded face
    plane = to_array(load(obj.ImagePlane.ImageFile))
    assert plane[:, :, 3].max() == 0                            # guide never exported


def test_new_sheet_picture_background(scene):
    doc, view = scene
    m = panels.NewSheetModel(doc, background="picture")
    m.set("dpi", "72")
    assert m.accept(), m.error
    imgs = api.list_images(m.created["name"], doc=doc)
    assert len(imgs) == 1 and imgs[0]["camera"] and imgs[0]["x"] == pytest.approx(0, abs=0.01)
    m2 = panels.NewSheetModel(doc)
    for k, v in (("format", "A5L"), ("plane", "XY"), ("background", "none"), ("dpi", "72")):
        m2.set(k, v)
    assert m2.accept() and m2.created["plane"] == "XY" and m2.created["underlay"] is None
