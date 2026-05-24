"""Domain models for ONVIFy."""

from onvify.models.camera import Camera, CameraStatus, Profile, Stream, StreamType
from onvify.models.detection import BoundingBox, Detection, DetectionEvent, ObjectClass

__all__ = [
    "BoundingBox",
    "Camera",
    "CameraStatus",
    "Detection",
    "DetectionEvent",
    "ObjectClass",
    "Profile",
    "Stream",
    "StreamType",
]
