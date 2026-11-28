# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pictures on the board (B1): Ctrl+V from the clipboard, drag and drop,
selection, move / resize / rotate with the edit tool, properties panel,
saved with the sheet."""

import FreeCAD as App
import FreeCADGui as Gui
import pytest
from conftest import process, qt
from test_gui import drag, key

from freecad.croquis import api, sheet

pytestmark = pytest.mark.gui


@pytest.fixture
def board(doc):
    obj = sheet.create_sheet(doc, "A5L", 72, "white", "XZ", "Pics")
    b = sheet.open_board(obj)
    b.window().resize(1300, 900)
    process()
    b.canvas.fit()
    return obj, b


def make_image(w=400, h=300, color=(220, 50, 50)):
    _c, QtGui, _w, _t = qt()
    img = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor(*color))
    return img


def test_ctrl_v_pastes_clipboard_picture(board, doc):
    QtCore, _g, QtWidgets, _t = qt()
    obj, b = board
    names = sorted(o.Name for o in doc.Objects)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj.ImagePlane)       # what Std_Paste would duplicate
    QtWidgets.QApplication.clipboard().setImage(make_image())
    tool = b.canvas.tool
    key(b.canvas, QtCore.Qt.Key_V, QtCore.Qt.ControlModifier)
    imgs = b.sheet.images()
    assert len(imgs) == 1 and imgs[0].w / imgs[0].h == pytest.approx(4 / 3)
    assert b.canvas.tool == tool                      # Ctrl+V did not pick the edit tool
    assert sorted(o.Name for o in doc.Objects) == names   # no FreeCAD object pasted
    sheet.close_board(obj)
    stored = api.list_images(obj, doc=doc)
    assert len(stored) == 1 and hasattr(obj, "Image_" + stored[0]["id"])


def test_drop_image_file(board, tmp_path):
    QtCore, QtGui, QtWidgets, _t = qt()
    _obj, b = board
    path = str(tmp_path / "drop.png")
    make_image(200, 400, (20, 20, 200)).save(path)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(path)])
    c = b.canvas
    r = c.sheet_rect_widget()
    pos = QtCore.QPointF(r.x() + r.width() * 0.3, r.y() + r.height() * 0.5)
    # Qt only routes drop events coming from a real drag session: call the
    # handlers the drag manager would call
    enter = QtGui.QDragEnterEvent(pos.toPoint(), QtCore.Qt.CopyAction, mime,
                                  QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    c.dragEnterEvent(enter)
    assert enter.isAccepted()
    ev = QtGui.QDropEvent(pos, QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton,
                          QtCore.Qt.NoModifier)
    c.dropEvent(ev)
    imgs = b.sheet.images()
    assert len(imgs) == 1
    e = imgs[0]
    cx, cy = c.to_mm(pos)
    assert e.x + e.w / 2 == pytest.approx(cx) and e.y + e.h / 2 == pytest.approx(cy)
    assert e.h / e.w == pytest.approx(2)


def test_edit_tool_moves_resizes_rotates_deletes(board):
    QtCore, _g, QtWidgets, _t = qt()
    _obj, b = board
    c = b.canvas
    QtWidgets.QApplication.clipboard().setImage(make_image())
    c.paste()
    e = b.sheet.images()[0]
    c.set_tool("edit")
    process(5)              # pending resize / fit events before taking coordinates
    centre = c.to_widget((e.x + e.w / 2, e.y + e.h / 2))
    drag(c, [(centre.x(), centre.y()), (centre.x() + 40, centre.y() + 20)])
    moved = b.sheet.images()[0]
    assert c.selected_image() is moved
    assert moved.x == pytest.approx(e.x + 40 / (c.scale * c.zoom), abs=0.2)
    assert b.image_panel.isVisible() or b.image_panel.isVisibleTo(b)
    # resize from the bottom right corner, proportions kept
    corner = c.to_widget((moved.x + moved.w, moved.y + moved.h))
    drag(c, [(corner.x(), corner.y()), (corner.x() + 60, corner.y() + 5)])
    big = b.sheet.images()[0]
    assert big.w > moved.w and big.w / big.h == pytest.approx(moved.w / moved.h, rel=1e-3)
    assert big.x == pytest.approx(moved.x, abs=1e-3)      # opposite corner fixed
    # rotate with the round handle
    from freecad.croquis.canvas.tools import image_handles
    _corners, rot, _top = image_handles(big, c.handler._handle_mm())
    h = c.to_widget(rot)
    right = c.to_widget((big.x + big.w + 30, big.y + big.h / 2))
    drag(c, [(h.x(), h.y()), (right.x(), right.y())])
    assert b.sheet.images()[0].rotation == pytest.approx(90, abs=3)
    # properties panel (generic model) changes the picture
    b.image_bridge.setValue("opacity", 40)
    assert b.sheet.images()[0].opacity == pytest.approx(0.4)
    b.image_bridge.setValue("render", False)
    assert b.sheet.images()[0].render is False
    count = c.undo_stack.count()
    key(c, QtCore.Qt.Key_Delete)
    assert b.sheet.images() == [] and c.undo_stack.count() == count + 1
    key(c, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
    assert len(b.sheet.images()) == 1


def test_new_sheet_from_clipboard_command(doc, croquis_wb):
    QtCore, _g, QtWidgets, _t = qt()
    App.setActiveDocument(doc.Name)
    QtWidgets.QApplication.clipboard().setImage(make_image(600, 300))
    Gui.runCommand("Croquis_NewSheetFromClipboard")
    process()
    sheets = api.list_sheets(doc)
    assert len(sheets) == 1
    s = sheets[0]
    assert s["width_mm"] / s["height_mm"] == pytest.approx(2) and s["images"] == 1
    assert sheet.board_of(doc.getObject(s["name"])) is not None
