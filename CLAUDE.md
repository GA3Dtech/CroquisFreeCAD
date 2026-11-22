# CLAUDE.md – Croquis

FreeCAD workbench (pure Python, PySide) for designer-style sketching: strokes
drawn on a 2D board (MDI tab), stored in the document, rendered to a PNG shown
by a linked `Image::ImagePlane`. Read `README.md` first; the full design
(French) is `docs/specification_fr.md`, its roadmap section drives the work.

## Layout

| File | Role |
|---|---|
| `freecad/croquis/init_gui.py` | Workbench class, toolbar, menu, preference page |
| `freecad/croquis/commands.py` | Gui commands (thin wrappers) |
| `freecad/croquis/model.py` | Pure data: formats, papers, layers, tool presets, `Stroke`, `SheetData` (JSON) — no Qt, no FreeCAD |
| `freecad/croquis/sheet.py` | `Croquis::Sheet` FeaturePython + ViewProvider, linked ImagePlane, PNG regeneration |
| `freecad/croquis/render/stroke_geom.py` | Pure geometry: input smoothing, pressure from speed, resampling |
| `freecad/croquis/render/brushes.py` | Draws one stroke into a QImage (pencil, marker) |
| `freecad/croquis/render/compositor.py` | Layer caches, blend modes, paper, full / partial composite, PNG export |
| `freecad/croquis/canvas/view.py` | Drawing widget (tablet / mouse input, zoom, pan) and the MDI board window |
| `freecad/croquis/canvas/undo.py` | QUndoStack commands at stroke level |
| `freecad/croquis/i18n.py` | `tr()` and language selection |
| `freecad/croquis/prefs.py` | All settings (`get`/`put`) and the preference page |
| `freecad/croquis/translations/` | `<code>.json` tables English → language |
| `freecad/croquis/resources/palettes/` | Marker palettes (JSON) |
| `tools/i18n.py` | Check / update the translation tables |

The repository lives directly in the user's FreeCAD `Mod` folder
(`~/.local/share/FreeCAD/v26-3/Mod/CroquisFreeCAD`): changes are live after a
FreeCAD restart.

## Language rules (strict)

- **Code, comments, docstrings, identifiers, commit messages: English only.**
- **User-facing texts: English in the code, wrapped in `tr()`** (or `N_()`
  for data tables translated at display), translated in
  `translations/<code>.json` (fr, de, it, es).
- Conversation with the user: French.

## Code conventions

- Every file starts with the `# -*- coding: utf-8 -*-` line, the
  `SPDX-License-Identifier: LGPL-2.1-or-later` line and the license header.
- PySide import pattern: `from PySide import ...` with a `PySide6` fallback.
  Avoid APIs that differ between Qt5 and Qt6 (`QTabletEvent.position()` vs
  `posF()`, enums: use the scoped form through helpers).
- Document changes go inside `doc.openTransaction(...)` /
  `commitTransaction()` (one undo step per user action).
- Sheet geometry is in **millimetres**; pixels only exist at render time
  (`SheetData.scale`). Never store pixel coordinates.
- Marker rule: a stroke must not darken over itself, two strokes must. Each
  stroke is drawn in its own buffer with `CompositionMode_Source` (no
  accumulation inside the stroke), then composited on its layer with the tool
  opacity and the layer blend mode (multiply for markers).
- Settings: always through `prefs.get()` / `prefs.put()` (keys in
  `prefs.DEFAULTS`), and expose new ones on the preference page.
- Translations: after changing texts run `python3 tools/i18n.py update`, fill
  the new entries of `translations/*.json`; `python3 tools/i18n.py check` must
  report nothing missing before a commit.

## Testing

No test suite. `model.py` and `render/stroke_geom.py` import without FreeCAD.
Rendering can be checked headless with the FreeCAD AppImage:
`QT_QPA_PLATFORM=offscreen ~/Appimages/FreeCAD_26.3rc1-Linux-x86_64.AppImage freecadcmd script.py`
(create a `QGuiApplication` first). Document objects can be tested in
`freecadcmd` too; the board window and tablet input must be checked in
FreeCAD by the user — say so explicitly when it has not been tested.

## Releases and git

- Bump `version` and `date` in `package.xml` for a release, update the status
  table of `README.md` when features change.
- `__pycache__/` is ignored; never commit it.
- Commit in small steps with English messages.
