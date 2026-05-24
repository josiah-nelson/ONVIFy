"""Tests for MediaMTX binary download and version management."""

from __future__ import annotations

import os
import shutil
import tarfile
from pathlib import Path

import pytest

from onvify.config import Settings, StreamingSettings
from onvify.services import mediamtx_binary
from onvify.services.mediamtx_binary import (
    MediaMTXReleasePlatform,
    detect_mediamtx_platform,
    mediamtx_asset_name,
    mediamtx_download_url,
    resolve_mediamtx_binary,
)


def _write_fake_mediamtx(path: Path, version: str) -> None:
    path.write_text(f"#!/bin/sh\necho {version}\n")
    path.chmod(path.stat().st_mode | 0o755)


def _make_tar_archive(tmp_path: Path, version: str) -> Path:
    source = tmp_path / "mediamtx"
    _write_fake_mediamtx(source, version)
    archive_path = tmp_path / f"mediamtx_{version}_linux_amd64.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(source, arcname="mediamtx")
    return archive_path


class TestMediaMTXPlatform:
    def test_detect_linux_amd64(self) -> None:
        release_platform = detect_mediamtx_platform(system="Linux", machine="x86_64")
        assert release_platform == MediaMTXReleasePlatform(
            os_name="linux",
            arch="amd64",
            archive_type="tar.gz",
            executable_name="mediamtx",
        )

    def test_detect_windows_arm64(self) -> None:
        release_platform = detect_mediamtx_platform(system="Windows", machine="ARM64")
        assert release_platform == MediaMTXReleasePlatform(
            os_name="windows",
            arch="arm64",
            archive_type="zip",
            executable_name="mediamtx.exe",
        )

    def test_asset_name_and_url(self) -> None:
        release_platform = MediaMTXReleasePlatform(
            os_name="darwin",
            arch="arm64",
            archive_type="tar.gz",
            executable_name="mediamtx",
        )
        assert mediamtx_asset_name("v1.18.2", release_platform) == "mediamtx_v1.18.2_darwin_arm64.tar.gz"
        assert (
            mediamtx_download_url("v1.18.2", release_platform)
            == "https://github.com/bluenviron/mediamtx/releases/download/v1.18.2/"
            "mediamtx_v1.18.2_darwin_arm64.tar.gz"
        )


class TestMediaMTXBinaryResolution:
    def test_auto_download_disabled_returns_none(self, tmp_path: Path) -> None:
        settings = Settings(
            root_dir=tmp_path,
            streaming=StreamingSettings(mediamtx_auto_download=False),
        )

        assert resolve_mediamtx_binary(settings) is None

    def test_configured_binary_is_version_checked(self, tmp_path: Path) -> None:
        binary = tmp_path / "mediamtx"
        _write_fake_mediamtx(binary, "v1.18.2")
        settings = Settings(
            root_dir=tmp_path,
            streaming=StreamingSettings(mediamtx_auto_download=False, mediamtx_bin=binary),
        )

        assert resolve_mediamtx_binary(settings) == binary

    def test_download_extracts_and_checks_binary(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        archive_path = _make_tar_archive(tmp_path, "v1.18.2")
        settings = Settings(root_dir=tmp_path, streaming=StreamingSettings(mediamtx_auto_download=True))

        monkeypatch.setattr(
            mediamtx_binary,
            "detect_mediamtx_platform",
            lambda: detect_mediamtx_platform("Linux", "x86_64"),
        )

        def fake_urlretrieve(url: str, filename: str | os.PathLike[str]) -> tuple[str, None]:
            shutil.copyfile(archive_path, filename)
            return (str(filename), None)

        monkeypatch.setattr(mediamtx_binary, "urlretrieve", fake_urlretrieve)

        binary = resolve_mediamtx_binary(settings)

        assert binary == tmp_path / "data" / "bin" / "mediamtx" / "v1.18.2" / "mediamtx"
        assert binary.exists()
        assert os.access(binary, os.X_OK)

    def test_download_fails_when_extracted_binary_reports_wrong_version(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        archive_path = _make_tar_archive(tmp_path, "v1.0.0")
        settings = Settings(root_dir=tmp_path, streaming=StreamingSettings(mediamtx_auto_download=True))

        monkeypatch.setattr(
            mediamtx_binary,
            "detect_mediamtx_platform",
            lambda: detect_mediamtx_platform("Linux", "x86_64"),
        )

        def fake_urlretrieve(url: str, filename: str | os.PathLike[str]) -> tuple[str, None]:
            shutil.copyfile(archive_path, filename)
            return (str(filename), None)

        monkeypatch.setattr(mediamtx_binary, "urlretrieve", fake_urlretrieve)

        with pytest.raises(RuntimeError, match="expected version"):
            resolve_mediamtx_binary(settings)
