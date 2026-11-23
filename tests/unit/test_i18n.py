# SPDX-License-Identifier: LGPL-2.1-or-later
"""Translations: complete, and the {named} fields kept in every language."""

import json
import os
import re
import subprocess
import sys

import pytest
from helpers import ROOT

pytestmark = pytest.mark.unit

TRANS = os.path.join(ROOT, "freecad", "croquis", "translations")
FIELD = re.compile(r"\{(\w+)(?:[:!][^}]*)?\}")


def test_i18n_check_clean():
    res = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "i18n.py"), "check"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "warning" not in res.stdout


@pytest.mark.parametrize("name", sorted(n for n in os.listdir(TRANS) if n.endswith(".json")))
def test_named_fields_identical(name):
    with open(os.path.join(TRANS, name), encoding="utf-8") as fh:
        table = json.load(fh)
    for src, dst in table.items():
        if src.startswith("_") or not dst:
            continue
        assert sorted(FIELD.findall(src)) == sorted(FIELD.findall(dst)), (name, src, dst)
