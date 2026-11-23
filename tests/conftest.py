# SPDX-License-Identifier: LGPL-2.1-or-later
"""Shared pytest setup: the repository root on sys.path (so that
freecad.croquis imports as a namespace package), fixture specs, the
--update-golden option of the rendering tests."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
LEGACY = os.path.join(TESTS, "fixtures", "legacy")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(TESTS, "fixtures"))

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


def legacy_json_files():
    out = []
    for dirpath, _dirs, files in os.walk(LEGACY):
        for name in sorted(files):
            if name.endswith(".json"):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def legacy_fcstd_files():
    out = []
    for dirpath, _dirs, files in os.walk(LEGACY):
        for name in sorted(files):
            if name.endswith(".FCStd"):
                out.append(os.path.join(dirpath, name))
    return sorted(out)
