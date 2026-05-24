"""Tests for stream consumer lifecycle decisions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import cast

import pytest

from onvify.api.websocket import ConnectionManager
from onvify.inference.protocol import InferenceBackend
from onvify.infrastructure.database import Database
from onvify.models.camera import Camera, Stream, StreamType
from onvify.services import mjpeg
from onvify.services.camera_manager import CameraManager
from onvify.services.stream_consumer import StreamConsumer


class IdleStreamConsumer(StreamConsumer):
    async def _consume_loop(self, camera: Camera) -> None:
        await asyncio.Event().wait()


def make_consumer(manager: CameraManager) -> IdleStreamConsumer:
    return IdleStreamConsumer(
        camera_manager=manager,
        backend=cast(InferenceBackend, object()),
        database=cast(Database, object()),
        ws_manager=ConnectionManager(),
    )


class TestStreamConsumerLifecycle:
    @pytest.mark.asyncio
    async def test_rtsp_without_ai_does_not_start(self) -> None:
        manager = CameraManager()
        camera = Camera(name="RTSP", source_streams=[Stream(url="rtsp://x")])
        await manager.add_camera(camera)
        consumer = make_consumer(manager)

        consumer.start_camera(camera)

        assert consumer.active_cameras == set()

    @pytest.mark.asyncio
    async def test_rtsp_with_ai_starts_as_ai_active(self) -> None:
        manager = CameraManager()
        camera = Camera(name="AI", source_streams=[Stream(url="rtsp://x")], ai_enabled=True)
        await manager.add_camera(camera)
        consumer = make_consumer(manager)

        consumer.start_camera(camera)

        assert consumer.active_cameras == {camera.id}
        assert consumer.active_ai_cameras == {camera.id}
        await consumer.stop_all_async()

    @pytest.mark.asyncio
    async def test_mjpeg_without_ai_starts_for_preview_only(self) -> None:
        manager = CameraManager()
        camera = Camera(
            name="MJPEG",
            source_streams=[Stream(url="http://example.test/mjpeg", stream_type=StreamType.MJPEG)],
        )
        await manager.add_camera(camera)
        consumer = make_consumer(manager)

        consumer.start_camera(camera)

        assert consumer.active_cameras == {camera.id}
        assert consumer.active_ai_cameras == set()
        await consumer.stop_all_async()

    @pytest.mark.asyncio
    async def test_stop_then_start_keeps_new_task_tracked_after_old_task_finishes(self) -> None:
        manager = CameraManager()
        camera = Camera(name="AI", source_streams=[Stream(url="rtsp://x")], ai_enabled=True)
        await manager.add_camera(camera)
        consumer = make_consumer(manager)

        consumer.start_camera(camera)
        consumer.stop_camera(camera.id)
        consumer.start_camera(camera)
        await asyncio.sleep(0)

        assert consumer.active_cameras == {camera.id}
        assert consumer.active_ai_cameras == {camera.id}
        assert consumer.get_frame_queue(camera.id) is not None
        await consumer.stop_all_async()

    @pytest.mark.asyncio
    async def test_status_change_broadcasts_via_websocket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        manager = CameraManager()
        camera = Camera(
            name="MJPEG",
            source_streams=[Stream(url="http://example.test/mjpeg", stream_type=StreamType.MJPEG)],
        )
        await manager.add_camera(camera)

        broadcasts: list[dict[str, object]] = []
        ws = ConnectionManager()

        async def record_broadcast(event: dict[str, object]) -> None:
            broadcasts.append(event)

        monkeypatch.setattr(ws, "broadcast", record_broadcast)
        consumer = StreamConsumer(
            camera_manager=manager,
            backend=cast(InferenceBackend, object()),
            database=cast(Database, object()),
            ws_manager=ws,
        )
        consumer._target_interval = 0
        consumer._frame_queues[camera.id] = asyncio.Queue(maxsize=2)

        async def pull_one_frame(url: str) -> AsyncIterator[bytes]:
            yield b"jpeg"

        monkeypatch.setattr(mjpeg, "pull_mjpeg_frames", pull_one_frame)

        await consumer._consume_mjpeg(camera, "http://example.test/mjpeg", None)

        status_events = [e for e in broadcasts if e.get("type") == "camera.status"]
        assert len(status_events) == 1
        assert status_events[0]["camera_id"] == str(camera.id)
        assert status_events[0]["status"] == "online"

    @pytest.mark.asyncio
    async def test_mjpeg_preview_without_pipeline_does_not_decode_frames(self, monkeypatch: pytest.MonkeyPatch) -> None:
        manager = CameraManager()
        camera = Camera(
            name="MJPEG",
            source_streams=[Stream(url="http://example.test/mjpeg", stream_type=StreamType.MJPEG)],
        )
        await manager.add_camera(camera)
        consumer = make_consumer(manager)
        consumer._target_interval = 0
        frame_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2)
        consumer._frame_queues[camera.id] = frame_queue

        async def pull_one_frame(url: str) -> AsyncIterator[bytes]:
            yield b"jpeg"

        def fail_decode(data: bytes) -> object:
            msg = "preview-only consumers should not decode frames"
            raise AssertionError(msg)

        monkeypatch.setattr(mjpeg, "pull_mjpeg_frames", pull_one_frame)
        monkeypatch.setattr(mjpeg, "decode_jpeg_frame", fail_decode)

        await consumer._consume_mjpeg(camera, "http://example.test/mjpeg", None)

        assert await frame_queue.get() == b"jpeg"
