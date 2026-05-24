"""Tests for SQLite persistence layer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

from onvify.infrastructure.database import Database
from onvify.models.camera import Camera, Stream, StreamType
from onvify.models.detection import BoundingBox, Detection, DetectionEvent, ObjectClass
from onvify.services.camera_manager import CameraManager


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.disconnect()


class TestCameraPersistence:
    @pytest.mark.asyncio
    async def test_save_and_load(self, db: Database) -> None:
        camera = Camera(
            name="Persisted Cam",
            source_streams=[Stream(url="rtsp://x", stream_type=StreamType.RTSP)],
        )
        await db.save_camera(camera)
        loaded = await db.list_cameras()
        assert len(loaded) == 1
        assert loaded[0].id == camera.id
        assert loaded[0].name == "Persisted Cam"

    @pytest.mark.asyncio
    async def test_upsert_on_save(self, db: Database) -> None:
        camera = Camera(
            name="Original",
            source_streams=[Stream(url="rtsp://x")],
        )
        await db.save_camera(camera)
        updated = camera.model_copy(update={"name": "Updated"})
        await db.save_camera(updated)
        loaded = await db.list_cameras()
        assert len(loaded) == 1
        assert loaded[0].name == "Updated"

    @pytest.mark.asyncio
    async def test_delete(self, db: Database) -> None:
        camera = Camera(name="ToDelete", source_streams=[Stream(url="rtsp://x")])
        await db.save_camera(camera)
        await db.delete_camera(camera.id)
        assert await db.list_cameras() == []

    @pytest.mark.asyncio
    async def test_manager_round_trip(self, db: Database) -> None:
        manager = CameraManager(database=db)
        cam = Camera(name="RT", source_streams=[Stream(url="rtsp://x")])
        await manager.add_camera(cam)

        manager2 = CameraManager(database=db)
        await manager2.load_from_database()
        assert len(manager2.list_cameras()) == 1
        assert manager2.list_cameras()[0].name == "RT"


class TestDetectionEventPersistence:
    @pytest.mark.asyncio
    async def test_save_and_query(self, db: Database) -> None:
        cam_id = uuid4()
        camera = Camera(id=cam_id, name="Cam", source_streams=[Stream(url="rtsp://x")])
        await db.save_camera(camera)

        event = DetectionEvent(
            camera_id=cam_id,
            detections=[
                Detection(
                    object_class=ObjectClass.PERSON,
                    confidence=0.9,
                    bbox=BoundingBox(x_min=0.1, y_min=0.2, x_max=0.5, y_max=0.8),
                )
            ],
            inference_time_ms=42.0,
            backend="local",
        )
        await db.save_detection_event(event)

        events = await db.list_detection_events(camera_id=cam_id)
        assert len(events) == 1
        assert events[0].camera_id == cam_id
        assert events[0].detections[0].object_class == ObjectClass.PERSON

    @pytest.mark.asyncio
    async def test_query_limit(self, db: Database) -> None:
        cam_id = uuid4()
        camera = Camera(id=cam_id, name="Cam", source_streams=[Stream(url="rtsp://x")])
        await db.save_camera(camera)

        for i in range(5):
            event = DetectionEvent(
                camera_id=cam_id,
                detections=[],
                inference_time_ms=float(i),
                backend="local",
            )
            await db.save_detection_event(event)

        events = await db.list_detection_events(limit=3)
        assert len(events) == 3
