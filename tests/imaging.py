# SPDX-License-Identifier: LGPL-2.1-or-later
"""Image helpers shared by the rendering and FreeCAD tests: QImage to
numpy, tolerant comparison with a reference image, artifacts on failure."""

import os

import numpy as np


def qt():
    try:
        from PySide import QtCore, QtGui
    except ImportError:
        from PySide6 import QtCore, QtGui
    return QtCore, QtGui


def ensure_app():
    """A QGuiApplication (offscreen when none exists yet; forced when there
    is no display, see qt.use_offscreen_without_display)."""
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _core, QtGui = qt()
    app = QtGui.QGuiApplication.instance()
    if app is None:
        app = QtGui.QGuiApplication(["croquis-tests"])
        ensure_app.app = app
    return app


def to_array(img):
    """RGBA uint8 array (h, w, 4), straight (not premultiplied) alpha."""
    _core, QtGui = qt()
    img = img.convertToFormat(QtGui.QImage.Format_RGBA8888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    ptr = img.constBits()
    if hasattr(ptr, "setsize"):
        ptr.setsize(h * bpl)
    buf = np.frombuffer(ptr, np.uint8, count=h * bpl)
    return buf.reshape(h, bpl)[:, :w * 4].reshape(h, w, 4).copy()


def load(path):
    _core, QtGui = qt()
    img = QtGui.QImage(path)
    assert not img.isNull(), "cannot read %s" % path
    return img


def flatten(arr, background=(255, 255, 255)):
    """RGB over a background, as float (for comparisons including alpha)."""
    a = arr[:, :, 3:4].astype(np.float32) / 255.0
    return arr[:, :, :3].astype(np.float32) * a + np.array(background, np.float32) * (1 - a)


def compare(img, ref_path, name, artifacts, update=False, mean_tol=2.0, bad_tol=0.005,
            bad_level=48):
    """Compare a QImage with a reference PNG. Tolerances: mean absolute
    difference (0..255) and the share of pixels differing by more than
    `bad_level`. Writes <name>_got.png / _diff.png in `artifacts` on failure,
    rewrites the reference when `update`. Returns (ok, message)."""
    _core, QtGui = qt()
    if update or not os.path.exists(ref_path):
        os.makedirs(os.path.dirname(ref_path), exist_ok=True)
        img.save(ref_path, "PNG")
        return True, "reference written"
    got = to_array(img)
    ref = to_array(load(ref_path))
    if got.shape != ref.shape:
        img.save(os.path.join(artifacts, name + "_got.png"), "PNG")
        return False, "size %s != reference %s" % (got.shape[:2], ref.shape[:2])
    # compare over white and over black so alpha differences count
    d = np.maximum(np.abs(flatten(got) - flatten(ref)),
                   np.abs(flatten(got, (0, 0, 0)) - flatten(ref, (0, 0, 0)))).max(axis=2)
    mean = float(d.mean())
    bad = float((d > bad_level).mean())
    ok = mean <= mean_tol and bad <= bad_tol
    if not ok:
        img.save(os.path.join(artifacts, name + "_got.png"), "PNG")
        diff = np.clip(d * 4, 0, 255).astype(np.uint8)
        h, w = diff.shape
        rgba = np.dstack([diff, diff, diff, np.full_like(diff, 255)]).copy()
        QtGui.QImage(rgba.tobytes(), w, h, 4 * w, QtGui.QImage.Format_RGBA8888).copy() \
            .save(os.path.join(artifacts, name + "_diff.png"), "PNG")
    return ok, "mean diff %.3f, %.3f%% pixels over %d" % (mean, bad * 100, bad_level)
