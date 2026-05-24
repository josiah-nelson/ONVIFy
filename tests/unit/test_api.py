"""Tests for FastAPI endpoints.

Uses TestClient as a context manager to trigger the async lifespan,
which initializes the database and all services.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Create a test client with isolated database and lifespan."""
    monkeypatch.setenv("AI_BACKEND", "local")
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))
    from onvify.api.app import create_app
    from onvify.api.dependencies import get_settings

    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


class TestSystemEndpoints:
    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/api/system/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_version(self, client: TestClient) -> None:
        response = client.get("/api/system/version")
        assert response.status_code == 200
        assert "version" in response.json()


class TestCameraEndpoints:
    def test_list_cameras_empty(self, client: TestClient) -> None:
        response = client.get("/api/cameras/")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_camera(self, client: TestClient) -> None:
        response = client.post(
            "/api/cameras/",
            json={
                "name": "Test Cam",
                "source_url": "rtsp://192.168.1.100:554/stream1",
                "stream_type": "rtsp",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Cam"
        assert data["status"] == "offline"

    def test_create_mjpeg_camera(self, client: TestClient) -> None:
        response = client.post(
            "/api/cameras/",
            json={
                "name": "MJPEG Cam",
                "source_url": "http://192.168.1.101/mjpeg",
                "stream_type": "mjpeg",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["source_streams"][0]["stream_type"] == "mjpeg"

    def test_get_missing_camera(self, client: TestClient) -> None:
        response = client.get("/api/cameras/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_camera_persists_across_list(self, client: TestClient) -> None:
        client.post(
            "/api/cameras/",
            json={"name": "Persist Test", "source_url": "rtsp://x"},
        )
        response = client.get("/api/cameras/")
        assert len(response.json()) == 1


class TestStreamEndpoints:
    def test_list_streams_stub(self, client: TestClient) -> None:
        response = client.get("/api/streams/")
        assert response.status_code == 200


class TestDetectionEndpoints:
    def test_detection_config(self, client: TestClient) -> None:
        response = client.get("/api/detection/config")
        assert response.status_code == 200
        data = response.json()
        assert "backend" in data
        assert "confidence_threshold" in data

    def test_detection_events_empty(self, client: TestClient) -> None:
        response = client.get("/api/detection/events")
        assert response.status_code == 200
        assert response.json() == []
