# SPDX-License-Identifier: LGPL-2.1-or-later
"""Panel models of the workbench (panels.py) without GUI: values, actions,
calls to the API."""

import pytest

from freecad.croquis import api, panels, prefs

pytestmark = pytest.mark.freecad


def test_new_sheet_model_creates_through_api(doc):
    m = panels.new_sheet_model(doc)
    assert [p.name for p in m.params] == ["label", "format", "dpi", "paper", "plane"]
    for name, value in (("label", "Front"), ("format", "A3P"), ("dpi", "72"),
                        ("paper", "kraft"), ("plane", "YZ")):
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


def test_new_sheet_model_reports_errors(doc):
    m = panels.new_sheet_model(doc)
    m.v["format"] = "A9"            # forced past the choice check
    assert not m.accept() and "format" in m.error and m.created is None
