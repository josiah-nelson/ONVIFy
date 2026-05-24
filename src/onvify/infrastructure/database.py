"""SQLite + aiosqlite database setup.

Provides async database access for camera configs, detection events,
and audit logs. Uses raw aiosqlite for now; can be upgraded to
SQLAlchemy + alembic when schema complexity warrants it.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import aiosqlite
import structlog

from onvify.models.camera import Camera
from onvify.models.detection import DetectionEvent

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

    # ── Camera persistence ──────────────────────────

    async def list_cameras(self) -> list[Camera]:
        cursor = await self.connection.execute("SELECT config_json FROM cameras ORDER BY name")
        rows = await cursor.fetchall()
        return [Camera.model_validate_json(row[0]) for row in rows]

    async def save_camera(self, camera: Camera) -> None:
        config_json = camera.model_dump_json()
        await self.connection.execute(
            """INSERT INTO cameras (id, name, config_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name = excluded.name,
                 config_json = excluded.config_json,
                 updated_at = excluded.updated_at""",
            (
                str(camera.id),
                camera.name,
                config_json,
                camera.created_at.isoformat(),
                camera.updated_at.isoformat(),
            ),
        )
        await self.connection.commit()

    async def delete_camera(self, camera_id: UUID) -> None:
        await self.connection.execute("DELETE FROM cameras WHERE id = ?", (str(camera_id),))
        await self.connection.commit()

    # ── Detection event persistence ─────────────────

    async def save_detection_event(self, event: DetectionEvent) -> None:
        detections_json = json.dumps([d.model_dump() for d in event.detections])
        await self.connection.execute(
            """INSERT INTO detection_events (id, camera_id, timestamp, detections_json, inference_time_ms, backend)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(event.id),
                str(event.camera_id),
                event.timestamp.isoformat(),
                detections_json,
                event.inference_time_ms,
                event.backend,
            ),
        )
        await self.connection.commit()

    async def list_detection_events(
        self,
        camera_id: UUID | None = None,
        limit: int = 100,
    ) -> list[DetectionEvent]:
        if camera_id:
            cursor = await self.connection.execute(
                "SELECT id, camera_id, timestamp, detections_json, inference_time_ms, backend "
                "FROM detection_events WHERE camera_id = ? ORDER BY timestamp DESC LIMIT ?",
                (str(camera_id), limit),
            )
        else:
            cursor = await self.connection.execute(
                "SELECT id, camera_id, timestamp, detections_json, inference_time_ms, backend "
                "FROM detection_events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        events: list[DetectionEvent] = []
        for row in rows:
            from onvify.models.detection import Detection

            detections = [Detection.model_validate(d) for d in json.loads(row[3])]
            events.append(
                DetectionEvent(
                    id=UUID(row[0]),
                    camera_id=UUID(row[1]),
                    timestamp=row[2],
                    detections=detections,
                    inference_time_ms=row[4],
                    backend=row[5] or "unknown",
                )
            )
        return events
