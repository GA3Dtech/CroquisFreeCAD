# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - QML hosting
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
qml_host.py (Croquis) - where panels are shown, QML or widgets:

  quick_usable()            Qt Quick importable, allowed by the preference
                            "Use QML panels" and drawing with OpenGL
  make_view(source, ctx)    a QQuickWidget for resources/qml/<source>,
                            errors raised with QML's own details
  build_panel(model)        the panel widget (QML, else WidgetForm)
  PanelDialog / run_dialog  a dialog around a panel, with OK / Cancel and
                            the model's session transaction

Pitfalls handled here (met by ShowRoom and FreeCAD-Nxt):
  * Qt Quick must draw with OpenGL like the 3D view: QSG_RHI_BACKEND and
    QQuickWindow.setGraphicsApi(OpenGL) before the first QQuickWidget,
    otherwise Qt 6 on Windows shows empty panels ("Failed to get a QRhi");
    when that is no longer possible, the widget fallback is used;
  * FreeCAD's PySide module has no QtQuick: PySide6 (Qt 6) or PySide2
    (FreeCAD 1.0, Qt 5) imported lazily, at first use only;
  * the bridge must outlive the QML scene (parent = the view), and the
    view is never resized from inside a QML binding (0 ms timer).

Adapted from FreeCAD-Nxt (https://github.com/obelisk79/FreeCAD-Nxt,
freecad/nxt/ui/quick_host.py and core/qtquick.py) and ShowRoom
(https://github.com/oficinerobotica/ShowRoom, dtpanels/bridge.py), both
LGPL-2.1-or-later.
"""

import os

from . import PACKAGE_DIR, prefs
from .bridge import Bridge, I18n, WidgetForm, make_theme
from .qt import QtCore, QtGui, QtWidgets

QML_DIR = os.path.join(PACKAGE_DIR, "resources", "qml")

_quick = {}     # cache: "ok" -> bool, "modules" -> (QtQml, QtQuick, QtQuickWidgets)
FORCE_WIDGETS = False       # tests: behave as if Qt Quick were unavailable


class QmlLoadError(RuntimeError):
    """A QML file failed to load; the message lists QML's errors."""


def quick_modules():
    """(QtQml, QtQuick, QtQuickWidgets) or ImportError."""
    if "modules" not in _quick:
        try:
            from PySide6 import QtQml, QtQuick, QtQuickWidgets
        except ImportError:
            from PySide2 import QtQml, QtQuick, QtQuickWidgets
        _quick["modules"] = (QtQml, QtQuick, QtQuickWidgets)
    return _quick["modules"]


def quick_usable():
    """True when QML panels can be used (preference on, Qt Quick present,
    OpenGL graphics API)."""
    if FORCE_WIDGETS or not prefs.get("UseQmlPanels"):
        return False
    if "ok" in _quick:
        return _quick["ok"]
    try:
        os.environ.setdefault("QSG_RHI_BACKEND", "opengl")
        _qml, quick, _widgets = quick_modules()
        ok = True
        try:        # Qt 6 only; Qt 5 always draws with OpenGL
            api = quick.QSGRendererInterface.GraphicsApi
            if quick.QQuickWindow.graphicsApi() not in (api.OpenGL, api.OpenGLRhi):
                quick.QQuickWindow.setGraphicsApi(api.OpenGL)
            ok = quick.QQuickWindow.graphicsApi() in (api.OpenGL, api.OpenGLRhi)
        except AttributeError:
            pass
    except Exception:
        ok = False
    _quick["ok"] = ok
    return ok


def make_view(source, context, parent=None, floating=False):
    """QQuickWidget showing resources/qml/<source>, with `context` as
    context properties. Raises QmlLoadError with QML's messages."""
    _qml, _quick_mod, qw = quick_modules()
    view = qw.QQuickWidget(parent)
    view.setResizeMode(qw.QQuickWidget.SizeViewToRootObject if floating
                       else qw.QQuickWidget.SizeRootObjectToView)
    if floating:
        view.setAttribute(QtCore.Qt.WA_AlwaysStackOnTop)
        view.setClearColor(QtGui.QColor(0, 0, 0, 0))
    view.engine().addImportPath(QML_DIR)
    ctx = view.rootContext()
    for name, value in context.items():
        ctx.setContextProperty(name, value)
    view.setSource(QtCore.QUrl.fromLocalFile(os.path.join(QML_DIR, source)))
    if view.status() != qw.QQuickWidget.Ready:
        detail = "\n".join(e.toString() for e in view.errors())
        view.deleteLater()
        raise QmlLoadError("%s failed to load:\n%s" % (source, detail))
    return view


def _fit_height(view, bridge, root_property="contentHeight"):
    """Follow the QML content height without resizing from a binding."""
    pending = {"h": int(view.rootObject().property(root_property) or 200) + 2}
    timer = QtCore.QTimer(view)
    timer.setSingleShot(True)
    timer.setInterval(0)

    def apply():
        if view.height() != pending["h"]:
            view.setFixedHeight(pending["h"])

    def request(h):
        pending["h"] = int(h) + 2
        timer.start()
    timer.timeout.connect(apply)
    bridge.heightChanged.connect(request)
    view.setFixedHeight(pending["h"])


def build_panel(model, parent=None):
    """(widget, bridge, "qml" | "widgets") for a panel model."""
    bridge = Bridge(model, theme=make_theme(parent))
    if quick_usable():
        try:
            view = make_view("Panel.qml", {"bridge": bridge, "i18n": I18n(bridge)}, parent)
            bridge.setParent(view)      # the bridge outlives the QML scene
            view.setMinimumWidth(200)
            _fit_height(view, bridge)
            return view, bridge, "qml"
        except Exception as exc:
            import FreeCAD as App
            App.Console.PrintWarning("Croquis: QML panel unavailable (%s), using widgets\n"
                                     % exc)
    form = WidgetForm(bridge, parent)
    bridge.setParent(form)
    return form, bridge, "widgets"


class PanelDialog(QtWidgets.QDialog):
    """A panel in a dialog with OK / Cancel. With a model transaction and
    a document, the whole session is one undo step: OK commits it, Cancel
    aborts it and leaves the document unchanged."""

    def __init__(self, model, doc=None, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.model = model
        self.doc = doc
        self.setWindowTitle(model.title)
        lay = QtWidgets.QVBoxLayout(self)
        self.panel, self.bridge, self.kind = build_panel(model, self)
        lay.addWidget(self.panel)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.bridge.closeRequested.connect(self.accept)
        self._open = False
        if model.transaction and doc is not None:
            doc.openTransaction(model.transaction)
            self._open = True

    def accept(self):
        if not self.model.accept():
            self.bridge.refresh()       # shows model.error
            return
        if self._open:
            self.doc.commitTransaction()
            self._open = False
        QtWidgets.QDialog.accept(self)

    def reject(self):
        self.model.reject()
        if self._open:
            self.doc.abortTransaction()
            self._open = False
        QtWidgets.QDialog.reject(self)


def run_dialog(model, doc=None, parent=None):
    """Show a panel dialog; True when accepted."""
    if parent is None:
        try:
            import FreeCADGui as Gui
            parent = Gui.getMainWindow()
        except Exception:
            parent = None
    dlg = PanelDialog(model, doc, parent)
    run = getattr(dlg, "exec", None) or dlg.exec_
    return bool(run())
