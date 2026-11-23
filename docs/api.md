# Croquis public API

`freecad.croquis.api` is the stable entry point for scripts and agents
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
| `create_sheet(doc=None, format="A4L", dpi=150, paper="transparent", plane="XZ", placement=None, label=None)` | metadata of the new sheet |
| `get_sheet(sheet, doc=None)` | metadata: name, label, format, size in mm, dpi, paper, plane, image plane name, stroke counts, layers |
| `list_strokes(sheet, layer=None, doc=None)` | strokes in drawing order (stroke format + `index`, `kind`) |
| `add_strokes(sheet, strokes, doc=None)` | `{"indices": [...], "sheet": metadata}` — all strokes are validated before anything changes |
| `delete_strokes(sheet, indices, doc=None)` | metadata |
| `set_layer(sheet, layer, visible=None, opacity=None, doc=None)` | metadata |
| `set_paper(sheet, paper, doc=None)` | metadata |
| `regenerate(sheet, doc=None)` | metadata (re-renders the image plane) |
| `render_png(sheet, path=None, include_underlay=False, dpi=None, doc=None)` | path of the PNG (temporary file when `path` is `None`); the document is not changed |
| `export_png(sheet, path, dpi=None, doc=None)` | path |
| `describe()` | API version, functions, tools, layers, formats, papers, planes |

Formats: `A5L A5P A4L A4P A3L A3P SQ`. Papers: `transparent white layout
grey kraft`. Planes: `XY XZ YZ`. Layers (bottom to top): `underlay
construction marker lines highlights`; strokes go on `construction`,
`marker`, `lines` or `highlights`.

## Stroke format

```json
{"tool": "pencil | grease | marker | highlight | eraser | line | spline",
 "points": [[x, y, pressure], ...],
 "bezier": [[x, y], ...],
 "color": "#rrggbb", "size": 1.2, "opacity": 0.9, "layer": "lines",
 "profile": {"peak": 0.45, "tin": 1.0, "tout": 1.0}}
```

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

## Through the FreeCAD MCP server

With [freecad-mcp](https://github.com/neka-nat/freecad-mcp), an agent can
draw on a sheet of the document open in FreeCAD (`execute_code`):

```python
from freecad.croquis import api
doc = App.ActiveDocument
s = api.list_sheets(doc)[0] if api.list_sheets(doc) else api.create_sheet(doc, "A4L")
api.add_strokes(s["name"], [
    {"tool": "marker", "points": [[40, 120], [250, 110]], "size": 10},
    {"tool": "spline", "points": [[30, 150], [120, 60], [260, 140]], "size": 1.5},
    {"tool": "line", "points": [[30, 180], [270, 180]], "profile": {"tin": 0}},
], doc=doc)
print(api.render_png(s["name"], doc=doc))   # read the PNG back to check the result
```

or build a file without any GUI (`execute_code_headless`):

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

Next step (not done yet): a dedicated MCP server exposing these functions
as typed tools.
