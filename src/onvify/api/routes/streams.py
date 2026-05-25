"""Stream management and MJPEG preview endpoints."""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlparse, urlunparse
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from onvify.api.dependencies import get_camera_manager, get_settings, get_stream_consumer
from onvify.config import Settings
from onvify.services.camera_manager import CameraManager
from onvify.services.mjpeg import mjpeg_response_stream
from onvify.services.stream_consumer import StreamConsumer

logger = structlog.get_logger()

router = APIRouter()


def _redact_url(url: str) -> str:
    """Strip userinfo (credentials) from a URL before returning it to API consumers."""
    parsed = urlparse(url)
    if parsed.username:
        redacted = parsed._replace(netloc=f"***@{parsed.hostname}" + (f":{parsed.port}" if parsed.port else ""))
        return urlunparse(redacted)
    return url


ManagerDep = Annotated[CameraManager, Depends(get_camera_manager)]
ConsumerDep = Annotated[StreamConsumer, Depends(get_stream_consumer)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/")
async def list_streams(manager: ManagerDep, consumer: ConsumerDep) -> list[dict[str, object]]:
    streams: list[dict[str, object]] = []
    active = consumer.active_cameras
    ai_active = consumer.active_ai_cameras
    for cam in manager.list_cameras():
        primary = cam.primary_stream
        streams.append(
            {
                "camera_id": str(cam.id),
                "camera_name": cam.name,
                "status": cam.status.value,
                "stream_type": primary.stream_type.value if primary else None,
                "source_url": _redact_url(primary.url) if primary else None,
                "consumer_active": cam.id in active,
                "ai_active": cam.id in ai_active,
            }
        )
    return streams


@router.get("/status")
async def stream_status(settings: SettingsDep) -> list[dict[str, Any]]:
    """Query MediaMTX API for active stream paths with status, bitrate, and reader count."""
    host = settings.server.mediamtx_api_host
    api_url = f"http://{host}:{settings.server.mediamtx_api_port}/v3/paths/list"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(api_url)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("mediamtx_api_unreachable", url=api_url, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail="MediaMTX API is unreachable",
        ) from exc
    except (ValueError, KeyError) as exc:
        logger.warning("mediamtx_api_invalid_response", url=api_url, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail="MediaMTX API returned invalid response",
        ) from exc

    items: list[dict[str, Any]] = data.get("items") or []

    result: list[dict[str, Any]] = []
    for path in items:
        readers = path.get("readers")
        reader_count = len(readers) if isinstance(readers, list) else 0
        result.append(
            {
                "name": path.get("name"),
                "ready": path.get("ready", False),
                "ready_time": path.get("readyTime"),
                "readers": reader_count,
                "bytes_received": path.get("bytesReceived", 0),
                "bytes_sent": path.get("bytesSent", 0),
            }
        )
    return result


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
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
