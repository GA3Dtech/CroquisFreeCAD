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
    tool_options_model(canvas)  options of the active tool on the board
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


# ----------------------------------------------------------------------
#  Tool options (board side panel)
# ----------------------------------------------------------------------
def tool_options_model(canvas):
    """Options of the active tool: spline mode, eraser mode and layers,
    width profile of vector strokes (or of the selected one in the edit
    tool), and a hint. Follows canvas.tool / the selection."""
    c = canvas

    def is_vector():
        return model.TOOLS.get(c.tool, {}).get("kind") == "vector" or \
            (c.tool == "edit" and c.selection() is not None)

    def option(tool, name):
        return (lambda: c.tool_settings[tool][name],
                lambda value: c.set_option(name, value))

    def profile(name):
        return (lambda: int(round(c.current()[name] * 100)),
                lambda value: c.set_profile(name, value / 100.0))

    def hint():
        tool = c.tool
        if tool == "line":
            return tr("Drag from one end to the other. Shift: angle in 15° steps.")
        if tool == "spline":
            if c.tool_settings["spline"]["mode"] == "points":
                return tr("Click the points of the curve; click the last one again, "
                          "double-click or Enter to finish. Backspace: remove the last "
                          "point, Esc: cancel.")
            return tr("Draw freely: the stroke is smoothed into an editable curve.")
        if tool == "edit":
            return tr("Click a line or spline stroke, then drag its points or the stroke "
                      "itself. Delete removes it.")
        return tr("Shift: straight line.")

    targets = [(model.ALL_LAYERS, tr("All layers"))] + [
        (k, tr_data(label)) for k, label, _b in model.LAYERS if k in model.ERASABLE_LAYERS]
    params = [
        Param("spline_mode", tr("Spline input:"), "choice", *option("spline", "mode"),
              options=[("freehand", tr("Freehand, smoothed")), ("points", tr("Control points"))],
              visible=lambda: c.tool == "spline"),
        Param("eraser_mode", tr("Eraser:"), "choice", *option("eraser", "mode"),
              options=[("soft", tr("Soft (pixels)")), ("strokes", tr("Whole strokes"))],
              visible=lambda: c.tool == "eraser"),
        Param("eraser_target", tr("Erase on:"), "choice", *option("eraser", "target"),
              options=targets, visible=lambda: c.tool == "eraser"),
        Param("peak", tr("Widest at:"), "int", *profile("peak"), min=5, max=95, step=5,
              unit="%", tip=tr("Position of the widest point along the stroke"),
              visible=is_vector),
        Param("tin", tr("Start taper:"), "int", *profile("tin"), min=0, max=100, step=10,
              unit="%", tip=tr("0 %: blunt start, 100 %: pointed start"), visible=is_vector),
        Param("tout", tr("End taper:"), "int", *profile("tout"), min=0, max=100, step=10,
              unit="%", tip=tr("0 %: blunt end, 100 %: pointed end"), visible=is_vector),
    ]
    return PanelModel(tr("Tool options"), params, hint=hint)
