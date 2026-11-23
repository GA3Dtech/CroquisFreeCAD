#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
tools/i18n.py (Croquis) - maintain the translation files.

Reads every tr("...") and N_("...") call of the workbench sources (Python AST, no FreeCAD
needed) and every i18n.tr("...") call of the QML files (resources/qml), and
compares the texts with freecad/croquis/translations/*.json.

    python3 tools/i18n.py check            # report missing / unused entries
    python3 tools/i18n.py update           # add missing entries (empty) to
                                           # every file, drop unused ones
    python3 tools/i18n.py new <code>       # create translations/<code>.json
    python3 tools/i18n.py export <file>    # write the English source texts

An empty entry falls back to English at run time: translators fill the
values, keep the {named} fields and the HTML tags as they are.
Exit status of 'check' is 1 when something is missing (usable in CI).
"""

import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "freecad", "croquis")
TRANS = os.path.join(PKG, "translations")


# QML: i18n.tr("...") with a plain string literal (double quotes)
QML_TR = re.compile(r'i18n\.tr\(\s*"((?:[^"\\]|\\.)*)"\s*\)')


def qml_texts(texts):
    for dirpath, _dirs, files in os.walk(PKG):
        for name in sorted(files):
            if not name.endswith(".qml"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, "r", encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    for m in QML_TR.finditer(line):
                        text = json.loads('"%s"' % m.group(1))
                        where = "%s:%d" % (os.path.relpath(path, ROOT), lineno)
                        texts.setdefault(text, []).append(where)
                    if "i18n.tr(" in line and not QML_TR.search(line):
                        print("warning: i18n.tr() argument is not a literal at %s:%d"
                              % (os.path.relpath(path, ROOT), lineno))


def source_texts():
    """{English text: [file:line, ...]} of every tr() / N_() call of the
    Python sources and every i18n.tr() call of the QML files."""
    texts = {}
    for dirpath, _dirs, files in os.walk(PKG):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                fname = f.id if isinstance(f, ast.Name) else \
                    f.attr if isinstance(f, ast.Attribute) else None
                if fname not in ("tr", "N_") or not node.args:
                    continue
                arg = node.args[0]
                where = "%s:%d" % (os.path.relpath(path, ROOT), node.lineno)
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    texts.setdefault(arg.value, []).append(where)
                else:
                    print("warning: tr() argument is not a literal at %s" % where)
    qml_texts(texts)
    return texts


def language_files():
    if not os.path.isdir(TRANS):
        return []
    return sorted(os.path.join(TRANS, n) for n in os.listdir(TRANS) if n.endswith(".json"))


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def check(texts):
    bad = False
    for path in language_files():
        data = load(path)
        missing = [t for t in texts if not data.get(t)]
        unused = [k for k in data if not k.startswith("_") and k not in texts]
        print("%s: %d text(s), %d missing, %d unused"
              % (os.path.basename(path), len(texts), len(missing), len(unused)))
        for t in missing:
            print("   missing: %r  (%s)" % (t, texts[t][0]))
        for t in unused:
            print("   unused : %r" % t)
        bad = bad or bool(missing)
    return 1 if bad else 0


def update(texts):
    for path in language_files():
        data = load(path)
        out = {k: v for k, v in data.items() if k.startswith("_")}
        for t in texts:                      # source order, unused dropped
            out[t] = data.get(t, "")
        save(path, out)
        print("%s updated" % os.path.basename(path))
    return 0


def main(argv):
    texts = source_texts()
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "check":
        return check(texts)
    if cmd == "update":
        return update(texts)
    if cmd == "new" and len(argv) > 2:
        os.makedirs(TRANS, exist_ok=True)
        path = os.path.join(TRANS, argv[2] + ".json")
        if os.path.exists(path):
            print("%s already exists" % path)
            return 1
        save(path, dict([("_language", argv[2])] + [(t, "") for t in texts]))
        print("%s created" % path)
        return 0
    if cmd == "export" and len(argv) > 2:
        save(argv[2], list(texts))
        print("%d text(s) written to %s" % (len(texts), argv[2]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
