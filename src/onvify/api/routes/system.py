"""System health, diagnostics, version, and WebSocket endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from onvify import __version__
from onvify.api.dependencies import get_camera_manager, get_stream_consumer, get_ws_manager
from onvify.api.websocket import ConnectionManager
from onvify.services.camera_manager import CameraManager
from onvify.services.stream_consumer import StreamConsumer

router = APIRouter()

ManagerDep = Annotated[CameraManager, Depends(get_camera_manager)]
ConsumerDep = Annotated[StreamConsumer, Depends(get_stream_consumer)]
WSManagerDep = Annotated[ConnectionManager, Depends(get_ws_manager)]


@router.get("/health")
async def health_check(manager: ManagerDep, consumer: ConsumerDep) -> dict[str, object]:
    cameras = manager.list_cameras()
    return {
        "status": "ok",
        "version": __version__,
        "cameras_total": len(cameras),
        "cameras_online": sum(1 for c in cameras if c.status.value == "online"),
        "ai_consumers_active": len(consumer.active_cameras),
    }


@router.get("/version")
async def get_version() -> dict[str, str]:
    return {"version": __version__}


@router.websocket("/ws")
async def websocket_events(websocket: WebSocket, ws_manager: WSManagerDep) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
