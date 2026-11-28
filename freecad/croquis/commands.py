# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - GUI commands
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
commands.py (Croquis) - FreeCAD commands. Thin wrappers: the work is done
in sheet.py (document objects) and canvas/ (drawing board).
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import icon
from .i18n import tr


class _Command(object):
    """Generic command: calls `action`, reports errors in the report view
    instead of letting them escape into FreeCAD."""

    def __init__(self, action, icon_file, menu_text, tooltip,
                 needs_document=True, needs=None, accel=None):
        self._action = action
        self._icon = icon_file
        self._menu_text = menu_text
        self._tooltip = tooltip
        self._needs_document = needs_document
        self._needs = needs
        self._accel = accel

    def GetResources(self):
        res = {"Pixmap": icon(self._icon),
               "MenuText": self._menu_text,
               "ToolTip": self._tooltip}
        if self._accel:
            res["Accel"] = self._accel
        return res

    def Activated(self):
        try:
            self._action()
        except Exception as exc:  # surface the error, never crash FreeCAD
            import traceback
            App.Console.PrintError("Croquis: %s\n%s\n" % (exc, traceback.format_exc()))

    def IsActive(self):
        if self._needs_document and App.ActiveDocument is None:
            return False
        if self._needs is not None:
            try:
                return bool(self._needs())
            except Exception:
                return False
        return True


# ----------------------------------------------------------------------
#  Selection helpers
# ----------------------------------------------------------------------
def selected_sheets():
    """Sheets in the selection; an image plane counts for its sheet."""
    from . import sheet
    out = []
    for obj in Gui.Selection.getSelection():
        if sheet.is_sheet(obj):
            target = obj
        else:
            target = next((o for o in obj.InList if sheet.is_sheet(o)), None)
        if target is not None and target not in out:
            out.append(target)
    return out


def _one_sheet():
    return len(selected_sheets()) == 1


# ----------------------------------------------------------------------
#  New sheet
# ----------------------------------------------------------------------
def new_sheet():
    """The New sheet panel (generic panel model, QML or widgets)."""
    from . import panels, qml_host, sheet
    doc = App.ActiveDocument
    m = panels.new_sheet_model(doc)
    if not qml_host.run_dialog(m) or m.created is None:
        return
    obj = doc.getObject(m.created["name"])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    sheet.open_board(obj)


def insert_image():
    """Picture file on the selected sheet (its open board when there is one)."""
    import os

    from . import api, sheet
    from .canvas.view import image_filter
    from .qt import QtWidgets
    obj = selected_sheets()[0]
    board = sheet.board_of(obj)
    if board is not None:
        board.insert_image()
        return
    folder = os.path.dirname(obj.Document.FileName) if obj.Document.FileName \
        else os.path.expanduser("~")
    path, _flt = QtWidgets.QFileDialog.getOpenFileName(
        Gui.getMainWindow(), tr("Insert image"), folder, image_filter())
    if path:
        api.add_image(obj, path)


def new_sheet_from_clipboard():
    """New sheet shaped like the picture of the clipboard, picture on it,
    board open."""
    from . import api, images, prefs, sheet
    from .qt import QtWidgets
    img, paths = images.from_mime(QtWidgets.QApplication.clipboard().mimeData())
    tmp = None
    if paths:
        path = paths[0]
    elif img is not None:
        path = tmp = images.save_temp(img, "croquis_clipboard")
    else:
        QtWidgets.QMessageBox.information(
            Gui.getMainWindow(), "Croquis",
            tr("The clipboard holds no picture. Copy a screenshot or an image first."))
        return
    try:
        res = api.new_sheet_from_image(App.ActiveDocument, path, plane=prefs.get("SheetPlane"),
                                       dpi=prefs.get("SheetDpi"), label=tr("Sketch"))
    finally:
        if tmp:
            import os
            os.remove(tmp)
    obj = App.ActiveDocument.getObject(res["sheet"]["name"])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    sheet.open_board(obj)


def capture_3d_view():
    """With a board open: put a capture of the 3D view on it. Otherwise:
    the New sheet dialog with the capture as background (same defaults:
    size of the view, camera plane, scale)."""
    from . import panels, qml_host, sheet
    doc = App.ActiveDocument
    board = sheet.active_board()
    if board is None:
        m = panels.NewSheetModel(doc, background="picture")
        if not qml_host.run_dialog(m) or m.created is None:
            return
        obj = doc.getObject(m.created["name"])
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj)
        sheet.open_board(obj)
        return
    m = panels.capture_model(doc, board)
    if not qml_host.run_dialog(m) or not m.result or "sheet" not in m.result:
        return
    obj = doc.getObject(m.result["sheet"]["name"])
    sheet.open_board(obj)


# ----------------------------------------------------------------------
#  Sketch on a face
# ----------------------------------------------------------------------
def _picked_faces():
    """(object, full sub-name, picked point or None) of the faces in the
    selection, through containers (top-level objects)."""
    out = []
    for sel in Gui.Selection.getSelectionEx("", 0):
        pts = list(getattr(sel, "PickedPoints", []) or [])
        for i, sub in enumerate(sel.SubElementNames):
            if sub.split(".")[-1].startswith("Face"):
                pt = pts[i] if i < len(pts) else None
                out.append((sel.Object, sub, pt))
    return out


def _camera_up(doc):
    try:
        view = Gui.getDocument(doc.Name).ActiveView
        return view.getCameraOrientation().multVec(App.Vector(0, 1, 0))
    except Exception:
        return None


def sheet_on_face_of(obj, sub, point=None):
    """New sheet on a face (api.create_sheet_on_face), board open."""
    from . import api, prefs, sheet
    doc = obj.Document
    up = _camera_up(doc)
    res = api.create_sheet_on_face(
        obj, sub, point=None if point is None else [point.x, point.y, point.z],
        up=None if up is None else [up.x, up.y, up.z], dpi=int(prefs.get("SheetDpi")), doc=doc)
    target = doc.getObject(res["name"])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(target)
    return sheet.open_board(target)


class _FacePicker(object):
    """Waits for a click on a face of the 3D view, then lays a sheet on it.
    Running the command again cancels."""

    def __init__(self):
        self.active = False

    def start(self):
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self)
        self.active = True
        _status(tr("Croquis: click a face to sketch on it (the command again cancels)"))

    def stop(self, message=""):
        if self.active:
            Gui.Selection.removeObserver(self)
            self.active = False
        _status(message)

    def addSelection(self, doc, obj, sub, pnt):
        if sub and sub.split(".")[-1].startswith("Face"):
            from .qt import QtCore
            QtCore.QTimer.singleShot(0, self.take)     # not inside the observer call

    def take(self):
        faces = _picked_faces()
        if not self.active or not faces:
            return
        self.stop()
        try:
            sheet_on_face_of(*faces[0])
        except Exception as exc:
            App.Console.PrintError("Croquis: %s\n" % exc)


_picker = _FacePicker()


def _status(text):
    try:
        Gui.getMainWindow().statusBar().showMessage(text, 0 if text else 1)
    except Exception:
        pass


def sheet_on_face():
    """A face selected: sheet on it at once. Otherwise wait for a click on
    a face (again: cancel)."""
    if _picker.active:
        _picker.stop()
        return
    faces = _picked_faces()
    if faces:
        sheet_on_face_of(*faces[0])
    else:
        _picker.start()


def edit_sheet():
    from . import sheet
    for obj in selected_sheets():
        sheet.open_board(obj)


def export_png():
    import os

    from . import api
    from .qt import QtWidgets
    obj = selected_sheets()[0]
    folder = os.path.dirname(obj.Document.FileName) if obj.Document.FileName \
        else os.path.expanduser("~")
    path, _flt = QtWidgets.QFileDialog.getSaveFileName(
        Gui.getMainWindow(), tr("Export sheet as PNG"),
        os.path.join(folder, obj.Label + ".png"), tr("PNG image (*.png)"))
    if not path:
        return
    if not path.lower().endswith(".png"):
        path += ".png"
    path = api.export_png(obj, path)
    if path:
        App.Console.PrintMessage(tr("Croquis: sheet exported to {path}").format(path=path)
                                 + "\n")


class _ToggleSheets(object):
    """Show / hide every sketch of the active document at once. Checkable:
    the button stays pressed while the sketches are shown."""

    def GetResources(self):
        return {"Pixmap": icon("ToggleSheets.svg"), "MenuText": tr("Show / hide the sketches"),
                "ToolTip": tr("Show or hide every sketch sheet of the document at once (C, V)"),
                "Accel": "C, V", "Checkable": True}

    def Activated(self, checked=None):
        from . import api
        try:
            api.set_sheets_visible(App.ActiveDocument)
        except Exception as exc:
            App.Console.PrintError("Croquis: %s\n" % exc)
        self._sync()

    def _sync(self):
        """Pressed while the sketches are shown."""
        from . import api
        try:
            state = api.sheets_visible(App.ActiveDocument) is True
            action = Gui.Command.get("Croquis_ToggleSheets").getAction()
            for a in action:
                if a.isChecked() != state:
                    a.blockSignals(True)
                    a.setChecked(state)
                    a.blockSignals(False)
        except Exception:
            pass

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        self._sync()
        return True


def export_pdf():
    """Selected sheets to one PDF, a page per sheet."""
    import os

    from . import sheet
    from .canvas.view import export_pdf_dialog
    objs = selected_sheets()
    folder = os.path.dirname(objs[0].Document.FileName) if objs[0].Document.FileName \
        else os.path.expanduser("~")
    path = export_pdf_dialog(Gui.getMainWindow(), [sheet.sheet_data(o) for o in objs],
                             os.path.join(folder, objs[0].Label + ".pdf"))
    if path:
        App.Console.PrintMessage(tr("Croquis: sheet exported to {path}").format(path=path)
                                 + "\n")


# Filled by register(); kept as module lists for init_gui
TOOLBAR = []
MENU = []
CONTEXT = []


def register():
    """Add every command to FreeCAD."""
    cmds = [
        ("Croquis_NewSheet", _Command(
            new_sheet, "NewSheet.svg", tr("New sketch sheet"),
            tr("Create a sketch sheet and its image plane, and open the drawing board"))),
        ("Croquis_EditSheet", _Command(
            edit_sheet, "EditSheet.svg", tr("Edit sketch sheet"),
            tr("Open the drawing board of the selected sheet (or double-click it)"),
            needs=lambda: bool(selected_sheets()))),
        ("Croquis_NewSheetFromClipboard", _Command(
            new_sheet_from_clipboard, "NewSheetClipboard.svg",
            tr("New sheet from clipboard"),
            tr("Create a sheet shaped like the picture of the clipboard (screenshot, "
               "copied image), with the picture on it, and open the drawing board"))),
        ("Croquis_Capture3D", _Command(
            capture_3d_view, "Capture3D.svg", tr("Capture 3D view"),
            tr("Picture of the 3D view on a sheet, to draw, arrow and write on it"))),
        ("Croquis_SheetOnFace", _Command(
            sheet_on_face, "SheetOnFace.svg", tr("Sketch on a face"),
            tr("Click a face of the model (or select it first): a transparent sheet is laid "
               "on it, framed and facing out, to annotate it"))),
        ("Croquis_InsertImage", _Command(
            insert_image, "InsertImage.svg", tr("Insert image…"),
            tr("Put a picture file on the selected sheet"), needs=_one_sheet)),
        ("Croquis_ExportPdf", _Command(
            export_pdf, "ExportPdf.svg", tr("Export sheets as PDF"),
            tr("Save the selected sheets as one PDF, a page per sheet (lines, splines, "
               "arrows and texts as vectors)"), needs=lambda: bool(selected_sheets()))),
        ("Croquis_ShowPanel", _Command(
            lambda: __import__("freecad.croquis.sheet", fromlist=["x"]).show_panels(),
            "Panel.svg", tr("Show the Croquis panel"),
            tr("Show the side panel of the drawing board (tool options, paper, layers)"),
            needs_document=False)),
        ("Croquis_ExportPng", _Command(
            export_png, "ExportPng.svg", tr("Export sheet as PNG"),
            tr("Save the selected sheet as a PNG image (transparent where the paper is)"),
            needs=_one_sheet)),
    ]
    cmds.append(("Croquis_ToggleSheets", _ToggleSheets()))
    for name, cmd in cmds:
        Gui.addCommand(name, cmd)
    TOOLBAR[:] = [name for name, _c in cmds]
    MENU[:] = list(TOOLBAR)
    TOOLBAR.remove("Croquis_ShowPanel")         # menu only
    CONTEXT[:] = ["Croquis_EditSheet", "Croquis_InsertImage", "Croquis_ExportPng",
                  "Croquis_ExportPdf"]
