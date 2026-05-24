"""Inference backend protocol definition.

All inference backends (local YOLO, OpenAI-compatible, dedicated vision API)
must implement this protocol. The pipeline orchestrator dispatches to whichever
backend is configured without knowing the implementation details.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

from onvify.models.detection import Detection


class BackendHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class BackendStatus(BaseModel):
    """Health status returned by an inference backend."""

    health: BackendHealth
    model_name: str | None = None
    device: str | None = None
    message: str | None = None


@runtime_checkable
class InferenceBackend(Protocol):
    """Protocol that all inference backends must implement."""

    async def detect(
        self,
        frame: npt.NDArray[np.uint8],
        confidence_threshold: float = 0.4,
    ) -> list[Detection]:
        """Run object detection on a single frame.

        Args:
            frame: BGR image as numpy array (H, W, 3).
            confidence_threshold: Minimum confidence to include a detection (0.0-1.0).

        Returns:
            List of detections found in the frame.
        """
        ...

    async def health_check(self) -> BackendStatus:
        """Return the current health and metadata of this backend."""
        ...

    def supported_models(self) -> list[str]:
        """Return model identifiers this backend can serve."""
        ...
