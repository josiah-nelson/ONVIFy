"""Two-stage inference pipeline orchestrator.

Stage 1 (motion gate) always runs locally and is cheap.
Stage 2 (detection) routes to the configured inference backend only when
the motion gate triggers.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from onvify.inference.motion_gate import MotionGate
from onvify.inference.protocol import InferenceBackend
from onvify.models.detection import DetectionEvent

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

logger = structlog.get_logger()


class InferencePipeline:
    """Orchestrates motion-gated inference with cooldown."""

    def __init__(
        self,
        backend: InferenceBackend,
        motion_sensitivity: int = 50,
        confidence_threshold: float = 0.4,
        cooldown_seconds: float = 5.0,
        motion_frame_width: int = 320,
    ) -> None:
        self._backend = backend
        self._gate = MotionGate(sensitivity=motion_sensitivity, frame_width=motion_frame_width)
        self._confidence = confidence_threshold
        self._cooldown = cooldown_seconds
        self._last_detection_time: float = 0.0

    @property
    def backend(self) -> InferenceBackend:
        return self._backend

    async def process_frame(
        self,
        frame: npt.NDArray[np.uint8],
        camera_id: UUID,
    ) -> DetectionEvent | None:
        """Run the two-stage pipeline on a single frame.

        Returns a DetectionEvent if objects were detected, None otherwise.
        """
        now = time.monotonic()
        if now - self._last_detection_time < self._cooldown:
            return None

        if not self._gate.check(frame):
            return None

        start = time.monotonic()
        detections = await self._backend.detect(frame, self._confidence)
        elapsed_ms = (time.monotonic() - start) * 1000

        if not detections:
            return None

        self._last_detection_time = now
        h, w = frame.shape[:2]

        logger.info(
            "detections_found",
            camera_id=str(camera_id),
            count=len(detections),
            inference_ms=round(elapsed_ms, 1),
        )

        return DetectionEvent(
            camera_id=camera_id,
            detections=detections,
            inference_time_ms=elapsed_ms,
            backend=type(self._backend).__name__,
            frame_width=w,
            frame_height=h,
        )

    def update_sensitivity(self, sensitivity: int) -> None:
        self._gate.sensitivity = sensitivity

    def reset(self) -> None:
        """Reset motion gate state (e.g., after camera reconnect)."""
        self._gate.reset()
        self._last_detection_time = 0.0
