"""ONVIF SOAP XML response templates.

These templates produce protocol-correct ONVIF SOAP responses. Some are
derived from the upstream project (MIT licensed, see NOTICE file).
"""

from onvify.onvif_xml.templates import (
    get_capabilities_response,
    get_device_information_response,
    get_profiles_response,
    get_scopes_response,
    get_stream_uri_response,
    soap_fault,
)

__all__ = [
    "get_capabilities_response",
    "get_device_information_response",
    "get_profiles_response",
    "get_scopes_response",
    "get_stream_uri_response",
    "soap_fault",
]
