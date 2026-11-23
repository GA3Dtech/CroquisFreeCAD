# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
build_fixtures.py (Croquis tests) - build the fixture documents described
in specs.py with the addon found in a given repository root.

Run inside FreeCAD (it needs FreeCAD and a QGuiApplication for rendering):

    FREECAD_USER_HOME=$(mktemp -d) freecadcmd tests/fixtures/build_fixtures.py \\
        --pass <repo root> <output folder>

Writes <output>/<document>.FCStd and <output>/json/<document>/<sheet>.json.
Use a temporary FREECAD_USER_HOME so that no other copy of the addon is on
the path.
"""

import json
import os
import sys


def build(root, out):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide import QtGui
    if QtGui.QGuiApplication.instance() is None:
        build._app = QtGui.QGuiApplication(["croquis-fixtures"])
    import freecad
    freecad.__path__.insert(0, os.path.join(root, "freecad"))
    import FreeCAD as App
    from freecad.croquis import model, sheet

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import specs

    os.makedirs(out, exist_ok=True)
    written = []
    for doc_name, sheets in specs.documents().items():
        doc = App.newDocument(doc_name)
        os.makedirs(os.path.join(out, "json", doc_name), exist_ok=True)
        for spec in sheets:
            obj = sheet.create_sheet(doc, spec["format"], spec["dpi"], spec["paper"],
                                     spec["plane"], spec["label"])
            data = model.SheetData.from_json(json.dumps(spec["data"]))
            sheet.store(obj, data)
            with open(os.path.join(out, "json", doc_name, spec["label"] + ".json"), "w",
                      encoding="utf-8") as fh:
                fh.write(obj.SheetData)
                fh.write("\n")
        doc.recompute()
        path = os.path.join(out, doc_name + ".FCStd")
        doc.saveAs(path)
        App.closeDocument(doc.Name)
        written.append(path)
    return written


# freecadcmd runs scripts under their own module name, not "__main__"
if any(a.endswith("build_fixtures.py") for a in sys.argv):
    args = [a for a in sys.argv if a != "--pass"]
    for p in build(os.path.abspath(args[-2]), os.path.abspath(args[-1])):
        print("fixture:", p)
