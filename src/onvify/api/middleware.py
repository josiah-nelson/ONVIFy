"""ASGI middleware for structured log context binding."""

from __future__ import annotations

from typing import Any

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send


class StructlogContextMiddleware:
    """Bind camera_id and stream_id context without wrapping streaming responses."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self._app(scope, receive, send)
            return

        structlog.contextvars.clear_contextvars()
        context = _extract_log_context(scope)
        if context:
            structlog.contextvars.bind_contextvars(**context)
        try:
            await self._app(scope, receive, send)
        finally:
            structlog.contextvars.clear_contextvars()


def _extract_log_context(scope: Scope) -> dict[str, str]:
    context: dict[str, str] = {}
    raw_path_params = scope.get("path_params")
    if isinstance(raw_path_params, dict):
        context.update(_string_context(raw_path_params))
    if context:
        return context
    return _path_context(str(scope.get("path", "")))


def _string_context(values: dict[str, Any]) -> dict[str, str]:
    context: dict[str, str] = {}
    camera_id = values.get("camera_id")
    if camera_id is not None:
        context["camera_id"] = str(camera_id)
    stream_id = values.get("stream_id")
    if stream_id is not None:
        context["stream_id"] = str(stream_id)
    return context


def _path_context(path: str) -> dict[str, str]:
    parts = [part for part in path.split("/") if part]
    if len(parts) < 3 or parts[0] != "api":
        return {}
    if parts[1] in {"cameras", "streams"}:
        return {"camera_id": parts[2]}
    return {}
