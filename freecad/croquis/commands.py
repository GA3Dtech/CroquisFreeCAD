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
class NewSheetDialog(object):
    """Format, resolution, paper and plane of a new sheet (defaults from
    the preferences, remembered for next time)."""

    def __init__(self):
        from .qt import QtWidgets
        from . import prefs
        self.dialog = d = QtWidgets.QDialog(Gui.getMainWindow())
        d.setWindowTitle(tr("New sketch sheet"))
        form = QtWidgets.QFormLayout(d)
        self.name = QtWidgets.QLineEdit(tr("Sketch"))
        form.addRow(tr("Name:"), self.name)
        self.fmt = QtWidgets.QComboBox()
        self.dpi = QtWidgets.QComboBox()
        self.paper = QtWidgets.QComboBox()
        self.plane = QtWidgets.QComboBox()
        prefs.fill_sheet_combos(self.fmt, self.dpi, self.paper, self.plane)
        prefs.select_data(self.fmt, prefs.get("SheetFormat"))
        prefs.select_data(self.dpi, prefs.get("SheetDpi"))
        prefs.select_data(self.paper, prefs.get("SheetPaper"))
        prefs.select_data(self.plane, prefs.get("SheetPlane"))
        form.addRow(tr("Format:"), self.fmt)
        form.addRow(tr("Resolution:"), self.dpi)
        form.addRow(tr("Paper:"), self.paper)
        form.addRow(tr("Image plane:"), self.plane)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        form.addRow(buttons)

    def run(self):
        """dict of the choices, or None when cancelled."""
        from . import prefs
        run = getattr(self.dialog, "exec", None) or self.dialog.exec_
        if not run():
            return None
        res = {"label": self.name.text().strip() or tr("Sketch"),
               "fmt": self.fmt.currentData(), "dpi": self.dpi.currentData(),
               "paper": self.paper.currentData(), "plane": self.plane.currentData()}
        prefs.put("SheetFormat", res["fmt"])
        prefs.put("SheetDpi", res["dpi"])
        prefs.put("SheetPaper", res["paper"])
        prefs.put("SheetPlane", res["plane"])
        return res


def new_sheet():
    from . import sheet
    choice = NewSheetDialog().run()
    if choice is None:
        return
    doc = App.ActiveDocument
    doc.openTransaction(tr("New sketch sheet"))
    try:
        obj = sheet.create_sheet(doc, choice["fmt"], choice["dpi"], choice["paper"],
                                 choice["plane"], choice["label"])
    finally:
        doc.commitTransaction()
    doc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    sheet.open_board(obj)


def edit_sheet():
    from . import sheet
    for obj in selected_sheets():
        sheet.open_board(obj)


def export_png():
    from . import sheet
    from .canvas.view import export_png_dialog
    import os
    obj = selected_sheets()[0]
    folder = os.path.dirname(obj.Document.FileName) if obj.Document.FileName \
        else os.path.expanduser("~")
    path = export_png_dialog(Gui.getMainWindow(), sheet.sheet_data(obj),
                             os.path.join(folder, obj.Label + ".png"))
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
        ("Croquis_ExportPng", _Command(
            export_png, "ExportPng.svg", tr("Export sheet as PNG"),
            tr("Save the selected sheet as a PNG image (transparent where the paper is)"),
            needs=_one_sheet)),
    ]
    for name, cmd in cmds:
        Gui.addCommand(name, cmd)
    TOOLBAR[:] = [name for name, _c in cmds]
    MENU[:] = list(TOOLBAR)
    CONTEXT[:] = ["Croquis_EditSheet", "Croquis_ExportPng"]
