# SPDX-License-Identifier: LGPL-2.1-or-later
"""Styled shapes (circle, ellipse, rectangle, arc): one drop-down button,
drawn with the last drawing tool, undo, erasers, export."""

import pytest
from conftest import process, qt
from test_gui import drag, key

from freecad.croquis import api, sheet
from freecad.croquis.render import compositor

pytestmark = pytest.mark.gui


@pytest.fixture
def board(doc):
    obj = sheet.create_sheet(doc, "A5L", 72, "white", "XZ", "Shapes")
    b = sheet.open_board(obj)
    b.window().resize(1300, 900)
    process()
    b.canvas.fit()
    return obj, b


@pytest.mark.parametrize("kind", ["circle", "ellipse", "rect", "arc"])
@pytest.mark.parametrize("brush", ["marker", "spline"])
def test_each_shape(board, kind, brush):
    QtCore, _g, _w, _t = qt()
    obj, b = board
    c = b.canvas
    c.set_tool(brush)                                  # the last drawing tool
    b.choose_shape(kind)
    assert c.tool == "shape" and b.canvas.tool_settings["shape"]["kind"] == kind
    a, z = c.to_widget((40, 30)), c.to_widget((120, 100))
    drag(c, [(a.x(), a.y()), ((a.x() + z.x()) / 2, (a.y() + z.y()) / 2), (z.x(), z.y())])
    s = c.sheet.strokes[-1]
    assert s.tool == brush and len(c.sheet.strokes) == 1
    xs = [p[0] for p in s.points]
    assert min(xs) < 45 and max(xs) > 115 if kind != "arc" else max(xs) > 115
    img = compositor.render_sheet(c.sheet)              # exported like any stroke
    assert img.pixelColor(img.width() // 2, img.height() // 2).isValid()
    key(c, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)  # undo
    assert c.sheet.strokes == []
    key(c, QtCore.Qt.Key_Y, QtCore.Qt.ControlModifier)
    assert len(c.sheet.strokes) == 1


def test_shift_escape_and_menu_memory(board):
    QtCore, _g, _w, _t = qt()
    obj, b = board
    c = b.canvas
    b.choose_shape("rect")
    c.set_tool("pencil")
    key(c, QtCore.Qt.Key_O)                              # the shape key reuses the last shape
    assert c.tool == "shape" and c.tool_settings["shape"]["kind"] == "rect"
    c.tool_settings["shape"]["hand"] = False
    a, z = c.to_widget((20, 20)), c.to_widget((80, 50))
    from test_gui import mouse
    L, N, E = QtCore.Qt.LeftButton, QtCore.Qt.NoButton, QtCore.QEvent
    mouse(c, E.MouseButtonPress, a.x(), a.y(), L, L)
    mouse(c, E.MouseMove, z.x(), z.y(), L, mods=QtCore.Qt.ShiftModifier)
    mouse(c, E.MouseButtonRelease, z.x(), z.y(), N, L, mods=QtCore.Qt.ShiftModifier)
    s = c.sheet.strokes[-1]
    xs, ys = [p[0] for p in s.points], [p[1] for p in s.points]
    assert max(xs) - min(xs) == pytest.approx(max(ys) - min(ys), abs=0.6)   # square
    n = len(c.sheet.strokes)
    mouse(c, E.MouseButtonPress, a.x(), a.y(), L, L)
    mouse(c, E.MouseMove, z.x(), z.y(), L)
    key(c, QtCore.Qt.Key_Escape)                         # cancel
    mouse(c, E.MouseButtonRelease, z.x(), z.y(), N, L)
    assert len(c.sheet.strokes) == n
    c.handler_eraser = None
    b.canvas.set_tool("eraser")
    b.options_bridge.setValue("eraser_mode", "strokes")
    edge = c.to_widget((s.points[0][0], s.points[0][1]))
    drag(c, [(edge.x() - 2, edge.y()), (edge.x() + 2, edge.y())])
    assert len(c.sheet.strokes) == n - 1                 # whole-stroke eraser removes it
    sheet.close_board(obj)
    assert api.get_sheet(obj, doc=obj.Document)["strokes"] == n - 1


def test_shape_after_arrow_has_no_heads(board):
    _obj, b = board
    c = b.canvas
    c.set_tool("arrow")
    b.choose_shape("rect")
    a, z = c.to_widget((30, 30)), c.to_widget((100, 80))
    drag(c, [(a.x(), a.y()), (z.x(), z.y())])
    s = c.sheet.strokes[-1]
    assert s.tool == "line" and "head_end" not in s.params
    assert s.params["shape"]["kind"] == "rect"
    assert s.color == c.tool_settings["arrow"]["color"]


@pytest.mark.parametrize("brush", ["marker", "pencil", "spline"])
def test_edit_tool_reshapes_shapes(board, brush):
    QtCore, _g, _w, _t = qt()
    _obj, b = board
    c = b.canvas
    c.set_tool(brush)
    b.choose_shape("rect")
    c.tool_settings["shape"]["hand"] = False
    a, z = c.to_widget((30, 30)), c.to_widget((90, 70))
    drag(c, [(a.x(), a.y()), (z.x(), z.y())])
    rect = c.sheet.strokes[-1]
    c.set_tool("edit")
    edge = c.to_widget((60, 30))                         # click the top side
    drag(c, [(edge.x(), edge.y()), (edge.x(), edge.y())])
    assert c.selection() is rect
    corner = c.to_widget((90, 70))                       # drag the bottom right corner
    target = c.to_widget((130, 100))
    drag(c, [(corner.x(), corner.y()), (target.x(), target.y())])
    big = c.sheet.strokes[-1]
    sh = big.params["shape"]
    assert big is not rect and big.tool == brush
    assert (min(sh["x0"], sh["x1"]), max(sh["x0"], sh["x1"])) == pytest.approx((30, 130), abs=0.5)
    xs = [p[0] for p in big.points]
    assert max(xs) == pytest.approx(130, abs=0.6)
    mid = c.to_widget((80, 30))                          # move the whole shape
    drag(c, [(mid.x(), mid.y()), (mid.x() + 40, mid.y())])
    moved = c.sheet.strokes[-1].params["shape"]
    assert min(moved["x0"], moved["x1"]) > 35
    key(c, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
    key(c, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
    assert c.sheet.strokes[-1].params["shape"] == rect.params["shape"]


def test_arc_ends_editable(board):
    _obj, b = board
    c = b.canvas
    c.set_tool("grease")
    b.choose_shape("arc")
    a, z = c.to_widget((30, 80)), c.to_widget((110, 80))
    drag(c, [(a.x(), a.y()), (z.x(), z.y())])
    c.set_tool("edit")
    top = c.to_widget((70, 80 - 80 / 3))                 # the bulge of the arc
    drag(c, [(top.x(), top.y()), (top.x(), top.y())])
    end = c.to_widget((110, 80))
    new_end = c.to_widget((150, 60))
    drag(c, [(end.x(), end.y()), (new_end.x(), new_end.y())])
    sh = c.sheet.strokes[-1].params["shape"]
    assert (sh["x1"], sh["y1"]) == pytest.approx((150, 60), abs=0.5)
    assert (sh["x0"], sh["y0"]) == pytest.approx((30, 80), abs=0.5)


def test_arc_radius_editable(board):
    _obj, b = board
    c = b.canvas
    c.set_tool("spline")
    b.choose_shape("arc")
    c.tool_settings["shape"]["hand"] = False
    a, z = c.to_widget((30, 80)), c.to_widget((110, 80))
    drag(c, [(a.x(), a.y()), (z.x(), z.y())])
    c.set_tool("edit")
    top = c.to_widget((70, 80 - 80 / 3))                 # click the arc
    drag(c, [(top.x(), top.y()), (top.x(), top.y())])
    deeper = c.to_widget((70, 40))                       # drag its top handle up
    drag(c, [(top.x(), top.y()), (deeper.x(), deeper.y())])
    s = c.sheet.strokes[-1]
    sh = s.params["shape"]
    assert sh["sag"] == pytest.approx(0.5, abs=0.02)     # 40 mm bulge on an 80 mm chord
    assert (sh["x0"], sh["x1"]) == pytest.approx((30, 110), abs=0.5)    # ends kept
    assert min(p[1] for p in s.points) == pytest.approx(40, abs=1.5)


def test_sheet_resized_from_the_board(board):
    from freecad.croquis import panels
    obj, b = board
    c = b.canvas
    c.set_tool("spline")
    b.choose_shape("rect")
    c.tool_settings["shape"]["hand"] = False
    a, z = c.to_widget((30, 40)), c.to_widget((90, 80))
    drag(c, [(a.x(), a.y()), (z.x(), z.y())])           # not applied yet: written on resize
    m = panels.resize_model(b)
    assert m.set("left", 40) and m.set("bottom", 25)
    assert "250 x 173" in m.hint_text()
    assert m.accept() and m.margins["left"] == 40
    m2 = panels.resize_model(b)
    m2.set("left", -205)
    assert not m2.accept() and m2.error
    b2 = sheet.resize_from_board(obj.Document, obj.Name, m.margins)
    process()
    assert b2 is not b and b2.sheet.width == 250 and b2.sheet.height == 173
    shape = b2.sheet.strokes[-1].params["shape"]
    assert (shape["x0"], shape["y0"]) == pytest.approx((70, 40), abs=0.5)
    assert api.get_sheet(obj.Name, doc=obj.Document)["width_mm"] == 250
    sheet.close_board(obj)
