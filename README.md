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

Version 0.1 (in development).

| Feature | State |
|---|---|
| Drawing board in a FreeCAD tab (zoom, pan, fit) | done |
| Mechanical pencil (pressure → opacity, graphite grain) | done |
| Alcohol marker (multiply, no self-darkening within a stroke) | done |
| Tablet pressure, pressure simulated from mouse speed | done |
| Undo / redo per stroke | done |
| Sheet stored in the document, linked image plane on XY / XZ / YZ | done |
| Double-click to edit, image regenerated on close | done |
| Transparent PNG export | done |
| Tapered spline stroke, grease pencil, layer panel, papers | v0.2 |
| 3D view capture as underlay, camera-aligned plane, ellipses, perspective grids | v0.3 |
| SVG export, TechDraw, chisel tip | v0.4 |

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
| **Edit sketch sheet** | Reopens the drawing board of the selected sheet (or double-click the sheet in the tree). |
| **Export sheet as PNG** | Saves the selected sheet as a PNG (transparent where the paper is transparent). |

In the drawing board:

| Input | Action |
|---|---|
| `P` / `M` | Mechanical pencil / alcohol marker |
| `[` / `]` | Smaller / larger tool |
| `Ctrl+Z`, `Ctrl+Shift+Z` / `Ctrl+Y` | Undo / redo |
| Mouse wheel | Zoom around the cursor |
| Middle button drag, or `Space` + drag | Pan |
| `F` | Fit the sheet in the window |

Closing the board writes the strokes into the document and regenerates the
image plane (one undo step in FreeCAD).

## Translations

User-facing texts are English in the code and translated through
`freecad/croquis/translations/<code>.json` (French, German, Italian,
Spanish). `python3 tools/i18n.py check` lists missing entries, `update` adds
them. The language follows FreeCAD or can be forced in
*Edit > Preferences > Croquis*.

## License

LGPL-2.1-or-later, see [LICENSE](LICENSE).
