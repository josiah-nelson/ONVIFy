"""Per-camera stream consumption and inference orchestration.

Manages an async task per AI-enabled camera that pulls frames, runs
the inference pipeline, broadcasts detection events via WebSocket,
and persists them to the database.
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
    """Manages frame-pulling tasks for all AI-enabled cameras."""

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

    def get_frame_queue(self, camera_id: UUID) -> asyncio.Queue[bytes] | None:
        return self._frame_queues.get(camera_id)

    def start_camera(self, camera: Camera) -> None:
        if camera.id in self._tasks and not self._tasks[camera.id].done():
            return
        if not camera.ai_enabled:
            return
        self._frame_queues[camera.id] = asyncio.Queue(maxsize=2)
        task = asyncio.create_task(
            self._consume_loop(camera),
            name=f"stream-{camera.id}",
        )
        camera_id = camera.id
        task.add_done_callback(lambda _t: self._on_task_done(camera_id))
        self._tasks[camera.id] = task
        logger.info("stream_consumer_started", camera_id=str(camera.id), name=camera.name)

    def _on_task_done(self, camera_id: UUID) -> None:
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

    async def stop_all_async(self) -> None:
        """Cancel all tasks and wait for them to finish."""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._frame_queues.clear()

    async def _consume_loop(self, camera: Camera) -> None:
        from onvify.inference.pipeline import InferencePipeline

        pipeline = InferencePipeline(
            backend=self._backend,
            motion_sensitivity=self._motion_sensitivity,
            confidence_threshold=self._confidence_threshold,
            cooldown_seconds=self._cooldown_seconds,
        )

        backoff = self._reconnect_base
        while True:
            try:
                self._manager.set_status(camera.id, CameraStatus.CONNECTING)
                primary = camera.primary_stream
                if primary is None:
                    logger.warning("no_primary_stream", camera_id=str(camera.id))
                    return

                if primary.stream_type == StreamType.MJPEG:
                    await self._consume_mjpeg(camera, primary.url, pipeline)
                else:
                    await self._consume_rtsp(camera, primary.url, pipeline)

            except asyncio.CancelledError:
                self._manager.set_status(camera.id, CameraStatus.OFFLINE)
                return
            except Exception:
                self._manager.set_status(camera.id, CameraStatus.ERROR)
                logger.exception("stream_consumer_error", camera_id=str(camera.id), backoff=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._reconnect_max)
                pipeline.reset()
            else:
                backoff = self._reconnect_base

    async def _consume_mjpeg(self, camera: Camera, url: str, pipeline: object) -> None:
        from onvify.inference.pipeline import InferencePipeline
        from onvify.services.mjpeg import decode_jpeg_frame, pull_mjpeg_frames

        assert isinstance(pipeline, InferencePipeline)
        self._manager.set_status(camera.id, CameraStatus.ONLINE)
        queue = self._frame_queues.get(camera.id)

        async for jpeg_bytes in pull_mjpeg_frames(url):
            frame = decode_jpeg_frame(jpeg_bytes)

            if queue and not queue.full():
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(jpeg_bytes)

            event = await pipeline.process_frame(frame, camera.id)
            if event:
                await self._db.save_detection_event(event)
                await self._ws.broadcast(event.model_dump(mode="json"))

            await asyncio.sleep(self._target_interval)

    async def _consume_rtsp(self, camera: Camera, url: str, pipeline: object) -> None:
        import cv2

        from onvify.inference.pipeline import InferencePipeline

        assert isinstance(pipeline, InferencePipeline)
        cap = await asyncio.to_thread(cv2.VideoCapture, url)
        if not cap.isOpened():
            msg = f"Failed to open RTSP stream: {_safe_url(url)}"
            raise ConnectionError(msg)

        self._manager.set_status(camera.id, CameraStatus.ONLINE)
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

                event = await pipeline.process_frame(frame, camera.id)
                if event:
                    await self._db.save_detection_event(event)
                    await self._ws.broadcast(event.model_dump(mode="json"))

                await asyncio.sleep(self._target_interval)
        finally:
            cap.release()
