# SPDX-License-Identifier: LGPL-2.1-or-later
"""Croquis - designer-style sketching for FreeCAD: pencil, marker and tapered
spline strokes, rendered as translucent image planes."""

import os
import re

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(PACKAGE_DIR, "resources", "icons")
PACKAGE_XML = os.path.join(PACKAGE_DIR, os.pardir, os.pardir, "package.xml")


def _read_version():
    """Version from package.xml, the single source of truth."""
    try:
        with open(PACKAGE_XML, "r", encoding="utf-8") as fh:
            m = re.search(r"<version>\s*([^<\s]+)\s*</version>", fh.read())
        return m.group(1) if m else "0.0.0"
    except OSError:
        return "0.0.0"


__version__ = _read_version()


def icon(name):
    """Absolute path of an icon shipped with the workbench."""
    return os.path.join(ICON_DIR, name)
