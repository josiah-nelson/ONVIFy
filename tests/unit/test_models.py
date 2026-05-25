"""Tests for domain models."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from onvify.models.camera import Camera, CameraStatus, Stream, StreamType
from onvify.models.detection import BoundingBox, Detection, DetectionEvent, ObjectClass
from onvify.models.onvif import ONVIFDeviceInfo


class TestCameraModel:
    def test_default_status(self) -> None:
        camera = Camera(name="Test", source_streams=[Stream(url="rtsp://x")])
        assert camera.status == CameraStatus.OFFLINE

    def test_primary_stream(self) -> None:
        s = Stream(url="rtsp://x", stream_type=StreamType.RTSP)
        camera = Camera(name="Test", source_streams=[s])
        assert camera.primary_stream is not None
        assert camera.primary_stream.url == "rtsp://x"

    def test_no_streams(self) -> None:
        camera = Camera(name="Empty", source_streams=[])
        assert camera.primary_stream is None
        assert camera.stream_type == "unknown"

    def test_stream_type_detection(self) -> None:
        rtsp = Camera(name="R", source_streams=[Stream(url="rtsp://x", stream_type=StreamType.RTSP)])
        mjpeg = Camera(name="M", source_streams=[Stream(url="http://x", stream_type=StreamType.MJPEG)])
        assert rtsp.stream_type == StreamType.RTSP
        assert mjpeg.stream_type == StreamType.MJPEG

    def test_onvif_password_requires_username(self) -> None:
        with pytest.raises(ValidationError, match="onvif_username is required"):
            Camera(name="Secure", source_streams=[Stream(url="rtsp://x")], onvif_password="secret")


class TestDetectionModels:
    def test_bounding_box_validation(self) -> None:
        bb = BoundingBox(x_min=0.1, y_min=0.2, x_max=0.9, y_max=0.8)
        assert bb.x_min == 0.1

    def test_bounding_box_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            BoundingBox(x_min=-0.1, y_min=0.2, x_max=0.9, y_max=0.8)

    def test_detection_event(self) -> None:
        cam_id = uuid4()
        event = DetectionEvent(
            camera_id=cam_id,
            detections=[
                Detection(
                    object_class=ObjectClass.PERSON,
                    confidence=0.85,
                    bbox=BoundingBox(x_min=0.1, y_min=0.2, x_max=0.5, y_max=0.8),
                )
            ],
            inference_time_ms=42.5,
        )
        assert event.camera_id == cam_id
        assert len(event.detections) == 1
        assert event.detections[0].object_class == ObjectClass.PERSON


class TestONVIFModels:
    def test_device_info_defaults(self) -> None:
        info = ONVIFDeviceInfo()
        assert info.manufacturer == "ONVIFy"
        assert info.model == "Virtual Camera"
