"""ONVIF Device/Media/Events service.

Serves ONVIF SOAP responses for each virtual camera so that NVRs
(UniFi Protect, Blue Iris, Milestone, etc.) can discover and stream from them.
"""

from __future__ import annotations

import structlog

from onvify.models.camera import Camera
from onvify.models.onvif import ONVIFDeviceInfo

logger = structlog.get_logger()


class ONVIFDeviceService:
    """Handles ONVIF SOAP requests for a virtual camera."""

    def __init__(self, camera: Camera, host_ip: str, device_info: ONVIFDeviceInfo | None = None) -> None:
        self._camera = camera
        self._host_ip = host_ip
        self._device_info = device_info or ONVIFDeviceInfo()

    @property
    def camera(self) -> Camera:
        return self._camera

    def get_device_information(self) -> ONVIFDeviceInfo:
        return self._device_info

    def get_stream_uri(self, profile_token: str) -> str | None:
        """Return the RTSP URI for a given ONVIF profile token."""
        for profile in self._camera.profiles:
            if profile.token == profile_token:
                return profile.stream.url
        return None

    def get_profiles(self) -> list[dict[str, str | int]]:
        """Return simplified profile list for ONVIF GetProfiles response."""
        profiles: list[dict[str, str | int]] = []
        for p in self._camera.profiles:
            profiles.append(
                {
                    "token": p.token,
                    "name": p.name,
                    "encoding": p.encoding,
                    "width": p.resolution_width,
                    "height": p.resolution_height,
                }
            )
        return profiles
