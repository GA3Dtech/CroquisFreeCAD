# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - 3D view capture
# Copyright (C) 2026 GA3Dtech
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or (at
# your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <https://www.gnu.org/licenses/>.
"""
capture.py (Croquis) - pictures of the 3D view, shared by the manual
capture (B2) and the underlay guides (B3, B4). GUI only.

The board is an MDI view too: when it is the active tab, "the active view"
is the board. Captures always target the document's own 3D view.
"""

import os
import tempfile

import FreeCAD as App

from .errors import GuiRequiredError

BACKGROUNDS = {"current": "Current", "white": "White", "transparent": "Transparent"}


def require_gui():
    if not App.GuiUp:
        raise GuiRequiredError("capturing the 3D view needs the FreeCAD GUI")


def view_3d(doc):
    """The 3D view of a document: the active one when it is a 3D view of
    that document, else its first 3D view."""
    require_gui()
    import FreeCADGui as Gui
    gdoc = Gui.getDocument(doc.Name)
    views = gdoc.mdiViewsOfType("Gui::View3DInventor")
    if not views:
        raise GuiRequiredError("the document %r has no 3D view" % doc.Name)
    try:
        active = gdoc.ActiveView
        if active in views:
            return active
    except Exception:
        pass
    return views[0]


def camera_of(view):
    """Camera of a 3D view, JSON-ready (the Inventor camera node as text,
    plus a few readable fields)."""
    text = view.getCamera()
    # the node type is in its text (no need for pivy)
    ortho = "OrthographicCamera" in text.split("{", 1)[0]
    rot = view.getCameraOrientation()
    return {"inventor": text, "type": "ortho" if ortho else "perspective",
            "orientation": [rot.Q[0], rot.Q[1], rot.Q[2], rot.Q[3]]}


def restore_camera(view, camera):
    view.setCamera(camera["inventor"])


def sheet_planes(doc):
    """Image planes of the Croquis sheets of a document."""
    from . import sheet
    return [o.ImagePlane for o in doc.Objects
            if sheet.is_sheet(o) and o.ImagePlane is not None]


class HiddenObjects(object):
    """Context manager: hide some objects in the 3D view, then restore."""

    def __init__(self, objects):
        self.objects = [o for o in objects if o is not None and o.ViewObject is not None]
        self.saved = []

    def __enter__(self):
        self.saved = [(o, o.ViewObject.Visibility) for o in self.objects]
        for o, _v in self.saved:
            o.ViewObject.Visibility = False
        return self

    def __exit__(self, *exc):
        for o, visible in self.saved:
            o.ViewObject.Visibility = visible
        return False


class NoNaviCube(object):
    """Context manager: the navigation cube is drawn into saved images;
    hide it during a capture."""

    def __init__(self, view):
        self.viewer = None
        self.was = False
        try:
            self.viewer = view.getViewer()
            self.was = self.viewer.isEnabledNaviCube()
        except Exception:
            self.viewer = None

    def __enter__(self):
        if self.viewer is not None and self.was:
            self.viewer.setEnabledNaviCube(False)
        return self

    def __exit__(self, *exc):
        if self.viewer is not None and self.was:
            self.viewer.setEnabledNaviCube(True)
        return False


def grab(view, width, height, background="current"):
    """QImage of the 3D view at width x height pixels (no navigation cube)."""
    from .images import read
    fd, path = tempfile.mkstemp(prefix="croquis_capture_", suffix=".png")
    os.close(fd)
    try:
        with NoNaviCube(view):
            view.saveImage(path, int(width), int(height), BACKGROUNDS[background])
        return read(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def view_size(view):
    """Pixel size of a 3D view's widget."""
    try:
        size = view.getSize()
        return int(size[0]), int(size[1])
    except Exception:
        return 800, 600


def capture(doc, width=None, height=None, background="current", hide_sheets=True,
            factor=1.0):
    """(QImage, camera dict) of the document's 3D view. Default size: the
    view's own size times `factor`."""
    view = view_3d(doc)
    if width is None or height is None:
        w, h = view_size(view)
        width, height = int(w * factor), int(h * factor)
    hidden = sheet_planes(doc) if hide_sheets else []
    with HiddenObjects(hidden):
        img = grab(view, width, height, background)
    return img, camera_of(view)


# ----------------------------------------------------------------------
#  Underlay guide aligned on the sheet plane (B3)
# ----------------------------------------------------------------------
UNDERLAY_STYLES = ("edges", "wireframe", "shaded")
FAR = 100000.0      # mm: the camera sees the whole model on both sides


def plane_camera(placement, width, height):
    """Inventor text of an orthographic camera looking at an image plane
    of width x height mm (centred on its placement, facing its +Z) along
    its normal, framing exactly the sheet. With ADJUST_CAMERA, a portrait
    viewport keeps the camera height as its width: height is set so the
    sheet fills the picture either way."""
    rot = placement.Rotation
    normal = rot.multVec(App.Vector(0, 0, 1))
    pos = placement.Base + normal * FAR
    axis, angle = rot.Axis, rot.Angle
    h = height if width >= height else width
    return ("#Inventor V2.1 ascii\n\nOrthographicCamera {\n"
            "  viewportMapping ADJUST_CAMERA\n"
            "  position %.9g %.9g %.9g\n"
            "  orientation %.9g %.9g %.9g %.9g\n"
            "  nearDistance 1\n  farDistance %.9g\n  aspectRatio 1\n"
            "  focalDistance %.9g\n  height %.9g\n}\n"
            % (pos.x, pos.y, pos.z, axis.x, axis.y, axis.z, angle, 2 * FAR, FAR, h))


class DrawStyle(object):
    """Context manager: every shape shown as wireframe (black lines for the
    'edges' style), then restored."""

    def __init__(self, doc, style):
        self.doc = doc
        self.style = style
        self.saved = []

    def __enter__(self):
        if self.style == "shaded":
            return self
        for o in self.doc.Objects:
            vo = getattr(o, "ViewObject", None)
            if vo is None or not hasattr(vo, "DisplayMode") or not vo.Visibility:
                continue
            try:
                modes = vo.getDisplayModes() if hasattr(vo, "getDisplayModes") else []
            except Exception:
                modes = []
            if "Wireframe" not in modes:
                continue
            saved = {"DisplayMode": vo.DisplayMode}
            if self.style == "edges" and hasattr(vo, "LineColor"):
                saved["LineColor"] = vo.LineColor
                vo.LineColor = (0.0, 0.0, 0.0)
            vo.DisplayMode = "Wireframe"
            self.saved.append((vo, saved))
        return self

    def __exit__(self, *exc):
        for vo, saved in self.saved:
            for k, v in saved.items():
                setattr(vo, k, v)
        return False


def grayscale(img):
    from .qt import QtGui
    return img.convertToFormat(QtGui.QImage.Format_Grayscale8) \
        .convertToFormat(QtGui.QImage.Format_ARGB32)


def capture_plane(obj, data, style="edges", hide_sheets=True, max_px=3000):
    """(QImage, settings) of the sheet's plane seen from its normal, framed
    on the sheet in true size, with the sheet's proportions; the sheet's
    own image plane (and the other sheets) hidden; the user's camera and
    the draw styles restored afterwards."""
    require_gui()
    if style not in UNDERLAY_STYLES:
        raise ValueError("style must be one of %s" % ", ".join(UNDERLAY_STYLES))
    doc = obj.Document
    view = view_3d(doc)
    w_px, h_px = data.pixel_size()
    k = min(1.0, float(max_px) / max(w_px, h_px))
    w_px, h_px = max(16, int(round(w_px * k))), max(16, int(round(h_px * k)))
    hidden = sheet_planes(doc) if hide_sheets else [obj.ImagePlane]
    user = view.getCamera()
    try:
        with HiddenObjects(hidden), DrawStyle(doc, style):
            view.setCamera(plane_camera(obj.ImagePlane.Placement, data.width, data.height))
            img = grab(view, w_px, h_px, "white" if style == "edges" else "current")
    finally:
        view.setCamera(user)
    if style == "edges":
        img = grayscale(img)
    return img, {"mode": "plane", "style": style, "hide_sheets": bool(hide_sheets)}
