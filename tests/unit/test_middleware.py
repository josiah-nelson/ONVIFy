"""Tests for ASGI log-context middleware."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
import structlog
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from onvify.api.middleware import StructlogContextMiddleware, bind_request_log_context


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


class TestStructlogContextMiddleware:
    @pytest.mark.asyncio
    async def test_binds_camera_id_from_known_path(self) -> None:
        contexts: list[dict[str, Any]] = []
        messages: list[Message] = []
        camera_id = str(uuid4())

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            contexts.append(structlog.contextvars.get_contextvars())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        async def send(message: Message) -> None:
            messages.append(message)

        scope: Scope = {"type": "http", "path": f"/api/streams/{camera_id}/mjpeg"}

        await StructlogContextMiddleware(app)(scope, _receive, send)

        assert contexts == [{"camera_id": camera_id}]
        assert [message["type"] for message in messages] == ["http.response.start", "http.response.body"]
        assert structlog.contextvars.get_contextvars() == {}

    @pytest.mark.asyncio
    async def test_does_not_bind_stream_status_as_camera_id(self) -> None:
        contexts: list[dict[str, Any]] = []

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            contexts.append(structlog.contextvars.get_contextvars())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        async def send(message: Message) -> None:
            return None

        scope: Scope = {"type": "http", "path": "/api/streams/status"}

        await StructlogContextMiddleware(app)(scope, _receive, send)

        assert contexts == [{}]
        assert structlog.contextvars.get_contextvars() == {}

    def test_bind_request_log_context_uses_routed_path_params(self) -> None:
        scope: Scope = {
            "type": "http",
            "path": "/ignored",
            "headers": [],
            "path_params": {"camera_id": "cam-1", "stream_id": "main"},
        }

        structlog.contextvars.clear_contextvars()
        try:
            bind_request_log_context(Request(scope))

            assert structlog.contextvars.get_contextvars() == {"camera_id": "cam-1", "stream_id": "main"}
        finally:
            structlog.contextvars.clear_contextvars()

    def test_bind_request_log_context_ignores_none_stream_id(self) -> None:
        scope: Scope = {
            "type": "http",
            "path": "/ignored",
            "headers": [],
            "path_params": {"camera_id": "cam-1", "stream_id": None},
        }

        structlog.contextvars.clear_contextvars()
        try:
            bind_request_log_context(Request(scope))

            assert structlog.contextvars.get_contextvars() == {"camera_id": "cam-1"}
        finally:
            structlog.contextvars.clear_contextvars()
