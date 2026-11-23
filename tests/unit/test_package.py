# SPDX-License-Identifier: LGPL-2.1-or-later
"""package.xml: valid, icons present, version consistent."""

import os
import re
import xml.etree.ElementTree as ET

import pytest
from helpers import ROOT

import freecad.croquis as croquis

pytestmark = pytest.mark.unit

NS = {"p": "https://wiki.freecad.org/Package_Metadata"}


def tree():
    return ET.parse(os.path.join(ROOT, "package.xml")).getroot()


def test_package_xml_valid():
    root = tree()
    assert root.find("p:name", NS).text == "Croquis"
    assert root.find("p:license", NS).text == "LGPL-2.1-or-later"
    wb = root.find("p:content/p:workbench", NS)
    assert wb.find("p:classname", NS).text == "CroquisWorkbench"


def test_icons_exist():
    root = tree()
    for el in root.iter("{%s}icon" % NS["p"]):
        assert os.path.isfile(os.path.join(ROOT, el.text)), el.text


def test_version_single_source():
    v = tree().find("p:version", NS).text
    assert re.match(r"^\d+\.\d+\.\d+$", v)
    assert croquis.__version__ == v
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
        log = fh.read()
    assert "## [Unreleased]" in log and ("## [%s]" % v) in log


def test_command_and_tool_icons_exist():
    names = set(re.findall(r'"(\w+\.svg)"', open(os.path.join(
        ROOT, "freecad", "croquis", "canvas", "view.py"), encoding="utf-8").read()))
    names |= set(re.findall(r'"(\w+\.svg)"', open(os.path.join(
        ROOT, "freecad", "croquis", "commands.py"), encoding="utf-8").read()))
    for n in names:
        assert os.path.isfile(croquis.icon(n)), n
