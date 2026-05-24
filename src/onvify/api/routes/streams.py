"""Stream management endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_streams() -> dict[str, str]:
    return {"status": "not_implemented"}
