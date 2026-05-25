"""Tests for ONVIF SOAP HTTP server."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime

import pytest

from onvify.models.camera import Camera, Profile, Stream
from onvify.services.onvif_server import ONVIFCameraServer, ONVIFServerManager, _extract_action, _password_digest


class TestExtractAction:
    def test_extracts_get_device_information(self) -> None:
        body = """
        <s:Body>
            <tds:GetDeviceInformation/>
        </s:Body>
        """
        assert _extract_action(body) == "GetDeviceInformation"

    def test_extracts_get_profiles(self) -> None:
        body = """
        <s:Body>
            <trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl"/>
        </s:Body>
        """
        assert _extract_action(body) == "GetProfiles"

    def test_extracts_get_stream_uri(self) -> None:
        body = """
        <s:Body>
            <trt:GetStreamUri>
                <trt:ProfileToken>main</trt:ProfileToken>
            </trt:GetStreamUri>
        </s:Body>
        """
        assert _extract_action(body) == "GetStreamUri"

    def test_returns_none_for_empty_body(self) -> None:
        assert _extract_action("") is None


@pytest.mark.asyncio
class TestONVIFCameraServer:
    async def test_responds_to_get_device_information(self) -> None:
        camera = Camera(name="Test Cam", source_streams=[Stream(url="rtsp://localhost/test")])
        server = ONVIFCameraServer(camera, "127.0.0.1", 0)
        await server.start()
        actual_port = server._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        try:
            soap_request = (
                '<?xml version="1.0"?>'
                '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
                "<s:Body><tds:GetDeviceInformation/></s:Body>"
                "</s:Envelope>"
            )
            response = await _send_soap_request("127.0.0.1", actual_port, soap_request)
            assert b"GetDeviceInformationResponse" in response
            assert b"ONVIFy" in response
        finally:
            await server.stop()

    async def test_responds_to_get_capabilities(self) -> None:
        camera = Camera(name="Cap Cam", source_streams=[Stream(url="rtsp://localhost/test")])
        server = ONVIFCameraServer(camera, "127.0.0.1", 0)
        await server.start()
        actual_port = server._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        try:
            soap_request = (
                '<?xml version="1.0"?>'
                '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
                "<s:Body><tds:GetCapabilities/></s:Body>"
                "</s:Envelope>"
            )
            response = await _send_soap_request("127.0.0.1", actual_port, soap_request)
            assert b"GetCapabilitiesResponse" in response
            assert b"device_service" in response
        finally:
            await server.stop()

    async def test_responds_to_get_stream_uri(self) -> None:
        stream = Stream(url="rtsp://192.168.1.10:554/stream1")
        profile = Profile(token="main", name="Main", stream=stream)
        camera = Camera(name="Stream Cam", source_streams=[stream], profiles=[profile])
        server = ONVIFCameraServer(camera, "127.0.0.1", 0)
        await server.start()
        actual_port = server._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        try:
            soap_request = (
                '<?xml version="1.0"?>'
                '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
                "<s:Body><trt:GetStreamUri>"
                "<trt:ProfileToken>main</trt:ProfileToken>"
                "</trt:GetStreamUri></s:Body>"
                "</s:Envelope>"
            )
            response = await _send_soap_request("127.0.0.1", actual_port, soap_request)
            assert b"rtsp://192.168.1.10:554/stream1" in response
        finally:
            await server.stop()

    async def test_returns_fault_for_unknown_action(self) -> None:
        camera = Camera(name="Fault Cam", source_streams=[Stream(url="rtsp://localhost/test")])
        server = ONVIFCameraServer(camera, "127.0.0.1", 0)
        await server.start()
        actual_port = server._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        try:
            soap_request = (
                '<?xml version="1.0"?>'
                '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
                "<s:Body><tds:FakeAction/></s:Body>"
                "</s:Envelope>"
            )
            response = await _send_soap_request("127.0.0.1", actual_port, soap_request)
            assert b"Fault" in response
            assert b"Action not supported" in response
        finally:
            await server.stop()

    async def test_requires_username_token_when_camera_has_onvif_credentials(self) -> None:
        camera = Camera(
            name="Secure Cam",
            source_streams=[Stream(url="rtsp://localhost/test")],
            onvif_username="operator",
            onvif_password="secret",
        )
        server = ONVIFCameraServer(camera, "127.0.0.1", 0)
        await server.start()
        actual_port = server._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        try:
            response = await _send_soap_request("127.0.0.1", actual_port, _soap_request(""))
            assert b"HTTP/1.1 401 Unauthorized" in response
            assert b"Authentication failed" in response
        finally:
            await server.stop()

    async def test_accepts_password_text_username_token(self) -> None:
        camera = Camera(
            name="Secure Cam",
            source_streams=[Stream(url="rtsp://localhost/test")],
            onvif_username="operator",
            onvif_password="secret",
        )
        server = ONVIFCameraServer(camera, "127.0.0.1", 0)
        await server.start()
        actual_port = server._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        try:
            response = await _send_soap_request(
                "127.0.0.1",
                actual_port,
                _soap_request(_password_text_token("operator", "secret")),
            )
            assert b"HTTP/1.1 200 OK" in response
            assert b"GetDeviceInformationResponse" in response
        finally:
            await server.stop()

    async def test_accepts_password_digest_username_token(self) -> None:
        camera = Camera(
            name="Secure Cam",
            source_streams=[Stream(url="rtsp://localhost/test")],
            onvif_username="operator",
            onvif_password="secret",
        )
        server = ONVIFCameraServer(camera, "127.0.0.1", 0)
        await server.start()
        actual_port = server._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        try:
            response = await _send_soap_request(
                "127.0.0.1",
                actual_port,
                _soap_request(_password_digest_token("operator", "secret")),
            )
            assert b"HTTP/1.1 200 OK" in response
            assert b"GetDeviceInformationResponse" in response
        finally:
            await server.stop()

    async def test_rejects_replayed_password_digest_username_token(self) -> None:
        camera = Camera(
            name="Secure Cam",
            source_streams=[Stream(url="rtsp://localhost/test")],
            onvif_username="operator",
            onvif_password="secret",
        )
        server = ONVIFCameraServer(camera, "127.0.0.1", 0)
        await server.start()
        actual_port = server._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        soap_request = _soap_request(_password_digest_token("operator", "secret"))

        try:
            first_response = await _send_soap_request("127.0.0.1", actual_port, soap_request)
            second_response = await _send_soap_request("127.0.0.1", actual_port, soap_request)
            assert b"HTTP/1.1 200 OK" in first_response
            assert b"HTTP/1.1 401 Unauthorized" in second_response
        finally:
            await server.stop()

    async def test_rejects_invalid_username_token(self) -> None:
        camera = Camera(
            name="Secure Cam",
            source_streams=[Stream(url="rtsp://localhost/test")],
            onvif_username="operator",
            onvif_password="secret",
        )
        server = ONVIFCameraServer(camera, "127.0.0.1", 0)
        await server.start()
        actual_port = server._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        try:
            response = await _send_soap_request(
                "127.0.0.1",
                actual_port,
                _soap_request(_password_text_token("operator", "wrong")),
            )
            assert b"HTTP/1.1 401 Unauthorized" in response
        finally:
            await server.stop()


@pytest.mark.asyncio
class TestONVIFServerManager:
    async def test_add_and_remove_camera(self) -> None:
        camera = Camera(name="Managed", source_streams=[Stream(url="rtsp://x")])
        mgr = ONVIFServerManager("127.0.0.1", 18001)
        port = await mgr.add_camera(camera)
        assert port == 18001
        await mgr.remove_camera(str(camera.id))

    async def test_stop_all_cleans_up(self) -> None:
        cam1 = Camera(name="Cam1", source_streams=[Stream(url="rtsp://x")])
        cam2 = Camera(name="Cam2", source_streams=[Stream(url="rtsp://y")])
        mgr = ONVIFServerManager("127.0.0.1", 18010)
        await mgr.add_camera(cam1)
        await mgr.add_camera(cam2)
        await mgr.stop_all()
        assert len(mgr._servers) == 0


async def _send_soap_request(host: str, port: int, body: str) -> bytes:
    reader, writer = await asyncio.open_connection(host, port)
    encoded = body.encode("utf-8")
    request = (
        f"POST /onvif/device_service HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Content-Type: application/soap+xml; charset=utf-8\r\n"
        f"Content-Length: {len(encoded)}\r\n"
        f"\r\n"
    ).encode() + encoded
    writer.write(request)
    await writer.drain()
    response = await asyncio.wait_for(reader.read(65536), timeout=5.0)
    writer.close()
    await writer.wait_closed()
    return response


def _soap_request(security_header: str) -> str:
    return (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
        'xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-wssecurity-secext-1.0.xsd" '
        'xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        f"{security_header}"
        "<s:Body><tds:GetDeviceInformation/></s:Body>"
        "</s:Envelope>"
    )


def _password_text_token(username: str, password: str) -> str:
    return (
        "<s:Header><wsse:Security><wsse:UsernameToken>"
        f"<wsse:Username>{username}</wsse:Username>"
        '<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/'
        f'oasis-200401-wss-username-token-profile-1.0#PasswordText">{password}</wsse:Password>'
        "</wsse:UsernameToken></wsse:Security></s:Header>"
    )


def _password_digest_token(username: str, password: str) -> str:
    nonce = base64.b64encode(b"fixed-nonce").decode("ascii")
    created = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    digest = _password_digest(nonce, created, password)
    return (
        "<s:Header><wsse:Security><wsse:UsernameToken>"
        f"<wsse:Username>{username}</wsse:Username>"
        '<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/'
        f'oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>'
        f"<wsse:Nonce>{nonce}</wsse:Nonce>"
        f"<wsu:Created>{created}</wsu:Created>"
        "</wsse:UsernameToken></wsse:Security></s:Header>"
    )
