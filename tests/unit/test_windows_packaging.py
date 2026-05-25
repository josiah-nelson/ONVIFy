"""Windows packaging contract tests."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

WIX_NS = {"wix": "http://wixtoolset.org/schemas/v4/wxs"}


def _find_required(root: ElementTree.Element, path: str) -> ElementTree.Element:
    element = root.find(path, WIX_NS)
    assert element is not None, f"{path} was not found"
    return element


def test_wix_project_registers_onvify_as_windows_service() -> None:
    project_root = Path(__file__).resolve().parents[2]
    root = ElementTree.parse(project_root / "packaging/windows/onvify.wxs").getroot()

    package = _find_required(root, "wix:Package")
    assert package.attrib["Name"] == "ONVIFy"
    assert package.attrib["Scope"] == "perMachine"

    executable = _find_required(root, ".//wix:File")
    assert executable.attrib["Source"] == "$(var.SourceDir)\\onvify.exe"
    assert executable.attrib["KeyPath"] == "yes"

    service_install = _find_required(root, ".//wix:ServiceInstall")
    assert service_install.attrib["Name"] == "ONVIFy"
    assert service_install.attrib["Type"] == "ownProcess"
    assert service_install.attrib["Start"] == "auto"
    assert service_install.attrib["Account"] == "[SERVICEACCOUNT]"
    assert service_install.attrib["Password"] == "[SERVICEPASSWORD]"

    service_control = _find_required(root, ".//wix:ServiceControl")
    assert service_control.attrib["Name"] == "ONVIFy"
    assert service_control.attrib["Start"] == "install"
    assert service_control.attrib["Stop"] == "both"
    assert service_control.attrib["Remove"] == "uninstall"
