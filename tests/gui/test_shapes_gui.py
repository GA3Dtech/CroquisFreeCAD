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
