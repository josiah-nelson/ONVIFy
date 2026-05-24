"""Shared test fixtures for ONVIFy."""

from __future__ import annotations

from pathlib import Path

import pytest

from onvify.config import Settings
from onvify.models.camera import Camera, Stream, StreamType
from onvify.services.camera_manager import CameraManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    """Provide a Settings instance with isolated defaults."""
    monkeypatch.delenv("WEB_UI_PORT", raising=False)
    monkeypatch.delenv("MEDIAMTX_PORT", raising=False)
    monkeypatch.delenv("AI_DEFAULT_MODEL", raising=False)
    return Settings(root_dir=tmp_path)


@pytest.fixture
def camera_manager() -> CameraManager:
    return CameraManager()


@pytest.fixture
def sample_camera() -> Camera:
    return Camera(
        name="Test Camera",
        source_streams=[
            Stream(url="rtsp://192.168.1.100:554/stream1", stream_type=StreamType.RTSP),
        ],
        ai_enabled=True,
        ai_model="yolov8n.pt",
    )


@pytest.fixture
def sample_mjpeg_camera() -> Camera:
    return Camera(
        name="MJPEG Camera",
        source_streams=[
            Stream(url="http://192.168.1.101/mjpeg", stream_type=StreamType.MJPEG, label="main"),
        ],
    )
