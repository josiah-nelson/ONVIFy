"""Tests for FastAPI endpoints.

Uses TestClient as a context manager to trigger the async lifespan,
which initializes the database and all services.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from onvify.api.routes.cameras import (
    CreateCameraRequest,
    UpdateCameraRequest,
    create_camera,
    delete_camera,
    update_camera,
)
from onvify.api.websocket import ConnectionManager
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


class HangingInferenceBackend:
    async def health_check(self) -> BackendStatus:
        await asyncio.sleep(60)
        return BackendStatus(health=BackendHealth.HEALTHY)


class RecordingMediaMTXManager:
    def __init__(self) -> None:
        self.reload_camera_counts: list[int] = []
        self.reload_attempts = 0
        self.fail_on_reload_attempts: set[int] = set()
        self.fail_next_reload = False
        self.stopped = False

    @property
    def is_configured(self) -> bool:
        return False

    @property
    def is_running(self) -> bool:
        return False

    @property
    def pid(self) -> int | None:
        return None

    def reload_config(self, cameras: list[Camera]) -> None:
        self.reload_attempts += 1
        if self.fail_next_reload or self.reload_attempts in self.fail_on_reload_attempts:
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
        self.inference_config_updates: list[dict[str, float | int | None]] = []

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

    def update_inference_config(
        self,
        *,
        motion_sensitivity: int | None = None,
        confidence_threshold: float | None = None,
        cooldown_seconds: float | None = None,
        target_interval: float | None = None,
    ) -> None:
        self.inference_config_updates.append(
            {
                "motion_sensitivity": motion_sensitivity,
                "confidence_threshold": confidence_threshold,
                "cooldown_seconds": cooldown_seconds,
                "target_interval": target_interval,
            }
        )

    async def stop_all_async(self) -> None:
        return None


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Create a test client with isolated database and lifespan."""
    monkeypatch.setenv("AI_BACKEND", "local")
    monkeypatch.setenv("MEDIAMTX_AUTO_DOWNLOAD", "false")
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


class TestFrontendAssets:
    def test_serves_built_frontend_index_and_assets(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        with self._client_with_dist(tmp_path, monkeypatch) as client:
            index_response = client.get("/")
            asset_response = client.get("/assets/app.js")
            spa_response = client.get("/cameras/123")

            assert index_response.status_code == 200
            assert "ONVIFy UI" in index_response.text
            assert index_response.headers["cache-control"] == "no-cache, must-revalidate"
            assert asset_response.status_code == 200
            assert "window.onvify" in asset_response.text
            assert spa_response.status_code == 200
            assert "ONVIFy UI" in spa_response.text
            assert spa_response.headers["cache-control"] == "no-cache, must-revalidate"

    def test_frontend_fallback_does_not_shadow_api_routes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with self._client_with_dist(tmp_path, monkeypatch) as client:
            response = client.get("/api/not-found")

            assert response.status_code == 404
            assert response.json() == {"detail": "Not Found"}

    def test_frontend_fallback_rejects_path_traversal(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "secret.txt").write_text("outside dist", encoding="utf-8")
        with self._client_with_dist(tmp_path, monkeypatch) as client:
            response = client.get("/%2E%2E/secret.txt")

            assert response.status_code == 404

    def test_frontend_routes_disabled_without_dist(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        with self._client(tmp_path, monkeypatch) as client:
            response = client.get("/")

            assert response.status_code == 404

    @contextmanager
    def _client_with_dist(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
        dist = tmp_path / "frontend" / "dist"
        assets = dist / "assets"
        assets.mkdir(parents=True)
        (dist / "index.html").write_text("<div>ONVIFy UI</div>", encoding="utf-8")
        (dist / "site.webmanifest").write_text('{"name":"ONVIFy"}', encoding="utf-8")
        (assets / "app.js").write_text("window.onvify = true;", encoding="utf-8")
        with self._client(tmp_path, monkeypatch) as client:
            yield client

    def test_frontend_root_static_files_are_not_cached(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        with self._client_with_dist(tmp_path, monkeypatch) as client:
            response = client.get("/site.webmanifest")
            index_response = client.get("/index.html")

            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-cache, must-revalidate"
            assert index_response.status_code == 200
            assert index_response.headers["cache-control"] == "no-cache, must-revalidate"

    @contextmanager
    def _client(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
        monkeypatch.setenv("ROOT_DIR", str(tmp_path))
        from onvify.api.app import create_app
        from onvify.api.dependencies import get_settings

        get_settings.cache_clear()
        try:
            with TestClient(create_app()) as client:
                yield client
        finally:
            get_settings.cache_clear()


class TestSystemEndpoints:
    def test_health_check(self, client: TestClient) -> None:
        app = cast(FastAPI, client.app)
        app.state.inference_backend = FakeInferenceBackend(
            BackendStatus(health=BackendHealth.HEALTHY, model_name="fake-model", device="test")
        )

        response = client.get("/api/system/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "cameras_total" in data
        assert "stream_consumers_active" in data
        assert "ai_consumers_active" in data
        assert data["database"] == {"connected": True}
        assert data["mediamtx"] == {"configured": False, "running": False, "pid": None}
        assert data["inference"] == {
            "health": "healthy",
            "model_name": "fake-model",
            "device": "test",
            "message": None,
        }

    def test_health_check_unavailable_when_inference_fails(self, client: TestClient) -> None:
        app = cast(FastAPI, client.app)
        app.state.inference_backend = FailingInferenceBackend()

        response = client.get("/api/system/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unavailable"
        assert data["inference"]["health"] == "unavailable"
        assert data["inference"]["message"] == "backend exploded"

    def test_health_check_unavailable_when_inference_times_out(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from onvify.api.routes import system as system_module

        monkeypatch.setattr(system_module, "_INFERENCE_HEALTH_TIMEOUT", 0.05)
        app = cast(FastAPI, client.app)
        app.state.inference_backend = HangingInferenceBackend()

        response = client.get("/api/system/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unavailable"
        assert data["inference"]["health"] == "unavailable"
        assert data["inference"]["message"] == "health check timed out"

    def test_version(self, client: TestClient) -> None:
        response = client.get("/api/system/version")
        assert response.status_code == 200
        assert "version" in response.json()

    def test_diagnostics(self, client: TestClient) -> None:
        response = client.get("/api/system/diagnostics")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0
        assert data["system"]["python_version"].startswith("3.")
        assert data["cameras"]["total"] == 0
        assert data["cameras"]["details"] == []
        assert "backend" in data["inference"]

    def test_diagnostics_with_camera(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/cameras/",
            json={"name": "Diag Cam", "source_url": "rtsp://x", "ai_enabled": True},
        )
        assert create_resp.status_code == 201
        response = client.get("/api/system/diagnostics")
        assert response.status_code == 200
        data = response.json()
        assert data["cameras"]["total"] == 1
        details = data["cameras"]["details"]
        assert len(details) == 1
        assert details[0]["name"] == "Diag Cam"
        assert details[0]["ai_enabled"] is True


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

    @pytest.mark.asyncio
    async def test_create_camera_persistence_error_preserved_when_rollback_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manager = CameraManager()
        mediamtx = RecordingMediaMTXManager()
        mediamtx.fail_on_reload_attempts = {2}
        consumer = RecordingStreamConsumer()

        async def fail_add(camera: Camera) -> Camera:
            msg = "db create failed"
            raise RuntimeError(msg)

        monkeypatch.setattr(manager, "add_camera", fail_add)

        with pytest.raises(RuntimeError, match="db create failed"):
            await create_camera(
                CreateCameraRequest(name="AI", source_url="rtsp://x", ai_enabled=True),
                manager,
                cast(MediaMTXManager, mediamtx),
                cast(StreamConsumer, consumer),
                ConnectionManager(),
            )

        assert mediamtx.reload_attempts == 2
        assert mediamtx.reload_camera_counts == [1]
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
                ConnectionManager(),
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert mediamtx.reload_camera_counts == [1, 1]
        assert consumer.started == []
        assert consumer.stopped == []

    @pytest.mark.asyncio
    async def test_update_camera_key_error_preserves_404_when_rollback_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manager = CameraManager()
        camera = Camera(name="AI", source_streams=[Stream(url="rtsp://x")], ai_enabled=True)
        await manager.add_camera(camera)
        mediamtx = RecordingMediaMTXManager()
        mediamtx.fail_on_reload_attempts = {2}
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
                ConnectionManager(),
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert mediamtx.reload_attempts == 2
        assert mediamtx.reload_camera_counts == [1]
        assert consumer.started == []
        assert consumer.stopped == []

    @pytest.mark.asyncio
    async def test_update_camera_persistence_error_preserved_when_rollback_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manager = CameraManager()
        camera = Camera(name="AI", source_streams=[Stream(url="rtsp://x")], ai_enabled=True)
        await manager.add_camera(camera)
        mediamtx = RecordingMediaMTXManager()
        mediamtx.fail_on_reload_attempts = {2}
        consumer = RecordingStreamConsumer()

        async def fail_update(camera_id: UUID, **kwargs: object) -> Camera:
            msg = "db update failed"
            raise RuntimeError(msg)

        monkeypatch.setattr(manager, "update_camera", fail_update)

        with pytest.raises(RuntimeError, match="db update failed"):
            await update_camera(
                camera.id,
                UpdateCameraRequest(name="AI Updated"),
                manager,
                cast(MediaMTXManager, mediamtx),
                cast(StreamConsumer, consumer),
                ConnectionManager(),
            )

        assert mediamtx.reload_attempts == 2
        assert mediamtx.reload_camera_counts == [1]
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
                ConnectionManager(),
            )

        assert mediamtx.reload_camera_counts == [0, 1]
        assert manager.get_camera(camera.id) is not None
        assert consumer.stopped == []

    @pytest.mark.asyncio
    async def test_delete_camera_persistence_error_preserved_when_rollback_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manager = CameraManager()
        camera = Camera(name="AI", source_streams=[Stream(url="rtsp://x")], ai_enabled=True)
        await manager.add_camera(camera)
        mediamtx = RecordingMediaMTXManager()
        mediamtx.fail_on_reload_attempts = {2}
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
                ConnectionManager(),
            )

        assert mediamtx.reload_attempts == 2
        assert mediamtx.reload_camera_counts == [0]
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
        client.post(
            "/api/cameras/",
            json={"name": "S", "source_url": "rtsp://user:secret@example.test/stream?channel=1"},
        )
        response = client.get("/api/streams/")
        data = response.json()
        assert len(data) == 1
        assert data[0]["camera_name"] == "S"
        assert data[0]["source_url"] == "rtsp://***@example.test/stream?channel=1"
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


class TestStreamStatusEndpoint:
    @staticmethod
    def _mock_response(status_code: int, json: dict[str, object]) -> httpx.Response:
        """Build an httpx.Response with a dummy request so raise_for_status() works."""
        return httpx.Response(
            status_code,
            json=json,
            request=httpx.Request("GET", "http://localhost:9997/v3/paths/list"),
        )

    def test_stream_status_returns_mediamtx_paths(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_response = self._mock_response(
            200,
            {
                "items": [
                    {
                        "name": "front_door",
                        "ready": True,
                        "readyTime": "2024-01-01T00:00:00Z",
                        "readers": [{"id": "r1"}, {"id": "r2"}],
                        "bytesReceived": 1024000,
                        "bytesSent": 512000,
                    },
                    {
                        "name": "backyard",
                        "ready": False,
                        "readyTime": None,
                        "readers": [],
                        "bytesReceived": 0,
                        "bytesSent": 0,
                    },
                ]
            },
        )

        async def mock_get(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
            return mock_response

        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

        response = client.get("/api/streams/status")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "front_door"
        assert data[0]["ready"] is True
        assert data[0]["readers"] == 2
        assert data[0]["bytes_received"] == 1024000
        assert data[0]["bytes_sent"] == 512000
        assert data[1]["name"] == "backyard"
        assert data[1]["ready"] is False

    def test_stream_status_mediamtx_unreachable(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        async def mock_get(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

        response = client.get("/api/streams/status")
        assert response.status_code == 502
        assert response.json()["detail"] == "MediaMTX API is unreachable"

    def test_stream_status_empty_items(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_response = self._mock_response(200, {"items": []})

        async def mock_get(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
            return mock_response

        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

        response = client.get("/api/streams/status")
        assert response.status_code == 200
        assert response.json() == []


class TestDetectionConfig:
    def test_get_detection_config(self, client: TestClient) -> None:
        response = client.get("/api/detection/config")
        assert response.status_code == 200
        data = response.json()
        assert "backend" in data
        assert "confidence_threshold" in data
        assert "motion_sensitivity" in data
        assert data["persistent"] is False

    def test_get_detection_config_redacts_backend_url(self, client: TestClient) -> None:
        from onvify.api.dependencies import get_settings

        settings = get_settings()
        settings.inference.backend_url = "https://user:secret@example.test/v1?api_key=hidden#token"

        response = client.get("/api/detection/config")

        assert response.status_code == 200
        assert response.json()["backend_url"] == "https://***@example.test/v1"

    def test_patch_detection_config(self, client: TestClient) -> None:
        _, consumer = install_recording_lifecycle_services(client)

        response = client.patch("/api/detection/config", json={"confidence_threshold": 75})

        assert response.status_code == 200
        data = response.json()
        assert data["confidence_threshold_pct"] == 75
        assert data["confidence_threshold"] == 0.75
        assert data["persistent"] is False
        assert data["applied_to_running_streams"] is True
        assert consumer.inference_config_updates == [
            {
                "motion_sensitivity": None,
                "confidence_threshold": 0.75,
                "cooldown_seconds": None,
                "target_interval": None,
            }
        ]

        get_response = client.get("/api/detection/config")
        assert get_response.status_code == 200
        assert get_response.json()["confidence_threshold_pct"] == 75

    def test_patch_detection_config_multiple_fields(self, client: TestClient) -> None:
        _, consumer = install_recording_lifecycle_services(client)

        response = client.patch(
            "/api/detection/config",
            json={"motion_sensitivity": 80, "cooldown_seconds": 10.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["motion_sensitivity"] == 80
        assert data["cooldown_seconds"] == 10.0
        assert consumer.inference_config_updates == [
            {
                "motion_sensitivity": 80,
                "confidence_threshold": None,
                "cooldown_seconds": 10.0,
                "target_interval": None,
            }
        ]

    def test_patch_detection_config_validation_error(self, client: TestClient) -> None:
        response = client.patch("/api/detection/config", json={"confidence_threshold": 200})
        assert response.status_code == 422

    def test_patch_detection_config_rejects_immutable_fields(self, client: TestClient) -> None:
        response = client.patch("/api/detection/config", json={"backend": "openai_compatible"})
        assert response.status_code == 422

    def test_patch_detection_config_empty_body(self, client: TestClient) -> None:
        response = client.patch("/api/detection/config", json={})
        assert response.status_code == 400


class TestWebSocket:
    def test_websocket_connect_disconnect(self, client: TestClient) -> None:
        with client.websocket_connect("/api/system/ws") as ws:
            assert ws is not None
