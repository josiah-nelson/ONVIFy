"""ONVIF SOAP XML response template rendering.

Generates spec-compliant ONVIF SOAP responses using Python's xml.etree
for safe, well-formed XML output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, SubElement, tostring

if TYPE_CHECKING:
    from onvify.models.camera import Camera, Profile
    from onvify.models.onvif import ONVIFDeviceInfo

NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_WSA = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
NS_DEVICE = "http://www.onvif.org/ver10/device/wsdl"
NS_MEDIA = "http://www.onvif.org/ver10/media/wsdl"
NS_SCHEMA = "http://www.onvif.org/ver10/schema"

_NS_MAP = {
    "s": NS_SOAP,
    "tds": NS_DEVICE,
    "tr2": NS_MEDIA,
    "tt": NS_SCHEMA,
}


def _envelope(action: str) -> tuple[Element, Element]:
    envelope = Element(f"{{{NS_SOAP}}}Envelope")
    for prefix, uri in _NS_MAP.items():
        envelope.set(f"xmlns:{prefix}", uri)

    header = SubElement(envelope, f"{{{NS_SOAP}}}Header")
    action_el = SubElement(header, f"{{{NS_WSA}}}Action")
    action_el.text = action

    body = SubElement(envelope, f"{{{NS_SOAP}}}Body")
    return envelope, body


def _serialize(envelope: Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(envelope, encoding="unicode", xml_declaration=False)


def get_device_information_response(info: ONVIFDeviceInfo) -> str:
    action = f"{NS_DEVICE}/GetDeviceInformationResponse"
    envelope, body = _envelope(action)

    resp = SubElement(body, f"{{{NS_DEVICE}}}GetDeviceInformationResponse")
    SubElement(resp, f"{{{NS_DEVICE}}}Manufacturer").text = info.manufacturer
    SubElement(resp, f"{{{NS_DEVICE}}}Model").text = info.model
    SubElement(resp, f"{{{NS_DEVICE}}}FirmwareVersion").text = info.firmware_version
    SubElement(resp, f"{{{NS_DEVICE}}}SerialNumber").text = info.serial_number
    SubElement(resp, f"{{{NS_DEVICE}}}HardwareId").text = info.hardware_id

    return _serialize(envelope)


def get_profiles_response(profiles: list[Profile]) -> str:
    action = f"{NS_MEDIA}/GetProfilesResponse"
    envelope, body = _envelope(action)

    resp = SubElement(body, f"{{{NS_MEDIA}}}GetProfilesResponse")
    for profile in profiles:
        prof_el = SubElement(resp, f"{{{NS_MEDIA}}}Profiles")
        prof_el.set("token", profile.token)
        prof_el.set("fixed", "true")
        SubElement(prof_el, f"{{{NS_SCHEMA}}}Name").text = profile.name

        video_enc = SubElement(prof_el, f"{{{NS_SCHEMA}}}VideoEncoderConfiguration")
        video_enc.set("token", f"{profile.token}_vec")
        SubElement(video_enc, f"{{{NS_SCHEMA}}}Name").text = f"{profile.name} Encoder"
        SubElement(video_enc, f"{{{NS_SCHEMA}}}Encoding").text = profile.encoding
        resolution = SubElement(video_enc, f"{{{NS_SCHEMA}}}Resolution")
        SubElement(resolution, f"{{{NS_SCHEMA}}}Width").text = str(profile.resolution_width)
        SubElement(resolution, f"{{{NS_SCHEMA}}}Height").text = str(profile.resolution_height)

    return _serialize(envelope)


def get_stream_uri_response(uri: str) -> str:
    action = f"{NS_MEDIA}/GetStreamUriResponse"
    envelope, body = _envelope(action)

    resp = SubElement(body, f"{{{NS_MEDIA}}}GetStreamUriResponse")
    media_uri = SubElement(resp, f"{{{NS_MEDIA}}}MediaUri")
    SubElement(media_uri, f"{{{NS_SCHEMA}}}Uri").text = uri
    SubElement(media_uri, f"{{{NS_SCHEMA}}}InvalidAfterConnect").text = "false"
    SubElement(media_uri, f"{{{NS_SCHEMA}}}InvalidAfterReboot").text = "false"
    SubElement(media_uri, f"{{{NS_SCHEMA}}}Timeout").text = "PT60S"

    return _serialize(envelope)


def get_capabilities_response(host: str, onvif_port: int) -> str:
    action = f"{NS_DEVICE}/GetCapabilitiesResponse"
    envelope, body = _envelope(action)
    base = f"http://{host}:{onvif_port}/onvif"

    resp = SubElement(body, f"{{{NS_DEVICE}}}GetCapabilitiesResponse")
    caps = SubElement(resp, f"{{{NS_DEVICE}}}Capabilities")

    device_cap = SubElement(caps, f"{{{NS_SCHEMA}}}Device")
    SubElement(device_cap, f"{{{NS_SCHEMA}}}XAddr").text = f"{base}/device_service"

    media_cap = SubElement(caps, f"{{{NS_SCHEMA}}}Media")
    SubElement(media_cap, f"{{{NS_SCHEMA}}}XAddr").text = f"{base}/media_service"

    events_cap = SubElement(caps, f"{{{NS_SCHEMA}}}Events")
    SubElement(events_cap, f"{{{NS_SCHEMA}}}XAddr").text = f"{base}/event_service"

    return _serialize(envelope)


def get_scopes_response(camera: Camera) -> str:
    action = f"{NS_DEVICE}/GetScopesResponse"
    envelope, body = _envelope(action)

    resp = SubElement(body, f"{{{NS_DEVICE}}}GetScopesResponse")

    scopes = [
        "onvif://www.onvif.org/type/video_encoder",
        "onvif://www.onvif.org/type/Network_Video_Transmitter",
        f"onvif://www.onvif.org/name/{camera.name}",
        "onvif://www.onvif.org/hardware/ONVIFy",
    ]

    for scope_uri in scopes:
        scope_el = SubElement(resp, f"{{{NS_DEVICE}}}Scopes")
        SubElement(scope_el, f"{{{NS_SCHEMA}}}ScopeDef").text = "Fixed"
        SubElement(scope_el, f"{{{NS_SCHEMA}}}ScopeItem").text = scope_uri

    return _serialize(envelope)


def soap_fault(code: str, reason: str) -> str:
    envelope = Element(f"{{{NS_SOAP}}}Envelope")
    envelope.set("xmlns:s", NS_SOAP)
    body = SubElement(envelope, f"{{{NS_SOAP}}}Body")
    fault = SubElement(body, f"{{{NS_SOAP}}}Fault")
    code_el = SubElement(fault, f"{{{NS_SOAP}}}Code")
    SubElement(code_el, f"{{{NS_SOAP}}}Value").text = f"s:{code}"
    reason_el = SubElement(fault, f"{{{NS_SOAP}}}Reason")
    text_el = SubElement(reason_el, f"{{{NS_SOAP}}}Text")
    text_el.set("xml:lang", "en")
    text_el.text = reason
    return _serialize(envelope)
