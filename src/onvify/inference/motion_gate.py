"""Stage 1: OpenCV pixel-difference motion gate.

Cheaply detects whether a frame has changed enough to warrant expensive
Stage 2 inference. Runs locally in the main process regardless of which
inference backend is configured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

logger = structlog.get_logger()


class MotionGate:
    """Compares consecutive frames to detect motion above a sensitivity threshold."""

    def __init__(self, sensitivity: int = 50, frame_width: int = 320) -> None:
        self._sensitivity = max(1, min(100, sensitivity))
        self._frame_width = frame_width
        self._prev_gray: npt.NDArray[np.uint8] | None = None

    @property
    def sensitivity(self) -> int:
        return self._sensitivity

    @sensitivity.setter
    def sensitivity(self, value: int) -> None:
        self._sensitivity = max(1, min(100, value))

    def check(self, frame: npt.NDArray[np.uint8]) -> bool:
        """Return True if motion exceeds the sensitivity threshold.

        Args:
            frame: BGR image as numpy array.

        Returns:
            True if the frame should be forwarded to Stage 2 inference.
        """
        try:
            import cv2
        except ImportError:
            return True

        small = cv2.resize(frame, (self._frame_width, int(frame.shape[0] * self._frame_width / frame.shape[1])))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self._prev_gray is None:
            self._prev_gray = gray
            return True

        delta = cv2.absdiff(self._prev_gray, gray)
        self._prev_gray = gray

        thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
        motion_ratio = thresh.sum() / (thresh.size * 255)
        threshold = 1.0 - (self._sensitivity / 100.0)

        return bool(motion_ratio > threshold)

    def reset(self) -> None:
        """Clear the previous frame reference."""
        self._prev_gray = None
