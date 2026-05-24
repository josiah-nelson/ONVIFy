"""Camera CRUD endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from onvify.api.dependencies import get_camera_manager, get_mediamtx_manager, get_stream_consumer
from onvify.models.camera import Camera, Stream, StreamType
from onvify.services.camera_manager import CameraManager
from onvify.services.stream_consumer import StreamConsumer
from onvify.services.streaming import MediaMTXManager

router = APIRouter()

ManagerDep = Annotated[CameraManager, Depends(get_camera_manager)]
MediaMTXDep = Annotated[MediaMTXManager, Depends(get_mediamtx_manager)]
ConsumerDep = Annotated[StreamConsumer, Depends(get_stream_consumer)]

logger = structlog.get_logger()


class CreateCameraRequest(BaseModel):
    name: str
    source_url: str
    stream_type: StreamType = StreamType.RTSP
    ai_enabled: bool = False
    ai_model: str | None = None
    onvif_username: str | None = None
    onvif_password: str | None = None


class UpdateCameraRequest(BaseModel):
    name: str | None = None
    ai_enabled: bool | None = None
    ai_model: str | None = None


async def _reload_mediamtx(mediamtx: MediaMTXManager, cameras: list[Camera]) -> None:
    try:
        await asyncio.to_thread(mediamtx.reload_config, cameras)
    except Exception as exc:
        logger.error("mediamtx_reload_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="MediaMTX config reload failed") from exc


async def _rollback_mediamtx(
    mediamtx: MediaMTXManager,
    cameras: list[Camera],
    operation: str,
    camera_id: UUID,
) -> None:
    try:
        await _reload_mediamtx(mediamtx, cameras)
    except HTTPException as exc:
        logger.error(
            "mediamtx_rollback_failed",
            operation=operation,
            camera_id=str(camera_id),
            detail=exc.detail,
        )


def _replace_camera(cameras: list[Camera], replacement: Camera) -> list[Camera]:
    return [replacement if camera.id == replacement.id else camera for camera in cameras]


@router.get("/")
async def list_cameras(manager: ManagerDep) -> list[Camera]:
    return manager.list_cameras()


@router.post("/", status_code=201)
async def create_camera(
    body: CreateCameraRequest,
    manager: ManagerDep,
    mediamtx: MediaMTXDep,
    consumer: ConsumerDep,
) -> Camera:
    stream = Stream(url=body.source_url, stream_type=body.stream_type)
    camera = Camera(
        name=body.name,
        source_streams=[stream],
        ai_enabled=body.ai_enabled,
        ai_model=body.ai_model,
        onvif_username=body.onvif_username,
        onvif_password=body.onvif_password,
    )
    await _reload_mediamtx(mediamtx, [*manager.list_cameras(), camera])
    try:
        created = await manager.add_camera(camera)
    except Exception:
        await _rollback_mediamtx(mediamtx, manager.list_cameras(), "create", camera.id)
        raise
    consumer.start_camera(created)
    return created


@router.get("/{camera_id}")
async def get_camera(camera_id: UUID, manager: ManagerDep) -> Camera:
    camera = manager.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@router.patch("/{camera_id}")
async def update_camera(
    camera_id: UUID,
    body: UpdateCameraRequest,
    manager: ManagerDep,
    mediamtx: MediaMTXDep,
    consumer: ConsumerDep,
) -> Camera:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    current = manager.get_camera(camera_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    candidate = current.model_copy(update=updates)
    await _reload_mediamtx(mediamtx, _replace_camera(manager.list_cameras(), candidate))
    try:
        updated = await manager.update_camera(camera_id, **updates)
    except KeyError as err:
        await _rollback_mediamtx(mediamtx, manager.list_cameras(), "update_missing", camera_id)
        raise HTTPException(status_code=404, detail="Camera not found") from err
    except Exception:
        await _rollback_mediamtx(mediamtx, manager.list_cameras(), "update", camera_id)
        raise
    consumer.stop_camera(camera_id)
    consumer.start_camera(updated)
    return updated


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(camera_id: UUID, manager: ManagerDep, mediamtx: MediaMTXDep, consumer: ConsumerDep) -> None:
    current = manager.get_camera(camera_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    remaining = [camera for camera in manager.list_cameras() if camera.id != camera_id]
    await _reload_mediamtx(mediamtx, remaining)
    try:
        await manager.remove_camera(camera_id)
    except KeyError as err:
        raise HTTPException(status_code=404, detail="Camera not found") from err
    except Exception:
        await _rollback_mediamtx(mediamtx, manager.list_cameras(), "delete", camera_id)
        raise
    consumer.stop_camera(camera_id)
