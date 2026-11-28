# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- New sheet: "Custom size" format with width and height in mm (remembered),
  and the 3D guide background in three styles: black edges on white,
  wireframe, shaded.
- The radius of an arc can be changed with the edit tool: drag the handle
  at its top (also to the other side); its ends stay in place.
- *Sheet size…* on the board enlarges (or trims) the sheet on any side
  afterwards; strokes, pictures and texts keep their place on the paper and
  in 3D, and a 3D guide is captured again. API 1.9.0: `resize_sheet`.
- *Sketch on a face*: click a face of the model (or select it first) and a
  transparent sheet is laid on it, framed on the face, facing out, up as
  seen on screen, board open: annotate anything in a click. A curved face
  gets the tangent plane at the click. API 1.10.0: `create_sheet_on_face`.

### Fixed
- Sheets with a scale other than 1 (camera orientation, A3 and other
  formats, scale tool) got a 3D guide framed on the unscaled sheet: what was
  traced over it came out too big in the 3D view (about x2 for an A3 on the
  camera plane). The guide now frames the image plane as it is in 3D.
- The board opened with the sheet fitted to a transient size: the sheet now
  stays fitted to the window (opening, tab resized) until you zoom or pan.

## [0.3.0] - 2026-11-24

### Fixed
- A shape drawn right after the arrow tool came out with arrow heads: with
  the arrow as last drawing tool, shapes are plain vector lines.

### Added
- Shapes can be reshaped with the edit tool (V): drag a corner of the box,
  the ends of an arc, or the whole shape; the shape is redrawn with its
  brush and hand-drawn look (raster and vector shapes alike).
- PDF export (board button, "Export sheets as PDF" for the selection, API
  `export_pdf`): a page per sheet at its size in mm; line, spline and arrow
  strokes and texts are vector graphics, pencil / marker layers, pictures
  and paper are high resolution pictures; the 3D guide is never exported.
- Styled shapes (key O): one drop-down button for circle, ellipse,
  rectangle (Shift: square) and arc, remembering the last one; drawn with
  the last drawing tool (pencil, marker, spline...) with a slight
  hand-drawn look (option); ordinary strokes (undo, erasers, exports).
- "Show / hide the sketches" (shortcut C, V): one checkable button shows or
  hides every sketch of the document; it stays pressed while they are
  shown. API 1.7: `sheets_visible`, `set_sheets_visible`.

### Changed
- One way to create sheets: "New sketch sheet" defaults to the size of the
  3D view, in the camera plane at scale, on transparent paper, with a 3D
  wireframe guide as background (shown on the board, never exported); the
  background can also be a capture of the 3D view or nothing. "Capture 3D
  view" opens the same dialog with the capture preselected (with a board
  open it still puts the capture on that board).
- "Camera orientation" is a plane choice everywhere (New sheet, preferences,
  API `plane="camera"`, sheets from the clipboard); API `format="view"`.
- Croquis is a passive workbench: documentation and docstrings describe a
  generic Python API for scripts, macros and addons; no agent / MCP
  positioning. README mentions that an AI coding agent writes the code.

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
- 3D view guide (underlay) aligned on the sheet plane: orthographic view
  along the sheet's normal, framed exactly on the sheet in true size, styles
  edges / wireframe / shaded; stored apart from the strokes in the
  `.FCStd`, shown on the board, never in the image plane nor the exports;
  "3D guide…" on the board. The navigation cube is no longer drawn into
  captures.
- API 1.4: `capture_underlay` (mode "plane"), `refresh_underlay`,
  `clear_underlay`; `render_png(include_underlay=True)`.
- Arrow tool (`A`): straight or curved vector arrows, heads at the start
  and / or end (open, filled, dot, size), editable with the edit tool.
- API 1.3: `add_arrow`; strokes accept `"heads"` for arrows.
- Text tool (`T`): text boxes with font, size (mm), bold, italic, colour,
  alignment, wrap width, frame, white background and callout arrow (its tip
  stays put when the box moves); typing keeps every key (no tool change, no
  FreeCAD shortcut); texts stay above strokes and erasers. API 1.6:
  `add_text`, `list_texts`, `edit_text`, `delete_text`.
- Scale tool (`K`) on the board: drag over something of known size, type
  its real length, and the sheet takes the right size in 3D; the scale is
  shown in the status line. API 1.5: `set_scale` (value or segment +
  length); `get_sheet` reports `scale`.
- A sheet created from a 3D view capture is placed in the camera plane, at
  the focal distance, scaled so it lies exactly on the captured view
  (orthographic and perspective); `capture_3d_view(align="camera")` by
  default, `"plane"` for the former XZ placement.
- API 1.2: `capture_3d_view`, `restore_image_view` (GUI only).
- API 1.1: `add_image`, `new_sheet_from_image`, `list_images`,
  `update_image_element`, `delete_image_element`; `create_sheet` accepts
  `format="custom"` with `width_mm` / `height_mm`.
- Public API `freecad.croquis.api` (sheets, strokes, layers, paper,
  PNG rendering, `describe()`) with typed errors (`errors.py`), documented
  in `docs/api.md`, for scripts, macros and other addons.

### Changed
- Supported FreeCAD versions: 1.1.x, 26.3 and 27.1 (development); 1.0 is
  dropped (`freecadmin` 1.1.0). The CI tests 1.1.4, 26.3rc2 and a 27.1
  weekly build.
- Known limitation: a file saved WITHOUT the GUI (API in `freecadcmd`)
  has no GUI data; FreeCAD 1.1 then opens its image
  plane hidden when the addon is absent (26.3 and later show it). Files
  saved from the GUI are not affected.
- New sheets go into one "Croquis" group of the document instead of
  piling up at the root of the tree.
- Sheet format version 2 (migration from v1 on read): new `images` layer
  and `elements` list. Croquis 0.2.0 drops the `elements` of a v2 sheet when
  it saves it (it does not keep unknown fields); later versions keep them.
- The version is read from `package.xml` only.
- The "New sketch sheet" and "Export sheet as PNG" commands go through
  the public API.

### Fixed
- Cool, warm and neutral greys were hard to tell apart: cool greys now lean
  clearly to blue and warm greys to yellow / brown; the palette selector
  shows a colour strip and a tooltip for each family.
- The "edges" and "wireframe" guide styles really switch shapes to
  wireframe (the display modes were queried with the wrong method, so
  faces stayed shaded).
- The board's side panel could be dragged to zero width and looked lost:
  it can no longer collapse, a "Panel" button shows / hides it, the menu
  has "Show the Croquis panel", and editing a sheet again shows it.
- Headless use (API in `freecadcmd`) on a
  machine without display no longer aborts with FreeCAD 1.1: Qt is forced
  to its offscreen platform there (the 1.1 AppImage launcher imposes xcb).
- "Back to this view", captures and the 3D guide stop a running camera
  animation first (with a real display the animation overwrote the camera).
- Updating a sketch no longer resets the size of its image plane: a sheet
  has a `Scale` property (3D mm per sheet mm), and scaling the image plane
  by hand updates it instead of being undone (in the GUI, the image plane
  resized itself when its picture changed).
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
