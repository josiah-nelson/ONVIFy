"""System health, diagnostics, version, and WebSocket endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from onvify import __version__
from onvify.api.dependencies import (
    get_camera_manager,
    get_database,
    get_inference_backend,
    get_mediamtx_manager,
    get_stream_consumer,
    get_ws_manager,
)
from onvify.api.websocket import ConnectionManager
from onvify.inference.protocol import BackendHealth, BackendStatus, InferenceBackend
from onvify.infrastructure.database import Database
from onvify.models.camera import CameraStatus
from onvify.services.camera_manager import CameraManager
from onvify.services.stream_consumer import StreamConsumer
from onvify.services.streaming import MediaMTXManager

router = APIRouter()

DatabaseDep = Annotated[Database, Depends(get_database)]
ManagerDep = Annotated[CameraManager, Depends(get_camera_manager)]
MediaMTXDep = Annotated[MediaMTXManager, Depends(get_mediamtx_manager)]
ConsumerDep = Annotated[StreamConsumer, Depends(get_stream_consumer)]
InferenceBackendDep = Annotated[InferenceBackend, Depends(get_inference_backend)]
WSManagerDep = Annotated[ConnectionManager, Depends(get_ws_manager)]


@router.get("/health")
async def health_check(
    db: DatabaseDep,
    manager: ManagerDep,
    mediamtx: MediaMTXDep,
    consumer: ConsumerDep,
    backend: InferenceBackendDep,
) -> dict[str, object]:
    cameras = manager.list_cameras()
    database_connected = await db.health_check()
    inference = await _inference_health(backend)
    mediamtx_status = _mediamtx_status(mediamtx)
    status = _overall_status(
        database_connected=database_connected,
        inference_health=inference.health,
        mediamtx_configured=mediamtx.is_configured,
        mediamtx_running=mediamtx.is_running,
    )
    return {
        "status": status,
        "version": __version__,
        "cameras_total": len(cameras),
        "cameras_online": sum(1 for c in cameras if c.status == CameraStatus.ONLINE),
        "stream_consumers_active": len(consumer.active_cameras),
        "ai_consumers_active": len(consumer.active_ai_cameras),
        "database": {"connected": database_connected},
        "mediamtx": mediamtx_status,
        "inference": inference.model_dump(mode="json"),
    }


async def _inference_health(backend: InferenceBackend) -> BackendStatus:
    try:
        return await backend.health_check()
    except Exception as exc:
        return BackendStatus(health=BackendHealth.UNAVAILABLE, message=str(exc))


def _mediamtx_status(mediamtx: MediaMTXManager) -> dict[str, object]:
    return {
        "configured": mediamtx.is_configured,
        "running": mediamtx.is_running,
        "pid": mediamtx.pid,
    }


def _overall_status(
    *,
    database_connected: bool,
    inference_health: BackendHealth,
    mediamtx_configured: bool,
    mediamtx_running: bool,
) -> str:
    if not database_connected or inference_health == BackendHealth.UNAVAILABLE:
        return "unavailable"
    if inference_health == BackendHealth.DEGRADED or (mediamtx_configured and not mediamtx_running):
        return "degraded"
    return "ok"


@router.get("/version")
async def get_version() -> dict[str, str]:
    return {"version": __version__}


@router.websocket("/ws")
async def websocket_events(websocket: WebSocket) -> None:
    ws_manager: ConnectionManager = websocket.app.state.ws_manager
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)
