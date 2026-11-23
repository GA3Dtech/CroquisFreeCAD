# SPDX-License-Identifier: LGPL-2.1-or-later
"""panel_model.py: the single description of a panel (no Qt, no FreeCAD)."""

import json

import pytest

from freecad.croquis.panel_model import KINDS, Action, PanelModel, Param

pytestmark = pytest.mark.unit


def make():
    state = {"n": 1.5, "i": 3, "b": False, "c": "a", "col": "#112233", "v": [0, 0, 0],
             "p": "", "t": "x", "calls": []}

    def field(k):
        return (lambda: state[k]), (lambda value: state.__setitem__(k, value))
    params = [
        Param("n", "Number", "number", *field("n"), section="S1", min=0, max=10, unit="mm"),
        Param("i", "Int", "int", *field("i"), section="S1", min=1, max=5),
        Param("b", "Bool", "bool", *field("b"), section="S2"),
        Param("c", "Choice", "choice", *field("c"), section="S1",
              options=[("a", "A"), ("b", "B")], visible=lambda: state["b"]),
        Param("col", "Colour", "color", *field("col"), section="S2"),
        Param("v", "Vector", "vector", *field("v"), section="S2"),
        Param("p", "Path", "path", *field("p"), section="S2", filter="*.png"),
        Param("t", "Text", "text", *field("t"), section="S2"),
        Param("l", "List", "list", lambda: ["one", "two"], section="S3"),
        Param("note", "", "note", lambda: "hello", section="S3"),
    ]
    actions = [Action("go", "Go", lambda: state["calls"].append("go"), primary=True),
               Action("close", "Close", lambda: "close"),
               Action("boom", "Boom", lambda: 1 / 0)]
    return PanelModel("Title", params, actions, hint=lambda: "hint %s" % state["i"]), state


def test_every_kind_covered():
    m, _s = make()
    assert sorted(set(p.kind for p in m.params)) == sorted(KINDS)


def test_sections_and_public_are_json():
    m, _s = make()
    secs = m.sections()
    assert [s["title"] for s in secs] == ["S1", "S2", "S3"]
    assert [p["name"] for p in secs[0]["params"]] == ["n", "i", "c"]
    json.dumps(secs)
    json.dumps(m.public_actions())
    json.dumps(m.values())
    c = secs[0]["params"][2]
    assert c["options"] == ["a", "b"] and c["optionLabels"] == ["A", "B"]
    assert secs[2]["params"][0]["readonly"] is True


def test_set_coerces_and_checks_limits():
    m, s = make()
    assert m.set("n", "2.5") and s["n"] == 2.5
    assert m.set("i", 4.6) and s["i"] == 5
    assert not m.set("i", 9) and "outside" in m.error and s["i"] == 5
    assert m.set("b", 1) and s["b"] is True
    assert not m.set("c", "z") and s["c"] == "a"
    assert m.set("c", "b") and s["c"] == "b"
    assert not m.set("col", "red")
    assert m.set("v", ["1", 2, 3.5]) and s["v"] == [1.0, 2.0, 3.5]
    assert not m.set("v", [1, 2])
    assert not m.set("n", "abc")
    assert not m.set("l", ["x"]) and "read-only" in m.error
    assert m.set("t", 42) and s["t"] == "42" and m.error == ""


def test_hidden_and_hint_follow_state():
    m, s = make()
    assert m.hidden() == ["c"]
    s["b"] = True
    assert m.hidden() == []
    assert m.hint_text() == "hint 3"
    assert PanelModel("x", [], hint="static").hint_text() == "static"


def test_actions():
    m, s = make()
    assert m.trigger("go") is None and s["calls"] == ["go"]
    assert m.trigger("close") == "close"
    assert m.trigger("boom") is None and "division" in m.error
    with pytest.raises(KeyError):
        m.trigger("nope")


def test_bad_definitions():
    with pytest.raises(ValueError):
        Param("x", "X", "slider", lambda: 0)
    with pytest.raises(ValueError):
        PanelModel("dup", [Param("a", "A", "bool", lambda: 0)],
                   [Action("a", "A", lambda: None)])


def test_failing_getter_does_not_break_values():
    m = PanelModel("t", [Param("x", "X", "number", lambda: 1 / 0)])
    assert m.values() == {"x": None} and m.error
