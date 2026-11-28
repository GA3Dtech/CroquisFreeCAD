# SPDX-License-Identifier: LGPL-2.1-or-later
"""Live 3D: the image plane follows the board a moment after each change,
without touching the document; saving the document writes the boards."""

import os

import FreeCADGui as Gui
import pytest
from conftest import process, qt
from test_gui import drag

from freecad.croquis import prefs, sheet

pytestmark = pytest.mark.gui


def wait(ms):
    QtCore, _g, _w, _t = qt()
    timer = QtCore.QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        process(1)
        QtCore.QThread.msleep(10)


def red_rows(doc):
    """Mean row of the red pixels of a top view of the document (or None)."""
    _c, QtGui, _w, _t = qt()
    view = Gui.getDocument(doc.Name).mdiViewsOfType("Gui::View3DInventor")[0]
    path = os.path.join(os.environ.get("CROQUIS_OUTPUT", "/tmp"), "live_%s.png" % doc.Name)
    view.saveImage(path, 200, 200, "White")
    img = QtGui.QImage(path)
    rows = [y for y in range(0, img.height(), 2) for x in range(0, img.width(), 2)
            if (lambda c: c.red() > 150 and c.green() < 90 and c.blue() < 90)(
                QtGui.QColor(img.pixel(x, y)))]
    return sum(rows) / float(len(rows)) if rows else None


@pytest.fixture
def board(doc):
    obj = sheet.create_sheet(doc, "A5L", 72, "white", "XY", "Live")
    view = Gui.getDocument(doc.Name).mdiViewsOfType("Gui::View3DInventor")[0]
    view.viewTop()
    view.fitAll()
    yield obj
    prefs.put("LiveUpdate", True)
    sheet.close_all_boards()


def _red_stroke(b):
    c = b.canvas
    c.set_tool("marker")
    c.set_color("#ff0000")
    c.set_opacity(1.0)
    c.set_size(20)
    a, z = c.to_widget((20, 30)), c.to_widget((190, 30))      # upper part of the sheet
    drag(c, [(a.x(), a.y()), ((a.x() + z.x()) / 2, a.y()), (z.x(), z.y())])


def test_3d_follows_the_board(doc, board):
    b = sheet.open_board(board)
    b.window().resize(1200, 800)
    process()
    b.canvas.fit()
    assert red_rows(doc) is None
    _red_stroke(b)
    wait(b.PREVIEW_DELAY_MS + 300)
    y = red_rows(doc)
    assert y is not None and y < 100                 # shown, and not upside down
    assert '"p"' not in board.SheetData or len(sheet.sheet_data(board).strokes) == 0
    b.canvas.undo_stack.undo()                       # undo follows too
    wait(b.PREVIEW_DELAY_MS + 300)
    assert red_rows(doc) is None


def test_live_update_off(doc, board):
    prefs.put("LiveUpdate", False)
    b = sheet.open_board(board)
    b.window().resize(1200, 800)
    process()
    b.canvas.fit()
    _red_stroke(b)
    wait(b.PREVIEW_DELAY_MS + 300)
    assert red_rows(doc) is None


def test_saving_writes_the_boards(doc, board, tmp_path):
    doc.saveAs(str(tmp_path / "live.FCStd"))
    b = sheet.open_board(board)
    b.window().resize(1200, 800)
    process()
    b.canvas.fit()
    _red_stroke(b)
    assert len(sheet.sheet_data(board).strokes) == 0
    doc.save()
    assert len(sheet.sheet_data(board).strokes) == 1
    assert not b.is_modified()


def test_save_as_writes_the_boards(doc, board, tmp_path):
    b = sheet.open_board(board)
    b.window().resize(1200, 800)
    process()
    b.canvas.fit()
    _red_stroke(b)
    path = str(tmp_path / "first.FCStd")
    doc.saveAs(path)                    # first save of a new document
    process()
    assert len(sheet.sheet_data(board).strokes) == 1 and not b.is_modified()
    import shutil

    import FreeCAD as App
    copy = str(tmp_path / "copy.FCStd")            # the file as written on disk
    shutil.copy(path, copy)
    other = App.openDocument(copy)
    try:
        assert len(sheet.sheet_data(other.getObject(board.Name)).strokes) == 1
    finally:
        App.closeDocument(other.Name)


def test_closing_the_board_is_quiet(doc, board):
    """Closing the tab after drawing: no error from the 3D preview once the
    board is gone (its timer is deleted before the undo stack)."""
    import sys
    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda *exc: errors.append(exc)
    try:
        b = sheet.open_board(board)
        process()
        b.canvas.fit()
        _red_stroke(b)
        tab = b.parentWidget()               # the board's MDI sub-window
        while tab is not None and not tab.inherits("QMdiSubWindow"):
            tab = tab.parentWidget()
        tab.close()                          # the tab's close button
        QtCore, _g, _w, _t = qt()
        # the deferred deletion of the tab (processEvents alone skips it)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        process(10)
        wait(600)
    finally:
        sys.excepthook = old_hook
    assert not errors, [str(e[1]) for e in errors]
    assert len(sheet.sheet_data(board).strokes) == 1
