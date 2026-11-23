# Legacy fixtures – Croquis v0.2.0

Frozen documents written by the addon **before** the quality work, kept to
prove that old files always open, regenerate and render the same.

| Item | Value |
|---|---|
| Addon | Croquis 0.2.0, commit `df8dfb8` (code unmodified, built from a worktree) |
| FreeCAD | 26.3.0 RC1 (`FreeCAD_26.3rc1-Linux-x86_64.AppImage`, Python 3.13, Qt 6.11) |
| Sheet data format | `version: 1` |
| Built on | 2026-11-23, with an empty `FREECAD_USER_HOME` (no other addon) |
| Generator | `tests/fixtures/build_fixtures.py` + `tests/fixtures/specs.py` |

Contents:

- `formats.FCStd`: one sheet per format (A5–A3 portrait / landscape, square)
  at 72, 100, 150, 200 and 300 dpi;
- `papers.FCStd`: one sheet per paper (transparent, white, layout, grey, kraft);
- `tools.FCStd`: one stroke of every tool (pencil, grease, marker, highlight,
  line, spline), soft erasers on all layers and on one layer, a sheet after a
  whole-stroke erase (the erased strokes are simply absent), hidden layers and
  layer opacities;
- `planes.FCStd`: image planes on XY, XZ and YZ;
- `json/<document>/<sheet>.json`: the `SheetData` property of every sheet.

Each `.FCStd` also holds the PNG rendered by v0.2.0 (`<Sheet>.png`), used as
the rendering reference of the legacy tests.

**Never regenerate these files.** New versions get their own folder.
