# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - GUI commands
# Copyright (C) 2026 GA3Dtech
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or (at
# your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <https://www.gnu.org/licenses/>.
"""
commands.py (Croquis) - FreeCAD commands. Thin wrappers: the work is done
in sheet.py (document objects) and canvas/ (drawing board).
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import icon
from .i18n import tr


class _Command(object):
    """Generic command: calls `action`, reports errors in the report view
    instead of letting them escape into FreeCAD."""

    def __init__(self, action, icon_file, menu_text, tooltip,
                 needs_document=True, needs=None, accel=None):
        self._action = action
        self._icon = icon_file
        self._menu_text = menu_text
        self._tooltip = tooltip
        self._needs_document = needs_document
        self._needs = needs
        self._accel = accel

    def GetResources(self):
        res = {"Pixmap": icon(self._icon),
               "MenuText": self._menu_text,
               "ToolTip": self._tooltip}
        if self._accel:
            res["Accel"] = self._accel
        return res

    def Activated(self):
        try:
            self._action()
        except Exception as exc:  # surface the error, never crash FreeCAD
            import traceback
            App.Console.PrintError("Croquis: %s\n%s\n" % (exc, traceback.format_exc()))

    def IsActive(self):
        if self._needs_document and App.ActiveDocument is None:
            return False
        if self._needs is not None:
            try:
                return bool(self._needs())
            except Exception:
                return False
        return True


# Filled by register(); kept as module lists for init_gui
TOOLBAR = []
MENU = []
CONTEXT = []


def register():
    """Add every command to FreeCAD."""
    pass
