# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- Development tooling: `pyproject.toml` (ruff, pytest markers),
  `.pre-commit-config.yaml`, `.gitattributes`.
- Frozen v0.2.0 fixture documents (`tests/fixtures/legacy/v0.2.0`).
- Unit tests (model, geometry, translations, package metadata) and
  offscreen rendering tests with reference images (`--update-golden`).
- FreeCAD integration tests run inside `freecadcmd` (`tests/run_in_freecad.py`,
  `tests/run_all.sh`): sheet creation, PNG inside the `.FCStd`, save / reopen,
  undo steps, export, legacy v0.2.0 files.
- Vanilla tests: every file written by the addon (and every legacy file)
  opens in a FreeCAD without the addon, with its image plane intact.
- `model.migrate()`: format migrations, applied when a sheet is read.

### Fixed
- Unknown fields, layers and tools written by a newer version of the addon
  are kept (and written back) instead of being dropped or drawn as pencil.

- GitHub Actions CI: lint, unit tests (Python 3.10 / 3.12), rendering
  tests, then FreeCAD 1.0.2 and 26.3rc2 (pinned official AppImages,
  extracted, cached): integration, vanilla and GUI smoke tests, JUnit
  checks and artifacts.
- GUI smoke tests (workbench, commands, board tools through synthetic
  events, undo keys, keyboard guards) and GUI vanilla tests (image plane
  displayed and visible in a 3D view capture without the addon).
- Ctrl+C on the board copies the rendered sheet to the clipboard.
- Panels built from a single model (`panel_model.py`) shown in QML with an
  automatic widget fallback (`bridge.py`, `qml_host.py`,
  `resources/qml/`); preference "Use QML panels". The New sheet dialog and
  the board's tool options use it.
- Custom QML paper / layers palette on the board (widget fallback kept).
- Pictures on sheets: paste with Ctrl+V (clipboard picture or copied image
  files), drag and drop, "Insert image…", "New sheet from clipboard";
  edit tool moves, resizes and rotates them, image panel (opacity, shown in
  the 3D image or not, lock, stacking, delete). Pictures are stored in the
  `.FCStd` (one file property per picture, reduced to the useful resolution
  by default) and drawn in the image plane under the strokes.
- "Capture 3D view" (workbench and board): picture of the document's 3D
  view, never the board, with the sheets hidden, onto a new sheet shaped
  like the view or onto the open board; the camera is kept with the picture
  ("Back to this view"). Shared capture code in `capture.py`.
- API 1.2: `capture_3d_view`, `restore_image_view` (GUI only).
- API 1.1: `add_image`, `new_sheet_from_image`, `list_images`,
  `update_image_element`, `delete_image_element`; `create_sheet` accepts
  `format="custom"` with `width_mm` / `height_mm`.
- Public API `freecad.croquis.api` (sheets, strokes, layers, paper,
  PNG rendering, `describe()`) with typed errors (`errors.py`), documented
  in `docs/api.md`, for scripts and agents through the FreeCAD MCP server.

### Changed
- Sheet format version 2 (migration from v1 on read): new `images` layer
  and `elements` list. Croquis 0.2.0 drops the `elements` of a v2 sheet when
  it saves it (it does not keep unknown fields); later versions keep them.
- The version is read from `package.xml` only.
- The "New sketch sheet" and "Export sheet as PNG" commands go through
  the public API.

### Fixed
- Ctrl+C / Ctrl+V on the drawing board no longer reach FreeCAD's copy /
  paste of document objects.

## [0.2.0] - 2026-11-22

### Added
- Grease pencil, white highlight, straight line, tapered spline stroke
  (freehand fitted or control points), soft and whole-stroke erasers,
  vector stroke editing.
- Paper and layer panel on the drawing board.

### Changed
- Leaving the Croquis workbench saves and closes the drawing boards.

## [0.1.0] - 2026-11-22

### Added
- Drawing board with mechanical pencil and alcohol marker, tablet pressure,
  undo / redo.
- Sheet object stored in the document with a linked image plane, PNG export.
