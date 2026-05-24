"""Per-camera ONVIF SOAP HTTP server.

Runs a lightweight asyncio TCP server for each virtual camera, exposing
ONVIF device and media service endpoints that NVRs can query.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import structlog

from onvify.models.onvif import ONVIFDeviceInfo
from onvify.onvif_xml import (
    get_capabilities_response,
    get_device_information_response,
    get_profiles_response,
    get_scopes_response,
    get_stream_uri_response,
    soap_fault,
)

if TYPE_CHECKING:
    from onvify.models.camera import Camera

logger = structlog.get_logger()

_ACTION_PATTERN = re.compile(
    r"<\w+:?Body[^>]*>.*?<\w+:?(\w+?)[\s/>]",
    re.DOTALL,
)
_PROFILE_TOKEN_PATTERN = re.compile(
    r"<\w+:?ProfileToken[^>]*>(.*?)</\w+:?ProfileToken>",
)


def _extract_action(body: str) -> str | None:
    match = _ACTION_PATTERN.search(body)
    return match.group(1) if match else None


def _extract_profile_token(body: str) -> str | None:
    match = _PROFILE_TOKEN_PATTERN.search(body)
    return match.group(1).strip() if match else None


class ONVIFCameraServer:
    """ONVIF SOAP endpoint for a single virtual camera."""

    def __init__(self, camera: Camera, host: str, port: int) -> None:
        self._camera = camera
        self._host = host
        self._port = port
        self._device_info = ONVIFDeviceInfo(serial_number=str(camera.id))
        self._server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        return self._port

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_connection, self._host, self._port)
        logger.info(
            "onvif_camera_server_started",
            camera_id=str(self._camera.id),
            name=self._camera.name,
            port=self._port,
        )

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("onvif_camera_server_stopped", camera_id=str(self._camera.id))

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not request_line:
                return

            headers: dict[str, str] = {}
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=10.0)
                if line in (b"\r\n", b"\n", b""):
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if ":" in decoded:
                    key, value = decoded.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            content_length = int(headers.get("content-length", "0"))
            body = ""
            if content_length > 0:
                raw_body = await asyncio.wait_for(reader.readexactly(content_length), timeout=10.0)
                body = raw_body.decode("utf-8", errors="replace")

            response_xml = self._dispatch(body)
            self._write_response(writer, 200, response_xml)
        except (TimeoutError, asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception:
            fault = soap_fault("Receiver", "Internal server error")
            self._write_response(writer, 500, fault)
        finally:
            writer.close()
            async with asyncio.timeout(5):
                await writer.wait_closed()

    def _dispatch(self, body: str) -> str:
        action = _extract_action(body)
        if action == "GetDeviceInformation":
            return get_device_information_response(self._device_info)
        if action == "GetProfiles":
            return get_profiles_response(self._camera.profiles)
        if action == "GetStreamUri":
            token = _extract_profile_token(body)
            uri = self._resolve_stream_uri(token)
            return get_stream_uri_response(uri)
        if action == "GetCapabilities":
            return get_capabilities_response(self._host, self._port)
        if action == "GetScopes":
            return get_scopes_response(self._camera)
        return soap_fault("Sender", f"Action not supported: {action}")

    def _resolve_stream_uri(self, profile_token: str | None) -> str:
        if profile_token:
            for profile in self._camera.profiles:
                if profile.token == profile_token:
                    return profile.stream.url
        primary = self._camera.primary_stream
        return primary.url if primary else ""

    @staticmethod
    def _write_response(writer: asyncio.StreamWriter, status: int, body: str) -> None:
        reason = "OK" if status == 200 else "Internal Server Error"
        encoded = body.encode("utf-8")
        header = (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: application/soap+xml; charset=utf-8\r\n"
            f"Content-Length: {len(encoded)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        writer.write(header.encode("utf-8") + encoded)


class ONVIFServerManager:
    """Manages ONVIF HTTP servers for all cameras."""

    def __init__(self, host: str, base_port: int) -> None:
        self._host = host
        self._base_port = base_port
        self._servers: dict[str, ONVIFCameraServer] = {}
        self._next_port = base_port

    async def add_camera(self, camera: Camera) -> int:
        port = camera.onvif_port or self._next_port
        server = ONVIFCameraServer(camera, self._host, port)
        await server.start()
        self._servers[str(camera.id)] = server
        self._next_port = max(self._next_port, port + 1)
        return port

    async def remove_camera(self, camera_id: str) -> None:
        server = self._servers.pop(camera_id, None)
        if server:
            await server.stop()

    async def stop_all(self) -> None:
        for server in self._servers.values():
            await server.stop()
        self._servers.clear()
