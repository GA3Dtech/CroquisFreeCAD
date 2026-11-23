# SPDX-License-Identifier: LGPL-2.1-or-later
"""Review guard: no module builds a widget form by hand that would double
a generated panel. Every remaining hand-made widget form is listed here
with the reason it is allowed."""

import os
import re

import pytest
from helpers import ROOT

pytestmark = pytest.mark.unit

PKG = os.path.join(ROOT, "freecad", "croquis")
FORM_BUILDERS = re.compile(r"\bQ(FormLayout|GroupBox|Dialog)\(")

ALLOWED = {
    "bridge.py": "WidgetForm: the generic widget fallback built from panel models",
    "qml_host.py": "PanelDialog: the generic dialog around any panel",
    "prefs.py": "Edit > Preferences page: FreeCAD's own preference mechanism",
    "canvas/view.py": "LayersPanel: widget fallback of the custom QML paper / layers "
                      "panel (rule 2: custom QML where it brings real value)",
}


def test_no_hand_made_forms():
    found = {}
    for dirpath, _dirs, files in os.walk(PKG):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, PKG).replace(os.sep, "/")
                with open(path, encoding="utf-8") as fh:
                    if FORM_BUILDERS.search(fh.read()):
                        found[rel] = True
    unexpected = sorted(set(found) - set(ALLOWED))
    assert unexpected == [], "hand-made widget forms: describe them as panel models " \
        "(panel_model.py) or justify them in ALLOWED: %s" % unexpected
