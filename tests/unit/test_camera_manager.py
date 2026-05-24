"""Tests for camera lifecycle management."""

from __future__ import annotations

import pytest

from onvify.models.camera import Camera, CameraStatus, StreamType
from onvify.services.camera_manager import CameraManager


class TestCameraManager:
    @pytest.mark.asyncio
    async def test_add_and_list(self, camera_manager: CameraManager, sample_camera: Camera) -> None:
        await camera_manager.add_camera(sample_camera)
        assert len(camera_manager.list_cameras()) == 1
        assert camera_manager.list_cameras()[0].id == sample_camera.id

    @pytest.mark.asyncio
    async def test_add_duplicate_raises(self, camera_manager: CameraManager, sample_camera: Camera) -> None:
        await camera_manager.add_camera(sample_camera)
        with pytest.raises(ValueError, match="already exists"):
            await camera_manager.add_camera(sample_camera)

    @pytest.mark.asyncio
    async def test_get_camera(self, camera_manager: CameraManager, sample_camera: Camera) -> None:
        await camera_manager.add_camera(sample_camera)
        result = camera_manager.get_camera(sample_camera.id)
        assert result is not None
        assert result.name == "Test Camera"

    def test_get_missing_camera(self, camera_manager: CameraManager) -> None:
        from uuid import uuid4

        assert camera_manager.get_camera(uuid4()) is None

    @pytest.mark.asyncio
    async def test_update_camera(self, camera_manager: CameraManager, sample_camera: Camera) -> None:
        await camera_manager.add_camera(sample_camera)
        updated = await camera_manager.update_camera(sample_camera.id, name="Renamed Camera")
        assert updated.name == "Renamed Camera"

    @pytest.mark.asyncio
    async def test_update_missing_raises(self, camera_manager: CameraManager) -> None:
        from uuid import uuid4

        with pytest.raises(KeyError, match="not found"):
            await camera_manager.update_camera(uuid4(), name="x")

    @pytest.mark.asyncio
    async def test_remove_camera(self, camera_manager: CameraManager, sample_camera: Camera) -> None:
        await camera_manager.add_camera(sample_camera)
        removed = await camera_manager.remove_camera(sample_camera.id)
        assert removed.id == sample_camera.id
        assert len(camera_manager.list_cameras()) == 0

    @pytest.mark.asyncio
    async def test_remove_missing_raises(self, camera_manager: CameraManager) -> None:
        from uuid import uuid4

        with pytest.raises(KeyError, match="not found"):
            await camera_manager.remove_camera(uuid4())

    @pytest.mark.asyncio
    async def test_set_status(self, camera_manager: CameraManager, sample_camera: Camera) -> None:
        await camera_manager.add_camera(sample_camera)
        camera_manager.set_status(sample_camera.id, CameraStatus.ONLINE)
        camera = camera_manager.get_camera(sample_camera.id)
        assert camera is not None
        assert camera.status == CameraStatus.ONLINE

    @pytest.mark.asyncio
    async def test_mjpeg_camera(self, camera_manager: CameraManager, sample_mjpeg_camera: Camera) -> None:
        await camera_manager.add_camera(sample_mjpeg_camera)
        camera = camera_manager.get_camera(sample_mjpeg_camera.id)
        assert camera is not None
        assert camera.stream_type == StreamType.MJPEG
