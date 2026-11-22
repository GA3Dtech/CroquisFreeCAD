# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - user interface translations
# Copyright (C) 2026 GA3Dtech
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or (at
# your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <https://www.gnu.org/licenses/>.
"""
i18n.py (Croquis) - translation of user-facing texts.

Source texts are written in English in the code and wrapped in tr("..."):

    from .i18n import tr
    QtWidgets.QLabel(tr("Paper:"))
    msg = tr("{n} stroke(s) on the sheet.").format(n=len(strokes))

Rules for code:
  * the argument of tr() must be a plain string literal (the extraction
    script reads the source code, it cannot see computed strings);
  * format AFTER translating, with named fields ({n}, {name}) so translators
    can move them in the sentence.

Each language is a JSON file in translations/<code>.json mapping the English
text to its translation. A missing or empty entry falls back to English, so
a partial translation is always usable. tools/i18n.py lists the missing
entries and adds them (empty) to every language file.

The language is the "Language" preference of the workbench: "auto" follows
the language of FreeCAD. It is read once per session: changing it needs a
restart of FreeCAD (menu and toolbar texts are created at startup).
"""

import os
import json

import FreeCAD as App

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/Croquis"
TRANSLATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translations")

# Code -> native name, in the order shown in the preferences
LANGUAGES = [
    ("en", "English"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("es", "Español"),
]

# FreeCAD "Language" preference (English names) -> code
_FREECAD_NAMES = {
    "english": "en", "french": "fr", "german": "de",
    "italian": "it", "spanish": "es",
}

_table = None
_code = None


def _freecad_language():
    """Code of the language FreeCAD runs in, 'en' when unknown."""
    try:
        name = App.ParamGet("User parameter:BaseApp/Preferences/General") \
            .GetString("Language", "")
    except Exception:
        name = ""
    name = name.strip().lower()
    for key, code in _FREECAD_NAMES.items():
        if name.startswith(key):
            return code
    if not name:
        try:
            try:
                from PySide import QtCore
            except ImportError:
                from PySide6 import QtCore
            code = QtCore.QLocale.system().name()[:2].lower()
            if code in dict(LANGUAGES):
                return code
        except Exception:
            pass
    return "en"


def preferred_language():
    """Value of the preference: 'auto' or a language code."""
    try:
        return App.ParamGet(PARAM_PATH).GetString("Language", "auto") or "auto"
    except Exception:
        return "auto"


def language():
    """Code of the language used by the workbench in this session."""
    global _code
    if _code is None:
        pref = preferred_language()
        _code = pref if pref in dict(LANGUAGES) else _freecad_language()
    return _code


def load_table(code):
    """{English: translation} of a language ({} for English or on error)."""
    if code == "en":
        return {}
    try:
        with open(os.path.join(TRANSLATIONS_DIR, code + ".json"), "r",
                  encoding="utf-8") as fh:
            data = json.load(fh)
        return {k: v for k, v in data.items() if not k.startswith("_") and v}
    except Exception as exc:
        App.Console.PrintWarning("Croquis: translation '%s' not loaded (%s)\n"
                                 % (code, exc))
        return {}


def tr(text):
    """Translation of the English `text` in the session language."""
    global _table
    if _table is None:
        _table = load_table(language())
    return _table.get(text, text)


def tr_data(text):
    """Translation of a text marked with N_() in a data table (model.py).
    Same lookup as tr(), under another name so tools/i18n.py does not
    expect a literal here."""
    global _table
    if _table is None:
        _table = load_table(language())
    return _table.get(text, text)
