"""Tests for ONVIF SOAP XML response templates."""

from __future__ import annotations

from xml.etree.ElementTree import fromstring

from onvify.models.camera import Camera, Profile, Stream
from onvify.models.onvif import ONVIFDeviceInfo
from onvify.onvif_xml import (
    get_capabilities_response,
    get_device_information_response,
    get_profiles_response,
    get_scopes_response,
    get_stream_uri_response,
    soap_fault,
)

NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_DEVICE = "http://www.onvif.org/ver10/device/wsdl"
NS_MEDIA = "http://www.onvif.org/ver10/media/wsdl"
NS_SCHEMA = "http://www.onvif.org/ver10/schema"


class TestGetDeviceInformationResponse:
    def test_contains_manufacturer_and_model(self) -> None:
        info = ONVIFDeviceInfo(manufacturer="TestMfg", model="TestModel", firmware_version="1.0.0")
        xml = get_device_information_response(info)
        root = fromstring(xml)
        body = root.find(f"{{{NS_SOAP}}}Body")
        assert body is not None
        resp = body.find(f"{{{NS_DEVICE}}}GetDeviceInformationResponse")
        assert resp is not None
        assert resp.findtext(f"{{{NS_DEVICE}}}Manufacturer") == "TestMfg"
        assert resp.findtext(f"{{{NS_DEVICE}}}Model") == "TestModel"
        assert resp.findtext(f"{{{NS_DEVICE}}}FirmwareVersion") == "1.0.0"

    def test_xml_declaration_present(self) -> None:
        info = ONVIFDeviceInfo()
        xml = get_device_information_response(info)
        assert xml.startswith('<?xml version="1.0"')


class TestGetProfilesResponse:
    def test_profiles_have_tokens_and_encoding(self) -> None:
        stream = Stream(url="rtsp://localhost/test")
        profiles = [
            Profile(
                token="main",
                name="Main Stream",
                stream=stream,
                encoding="H264",
                resolution_width=1920,
                resolution_height=1080,
            ),
            Profile(
                token="sub",
                name="Sub Stream",
                stream=stream,
                encoding="H264",
                resolution_width=640,
                resolution_height=480,
            ),
        ]
        xml = get_profiles_response(profiles)
        root = fromstring(xml)
        body = root.find(f"{{{NS_SOAP}}}Body")
        assert body is not None
        resp = body.find(f"{{{NS_MEDIA}}}GetProfilesResponse")
        assert resp is not None
        profile_els = resp.findall(f"{{{NS_MEDIA}}}Profiles")
        assert len(profile_els) == 2
        assert profile_els[0].get("token") == "main"
        assert profile_els[1].get("token") == "sub"

    def test_empty_profiles_returns_valid_soap(self) -> None:
        xml = get_profiles_response([])
        root = fromstring(xml)
        body = root.find(f"{{{NS_SOAP}}}Body")
        assert body is not None


class TestGetStreamUriResponse:
    def test_contains_uri(self) -> None:
        xml = get_stream_uri_response("rtsp://192.168.1.10:8554/camera1")
        root = fromstring(xml)
        body = root.find(f"{{{NS_SOAP}}}Body")
        assert body is not None
        resp = body.find(f"{{{NS_MEDIA}}}GetStreamUriResponse")
        assert resp is not None
        media_uri = resp.find(f"{{{NS_MEDIA}}}MediaUri")
        assert media_uri is not None
        assert media_uri.findtext(f"{{{NS_SCHEMA}}}Uri") == "rtsp://192.168.1.10:8554/camera1"


class TestGetCapabilitiesResponse:
    def test_contains_service_xaddrs(self) -> None:
        xml = get_capabilities_response("192.168.1.100", 8080)
        root = fromstring(xml)
        body = root.find(f"{{{NS_SOAP}}}Body")
        assert body is not None
        resp = body.find(f"{{{NS_DEVICE}}}GetCapabilitiesResponse")
        assert resp is not None
        caps = resp.find(f"{{{NS_DEVICE}}}Capabilities")
        assert caps is not None
        device = caps.find(f"{{{NS_SCHEMA}}}Device")
        assert device is not None
        assert "device_service" in (device.findtext(f"{{{NS_SCHEMA}}}XAddr") or "")


class TestGetScopesResponse:
    def test_contains_camera_name_scope(self) -> None:
        camera = Camera(name="Front Door", source_streams=[Stream(url="rtsp://x")])
        xml = get_scopes_response(camera)
        root = fromstring(xml)
        body = root.find(f"{{{NS_SOAP}}}Body")
        assert body is not None
        resp = body.find(f"{{{NS_DEVICE}}}GetScopesResponse")
        assert resp is not None
        scope_items = [el.findtext(f"{{{NS_SCHEMA}}}ScopeItem") for el in resp.findall(f"{{{NS_DEVICE}}}Scopes")]
        assert any("Front Door" in (s or "") for s in scope_items)


class TestSoapFault:
    def test_fault_structure(self) -> None:
        xml = soap_fault("Sender", "Action not recognized")
        root = fromstring(xml)
        body = root.find(f"{{{NS_SOAP}}}Body")
        assert body is not None
        fault = body.find(f"{{{NS_SOAP}}}Fault")
        assert fault is not None
        reason = fault.find(f"{{{NS_SOAP}}}Reason")
        assert reason is not None
        text = reason.find(f"{{{NS_SOAP}}}Text")
        assert text is not None
        assert text.text == "Action not recognized"
