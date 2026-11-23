# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
run_in_freecad.py (Croquis tests) - run pytest inside FreeCAD.

    freecadcmd tests/run_in_freecad.py --pass <pytest arguments>
    FreeCAD    tests/run_in_freecad.py --pass <pytest arguments>   (GUI tests)

Environment:
    CROQUIS_PYTEST_SITE   folder where pytest was installed with
                          `pip install --target` (added to sys.path)
    CROQUIS_JUNIT         JUnit XML report to write
    CROQUIS_VANILLA=1     do not put the repository on the path (tests of
                          files opened by FreeCAD without the addon)

freecadcmd may exit with status 0 even when the script fails: this
launcher always ends with os._exit(<pytest status>).
"""

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    args = sys.argv[sys.argv.index("--pass") + 1:] if "--pass" in sys.argv else []
    site = os.environ.get("CROQUIS_PYTEST_SITE")
    if site:
        sys.path.insert(0, site)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if os.environ.get("CROQUIS_VANILLA"):
        root = os.path.dirname(HERE)
        sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != root]
        os.chdir(os.environ.get("TMPDIR", "/tmp"))
    # In the GUI, sys.stdout goes to the report view: print to the console
    if sys.__stdout__ is not None:
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    import pytest
    junit = os.environ.get("CROQUIS_JUNIT")
    if junit:
        args.append("--junitxml=" + junit)
    args += ["-p", "no:cacheprovider", "--rootdir", os.path.dirname(HERE),
             "-c", os.path.join(os.path.dirname(HERE), "pyproject.toml")]
    return pytest.main(args)


try:
    code = int(main())
except SystemExit as exc:
    code = exc.code if isinstance(exc.code, int) else 1
except BaseException:
    traceback.print_exc()
    code = 3
sys.stdout.flush()
sys.stderr.flush()
os._exit(code)
