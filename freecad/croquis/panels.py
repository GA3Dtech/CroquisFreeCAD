# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - panel models of the workbench
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
panels.py (Croquis) - the panels of the workbench, described as panel
models (panel_model.py). The generic engine (bridge.py, qml_host.py) shows
them in QML or, as a fallback, in classic widgets: no panel is written by
hand twice. The models call api.py; they hold no drawing logic.

    new_sheet_model(doc)        "New sketch sheet" dialog
"""

from . import model, prefs
from .i18n import tr, tr_data
from .panel_model import PanelModel, Param


# ----------------------------------------------------------------------
#  New sheet
# ----------------------------------------------------------------------
class NewSheetModel(PanelModel):
    """Name, format, resolution, paper and plane of a new sheet. Defaults
    from the preferences, remembered on OK; OK creates the sheet through
    the API (one undo step)."""

    def __init__(self, doc, open_board=True):
        self.doc = doc
        self.open_board = open_board
        self.created = None
        self.v = {"label": tr("Sketch"), "format": prefs.get("SheetFormat"),
                  "dpi": str(prefs.get("SheetDpi")), "paper": prefs.get("SheetPaper"),
                  "plane": prefs.get("SheetPlane")}

        def field(name):
            return (lambda: self.v[name]), (lambda value: self.v.__setitem__(name, value))
        params = [
            Param("label", tr("Name:"), "text", *field("label")),
            Param("format", tr("Format:"), "choice", *field("format"),
                  options=[(k, tr_data(label)) for k, label, _w, _h in model.FORMATS]),
            Param("dpi", tr("Resolution:"), "choice", *field("dpi"),
                  options=[(str(d), tr("{dpi} dpi").format(dpi=d)) for d in model.DPIS]),
            Param("paper", tr("Paper:"), "choice", *field("paper"),
                  options=[(k, tr_data(label)) for k, label, _c in model.PAPERS]),
            Param("plane", tr("Image plane:"), "choice", *field("plane"),
                  options=[("XY", tr("XY (top)")), ("XZ", tr("XZ (front)")),
                           ("YZ", tr("YZ (side)"))]),
        ]
        # unknown stored preferences fall back on the first option
        for p in params[1:]:
            if self.v[p.name] not in [o for o, _l in p.options]:
                self.v[p.name] = p.options[0][0]
        PanelModel.__init__(self, tr("New sketch sheet"), params)

    def accept(self):
        from . import api
        try:
            info = api.create_sheet(self.doc, self.v["format"], int(self.v["dpi"]),
                                    self.v["paper"], self.v["plane"],
                                    label=self.v["label"].strip() or tr("Sketch"))
        except Exception as exc:
            self.error = str(exc)
            return False
        prefs.put("SheetFormat", self.v["format"])
        prefs.put("SheetDpi", int(self.v["dpi"]))
        prefs.put("SheetPaper", self.v["paper"])
        prefs.put("SheetPlane", self.v["plane"])
        self.created = info
        return True


def new_sheet_model(doc):
    return NewSheetModel(doc)
