"""Camera lifecycle management service.

Owns creation, configuration, persistence, and teardown of virtual cameras.
Dispatches to the appropriate stream grabber (RTSP or MJPEG) based on the
camera's source stream type.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog

from onvify.models.camera import Camera, CameraStatus

logger = structlog.get_logger()


class CameraManager:
    """Manages the lifecycle of all virtual cameras."""

    def __init__(self) -> None:
        self._cameras: dict[UUID, Camera] = {}

    @property
    def cameras(self) -> dict[UUID, Camera]:
        return dict(self._cameras)

    def add_camera(self, camera: Camera) -> Camera:
        if camera.id in self._cameras:
            msg = f"Camera {camera.id} already exists"
            raise ValueError(msg)

        self._cameras[camera.id] = camera
        logger.info("camera_added", camera_id=str(camera.id), name=camera.name)
        return camera

    def get_camera(self, camera_id: UUID) -> Camera | None:
        return self._cameras.get(camera_id)

    def update_camera(self, camera_id: UUID, **kwargs: object) -> Camera:
        camera = self._cameras.get(camera_id)
        if camera is None:
            msg = f"Camera {camera_id} not found"
            raise KeyError(msg)

        updated = camera.model_copy(update={**kwargs, "updated_at": datetime.now()})
        self._cameras[camera_id] = updated
        logger.info("camera_updated", camera_id=str(camera_id), fields=list(kwargs.keys()))
        return updated

    def remove_camera(self, camera_id: UUID) -> Camera:
        camera = self._cameras.pop(camera_id, None)
        if camera is None:
            msg = f"Camera {camera_id} not found"
            raise KeyError(msg)

        logger.info("camera_removed", camera_id=str(camera_id), name=camera.name)
        return camera

    def set_status(self, camera_id: UUID, status: CameraStatus) -> None:
        camera = self._cameras.get(camera_id)
        if camera is None:
            return
        self._cameras[camera_id] = camera.model_copy(update={"status": status})

    def list_cameras(self) -> list[Camera]:
        return list(self._cameras.values())
