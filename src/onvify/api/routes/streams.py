"""Stream management and MJPEG preview endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from onvify.api.dependencies import get_camera_manager, get_stream_consumer
from onvify.services.camera_manager import CameraManager
from onvify.services.mjpeg import mjpeg_response_stream
from onvify.services.stream_consumer import StreamConsumer

router = APIRouter()

ManagerDep = Annotated[CameraManager, Depends(get_camera_manager)]
ConsumerDep = Annotated[StreamConsumer, Depends(get_stream_consumer)]


@router.get("/")
async def list_streams(manager: ManagerDep, consumer: ConsumerDep) -> list[dict[str, object]]:
    streams: list[dict[str, object]] = []
    for cam in manager.list_cameras():
        primary = cam.primary_stream
        streams.append(
            {
                "camera_id": str(cam.id),
                "camera_name": cam.name,
                "status": cam.status.value,
                "stream_type": primary.stream_type.value if primary else None,
                "source_url": primary.url if primary else None,
                "ai_active": cam.id in consumer.active_cameras,
            }
        )
    return streams


@router.get("/{camera_id}/mjpeg")
async def mjpeg_preview(camera_id: UUID, manager: ManagerDep, consumer: ConsumerDep) -> StreamingResponse:
    camera = manager.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    queue = consumer.get_frame_queue(camera_id)
    if queue is None:
        raise HTTPException(status_code=409, detail="Stream consumer not active for this camera")

    return StreamingResponse(
        mjpeg_response_stream(queue),
        media_type="multipart/x-mixed-replace; boundary=--frame",
    )
