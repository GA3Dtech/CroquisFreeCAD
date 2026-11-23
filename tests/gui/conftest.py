# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI smoke tests: run with the FreeCAD GUI binary (tests/run_all.sh gui),
offscreen locally, under xvfb in the CI."""

import pytest

App = pytest.importorskip("FreeCAD", reason="runs inside FreeCAD (tests/run_in_freecad.py)")
if not App.GuiUp:
    pytest.skip("needs the FreeCAD GUI", allow_module_level=True)

import FreeCADGui as Gui  # noqa: E402


def qt():
    from PySide import QtCore, QtGui, QtWidgets
    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest
    return QtCore, QtGui, QtWidgets, QtTest


@pytest.fixture
def doc():
    d = App.newDocument("CroquisGui")
    name = d.Name
    yield d
    from freecad.croquis import sheet
    sheet.close_all_boards()
    if name in App.listDocuments():
        App.closeDocument(name)


@pytest.fixture
def croquis_wb():
    Gui.activateWorkbench("CroquisWorkbench")
    yield
    Gui.activateWorkbench("CroquisWorkbench")


def process(n=3):
    QtCore, _g, QtWidgets, _t = qt()
    for _ in range(n):
        QtWidgets.QApplication.processEvents()
