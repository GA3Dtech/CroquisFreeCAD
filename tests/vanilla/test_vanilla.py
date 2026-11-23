# SPDX-License-Identifier: LGPL-2.1-or-later
"""Every file written by the addon opens in a FreeCAD without the addon:
the sheet object becomes inert, its image plane keeps showing the last
render, exactly like an imported picture."""

import os
import shutil

import FreeCAD as App
import pytest
from files import documents, open_captured, unexpected_errors
from imaging import load, to_array

pytestmark = pytest.mark.vanilla

# Image X and image up in the document for each plane (sheet.plane_rotation)
PLANE_AXES = {"XY": ((1, 0, 0), (0, 1, 0)), "XZ": ((1, 0, 0), (0, 0, 1)),
              "YZ": ((0, 1, 0), (0, 0, 1))}


def test_addon_not_importable():
    with pytest.raises(ImportError):
        import freecad.croquis  # noqa: F401
    import sys
    assert not any(os.path.isdir(os.path.join(p or ".", "freecad", "croquis"))
                   for p in sys.path)


def sheets_of(doc):
    """Croquis sheets, recognized by their properties (no proxy here)."""
    return [o for o in doc.Objects
            if o.TypeId == "App::FeaturePython" and hasattr(o, "SheetData")
            and hasattr(o, "ImagePlane")]


def plane_of(rot):
    ix, iy = rot.multVec(App.Vector(1, 0, 0)), rot.multVec(App.Vector(0, 1, 0))
    for name, (ex, ey) in PLANE_AXES.items():
        if (ix - App.Vector(*ex)).Length < 1e-6 and (iy - App.Vector(*ey)).Length < 1e-6:
            return name
    return None


@pytest.mark.parametrize("path", documents(), ids=os.path.basename)
def test_open_without_addon(path, tmp_path):
    copy = str(tmp_path / os.path.basename(path))
    shutil.copy(path, copy)
    doc, text = open_captured(App, copy)
    try:
        assert unexpected_errors(text) == [], text
        sheets = sheets_of(doc)
        assert sheets, "no sheet found"
        for o in sheets:
            img = o.ImagePlane
            assert img is not None and img.TypeId == "Image::ImagePlane"
            # the image is the copy extracted from the document
            assert os.path.isfile(img.ImageFile), img.ImageFile
            assert os.path.realpath(img.ImageFile).startswith(
                os.path.realpath(doc.TransientDir))
            pic = load(img.ImageFile)
            dpi = int(o.Resolution)
            assert pic.width() == round(o.SheetWidth.Value * dpi / 25.4)
            assert pic.height() == round(o.SheetHeight.Value * dpi / 25.4)
            assert to_array(pic)[:, :, 3].max() > 0, "empty image"
            assert img.XSize.Value == pytest.approx(o.SheetWidth.Value)
            assert img.YSize.Value == pytest.approx(o.SheetHeight.Value)
            plane = plane_of(img.Placement.Rotation)
            assert plane is not None
            if o.Label.startswith("plane_"):
                assert plane == o.Label[len("plane_"):]
        doc.recompute()
        for o in doc.Objects:
            assert "Invalid" not in o.State and "Error" not in o.State, (o.Name, o.State)
    finally:
        App.closeDocument(doc.Name)
