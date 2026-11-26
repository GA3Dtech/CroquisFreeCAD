# SPDX-License-Identifier: LGPL-2.1-or-later
"""Panel models of the workbench (panels.py) without GUI: values, actions,
calls to the API."""

import pytest

from freecad.croquis import api, model, panels, prefs

pytestmark = pytest.mark.freecad


def test_new_sheet_model_creates_through_api(doc):
    m = panels.new_sheet_model(doc)
    assert [p.name for p in m.params] == ["label", "format", "width", "height", "dpi",
                                         "paper", "plane", "background"]
    assert set(m.hidden()) >= {"width", "height"}             # only for a custom size
    for name, value in (("label", "Front"), ("format", "A3P"), ("dpi", "72"),
                        ("paper", "kraft"), ("plane", "YZ"), ("background", "none")):
        assert m.set(name, value), m.error
    assert not m.set("dpi", "73")           # not an option
    count = doc.UndoCount
    assert m.accept()
    info = m.created
    assert info["label"] == "Front" and info["format"] == "A3P" and info["dpi"] == 72
    assert info["paper"] == "kraft" and info["plane"] == "YZ"
    assert api.list_sheets(doc)[0]["name"] == info["name"]
    assert doc.UndoCount == count + 1
    assert prefs.get("SheetFormat") == "A3P" and prefs.get("SheetDpi") == 72


def test_new_sheet_custom_size(doc):
    m = panels.new_sheet_model(doc)
    for name, value in (("format", "custom"), ("width", 640), ("height", 125.5), ("dpi", "72"),
                        ("plane", "XY"), ("background", "none")):
        assert m.set(name, value), m.error
    assert "width" not in m.hidden()
    assert not m.set("width", 2)                              # below the minimum
    assert m.accept(), m.error
    assert (m.created["width_mm"], m.created["height_mm"]) == (640, 125.5)
    assert m.created["format"] == "custom"
    assert panels.new_sheet_model(doc).v["width"] == 640       # remembered


def test_new_sheet_model_reports_errors(doc):
    m = panels.new_sheet_model(doc)
    m.v["format"] = "A9"            # forced past the choice check
    assert not m.accept() and "format" in m.error and m.created is None


class FakeCanvas(object):
    """What tool_options_model needs from SheetCanvas."""

    def __init__(self):
        from freecad.croquis.canvas.view import default_settings
        self.tool_settings = default_settings()
        self.tool = "pencil"
        self.sel = None
        self.calls = []

    def selection(self):
        return self.sel

    def current(self):
        return self.tool_settings["spline" if self.tool == "edit" else self.tool]

    # (the real canvas returns a plain dict too)

    def set_option(self, name, value):
        self.tool_settings[self.tool][name] = value
        self.calls.append(("option", name, value))

    def set_profile(self, name, value):
        self.tool_settings[self.tool][name] = value
        self.calls.append(("profile", name, value))

    def set_param(self, name, value):
        self.tool_settings[self.tool][name] = value
        self.calls.append(("param", name, value))


def test_tool_options_follow_the_tool():
    pytest.importorskip("FreeCAD")
    from freecad.croquis.qt import QtWidgets
    if QtWidgets.QApplication.instance() is None:
        pytest.skip("canvas settings need Qt widgets")
    c = FakeCanvas()
    m = panels.tool_options_model(c)
    assert m.values()["tout"] == 100 and m.error == ""     # raster tool: defaults shown
    vector = ["peak", "tin", "tout"]
    arrow = {"arrow_mode", "head_end", "head_start", "head_style", "head_size",
             "shape_kind", "shape_hand"}             # (shape options hidden too)
    assert set(m.hidden()) == {"spline_mode", "eraser_mode", "eraser_target"} | set(vector) \
        | arrow
    c.tool = "spline"
    assert set(m.hidden()) == {"eraser_mode", "eraser_target"} | arrow
    assert m.set("spline_mode", "points") and c.calls[-1] == ("option", "mode", "points")
    assert m.set("tin", 30) and c.calls[-1] == ("profile", "tin", 0.3)
    assert m.values()["tin"] == 30
    assert "points" in m.hint_text().lower() or "point" in m.hint_text().lower()
    c.tool = "arrow"
    assert set(m.hidden()) == {"spline_mode", "eraser_mode", "eraser_target",
                               "shape_kind", "shape_hand"} | set(vector)
    assert m.set("head_style", "filled") and c.calls[-1] == ("param", "head_style", "filled")
    c.tool = "eraser"
    assert set(m.hidden()) == {"spline_mode"} | set(vector) | arrow
    assert m.set("eraser_target", "marker")
    assert not m.set("eraser_target", "underlay")
    assert c.tool_settings["eraser"]["target"] == "marker"
    c.tool = "edit"
    assert "peak" in m.hidden()
    c.sel = model.Stroke("spline", "#000000", 1, 1, "lines", [(0, 0, 1)] * 4)
    assert "peak" not in m.hidden()
