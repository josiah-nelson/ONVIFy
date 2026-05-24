"""SQLite + aiosqlite database setup.

Provides async database access for camera configs, detection events,
and audit logs. Uses raw aiosqlite for now; can be upgraded to
SQLAlchemy + alembic when schema complexity warrants it.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import structlog

logger = structlog.get_logger()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS detection_events (
    id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    detections_json TEXT NOT NULL,
    inference_time_ms REAL,
    backend TEXT,
    FOREIGN KEY (camera_id) REFERENCES cameras(id)
);
"""


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._path))
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        logger.info("database_connected", path=str(self._path))

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("database_disconnected")

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            msg = "Database not connected"
            raise RuntimeError(msg)
        return self._conn
