"""Camera CRUD endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from onvify.api.dependencies import get_camera_manager
from onvify.models.camera import Camera, Stream, StreamType
from onvify.services.camera_manager import CameraManager

router = APIRouter()

ManagerDep = Annotated[CameraManager, Depends(get_camera_manager)]


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
def list_cameras(manager: ManagerDep) -> list[Camera]:
    return manager.list_cameras()


@router.post("/", status_code=201)
def create_camera(body: CreateCameraRequest, manager: ManagerDep) -> Camera:
    stream = Stream(url=body.source_url, stream_type=body.stream_type)
    camera = Camera(
        name=body.name,
        source_streams=[stream],
        ai_enabled=body.ai_enabled,
        ai_model=body.ai_model,
        onvif_username=body.onvif_username,
        onvif_password=body.onvif_password,
    )
    return manager.add_camera(camera)


@router.get("/{camera_id}")
def get_camera(camera_id: UUID, manager: ManagerDep) -> Camera:
    camera = manager.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@router.patch("/{camera_id}")
def update_camera(camera_id: UUID, body: UpdateCameraRequest, manager: ManagerDep) -> Camera:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        return manager.update_camera(camera_id, **updates)
    except KeyError as err:
        raise HTTPException(status_code=404, detail="Camera not found") from err


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: UUID, manager: ManagerDep) -> None:
    try:
        manager.remove_camera(camera_id)
    except KeyError as err:
        raise HTTPException(status_code=404, detail="Camera not found") from err
