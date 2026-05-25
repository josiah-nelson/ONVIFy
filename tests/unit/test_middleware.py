"""Tests for ASGI log-context middleware."""

from __future__ import annotations

from typing import Any

import pytest
import structlog
from starlette.types import Message, Receive, Scope, Send

from onvify.api.middleware import StructlogContextMiddleware


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


class TestStructlogContextMiddleware:
    @pytest.mark.asyncio
    async def test_binds_camera_id_from_known_path(self) -> None:
        contexts: list[dict[str, Any]] = []
        messages: list[Message] = []

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            contexts.append(structlog.contextvars.get_contextvars())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        async def send(message: Message) -> None:
            messages.append(message)

        scope: Scope = {"type": "http", "path": "/api/streams/cam-1/mjpeg"}

        await StructlogContextMiddleware(app)(scope, _receive, send)

        assert contexts == [{"camera_id": "cam-1"}]
        assert [message["type"] for message in messages] == ["http.response.start", "http.response.body"]
        assert structlog.contextvars.get_contextvars() == {}

    @pytest.mark.asyncio
    async def test_ignores_none_stream_id_from_path_params(self) -> None:
        contexts: list[dict[str, Any]] = []

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            contexts.append(structlog.contextvars.get_contextvars())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        async def send(message: Message) -> None:
            return None

        scope: Scope = {
            "type": "http",
            "path": "/ignored",
            "path_params": {"camera_id": "cam-1", "stream_id": None},
        }

        await StructlogContextMiddleware(app)(scope, _receive, send)

        assert contexts == [{"camera_id": "cam-1"}]
        assert structlog.contextvars.get_contextvars() == {}
