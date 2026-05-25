"""AI detection configuration, event history, and health endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status
from pydantic import BaseModel, Field

from onvify.api.dependencies import get_database, get_inference_backend, get_settings
from onvify.config import InferenceSettings, Settings
from onvify.inference.protocol import BackendHealth, BackendStatus, InferenceBackend
from onvify.infrastructure.database import Database
from onvify.models.detection import DetectionEvent

logger = structlog.get_logger()

router = APIRouter()

DatabaseDep = Annotated[Database, Depends(get_database)]
InferenceBackendDep = Annotated[InferenceBackend, Depends(get_inference_backend)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class UpdateDetectionConfigRequest(BaseModel, extra="forbid"):
    confidence_threshold: int | None = Field(None, ge=1, le=100)
    motion_sensitivity: int | None = Field(None, ge=1, le=100)
    cooldown_seconds: float | None = Field(None, ge=0.0)
    target_interval: float | None = Field(None, ge=0.01)


def _serialize_inference_config(inf: InferenceSettings) -> dict[str, object]:
    return {
        "backend": inf.backend,
        "backend_url": inf.backend_url,
        "default_model": inf.default_model,
        "confidence_threshold_pct": inf.confidence_threshold,
        "confidence_threshold": inf.confidence_threshold / 100.0,
        "motion_sensitivity": inf.motion_sensitivity,
        "cooldown_seconds": inf.cooldown_seconds,
        "target_interval": inf.target_interval,
    }


@router.get("/config")
async def get_detection_config(settings: SettingsDep) -> dict[str, object]:
    return _serialize_inference_config(settings.inference)


@router.patch("/config")
async def update_detection_config(
    body: UpdateDetectionConfigRequest,
    settings: SettingsDep,
) -> dict[str, object]:
    inf = settings.inference
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    before = {k: getattr(inf, k) for k in updates}
    for key, value in updates.items():
        setattr(inf, key, value)
    after = {k: getattr(inf, k) for k in updates}

    logger.info("detection_config_updated", before=before, after=after)
    return _serialize_inference_config(inf)


@router.get("/events")
async def list_detection_events(
    db: DatabaseDep,
    camera_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[DetectionEvent]:
    return await db.list_detection_events(camera_id=camera_id, limit=limit)


@router.get("/health")
async def get_detection_health(backend: InferenceBackendDep, response: Response) -> BackendStatus:
    try:
        backend_status = await backend.health_check()
    except Exception as exc:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
        return BackendStatus(health=BackendHealth.UNAVAILABLE, message=str(exc))

    if backend_status.health != BackendHealth.HEALTHY:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
    return backend_status
