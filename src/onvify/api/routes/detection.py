"""AI detection configuration and event endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/config")
def get_detection_config() -> dict[str, str]:
    return {"status": "not_implemented"}
