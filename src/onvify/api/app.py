"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from onvify import __version__
from onvify.api.dependencies import get_settings
from onvify.api.middleware import StructlogContextMiddleware, bind_request_log_context
from onvify.api.routes import cameras, detection, streams, system
from onvify.api.websocket import ConnectionManager
from onvify.config import Settings
from onvify.inference.factory import create_inference_backend
from onvify.infrastructure.database import Database
from onvify.services.camera_manager import CameraManager
from onvify.services.mediamtx_binary import resolve_mediamtx_binary
from onvify.services.stream_consumer import StreamConsumer
from onvify.services.streaming import MediaMTXManager

logger = structlog.get_logger()

_INDEX_CACHE_HEADERS = {"Cache-Control": "no-cache, must-revalidate"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    db = Database(settings.root_dir / "data" / "onvify.db")

    try:
        await db.connect()
        app.state.database = db

        manager = CameraManager(database=db)
        await manager.load_from_database()
        app.state.camera_manager = manager

        mediamtx_bin = await asyncio.to_thread(resolve_mediamtx_binary, settings)
        mediamtx = MediaMTXManager(settings, mediamtx_bin=mediamtx_bin)
        mediamtx.write_config(manager.list_cameras())
        mediamtx.start()
        app.state.mediamtx = mediamtx

        ws_manager = ConnectionManager()
        app.state.ws_manager = ws_manager

        backend = create_inference_backend(settings.inference)
        app.state.inference_backend = backend
        consumer = StreamConsumer(
            camera_manager=manager,
            backend=backend,
            database=db,
            ws_manager=ws_manager,
            motion_sensitivity=settings.inference.motion_sensitivity,
            confidence_threshold=settings.inference.confidence_threshold / 100.0,
            cooldown_seconds=settings.inference.cooldown_seconds,
            reconnect_base=settings.streaming.grabber_reconnect_base,
            reconnect_max=settings.streaming.grabber_reconnect_max,
            target_interval=settings.inference.target_interval,
        )
        consumer.start_all()
        app.state.stream_consumer = consumer

        logger.info(
            "onvify_started",
            version=__version__,
            cameras=len(manager.list_cameras()),
            ai_cameras=len(consumer.active_ai_cameras),
            inference_backend=settings.inference.backend,
        )

        yield
    finally:
        if hasattr(app.state, "stream_consumer"):
            await app.state.stream_consumer.stop_all_async()
        if hasattr(app.state, "mediamtx"):
            app.state.mediamtx.stop()
        await db.disconnect()
        logger.info("onvify_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="ONVIFy",
        description="Enterprise ONVIF/RTSP virtual camera server with pluggable AI detection",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(StructlogContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    log_context_dependency = [Depends(bind_request_log_context)]
    app.include_router(cameras.router, prefix="/api/cameras", tags=["cameras"], dependencies=log_context_dependency)
    app.include_router(streams.router, prefix="/api/streams", tags=["streams"], dependencies=log_context_dependency)
    app.include_router(detection.router, prefix="/api/detection", tags=["detection"])
    app.include_router(system.router, prefix="/api/system", tags=["system"])
    _register_frontend_routes(app, get_settings())

    return app


def _register_frontend_routes(app: FastAPI, settings: Settings) -> None:
    dist_dir = _frontend_dist_dir(settings)
    if dist_dir is None:
        return

    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend_assets")

    index_path = dist_dir / "index.html"
    dist_root = dist_dir.resolve()

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return _frontend_index_response(index_path)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend_fallback(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = (dist_root / full_path).resolve()
        try:
            candidate.relative_to(dist_root)
        except ValueError as err:
            raise HTTPException(status_code=404, detail="Not Found") from err

        if candidate.is_file():
            return FileResponse(candidate)
        return _frontend_index_response(index_path)


def _frontend_dist_dir(settings: Settings) -> Path | None:
    dist_dir = settings.frontend_dist_dir or settings.root_dir / "frontend" / "dist"
    index_path = dist_dir / "index.html"
    return dist_dir if index_path.is_file() else None


def _frontend_index_response(index_path: Path) -> FileResponse:
    return FileResponse(index_path, headers=_INDEX_CACHE_HEADERS)
