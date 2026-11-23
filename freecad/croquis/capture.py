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


def grab(view, width, height, background="current"):
    """QImage of the 3D view at width x height pixels."""
    from .images import read
    fd, path = tempfile.mkstemp(prefix="croquis_capture_", suffix=".png")
    os.close(fd)
    try:
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
