# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - sheets laid on a face of the model
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
face.py (Croquis) - where a sheet goes to annotate a face of the model:
on its plane (the tangent plane at the picked point for a curved face),
facing outwards, a hair above it, framed on the face. Pure FreeCAD / Part,
works in freecadcmd.
"""

import FreeCAD as App

LONG_SIDE = 297.0       # mm of the sheet; the Scale gives the real size
MARGIN = 0.06           # free paper around the face, ratio of its size
MIN_SIDE = 40.0         # mm of the sheet, for long thin faces


class FaceError(ValueError):
    pass


def face_shape(obj, sub):
    """The face `sub` of `obj` with its global placement (`sub` may be a
    full sub-name through containers, e.g. "Body.Pad.Face3")."""
    import Part
    if not sub or not sub.split(".")[-1].startswith("Face"):
        raise FaceError("not a face: %r" % (sub,))
    try:
        shape = Part.getShape(obj, sub, needSubElement=True)
    except Exception as exc:
        raise FaceError("no face %r on %s (%s)" % (sub, obj.Name, exc))
    if shape is None or shape.isNull() or shape.ShapeType != "Face":
        raise FaceError("no face %r on %s" % (sub, obj.Name))
    return shape


def _axes(normal, up):
    """Sheet axes (x right, y up, normal) with y as close to `up` as the
    plane allows; global Z, then Y, when `up` is (nearly) along the normal."""
    n = App.Vector(normal).normalize()
    for cand in (up, App.Vector(0, 0, 1), App.Vector(0, 1, 0)):
        if cand is None:
            continue
        c = App.Vector(cand)
        if c.Length < 1e-9:
            continue
        c.normalize()
        y = c - n * c.dot(n)
        if y.Length > 0.2:
            y.normalize()
            return y.cross(n), y, n
    raise FaceError("no up direction")


def face_frame(face, point=None, up=None):
    """(placement, (width, height) sheet mm, scale) of a sheet lying on
    `face`. point: picked point (global), sets the tangent plane of a
    curved face; up: direction that should read as up on the sheet (the
    camera's up in the GUI)."""
    u0, u1, v0, v1 = face.ParameterRange
    if point is not None:
        u, v = face.Surface.parameter(App.Vector(point))
    else:
        u, v = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    normal = face.normalAt(u, v)
    if point is not None:
        origin = App.Vector(point)
    elif face.findPlane() is not None:
        origin = face.CenterOfMass
    else:
        origin = face.valueAt(u, v)
    x, y, n = _axes(normal, up)
    pts = []
    for e in face.Edges:
        try:
            pts.extend(e.discretize(Number=64))
        except Exception:
            pts.extend(vx.Point for vx in e.Vertexes)
    if not pts:
        raise FaceError("the face has no boundary")
    xs = [(p - origin).dot(x) for p in pts]
    ys = [(p - origin).dot(y) for p in pts]
    hs = [(p - origin).dot(n) for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    if max(w, h) < 1e-6:
        raise FaceError("the face is too small")
    pad = MARGIN * max(w, h)
    w, h = w + 2 * pad, h + 2 * pad
    k = max(w, h) / LONG_SIDE
    sw, sh = max(w / k, MIN_SIDE), max(h / k, MIN_SIDE)
    # a hair above the face (above its highest point when it is curved)
    lift = max(hs + [0.0]) + max(0.05, 0.002 * max(w, h))
    centre = origin + x * ((max(xs) + min(xs)) / 2.0) + y * ((max(ys) + min(ys)) / 2.0) \
        + n * lift
    rot = App.Rotation(x, y, n, "ZYX")
    return App.Placement(centre, rot), (round(sw, 2), round(sh, 2)), k
