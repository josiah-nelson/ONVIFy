"""Per-camera ONVIF SOAP HTTP server.

Runs a lightweight asyncio TCP server for each virtual camera, exposing
ONVIF device and media service endpoints that NVRs can query.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import re
from typing import TYPE_CHECKING
from xml.etree import ElementTree

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
    r"<\w+:?Body[^>]*>.*?<(?:\w+:)?(\w+)[\s/>]",
    re.DOTALL,
)
_MAX_REQUEST_BODY = 1 * 1024 * 1024
_PROFILE_TOKEN_PATTERN = re.compile(
    r"<\w+:?ProfileToken[^>]*>(.*?)</\w+:?ProfileToken>",
)
_PASSWORD_DIGEST_TYPE = "PasswordDigest"
_PASSWORD_TEXT_TYPE = "PasswordText"


def _extract_action(body: str) -> str | None:
    match = _ACTION_PATTERN.search(body)
    return match.group(1) if match else None


def _extract_profile_token(body: str) -> str | None:
    match = _PROFILE_TOKEN_PATTERN.search(body)
    return match.group(1).strip() if match else None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ElementTree.Element, name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) == name:
            return child.text or ""
    return None


def _username_token(body: str) -> ElementTree.Element | None:
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return None
    for element in root.iter():
        if _local_name(element.tag) == "UsernameToken":
            return element
    return None


def _password_type(token: ElementTree.Element) -> str:
    for child in token:
        if _local_name(child.tag) == "Password":
            password_type = child.attrib.get("Type", "")
            if password_type.endswith(_PASSWORD_DIGEST_TYPE):
                return _PASSWORD_DIGEST_TYPE
            return _PASSWORD_TEXT_TYPE
    return _PASSWORD_TEXT_TYPE


def _decode_nonce(nonce: str) -> bytes:
    try:
        return base64.b64decode(nonce, validate=True)
    except ValueError:
        return nonce.encode("utf-8")


def _password_digest(nonce: str, created: str, password: str) -> str:
    # WS-Security UsernameToken defines PasswordDigest as SHA-1 over nonce, Created, and password.
    digest = hashlib.sha1()
    digest.update(_decode_nonce(nonce))
    digest.update(created.encode("utf-8"))
    digest.update(password.encode("utf-8"))
    return base64.b64encode(digest.digest()).decode("ascii")


def _valid_username_token(body: str, username: str, password: str) -> bool:
    token = _username_token(body)
    if token is None:
        return False

    actual_username = _child_text(token, "Username")
    actual_password = _child_text(token, "Password")
    if actual_password is None or not hmac.compare_digest(actual_username or "", username):
        return False

    if _password_type(token) == _PASSWORD_TEXT_TYPE:
        return hmac.compare_digest(actual_password, password)

    nonce = _child_text(token, "Nonce")
    created = _child_text(token, "Created")
    if not nonce or not created:
        return False
    return hmac.compare_digest(actual_password, _password_digest(nonce, created, password))


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
            if content_length > _MAX_REQUEST_BODY:
                fault = soap_fault("Sender", "Request body too large")
                self._write_response(writer, 400, fault)
                return
            if content_length > 0:
                raw_body = await asyncio.wait_for(reader.readexactly(content_length), timeout=10.0)
                body = raw_body.decode("utf-8", errors="replace")

            if not self._is_authenticated(body):
                fault = soap_fault("Sender", "Authentication failed")
                self._write_response(writer, 401, fault)
                return

            response_xml = self._dispatch(body)
            self._write_response(writer, 200, response_xml)
        except (TimeoutError, asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception:
            logger.exception("onvif_unhandled_error", camera_id=str(self._camera.id))
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

    def _is_authenticated(self, body: str) -> bool:
        username = self._camera.onvif_username
        password = self._camera.onvif_password
        if username is None and password is None:
            return True
        if username is None:
            return False
        return _valid_username_token(body, username, password or "")

    def _resolve_stream_uri(self, profile_token: str | None) -> str:
        if profile_token:
            for profile in self._camera.profiles:
                if profile.token == profile_token:
                    return profile.stream.url
        primary = self._camera.primary_stream
        return primary.url if primary else ""

    @staticmethod
    def _write_response(writer: asyncio.StreamWriter, status: int, body: str) -> None:
        reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 500: "Internal Server Error"}.get(
            status, "Internal Server Error"
        )
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
        await asyncio.gather(*(server.stop() for server in self._servers.values()))
        self._servers.clear()
