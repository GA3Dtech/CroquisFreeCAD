# SPDX-License-Identifier: LGPL-2.1-or-later
"""Documents checked without the addon, and how to open them while
capturing what FreeCAD prints."""

import glob
import os
import re
import tempfile

from helpers import legacy_fcstd_files

# Messages expected when a document holding Croquis sheets is opened
# without the addon: the proxy classes cannot be imported. Anything else
# that looks like an error fails the test.
EXPECTED = [
    re.compile(r"freecad\.croquis"),
    re.compile(r"No module named 'freecad\.croquis"),
    re.compile(r"[Pp]roxy"),
    re.compile(r"Croquis\d*"),
]
ERROR = re.compile(r"(error|exception|traceback|failed)", re.I)


def documents():
    """Legacy fixtures + documents written by the FreeCAD tests."""
    out = list(legacy_fcstd_files())
    produced = os.environ.get("CROQUIS_OUTPUT")
    if produced:
        out += sorted(glob.glob(os.path.join(produced, "*.FCStd")))
    return out


def open_captured(App, path):
    """Open a document, returning (document, printed text): stdout and
    stderr are redirected at file-descriptor level, since FreeCAD's
    console writes from C++."""
    log = tempfile.TemporaryFile(mode="w+b")
    saved = os.dup(1), os.dup(2)
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    try:
        doc = App.openDocument(path)
        App.Console.PrintMessage("")
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])
    log.seek(0)
    return doc, log.read().decode("utf-8", "replace")


def unexpected_errors(text):
    bad = []
    for line in text.splitlines():
        if ERROR.search(line) and not any(p.search(line) for p in EXPECTED):
            bad.append(line)
    return bad
