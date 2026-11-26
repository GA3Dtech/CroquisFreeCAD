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
             ("line", "L"), ("spline", "S"), ("arrow", "A"), ("eraser", "E")]


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


def test_arrow_options(board):
    _obj, b = board
    c = b.canvas
    c.set_tool("arrow")
    hidden = set(b.options_bridge.hidden)
    assert {"arrow_mode", "head_end", "head_style"}.isdisjoint(hidden)
    assert "peak" in hidden
    b.options_bridge.setValue("head_style", "dot")
    b.options_bridge.setValue("arrow_mode", "freehand")
    w = c.sheet_rect_widget()
    drag(c, [(w.x() + 60 + 8 * i, w.y() + 80 + 3 * i) for i in range(25)])
    s = c.sheet.strokes[-1]
    assert s.tool == "arrow" and s.profile()["head_style"] == "dot"
    assert len(s.points) >= 4                     # fitted Bezier chain


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


def test_scale_tool(board, monkeypatch):
    QtCore, _g, QtWidgets, _t = qt()
    obj, b = board
    c = b.canvas
    key(c, QtCore.Qt.Key_K)
    assert c.tool == "scale"
    asked = []

    def fake(parent, title, label, value, lo, hi, dec):
        asked.append(value)
        return 100.0, True
    monkeypatch.setattr(QtWidgets.QInputDialog, "getDouble", fake)
    a, z = c.to_widget((20, 50)), c.to_widget((70, 50))     # 50 mm on the sheet
    drag(c, [(a.x(), a.y()), (z.x(), z.y())])
    assert len(asked) == 1 and asked[0] == pytest.approx(50, abs=0.5), asked
    assert c.sheet.plane_scale == pytest.approx(2.0, rel=0.02)
    assert "1:2" in b.status.text()
    sheet.close_board(obj)
    assert obj.Scale == pytest.approx(2.0, rel=0.02)
    assert obj.ImagePlane.XSize.Value == pytest.approx(210 * obj.Scale)


def test_manual_plane_scale_survives_board_update(board):
    from freecad.croquis.canvas import undo
    obj, b = board
    sheet.close_board(obj)
    obj.ImagePlane.XSize = obj.ImagePlane.XSize.Value * 3     # scaled by hand in 3D
    obj.ImagePlane.YSize = obj.ImagePlane.YSize.Value * 3
    b = sheet.open_board(obj)
    c = b.canvas
    c.undo_stack.push(undo.AddStroke(c, model.Stroke("marker", "#555555", 6, 0.5, "marker",
                                                     [(20, 20, 1), (180, 120, 1)])))
    sheet.close_board(obj)                                    # update
    assert obj.Scale == pytest.approx(3.0)
    assert obj.ImagePlane.XSize.Value == pytest.approx(210 * 3)


def test_side_panel_cannot_get_lost(board):
    obj, b = board
    total = sum(b.split.sizes())
    b.split.moveSplitter(total, 1)                 # drag the handle to the edge
    process()
    assert b.split.sizes()[1] >= b.side.minimumWidth() and b.side.isVisibleTo(b)
    b.panel_action.trigger()                        # hide with the button
    assert not b.side.isVisibleTo(b)
    Gui.runCommand("Croquis_ShowPanel")            # menu command brings it back
    process()
    assert b.side.isVisibleTo(b) and b.panel_action.isChecked()
    b.set_panel_visible(False)
    sheet.open_board(obj)                           # editing again shows it
    assert b.side.isVisibleTo(b)


def test_toggle_sheets_command(doc, croquis_wb):
    App.setActiveDocument(doc.Name)
    a = api.create_sheet(doc, "A5L", 72, "white", "XY")
    api.create_sheet(doc, "A5L", 72, "white", "XZ")
    cmd = Gui.Command.get("Croquis_ToggleSheets")
    assert cmd.getInfo()["shortcut"] == "C, V"
    Gui.runCommand("Croquis_ToggleSheets")
    process()
    assert api.sheets_visible(doc) is False
    assert not doc.getObject(a["image_plane"]).ViewObject.Visibility
    assert not cmd.getAction()[0].isChecked()               # icon shows the state
    Gui.runCommand("Croquis_ToggleSheets")
    assert api.sheets_visible(doc) is True and cmd.getAction()[0].isChecked()


def test_sheet_fitted_until_the_user_zooms(board):
    _obj, b = board
    c = b.canvas

    def fits():
        r = c.sheet_rect_widget()
        return r.left() >= 0 and r.top() >= 0 and r.right() <= c.width() + 1 and \
            r.bottom() <= c.height() + 1 and (r.width() > c.width() - 60 or
                                              r.height() > c.height() - 60)
    for size in ((900, 600), (1400, 1000), (700, 900)):
        b.window().resize(*size)
        process()
        assert fits(), size
    c.set_zoom(c.zoom * 2)                          # the user zooms: no more auto fit
    zoom = c.zoom
    b.window().resize(1000, 700)
    process()
    assert c.zoom == zoom
    c.fit()                                         # F still fits
    assert fits()
