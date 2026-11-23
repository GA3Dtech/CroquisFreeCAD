# Croquis

*Designer-style sketching for FreeCAD: pencil, marker and tapered spline
strokes, rendered as translucent image planes.*

Product designers usually sketch elsewhere (paper, tablet, Photoshop,
Sketchbook) and then import the result as an image plane to model over it.
**Croquis** lets you draw those sketches directly in FreeCAD. The result is
the very same object as an imported picture (an `Image::ImagePlane` placed
in the scene), but it stays **editable**: the strokes are stored in the
document, and double-clicking the sheet reopens the drawing board.

Two main uses:

1. **Intent sketch before modelling**: draw a side view or a perspective,
   place it on a plane, model over it.
2. **Overpaint** *(planned, v0.3)*: capture the 3D view, put it under the
   sheet at low opacity, and explore variants with markers on top.

## Status

Version 0.2.

| Feature | State |
|---|---|
| Drawing board in a FreeCAD tab (zoom, pan, fit), closed when leaving the workbench | done |
| Mechanical pencil, grease pencil (pressure fills the grain), white highlight | done |
| Alcohol marker (multiply, no self-darkening within a stroke) | done |
| Straight line and tapered spline stroke (freehand fitted, or control points), editable | done |
| Eraser: soft (pixels) or whole strokes, on all layers or one | done |
| Paper (transparent, white, layout pad, tinted grey, kraft) and layer visibility / opacity | done |
| Tablet pressure, pressure simulated from mouse speed, undo / redo | done |
| Sheet stored in the document, linked image plane on XY / XZ / YZ, PNG export | done |
| Pictures pasted (Ctrl+V), dropped or inserted, new sheet from the clipboard; move, resize, rotate, opacity, stacking | done (v0.3) |
| Manual 3D view capture, 3D view underlay (plane and camera), arrows, text and callouts | v0.3 |
| Ellipses, perspective grids | later |
| SVG export, TechDraw, chisel tip, custom palettes | v0.4 |

The full design (in French) is in [docs/specification_fr.md](docs/specification_fr.md).

## Installation

Clone the repository into the `Mod` folder of your FreeCAD user data
directory, then restart FreeCAD:

```
git clone https://github.com/GA3Dtech/CroquisFreeCAD ~/.local/share/FreeCAD/v1-1/Mod/CroquisFreeCAD
```

Requires FreeCAD 1.0 or newer (Qt5 or Qt6).

## Usage

| Command | What it does |
|---|---|
| **New sketch sheet** | Choose a format, resolution, paper and plane; creates a `Croquis` sheet and its image plane, and opens the drawing board. |
| **Edit sketch sheet** | Reopens the drawing board of the selected sheet (or double-click the sheet in the tree, from any workbench). |
| **New sheet from clipboard** | Creates a sheet shaped like the picture in the clipboard (screenshot, copied image), with the picture on it, and opens the board. |
| **Insert image…** | Puts a picture file on the selected sheet. |
| **Export sheet as PNG** | Saves the selected sheet as a PNG (transparent where the paper is transparent). |

The drawing board belongs to the Croquis workbench: switching to another
workbench writes the strokes into the document and closes it. The sheet then
stays in the scene as a plain image plane, to be used like any imported
picture.

### Tools

| Key | Tool | Layer | Notes |
|---|---|---|---|
| `P` | Mechanical pencil | Construction | Pressure drives the opacity, light graphite grain. |
| `G` | Grease pencil | Lines | Pressure drives width and density; a light touch shows the paper grain. |
| `M` | Alcohol marker | Marker | Multiply: overlapping strokes darken, a stroke never darkens itself. |
| `W` | White highlight | Highlights | For reflections, best on tinted paper. |
| `L` | Straight line | Lines | Tapered vector line, drag from end to end; `Shift` snaps to 15°. |
| `S` | Spline stroke | Lines | Thin, wide in the middle, pointed. *Freehand* is smoothed into Bezier curves; *Control points*: click the points, click the last one again (or double-click, `Enter`, right-click) to finish, `Backspace` removes the last point, `Esc` cancels. |
| `E` | Eraser | All or one | *Soft* removes pixels; *Whole strokes* deletes every stroke it touches. |
| `V` | Edit vector strokes | – | Click a line or spline: drag its anchors, handles or the whole stroke; colour, size, opacity and width profile apply to it; `Delete` removes it. |

**Pictures**: `Ctrl+V` pastes the clipboard picture (or image files copied
in a file manager), image files can be dropped on the board, and
*Insert image…* opens a file. A picture fits the sheet without distortion;
with the edit tool (`V`) drag it, resize it by a corner (`Shift`: free
proportions), rotate it with the round handle; its panel sets opacity,
whether it shows in the 3D image, lock, stacking. Erasers never touch
pictures. `Ctrl+C` copies the rendered sheet.

With the raster tools, `Shift` at the press draws a straight line. Line and
spline strokes have a width profile: position of the widest point, start
taper and end taper (0 % blunt, 100 % pointed).

| Input | Action |
|---|---|
| `[` / `]` | Smaller / larger tool |
| `Ctrl+Z`, `Ctrl+Shift+Z` / `Ctrl+Y` | Undo / redo |
| Mouse wheel | Zoom around the cursor |
| Middle button drag, or `Space` + drag | Pan |
| `F` | Fit the sheet in the window |

The side panel sets the paper and the visibility and opacity of each layer
(Highlights, Lines, Marker, Construction, top to bottom).

Closing the board (or *Update 3D*) writes the strokes into the document and
regenerates the image plane, as one undo step in FreeCAD.

## Tests

```
tests/run_all.sh            # lint, translations, unit, render, FreeCAD, vanilla, GUI
tests/run_all.sh unit       # or render / freecad / vanilla / gui
```

Unit and rendering tests run on plain Python (pytest, PySide6, numpy); the
other levels run inside a FreeCAD AppImage (`FREECAD_APPIMAGE`). The CI runs
them all on FreeCAD 1.0.2 and 26.3rc2, including a check that every file
written by Croquis opens in a FreeCAD **without the addon**, its image plane
intact.

## API for agents (MCP)

`freecad.croquis.api` is a stable, headless-safe API (millimetres,
`#rrggbb` colours, JSON-ready results, typed errors, one undo step per call).
Full reference: [docs/api.md](docs/api.md). With the FreeCAD MCP server
(`execute_code`), an agent can draw on an open sheet:

```python
from freecad.croquis import api
doc = App.ActiveDocument
s = api.create_sheet(doc, format="A4L", plane="XZ")
api.add_strokes(s["name"], [{"tool": "spline", "points": [[30, 150], [120, 60], [260, 140]]}],
                doc=doc)
print(api.render_png(s["name"], doc=doc))
```

The same code runs in `freecadcmd` (`execute_code_headless`).

## Translations

User-facing texts are English in the code and translated through
`freecad/croquis/translations/<code>.json` (French, German, Italian,
Spanish). `python3 tools/i18n.py check` lists missing entries, `update` adds
them. The language follows FreeCAD or can be forced in
*Edit > Preferences > Croquis*.

## License

LGPL-2.1-or-later, see [LICENSE](LICENSE).
