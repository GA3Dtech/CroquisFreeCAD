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

from ..i18n import tr
from ..qt import QUndoCommand


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


class RemoveStrokes(QUndoCommand):
    """Delete strokes (stroke eraser, Delete key in the edit tool)."""

    def __init__(self, canvas, strokes):
        QUndoCommand.__init__(self, tr("Erase strokes"))
        self.canvas = canvas
        self.strokes = list(strokes)
        self.removed = []       # (index, stroke) in increasing index order

    def redo(self):
        sheet = self.canvas.sheet
        ids = set(id(s) for s in self.strokes)
        self.removed = [(i, s) for i, s in enumerate(sheet.strokes) if id(s) in ids]
        sheet.strokes = [s for s in sheet.strokes if id(s) not in ids]
        self.canvas.strokes_removed(self.strokes)
        self.canvas.sheet_changed(self.canvas.compositor.refresh_strokes(self.strokes))

    def undo(self):
        strokes = self.canvas.sheet.strokes
        # increasing order: each index is valid once the previous ones are back
        for i, s in self.removed:
            strokes.insert(min(i, len(strokes)), s)
        self.canvas.sheet_changed(self.canvas.compositor.refresh_strokes(self.strokes))


class ReplaceStroke(QUndoCommand):
    """Swap a stroke for an edited copy. Consecutive edits of the same
    setting (`merge_key`, e.g. dragging a spin box) merge into one step."""

    MERGE_ID = 4242

    def __init__(self, canvas, old, new, merge_key=None):
        QUndoCommand.__init__(self, tr("Edit stroke"))
        self.canvas = canvas
        self.old = old
        self.new = new
        self.merge_key = merge_key

    def _swap(self, a, b):
        strokes = self.canvas.sheet.strokes
        for i in range(len(strokes)):
            if strokes[i] is a:
                strokes[i] = b
                break
        self.canvas.stroke_replaced(a, b)
        self.canvas.sheet_changed(self.canvas.compositor.refresh_strokes([a, b]))

    def redo(self):
        self._swap(self.old, self.new)

    def undo(self):
        self._swap(self.new, self.old)

    def id(self):
        return self.MERGE_ID if self.merge_key else -1

    def mergeWith(self, other):
        if not isinstance(other, ReplaceStroke) or other.merge_key != self.merge_key \
                or other.old is not self.new:
            return False
        self.new = other.new
        return True


# ----------------------------------------------------------------------
#  Elements (images...)
# ----------------------------------------------------------------------
class AddElement(QUndoCommand):
    def __init__(self, canvas, element, text=None):
        QUndoCommand.__init__(self, text or tr("Add image"))
        self.canvas = canvas
        self.element = element

    def redo(self):
        self.canvas.sheet.elements.append(self.element)
        self.canvas.sheet_changed(self.canvas.compositor.refresh_elements([self.element]))

    def undo(self):
        els = self.canvas.sheet.elements
        self.canvas.sheet.elements = [e for e in els if e is not self.element]
        self.canvas.strokes_removed([self.element])
        self.canvas.sheet_changed(self.canvas.compositor.refresh_elements([self.element]))


class RemoveElements(QUndoCommand):
    def __init__(self, canvas, elements):
        QUndoCommand.__init__(self, tr("Delete image"))
        self.canvas = canvas
        self.elements = list(elements)
        self.removed = []

    def redo(self):
        ids = set(id(e) for e in self.elements)
        els = self.canvas.sheet.elements
        self.removed = [(i, e) for i, e in enumerate(els) if id(e) in ids]
        self.canvas.sheet.elements = [e for e in els if id(e) not in ids]
        self.canvas.strokes_removed(self.elements)
        self.canvas.sheet_changed(self.canvas.compositor.refresh_elements(self.elements))

    def undo(self):
        els = self.canvas.sheet.elements
        for i, e in self.removed:
            els.insert(min(i, len(els)), e)
        self.canvas.sheet_changed(self.canvas.compositor.refresh_elements(self.elements))


class ReplaceElement(QUndoCommand):
    """Swap an element for an edited copy; consecutive edits of one setting
    merge into one step."""

    MERGE_ID = 4343

    def __init__(self, canvas, old, new, merge_key=None, index=None):
        QUndoCommand.__init__(self, tr("Edit image"))
        self.canvas = canvas
        self.old = old
        self.new = new
        self.merge_key = merge_key
        self.index = index          # new position in the list (stacking), or None

    def _swap(self, a, b, index):
        els = self.canvas.sheet.elements
        i = next((k for k, e in enumerate(els) if e is a), None)
        if i is not None:
            del els[i]
            els.insert(i if index is None else max(0, min(index, len(els))), b)
        self.canvas.stroke_replaced(a, b)
        self.canvas.sheet_changed(self.canvas.compositor.refresh_elements([a, b]))

    def redo(self):
        self._old_index = next((k for k, e in enumerate(self.canvas.sheet.elements)
                                if e is self.old), None)
        self._swap(self.old, self.new, self.index)

    def undo(self):
        self._swap(self.new, self.old, self._old_index)

    def id(self):
        return self.MERGE_ID if self.merge_key else -1

    def mergeWith(self, other):
        if not isinstance(other, ReplaceElement) or other.merge_key != self.merge_key \
                or other.old is not self.new or other.index is not None:
            return False
        self.new = other.new
        return True
