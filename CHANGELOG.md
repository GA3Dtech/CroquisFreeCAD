# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- Development tooling: `pyproject.toml` (ruff, pytest markers),
  `.pre-commit-config.yaml`, `.gitattributes`.

### Changed
- The version is read from `package.xml` only.

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
