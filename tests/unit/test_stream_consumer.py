"""Tests for stream consumer lifecycle decisions."""

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from onvify.api.websocket import ConnectionManager
from onvify.inference.protocol import InferenceBackend
from onvify.infrastructure.database import Database
from onvify.models.camera import Camera, Stream, StreamType
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
        ws_manager=cast(ConnectionManager, object()),
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
