"""MediaMTX binary resolution, download, extraction, and version checks."""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.request import urlretrieve

import structlog

from onvify.config import Settings

logger = structlog.get_logger()

RELEASE_BASE_URL = "https://github.com/bluenviron/mediamtx/releases/download"


@dataclass(frozen=True)
class MediaMTXReleasePlatform:
    os_name: Literal["linux", "darwin", "windows"]
    arch: Literal["amd64", "arm64", "armv6", "armv7"]
    archive_type: Literal["tar.gz", "zip"]
    executable_name: str


def detect_mediamtx_platform(system: str | None = None, machine: str | None = None) -> MediaMTXReleasePlatform:
    """Map the current host to a MediaMTX release asset platform."""
    system_name = (system or platform.system()).lower()
    machine_name = (machine or platform.machine()).lower()

    if system_name == "darwin":
        os_name: Literal["linux", "darwin", "windows"] = "darwin"
        archive_type: Literal["tar.gz", "zip"] = "tar.gz"
        executable_name = "mediamtx"
    elif system_name == "windows":
        os_name = "windows"
        archive_type = "zip"
        executable_name = "mediamtx.exe"
    elif system_name == "linux":
        os_name = "linux"
        archive_type = "tar.gz"
        executable_name = "mediamtx"
    else:
        msg = f"Unsupported MediaMTX operating system: {system_name}"
        raise RuntimeError(msg)

    arch = _normalize_arch(machine_name)
    if os_name in {"darwin", "windows"} and arch not in {"amd64", "arm64"}:
        msg = f"Unsupported MediaMTX architecture for {os_name}: {machine_name}"
        raise RuntimeError(msg)
    return MediaMTXReleasePlatform(
        os_name=os_name,
        arch=arch,
        archive_type=archive_type,
        executable_name=executable_name,
    )


def mediamtx_asset_name(version: str, release_platform: MediaMTXReleasePlatform) -> str:
    return f"mediamtx_{version}_{release_platform.os_name}_{release_platform.arch}.{release_platform.archive_type}"


def mediamtx_download_url(version: str, release_platform: MediaMTXReleasePlatform) -> str:
    asset_name = mediamtx_asset_name(version, release_platform)
    return f"{RELEASE_BASE_URL}/{version}/{asset_name}"


def resolve_mediamtx_binary(settings: Settings) -> Path | None:
    """Return a usable MediaMTX binary, downloading the configured version when enabled."""
    version = settings.streaming.mediamtx_version
    configured = settings.streaming.mediamtx_bin
    if configured is not None:
        binary = _resolve_configured_binary(configured)
        _ensure_binary_version(binary, version)
        return binary

    if not settings.streaming.mediamtx_auto_download:
        logger.info("mediamtx_auto_download_disabled")
        return None

    release_platform = detect_mediamtx_platform()
    binary = _managed_binary_path(settings.root_dir, version, release_platform)
    if binary.exists() and _binary_matches_version(binary, version):
        logger.info("mediamtx_binary_reused", path=str(binary), version=version)
        return binary

    url = mediamtx_download_url(version, release_platform)
    archive_name = mediamtx_asset_name(version, release_platform)
    with tempfile.TemporaryDirectory(prefix="onvify-mediamtx-") as tmp_dir:
        archive_path = Path(tmp_dir) / archive_name
        logger.info("mediamtx_binary_download_started", url=url)
        urlretrieve(url, str(archive_path))
        _extract_binary(archive_path, release_platform, binary)

    _ensure_binary_version(binary, version)
    logger.info("mediamtx_binary_ready", path=str(binary), version=version)
    return binary


def _normalize_arch(machine_name: str) -> Literal["amd64", "arm64", "armv6", "armv7"]:
    if machine_name in {"x86_64", "amd64"}:
        return "amd64"
    if machine_name in {"aarch64", "arm64"}:
        return "arm64"
    if machine_name.startswith("armv7"):
        return "armv7"
    if machine_name.startswith("armv6"):
        return "armv6"
    msg = f"Unsupported MediaMTX architecture: {machine_name}"
    raise RuntimeError(msg)


def _resolve_configured_binary(configured: Path) -> Path:
    if configured.is_absolute():
        candidate = configured
    else:
        found = shutil.which(str(configured))
        candidate = Path(found) if found else configured
    candidate = candidate.expanduser()
    if not candidate.exists():
        msg = f"Configured MediaMTX binary does not exist: {candidate}"
        raise FileNotFoundError(msg)
    return candidate


def _managed_binary_path(root_dir: Path, version: str, release_platform: MediaMTXReleasePlatform) -> Path:
    return root_dir / "data" / "bin" / "mediamtx" / version / release_platform.executable_name


def _binary_matches_version(binary: Path, version: str) -> bool:
    try:
        _ensure_binary_version(binary, version)
    except Exception:
        return False
    return True


def _ensure_binary_version(binary: Path, version: str) -> None:
    result = subprocess.run(
        [str(binary), "--version"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0 or (version not in output and version.removeprefix("v") not in output):
        msg = f"MediaMTX binary {binary} does not report expected version {version}"
        raise RuntimeError(msg)


def _extract_binary(
    archive_path: Path,
    release_platform: MediaMTXReleasePlatform,
    binary_path: Path,
) -> None:
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    if release_platform.archive_type == "zip":
        _extract_from_zip(archive_path, release_platform.executable_name, binary_path)
    else:
        _extract_from_tar(archive_path, release_platform.executable_name, binary_path)
    if os.name != "nt":
        binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _extract_from_tar(archive_path: Path, executable_name: str, binary_path: Path) -> None:
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive.getmembers():
            if Path(member.name).name != executable_name or not member.isfile():
                continue
            source = archive.extractfile(member)
            if source is None:
                break
            with source:
                binary_path.write_bytes(source.read())
            return
    msg = f"MediaMTX binary {executable_name!r} not found in {archive_path.name}"
    raise RuntimeError(msg)


def _extract_from_zip(archive_path: Path, executable_name: str, binary_path: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            if Path(member).name != executable_name:
                continue
            with archive.open(member) as source:
                binary_path.write_bytes(source.read())
            return
    msg = f"MediaMTX binary {executable_name!r} not found in {archive_path.name}"
    raise RuntimeError(msg)
