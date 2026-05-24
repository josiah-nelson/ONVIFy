"""Tests for FastAPI endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from onvify.api.app import create_app


class TestSystemEndpoints:
    def test_health_check(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/system/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_version(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/system/version")
        assert response.status_code == 200
        assert "version" in response.json()


class TestCameraEndpoints:
    def test_list_cameras_empty(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/cameras/")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_camera(self) -> None:
        app = create_app()
        client = TestClient(app)
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

    def test_create_mjpeg_camera(self) -> None:
        app = create_app()
        client = TestClient(app)
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

    def test_get_missing_camera(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/cameras/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
