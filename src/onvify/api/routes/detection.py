"""AI detection configuration, event history, and health endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from onvify.api.dependencies import get_database, get_inference_backend, get_settings
from onvify.config import Settings
from onvify.inference.protocol import BackendStatus, InferenceBackend
from onvify.infrastructure.database import Database
from onvify.models.detection import DetectionEvent

router = APIRouter()

DatabaseDep = Annotated[Database, Depends(get_database)]
InferenceBackendDep = Annotated[InferenceBackend, Depends(get_inference_backend)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/config")
async def get_detection_config(settings: SettingsDep) -> dict[str, object]:
    inf = settings.inference
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


@router.get("/events")
async def list_detection_events(
    db: DatabaseDep,
    camera_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[DetectionEvent]:
    return await db.list_detection_events(camera_id=camera_id, limit=limit)


@router.get("/health")
async def get_detection_health(backend: InferenceBackendDep) -> BackendStatus:
    return await backend.health_check()
