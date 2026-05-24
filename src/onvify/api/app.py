"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from onvify import __version__
from onvify.api.routes import cameras, detection, streams, system

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("onvify_starting", version=__version__)
    yield
    logger.info("onvify_shutting_down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="ONVIFy",
        description="Enterprise ONVIF/RTSP virtual camera server with pluggable AI detection",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(cameras.router, prefix="/api/cameras", tags=["cameras"])
    app.include_router(streams.router, prefix="/api/streams", tags=["streams"])
    app.include_router(detection.router, prefix="/api/detection", tags=["detection"])
    app.include_router(system.router, prefix="/api/system", tags=["system"])

    return app
