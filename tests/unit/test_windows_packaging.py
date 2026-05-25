"""Windows packaging contract tests."""

from __future__ import annotations

import tomllib
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
    assert package.attrib["Version"] == "$(var.ProductVersion)"
    assert package.attrib["UpgradeCode"] == "8F6B8C9F-2732-4F44-AFD0-AAD70F14D5E2"

    service_account = _find_required(root, ".//wix:Property[@Id='SERVICEACCOUNT']")
    assert service_account.attrib["Value"] == r"NT AUTHORITY\NetworkService"
    assert root.find(".//wix:Property[@Id='SERVICEPASSWORD']", WIX_NS) is None

    executable = _find_required(root, ".//wix:File[@Id='ONVIFyExe']")
    assert executable.attrib["Source"] == "$(var.SourceDir)\\onvify.exe"
    assert executable.attrib["KeyPath"] == "yes"

    service_install = _find_required(root, ".//wix:ServiceInstall[@Id='ONVIFyServiceInstall']")
    assert service_install.attrib["Name"] == "ONVIFy"
    assert service_install.attrib["Type"] == "ownProcess"
    assert service_install.attrib["Start"] == "auto"
    assert service_install.attrib["Account"] == "[SERVICEACCOUNT]"
    assert "Password" not in service_install.attrib

    service_dependencies = service_install.findall("wix:ServiceDependency", WIX_NS)
    assert [dependency.attrib["Id"] for dependency in service_dependencies] == ["Tcpip", "Afd"]

    failure_actions = _find_required(service_install, "wix:ServiceConfigFailureActions")
    assert failure_actions.attrib["OnInstall"] == "yes"
    assert failure_actions.attrib["OnReinstall"] == "yes"
    assert failure_actions.attrib["ResetPeriod"] == "86400"

    failures = failure_actions.findall("wix:Failure", WIX_NS)
    assert [(failure.attrib["Action"], failure.attrib["Delay"]) for failure in failures] == [
        ("restartService", "5000"),
        ("restartService", "5000"),
        ("restartService", "5000"),
    ]

    service_start = _find_required(root, ".//wix:ServiceControl[@Id='ONVIFyServiceStart']")
    assert service_start.attrib["Name"] == "ONVIFy"
    assert service_start.attrib["Start"] == "install"
    assert service_start.attrib["Wait"] == "no"

    service_stop = _find_required(root, ".//wix:ServiceControl[@Id='ONVIFyServiceStop']")
    assert service_stop.attrib["Name"] == "ONVIFy"
    assert service_stop.attrib["Stop"] == "both"
    assert service_stop.attrib["Remove"] == "uninstall"
    assert service_stop.attrib["Wait"] == "yes"


def test_windows_pyinstaller_bundle_script_targets_onvify_cli() -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = (project_root / "packaging/windows/build-exe.ps1").read_text()

    assert '-m", "PyInstaller' in script
    assert '"--onefile"' in script
    assert '"--name", "onvify"' in script
    assert '"--distpath", $DistPath' in script
    assert '"--collect-all", "onvify"' in script
    assert '"src\\onvify\\cli.py"' in script
    assert '"onvify.exe"' in script


def test_pyinstaller_is_declared_as_packaging_dependency() -> None:
    project_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text())

    packaging_deps = pyproject["project"]["optional-dependencies"]["packaging"]
    assert any(dep.startswith("pyinstaller>=") for dep in packaging_deps)
