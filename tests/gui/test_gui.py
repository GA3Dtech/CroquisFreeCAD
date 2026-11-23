# SPDX-License-Identifier: LGPL-2.1-or-later
"""Workbench, commands, board and its keyboard guards in the FreeCAD GUI."""

import math
import os

import FreeCAD as App
import FreeCADGui as Gui
import pytest
from conftest import process, qt

from freecad.croquis import api, model, qml_host, sheet

pytestmark = pytest.mark.gui

COMMANDS = ["Croquis_NewSheet", "Croquis_EditSheet", "Croquis_ExportPng"]


def board_of(obj):
    sub = sheet._boards.get(sheet._key(obj))
    return sub.widget() if sub is not None else None


def new_sheet(doc, monkeypatch, **choice):
    c = {"label": "Gui", "format": "A5L", "dpi": "72", "paper": "white", "plane": "XZ"}
    c.update(choice)

    def fake_dialog(m, doc=None, parent=None):     # the user fills the panel, OK
        for name, value in c.items():
            assert m.set(name, value), m.error
        return m.accept()
    monkeypatch.setattr(qml_host, "run_dialog", fake_dialog)
    App.setActiveDocument(doc.Name)
    Gui.runCommand("Croquis_NewSheet")
    process()
    obj = [o for o in doc.Objects if sheet.is_sheet(o)][-1]
    return obj


# ----------------------------------------------------------------------
#  Workbench and commands
# ----------------------------------------------------------------------
def test_workbench_and_commands(croquis_wb):
    assert Gui.activeWorkbench().name() == "CroquisWorkbench"
    names = Gui.listCommands()
    for name in COMMANDS:
        assert name in names
        res = Gui.Command.get(name).getInfo()
        assert os.path.isfile(res["pixmap"]), res


def test_new_edit_double_click(doc, croquis_wb, monkeypatch):
    obj = new_sheet(doc, monkeypatch)
    board = board_of(obj)
    assert board is not None and obj.ImagePlane is not None
    sheet.close_board(obj)
    assert board_of(obj) is None
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    Gui.runCommand("Croquis_EditSheet")
    process()
    assert board_of(obj) is not None
    sheet.close_board(obj)
    obj.ViewObject.Proxy.doubleClicked(obj.ViewObject)
    assert board_of(obj) is not None


def test_leaving_workbench_saves_and_closes(doc, croquis_wb, monkeypatch):
    from freecad.croquis.canvas import undo
    obj = new_sheet(doc, monkeypatch)
    c = board_of(obj).canvas
    c.undo_stack.push(undo.AddStroke(c, model.Stroke(
        "marker", "#555555", 6, 0.5, "marker", [(20, 20, 1), (180, 120, 1)])))
    Gui.activateWorkbench("PartWorkbench")
    process()
    assert not sheet._boards
    assert api.get_sheet(obj, doc=doc)["strokes"] == 1


# ----------------------------------------------------------------------
#  Board: tools with synthetic mouse events
# ----------------------------------------------------------------------
def mouse(canvas, kind, x, y, buttons, button=None, mods=None):
    QtCore, QtGui, QtWidgets, _t = qt()
    L = QtCore.Qt.LeftButton
    ev = QtGui.QMouseEvent(kind, QtCore.QPointF(x, y), QtCore.QPointF(x, y),
                           button if button is not None else QtCore.Qt.NoButton,
                           buttons, mods if mods is not None else QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(canvas, ev)
    return L


def drag(canvas, pts):
    QtCore, _g, _w, _t = qt()
    L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
    E = QtCore.QEvent
    mouse(canvas, E.MouseButtonPress, *pts[0], L, L)
    for p in pts[1:]:
        mouse(canvas, E.MouseMove, *p, L)
    mouse(canvas, E.MouseButtonRelease, *pts[-1], N, L)


def key(widget, k, mods=None):
    """Through QTest, so FreeCAD's shortcut map sees the key first."""
    QtCore, _g, QtWidgets, QtTest = qt()
    widget.activateWindow()
    widget.setFocus()
    process()
    QtTest.QTest.keyClick(widget, k, mods if mods is not None else QtCore.Qt.NoModifier)
    process()


@pytest.fixture
def board(doc, croquis_wb, monkeypatch):
    obj = new_sheet(doc, monkeypatch)
    b = board_of(obj)
    b.window().resize(1300, 900)
    process()
    b.canvas.fit()
    return obj, b


TOOL_KEYS = [("pencil", "P"), ("grease", "G"), ("marker", "M"), ("highlight", "W"),
             ("line", "L"), ("spline", "S"), ("eraser", "E")]


@pytest.mark.parametrize("tool,letter", TOOL_KEYS)
def test_each_tool_draws_its_stroke(board, tool, letter):
    QtCore, _g, _w, _t = qt()
    _obj, b = board
    c = b.canvas
    c.set_tool("edit")
    key(c, getattr(QtCore.Qt, "Key_" + letter))
    assert c.tool == tool
    w = c.sheet_rect_widget()
    pts = [(w.x() + w.width() * (0.2 + 0.6 * i / 30),
            w.y() + w.height() * (0.5 + 0.2 * math.sin(i / 5))) for i in range(31)]
    before = len(c.sheet.strokes)
    drag(c, pts)
    assert len(c.sheet.strokes) == before + 1
    assert c.sheet.strokes[-1].tool == tool


def test_undo_redo_keys(board):
    QtCore, _g, _w, _t = qt()
    _obj, b = board
    c = b.canvas
    w = c.sheet_rect_widget()
    drag(c, [(w.x() + 50, w.y() + 50), (w.x() + 200, w.y() + 90)])
    assert len(c.sheet.strokes) == 1
    key(c, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
    assert len(c.sheet.strokes) == 0
    key(c, QtCore.Qt.Key_Y, QtCore.Qt.ControlModifier)
    assert len(c.sheet.strokes) == 1


def test_delete_on_board_keeps_document_objects(board, doc):
    QtCore, _g, _w, _t = qt()
    obj, b = board
    names = sorted(o.Name for o in doc.Objects)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    Gui.Selection.addSelection(obj.ImagePlane)
    for k in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
        key(b.canvas, k)
    assert sorted(o.Name for o in doc.Objects) == names


def test_copy_paste_on_board_keep_document_objects(board, doc):
    QtCore, _g, QtWidgets, _t = qt()
    obj, b = board
    names = sorted(o.Name for o in doc.Objects)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj.ImagePlane)
    QtWidgets.QApplication.clipboard().clear()
    key(b.canvas, QtCore.Qt.Key_C, QtCore.Qt.ControlModifier)
    key(b.canvas, QtCore.Qt.Key_V, QtCore.Qt.ControlModifier)
    assert sorted(o.Name for o in doc.Objects) == names
    assert b.canvas.tool == "pencil"        # Ctrl+V does not pick the edit tool
    img = QtWidgets.QApplication.clipboard().image()
    assert not img.isNull() and img.width() == b.canvas.compositor.w
