"""Camera CRUD endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

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
    created = await manager.add_camera(camera)
    mediamtx.reload_config(manager.list_cameras())
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
    try:
        updated = await manager.update_camera(camera_id, **updates)
    except KeyError as err:
        raise HTTPException(status_code=404, detail="Camera not found") from err
    mediamtx.reload_config(manager.list_cameras())
    consumer.stop_camera(camera_id)
    consumer.start_camera(updated)
    return updated


@router.delete("/{camera_id}", status_code=204)
async def delete_camera(camera_id: UUID, manager: ManagerDep, mediamtx: MediaMTXDep, consumer: ConsumerDep) -> None:
    try:
        await manager.remove_camera(camera_id)
    except KeyError as err:
        raise HTTPException(status_code=404, detail="Camera not found") from err
    consumer.stop_camera(camera_id)
    mediamtx.reload_config(manager.list_cameras())
