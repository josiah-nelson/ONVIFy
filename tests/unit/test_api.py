"""Tests for FastAPI endpoints.

Uses TestClient as a context manager to trigger the async lifespan,
which initializes the database and all services.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from onvify.api.routes.cameras import UpdateCameraRequest, delete_camera, update_camera
from onvify.inference.protocol import BackendHealth, BackendStatus
from onvify.models.camera import Camera, Stream, StreamType
from onvify.services.camera_manager import CameraManager
from onvify.services.stream_consumer import StreamConsumer
from onvify.services.streaming import MediaMTXManager


class FakeInferenceBackend:
    def __init__(self, status: BackendStatus) -> None:
        self._status = status

    async def health_check(self) -> BackendStatus:
        return self._status


class FailingInferenceBackend:
    async def health_check(self) -> BackendStatus:
        msg = "backend exploded"
        raise RuntimeError(msg)


class RecordingMediaMTXManager:
    def __init__(self) -> None:
        self.reload_camera_counts: list[int] = []
        self.fail_next_reload = False
        self.stopped = False

    def reload_config(self, cameras: list[Camera]) -> None:
        if self.fail_next_reload:
            self.fail_next_reload = False
            msg = "failed to write MediaMTX config"
            raise OSError(msg)
        self.reload_camera_counts.append(len(cameras))

    def stop(self) -> None:
        self.stopped = True


class RecordingStreamConsumer:
    def __init__(self) -> None:
        self.started: list[UUID] = []
        self.stopped: list[UUID] = []

    @property
    def active_cameras(self) -> set[UUID]:
        return set(self.started) - set(self.stopped)

    @property
    def active_ai_cameras(self) -> set[UUID]:
        return set()

    def start_camera(self, camera: Camera) -> None:
        if camera.ai_enabled or camera.stream_type == StreamType.MJPEG:
            self.started.append(camera.id)

    def stop_camera(self, camera_id: UUID) -> None:
        self.stopped.append(camera_id)

    async def stop_all_async(self) -> None:
        return None


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


def install_recording_lifecycle_services(
    client: TestClient,
) -> tuple[RecordingMediaMTXManager, RecordingStreamConsumer]:
    app = cast(FastAPI, client.app)
    mediamtx = RecordingMediaMTXManager()
    consumer = RecordingStreamConsumer()
    app.state.mediamtx = mediamtx
    app.state.stream_consumer = consumer
    return mediamtx, consumer


class TestSystemEndpoints:
    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/api/system/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "cameras_total" in data
        assert "ai_consumers_active" in data

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
        install_recording_lifecycle_services(client)
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

    def test_create_camera_reloads_mediamtx(self, client: TestClient) -> None:
        mediamtx, consumer = install_recording_lifecycle_services(client)
        response = client.post(
            "/api/cameras/",
            json={"name": "Lifecycle", "source_url": "rtsp://192.168.1.100:554/stream1"},
        )

        assert response.status_code == 201
        assert mediamtx.reload_camera_counts == [1]
        assert consumer.started == []

    def test_create_camera_reload_failure_does_not_persist_or_start_consumer(self, client: TestClient) -> None:
        mediamtx, consumer = install_recording_lifecycle_services(client)
        mediamtx.fail_next_reload = True

        response = client.post(
            "/api/cameras/",
            json={"name": "Broken", "source_url": "rtsp://192.168.1.100:554/stream1", "ai_enabled": True},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["detail"] == "MediaMTX config reload failed"
        assert client.get("/api/cameras/").json() == []
        assert consumer.started == []

    def test_create_ai_camera_starts_consumer(self, client: TestClient) -> None:
        mediamtx, consumer = install_recording_lifecycle_services(client)
        response = client.post(
            "/api/cameras/",
            json={
                "name": "AI Cam",
                "source_url": "rtsp://192.168.1.100:554/stream1",
                "ai_enabled": True,
            },
        )
        camera_id = UUID(response.json()["id"])

        assert mediamtx.reload_camera_counts == [1]
        assert consumer.started == [camera_id]

    def test_create_mjpeg_camera_starts_consumer(self, client: TestClient) -> None:
        _, consumer = install_recording_lifecycle_services(client)
        response = client.post(
            "/api/cameras/",
            json={
                "name": "MJPEG Lifecycle",
                "source_url": "http://192.168.1.101/mjpeg",
                "stream_type": "mjpeg",
            },
        )
        camera_id = UUID(response.json()["id"])

        assert consumer.started == [camera_id]

    def test_update_camera_restarts_consumer_and_reloads_mediamtx(self, client: TestClient) -> None:
        mediamtx, consumer = install_recording_lifecycle_services(client)
        response = client.post(
            "/api/cameras/",
            json={"name": "AI", "source_url": "rtsp://x", "ai_enabled": True},
        )
        camera_id = UUID(response.json()["id"])
        mediamtx.reload_camera_counts.clear()
        consumer.started.clear()

        response = client.patch(f"/api/cameras/{camera_id}", json={"name": "AI Updated"})

        assert response.status_code == 200
        assert mediamtx.reload_camera_counts == [1]
        assert consumer.stopped == [camera_id]
        assert consumer.started == [camera_id]

    def test_update_camera_reload_failure_does_not_persist_or_restart_consumer(self, client: TestClient) -> None:
        mediamtx, consumer = install_recording_lifecycle_services(client)
        response = client.post(
            "/api/cameras/",
            json={"name": "AI", "source_url": "rtsp://x", "ai_enabled": True},
        )
        camera_id = UUID(response.json()["id"])
        mediamtx.reload_camera_counts.clear()
        consumer.started.clear()
        consumer.stopped.clear()
        mediamtx.fail_next_reload = True

        response = client.patch(f"/api/cameras/{camera_id}", json={"name": "AI Updated"})

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert client.get(f"/api/cameras/{camera_id}").json()["name"] == "AI"
        assert consumer.started == []
        assert consumer.stopped == []

    @pytest.mark.asyncio
    async def test_update_camera_key_error_rolls_back_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manager = CameraManager()
        camera = Camera(name="AI", source_streams=[Stream(url="rtsp://x")], ai_enabled=True)
        await manager.add_camera(camera)
        mediamtx = RecordingMediaMTXManager()
        consumer = RecordingStreamConsumer()

        async def fail_update(camera_id: UUID, **kwargs: object) -> Camera:
            msg = f"Camera {camera_id} not found"
            raise KeyError(msg)

        monkeypatch.setattr(manager, "update_camera", fail_update)

        with pytest.raises(HTTPException) as exc_info:
            await update_camera(
                camera.id,
                UpdateCameraRequest(name="AI Updated"),
                manager,
                cast(MediaMTXManager, mediamtx),
                cast(StreamConsumer, consumer),
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert mediamtx.reload_camera_counts == [1, 1]
        assert consumer.started == []
        assert consumer.stopped == []

    def test_delete_camera_stops_consumer_and_reloads_mediamtx(self, client: TestClient) -> None:
        mediamtx, consumer = install_recording_lifecycle_services(client)
        response = client.post(
            "/api/cameras/",
            json={"name": "AI", "source_url": "rtsp://x", "ai_enabled": True},
        )
        camera_id = UUID(response.json()["id"])
        mediamtx.reload_camera_counts.clear()
        consumer.stopped.clear()

        response = client.delete(f"/api/cameras/{camera_id}")

        assert response.status_code == 204
        assert consumer.stopped == [camera_id]
        assert mediamtx.reload_camera_counts == [0]

    def test_delete_camera_reload_failure_does_not_remove_or_stop_consumer(self, client: TestClient) -> None:
        mediamtx, consumer = install_recording_lifecycle_services(client)
        response = client.post(
            "/api/cameras/",
            json={"name": "AI", "source_url": "rtsp://x", "ai_enabled": True},
        )
        camera_id = UUID(response.json()["id"])
        mediamtx.reload_camera_counts.clear()
        consumer.stopped.clear()
        mediamtx.fail_next_reload = True

        response = client.delete(f"/api/cameras/{camera_id}")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert client.get(f"/api/cameras/{camera_id}").status_code == 200
        assert consumer.stopped == []

    @pytest.mark.asyncio
    async def test_delete_camera_persistence_failure_rolls_back_without_duplicate_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manager = CameraManager()
        camera = Camera(name="AI", source_streams=[Stream(url="rtsp://x")], ai_enabled=True)
        await manager.add_camera(camera)
        mediamtx = RecordingMediaMTXManager()
        consumer = RecordingStreamConsumer()

        async def fail_remove(camera_id: UUID) -> Camera:
            msg = "db delete failed"
            raise RuntimeError(msg)

        monkeypatch.setattr(manager, "remove_camera", fail_remove)

        with pytest.raises(RuntimeError, match="db delete failed"):
            await delete_camera(
                camera.id,
                manager,
                cast(MediaMTXManager, mediamtx),
                cast(StreamConsumer, consumer),
            )

        assert mediamtx.reload_camera_counts == [0, 1]
        assert manager.get_camera(camera.id) is not None
        assert consumer.stopped == []

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
    def test_list_streams_empty(self, client: TestClient) -> None:
        response = client.get("/api/streams/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_streams_with_camera(self, client: TestClient) -> None:
        client.post("/api/cameras/", json={"name": "S", "source_url": "rtsp://x"})
        response = client.get("/api/streams/")
        data = response.json()
        assert len(data) == 1
        assert data[0]["camera_name"] == "S"
        assert data[0]["ai_active"] is False

    def test_mjpeg_preview_missing_camera(self, client: TestClient) -> None:
        response = client.get("/api/streams/00000000-0000-0000-0000-000000000000/mjpeg")
        assert response.status_code == 404


class TestDetectionEndpoints:
    def _set_inference_backend(self, client: TestClient, status: BackendStatus) -> None:
        app = cast(FastAPI, client.app)
        app.state.inference_backend = FakeInferenceBackend(status)

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

    def test_detection_health(self, client: TestClient) -> None:
        self._set_inference_backend(
            client,
            BackendStatus(
                health=BackendHealth.HEALTHY,
                model_name="fake-model",
                device="test",
            ),
        )
        response = client.get("/api/detection/health")

        assert response.status_code == 200
        assert response.json() == {
            "health": "healthy",
            "model_name": "fake-model",
            "device": "test",
            "message": None,
        }

    @pytest.mark.parametrize("health", [BackendHealth.UNAVAILABLE, BackendHealth.DEGRADED])
    def test_detection_health_non_healthy_returns_503(self, client: TestClient, health: BackendHealth) -> None:
        self._set_inference_backend(
            client,
            BackendStatus(
                health=health,
                model_name="fake-model",
                device="test",
                message=f"backend {health.value}",
            ),
        )
        response = client.get("/api/detection/health")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.json()["health"] == health.value
        assert response.json()["message"] == f"backend {health.value}"

    def test_detection_health_exception_returns_503(self, client: TestClient) -> None:
        app = cast(FastAPI, client.app)
        app.state.inference_backend = FailingInferenceBackend()

        response = client.get("/api/detection/health")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.json()["health"] == "unavailable"
        assert response.json()["message"] == "backend exploded"


class TestWebSocket:
    def test_websocket_connect_disconnect(self, client: TestClient) -> None:
        with client.websocket_connect("/api/system/ws") as ws:
            assert ws is not None
