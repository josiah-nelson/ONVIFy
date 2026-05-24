"""MediaMTX process and RTSP stream management.

Manages the MediaMTX subprocess lifecycle and generates its YAML configuration
based on the current set of virtual cameras.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import structlog
import yaml

from onvify.config import Settings
from onvify.models.camera import Camera

logger = structlog.get_logger()


def _build_mediamtx_config(cameras: list[Camera], settings: Settings) -> dict[str, Any]:
    """Generate a MediaMTX YAML config dict for the current camera set."""
    paths: dict[str, dict[str, str]] = {}
    for camera in cameras:
        stream = camera.primary_stream
        if stream is None:
            continue
        path_name = camera.name.lower().replace(" ", "_")
        paths[path_name] = {
            "source": stream.url,
            "sourceProtocol": "tcp",
        }

    return {
        "rtspAddress": f":{settings.server.mediamtx_port}",
        "api": True,
        "apiAddress": f":{settings.server.mediamtx_api_port}",
        "paths": paths,
    }


class MediaMTXManager:
    """Manages the MediaMTX RTSP server subprocess."""

    def __init__(self, settings: Settings, mediamtx_bin: Path | None = None) -> None:
        self._settings = settings
        self._bin = mediamtx_bin
        self._process: subprocess.Popen[bytes] | None = None
        self._config_path = settings.root_dir / "mediamtx.yml"

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def write_config(self, cameras: list[Camera]) -> Path:
        config = _build_mediamtx_config(cameras, self._settings)
        self._config_path.write_text(yaml.dump(config, default_flow_style=False))
        logger.info("mediamtx_config_written", path=str(self._config_path), camera_count=len(cameras))
        return self._config_path

    def start(self) -> None:
        if self._bin is None:
            logger.warning("mediamtx_binary_not_configured")
            return
        if self.is_running:
            logger.warning("mediamtx_already_running")
            return

        self._process = subprocess.Popen(
            [str(self._bin), str(self._config_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.info("mediamtx_started", pid=self._process.pid)

    def stop(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
        logger.info("mediamtx_stopped")
        self._process = None

    def reload_config(self, cameras: list[Camera]) -> None:
        self.write_config(cameras)
        if self.is_running:
            self.stop()
            self.start()
