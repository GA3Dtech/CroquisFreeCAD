# SPDX-License-Identifier: LGPL-2.1-or-later
"""Every source file carries the SPDX licence identifier."""

import os
import subprocess

import pytest
from helpers import ROOT

pytestmark = pytest.mark.unit

EXTS = (".py", ".qml", ".sh", ".yml", ".yaml", ".toml")


def tracked_sources():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        out = []
        for dirpath, _d, files in os.walk(ROOT):
            if ".git" in dirpath or ".venv" in dirpath:
                continue
            out += [os.path.relpath(os.path.join(dirpath, f), ROOT) for f in files]
    return sorted(f for f in out if f.endswith(EXTS) and "fixtures/legacy" not in f)


def test_spdx_headers():
    missing = []
    for rel in tracked_sources():
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            head = fh.read(600)
        if "SPDX-License-Identifier: LGPL-2.1-or-later" not in head:
            missing.append(rel)
    assert missing == []
