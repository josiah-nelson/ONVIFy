"""WS-Discovery responder for ONVIF device discovery.

Listens on the WS-Discovery multicast address (239.255.255.250:3702) and
responds with probe matches for each virtual camera, allowing NVRs to
automatically discover ONVIFy cameras on the network.
"""

from __future__ import annotations

import asyncio
import re
import socket
import struct
import uuid
from typing import Any

import structlog

from onvify.models.camera import Camera

logger = structlog.get_logger()

WS_DISCOVERY_MULTICAST = ("239.255.255.250", 3702)

_MESSAGE_ID_PATTERN = re.compile(r"<\w+:?MessageID[^>]*>(.*?)</\w+:?MessageID>", re.DOTALL)
_TYPES_PATTERN = re.compile(r"<\w+:?Types[^>]*>(.*?)</\w+:?Types>", re.DOTALL)
_ACTION_PROBE = "http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe"


def _extract_message_id(xml: str) -> str | None:
    match = _MESSAGE_ID_PATTERN.search(xml)
    return match.group(1).strip() if match else None


_PROBE_ELEMENT_PATTERN = re.compile(r"<\w+:Probe[\s>/>]")


def _is_probe(xml: str) -> bool:
    return _ACTION_PROBE in xml or bool(_PROBE_ELEMENT_PATTERN.search(xml))


def _matches_probe_types(xml: str) -> bool:
    match = _TYPES_PATTERN.search(xml)
    if not match:
        return True
    types_text = match.group(1).strip()
    if not types_text:
        return True
    return "NetworkVideoTransmitter" in types_text


def _build_probe_match(camera: Camera, host_ip: str, message_id: str) -> str:
    """Build a WS-Discovery ProbeMatch XML response."""
    xaddrs = f"http://{host_ip}:{camera.onvif_port}/onvif/device_service"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <s:Header>
    <a:MessageID>urn:uuid:{uuid.uuid4()}</a:MessageID>
    <a:RelatesTo>{message_id}</a:RelatesTo>
    <a:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:To>
    <a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</a:Action>
  </s:Header>
  <s:Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <a:EndpointReference>
          <a:Address>urn:uuid:{camera.id}</a:Address>
        </a:EndpointReference>
        <d:Types>dn:NetworkVideoTransmitter</d:Types>
        <d:Scopes>onvif://www.onvif.org/name/{camera.name}</d:Scopes>
        <d:XAddrs>{xaddrs}</d:XAddrs>
        <d:MetadataVersion>1</d:MetadataVersion>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </s:Body>
</s:Envelope>"""


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """UDP protocol handler for WS-Discovery multicast messages."""

    def __init__(self, responder: WSDiscoveryResponder) -> None:
        self._responder = responder
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int] | tuple[Any, ...]) -> None:
        try:
            xml = data.decode("utf-8", errors="replace")
        except Exception:
            return

        if not _is_probe(xml):
            return

        if not _matches_probe_types(xml):
            return

        message_id = _extract_message_id(xml) or f"urn:uuid:{uuid.uuid4()}"
        self._responder.handle_probe(message_id, addr)

    def error_received(self, exc: Exception) -> None:
        logger.warning("ws_discovery_udp_error", error=str(exc))

    def connection_lost(self, exc: Exception | None) -> None:
        pass


class WSDiscoveryResponder:
    """Responds to WS-Discovery Probe requests on the network."""

    def __init__(self, host_ip: str) -> None:
        self._host_ip = host_ip
        self._cameras: list[Camera] = []
        self._running = False
        self._transport: asyncio.DatagramTransport | None = None

    def set_cameras(self, cameras: list[Camera]) -> None:
        self._cameras = [c for c in cameras if c.onvif_port is not None]

    async def start(self) -> None:
        loop = asyncio.get_running_loop()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("", WS_DISCOVERY_MULTICAST[1]))

        mreq = struct.pack(
            "4s4s",
            socket.inet_aton(WS_DISCOVERY_MULTICAST[0]),
            socket.inet_aton(self._host_ip),
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)

        transport, _ = await loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(self),
            sock=sock,
        )
        self._transport = transport
        self._running = True
        logger.info("ws_discovery_started", host=self._host_ip, port=WS_DISCOVERY_MULTICAST[1])

    async def stop(self) -> None:
        if self._transport:
            self._transport.close()
            self._transport = None
        self._running = False
        logger.info("ws_discovery_stopped")

    def handle_probe(self, message_id: str, addr: tuple[Any, ...]) -> None:
        if not self._running or not self._transport:
            return

        for camera in self._cameras:
            response = _build_probe_match(camera, self._host_ip, message_id)
            self._transport.sendto(response.encode("utf-8"), addr[:2])

        logger.debug(
            "ws_discovery_probe_responded",
            source=f"{addr[0]}:{addr[1]}",
            cameras=len(self._cameras),
        )
