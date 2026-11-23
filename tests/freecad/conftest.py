# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests run inside freecadcmd (tests/run_in_freecad.py)."""

import os
import tempfile

import pytest

App = pytest.importorskip("FreeCAD", reason="runs inside FreeCAD (tests/run_in_freecad.py)")

from imaging import ensure_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    return ensure_app()


@pytest.fixture(scope="session")
def output_dir():
    """Files written here are opened again by the vanilla tests."""
    d = os.environ.get("CROQUIS_OUTPUT") or tempfile.mkdtemp(prefix="croquis-out-")
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture
def doc():
    d = App.newDocument("CroquisTest")
    d.UndoMode = 1
    name = d.Name
    yield d
    if name in App.listDocuments():     # the test may have closed it
        App.closeDocument(name)
