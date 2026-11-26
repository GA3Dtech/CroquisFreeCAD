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
    guide_model(board)          "3D view guide" dialog of the board
    text_model(canvas)          text box settings (selected box, or new ones)
"""

from . import model, prefs
from .i18n import tr, tr_data
from .panel_model import Action, PanelModel, Param


# ----------------------------------------------------------------------
#  New sheet
# ----------------------------------------------------------------------
class NewSheetModel(PanelModel):
    """Name, format, resolution, paper, plane and background of a new sheet.
    Defaults (preferences, remembered on OK): the size of the 3D view, in
    the camera plane at scale, transparent paper, a 3D wireframe guide
    (shown on the board, never exported). Background "picture" puts a
    capture of the 3D view on the sheet (the former "view from 3D"). OK
    creates everything through the API."""

    def __init__(self, doc, open_board=True, background=None):
        self.doc = doc
        self.open_board = open_board
        self.created = None
        bg = background or prefs.get("SheetBackground")
        self.v = {"label": tr("Sketch"), "format": prefs.get("SheetFormat"),
                  "dpi": str(prefs.get("SheetDpi")), "paper": prefs.get("SheetPaper"),
                  "plane": prefs.get("SheetPlane"),
                  "background": "guide_edges" if bg == "guide" else bg,
                  "width": prefs.get("SheetWidth"), "height": prefs.get("SheetHeight")}

        def field(name):
            return (lambda: self.v[name]), (lambda value: self.v.__setitem__(name, value))
        params = [
            Param("label", tr("Name:"), "text", *field("label")),
            Param("format", tr("Format:"), "choice", *field("format"),
                  options=[("view", tr("Size of the 3D view"))] +
                  [(k, tr_data(label)) for k, label, _w, _h in model.FORMATS] +
                  [("custom", tr("Custom size"))]),
            Param("width", tr("Width:"), "number", *field("width"), min=10, max=5000,
                  step=10, decimals=1, unit="mm", visible=lambda: self.v["format"] == "custom"),
            Param("height", tr("Height:"), "number", *field("height"), min=10, max=5000,
                  step=10, decimals=1, unit="mm", visible=lambda: self.v["format"] == "custom"),
            Param("dpi", tr("Resolution:"), "choice", *field("dpi"),
                  options=[(str(d), tr("{dpi} dpi").format(dpi=d)) for d in model.DPIS]),
            Param("paper", tr("Paper:"), "choice", *field("paper"),
                  options=[(k, tr_data(label)) for k, label, _c in model.PAPERS]),
            Param("plane", tr("Image plane:"), "choice", *field("plane"),
                  options=[("camera", tr("Camera orientation")), ("XY", tr("XY (top)")),
                           ("XZ", tr("XZ (front)")), ("YZ", tr("YZ (side)"))],
                  tip=tr("Camera orientation: the sheet lies on the 3D view, at the right "
                         "scale where the camera focuses")),
            Param("background", tr("Background:"), "choice", *field("background"),
                  options=[("guide_edges", tr("3D guide: black edges on white")),
                           ("guide_wireframe", tr("3D guide: wireframe")),
                           ("guide_shaded", tr("3D guide: shaded")),
                           ("picture", tr("Capture of the 3D view")), ("none", tr("None"))],
                  tip=tr("The guide can be shown, hidden or captured again at any time "
                         "(layer panel, 3D guide button)")),
        ]
        # unknown stored preferences fall back on the first option
        for p in params[1:]:
            if p.kind == "choice" and self.v[p.name] not in [o for o, _l in p.options]:
                self.v[p.name] = p.options[0][0]
        PanelModel.__init__(self, tr("New sketch sheet"), params)

    def accept(self):
        from . import api
        try:
            size = {}
            if self.v["format"] == "custom":
                size = {"width_mm": float(self.v["width"]), "height_mm": float(self.v["height"])}
            info = api.create_sheet(self.doc, self.v["format"], int(self.v["dpi"]),
                                    self.v["paper"], self.v["plane"],
                                    label=self.v["label"].strip() or tr("Sketch"), **size)
        except Exception as exc:
            self.error = str(exc)
            return False
        try:
            if self.v["background"].startswith("guide_"):
                info = api.capture_underlay(info["name"], style=self.v["background"][6:],
                                            doc=self.doc)
            elif self.v["background"] == "picture":
                info = api.capture_3d_view(self.doc, target_sheet=info["name"],
                                           fill=True)["sheet"]
        except Exception as exc:        # the sheet exists: keep it, say why
            import FreeCAD as App

            from . import errors
            if not isinstance(exc, errors.GuiRequiredError):
                App.Console.PrintWarning("Croquis: background not captured (%s)\n" % exc)
        prefs.put("SheetFormat", self.v["format"])
        prefs.put("SheetDpi", int(self.v["dpi"]))
        prefs.put("SheetPaper", self.v["paper"])
        prefs.put("SheetPlane", self.v["plane"])
        prefs.put("SheetBackground", self.v["background"])
        if self.v["format"] == "custom":
            prefs.put("SheetWidth", float(self.v["width"]))
            prefs.put("SheetHeight", float(self.v["height"]))
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
        sel = c.selection()
        if getattr(sel, "kind", None) == "image" or c.tool == "arrow" or \
                getattr(sel, "tool", None) == "arrow":
            return False
        return model.TOOLS.get(c.tool, {}).get("kind") == "vector" or \
            (c.tool == "edit" and sel is not None)

    def option(tool, name):
        return (lambda: c.tool_settings[tool][name],
                lambda value: c.set_option(name, value))

    def profile(name):
        # current() of a raster tool has no profile: show the default
        return (lambda: int(round(c.current().get(name, model.DEFAULT_PROFILE[name]) * 100)),
                lambda value: c.set_profile(name, value / 100.0))

    def is_arrow():
        sel = c.selection()
        return c.tool == "arrow" or getattr(sel, "tool", None) == "arrow"

    def arrow(name):
        def get():
            return c.current().get(name, model.DEFAULT_ARROW[name])
        return get, (lambda value: c.set_param(name, value))

    def hint():
        tool = c.tool
        if tool == "shape":
            from .i18n import tr_data as _td
            brush = _td(model.TOOLS[c.last_brush]["label"]) if hasattr(c, "last_brush") \
                else ""
            return tr("Drawn with the last drawing tool ({tool}). Drag to draw; Shift: "
                      "circle, square or half circle; Esc cancels.").format(tool=brush)
        if tool == "arrow":
            return tr("Straight: drag from the tail to the tip. Curved: draw freely or "
                      "click points, as with the spline.")
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
        if tool == "scale":
            return tr("Drag over something of known size, then type its real length: the "
                      "sheet takes the right size in 3D. Shift: angle in 15° steps.")
        return tr("Shift: straight line.")

    targets = [(model.ALL_LAYERS, tr("All layers"))] + [
        (k, tr_data(label)) for k, label, _b in model.LAYERS if k in model.ERASABLE_LAYERS]
    params = [
        Param("spline_mode", tr("Spline input:"), "choice", *option("spline", "mode"),
              options=[("freehand", tr("Freehand, smoothed")), ("points", tr("Control points"))],
              visible=lambda: c.tool == "spline"),
        Param("arrow_mode", tr("Arrow shape:"), "choice", *option("arrow", "mode"),
              options=[("straight", tr("Straight")), ("freehand", tr("Curved, freehand")),
                       ("points", tr("Curved, control points"))],
              visible=lambda: c.tool == "arrow"),
        Param("head_end", tr("Head at the end"), "bool", *arrow("head_end"), visible=is_arrow),
        Param("head_start", tr("Head at the start"), "bool", *arrow("head_start"),
              visible=is_arrow),
        Param("head_style", tr("Head:"), "choice", *arrow("head_style"),
              options=[("open", tr("Open")), ("filled", tr("Filled")), ("dot", tr("Dot"))],
              visible=is_arrow),
        Param("head_size", tr("Head size:"), "number", *arrow("head_size"), min=0, max=50,
              step=0.5, decimals=1, unit="mm", tip=tr("0: from the stroke width"),
              visible=is_arrow),
        Param("shape_kind", tr("Shape:"), "choice",
              lambda: c.tool_settings["shape"]["kind"],
              lambda v: c.tool_settings["shape"].__setitem__("kind", v),
              options=[("circle", tr("Circle")), ("ellipse", tr("Ellipse")),
                       ("rect", tr("Rectangle")), ("arc", tr("Arc"))],
              visible=lambda: c.tool == "shape"),
        Param("shape_hand", tr("Hand-drawn look"), "bool",
              lambda: c.tool_settings["shape"]["hand"],
              lambda v: c.tool_settings["shape"].__setitem__("hand", bool(v)),
              visible=lambda: c.tool == "shape"),
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
                  "target": "board" if board is not None else "new",
                  "align": True}

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
            Param("align", tr("Place the new sheet on the view (camera plane, scale)"),
                  "bool", *field("align"), visible=lambda: self.v["target"] == "new",
                  tip=tr("The sheet lies exactly on the captured view in 3D, at the right "
                         "scale where the camera focuses")),
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
                self.result = api.capture_3d_view(
                    self.doc, background=self.v["background"], hide_sheets=self.v["hide"],
                    factor=float(self.v["factor"]),
                    align="camera" if self.v["align"] else "plane")
        except Exception as exc:
            self.error = str(exc)
            return False
        prefs.put("CaptureFactor", self.v["factor"])
        prefs.put("CaptureBackground", self.v["background"])
        prefs.put("CaptureHideSheets", self.v["hide"])
        return True


def capture_model(doc, board=None):
    return CaptureModel(doc, board)



# ----------------------------------------------------------------------
#  3D view guide (underlay) of the board
# ----------------------------------------------------------------------
class GuideModel(PanelModel):
    """The board's 3D view guide: a view along the sheet's normal, framed
    on the sheet in true size, drawn under the strokes and never exported.
    OK captures it; 'Remove the guide' clears it."""

    def __init__(self, board):
        self.board = board
        current = board.sheet.underlay or {}
        self.v = {"style": current.get("style", "edges"),
                  "hide": current.get("hide_sheets", True)}

        def field(name):
            return (lambda: self.v[name]), (lambda value: self.v.__setitem__(name, value))
        params = [
            Param("style", tr("Style:"), "choice", *field("style"),
                  options=[("edges", tr("Edges (black on white)")),
                           ("wireframe", tr("Wireframe")), ("shaded", tr("Shaded"))]),
            Param("hide", tr("Hide the other sketch sheets"), "bool", *field("hide")),
        ]
        actions = [Action("clear", tr("Remove the guide"), self.clear)]
        PanelModel.__init__(self, tr("3D view guide"), params, actions,
                            hint=tr("The model seen along the sheet's normal, in true size: "
                                    "trace over it. Never in the 3D image nor the exports; "
                                    "its opacity is in the layer panel."))

    def clear(self):
        self.board.canvas.set_guide(None, None)
        return "close"

    def accept(self):
        from . import capture
        try:
            c = self.board.canvas
            obj = c.document().getObject(self.board.sheet_name)
            img, settings = capture.capture_plane(obj, c.sheet, self.v["style"], self.v["hide"])
        except Exception as exc:
            self.error = str(exc)
            return False
        self.board.canvas.set_guide(img, settings)
        return True


def guide_model(board):
    return GuideModel(board)



# ----------------------------------------------------------------------
#  Text boxes
# ----------------------------------------------------------------------
def text_model(canvas):
    """Font, size, bold, italic, colour, alignment, wrapping width, frame,
    white background and callout arrow: of the selected text box (edit
    tool), else of the next ones (text tool)."""
    from .render import text as text_mod
    c = canvas

    def get(name):
        def g():
            e = c.selected_text()
            if e is not None:
                return bool(e.leader) if name == "leader" else getattr(e, name)
            return c.tool_settings["text"][name]
        return g

    def put(name):
        def s(value):
            e = c.selected_text()
            if e is None:
                c.tool_settings["text"][name] = value
                return
            if name == "leader":
                x0, _y0, _x1, y1 = e.box()
                value = [x0 - 15.0, y1 + 20.0] if value else None
            c.set_text(merge_key=name, **{name: value})
        return s

    fonts = text_mod.available_fonts()

    def font_options():
        current = get("font")()
        names = fonts if current in fonts else [current] + fonts
        return [(f, f) for f in names]

    params = [
        Param("font", tr("Font:"), "choice", get("font"), put("font"), options=font_options()),
        Param("size", tr("Size:"), "number", get("size"), put("size"), min=0.5, max=200,
              step=0.5, decimals=1, unit="mm", tip=tr("Height of a line of text on the sheet")),
        Param("bold", tr("Bold"), "bool", get("bold"), put("bold")),
        Param("italic", tr("Italic"), "bool", get("italic"), put("italic")),
        Param("color", tr("Colour:"), "color", get("color"), put("color")),
        Param("align", tr("Alignment:"), "choice", get("align"), put("align"),
              options=[("left", tr("Left")), ("center", tr("Centre")), ("right", tr("Right"))]),
        Param("w", tr("Wrap width:"), "number", get("w"), put("w"), min=0, max=2000, step=5,
              decimals=1, unit="mm", tip=tr("0: no wrapping, one line per paragraph")),
        Param("frame", tr("Frame"), "bool", get("frame"), put("frame")),
        Param("background", tr("White background"), "bool", get("background"),
              put("background")),
        Param("leader", tr("Callout arrow"), "bool", get("leader"), put("leader"),
              tip=tr("An arrow from the box to a point; drag its tip with the edit tool "
                     "(V). Moving the box keeps the tip in place.")),
    ]
    return PanelModel(tr("Text"), params,
                      hint=lambda: tr("Click on the sheet to write; Escape or a click "
                                      "elsewhere validates. Double-click a text to edit it."))
