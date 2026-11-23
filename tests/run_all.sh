#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Run every test level locally, like the CI does.
#
#   tests/run_all.sh [unit|render|freecad|vanilla|gui|all]
#
# FREECAD_APPIMAGE   FreeCAD AppImage to use
#                    (default ~/Appimages/FreeCAD_26.3rc1-Linux-x86_64.AppImage)
# PYTHON             Python with pytest, ruff, PySide6, numpy for the levels
#                    run outside FreeCAD (default .venv/bin/python, else python3)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LEVEL="${1:-all}"
APPIMAGE="${FREECAD_APPIMAGE:-$HOME/Appimages/FreeCAD_26.3rc1-Linux-x86_64.AppImage}"
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
    "$APPIMAGE" freecadcmd "$WORK/pyver.py" --pass "$WORK/pyver.txt" >/dev/null 2>&1 || true
    cat "$WORK/pyver.txt"
}

prepare_freecad() {
    local ver
    ver="$(fc_python_version)"
    export CROQUIS_PYTEST_SITE="$WORK/site-$ver"
    if [ ! -d "$CROQUIS_PYTEST_SITE/pytest" ]; then
        if command -v uv >/dev/null; then
            uv pip install -q --target "$CROQUIS_PYTEST_SITE" --python-version "$ver" pytest
        else
            "$PYTHON" -m pip install -q --target "$CROQUIS_PYTEST_SITE" pytest
        fi
    fi
}

run_fc() {   # binary(freecadcmd|FreeCAD) level [vanilla]
    local bin="$1" level="$2" home="$WORK/home-$2"
    echo "== $level (FreeCAD: $(basename "$APPIMAGE") $bin)"
    rm -rf "$home"; mkdir -p "$home/Mod"
    if [ "${3:-}" != vanilla ]; then
        ln -s "$ROOT" "$home/Mod/CroquisFreeCAD"
        unset CROQUIS_VANILLA
    else
        export CROQUIS_VANILLA=1
    fi
    FREECAD_USER_HOME="$home" FREECAD_QT_QPA_PLATFORM="${FREECAD_QT_QPA_PLATFORM:-offscreen}" \
    CROQUIS_JUNIT="$WORK/junit-$level.xml" \
        "$APPIMAGE" "$bin" "$ROOT/tests/run_in_freecad.py" --pass -q "$ROOT/tests/$level" \
        || status=1
    unset CROQUIS_VANILLA
}

case "$LEVEL" in
    unit|render) run_host "$LEVEL" ;;
    freecad) prepare_freecad; run_fc freecadcmd render; run_fc freecadcmd freecad ;;
    vanilla) prepare_freecad; run_fc freecadcmd vanilla vanilla ;;
    gui) prepare_freecad; run_fc FreeCAD gui ;;
    all)
        (cd "$ROOT" && "$PYTHON" -m ruff check freecad tools tests) || status=1
        python3 "$ROOT/tools/i18n.py" check >/dev/null || status=1
        run_host unit; run_host render
        prepare_freecad
        run_fc freecadcmd render; run_fc freecadcmd freecad
        run_fc freecadcmd vanilla vanilla
        run_fc FreeCAD gui
        ;;
    *) echo "unknown level $LEVEL"; exit 2 ;;
esac
echo "work folder: $WORK"
exit $status
