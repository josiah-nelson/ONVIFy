"""FastAPI dependency injection providers."""

from __future__ import annotations

from functools import lru_cache

from onvify.config import Settings
from onvify.services.camera_manager import CameraManager


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


_camera_manager: CameraManager | None = None


def get_camera_manager() -> CameraManager:
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
    return _camera_manager
