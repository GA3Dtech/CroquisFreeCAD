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
- Public API `freecad.croquis.api` (sheets, strokes, layers, paper,
  PNG rendering, `describe()`) with typed errors (`errors.py`), documented
  in `docs/api.md`, for scripts and agents through the FreeCAD MCP server.

### Changed
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
