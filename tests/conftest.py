# SPDX-License-Identifier: LGPL-2.1-or-later
"""Shared pytest setup: the repository root on sys.path (so that
freecad.croquis imports as a namespace package), fixture specs, the
--update-golden option of the rendering tests."""

import os
import sys

import pytest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
for _p in (ROOT, TESTS, os.path.join(TESTS, "fixtures")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Inside FreeCAD the "freecad" namespace already exists: make sure this
# repository's copy of the addon is the one imported
try:
    import freecad
    _pkg = os.path.join(ROOT, "freecad")
    if _pkg not in list(freecad.__path__):
        freecad.__path__.insert(0, _pkg)
except ImportError:
    pass


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true", default=False,
                     help="rewrite the reference images of the rendering tests")


@pytest.fixture(scope="session")
def update_golden(request):
    return request.config.getoption("--update-golden")


@pytest.fixture(scope="session")
def artifacts_dir():
    d = os.environ.get("CROQUIS_ARTIFACTS") or os.path.join(ROOT, "tests", "_artifacts")
    os.makedirs(d, exist_ok=True)
    return d
