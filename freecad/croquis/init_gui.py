# SPDX-License-Identifier: LGPL-2.1-or-later
"""
init_gui.py (Croquis) - registers the workbench, its commands and its
preference page.

Namespace-package layout (FreeCAD workbench starter kit): FreeCAD imports
freecad.croquis and runs this module at startup.
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import icon, __version__
from . import commands
from .i18n import tr

commands.register()

from . import prefs

try:
    # The preference dialog looks for an icon named "preferences-<group>"
    # (lower case, spaces as "_") in the icon search path
    from . import ICON_DIR
    Gui.addIconPath(ICON_DIR)
    prefs.register()
except Exception as exc:
    App.Console.PrintWarning("Croquis: preference page not added (%s)\n" % exc)


class CroquisWorkbench(Gui.Workbench):
    """Designer-style sketching: sheets drawn in a 2D board, shown in the 3D
    scene as image planes."""

    MenuText = "Croquis"
    ToolTip = tr("Designer-style sketching: pencil, marker and tapered spline "
                 "strokes, rendered as translucent image planes.")
    Icon = icon("Croquis.svg")

    def Initialize(self):
        self.appendToolbar("Croquis", commands.TOOLBAR)
        self.appendMenu("Croquis", commands.MENU)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def ContextMenu(self, recipient):
        if recipient == "Tree":
            self.appendContextMenu("", commands.CONTEXT)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(CroquisWorkbench())

App.Console.PrintLog("Croquis %s loaded\n" % __version__)
