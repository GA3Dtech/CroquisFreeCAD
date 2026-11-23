# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - panel models
# Copyright (C) 2026 GA3Dtech
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or (at
# your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <https://www.gnu.org/licenses/>.
"""
panel_model.py (Croquis) - the single description of a panel, from which
bridge.py builds BOTH user interfaces: the QML form (resources/qml) and the
widget fallback (WidgetForm). A panel is never written twice by hand: when
the generic engine cannot show something, add a parameter kind here and in
the engine, not a hand-made panel.

Pure Python, testable without FreeCAD or Qt. The model calls api.py (or
the model functions it uses); no business logic lives in the QML, the
widgets or the bridge.

    PanelModel(title, params, actions, icon=None, transaction=None)
    Param(name, label, kind, get, set=None, section="", **limits)
    Action(name, label, run, primary=False)

Parameter kinds: number, int, bool, choice, color, vector, path, text, list,
note.
  number / int: min, max, step, decimals, unit
  choice:       options = [(value, label), ...]
  vector:       3 numbers (unit)
  path:         file name; filter = "Images (*.png *.jpg)"
  text:         one line of free text
  list:         read-only list of strings (rows), e.g. results
  note:         read-only text

`transaction`: when set, the host opens a FreeCAD transaction of that name
for the whole session of the panel: OK commits it, Cancel aborts it, so
Cancel leaves the document as it was (as in Part Design).

Design adapted from ShowRoom (https://github.com/oficinerobotica/ShowRoom,
dtpanels/models.py and bridge.py, LGPL-2.1-or-later).
"""

KINDS = ("number", "int", "bool", "choice", "color", "vector", "path", "text", "list", "note")


class PanelError(Exception):
    """A value refused by a parameter (shown in the panel, not raised to
    FreeCAD)."""


class Param(object):
    """One editable (or read-only) value of a panel."""

    def __init__(self, name, label, kind, get, set=None, section="", tip="", min=0.0,
                 max=100.0, step=1.0, decimals=2, unit="", options=None, filter="",
                 visible=None):
        if kind not in KINDS:
            raise ValueError("unknown parameter kind %r" % (kind,))
        self.name = name
        self.label = label
        self.kind = kind
        self.get = get
        self.setter = set
        self.section = section
        self.tip = tip
        self.min = float(min)
        self.max = float(max)
        self.step = float(step)
        self.decimals = 0 if kind == "int" else int(decimals)
        self.unit = unit
        self.options = list(options or [])
        self.filter = filter
        self.visible = visible          # callable -> bool, None = always

    @property
    def readonly(self):
        return self.setter is None or self.kind in ("list", "note")

    def coerce(self, value):
        """Value converted to the kind and checked against the limits."""
        k = self.kind
        try:
            if k == "int":
                value = int(round(float(value)))
            elif k == "number":
                value = float(value)
            elif k == "bool":
                value = bool(value)
            elif k == "vector":
                value = [float(v) for v in value]
                if len(value) != 3:
                    raise ValueError
            elif k in ("color", "path", "choice", "text"):
                value = str(value)
        except (TypeError, ValueError):
            raise PanelError("%s: invalid value %r" % (self.label, value))
        if k in ("int", "number") and not (self.min <= value <= self.max):
            raise PanelError("%s: %s is outside [%s, %s]"
                             % (self.label, value, _fmt(self.min), _fmt(self.max)))
        if k == "choice" and value not in [v for v, _l in self.options]:
            raise PanelError("%s: %r is not an option" % (self.label, value))
        if k == "color" and not (len(value) == 7 and value.startswith("#")):
            raise PanelError("%s: %r is not a #rrggbb colour" % (self.label, value))
        return value

    def public(self):
        """What the user interfaces see (no callables), JSON-ready."""
        return {"name": self.name, "label": self.label, "kind": self.kind,
                "section": self.section, "tip": self.tip, "min": self.min, "max": self.max,
                "step": self.step, "decimals": self.decimals, "unit": self.unit,
                "options": [v for v, _l in self.options],
                "optionLabels": [lab for _v, lab in self.options],
                "filter": self.filter, "readonly": self.readonly}


def _fmt(v):
    return ("%g" % v)


class Action(object):
    """A button. run() may return "close" to close the panel."""

    def __init__(self, name, label, run, primary=False, tip=""):
        self.name = name
        self.label = label
        self.run = run
        self.primary = primary
        self.tip = tip

    def public(self):
        return {"name": self.name, "label": self.label, "primary": self.primary,
                "tip": self.tip}


class PanelModel(object):
    """A panel: title, parameters grouped in sections, actions, and what
    OK / Cancel do (accept() / reject(), overridable)."""

    def __init__(self, title, params, actions=(), icon=None, transaction=None, hint=""):
        # hint: a string, or a callable returning it (follows the state)
        self.title = title
        self.params = list(params)
        self.actions = list(actions)
        self.icon = icon
        self.transaction = transaction
        self.hint = hint
        self.error = ""
        names = [p.name for p in self.params] + [a.name for a in self.actions]
        if len(names) != len(set(names)):
            raise ValueError("duplicate parameter / action names in %r" % title)

    # --- description for the user interfaces
    def param(self, name):
        for p in self.params:
            if p.name == name:
                return p
        raise KeyError(name)

    def sections(self):
        """[{"title": str, "params": [public dict, ...]}, ...] in order of
        first appearance."""
        out = []
        index = {}
        for p in self.params:
            if p.section not in index:
                index[p.section] = len(out)
                out.append({"title": p.section, "params": []})
            out[index[p.section]]["params"].append(p.public())
        return out

    def hint_text(self):
        return self.hint() if callable(self.hint) else (self.hint or "")

    def hidden(self):
        return [p.name for p in self.params if p.visible is not None and not p.visible()]

    def values(self):
        out = {}
        for p in self.params:
            try:
                out[p.name] = p.get()
            except Exception as exc:        # a getter must never break the panel
                out[p.name] = None
                self.error = str(exc)
        return out

    def public_actions(self):
        return [a.public() for a in self.actions]

    # --- edits
    def set(self, name, value):
        """Set a parameter. Returns True on success; on refusal keeps the
        message in self.error and returns False."""
        p = self.param(name)
        if p.readonly:
            self.error = "%s is read-only" % p.label
            return False
        try:
            p.setter(p.coerce(value))
        except PanelError as exc:
            self.error = str(exc)
            return False
        except Exception as exc:
            self.error = str(exc)
            return False
        self.error = ""
        return True

    def trigger(self, name):
        for a in self.actions:
            if a.name == name:
                try:
                    res = a.run()
                    self.error = ""
                    return res
                except Exception as exc:
                    self.error = str(exc)
                    return None
        raise KeyError(name)

    def accept(self):
        """OK. Returns True to close the panel."""
        return True

    def reject(self):
        """Cancel."""
        return True
