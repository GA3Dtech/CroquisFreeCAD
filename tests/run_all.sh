#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Run every test level locally, like the CI does.
#
#   tests/run_all.sh [unit|render|freecad|vanilla|gui|all]
#
# FREECAD_APPIMAGE   FreeCAD AppImage to use, or the AppRun of an extracted
#                    AppImage (CI: no FUSE on the runners)
#                    (default ~/Appimages/FreeCAD_26.3rc3-Linux-x86_64.AppImage)
# CROQUIS_WORK       work folder (default: a new temporary folder); keep the
#                    same one for "freecad" then "vanilla" so the vanilla
#                    tests also open the files written by the FreeCAD tests
# PYTHON             Python with pytest, ruff, PySide6, numpy for the levels
#                    run outside FreeCAD (default .venv/bin/python, else python3)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LEVEL="${1:-all}"
APPIMAGE="${FREECAD_APPIMAGE:-$HOME/Appimages/FreeCAD_26.3rc3-Linux-x86_64.AppImage}"
PYTHON="${PYTHON:-$( [ -x "$ROOT/.venv/bin/python" ] && echo "$ROOT/.venv/bin/python" || echo python3)}"
WORK="${CROQUIS_WORK:-$(mktemp -d -t croquis-tests-XXXXXX)}"
export CROQUIS_ARTIFACTS="${CROQUIS_ARTIFACTS:-$WORK/artifacts}"
export CROQUIS_OUTPUT="${CROQUIS_OUTPUT:-$WORK/output}"
mkdir -p "$CROQUIS_ARTIFACTS" "$CROQUIS_OUTPUT"
status=0

run_host() {   # level marker
    echo "== $1 (host Python)"
    (cd "$ROOT" && "$PYTHON" -m pytest -q "tests/$1") || status=1
}

fc_python_version() {
    printf 'import sys\nopen(sys.argv[-1], "w").write("%%d.%%d" %% sys.version_info[:2])\n' > "$WORK/pyver.py"
    FREECAD_USER_HOME="$WORK/home-pyver" \
        "$APPIMAGE" freecadcmd "$WORK/pyver.py" --pass "$WORK/pyver.txt" >/dev/null 2>&1 || true
    cat "$WORK/pyver.txt"
}

prepare_freecad() {
    local ver
    ver="$(fc_python_version)"
    echo "FreeCAD Python: $ver"
    export CROQUIS_PYTEST_SITE="$WORK/site-$ver"
    if [ ! -d "$CROQUIS_PYTEST_SITE/pytest" ]; then
        # pytest is pure Python: any pip can install it for FreeCAD's Python
        if command -v uv >/dev/null; then
            uv pip install -q --target "$CROQUIS_PYTEST_SITE" --python-version "$ver" pytest
        elif "$PYTHON" -m pip --version >/dev/null 2>&1; then
            "$PYTHON" -m pip install -q --target "$CROQUIS_PYTEST_SITE" pytest
        else
            python3 -m pip install -q --target "$CROQUIS_PYTEST_SITE" pytest
        fi
    fi
}

run_fc() {   # binary(freecadcmd|FreeCAD) level [vanilla]
    local bin="$1" level="$2" report="$2-$1" home="$WORK/home-$2-$1"
    echo "== $level (FreeCAD: $(basename "$APPIMAGE") $bin)"
    rm -rf "$home"; mkdir -p "$home/Mod"
    if [ "${3:-}" != vanilla ]; then
        ln -s "$ROOT" "$home/Mod/CroquisFreeCAD"
        unset CROQUIS_VANILLA
    else
        export CROQUIS_VANILLA=1
    fi
    FREECAD_USER_HOME="$home" FREECAD_QT_QPA_PLATFORM="${FREECAD_QT_QPA_PLATFORM:-offscreen}" \
    CROQUIS_JUNIT="$WORK/junit-$report.xml" \
        "$APPIMAGE" "$bin" "$ROOT/tests/run_in_freecad.py" --pass -q "$ROOT/tests/$level" \
        || status=1
    unset CROQUIS_VANILLA
}

case "$LEVEL" in
    unit|render) run_host "$LEVEL" ;;
    freecad) prepare_freecad; run_fc freecadcmd render; run_fc freecadcmd freecad ;;
    vanilla) prepare_freecad; run_fc freecadcmd vanilla vanilla ;;
    gui) prepare_freecad; run_fc FreeCAD gui; run_fc FreeCAD vanilla vanilla ;;
    all)
        (cd "$ROOT" && "$PYTHON" -m ruff check freecad tools tests) || status=1
        python3 "$ROOT/tools/i18n.py" check >/dev/null || status=1
        run_host unit; run_host render
        prepare_freecad
        run_fc freecadcmd render; run_fc freecadcmd freecad
        run_fc freecadcmd vanilla vanilla
        run_fc FreeCAD gui; run_fc FreeCAD vanilla vanilla
        ;;
    *) echo "unknown level $LEVEL"; exit 2 ;;
esac
echo "work folder: $WORK"
exit $status
