# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - sheet document object
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
sheet.py (Croquis) - the "Croquis::Sheet" object of a document.

A sheet is an App::FeaturePython holding the strokes as JSON (property
SheetData, model.SheetData) and a link to an Image::ImagePlane showing the
rendered PNG in the 3D scene. The image plane is a plain FreeCAD image
plane: everything that works with an imported picture works with it.

    create_sheet(doc, ...)     new sheet + image plane, returns the sheet
    update_image(obj, data)    render the PNG and load it in the image plane
    open_board(obj)            drawing board in a FreeCAD tab (GUI)

This module must import without the GUI (the proxies are restored when a
document is opened in FreeCADCmd): Qt and FreeCADGui are imported lazily.
"""

import os
import tempfile

import FreeCAD as App

from . import icon, model
from .i18n import tr

TYPE = "Croquis::Sheet"
PLANES = ("XY", "XZ", "YZ")


def is_sheet(obj):
    proxy = getattr(obj, "Proxy", None)
    return getattr(proxy, "Type", None) == TYPE


def plane_rotation(plane):
    """Rotation putting the image (X right, Y up, facing +Z) on a plane of
    the document, seen the right way up from the matching standard view."""
    if plane == "XZ":       # front view: image X -> X, image up -> Z
        return App.Rotation(App.Vector(1, 0, 0), 90)
    if plane == "YZ":       # right view: image X -> Y, image up -> Z
        return App.Rotation(App.Vector(1, 1, 1), 120)
    return App.Rotation()


def sheet_data(obj):
    """model.SheetData of a sheet object (paper and dpi from its properties,
    picture files from its file properties)."""
    data = model.SheetData.from_json(obj.SheetData)
    data.paper = obj.Paper
    data.dpi = int(obj.Resolution)
    for e in data.elements:
        name = getattr(e, "file", None)
        if name and hasattr(obj, name):
            data.files[name] = getattr(obj, name)
    # Scale of the image plane (3D mm per sheet mm), changed by the board's
    # scale tool; not in the JSON: the Scale property is the reference
    data.plane_scale = data.plane_scale_read = float(getattr(obj, "Scale", 1.0) or 1.0)
    if data.underlay is not None and hasattr(obj, model.SheetData.UNDERLAY_FILE):
        data.files[model.SheetData.UNDERLAY_FILE] = getattr(obj, model.SheetData.UNDERLAY_FILE)
    return data


IMAGE_PREFIX = "Image_"


def sync_files(obj, data):
    """Store the picture of every image element in a file property of the
    sheet (App::PropertyFileIncluded: the file is saved inside the .FCStd),
    drop the properties no element uses any more."""
    used = set()
    for e in data.images():
        name = e.file
        used.add(name)
        path = data.files.get(name)
        if not path:
            continue
        if not hasattr(obj, name):
            obj.addProperty("App::PropertyFileIncluded", name, "Croquis images",
                            "Picture of an image element of the sheet")
            obj.setEditorMode(name, 2)
        if getattr(obj, name) != path:
            setattr(obj, name, path)
        data.files[name] = getattr(obj, name)      # the document's own copy
    for name in list(obj.PropertiesList):
        if name.startswith(IMAGE_PREFIX) and name not in used:
            obj.removeProperty(name)
    # the 3D view guide (never drawn in the image plane)
    guide = model.SheetData.UNDERLAY_FILE
    path = data.files.get(guide) if data.underlay is not None else None
    if path:
        if not hasattr(obj, guide):
            obj.addProperty("App::PropertyFileIncluded", guide, "Croquis images",
                            "3D view guide under the strokes (not in the image plane)")
            obj.setEditorMode(guide, 2)
        if getattr(obj, guide) != path:
            setattr(obj, guide, path)
        data.files[guide] = getattr(obj, guide)
    elif hasattr(obj, guide):
        obj.removeProperty(guide)


# ----------------------------------------------------------------------
#  Feature
# ----------------------------------------------------------------------
class SheetFeature(object):
    """Proxy of a sketch sheet."""

    Type = TYPE

    def __init__(self, obj):
        obj.Proxy = self
        self.setup(obj)

    def setup(self, obj):
        grp = "Croquis"
        if not hasattr(obj, "SheetData"):
            obj.addProperty("App::PropertyString", "SheetData", grp,
                            "Strokes, layers and paper of the sheet (JSON)")
        if not hasattr(obj, "Paper"):
            obj.addProperty("App::PropertyEnumeration", "Paper", grp,
                            "Paper under the strokes (transparent: PNG with alpha)")
            obj.Paper = [k for k, _l, _c in model.PAPERS]
            obj.Paper = "transparent"
        if not hasattr(obj, "Resolution"):
            obj.addProperty("App::PropertyInteger", "Resolution", grp,
                            "Resolution of the rendered image, in dots per inch")
            obj.Resolution = 150
        if not hasattr(obj, "SheetWidth"):
            obj.addProperty("App::PropertyLength", "SheetWidth", grp, "Width of the sheet")
        if not hasattr(obj, "SheetHeight"):
            obj.addProperty("App::PropertyLength", "SheetHeight", grp, "Height of the sheet")
        if not hasattr(obj, "ImagePlane"):
            obj.addProperty("App::PropertyLink", "ImagePlane", grp,
                            "Image plane showing the sheet in the 3D view")
        if not hasattr(obj, "Scale"):
            obj.addProperty("App::PropertyFloat", "Scale", grp,
                            "Size in the 3D view of one millimetre of the sheet (1 = true "
                            "size); scaling the image plane by hand updates it")
            obj.Scale = 1.0
        obj.setEditorMode("SheetData", 2)       # hidden: large JSON
        obj.setEditorMode("SheetWidth", 1)      # read-only
        obj.setEditorMode("SheetHeight", 1)

    def onDocumentRestored(self, obj):
        self.setup(obj)

    def onChanged(self, obj, prop):
        if prop == "Scale":
            if not _storing and "Restore" not in obj.State and hasattr(obj, "ImagePlane"):
                if obj.Scale <= 0:
                    obj.Scale = 1.0
                    return
                size_plane(obj)
            return
        # Paper / resolution edited in the property view: re-render
        if prop not in ("Paper", "Resolution"):
            return
        if _storing or "Restore" in obj.State or not hasattr(obj, "ImagePlane"):
            return
        if prop == "Resolution" and obj.Resolution < 10:
            obj.Resolution = 10
            return
        if App.GuiUp and obj.ImagePlane is not None and obj.SheetData:
            try:
                update_image(obj, sheet_data(obj))
            except Exception as exc:
                App.Console.PrintError("Croquis: image not updated (%s)\n" % exc)

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


class ViewProviderSheet(object):
    """Tree entry of a sheet: image plane as child, double-click to draw."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object
        try:
            from pivy import coin
            vobj.addDisplayMode(coin.SoGroup(), "Default")
        except Exception:
            pass

    def getDisplayModes(self, vobj):
        return ["Default"]

    def getDefaultDisplayMode(self):
        return "Default"

    def getIcon(self):
        return icon("Croquis.svg")

    def claimChildren(self):
        obj = getattr(self, "Object", None)
        plane = getattr(obj, "ImagePlane", None) if obj is not None else None
        return [plane] if plane is not None else []

    def doubleClicked(self, vobj):
        open_board(vobj.Object)
        return True

    def setupContextMenu(self, vobj, menu):
        from .qt import QtGui
        action = menu.addAction(QtGui.QIcon(icon("EditSheet.svg")), tr("Edit sketch sheet"))
        action.triggered.connect(lambda: open_board(vobj.Object))

    def onDelete(self, vobj, subelements):
        close_board(vobj.Object, save=False)
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


# ----------------------------------------------------------------------
#  Creation and image
# ----------------------------------------------------------------------
def create_sheet(doc, fmt="A4L", dpi=150, paper="transparent", plane="XZ",
                 label=None, size=None):
    """New sheet and its image plane (inside the caller's transaction).
    size: (width, height) in mm instead of a format."""
    import Image  # noqa: F401  (registers Image::ImagePlane)
    w, h = size if size is not None else model.format_size(fmt)
    data = model.SheetData(w, h, dpi, paper)

    obj = doc.addObject("App::FeaturePython", "Croquis")
    SheetFeature(obj)
    if App.GuiUp:
        ViewProviderSheet(obj.ViewObject)
    if label:
        obj.Label = label
    obj.SheetWidth = w
    obj.SheetHeight = h
    obj.Resolution = int(dpi)
    obj.Paper = paper
    obj.SheetData = data.to_json()

    img = doc.addObject("Image::ImagePlane", obj.Name + "_Image")
    img.Label = obj.Label + " " + tr("(image)")
    img.Placement = App.Placement(App.Vector(0, 0, 0), plane_rotation(plane))
    img.XSize, img.YSize = w, h
    obj.ImagePlane = img
    container(doc).addObject(obj)
    update_image(obj, data)
    return obj


def container(doc):
    """The document's "Croquis" group, holding every sheet (created on
    first use; a plain group, so files still open without the addon)."""
    for o in doc.Objects:
        if o.TypeId == "App::DocumentObjectGroup" and hasattr(o, "CroquisContainer"):
            return o
    grp = doc.addObject("App::DocumentObjectGroup", "Croquis_Sheets")
    grp.Label = "Croquis"
    grp.addProperty("App::PropertyBool", "CroquisContainer", "Croquis",
                    "Group of the Croquis sheets of the document")
    grp.CroquisContainer = True
    grp.setEditorMode("CroquisContainer", 2)
    return grp


def update_image(obj, data):
    """Render the sheet and load the PNG into its image plane (the file is
    copied into the document, so it is saved inside the .FCStd)."""
    img = obj.ImagePlane
    if img is None:
        return
    from .render import compositor
    folder = tempfile.mkdtemp(prefix="croquis_")
    # FreeCAD keeps the first file name in the document and only replaces
    # its content (with a backup for undo), so the name can stay the same
    path = os.path.join(folder, "%s.png" % obj.Name)
    try:
        if not compositor.save_png(data, path):
            raise IOError(tr("Could not write {path}.").format(path=path))
        # detect a manual scaling BEFORE loading the picture: in the GUI the
        # image plane's view provider resizes the plane on a new image
        adopt_manual_scale(obj)
        img.ImageFile = path
        size_plane(obj, data.width, data.height)
    finally:
        try:
            os.remove(path)
            os.rmdir(folder)
        except OSError:
            pass


def adopt_manual_scale(obj):
    """The image plane was scaled by hand (XSize no longer matches the
    sheet width x Scale): keep that scale instead of resetting it."""
    img = obj.ImagePlane
    if img is None or not hasattr(obj, "Scale") or obj.SheetWidth.Value <= 0:
        return
    expected = obj.SheetWidth.Value * obj.Scale
    actual = img.XSize.Value
    if actual > 0 and abs(actual - expected) > 1e-6 * max(1.0, expected):
        global _storing
        _storing = True
        try:
            obj.Scale = actual / obj.SheetWidth.Value
        finally:
            _storing = False


def size_plane(obj, width=None, height=None):
    """Image plane size = sheet size x Scale."""
    img = obj.ImagePlane
    if img is None:
        return
    k = getattr(obj, "Scale", 1.0) or 1.0
    img.XSize = (width if width is not None else obj.SheetWidth.Value) * k
    img.YSize = (height if height is not None else obj.SheetHeight.Value) * k


_storing = False


def write(obj, data):
    """Write the strokes, paper and layers of `data` into the sheet object
    and refresh its image (inside the caller's transaction)."""
    global _storing
    _storing = True     # no re-render from onChanged: done once below
    try:
        if obj.Paper != data.paper:
            obj.Paper = data.paper
        if int(obj.Resolution) != int(data.dpi):
            obj.Resolution = int(data.dpi)
    finally:
        _storing = False
    adopt_manual_scale(obj)
    scale = getattr(data, "plane_scale", None)
    if scale is not None and scale != getattr(data, "plane_scale_read", None) and scale > 0:
        _storing = True
        try:
            obj.Scale = scale           # set on the board (scale tool) or the API
        finally:
            _storing = False
        size_plane(obj)
    sync_files(obj, data)
    obj.SheetData = data.to_json()
    # the size after the render: update_image compares the plane with the
    # former size to detect a manual scaling
    update_image(obj, data)
    obj.SheetWidth = data.width
    obj.SheetHeight = data.height


def store(obj, data):
    """write() as one FreeCAD undo step."""
    doc = obj.Document
    doc.openTransaction(tr("Edit sketch sheet"))
    try:
        write(obj, data)
    finally:
        doc.commitTransaction()


def plane_of(obj):
    """"XY", "XZ", "YZ" when the image plane lies on one of them, else
    "custom"."""
    img = obj.ImagePlane
    if img is None:
        return "custom"
    rot = img.Placement.Rotation
    for name in PLANES:
        ref = plane_rotation(name)
        if all((rot.multVec(v) - ref.multVec(v)).Length < 1e-6
               for v in (App.Vector(1, 0, 0), App.Vector(0, 1, 0))):
            return name
    return "custom"


# ----------------------------------------------------------------------
#  Drawing board (GUI)
# ----------------------------------------------------------------------
_boards = {}    # (document name, object name) -> QMdiSubWindow
WORKBENCH = "CroquisWorkbench"


def _key(obj):
    return (obj.Document.Name, obj.Name)


def open_board(obj):
    """Open (or bring forward) the drawing board of a sheet in a tab of
    FreeCAD's main window."""
    import FreeCADGui as Gui

    from .canvas.view import SheetBoard
    from .qt import QtCore, QtGui, QtWidgets

    # The board belongs to the Croquis workbench: leaving the workbench
    # closes it (init_gui.CroquisWorkbench.Deactivated)
    if Gui.activeWorkbench().name() != WORKBENCH:
        Gui.activateWorkbench(WORKBENCH)

    key = _key(obj)
    sub = _boards.get(key)
    if sub is not None:
        try:
            sub.mdiArea().setActiveSubWindow(sub)
            sub.widget().show_panel()       # editing again brings the panel back
            sub.widget().canvas.setFocus()
            return sub.widget()
        except RuntimeError:        # deleted on the C++ side
            _boards.pop(key, None)

    mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    if mdi is None:
        raise RuntimeError("main window has no MDI area")

    doc_name, obj_name = key

    def apply(board):
        doc = App.getDocument(doc_name) if doc_name in App.listDocuments() else None
        target = doc.getObject(obj_name) if doc is not None else None
        if target is None:
            App.Console.PrintWarning(
                tr("Croquis: the sheet no longer exists, strokes not saved.") + "\n")
            return
        store(target, board.sheet)

    export_dir = os.path.dirname(obj.Document.FileName) if obj.Document.FileName \
        else os.path.expanduser("~")
    board = SheetBoard(sheet_data(obj), "%s - Croquis" % obj.Label, on_apply=apply,
                       export_path=os.path.join(export_dir, obj.Label + ".png"))
    board.canvas.doc_name = doc_name
    board.sheet_name = obj_name
    sub = mdi.addSubWindow(board)
    sub.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    sub.setWindowIcon(QtGui.QIcon(icon("Croquis.svg")))
    sub.destroyed.connect(lambda *_a: _boards.pop(key, None))
    _boards[key] = sub
    sub.showMaximized()
    mdi.setActiveSubWindow(sub)
    board.canvas.setFocus()
    return board


def active_board():
    """The board in the active MDI tab, or None."""
    import FreeCADGui as Gui

    from .qt import QtWidgets
    mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    sub = mdi.activeSubWindow() if mdi is not None else None
    for s in _boards.values():
        if s is sub:
            return s.widget()
    return None


def show_panels():
    """'Show the Croquis panel': the side panel of the active board (or of
    every open board)."""
    board = active_board()
    boards = [board] if board is not None else \
        [s.widget() for s in list(_boards.values())]
    for b in boards:
        try:
            b.show_panel()
        except RuntimeError:
            pass
    return len(boards)


def board_of(obj):
    """The open board of a sheet, or None."""
    sub = _boards.get(_key(obj))
    try:
        return sub.widget() if sub is not None else None
    except RuntimeError:
        return None


def resize_from_board(doc, name, margins):
    """'Sheet size…' of a board: write and close the board, resize the
    sheet (api.resize_sheet), open the board again."""
    from . import api
    obj = doc.getObject(name) if doc is not None else None
    if obj is None:
        return None
    close_board(obj, save=True)
    try:
        api.resize_sheet(obj, doc=doc, **margins)
    finally:
        board = open_board(obj)
    return board


def close_board(obj, save=True):
    """Close the board of a sheet if it is open (without saving when the
    sheet is being deleted)."""
    _close(_key(obj), save)


def close_all_boards():
    """Close every board, saving the strokes, and come back to the 3D view:
    outside the Croquis workbench a sheet is just its image plane."""
    docs = set()
    for key in list(_boards):
        docs.add(key[0])
        _close(key, True)
    import FreeCADGui as Gui
    for name in docs:
        try:
            Gui.getDocument(name).activateView("Gui::View3DInventor")
        except Exception:
            pass


def _close(key, save):
    sub = _boards.pop(key, None)
    if sub is None:
        return
    try:
        if not save:
            sub.widget().on_apply = None
            sub.widget().mark_saved()
        sub.close()
    except RuntimeError:
        pass
