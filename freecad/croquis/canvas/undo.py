# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - undo commands of the drawing board
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
undo.py (Croquis) - QUndoStack commands at stroke level.

The board has its own undo stack while it is open: undoing a stroke must
not go through FreeCAD's document undo (one transaction per stroke would
flood it). When the board closes, all the strokes are written to the
document in one FreeCAD transaction.

`canvas` is the SheetCanvas: it owns `sheet` (SheetData), `compositor`
and repaints with sheet_changed(rect).
"""

from ..qt import QUndoCommand
from ..i18n import tr


class AddStroke(QUndoCommand):
    def __init__(self, canvas, stroke):
        QUndoCommand.__init__(self, tr("Stroke"))
        self.canvas = canvas
        self.stroke = stroke

    def redo(self):
        self.canvas.sheet.strokes.append(self.stroke)
        self.canvas.sheet_changed(self.canvas.compositor.add_stroke(self.stroke))

    def undo(self):
        sheet = self.canvas.sheet
        # normally the last one, but stay safe if another command reordered
        for i in range(len(sheet.strokes) - 1, -1, -1):
            if sheet.strokes[i] is self.stroke:
                del sheet.strokes[i]
                break
        self.canvas.sheet_changed(self.canvas.compositor.remove_stroke(self.stroke))


class ClearSheet(QUndoCommand):
    def __init__(self, canvas):
        QUndoCommand.__init__(self, tr("Clear sheet"))
        self.canvas = canvas
        self.saved = list(canvas.sheet.strokes)

    def redo(self):
        self.canvas.sheet.strokes = []
        self.canvas.compositor.rebuild()
        self.canvas.sheet_changed(None)

    def undo(self):
        self.canvas.sheet.strokes = list(self.saved)
        self.canvas.compositor.rebuild()
        self.canvas.sheet_changed(None)
