# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run inside a FreeCAD WITHOUT the addon: tests/run_all.sh vanilla
(CROQUIS_VANILLA=1, empty FREECAD_USER_HOME)."""

import os

import pytest

App = pytest.importorskip("FreeCAD", reason="runs inside FreeCAD (tests/run_in_freecad.py)")

if not os.environ.get("CROQUIS_VANILLA"):
    pytest.skip("vanilla tests need CROQUIS_VANILLA=1 and a FreeCAD without the addon",
                allow_module_level=True)

from imaging import ensure_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    return ensure_app()
