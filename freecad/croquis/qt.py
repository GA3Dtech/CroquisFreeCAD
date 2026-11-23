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

# Moved from QtWidgets to QtGui in Qt6
QUndoStack = getattr(QtGui, "QUndoStack", None) or QtWidgets.QUndoStack
QUndoCommand = getattr(QtGui, "QUndoCommand", None) or QtWidgets.QUndoCommand
QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction
QActionGroup = getattr(QtGui, "QActionGroup", None) or QtWidgets.QActionGroup
QShortcut = getattr(QtGui, "QShortcut", None) or QtWidgets.QShortcut


def use_offscreen_without_display():
    """Before creating a QGuiApplication in freecadcmd: with no display,
    Qt must use its offscreen platform. FreeCAD's AppImage launcher may set
    QT_QPA_PLATFORM to a windowing platform (1.1: xcb), which aborts the
    process without a display, so it is overridden here."""
    import os
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def event_pos(event):
    """Position (QPointF, widget coordinates) of a mouse / tablet / wheel
    event in both Qt5 and Qt6."""
    if hasattr(event, "position"):
        return event.position()
    if hasattr(event, "posF"):
        return event.posF()
    return event.localPos()


__all__ = ["QtCore", "QtGui", "QtWidgets", "QT6", "QUndoStack", "QUndoCommand",
           "QAction", "QActionGroup", "QShortcut", "event_pos", "use_offscreen_without_display"]
