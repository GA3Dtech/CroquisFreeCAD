# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""qt.py (Croquis) - one place for the PySide import: FreeCAD's PySide
module (Qt5 in 1.0, Qt6 in 1.1+), PySide6 / PySide2 as fallbacks when run
outside FreeCAD."""

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets

QT6 = QtCore.qVersion().startswith("6")

__all__ = ["QtCore", "QtGui", "QtWidgets", "QT6"]
