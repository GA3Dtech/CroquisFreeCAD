# SPDX-License-Identifier: LGPL-2.1-or-later
"""Paths and fixture file lists shared by the test modules."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
LEGACY = os.path.join(TESTS, "fixtures", "legacy")


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
