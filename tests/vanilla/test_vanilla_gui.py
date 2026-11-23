# SPDX-License-Identifier: LGPL-2.1-or-later
"""Without the addon, in the GUI: the image plane of a sheet is displayed
(scene bounding box) and shows up in a capture of the 3D view."""

import os
import shutil

import FreeCAD as App
import pytest
from files import documents, open_captured
from imaging import load, to_array

pytestmark = [pytest.mark.vanilla, pytest.mark.gui]

if not App.GuiUp:
    pytest.skip("needs the FreeCAD GUI", allow_module_level=True)

import FreeCADGui as Gui  # noqa: E402

OFFSCREEN = os.environ.get("QT_QPA_PLATFORM", "") == "offscreen" or \
    os.environ.get("FREECAD_QT_QPA_PLATFORM", "") == "offscreen"


def bounding_box(vobj):
    from pivy import coin
    act = coin.SoGetBoundingBoxAction(coin.SbViewportRegion(400, 300))
    act.apply(vobj.RootNode)
    return act.getBoundingBox()


@pytest.mark.parametrize("path", documents(), ids=os.path.basename)
def test_image_plane_displayed(path, tmp_path):
    copy = str(tmp_path / os.path.basename(path))
    shutil.copy(path, copy)
    doc, _text = open_captured(App, copy)
    try:
        planes = [o for o in doc.Objects if o.TypeId == "Image::ImagePlane"]
        assert planes
        for img in planes:
            box = bounding_box(img.ViewObject)
            assert not box.isEmpty(), img.Name
            lo, hi = box.getMin().getValue(), box.getMax().getValue()
            extent = sorted(abs(b - a) for a, b in zip(lo, hi))
            # a flat rectangle of the sheet size (mm)
            assert extent[0] < 1e-3
            assert extent[2] == pytest.approx(max(img.XSize.Value, img.YSize.Value), rel=1e-3)
        # capture: only one sheet visible, seen from its normal
        for o in doc.Objects:
            if o.TypeId == "Image::ImagePlane":
                o.ViewObject.Visibility = o is planes[0]
        Gui.setActiveDocument(doc.Name)
        view = Gui.ActiveDocument.ActiveView
        rot = planes[0].Placement.Rotation
        view.setCameraOrientation(rot)
        view.fitAll()
        out = str(tmp_path / "capture.png")
        view.saveImage(out, 400, 300, "White")
        arr = to_array(load(out))
        centre = arr[100:200, 130:270, :3]
        if OFFSCREEN and (arr[:, :, :3] == 255).all():
            pytest.skip("no OpenGL rendering on the offscreen platform (checked under xvfb)")
        assert (centre < 250).any(), "the image plane is not visible in the capture"
    finally:
        App.closeDocument(doc.Name)
