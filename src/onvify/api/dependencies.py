"""FastAPI dependency injection providers.

All long-lived services are stored on app.state during lifespan startup
and retrieved here via the Request object.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Request

from onvify.config import Settings

if TYPE_CHECKING:
    from onvify.api.websocket import ConnectionManager
    from onvify.infrastructure.database import Database
    from onvify.services.camera_manager import CameraManager
    from onvify.services.stream_consumer import StreamConsumer
    from onvify.services.streaming import MediaMTXManager


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_database(request: Request) -> Database:
    return request.app.state.database  # type: ignore[no-any-return]


def get_camera_manager(request: Request) -> CameraManager:
    return request.app.state.camera_manager  # type: ignore[no-any-return]


def get_mediamtx_manager(request: Request) -> MediaMTXManager:
    return request.app.state.mediamtx  # type: ignore[no-any-return]


def get_ws_manager(request: Request) -> ConnectionManager:
    return request.app.state.ws_manager  # type: ignore[no-any-return]


def get_stream_consumer(request: Request) -> StreamConsumer:
    return request.app.state.stream_consumer  # type: ignore[no-any-return]
