# Croquis public API

`freecad.croquis.api` is the stable entry point for scripts, macros and
other addons
(`API_VERSION` follows semantic versioning; `api.describe()` returns the
full catalogue as JSON-ready data).

```python
from freecad.croquis import api
```

## Conventions

- **Documents**: a document object, its name or label, or `None` for the
  active document. **Sheets**: a sheet object, its `Name` or `Label`, or the
  name of its image plane (pass `doc=` when using names).
- **Units**: millimetres on the sheet, origin at the top left corner, y
  pointing down (like an image). Colours are `"#rrggbb"`.
- **Results** are plain dicts, lists, strings, numbers and booleans:
  `json.dumps()` works on every result.
- **Undo**: every call that changes a document is one FreeCAD transaction.
- **Headless**: everything works in `freecadcmd` (an offscreen
  `QGuiApplication` is created for rendering when needed). Functions that
  need the GUI are flagged `"gui": true` in `describe()` and raise
  `GuiRequiredError` in `freecadcmd`.
- **Errors** (`freecad.croquis.errors`), all subclasses of `CroquisError`:
  `NoDocumentError`, `SheetNotFoundError`, `InvalidStrokeError`,
  `InvalidArgumentError` (also a `ValueError`), `GuiRequiredError`.

## Functions

| Function | Returns |
|---|---|
| `list_sheets(doc=None)` | list of sheet metadata |
| `create_sheet(doc=None, format="A4L", dpi=150, paper="transparent", plane="XZ", placement=None, label=None, width_mm=None, height_mm=None)` | metadata of the new sheet (`format="custom"` with `width_mm`, `height_mm`) |
| `get_sheet(sheet, doc=None)` | metadata: name, label, format, size in mm, dpi, paper, plane, image plane name, stroke counts, layers |
| `list_strokes(sheet, layer=None, doc=None)` | strokes in drawing order (stroke format + `index`, `kind`) |
| `add_strokes(sheet, strokes, doc=None)` | `{"indices": [...], "sheet": metadata}` — all strokes are validated before anything changes |
| `add_arrow(sheet, points, curved=False, head_start=False, head_end=True, style="open", width_mm=0.8, color="#1b1b1d", layer="lines", head_size_mm=0.0, opacity=1.0, doc=None)` | like `add_strokes` — tail at `points[0]`, tip at `points[-1]`; straight with 2 points, a smooth curve through all points when `curved` |
| `delete_strokes(sheet, indices, doc=None)` | metadata |
| `set_layer(sheet, layer, visible=None, opacity=None, doc=None)` | metadata |
| `set_paper(sheet, paper, doc=None)` | metadata |
| `regenerate(sheet, doc=None)` | metadata (re-renders the image plane) |
| `add_image(sheet, path, x_mm=None, y_mm=None, width_mm=None, layer="images", include_in_render=True, opacity=1.0, rotation=0.0, keep_original=False, doc=None)` | the image element (`id`, `x`, `y`, `w`, `h` in mm, `rotation`, `opacity`, `layer`, `render`, `locked`, `source_px`) — fitted in the sheet by default, picture reduced to the useful resolution unless `keep_original` |
| `new_sheet_from_image(doc, path, plane="XY", dpi=150, paper="white", long_side_mm=297.0, label=None)` | `{"sheet": metadata, "image": element}` — sheet shaped like the picture |
| `list_images(sheet, doc=None)` | image elements, bottom to top |
| `update_image_element(sheet, image_id, doc=None, **changes)` | the element (fields `x y w h rotation opacity render locked layer`) |
| `delete_image_element(sheet, image_id, doc=None)` | metadata |
| `capture_3d_view(doc=None, width_px=None, height_px=None, background="current", hide_sheets=True, target_sheet=None, factor=1.0)` | **GUI.** `{"sheet", "image", "camera"}` — picture of the document's 3D view on a new sheet (or `target_sheet`), camera kept |
| `restore_image_view(sheet, image_id, doc=None)` | **GUI.** the camera; puts the 3D view back where the picture was captured |
| `add_text(sheet, text, x_mm, y_mm, width_mm=None, size_mm=5.0, color="#1b1b1d", font="Sans Serif", bold=False, italic=False, align="left", frame=False, background=False, leader_to=None, layer="lines", doc=None)` | the text element (`h` computed); `leader_to` [x, y] adds a callout arrow |
| `list_texts(sheet, doc=None)` / `edit_text(sheet, text_id, doc=None, **changes)` / `delete_text(sheet, text_id, doc=None)` | elements / element / metadata |
| `set_scale(sheet, scale=None, segment=None, length_mm=None, doc=None)` | metadata — 3D size of the sheet, from a value or a segment of known real length |
| `capture_underlay(sheet, mode="plane", style="edges", opacity=0.4, hide_sheets=True, doc=None)` | **GUI.** metadata — 3D view guide along the sheet's normal, true size, never exported (`style`: edges, wireframe, shaded) |
| `refresh_underlay(sheet, doc=None)` | **GUI.** metadata — captured again with the stored settings |
| `clear_underlay(sheet, doc=None)` | metadata |
| `render_png(sheet, path=None, include_underlay=False, dpi=None, doc=None)` | path of the PNG (temporary file when `path` is `None`); the document is not changed |
| `export_png(sheet, path, dpi=None, doc=None)` | path |
| `describe()` | API version, functions, tools, layers, formats, papers, planes |

Formats: `A5L A5P A4L A4P A3L A3P SQ`. Papers: `transparent white layout
grey kraft`. Planes: `XY XZ YZ`. Layers (bottom to top): `underlay
construction marker lines highlights`; strokes go on `construction`,
`marker`, `lines` or `highlights`.

## Stroke format

```json
{"tool": "pencil | grease | marker | highlight | eraser | line | spline | arrow",
 "points": [[x, y, pressure], ...],
 "bezier": [[x, y], ...],
 "color": "#rrggbb", "size": 1.2, "opacity": 0.9, "layer": "lines",
 "profile": {"peak": 0.45, "tin": 1.0, "tout": 1.0},
 "heads": {"start": false, "end": true, "style": "open | filled | dot", "size": 0}}
```

`heads` is for arrows only (`size` in mm, 0 = from the width).

- Raster tools and the eraser: `points` in mm, pressure 0..1 (optional,
  default 1). The eraser's `layer` is `"*"` (all layers, default) or one
  layer.
- `line` / `spline`: either `points` (the curve goes through them; exactly
  2 for a line) or `bezier` (a chain `P0 C1 C2 P1 ...` of 3n + 1 points).
  `size` is the maximum width; `profile` sets where the stroke is widest
  (`peak`) and how pointed its start (`tin`) and end (`tout`) are
  (0 blunt, 1 pointed).
- Missing optional fields take the tool defaults (`describe()["tools"]`).
- Unknown fields, out-of-range values, wrong point counts or wrong layers
  raise `InvalidStrokeError` (the message names the stroke and the field).

## Examples

Draw on a sheet of the open document (macro or Python console):

```python
from freecad.croquis import api
doc = App.ActiveDocument
s = api.list_sheets(doc)[0] if api.list_sheets(doc) else api.create_sheet(doc, "A4L")
api.add_strokes(s["name"], [
    {"tool": "marker", "points": [[40, 120], [250, 110]], "size": 10},
    {"tool": "spline", "points": [[30, 150], [120, 60], [260, 140]], "size": 1.5},
    {"tool": "line", "points": [[30, 180], [270, 180]], "profile": {"tin": 0}},
], doc=doc)
print(api.render_png(s["name"], doc=doc))
```

Capture the 3D view and annotate it (GUI):

```python
from freecad.croquis import api
res = api.capture_3d_view(App.ActiveDocument, background="white")
api.add_strokes(res["sheet"]["name"], [
    {"tool": "line", "points": [[40, 40], [120, 90]], "size": 1.2},
], doc=App.ActiveDocument)
```

Build a file without any GUI (`freecadcmd` script):

```python
import FreeCAD as App
from freecad.croquis import api
doc = App.newDocument("Sketch")
s = api.create_sheet(doc, format="A5L", dpi=150, paper="white", plane="XY")
api.add_strokes(s["name"], [{"tool": "spline", "points": [[20, 100], [100, 30], [190, 90]]}],
                doc=doc)
api.export_png(s["name"], "/tmp/sketch.png", doc=doc)
doc.saveAs("/tmp/sketch.FCStd")
```

## Scope

Croquis is a passive workbench: importing it starts nothing, it opens no
network connection and embeds no server, bridge or AI client. This API is
plain Python; any script, macro or third-party addon may call it
(including an MCP addon, for those who want one).
