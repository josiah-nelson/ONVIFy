"""Camera and stream domain models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class StreamType(StrEnum):
    RTSP = "rtsp"
    MJPEG = "mjpeg"


class CameraStatus(StrEnum):
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ONLINE = "online"
    ERROR = "error"


class Stream(BaseModel):
    """A single video stream from a camera (main or sub-stream)."""

    url: str
    stream_type: StreamType = StreamType.RTSP
    label: str = "main"
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None


class Profile(BaseModel):
    """ONVIF media profile exposed by the virtual camera."""

    token: str
    name: str
    stream: Stream
    encoding: str = "H264"
    resolution_width: int = 1920
    resolution_height: int = 1080


class Camera(BaseModel):
    """A virtual ONVIF camera backed by a real source stream."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    source_streams: list[Stream]
    profiles: list[Profile] = Field(default_factory=list)
    onvif_port: int | None = None
    status: CameraStatus = CameraStatus.OFFLINE
    ai_enabled: bool = False
    ai_model: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # ONVIF credentials for the virtual device
    onvif_username: str | None = None
    onvif_password: str | None = None

    @property
    def primary_stream(self) -> Stream | None:
        return self.source_streams[0] if self.source_streams else None

    @property
    def stream_type(self) -> StreamType | Literal["unknown"]:
        primary = self.primary_stream
        return primary.stream_type if primary else "unknown"
