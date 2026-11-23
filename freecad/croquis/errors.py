# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Croquis - typed errors of the public API
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
errors.py (Croquis) - exceptions raised by the public API (api.py), so
that scripts and agents can tell a missing document from a bad stroke.
Messages are English and stable (they are part of the API contract).
"""


class CroquisError(Exception):
    """Base class of every Croquis error."""


class NoDocumentError(CroquisError):
    """No document given and no active document, or unknown document."""


class SheetNotFoundError(CroquisError):
    """The object is not a Croquis sheet, or no sheet has that name."""


class InvalidStrokeError(CroquisError):
    """A stroke given to add_strokes() does not follow the format."""


class InvalidArgumentError(CroquisError, ValueError):
    """An argument is out of range or of the wrong type."""


class GuiRequiredError(CroquisError):
    """The function needs the FreeCAD GUI (3D view capture...)."""
