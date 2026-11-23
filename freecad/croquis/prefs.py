# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - settings and preference page
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
prefs.py (Croquis) - every setting of the workbench in one place
(parameter group Mod/Croquis), plus the "Croquis" page of Edit > Preferences.

Modules read settings through get() / put() with the keys defined in
DEFAULTS, never with their own ParamGet calls, so the preference page always
shows every setting.
"""

import FreeCAD as App

from .i18n import LANGUAGES, tr, tr_data

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/Croquis"

# key -> default value (its type selects the parameter accessor)
DEFAULTS = {
    "Language": "auto",
    "SheetFormat": "A4L",           # key of model.FORMATS
    "SheetDpi": 150,
    "SheetPaper": "transparent",    # key of model.PAPERS
    "SheetPlane": "XZ",             # XY / XZ / YZ
    "PressureCurve": 1.0,           # exponent applied to tablet pressure
    "MouseSpeedPressure": True,     # mouse: fast stroke = thinner, lighter
    "Smoothing": 4,                 # input stabilizer, 0 = raw input
    "UseQmlPanels": True,           # QML panels (else classic widgets)
}


def _grp():
    return App.ParamGet(PARAM_PATH)


def get(key):
    default = DEFAULTS[key]
    g = _grp()
    try:
        if isinstance(default, bool):
            return g.GetBool(key, default)
        if isinstance(default, int):
            return g.GetInt(key, default)
        if isinstance(default, float):
            return g.GetFloat(key, default)
        return g.GetString(key, default)
    except Exception:
        return default


def put(key, value):
    default = DEFAULTS[key]
    g = _grp()
    if isinstance(default, bool):
        g.SetBool(key, bool(value))
    elif isinstance(default, int):
        g.SetInt(key, int(value))
    elif isinstance(default, float):
        g.SetFloat(key, float(value))
    else:
        g.SetString(key, value or "")


# ----------------------------------------------------------------------
#  Preference page (Edit > Preferences > Croquis)
# ----------------------------------------------------------------------
def _qt():
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    return QtWidgets


def fill_sheet_combos(fmt, dpi, paper, plane):
    """Fill the combo boxes shared by the preference page and the
    "New sheet" dialog (data = stored key)."""
    from . import model
    for key, label, _w, _h in model.FORMATS:
        fmt.addItem(tr_data(label), key)
    for value in model.DPIS:
        dpi.addItem(tr("{dpi} dpi").format(dpi=value), value)
    for key, label, _color in model.PAPERS:
        paper.addItem(tr_data(label), key)
    plane.addItem(tr("XY (top)"), "XY")
    plane.addItem(tr("XZ (front)"), "XZ")
    plane.addItem(tr("YZ (side)"), "YZ")


def select_data(combo, value):
    i = combo.findData(value)
    combo.setCurrentIndex(i if i >= 0 else 0)


class PreferencePage(object):
    """FreeCAD Python preference page: `form` + loadSettings / saveSettings."""

    def __init__(self, parent=None):
        QtWidgets = _qt()
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(tr("General"))
        lay = QtWidgets.QVBoxLayout(self.form)

        # --- interface
        g = QtWidgets.QGroupBox(tr("Interface"))
        f = QtWidgets.QFormLayout(g)
        self.language = QtWidgets.QComboBox()
        self.language.addItem(tr("Same as FreeCAD"), "auto")
        for code, name in LANGUAGES:
            self.language.addItem(name, code)
        f.addRow(tr("Language:"), self.language)
        self.use_qml = QtWidgets.QCheckBox(tr("Use QML panels"))
        self.use_qml.setToolTip(
            tr("Off: every panel uses classic widgets (same functions). Useful when "
               "Qt Quick is missing or draws badly on this system."))
        f.addRow(self.use_qml)
        note = QtWidgets.QLabel(tr("Language changes apply after restarting FreeCAD."))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        f.addRow(note)
        lay.addWidget(g)

        # --- new sheets
        g = QtWidgets.QGroupBox(tr("New sheets"))
        f = QtWidgets.QFormLayout(g)
        self.fmt = QtWidgets.QComboBox()
        self.dpi = QtWidgets.QComboBox()
        self.paper = QtWidgets.QComboBox()
        self.plane = QtWidgets.QComboBox()
        fill_sheet_combos(self.fmt, self.dpi, self.paper, self.plane)
        f.addRow(tr("Format:"), self.fmt)
        f.addRow(tr("Resolution:"), self.dpi)
        f.addRow(tr("Paper:"), self.paper)
        f.addRow(tr("Image plane:"), self.plane)
        lay.addWidget(g)

        # --- input
        g = QtWidgets.QGroupBox(tr("Pen input"))
        f = QtWidgets.QFormLayout(g)
        self.curve = QtWidgets.QDoubleSpinBox()
        self.curve.setRange(0.2, 5.0)
        self.curve.setSingleStep(0.1)
        self.curve.setDecimals(1)
        self.curve.setToolTip(
            tr("Exponent applied to the tablet pressure: above 1 a harder press is "
               "needed, below 1 a light touch already gives a dark stroke."))
        f.addRow(tr("Pressure curve:"), self.curve)
        self.speed = QtWidgets.QCheckBox(
            tr("With a mouse, simulate pressure from speed (fast stroke = thinner)"))
        f.addRow(self.speed)
        self.smoothing = QtWidgets.QSpinBox()
        self.smoothing.setRange(0, 10)
        self.smoothing.setToolTip(tr("Steadies the hand: 0 keeps the raw input."))
        f.addRow(tr("Stroke smoothing:"), self.smoothing)
        lay.addWidget(g)
        lay.addStretch(1)

    def loadSettings(self):
        select_data(self.language, get("Language"))
        self.use_qml.setChecked(get("UseQmlPanels"))
        select_data(self.fmt, get("SheetFormat"))
        select_data(self.dpi, get("SheetDpi"))
        select_data(self.paper, get("SheetPaper"))
        select_data(self.plane, get("SheetPlane"))
        self.curve.setValue(get("PressureCurve"))
        self.speed.setChecked(get("MouseSpeedPressure"))
        self.smoothing.setValue(get("Smoothing"))

    def saveSettings(self):
        put("Language", self.language.currentData())
        put("UseQmlPanels", self.use_qml.isChecked())
        put("SheetFormat", self.fmt.currentData())
        put("SheetDpi", self.dpi.currentData())
        put("SheetPaper", self.paper.currentData())
        put("SheetPlane", self.plane.currentData())
        put("PressureCurve", self.curve.value())
        put("MouseSpeedPressure", self.speed.isChecked())
        put("Smoothing", self.smoothing.value())


def register():
    import FreeCADGui as Gui
    Gui.addPreferencePage(PreferencePage, "Croquis")
