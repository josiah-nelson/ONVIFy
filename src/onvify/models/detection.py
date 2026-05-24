"""AI detection event models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ObjectClass(StrEnum):
    PERSON = "person"
    VEHICLE = "vehicle"
    ANIMAL = "animal"
    UNKNOWN = "unknown"


class BoundingBox(BaseModel):
    """Normalized bounding box coordinates (0.0 to 1.0)."""

    x_min: float = Field(ge=0.0, le=1.0)
    y_min: float = Field(ge=0.0, le=1.0)
    x_max: float = Field(ge=0.0, le=1.0)
    y_max: float = Field(ge=0.0, le=1.0)


class Detection(BaseModel):
    """A single detected object within a frame."""

    object_class: ObjectClass
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox
    label: str | None = None


class DetectionEvent(BaseModel):
    """An inference result containing one or more detections for a camera frame."""

    id: UUID = Field(default_factory=uuid4)
    camera_id: UUID
    timestamp: datetime = Field(default_factory=datetime.now)
    detections: list[Detection]
    inference_time_ms: float
    backend: str = "local"
    frame_width: int | None = None
    frame_height: int | None = None
