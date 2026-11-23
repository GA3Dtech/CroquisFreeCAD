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
    image_model(canvas)         properties of the selected picture
    capture_model(doc, board)   "Capture 3D view" dialog
"""

from . import model, prefs
from .i18n import tr, tr_data
from .panel_model import Action, PanelModel, Param


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
        # current() of a raster tool has no profile: show the default
        return (lambda: int(round(c.current().get(name, model.DEFAULT_PROFILE[name]) * 100)),
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


# ----------------------------------------------------------------------
#  Image properties (board side panel, edit tool)
# ----------------------------------------------------------------------
def image_model(canvas):
    """Properties of the picture selected with the edit tool: opacity,
    shown in the image plane or not, locked, rotation, width (height
    follows the proportions), stacking, delete."""
    c = canvas

    def img():
        return c.selected_image()

    def getter(name, scale=1.0, default=0):
        def get():
            e = img()
            return default if e is None else getattr(e, name) * scale
        return get

    def setter(name, scale=1.0):
        return lambda value: c.set_image(merge_key=name, **{name: value / scale})

    def set_width(value):
        e = img()
        if e is not None and value > 0:
            k = value / e.w
            cx, cy = e.x + e.w / 2.0, e.y + e.h / 2.0
            c.set_image(merge_key="size", w=value, h=e.h * k,
                        x=cx - value / 2.0, y=cy - e.h * k / 2.0)

    def restack(top):
        e = img()
        if e is not None:
            c.set_image(index=len(c.sheet.elements) if top else 0)

    def delete():
        e = img()
        if e is not None:
            from .canvas import undo
            c.undo_stack.push(undo.RemoveElements(c, [e]))

    def back_to_view():
        e = img()
        if e is None or not e.camera:
            raise ValueError(tr("This picture has no recorded 3D view."))
        from . import capture
        doc = c.document()
        capture.restore_camera(capture.view_3d(doc), e.camera)
        import FreeCADGui as Gui
        Gui.getDocument(doc.Name).activateView("Gui::View3DInventor")

    def size_note():
        e = img()
        if e is None or not e.source_px:
            return ""
        return tr("{w} × {h} px stored").format(w=e.source_px[0], h=e.source_px[1])

    params = [
        Param("opacity", tr("Opacity:"), "int", lambda: int(round(getter("opacity")() * 100)),
              lambda v: c.set_image(merge_key="opacity", opacity=v / 100.0),
              min=0, max=100, step=5, unit="%"),
        Param("render", tr("Show in the 3D image and exports"), "bool",
              getter("render", default=True), lambda v: c.set_image(render=bool(v)),
              tip=tr("Off: the picture only helps while drawing")),
        Param("locked", tr("Locked"), "bool", getter("locked", default=False),
              lambda v: c.set_image(locked=bool(v)),
              tip=tr("A locked picture can no longer be selected on the board")),
        Param("rotation", tr("Rotation:"), "number", getter("rotation"), setter("rotation"),
              min=-180, max=180, step=5, decimals=1, unit="°"),
        Param("width", tr("Width:"), "number", getter("w"), set_width, min=1, max=5000,
              step=5, decimals=1, unit="mm"),
        Param("size", "", "note", size_note),
    ]
    actions = [
        Action("front", tr("Bring to front"), lambda: restack(True)),
        Action("back", tr("Send to back"), lambda: restack(False)),
        Action("delete", tr("Delete image"), delete),
        Action("view", tr("Back to this view"), back_to_view,
               tip=tr("Put the 3D view back where this capture was taken")),
    ]
    return PanelModel(tr("Image"), params, actions)


# ----------------------------------------------------------------------
#  3D view capture
# ----------------------------------------------------------------------
class CaptureModel(PanelModel):
    """Resolution, background, hiding the sheets, destination (a new sheet,
    or the open board). OK captures the document's 3D view; the picture is
    a content image, ready to draw, arrow and write on."""

    def __init__(self, doc, board=None):
        self.doc = doc
        self.board = board
        self.result = None
        self.v = {"factor": prefs.get("CaptureFactor"),
                  "background": prefs.get("CaptureBackground"),
                  "hide": prefs.get("CaptureHideSheets"),
                  "target": "board" if board is not None else "new"}

        def field(name):
            return (lambda: self.v[name]), (lambda value: self.v.__setitem__(name, value))
        params = [
            Param("factor", tr("Resolution:"), "choice", *field("factor"),
                  options=[("1", tr("View size")), ("2", tr("Twice the view size")),
                           ("4", tr("4 × the view size"))]),
            Param("background", tr("Background:"), "choice", *field("background"),
                  options=[("current", tr("As in the view")), ("white", tr("White")),
                           ("transparent", tr("Transparent"))]),
            Param("hide", tr("Hide the sketch sheets"), "bool", *field("hide")),
            Param("target", tr("Put the picture on:"), "choice", *field("target"),
                  options=[("new", tr("A new sheet")), ("board", tr("The open board"))],
                  visible=lambda: board is not None),
        ]
        if self.v["factor"] not in ("1", "2", "4"):
            self.v["factor"] = "1"
        PanelModel.__init__(self, tr("Capture 3D view"), params,
                            hint=tr("Frame the 3D view first: the whole view is captured."))

    def accept(self):
        from . import api, capture
        try:
            if self.v["target"] == "board" and self.board is not None:
                img, camera = capture.capture(self.doc, background=self.v["background"],
                                              hide_sheets=self.v["hide"],
                                              factor=float(self.v["factor"]))
                self.result = {"element": self.board.canvas.add_picture(img, camera=camera)}
            else:
                self.result = api.capture_3d_view(self.doc, background=self.v["background"],
                                                  hide_sheets=self.v["hide"],
                                                  factor=float(self.v["factor"]))
        except Exception as exc:
            self.error = str(exc)
            return False
        prefs.put("CaptureFactor", self.v["factor"])
        prefs.put("CaptureBackground", self.v["background"])
        prefs.put("CaptureHideSheets", self.v["hide"])
        return True


def capture_model(doc, board=None):
    return CaptureModel(doc, board)
