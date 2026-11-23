# SPDX-License-Identifier: LGPL-2.1-or-later
"""Generic panels in the GUI: every QML file loads without error or
warning, QML and widget fallback show the same parameters and actions,
OK / Cancel and transactions, keys typed in a panel field stay there."""

import glob
import os

import FreeCAD as App
import FreeCADGui as Gui
import pytest
from conftest import process, qt

from freecad.croquis import model, panels, qml_host, sheet
from freecad.croquis.bridge import Bridge, I18n, LayersBridge, WidgetForm
from freecad.croquis.panel_model import Action, PanelModel, Param

pytestmark = pytest.mark.gui

QML_FILES = sorted(glob.glob(os.path.join(qml_host.QML_DIR, "*.qml")))


def every_kind_model():
    v = {"n": 1.0, "i": 2, "b": True, "c": "a", "col": "#336699", "vec": [1, 2, 3],
         "p": "/tmp/x.png", "t": "text"}

    def f(k):
        return (lambda: v[k]), (lambda x: v.__setitem__(k, x))
    return PanelModel("All kinds", [
        Param("n", "Number", "number", *f("n"), section="A", unit="mm"),
        Param("i", "Int", "int", *f("i"), section="A"),
        Param("b", "Bool", "bool", *f("b"), section="A"),
        Param("c", "Choice", "choice", *f("c"), section="B", options=[("a", "A"), ("b", "B")]),
        Param("col", "Colour", "color", *f("col"), section="B"),
        Param("vec", "Vector", "vector", *f("vec"), section="B"),
        Param("p", "Path", "path", *f("p"), section="C"),
        Param("t", "Text", "text", *f("t"), section="C"),
        Param("l", "List", "list", lambda: ["a", "b"], section="C"),
        Param("note", "Note", "note", lambda: "note", section="C"),
    ], [Action("go", "Go", lambda: None, primary=True)], hint="hint")


@pytest.fixture
def quick():
    if not qml_host.quick_usable():
        pytest.skip("Qt Quick not usable here")
    return qml_host.quick_modules()


@pytest.fixture
def messages():
    QtCore, _g, _w, _t = qt()
    caught = []

    def handler(mode, context, text):
        caught.append(str(text))
    old = QtCore.qInstallMessageHandler(handler)
    yield caught
    QtCore.qInstallMessageHandler(old)


@pytest.mark.parametrize("path", QML_FILES, ids=os.path.basename)
def test_qml_file_loads(path, quick, messages):
    QtCore, _g, _w, _t = qt()
    qml, _q, _qw = quick
    engine = qml.QQmlEngine()
    engine.addImportPath(qml_host.QML_DIR)
    bridge = Bridge(every_kind_model())
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("i18n", I18n(bridge))
    layers = LayersBridge(FakeLayersCanvas(), parent=bridge)     # kept alive by its parent
    engine.rootContext().setContextProperty("layers", layers)
    comp = qml.QQmlComponent(engine, QtCore.QUrl.fromLocalFile(path))
    assert comp.status() == qml.QQmlComponent.Ready, \
        "\n".join(e.toString() for e in comp.errors())
    obj = comp.create()
    assert obj is not None, "\n".join(e.toString() for e in comp.errors())
    process()
    bad = [m for m in messages if "qml" in m.lower() or "TypeError" in m or "ReferenceError" in m]
    assert bad == []
    obj.deleteLater()


class FakeLayersCanvas(object):
    def __init__(self):
        self.sheet = model.SheetData()

    def set_paper(self, key):
        self.sheet.paper = key

    def set_layer(self, key, visible=None, opacity=None):
        if visible is not None:
            self.sheet.layers[key]["visible"] = visible
        if opacity is not None:
            self.sheet.layers[key]["opacity"] = opacity


def test_layers_panel_qml_and_fallback(doc, monkeypatch):
    obj = sheet.create_sheet(doc, "A5L", 72, "white", "XZ", "L")
    b = sheet.open_board(obj)
    process()
    if qml_host.quick_usable():
        assert b.layers_kind == "qml"
        root = b.layers.rootObject()
        for key in model.PANEL_LAYERS:
            assert find_item(root, "layer_" + key) is not None
        for key, _l, _c in model.PAPERS:
            assert find_item(root, "paper_" + key) is not None
        b.layers_bridge.setPaper("kraft")
        b.layers_bridge.setOpacity("marker", 0.25)
        b.layers_bridge.setVisible("lines", False)
        assert b.sheet.paper == "kraft" and b.sheet.layers["marker"]["opacity"] == 0.25
        assert b.sheet.layers["lines"]["visible"] is False and b.is_modified()
    sheet.close_board(obj)
    assert obj.Paper == ("kraft" if qml_host.quick_usable() else "white")
    monkeypatch.setattr(qml_host, "FORCE_WIDGETS", True)
    b = sheet.open_board(obj)
    assert b.layers_kind == "widgets"
    assert b.layers.paper.count() == len(model.PAPERS)


def panel_models(doc, board):
    return {"new_sheet": panels.new_sheet_model(doc),
            "tool_options": panels.tool_options_model(board.canvas),
            "every_kind": every_kind_model()}


@pytest.fixture
def board(doc):
    obj = sheet.create_sheet(doc, "A5L", 72, "white", "XZ", "P")
    b = sheet.open_board(obj)
    process()
    return b


def test_qml_and_widgets_same_content(doc, board, monkeypatch):
    for name, m in panel_models(doc, board).items():
        expected_params = [p.name for p in m.params]
        expected_actions = [a.name for a in m.actions]
        monkeypatch.setattr(qml_host, "FORCE_WIDGETS", True)
        w, b, kind = qml_host.build_panel(m)
        assert kind == "widgets" and isinstance(w, WidgetForm), name
        assert list(w.editors) == expected_params, name
        assert list(w.action_buttons) == expected_actions, name
        monkeypatch.setattr(qml_host, "FORCE_WIDGETS", False)
        if qml_host.quick_usable():
            v, b2, kind = qml_host.build_panel(m)
            assert kind == "qml", name
            names = [p["name"] for s in b2.sections for p in s["params"]]
            assert names == expected_params
            assert [a["name"] for a in b2.actions] == expected_actions
            v.deleteLater()
        w.deleteLater()


def test_board_options_panel_follows_tool(board):
    b = board
    for tool in ("pencil", "marker", "line", "spline", "eraser", "edit"):
        b.canvas.set_tool(tool)
        b.options_bridge.values      # every getter, hidden parameters included
        assert b.options_bridge.error == "", (tool, b.options_bridge.error)
    hidden = set(b.options_bridge.hidden)
    assert "spline_mode" in hidden
    b.canvas.set_tool("spline")
    assert "spline_mode" not in set(b.options_bridge.hidden)


def test_new_sheet_dialog_ok_and_cancel(doc):
    App.setActiveDocument(doc.Name)
    n = len(doc.Objects)
    dlg = qml_host.PanelDialog(panels.new_sheet_model(doc), doc)
    dlg.reject()
    assert len(doc.Objects) == n
    m = panels.new_sheet_model(doc)
    dlg = qml_host.PanelDialog(m, doc)
    dlg.bridge.setValue("format", "SQ")
    dlg.accept()
    assert m.created and m.created["format"] == "SQ"
    assert len(doc.Objects) == n + 2


def test_session_transaction(doc):
    from freecad.croquis import api
    info = api.create_sheet(doc, "A5L", 72, "white", "XY")
    obj = doc.getObject(info["name"])
    before = obj.SheetData

    def set_paper(value):
        data = sheet.sheet_data(obj)
        data.paper = value
        sheet.write(obj, data)
    model = PanelModel("Sheet", [Param("paper", "Paper", "choice", lambda: obj.Paper, set_paper,
                                       options=[("white", "W"), ("kraft", "K")])],
                       transaction="Sheet properties")
    count = doc.UndoCount
    dlg = qml_host.PanelDialog(model, doc)
    dlg.bridge.setValue("paper", "kraft")
    assert obj.Paper == "kraft"
    dlg.reject()                         # Cancel: document unchanged
    assert obj.Paper == "white" and obj.SheetData == before and doc.UndoCount == count
    dlg = qml_host.PanelDialog(model, doc)
    dlg.bridge.setValue("paper", "kraft")
    dlg.bridge.setValue("paper", "white")
    dlg.bridge.setValue("paper", "kraft")
    dlg.accept()                         # OK: one undo step for the session
    assert obj.Paper == "kraft" and doc.UndoCount == count + 1


def find_item(item, name):
    """QML item by objectName in the visual tree (Loader / Repeater items
    are not in the QObject tree, findChild misses them)."""
    for child in item.childItems():
        if child.objectName() == name:
            return child
        found = find_item(child, name)
        if found is not None:
            return found
    return None


def _type_into_field(board, use_widgets, monkeypatch):
    """Focus the 'Widest at' field of the tool options and type in it."""
    QtCore, _g, QtWidgets, QtTest = qt()
    monkeypatch.setattr(qml_host, "FORCE_WIDGETS", use_widgets)
    w, bridge, kind = qml_host.build_panel(panels.tool_options_model(board.canvas),
                                           board.side)
    board.side.layout().insertWidget(0, w)
    board.canvas.set_tool("spline")
    bridge.refresh()
    process()
    if kind == "qml":
        field = find_item(w.rootObject(), "input_peak")
        assert field is not None
        w.setFocus()
        field.forceActiveFocus()
        target = w
    else:
        field = w.editors["peak"][1]
        field.setFocus()
        target = field.lineEdit()
    process()
    for k in (QtCore.Qt.Key_End, QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace,
              QtCore.Qt.Key_P, QtCore.Qt.Key_E, QtCore.Qt.Key_1, QtCore.Qt.Key_V):
        QtTest.QTest.keyClick(target, k)
        process(1)
    text = field.property("text") if kind == "qml" else field.lineEdit().text()
    return kind, text


@pytest.mark.parametrize("use_widgets", [False, True], ids=["qml", "widgets"])
def test_keys_typed_in_a_panel_field_stay_there(doc, board, use_widgets, monkeypatch):
    obj = [o for o in doc.Objects if sheet.is_sheet(o)][0]
    names = sorted(o.Name for o in doc.Objects)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    if not use_widgets and not qml_host.quick_usable():
        pytest.skip("Qt Quick not usable here")
    kind, text = _type_into_field(board, use_widgets, monkeypatch)
    assert kind == ("widgets" if use_widgets else "qml")
    assert board.canvas.tool == "spline"                      # no tool key reached the board
    assert sorted(o.Name for o in doc.Objects) == names       # Delete deleted nothing
    assert text != "45"                                       # the field got the keys
