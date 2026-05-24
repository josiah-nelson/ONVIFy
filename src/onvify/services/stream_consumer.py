"""Per-camera stream consumption and inference orchestration.

Manages async tasks for cameras that need local frame consumption,
including AI-enabled cameras and MJPEG preview sources.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse
from uuid import UUID

import structlog

from onvify.models.camera import Camera, CameraStatus, StreamType

if TYPE_CHECKING:
    from onvify.api.websocket import ConnectionManager
    from onvify.inference.pipeline import InferencePipeline
    from onvify.inference.protocol import InferenceBackend
    from onvify.infrastructure.database import Database
    from onvify.services.camera_manager import CameraManager

logger = structlog.get_logger()


def _safe_url(url: str) -> str:
    """Redact credentials from a URL for safe use in logs and error messages."""
    parsed = urlparse(url)
    if parsed.username:
        redacted = parsed._replace(netloc=f"***@{parsed.hostname}" + (f":{parsed.port}" if parsed.port else ""))
        return urlunparse(redacted)
    return url


class StreamConsumer:
    """Manages frame-pulling tasks for AI-enabled cameras and MJPEG previews."""

    def __init__(
        self,
        camera_manager: CameraManager,
        backend: InferenceBackend,
        database: Database,
        ws_manager: ConnectionManager,
        motion_sensitivity: int = 50,
        confidence_threshold: float = 0.4,
        cooldown_seconds: float = 5.0,
        reconnect_base: float = 1.0,
        reconnect_max: float = 30.0,
        target_interval: float = 0.5,
    ) -> None:
        self._manager = camera_manager
        self._backend = backend
        self._db = database
        self._ws = ws_manager
        self._motion_sensitivity = motion_sensitivity
        self._confidence_threshold = confidence_threshold
        self._cooldown_seconds = cooldown_seconds
        self._reconnect_base = reconnect_base
        self._reconnect_max = reconnect_max
        self._target_interval = target_interval
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._frame_queues: dict[UUID, asyncio.Queue[bytes]] = {}

    @property
    def active_cameras(self) -> set[UUID]:
        return {cid for cid, task in self._tasks.items() if not task.done()}

    @property
    def active_ai_cameras(self) -> set[UUID]:
        active: set[UUID] = set()
        for camera_id in self.active_cameras:
            camera = self._manager.get_camera(camera_id)
            if camera and camera.ai_enabled:
                active.add(camera_id)
        return active

    def get_frame_queue(self, camera_id: UUID) -> asyncio.Queue[bytes] | None:
        return self._frame_queues.get(camera_id)

    def start_camera(self, camera: Camera) -> None:
        if camera.id in self._tasks and not self._tasks[camera.id].done():
            return
        if not self._should_consume(camera):
            return
        self._frame_queues[camera.id] = asyncio.Queue(maxsize=2)
        task = asyncio.create_task(
            self._consume_loop(camera),
            name=f"stream-{camera.id}",
        )
        camera_id = camera.id
        self._tasks[camera.id] = task

        def cleanup(_done: asyncio.Future[None]) -> None:
            self._on_task_done(camera_id, task)

        task.add_done_callback(cleanup)
        logger.info("stream_consumer_started", camera_id=str(camera.id), name=camera.name)

    def _on_task_done(self, camera_id: UUID, task: asyncio.Task[None]) -> None:
        if self._tasks.get(camera_id) is not task:
            return
        self._tasks.pop(camera_id, None)
        self._frame_queues.pop(camera_id, None)

    def stop_camera(self, camera_id: UUID) -> None:
        task = self._tasks.pop(camera_id, None)
        self._frame_queues.pop(camera_id, None)
        if task and not task.done():
            task.cancel()
            logger.info("stream_consumer_stopped", camera_id=str(camera_id))

    def start_all(self) -> None:
        for camera in self._manager.list_cameras():
            self.start_camera(camera)

    def _should_consume(self, camera: Camera) -> bool:
        return camera.ai_enabled or camera.stream_type == StreamType.MJPEG

    async def stop_all_async(self) -> None:
        """Cancel all tasks and wait for them to finish."""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._frame_queues.clear()

    async def _set_status(self, camera_id: UUID, status: CameraStatus) -> None:
        self._manager.set_status(camera_id, status)
        await self._ws.broadcast_event(
            "camera.status",
            {"camera_id": str(camera_id), "status": status.value},
        )

    async def _consume_loop(self, camera: Camera) -> None:
        from onvify.inference.pipeline import InferencePipeline

        pipeline: InferencePipeline | None = None
        if camera.ai_enabled:
            pipeline = InferencePipeline(
                backend=self._backend,
                motion_sensitivity=self._motion_sensitivity,
                confidence_threshold=self._confidence_threshold,
                cooldown_seconds=self._cooldown_seconds,
            )

        backoff = self._reconnect_base
        primary = camera.primary_stream
        while True:
            try:
                await self._set_status(camera.id, CameraStatus.CONNECTING)
                if primary is None:
                    await self._set_status(camera.id, CameraStatus.OFFLINE)
                    logger.warning("no_primary_stream", camera_id=str(camera.id))
                    return

                if primary.stream_type == StreamType.MJPEG:
                    await self._consume_mjpeg(camera, primary.url, pipeline)
                else:
                    await self._consume_rtsp(camera, primary.url, pipeline)

            except asyncio.CancelledError:
                await self._set_status(camera.id, CameraStatus.OFFLINE)
                return
            except Exception as exc:
                await self._set_status(camera.id, CameraStatus.ERROR)
                safe = _safe_url(primary.url) if primary else "unknown"
                logger.error(
                    "stream_consumer_error",
                    camera_id=str(camera.id),
                    backoff=backoff,
                    error=str(exc),
                    url=safe,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._reconnect_max)
                if pipeline:
                    pipeline.reset()
            else:
                backoff = self._reconnect_base

    async def _consume_mjpeg(self, camera: Camera, url: str, pipeline: InferencePipeline | None) -> None:
        from onvify.services.mjpeg import decode_jpeg_frame, pull_mjpeg_frames

        await self._set_status(camera.id, CameraStatus.ONLINE)
        queue = self._frame_queues.get(camera.id)

        async for jpeg_bytes in pull_mjpeg_frames(url):
            if queue and not queue.full():
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(jpeg_bytes)

            if pipeline:
                frame = decode_jpeg_frame(jpeg_bytes)
                event = await pipeline.process_frame(frame, camera.id)
                if event:
                    await self._db.save_detection_event(event)
                    await self._ws.broadcast_event(
                        "detection.event",
                        {"event": event.model_dump(mode="json")},
                    )

            await asyncio.sleep(self._target_interval)

    async def _consume_rtsp(self, camera: Camera, url: str, pipeline: InferencePipeline | None) -> None:
        import cv2

        cap = await asyncio.to_thread(cv2.VideoCapture, url)
        if not cap.isOpened():
            cap.release()
            msg = f"Failed to open RTSP stream: {_safe_url(url)}"
            raise ConnectionError(msg)

        await self._set_status(camera.id, CameraStatus.ONLINE)
        queue = self._frame_queues.get(camera.id)

        try:
            while True:
                ret, frame = await asyncio.to_thread(cap.read)
                if not ret:
                    msg = f"RTSP stream ended: {_safe_url(url)}"
                    raise ConnectionError(msg)

                if queue and not queue.full():
                    ret_jpg, jpeg_bytes = await asyncio.to_thread(
                        cv2.imencode, ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                    )
                    if ret_jpg:
                        with contextlib.suppress(asyncio.QueueFull):
                            queue.put_nowait(jpeg_bytes.tobytes())

                if pipeline:
                    event = await pipeline.process_frame(frame, camera.id)
                    if event:
                        await self._db.save_detection_event(event)
                        await self._ws.broadcast_event(
                            "detection.event",
                            {"event": event.model_dump(mode="json")},
                        )

                await asyncio.sleep(self._target_interval)
        finally:
            cap.release()
