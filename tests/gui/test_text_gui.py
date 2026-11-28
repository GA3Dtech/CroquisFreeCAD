# SPDX-License-Identifier: LGPL-2.1-or-later
"""Text boxes on the board (B6): typing keeps every key, Escape validates,
double-click edits, panel settings, callout tip stays when the box moves."""

import FreeCADGui as Gui
import pytest
from conftest import process, qt
from test_gui import drag, key

from freecad.croquis import api, sheet

pytestmark = pytest.mark.gui


@pytest.fixture
def board(doc):
    obj = sheet.create_sheet(doc, "A5L", 72, "white", "XZ", "Txt")
    b = sheet.open_board(obj)
    b.window().resize(1300, 900)
    process()
    b.canvas.fit()
    return obj, b


def click(c, x, y):
    QtCore, _g, _w, _t = qt()
    L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
    from test_gui import mouse
    mouse(c, QtCore.QEvent.MouseButtonPress, x, y, L, L)
    mouse(c, QtCore.QEvent.MouseButtonRelease, x, y, N, L)


def test_typing_keeps_keys_and_escape_validates(board, doc):
    QtCore, _g, QtWidgets, QtTest = qt()
    obj, b = board
    c = b.canvas
    key(c, QtCore.Qt.Key_T)
    assert c.tool == "text" and b.text_panel.isVisibleTo(b)
    process(10)             # the text panel (QML) finishes loading before typing
    p = c.to_widget((30, 40))
    names = sorted(o.Name for o in doc.Objects)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    # FreeCAD 1.1 may activate the new document's 3D view tab late, after
    # the board: bring the board forward again before typing
    process(10)
    sheet.open_board(obj)
    process(10)
    click(c, p.x(), p.y())
    ed = c.editor
    # the focus widget of its window (hasFocus() is False while the test
    # window is momentarily inactive)
    assert ed is not None and ed.window().focusWidget() is ed
    QtTest.QTest.keyClicks(ed, "pvme")                      # tool letters
    for k in (QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Delete, QtCore.Qt.Key_1):
        QtTest.QTest.keyClick(ed, k)
    QtTest.QTest.keyClick(ed, QtCore.Qt.Key_Return)
    QtTest.QTest.keyClicks(ed, "ok")
    process()
    assert c.tool == "text"                                 # no tool change
    assert sorted(o.Name for o in doc.Objects) == names     # Delete deleted nothing
    assert c.editor is ed
    QtTest.QTest.keyClick(ed, QtCore.Qt.Key_Escape)
    process()
    assert c.editor is None
    texts = b.sheet.texts()
    assert len(texts) == 1 and texts[0].text == "pvm1\nok"
    assert texts[0].x == pytest.approx(30, abs=0.5) and texts[0].h > 0
    sheet.close_board(obj)
    assert api.list_texts(obj, doc=doc)[0]["text"] == "pvm1\nok"


def test_double_click_edits_and_panel(board):
    QtCore, _g, _w, QtTest = qt()
    _obj, b = board
    c = b.canvas
    c.set_tool("text")
    b.text_bridge.setValue("size", 8)
    b.text_bridge.setValue("bold", True)
    p = c.to_widget((40, 30))
    click(c, p.x(), p.y())
    QtTest.QTest.keyClicks(c.editor, "Hi")
    c.commit_text()
    e = b.sheet.texts()[0]
    assert e.size == 8 and e.bold
    c.set_tool("edit")
    centre = c.to_widget((e.x + e.width / 2, e.y + e.h / 2))
    ev = __import__("PySide").QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonDblClick, centre, centre, QtCore.Qt.LeftButton,
        QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    c.mouseDoubleClickEvent(ev)
    assert c.editor is not None and c.editor.toPlainText() == "Hi"
    QtTest.QTest.keyClick(c.editor, QtCore.Qt.Key_End)
    QtTest.QTest.keyClicks(c.editor, "!")
    c.commit_text()
    assert b.sheet.texts()[0].text == "Hi!"


def test_callout_tip_stays_when_box_moves(board):
    QtCore, _g, _w, QtTest = qt()
    _obj, b = board
    c = b.canvas
    c.set_tool("text")
    b.text_bridge.setValue("leader", True)
    p = c.to_widget((80, 40))
    click(c, p.x(), p.y())
    QtTest.QTest.keyClicks(c.editor, "Callout")
    c.commit_text()
    e = b.sheet.texts()[0]
    tip = list(e.leader)
    c.set_tool("edit")
    centre = c.to_widget((e.x + e.width / 2, e.y + e.h / 2))
    drag(c, [(centre.x(), centre.y()), (centre.x() + 50, centre.y() + 30)])
    moved = b.sheet.texts()[0]
    assert moved.x > e.x and moved.leader == tip
    assert c.selected_text() is moved
    b.text_bridge.setValue("italic", True)                   # panel edits the selection
    assert b.sheet.texts()[0].italic


def test_editor_survives_switching_window(board):
    """Another application activated while typing: the text box stays open;
    focus moved elsewhere on FreeCAD validates it."""
    QtCore, QtGui, QtWidgets, QtTest = qt()
    _obj, b = board
    c = b.canvas
    key(c, QtCore.Qt.Key_T)
    p = c.to_widget((30, 40))
    click(c, p.x(), p.y())
    ed = c.editor
    QtTest.QTest.keyClicks(ed, "abc")
    for reason in (QtCore.Qt.ActiveWindowFocusReason, QtCore.Qt.OtherFocusReason,
                   QtCore.Qt.PopupFocusReason):
        QtWidgets.QApplication.sendEvent(ed, QtGui.QFocusEvent(QtCore.QEvent.FocusOut, reason))
        process()
        assert c.editor is ed
    QtWidgets.QApplication.sendEvent(
        ed, QtGui.QFocusEvent(QtCore.QEvent.FocusOut, QtCore.Qt.MouseFocusReason))
    process()
    assert c.editor is None and b.sheet.texts()[-1].text == "abc"


def test_text_being_typed_kept_on_close(board, doc):
    QtCore, _g, _w, QtTest = qt()
    obj, b = board
    c = b.canvas
    key(c, QtCore.Qt.Key_T)
    p = c.to_widget((30, 40))
    click(c, p.x(), p.y())
    QtTest.QTest.keyClicks(c.editor, "unfinished")
    sheet.close_board(obj)
    process()
    assert [t["text"] for t in api.list_texts(obj, doc=doc)] == ["unfinished"]
