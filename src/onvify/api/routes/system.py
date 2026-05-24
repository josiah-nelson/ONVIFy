"""System health, diagnostics, and version endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from onvify import __version__

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/version")
def get_version() -> dict[str, str]:
    return {"version": __version__}
