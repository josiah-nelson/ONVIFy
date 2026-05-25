"""FastAPI middleware for structured log context binding."""

from __future__ import annotations

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class StructlogContextMiddleware(BaseHTTPMiddleware):
    """Bind camera_id (and stream_id when present) from path parameters to structlog context.

    This ensures all log messages emitted during request processing automatically
    include the relevant identifiers without manual passing.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        structlog.contextvars.clear_contextvars()

        path_params = request.path_params
        if "camera_id" in path_params:
            structlog.contextvars.bind_contextvars(camera_id=str(path_params["camera_id"]))
        if "stream_id" in path_params:
            structlog.contextvars.bind_contextvars(stream_id=str(path_params["stream_id"]))

        try:
            return await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
