# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - pictures
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
images.py (Croquis) - reading and preparing the pictures of image elements
(Qt only, no FreeCAD): anything QImageReader reads (PNG, JPEG, BMP,
WebP...), EXIF orientation applied, reduced by default to the resolution
the sheet can use (the picture is stored inside the .FCStd: see the "file
weight" risk of the specification).
"""

import os
import tempfile

from .qt import QtCore, QtGui

# a stored picture keeps this many pixels per sheet pixel (room to zoom in)
USEFUL_FACTOR = 2.0


def read(path):
    """QImage of a file, orientation applied; ValueError when unreadable."""
    reader = QtGui.QImageReader(path)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        raise ValueError("cannot read the image %r (%s)" % (path, reader.errorString()))
    return img


def useful_size(w_mm, h_mm, dpi, factor=USEFUL_FACTOR):
    """Largest useful picture size in pixels for a w x h mm placement."""
    k = dpi / 25.4 * factor
    return max(1, int(round(w_mm * k))), max(1, int(round(h_mm * k)))


def reduce(img, max_w, max_h):
    """The picture scaled down (never up) to fit max_w x max_h."""
    if img.width() <= max_w and img.height() <= max_h:
        return img
    return img.scaled(max_w, max_h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)


def save_temp(img, stem="croquis"):
    """Write a picture to a new temporary PNG file; returns its path."""
    fd, path = tempfile.mkstemp(prefix=stem + "_", suffix=".png")
    os.close(fd)
    if not img.save(path, "PNG"):
        os.remove(path)
        raise IOError("cannot write %r" % path)
    return path


def from_mime(mime):
    """(QImage or None, [local file paths]) found in clipboard / drop data:
    a picture (screenshot, image copied from a browser) or file names
    (copied or dragged from a file manager)."""
    img = None
    if mime is not None and mime.hasImage():
        data = mime.imageData()
        if isinstance(data, QtGui.QImage) and not data.isNull():
            img = data
        elif isinstance(data, QtGui.QPixmap) and not data.isNull():
            img = data.toImage()
    paths = []
    if mime is not None and mime.hasUrls():
        paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
    elif mime is not None and mime.hasText():
        for line in mime.text().splitlines():
            line = line.strip()
            if line.startswith("file://"):
                line = QtCore.QUrl(line).toLocalFile()
            if line and os.path.isfile(line):
                paths.append(line)
    readable = set(bytes(f).decode().lower() for f in QtGui.QImageReader.supportedImageFormats())
    paths = [p for p in paths if os.path.splitext(p)[1][1:].lower() in readable]
    return img, paths
