"""Tests for WS-Discovery responder."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from onvify.models.camera import Camera, Stream
from onvify.services.onvif_discovery import (
    WSDiscoveryResponder,
    _build_probe_match,
    _DiscoveryProtocol,
    _extract_message_id,
    _is_probe,
    _matches_probe_types,
)


class TestExtractMessageId:
    def test_extracts_from_probe(self) -> None:
        xml = """
        <s:Header>
            <a:MessageID>urn:uuid:abc-123</a:MessageID>
        </s:Header>
        """
        assert _extract_message_id(xml) == "urn:uuid:abc-123"

    def test_returns_none_when_missing(self) -> None:
        assert _extract_message_id("<s:Header></s:Header>") is None

    def test_handles_prefixed_tag(self) -> None:
        xml = "<wsa:MessageID>urn:uuid:xyz</wsa:MessageID>"
        assert _extract_message_id(xml) == "urn:uuid:xyz"


class TestIsProbe:
    def test_matches_action_uri(self) -> None:
        xml = "<a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>"
        assert _is_probe(xml) is True

    def test_matches_probe_element(self) -> None:
        xml = "<d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe>"
        assert _is_probe(xml) is True

    def test_rejects_non_probe(self) -> None:
        xml = "<d:ProbeMatches></d:ProbeMatches>"
        assert _is_probe(xml) is False


class TestMatchesProbeTypes:
    def test_matches_network_video_transmitter(self) -> None:
        xml = "<d:Types>dn:NetworkVideoTransmitter</d:Types>"
        assert _matches_probe_types(xml) is True

    def test_matches_empty_types(self) -> None:
        xml = "<d:Types></d:Types>"
        assert _matches_probe_types(xml) is True

    def test_matches_when_no_types_element(self) -> None:
        xml = "<d:Probe></d:Probe>"
        assert _matches_probe_types(xml) is True

    def test_rejects_unrelated_type(self) -> None:
        xml = "<d:Types>dp:Printer</d:Types>"
        assert _matches_probe_types(xml) is False


class TestBuildProbeMatch:
    def test_contains_camera_id_and_xaddrs(self) -> None:
        camera = Camera(name="Front", source_streams=[Stream(url="rtsp://x")], onvif_port=8001)
        xml = _build_probe_match(camera, "192.168.1.100", "urn:uuid:test-id")
        assert str(camera.id) in xml
        assert "http://192.168.1.100:8001/onvif/device_service" in xml
        assert "urn:uuid:test-id" in xml
        assert "NetworkVideoTransmitter" in xml


class TestDiscoveryProtocol:
    def test_responds_to_probe(self) -> None:
        responder = WSDiscoveryResponder("192.168.1.100")
        camera = Camera(name="Test", source_streams=[Stream(url="rtsp://x")], onvif_port=8001)
        responder.set_cameras([camera])
        responder._running = True
        transport = MagicMock()
        responder._transport = transport

        protocol = _DiscoveryProtocol(responder)
        probe_xml = (
            '<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
            ' xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
            ' xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
            "<s:Header>"
            "<a:MessageID>urn:uuid:probe-001</a:MessageID>"
            "<a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>"
            "</s:Header>"
            "<s:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></s:Body>"
            "</s:Envelope>"
        )
        protocol.datagram_received(probe_xml.encode("utf-8"), ("10.0.0.5", 49152))

        transport.sendto.assert_called_once()
        sent_data = transport.sendto.call_args[0][0]
        assert b"ProbeMatches" in sent_data
        assert b"urn:uuid:probe-001" in sent_data

    def test_ignores_non_probe(self) -> None:
        responder = WSDiscoveryResponder("192.168.1.100")
        responder._running = True
        transport = MagicMock()
        responder._transport = transport

        protocol = _DiscoveryProtocol(responder)
        protocol.datagram_received(b"<Hello/>", ("10.0.0.5", 49152))

        transport.sendto.assert_not_called()

    def test_ignores_wrong_type(self) -> None:
        responder = WSDiscoveryResponder("192.168.1.100")
        camera = Camera(name="Test", source_streams=[Stream(url="rtsp://x")], onvif_port=8001)
        responder.set_cameras([camera])
        responder._running = True
        transport = MagicMock()
        responder._transport = transport

        protocol = _DiscoveryProtocol(responder)
        probe_xml = (
            "<a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>"
            "<d:Types>dp:Printer</d:Types>"
            "<a:MessageID>urn:uuid:wrong</a:MessageID>"
        )
        protocol.datagram_received(probe_xml.encode("utf-8"), ("10.0.0.5", 49152))

        transport.sendto.assert_not_called()


@pytest.mark.asyncio
class TestWSDiscoveryResponder:
    async def test_set_cameras_filters_without_onvif_port(self) -> None:
        responder = WSDiscoveryResponder("192.168.1.100")
        cameras = [
            Camera(name="WithPort", source_streams=[Stream(url="rtsp://x")], onvif_port=8001),
            Camera(name="NoPort", source_streams=[Stream(url="rtsp://y")]),
        ]
        responder.set_cameras(cameras)
        assert len(responder._cameras) == 1
        assert responder._cameras[0].name == "WithPort"
