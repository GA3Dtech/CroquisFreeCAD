# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - public API
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
api.py (Croquis) - the stable public API, for scripts and agents (for
example through the FreeCAD MCP server: execute_code in a running FreeCAD,
execute_code_headless in freecadcmd).

    from freecad.croquis import api
    s = api.create_sheet("MyDoc", format="A5L", plane="XZ")
    api.add_strokes(s["name"], [{"tool": "spline", "points": [[20, 100], [80, 40],
                                 [160, 90]]}], doc="MyDoc")
    api.render_png(s["name"], "/tmp/sketch.png", doc="MyDoc")

Contract:
  * no dialog; works in freecadcmd except the functions marked GUI;
  * documents: a document object, its name, or None for the active one;
    sheets: a sheet object or its name (Name or Label) in `doc`;
  * lengths in millimetres on the sheet (origin top left, y down),
    colours "#rrggbb", returns made of dict / list / str / number / bool
    only (json.dumps works on every result);
  * one FreeCAD transaction (undo step) per call that changes a document;
  * errors are the typed exceptions of errors.py;
  * API_VERSION follows semantic versioning: a minor bump adds functions
    or optional arguments, a major bump breaks callers.

Stroke format of add_strokes() / list_strokes():
    {"tool": "pencil" | "grease" | "marker" | "highlight" | "eraser"
             | "line" | "spline",
     "points": [[x, y, pressure], ...]   raster tools and eraser (mm, 0..1;
                                         pressure optional, default 1)
               [[x, y], ...]             line / spline: points the curve goes
                                         through (2 for a line)
     "bezier": [[x, y], ...]             line / spline instead of "points":
                                         Bezier chain P0 C1 C2 P1 ... (3n + 1)
     "color": "#rrggbb", "size": mm (max width for line / spline),
     "opacity": 0..1, "layer": layer key ("*" = all layers, eraser only),
     "profile": {"peak": 0..1, "tin": 0..1, "tout": 0..1}  line / spline}
Missing optional fields take the tool defaults (model.TOOLS).
"""

import inspect
import os
import re
import tempfile

import FreeCAD as App

from . import model
from .errors import (
    GuiRequiredError,  # noqa: F401  (part of the API, used by GUI functions)
    InvalidArgumentError,
    InvalidStrokeError,
    NoDocumentError,
    SheetNotFoundError,
)
from .i18n import tr

API_VERSION = "1.1.0"

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


# ----------------------------------------------------------------------
#  Helpers
# ----------------------------------------------------------------------
def _ensure_qt():
    """Rendering needs a QGuiApplication: create an offscreen one in
    freecadcmd (the GUI already has its own)."""
    from .qt import QtCore, QtGui
    if QtCore.QCoreApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _ensure_qt.app = QtGui.QGuiApplication(["croquis"])


def _doc(doc):
    if doc is None:
        if App.ActiveDocument is None:
            raise NoDocumentError("no document given and no active document")
        return App.ActiveDocument
    if isinstance(doc, str):
        if doc in App.listDocuments():
            return App.getDocument(doc)
        for d in App.listDocuments().values():
            if d.Label == doc:
                return d
        raise NoDocumentError("no open document named %r" % doc)
    if not hasattr(doc, "Objects"):
        raise NoDocumentError("not a FreeCAD document: %r" % (doc,))
    return doc


def _sheet(sheet, doc=None):
    from . import sheet as sheet_mod
    if isinstance(sheet, str):
        d = _doc(doc)
        obj = d.getObject(sheet)
        if obj is None:
            matches = d.getObjectsByLabel(sheet)
            obj = matches[0] if matches else None
        if obj is None:
            raise SheetNotFoundError("no object %r in document %r" % (sheet, d.Name))
    else:
        obj = sheet
    if not sheet_mod.is_sheet(obj):
        # an image plane of a sheet stands for its sheet
        owner = [o for o in getattr(obj, "InList", []) if sheet_mod.is_sheet(o)]
        if not owner:
            raise SheetNotFoundError("%r is not a Croquis sheet"
                                     % getattr(obj, "Name", obj))
        obj = owner[0]
    return obj


def _transaction(doc, name, fn):
    doc.openTransaction(name)
    try:
        res = fn()
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    return res


def _format_key(w, h):
    for key, _label, fw, fh in model.FORMATS:
        if abs(fw - w) < 1e-6 and abs(fh - h) < 1e-6:
            return key
    return "custom"


def _num(value, name, lo=None, hi=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidArgumentError("%s must be a number, got %r" % (name, value))
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise InvalidArgumentError("%s must be in [%s, %s], got %r" % (name, lo, hi, value))
    return float(value)


def _sheet_info(obj):
    from . import sheet as sheet_mod
    data = sheet_mod.sheet_data(obj)
    counts = {}
    for s in data.strokes:
        counts[s.layer] = counts.get(s.layer, 0) + 1
    return {
        "name": obj.Name,
        "label": obj.Label,
        "document": obj.Document.Name,
        "format": _format_key(data.width, data.height),
        "width_mm": data.width,
        "height_mm": data.height,
        "dpi": data.dpi,
        "paper": data.paper,
        "plane": sheet_mod.plane_of(obj),
        "image_plane": obj.ImagePlane.Name if obj.ImagePlane is not None else None,
        "strokes": len(data.strokes),
        "images": len(data.images()),
        "strokes_per_layer": counts,
        "layers": [{"key": k, "label": label, "blend": blend,
                    "visible": bool(data.layers[k]["visible"]),
                    "opacity": float(data.layers[k]["opacity"]),
                    "erasable": k in model.ERASABLE_LAYERS}
                   for k, label, blend in model.LAYERS],
        "format_version": data.version,
    }


def _stroke_out(index, s):
    if s.kind == "vector":
        pts = [[round(p[0], 3), round(p[1], 3)] for p in s.points]
        geom = {"bezier": pts, "profile": s.profile()}
    else:
        geom = {"points": [[round(p[0], 3), round(p[1], 3), round(p[2], 3)] for p in s.points]}
    d = {"index": index, "tool": s.tool, "kind": s.kind, "color": s.color,
         "size": s.size, "opacity": s.opacity, "layer": s.layer}
    d.update(geom)
    return d


def _point(p, i, with_pressure):
    if not isinstance(p, (list, tuple)) or len(p) not in (2, 3):
        raise InvalidStrokeError("point %d must be [x, y] or [x, y, pressure], got %r" % (i, p))
    try:
        x = _num(p[0], "x")
        y = _num(p[1], "y")
        pr = _num(p[2], "pressure", 0.0, 1.0) if len(p) == 3 else 1.0
    except InvalidArgumentError as exc:
        raise InvalidStrokeError("point %d: %s" % (i, exc))
    return (x, y, pr) if with_pressure else (x, y)


def stroke_from_dict(d):
    """model.Stroke from the API stroke format (strict validation)."""
    from .render import stroke_geom as geom
    if not isinstance(d, dict):
        raise InvalidStrokeError("a stroke must be a dict, got %r" % (d,))
    known = {"tool", "points", "bezier", "color", "size", "opacity", "layer", "profile"}
    extra = set(d) - known
    if extra:
        raise InvalidStrokeError("unknown stroke field(s): %s" % ", ".join(sorted(extra)))
    tool = d.get("tool")
    if tool not in model.TOOLS:
        raise InvalidStrokeError("tool must be one of %s, got %r"
                                 % (", ".join(model.TOOL_KEYS), tool))
    t = model.TOOLS[tool]
    color = d.get("color", t["color"])
    if not isinstance(color, str) or not _COLOR.match(color):
        raise InvalidStrokeError("color must be '#rrggbb', got %r" % (color,))
    try:
        size = _num(d.get("size", t["size"]), "size", 0.01, 200.0)
        opacity = _num(d.get("opacity", t["opacity"]), "opacity", 0.0, 1.0)
    except InvalidArgumentError as exc:
        raise InvalidStrokeError(str(exc))
    layer = d.get("layer", t["layer"])
    if t["kind"] == "eraser":
        if layer != model.ALL_LAYERS and layer not in model.ERASABLE_LAYERS:
            raise InvalidStrokeError("an eraser works on '*' or one of %s, got %r"
                                     % (", ".join(model.ERASABLE_LAYERS), layer))
    elif layer not in model.ERASABLE_LAYERS:
        raise InvalidStrokeError("layer must be one of %s, got %r"
                                 % (", ".join(model.ERASABLE_LAYERS), layer))
    params = None
    if t["kind"] == "vector":
        if ("points" in d) == ("bezier" in d):
            raise InvalidStrokeError("a %s stroke needs either 'points' or 'bezier'" % tool)
        if "bezier" in d:
            chain = [_point(p, i, False) for i, p in enumerate(d["bezier"])]
            if len(chain) < 4 or (len(chain) - 1) % 3:
                raise InvalidStrokeError("'bezier' needs 3n + 1 points (n >= 1), got %d"
                                         % len(chain))
        else:
            anchors = [_point(p, i, False) for i, p in enumerate(d["points"])]
            if len(anchors) < 2:
                raise InvalidStrokeError("a %s stroke needs at least 2 points" % tool)
            if tool == "line" and len(anchors) != 2:
                raise InvalidStrokeError("a line has exactly 2 points, got %d" % len(anchors))
            chain = geom.line_chain(*(anchors[0] + anchors[1])) if tool == "line" \
                else geom.anchors_to_chain(anchors)
        pts = [(x, y, 1.0) for x, y in chain]
        prof = dict(model.DEFAULT_PROFILE)
        given = d.get("profile", {})
        if not isinstance(given, dict) or set(given) - set(prof):
            raise InvalidStrokeError("profile keys are peak, tin, tout; got %r" % (given,))
        try:
            for k, v in given.items():
                prof[k] = _num(v, "profile." + k, 0.0, 1.0)
        except InvalidArgumentError as exc:
            raise InvalidStrokeError(str(exc))
        params = prof
    else:
        if "bezier" in d or "profile" in d:
            raise InvalidStrokeError("'bezier' and 'profile' are for line / spline strokes")
        raw = d.get("points")
        if not isinstance(raw, (list, tuple)) or not raw:
            raise InvalidStrokeError("'points' must be a non-empty list")
        pts = [_point(p, i, True) for i, p in enumerate(raw)]
    return model.Stroke(tool, color.lower(), size, opacity, layer, pts, params)


# ----------------------------------------------------------------------
#  Sheets
# ----------------------------------------------------------------------
def list_sheets(doc=None):
    """Sheets of a document, with their metadata."""
    from . import sheet as sheet_mod
    return [_sheet_info(o) for o in _doc(doc).Objects if sheet_mod.is_sheet(o)]


def create_sheet(doc=None, format="A4L", dpi=150, paper="transparent", plane="XZ",
                 placement=None, label=None, width_mm=None, height_mm=None):
    """New sheet and its image plane. format: key of model.FORMATS, or
    "custom" with width_mm and height_mm; plane: XY / XZ / YZ; placement:
    optional FreeCAD Placement of the image plane (overrides plane).
    Returns the sheet metadata."""
    from . import sheet as sheet_mod
    d = _doc(doc)
    size = None
    if format == "custom":
        size = (_num(width_mm, "width_mm", 10, 5000), _num(height_mm, "height_mm", 10, 5000))
    elif format not in [k for k, _l, _w, _h in model.FORMATS]:
        raise InvalidArgumentError("format must be one of %s or custom, got %r"
                                   % (", ".join(k for k, _l, _w, _h in model.FORMATS), format))
    if isinstance(dpi, bool) or not isinstance(dpi, int) or not 10 <= dpi <= 1200:
        raise InvalidArgumentError("dpi must be an integer in [10, 1200], got %r" % (dpi,))
    if paper not in [k for k, _l, _c in model.PAPERS]:
        raise InvalidArgumentError("paper must be one of %s, got %r"
                                   % (", ".join(k for k, _l, _c in model.PAPERS), paper))
    if plane not in sheet_mod.PLANES:
        raise InvalidArgumentError("plane must be one of XY, XZ, YZ, got %r" % (plane,))
    if placement is not None and not isinstance(placement, App.Placement):
        raise InvalidArgumentError("placement must be a FreeCAD.Placement")
    _ensure_qt()

    def run():
        obj = sheet_mod.create_sheet(d, format, dpi, paper, plane, label, size=size)
        if placement is not None:
            obj.ImagePlane.Placement = placement
        return obj
    obj = _transaction(d, tr("New sketch sheet"), run)
    d.recompute()
    return _sheet_info(obj)


def get_sheet(sheet, doc=None):
    """Metadata of a sheet: size, dpi, paper, plane, layers, stroke count."""
    return _sheet_info(_sheet(sheet, doc))


def regenerate(sheet, doc=None):
    """Render the sheet again into its image plane. Returns the metadata."""
    from . import sheet as sheet_mod
    obj = _sheet(sheet, doc)
    _ensure_qt()
    _transaction(obj.Document, tr("Edit sketch sheet"),
                 lambda: sheet_mod.update_image(obj, sheet_mod.sheet_data(obj)))
    return _sheet_info(obj)


def set_paper(sheet, paper, doc=None):
    """Change the paper (transparent, white, layout, grey, kraft)."""
    if paper not in [k for k, _l, _c in model.PAPERS]:
        raise InvalidArgumentError("paper must be one of %s, got %r"
                                   % (", ".join(k for k, _l, _c in model.PAPERS), paper))
    return _edit(sheet, doc, tr("Edit sketch sheet"), lambda data: setattr(data, "paper", paper))


def set_layer(sheet, layer, visible=None, opacity=None, doc=None):
    """Visibility and / or opacity (0..1) of a layer."""
    if layer not in model.LAYER_KEYS:
        raise InvalidArgumentError("layer must be one of %s, got %r"
                                   % (", ".join(model.LAYER_KEYS), layer))
    if visible is not None and not isinstance(visible, bool):
        raise InvalidArgumentError("visible must be True, False or None")
    if opacity is not None:
        opacity = _num(opacity, "opacity", 0.0, 1.0)

    def change(data):
        if visible is not None:
            data.layers[layer]["visible"] = visible
        if opacity is not None:
            data.layers[layer]["opacity"] = opacity
    return _edit(sheet, doc, tr("Edit sketch sheet"), change)


def _edit(sheet, doc, name, change):
    from . import sheet as sheet_mod
    obj = _sheet(sheet, doc)
    _ensure_qt()

    def run():
        data = sheet_mod.sheet_data(obj)
        result = change(data)
        sheet_mod.write(obj, data)
        return result
    result = _transaction(obj.Document, name, run)
    return _sheet_info(obj) if result is None else result


# ----------------------------------------------------------------------
#  Strokes
# ----------------------------------------------------------------------
def list_strokes(sheet, layer=None, doc=None):
    """Strokes of a sheet (optionally of one layer), in drawing order, in
    the API stroke format plus "index" and "kind"."""
    from . import sheet as sheet_mod
    if layer is not None and layer not in model.LAYER_KEYS + [model.ALL_LAYERS]:
        raise InvalidArgumentError("unknown layer %r" % (layer,))
    data = sheet_mod.sheet_data(_sheet(sheet, doc))
    return [_stroke_out(i, s) for i, s in enumerate(data.strokes)
            if layer is None or s.layer == layer]


def add_strokes(sheet, strokes, doc=None):
    """Append strokes (API stroke format, validated before anything is
    changed). Returns {"indices": [...], "sheet": metadata}."""
    if not isinstance(strokes, (list, tuple)) or not strokes:
        raise InvalidStrokeError("strokes must be a non-empty list")
    built = []
    for i, d in enumerate(strokes):
        try:
            built.append(stroke_from_dict(d))
        except InvalidStrokeError as exc:
            raise InvalidStrokeError("stroke %d: %s" % (i, exc))

    def change(data):
        first = len(data.strokes)
        data.strokes.extend(built)
        return list(range(first, first + len(built)))
    obj = _sheet(sheet, doc)
    indices = _edit(obj, None, tr("Edit sketch sheet"), change)
    return {"indices": indices, "sheet": _sheet_info(obj)}


def delete_strokes(sheet, indices, doc=None):
    """Remove strokes by index (as listed by list_strokes)."""
    from . import sheet as sheet_mod
    obj = _sheet(sheet, doc)
    n = len(sheet_mod.sheet_data(obj).strokes)
    if not isinstance(indices, (list, tuple)) or not indices:
        raise InvalidArgumentError("indices must be a non-empty list")
    for i in indices:
        if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < n:
            raise InvalidArgumentError("stroke index %r out of range [0, %d)" % (i, n))
    drop = set(indices)

    def change(data):
        data.strokes = [s for i, s in enumerate(data.strokes) if i not in drop]
    _edit(obj, None, tr("Edit sketch sheet"), change)
    return _sheet_info(obj)


# ----------------------------------------------------------------------
#  Image elements (pictures on the sheet)
# ----------------------------------------------------------------------
IMAGE_FIELDS = ("x", "y", "w", "h", "rotation", "opacity", "render", "locked", "layer")


def _image_out(e):
    d = e.to_dict()
    d.pop("file", None)
    return d


def _find_image(data, image_id):
    for e in data.images():
        if e.id == image_id:
            return e
    raise InvalidArgumentError("no image element %r on the sheet" % (image_id,))


def image_element(data, img, path, x_mm=None, y_mm=None, width_mm=None, layer="images",
                  render=True, opacity=1.0, rotation=0.0, keep_original=False, camera=None,
                  margin=0.05):
    """New ImageElement for a QImage on `data` (placed, picture reduced and
    written to a temporary file registered in data.files). Shared by the
    API and the board (paste, drop, capture)."""
    from . import images
    if width_mm is None:
        x, y, w, h = model.fit_rect(img.width(), img.height(), data.width, data.height, margin)
    else:
        w = _num(width_mm, "width_mm", 0.1, 10000)
        h = w * img.height() / float(img.width())
        x, y = (data.width - w) / 2.0, (data.height - h) / 2.0
    if x_mm is not None:
        x = _num(x_mm, "x_mm")
    if y_mm is not None:
        y = _num(y_mm, "y_mm")
    if not keep_original:
        img = images.reduce(img, *images.useful_size(w, h, data.dpi))
    tmp = path if (keep_original and path) else images.save_temp(img, "croquis_image")
    image_id = data.new_id()
    e = model.ImageElement(image_id, "Image_" + image_id, x, y, w, h, rotation, opacity, layer,
                           render, camera=camera, source_px=[img.width(), img.height()])
    data.files[e.file] = tmp
    return e


def add_image(sheet, path, x_mm=None, y_mm=None, width_mm=None, layer="images",
              include_in_render=True, opacity=1.0, rotation=0.0, keep_original=False,
              doc=None):
    """Put a picture file on the sheet (content image: drawn in the image
    plane unless include_in_render is False). By default it fits inside the
    sheet, centred, proportions kept; width_mm sets its width (height from
    the proportions), x_mm / y_mm its top left corner. The picture is
    reduced to the resolution the sheet can use unless keep_original.
    Returns the image element."""
    from . import images
    obj = _sheet(sheet, doc)
    if layer not in model.LAYER_KEYS or layer == "underlay":
        raise InvalidArgumentError("layer must be one of the drawing layers, got %r" % (layer,))
    opacity = _num(opacity, "opacity", 0.0, 1.0)
    rotation = _num(rotation, "rotation", -3600, 3600)
    if not isinstance(path, str) or not os.path.isfile(path):
        raise InvalidArgumentError("no image file %r" % (path,))
    _ensure_qt()
    try:
        img = images.read(path)
    except ValueError as exc:
        raise InvalidArgumentError(str(exc))

    temps = []

    def change(data):
        e = image_element(data, img, path, x_mm, y_mm, width_mm, layer,
                          bool(include_in_render), opacity, rotation, keep_original)
        data.elements.append(e)
        temps.append(data.files[e.file])
        return e
    try:
        e = _edit(obj, None, tr("Edit sketch sheet"), change)
    finally:
        _remove_temps(temps, keep=path)
    return _image_out(e)


def _remove_temps(paths, keep=None):
    """Temporary pictures, once the document has its own copy."""
    for p in paths:
        if p and p != keep and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


def new_sheet_from_image(doc, path, plane="XY", dpi=150, paper="white", long_side_mm=297.0,
                         label=None):
    """New sheet whose proportions follow the picture (long side
    long_side_mm), with the picture filling it. Returns {"sheet": metadata,
    "image": element}."""
    from . import images
    if not isinstance(path, str) or not os.path.isfile(path):
        raise InvalidArgumentError("no image file %r" % (path,))
    _ensure_qt()
    try:
        img = images.read(path)
    except ValueError as exc:
        raise InvalidArgumentError(str(exc))
    long_side_mm = _num(long_side_mm, "long_side_mm", 20, 5000)
    k = long_side_mm / float(max(img.width(), img.height()))
    w, h = round(img.width() * k, 2), round(img.height() * k, 2)
    info = create_sheet(doc, "custom", dpi, paper, plane, label=label, width_mm=w, height_mm=h)
    obj = _sheet(info["name"], doc)
    temps = []

    def change(data):
        e = image_element(data, img, path, margin=0.0)
        data.elements.append(e)
        temps.append(data.files[e.file])
        return e
    try:
        e = _edit(obj, None, tr("Edit sketch sheet"), change)
    finally:
        _remove_temps(temps, keep=path)
    return {"sheet": _sheet_info(obj), "image": _image_out(e)}


def list_images(sheet, doc=None):
    """Image elements of a sheet, bottom to top."""
    from . import sheet as sheet_mod
    return [_image_out(e) for e in sheet_mod.sheet_data(_sheet(sheet, doc)).images()]


def update_image_element(sheet, image_id, doc=None, **changes):
    """Change an image element: x, y, w, h (mm), rotation (degrees),
    opacity (0..1), render (bool: drawn in the image plane), locked (bool),
    layer. Returns the element."""
    bad = set(changes) - set(IMAGE_FIELDS)
    if bad:
        raise InvalidArgumentError("unknown image field(s): %s" % ", ".join(sorted(bad)))
    checked = {}
    for k, v in changes.items():
        if k in ("render", "locked"):
            if not isinstance(v, bool):
                raise InvalidArgumentError("%s must be True or False" % k)
            checked[k] = v
        elif k == "layer":
            if v not in model.LAYER_KEYS or v == "underlay":
                raise InvalidArgumentError("layer must be a drawing layer, got %r" % (v,))
            checked[k] = v
        elif k == "opacity":
            checked[k] = _num(v, k, 0.0, 1.0)
        elif k in ("w", "h"):
            checked[k] = _num(v, k, 0.1, 10000)
        else:
            checked[k] = _num(v, k)

    def change(data):
        e = _find_image(data, image_id)
        for k, v in checked.items():
            setattr(e, k, v)
        return e
    return _image_out(_edit(sheet, doc, tr("Edit sketch sheet"), change))


def delete_image_element(sheet, image_id, doc=None):
    """Remove an image element (and its stored picture)."""
    def change(data):
        data.elements.remove(_find_image(data, image_id))
    _edit(sheet, doc, tr("Edit sketch sheet"), change)
    return get_sheet(sheet, doc)


# ----------------------------------------------------------------------
#  Rendering
# ----------------------------------------------------------------------
def render_png(sheet, path=None, include_underlay=False, dpi=None, doc=None):
    """Render the sheet to a PNG file (a temporary file when path is None)
    without changing the document. Returns the path."""
    from . import sheet as sheet_mod
    from .render import compositor
    obj = _sheet(sheet, doc)
    if dpi is not None and (isinstance(dpi, bool) or not isinstance(dpi, int)
                            or not 10 <= dpi <= 1200):
        raise InvalidArgumentError("dpi must be an integer in [10, 1200], got %r" % (dpi,))
    if path is None:
        fd, path = tempfile.mkstemp(prefix="croquis_%s_" % obj.Name, suffix=".png")
        os.close(fd)
    _ensure_qt()
    data = sheet_mod.sheet_data(obj)
    if not compositor.save_png(data, path, dpi=dpi, export=not include_underlay):
        raise InvalidArgumentError("could not write %r" % (path,))
    return path


def export_png(sheet, path, dpi=None, doc=None):
    """Write the sheet as a PNG file at `path`. Returns the path."""
    if not isinstance(path, str) or not path:
        raise InvalidArgumentError("path must be a file name")
    return render_png(sheet, path, dpi=dpi, doc=doc)


# ----------------------------------------------------------------------
#  Introspection
# ----------------------------------------------------------------------
PUBLIC = ["list_sheets", "create_sheet", "get_sheet", "regenerate", "set_paper", "set_layer",
          "list_strokes", "add_strokes", "delete_strokes", "add_image", "new_sheet_from_image",
          "list_images", "update_image_element", "delete_image_element", "render_png",
          "export_png", "describe"]

GUI_ONLY = []


def describe():
    """Catalogue of the API: version, functions (signature, summary, GUI
    requirement), tools, layers, formats and papers."""
    funcs = {}
    for name in PUBLIC:
        fn = globals()[name]
        doc = inspect.getdoc(fn) or ""
        funcs[name] = {"signature": name + str(inspect.signature(fn)),
                       "summary": doc.split("\n\n")[0].replace("\n", " "),
                       "gui": name in GUI_ONLY}
    return {
        "api_version": API_VERSION,
        "format_version": model.FORMAT_VERSION,
        "functions": funcs,
        "tools": {k: {"kind": t["kind"], "layer": t["layer"], "color": t["color"],
                      "size": t["size"], "opacity": t["opacity"]}
                  for k, t in model.TOOLS.items()},
        "layers": [k for k, _l, _b in model.LAYERS],
        "erasable_layers": list(model.ERASABLE_LAYERS),
        "formats": {k: [w, h] for k, _l, w, h in model.FORMATS},
        "papers": [k for k, _l, _c in model.PAPERS],
        "planes": ["XY", "XZ", "YZ"],
    }
