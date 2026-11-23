# SPDX-License-Identifier: LGPL-2.1-or-later
import pytest
from imaging import ensure_app


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    return ensure_app()
