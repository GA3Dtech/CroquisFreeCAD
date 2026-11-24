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
| `freecad/croquis/api.py` | **Public API** (stable, headless-safe, JSON results, one transaction per call); `docs/api.md` |
| `freecad/croquis/errors.py` | Typed exceptions of the API |
| `freecad/croquis/sheet.py` | `Croquis::Sheet` FeaturePython + ViewProvider, linked ImagePlane, PNG regeneration |
| `freecad/croquis/render/stroke_geom.py` | Pure geometry: input smoothing, pressure from speed, Catmull-Rom, Schneider Bezier fitting, width profile, hit testing |
| `freecad/croquis/render/brushes.py` | Draws one stroke into a QImage (raster brushes, vector strokes as dense pseudo strokes, grain) |
| `freecad/croquis/render/compositor.py` | Layer caches, erasers (DestinationOut), hidden strokes, blend modes, paper, partial composite, PNG export |
| `freecad/croquis/canvas/view.py` | SheetCanvas (input devices, zoom, pan, shortcuts, painting) and SheetBoard (toolbar, tool options, paper / layers panel) |
| `freecad/croquis/canvas/tools.py` | One object per tool: brushes, straight line, spline, erasers, vector edit |
| `freecad/croquis/canvas/undo.py` | QUndoStack commands at stroke level |
| `freecad/croquis/images.py` | Pictures: reading (EXIF orientation), reduction to the useful resolution, clipboard / drop data |
| `freecad/croquis/capture.py` | 3D view captures (manual capture, plane-aligned guide), always the document's 3D view, sheets / navigation cube hidden |
| `freecad/croquis/panel_model.py` | Single description of a panel (typed parameters, actions, sections) — pure Python |
| `freecad/croquis/panels.py` | The workbench's panel models (New sheet, tool options…), calling `api.py` |
| `freecad/croquis/bridge.py` | Generic engine: `Bridge` (QML), `WidgetForm` (widget fallback), `I18n`, theme; `LayersBridge` |
| `freecad/croquis/qml_host.py` | Qt Quick availability (OpenGL, preference), `make_view`, `build_panel`, `PanelDialog` |
| `freecad/croquis/resources/qml/` | Generic QML components (`Panel`, `Section`, one `*Row` per kind) and custom QML (`LayersPanel`) |
| `freecad/croquis/qt.py` | Single PySide import point, Qt5 / Qt6 helpers |
| `freecad/croquis/i18n.py` | `tr()` and language selection |
| `freecad/croquis/prefs.py` | All settings (`get`/`put`) and the preference page |
| `freecad/croquis/translations/` | `<code>.json` tables English → language |
| `freecad/croquis/resources/palettes/` | Marker palettes (JSON) |
| `tools/i18n.py` | Check / update the translation tables (Python and QML) |
| `tests/` | Test suite, see *Testing*; `tests/fixtures/legacy/` frozen files (never regenerate) |
| `.github/workflows/ci.yml` | CI: lint, unit, render, FreeCAD 1.1.4 / 26.3rc2 / 27.1 dev (integration, vanilla, GUI) |

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

- **Croquis is a passive workbench, not an MCP and must never become one.**
  No server, bridge, network listener, AI client or remote call; nothing runs
  at import or startup beyond registering the workbench. It only exposes the
  Python API (`api.py`), generic (scripts, macros, addons). Agent-side code
  (MCP servers, prompts, bridges) never enters the repository
  (`tests/unit/test_passive.py` guards it).

- Every file starts with the `# -*- coding: utf-8 -*-` line, the
  `SPDX-License-Identifier: LGPL-2.1-or-later` line and the license header.
- PySide import pattern: `from PySide import ...` with a `PySide6` fallback.
  Avoid APIs that differ between Qt5 and Qt6 (`QTabletEvent.position()` vs
  `posF()`, enums: use the scoped form through helpers).
- **Every change of a document goes through `api.py` or the model functions
  it uses (`sheet.write` / `sheet.store`, `sheet.create_sheet`)**: no GUI
  code edits sheet properties directly. New features add their API
  function (and its tests) first.
- Document changes go inside `doc.openTransaction(...)` /
  `commitTransaction()` (one undo step per user action).
- **Files must open in a FreeCAD without any addon.** The `Croquis::Sheet`
  object may become inert there, but its `Image::ImagePlane` must keep
  showing the last render, exactly like an imported picture. Never store
  anything the image plane needs outside standard FreeCAD properties
  (`tests/vanilla` checks it on FreeCAD 1.1, 26.3 and 27.1).
- Sheet geometry is in **millimetres**; pixels only exist at render time
  (`SheetData.scale`). Never store pixel coordinates.
- Marker rule: a stroke must not darken over itself, two strokes must. Each
  stroke is drawn in its own buffer with `CompositionMode_Source` (no
  accumulation inside the stroke), then composited on its layer with the tool
  opacity and the layer blend mode (multiply for markers).
- Format v2: content images (`elements`, layer `images`, included in the
  image plane) versus the guide (`underlay`, layer `underlay`, NEVER in the
  image plane or exports unless asked). Pictures live in
  `App::PropertyFileIncluded` properties (`Image_<id>`, `UnderlayImage`),
  never base64 in the JSON. New element kinds go in `model.ELEMENT_KINDS`
  (unknown kinds are kept), no format bump needed.
- Vector strokes (`kind == "vector"`) store a Bezier chain in `points`
  (P0 C1 C2 P1 ..., pressure unused) and their width profile in `params`.
  Raster strokes store input points (x, y, pressure).
- The drawing board belongs to the Croquis workbench: `Deactivated` closes
  (and saves) every board; `open_board` switches to the workbench.
- The canvas takes its keys (tool letters, Delete, Esc, Enter, Ctrl+Z...)
  through `ShortcutOverride`, otherwise FreeCAD's global shortcuts fire
  (Delete would delete document objects). Add new keys to `_OWN_KEYS`.
- **Panels, rule 1: one model generates both interfaces.** A form panel
  (options, parameters, lists, actions) is a `PanelModel` (`panels.py`);
  the generic engine shows it in QML and builds the widget fallback
  automatically. Never write the same panel twice (QML + widgets): when the
  engine cannot show something, add a parameter kind to `panel_model.py`,
  `bridge.WidgetForm` and a `*Row.qml`. No business logic in QML, widgets
  or bridges: models call `api.py`.
- **Panels, rule 2: custom QML only where it brings real value** (rich long
  lists or grids, floating see-through items on the 3D view, palettes / HUD
  around the drawing area), each justified in one line in its header, with a
  simpler widget fallback keeping the function. Dialogs, confirmations and
  very simple panels stay classic widgets or go through rule 1.
  `tests/unit/test_panel_review.py` lists the allowed hand-made widget forms.
- **The drawing canvas stays a QPainter widget** (`SheetCanvas`: tablet,
  pressure, rendering speed); only the panels around it may be QML.
- QML pitfalls: OpenGL graphics API set before the first `QQuickWidget`
  (`qml_host.quick_usable`), else widget fallback; QtQuick imported from
  PySide6 / PySide2 lazily (FreeCAD's PySide lacks it); versioned imports
  (`QtQuick 2.15`, Qt 5 and Qt 6); the bridge's parent is the view; never
  resize a view from a QML binding (0 ms timer); give rows their initial
  properties (`Loader.setSource(url, props)`); QML texts use
  `i18n.tr("...")` (scanned by `tools/i18n.py`), never `qsTr`; Loader /
  Repeater items are not in the QObject tree (walk `childItems()`); a
  focused QML field must keep its keys (tested).
- Settings: always through `prefs.get()` / `prefs.put()` (keys in
  `prefs.DEFAULTS`), and expose new ones on the preference page.
- Translations: after changing texts run `python3 tools/i18n.py update`, fill
  the new entries of `translations/*.json`; `python3 tools/i18n.py check` must
  report nothing missing before a commit.

## Testing

**Every change of logic comes with a test; unit, rendering and FreeCAD
tests must be green before a commit.** GUI behaviour with a real tablet and
the feel of drawing can only be checked by hand: say so explicitly.

| Level | Where | Run |
|---|---|---|
| unit | `tests/unit` (pure Python, no Qt / FreeCAD) | `.venv/bin/python -m pytest tests/unit` |
| render | `tests/render` (Qt offscreen, reference images in `tests/expected/render`) | `.venv/bin/python -m pytest tests/render` (`--update-golden` to rewrite on purpose) |
| freecad | `tests/freecad` (inside `freecadcmd`) | `tests/run_all.sh freecad` |
| vanilla | `tests/vanilla` (FreeCAD **without** the addon) | `tests/run_all.sh vanilla` (after `freecad`, same `CROQUIS_WORK`) |
| gui | `tests/gui` + GUI part of `tests/vanilla` (FreeCAD GUI, offscreen locally, xvfb in CI) | `tests/run_all.sh gui` |
| all | lint, translations and every level | `tests/run_all.sh` |

- `.venv`: `uv venv .venv && uv pip install --python .venv/bin/python pytest ruff PySide6 numpy`.
- `tests/run_all.sh` uses `FREECAD_APPIMAGE` (default the user's 26.3 RC1
  AppImage; an extracted `AppRun` works too), an isolated
  `FREECAD_USER_HOME` with the repository linked in its `Mod` folder, and
  installs pytest for FreeCAD's Python. `tests/run_in_freecad.py` runs pytest
  inside FreeCAD and always ends with `os._exit` (freecadcmd may return 0 on
  failure); `tests/check_junit.py` checks the reports.
- Fixtures: `tests/fixtures/specs.py` (deterministic sheets) and
  `build_fixtures.py`. Format changes go through `model.FORMAT_VERSION` + a
  tested migration in `model.MIGRATIONS`; legacy files must keep opening.
- Never test on the user's open documents: work on copies in a temporary
  folder (whatever tool drives FreeCAD) and close them.

## Releases and git

- Bump `version` and `date` in `package.xml` for a release, update the status
  table of `README.md` when features change.
- `__pycache__/` is ignored; never commit it.
- Commit in small steps with English messages; each commit green.
