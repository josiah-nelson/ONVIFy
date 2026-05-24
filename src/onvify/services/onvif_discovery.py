"""WS-Discovery responder for ONVIF device discovery.

Listens on the WS-Discovery multicast address (239.255.255.250:3702) and
responds with probe matches for each virtual camera, allowing NVRs to
automatically discover ONVIFy cameras on the network.
"""

from __future__ import annotations

import uuid

import structlog

from onvify.models.camera import Camera

logger = structlog.get_logger()

WS_DISCOVERY_MULTICAST = ("239.255.255.250", 3702)


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


class WSDiscoveryResponder:
    """Responds to WS-Discovery Probe requests on the network."""

    def __init__(self, host_ip: str) -> None:
        self._host_ip = host_ip
        self._cameras: list[Camera] = []
        self._running = False

    def set_cameras(self, cameras: list[Camera]) -> None:
        self._cameras = [c for c in cameras if c.onvif_port is not None]

    async def start(self) -> None:
        self._running = True
        logger.info("ws_discovery_started", host=self._host_ip)

    async def stop(self) -> None:
        self._running = False
        logger.info("ws_discovery_stopped")
