"""ONVIF protocol-specific types."""

from __future__ import annotations

from pydantic import BaseModel


class ONVIFScope(BaseModel):
    """ONVIF device scope for WS-Discovery."""

    scope_def: str = "Fixed"
    scope_item: str = ""


class ONVIFDeviceInfo(BaseModel):
    """Device information returned by ONVIF GetDeviceInformation."""

    manufacturer: str = "ONVIFy"
    model: str = "Virtual Camera"
    firmware_version: str = "0.1.0"
    serial_number: str = ""
    hardware_id: str = ""


class ONVIFNetworkInterface(BaseModel):
    """Network interface information for ONVIF responses."""

    token: str = "eth0"
    name: str = "eth0"
    ip_address: str = ""
    prefix_length: int = 24
    mac_address: str = ""
    enabled: bool = True
