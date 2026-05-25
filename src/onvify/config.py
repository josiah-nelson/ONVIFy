"""Application configuration via Pydantic Settings.

All configuration is loaded from environment variables and/or a .env file.
Defaults are production-safe — the server starts with zero configuration.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BITRATE_PATTERN = re.compile(r"^\d+[kKmM]?$")
_MEDIAMTX_VERSION_PATTERN = re.compile(r"^v?\d+\.\d+\.\d+$")
_X264_PRESETS = frozenset(
    {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
)

Port = Annotated[int, Field(ge=1, le=65535)]


class ServerSettings(BaseSettings):
    """Network ports and concurrency."""

    model_config = SettingsConfigDict(env_prefix="")

    web_ui_port: Port = 5552
    mediamtx_port: Port = 8554
    mediamtx_api_host: str = "127.0.0.1"
    mediamtx_api_port: Port = 9997
    onvif_base_port: Port = 8001
    wsgi_max_workers: int = Field(20, ge=1)


class InferenceSettings(BaseSettings):
    """AI detection pipeline configuration."""

    model_config = SettingsConfigDict(env_prefix="AI_")

    default_model: str = "yolov8n.pt"
    inference_frame_width: int = Field(640, ge=1)
    cooldown_seconds: float = Field(5.0, ge=0.0)
    target_interval: float = Field(0.50, ge=0.01)
    confidence_threshold: int = Field(40, ge=1, le=100)
    motion_sensitivity: int = Field(50, ge=1, le=100)
    torch_threads: int | None = None
    backend: Literal["local", "openai_compatible", "dedicated"] = "local"
    backend_url: str | None = None


class StreamingSettings(BaseSettings):
    """RTSP/MJPEG streaming and encoding configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    mediamtx_version: str = "v1.18.2"
    mediamtx_bin: Path | None = None
    mediamtx_auto_download: bool = True
    grabber_reconnect_base: float = Field(1.0, ge=0.5)
    grabber_reconnect_max: float = Field(30.0, ge=1.0)
    gf_video_bitrate: str = "2500k"
    gf_video_bufsize: str = "5000k"
    gf_encoder_preset: str = "ultrafast"

    @field_validator("mediamtx_version")
    @classmethod
    def validate_mediamtx_version(cls, v: str) -> str:
        if not _MEDIAMTX_VERSION_PATTERN.match(v):
            msg = f"Invalid MediaMTX version: {v!r}. Expected a semantic version like 'v1.18.2'."
            raise ValueError(msg)
        return v if v.startswith("v") else f"v{v}"

    @field_validator("gf_video_bitrate", "gf_video_bufsize")
    @classmethod
    def validate_bitrate(cls, v: str) -> str:
        if not _BITRATE_PATTERN.match(v):
            msg = f"Invalid bitrate format: {v!r}. Expected pattern like '2500k' or '5000k'."
            raise ValueError(msg)
        return v

    @field_validator("gf_encoder_preset")
    @classmethod
    def validate_preset(cls, v: str) -> str:
        if v not in _X264_PRESETS:
            msg = f"Invalid x264 preset: {v!r}. Must be one of {sorted(_X264_PRESETS)}."
            raise ValueError(msg)
        return v


class Settings(BaseSettings):
    """Root configuration aggregating all subsections."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    root_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)
    config_file: Path | None = None
    debug: bool = False
    log_format: Literal["json", "console"] = "console"

    server: ServerSettings = Field(default_factory=ServerSettings)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    streaming: StreamingSettings = Field(default_factory=StreamingSettings)
