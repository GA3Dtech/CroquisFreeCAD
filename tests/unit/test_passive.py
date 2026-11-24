# SPDX-License-Identifier: LGPL-2.1-or-later
"""Croquis is a passive workbench: no network, no server, no AI client,
nothing started at import (Addon Index: outside the 'AI agents' scope)."""

import ast
import os
import re

import pytest
from helpers import ROOT

pytestmark = pytest.mark.unit

PKG = os.path.join(ROOT, "freecad", "croquis")
FORBIDDEN_IMPORTS = {"socket", "socketserver", "http", "urllib", "requests", "asyncio",
                     "websocket", "websockets", "xmlrpc", "ssl", "subprocess", "threading",
                     "mcp", "anthropic", "openai"}


def sources():
    for dirpath, _dirs, files in os.walk(PKG):
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


@pytest.mark.parametrize("path", sorted(sources()), ids=lambda p: os.path.relpath(p, PKG))
def test_no_network_or_ai_imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        for n in names:
            assert n.split(".")[0] not in FORBIDDEN_IMPORTS, (path, n)


def test_no_agent_wording_in_code_and_docs():
    pattern = re.compile(r"\bmcp\b|\bagents?\b", re.I)
    files = list(sources()) + [os.path.join(ROOT, "README.md"),
                               os.path.join(ROOT, "docs", "api.md")]
    for path in files:
        text = open(path, encoding="utf-8").read()
        for line in text.splitlines():
            if pattern.search(line) and "AI coding agent" not in line \
                    and "MCP addon, for those who want one" not in line:
                pytest.fail("%s: %s" % (os.path.relpath(path, ROOT), line.strip()))


def test_import_starts_nothing():
    """The package __init__ only defines paths and the version."""
    tree = ast.parse(open(os.path.join(PKG, "__init__.py"), encoding="utf-8").read())
    for node in tree.body:
        assert isinstance(node, (ast.Expr, ast.Import, ast.ImportFrom, ast.Assign,
                                 ast.FunctionDef)), ast.dump(node)[:80]
