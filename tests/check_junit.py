#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exit 1 when a JUnit report has failures or errors, or when a report is
missing / empty (FreeCAD may die before pytest writes anything)."""

import sys
import xml.etree.ElementTree as ET


def main(paths):
    if not paths:
        print("no JUnit report")
        return 1
    bad = 0
    for path in paths:
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError) as exc:
            print("%s: unreadable (%s)" % (path, exc))
            bad += 1
            continue
        suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
        tests = sum(int(s.get("tests", 0)) for s in suites)
        fails = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
        print("%s: %d tests, %d failures / errors" % (path, tests, fails))
        if fails or not tests:
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
