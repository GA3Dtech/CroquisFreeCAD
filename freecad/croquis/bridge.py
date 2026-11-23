# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - panel bridge and widget fallback
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
bridge.py (Croquis) - the generic engine that turns a panel model
(panel_model.py) into a user interface:

  Bridge      QObject exposed to QML as "bridge": sections, values, hidden
              parameters, actions, error, theme; slots setValue / trigger /
              pickColor / browse. Used by resources/qml/Panel.qml.
  WidgetForm  the same panel in classic widgets, built from the same model:
              the fallback when Qt Quick is unavailable, cannot use OpenGL,
              fails to load, or the "Use QML panels" preference is off.
  I18n        QObject exposed to QML as "i18n": i18n.tr("...") calls tr()
              (no qsTr: tools/i18n.py scans the .qml files for i18n.tr).

Adapted from ShowRoom (https://github.com/oficinerobotica/ShowRoom,
dtpanels/bridge.py: Bridge, _WidgetForm, make_theme; LGPL-2.1-or-later).
"""

from .i18n import tr, tr_data
from .qt import QtCore, QtGui, QtWidgets


# ----------------------------------------------------------------------
#  Theme
# ----------------------------------------------------------------------
def _mix(a, b, k):
    return QtGui.QColor(int(a.red() + (b.red() - a.red()) * k),
                        int(a.green() + (b.green() - a.green()) * k),
                        int(a.blue() + (b.blue() - a.blue()) * k)).name()


def make_theme(widget=None):
    """Colours and font of the running FreeCAD theme (light or dark),
    passed to QML so the panels follow it."""
    pal = widget.palette() if widget is not None else QtWidgets.QApplication.palette()
    win = QtGui.QColor(pal.color(QtGui.QPalette.Window))
    txt = QtGui.QColor(pal.color(QtGui.QPalette.WindowText))
    base = QtGui.QColor(pal.color(QtGui.QPalette.Base))
    accent = QtGui.QColor(pal.color(QtGui.QPalette.Highlight))
    if abs(txt.lightness() - win.lightness()) < 80:     # unreadable pair: force contrast
        txt = QtGui.QColor("#f2f2f2" if win.lightness() < 128 else "#1a1a1a")
    font = QtGui.QFontInfo(QtWidgets.QApplication.font())
    px = font.pixelSize() if font.pixelSize() > 0 else 13
    usable = abs(base.lightness() - win.lightness()) > 6
    return {"dark": win.lightness() < 128, "window": win.name(), "text": txt.name(),
            "s": max(0.9, px / 12.0), "family": font.family(),
            "card": _mix(win, txt, 0.05),
            "field": base.name() if usable else _mix(win, txt, 0.11),
            "line": _mix(win, txt, 0.22), "muted": _mix(win, txt, 0.6),
            "accent": accent.name(),
            "accentText": "#ffffff" if accent.lightness() < 150 else "#101010",
            "bad": "#d6453d" if win.lightness() >= 128 else "#f0736b"}


class I18n(QtCore.QObject):
    """i18n.tr("...") in QML (the texts are collected by tools/i18n.py)."""

    @QtCore.Slot(str, result=str)
    def tr(self, text):
        return tr_data(text)


# ----------------------------------------------------------------------
#  Bridge
# ----------------------------------------------------------------------
class Bridge(QtCore.QObject):
    """Model <-> user interface. Every change goes through the model."""

    valuesChanged = QtCore.Signal()
    stateChanged = QtCore.Signal()
    heightChanged = QtCore.Signal(float)
    closeRequested = QtCore.Signal()

    def __init__(self, model, parent=None, theme=None):
        QtCore.QObject.__init__(self, parent)
        self.model = model
        self._theme = theme or make_theme()
        self._sections = model.sections()
        self._actions = model.public_actions()

    # --- properties read by QML
    def _values(self):
        return self.model.values()

    sections = QtCore.Property("QVariant", lambda self: self._sections, constant=True)
    actions = QtCore.Property("QVariant", lambda self: self._actions, constant=True)
    theme = QtCore.Property("QVariant", lambda self: self._theme, constant=True)
    title = QtCore.Property(str, lambda self: self.model.title, constant=True)
    hint = QtCore.Property(str, lambda self: self.model.hint_text(), notify=stateChanged)
    values = QtCore.Property("QVariant", _values, notify=valuesChanged)
    hidden = QtCore.Property("QVariant", lambda self: self.model.hidden(), notify=valuesChanged)
    error = QtCore.Property(str, lambda self: self.model.error, notify=stateChanged)

    # --- slots
    @QtCore.Slot(str, "QVariant")
    def setValue(self, name, value):
        self.model.set(name, value)
        self.refresh()

    @QtCore.Slot(str)
    def trigger(self, name):
        res = self.model.trigger(name)
        self.refresh()
        if res == "close":
            self.closeRequested.emit()

    @QtCore.Slot(str)
    def pickColor(self, name):
        p = self.model.param(name)
        col = QtWidgets.QColorDialog.getColor(QtGui.QColor(p.get()), None, p.label)
        if col.isValid():
            self.setValue(name, col.name())

    @QtCore.Slot(str)
    def browse(self, name):
        p = self.model.param(name)
        path, _flt = QtWidgets.QFileDialog.getOpenFileName(None, p.label, p.get() or "",
                                                           p.filter or "")
        if path:
            self.setValue(name, path)

    @QtCore.Slot(float)
    def setContentHeight(self, h):
        self.heightChanged.emit(h)

    def refresh(self):
        self.valuesChanged.emit()
        self.stateChanged.emit()


# ----------------------------------------------------------------------
#  Widget fallback
# ----------------------------------------------------------------------
def _color_icon(color):
    pix = QtGui.QPixmap(16, 16)
    pix.fill(QtGui.QColor(color or "#000000"))
    return QtGui.QIcon(pix)


class WidgetForm(QtWidgets.QWidget):
    """Classic widgets for a panel model: same sections, parameters and
    actions as the QML form, built automatically."""

    def __init__(self, bridge, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.bridge = bridge
        self.editors = {}       # name -> (public param, editor widget, label widget)
        self.action_buttons = {}
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.hint = QtWidgets.QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: gray;")
        lay.addWidget(self.hint)
        for sec in bridge.sections:
            box = QtWidgets.QGroupBox(sec["title"]) if sec["title"] else QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(box)
            if not sec["title"]:
                form.setContentsMargins(0, 0, 0, 0)
            for p in sec["params"]:
                w = self._editor(p)
                w.setToolTip(p["tip"])
                if p["kind"] in ("note", "list"):
                    label = QtWidgets.QLabel(p["label"]) if p["label"] else None
                    if label is not None:
                        form.addRow(label)
                    form.addRow(w)
                else:
                    label = QtWidgets.QLabel(p["label"])
                    form.addRow(label, w)
                self.editors[p["name"]] = (p, w, label)
            lay.addWidget(box)
        row = QtWidgets.QHBoxLayout()
        for a in bridge.actions:
            b = QtWidgets.QPushButton(a["label"])
            b.setToolTip(a["tip"])
            b.setDefault(a["primary"])
            b.clicked.connect(lambda _c=False, n=a["name"]: bridge.trigger(n))
            row.addWidget(b)
            self.action_buttons[a["name"]] = b
        lay.addLayout(row)
        self.err = QtWidgets.QLabel()
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: #d6453d;")
        lay.addWidget(self.err)
        lay.addStretch(1)
        bridge.valuesChanged.connect(self.sync)
        bridge.stateChanged.connect(self.sync_state)
        self.sync()
        self.sync_state()

    def _editor(self, p):
        name, kind, b = p["name"], p["kind"], self.bridge
        if kind == "bool":
            w = QtWidgets.QCheckBox()
            w.toggled.connect(lambda v: b.setValue(name, v))
        elif kind == "choice":
            w = QtWidgets.QComboBox()
            for value, label in zip(p["options"], p["optionLabels"]):
                w.addItem(label, value)
            w.currentIndexChanged.connect(lambda _i: b.setValue(name, w.currentData()))
        elif kind in ("number", "int"):
            w = QtWidgets.QSpinBox() if kind == "int" else QtWidgets.QDoubleSpinBox()
            if kind == "number":
                w.setDecimals(p["decimals"])
            w.setRange(p["min"], p["max"]) if kind == "number" \
                else w.setRange(int(p["min"]), int(p["max"]))
            w.setSingleStep(p["step"] if kind == "number" else max(1, int(p["step"])))
            if p["unit"]:
                w.setSuffix(" " + p["unit"])
            w.setKeyboardTracking(False)
            w.valueChanged.connect(lambda v: b.setValue(name, v))
        elif kind == "color":
            w = QtWidgets.QPushButton()
            w.clicked.connect(lambda: b.pickColor(name))
        elif kind == "vector":
            w = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            w.spins = []
            for _i in range(3):
                s = QtWidgets.QDoubleSpinBox()
                s.setRange(-1e9, 1e9)
                s.setDecimals(p["decimals"])
                s.setKeyboardTracking(False)
                s.valueChanged.connect(
                    lambda _v: b.setValue(name, [x.value() for x in w.spins]))
                hl.addWidget(s)
                w.spins.append(s)
        elif kind == "path":
            w = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            w.edit = QtWidgets.QLineEdit()
            w.edit.editingFinished.connect(lambda: b.setValue(name, w.edit.text()))
            btn = QtWidgets.QPushButton(tr("Browse…"))
            btn.clicked.connect(lambda: b.browse(name))
            hl.addWidget(w.edit, 1)
            hl.addWidget(btn)
        elif kind == "text":
            w = QtWidgets.QLineEdit()
            w.editingFinished.connect(lambda: b.setValue(name, w.text()))
        elif kind == "list":
            w = QtWidgets.QListWidget()
            w.setMaximumHeight(140)
        else:   # note
            w = QtWidgets.QLabel()
            w.setWordWrap(True)
        if p["readonly"] and kind not in ("note", "list"):
            w.setEnabled(False)
        return w

    def sync(self):
        values = self.bridge.values
        hidden = set(self.bridge.hidden)
        for name, (p, w, label) in self.editors.items():
            v = values.get(name)
            kind = p["kind"]
            w.blockSignals(True)
            try:
                if kind == "bool":
                    w.setChecked(bool(v))
                elif kind == "choice":
                    w.setCurrentIndex(max(0, w.findData(v)))
                elif kind in ("number", "int") and v is not None:
                    w.setValue(v)
                elif kind == "color":
                    w.setIcon(_color_icon(v))
                    w.setText(v or "")
                elif kind == "vector" and v is not None:
                    for s, x in zip(w.spins, v):
                        s.blockSignals(True)
                        s.setValue(x)
                        s.blockSignals(False)
                elif kind == "path":
                    w.edit.setText(v or "")
                elif kind == "text":
                    if not w.hasFocus():
                        w.setText(v or "")
                elif kind == "list":
                    w.clear()
                    w.addItems([str(x) for x in (v or [])])
                elif kind == "note":
                    w.setText(v or "")
            finally:
                w.blockSignals(False)
            for x in (w, label):
                if x is not None:
                    x.setVisible(name not in hidden)

    def sync_state(self):
        self.hint.setText(self.bridge.hint)
        self.hint.setVisible(bool(self.bridge.hint))
        self.err.setText(self.bridge.error)
        self.err.setVisible(bool(self.bridge.error))


# ----------------------------------------------------------------------
#  Paper / layers palette (custom QML, rule 2)
# ----------------------------------------------------------------------
class LayersBridge(QtCore.QObject):
    """State of resources/qml/LayersPanel.qml: papers, the current paper,
    the drawable layers (top first) with visibility and opacity. Changes go
    to the canvas (set_paper / set_layer); no logic here."""

    changed = QtCore.Signal()

    def __init__(self, canvas, parent=None, theme=None):
        QtCore.QObject.__init__(self, parent)
        from . import model
        self.canvas = canvas
        self._theme = theme or make_theme()
        self._papers = [{"key": k, "label": tr_data(label), "color": color or ""}
                        for k, label, color in model.PAPERS]
        users = {}
        for key in model.TOOL_KEYS:
            t = model.TOOLS[key]
            if t["kind"] != "eraser":
                users.setdefault(t["layer"], []).append(tr_data(t["label"]))
        self._layer_defs = [(k, tr_data(label), ", ".join(users.get(k, [])))
                            for k, label, _b in reversed(model.LAYERS)
                            if k in model.ERASABLE_LAYERS]
        signal = getattr(canvas, "sheetEdited", None)
        if signal is not None:
            signal.connect(self.changed)

    def _layers(self):
        info = self.canvas.sheet.layers
        return [{"key": k, "label": label, "tools": tools,
                 "visible": bool(info[k]["visible"]), "opacity": float(info[k]["opacity"])}
                for k, label, tools in self._layer_defs]

    theme = QtCore.Property("QVariant", lambda self: self._theme, constant=True)
    papers = QtCore.Property("QVariant", lambda self: self._papers, constant=True)
    paper = QtCore.Property(str, lambda self: self.canvas.sheet.paper, notify=changed)
    layers = QtCore.Property("QVariant", _layers, notify=changed)

    @QtCore.Slot(str)
    def setPaper(self, key):
        self.canvas.set_paper(key)
        self.changed.emit()

    @QtCore.Slot(str, bool)
    def setVisible(self, key, visible):
        self.canvas.set_layer(key, visible=visible)
        self.changed.emit()

    @QtCore.Slot(str, float)
    def setOpacity(self, key, opacity):
        self.canvas.set_layer(key, opacity=max(0.0, min(1.0, opacity)))
        self.changed.emit()
