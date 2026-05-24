"""WebSocket manager for real-time detection events and camera status."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import WebSocket

logger = structlog.get_logger()


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        logger.info("websocket_connected", total=len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections = [c for c in self._connections if c is not websocket]
        logger.info("websocket_disconnected", total=len(self._connections))

    async def broadcast(self, event: dict[str, Any]) -> None:
        async with self._lock:
            stale: list[WebSocket] = []
            for conn in self._connections:
                try:
                    await conn.send_json(event)
                except Exception:
                    stale.append(conn)
            for conn in stale:
                self._connections.remove(conn)
