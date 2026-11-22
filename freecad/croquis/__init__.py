# SPDX-License-Identifier: LGPL-2.1-or-later
"""Croquis - designer-style sketching for FreeCAD: pencil, marker and tapered
spline strokes, rendered as translucent image planes."""

import os

__version__ = "0.1.0"

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(PACKAGE_DIR, "resources", "icons")


def icon(name):
    """Absolute path of an icon shipped with the workbench."""
    return os.path.join(ICON_DIR, name)
