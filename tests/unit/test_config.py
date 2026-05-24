"""Tests for Pydantic Settings configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from onvify.config import InferenceSettings, ServerSettings, Settings, StreamingSettings


class TestServerSettings:
    def test_defaults(self) -> None:
        s = ServerSettings()
        assert s.web_ui_port == 5552
        assert s.mediamtx_port == 8554
        assert s.mediamtx_api_port == 9997
        assert s.onvif_base_port == 8001
        assert s.wsgi_max_workers == 20

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEB_UI_PORT", "8080")
        monkeypatch.setenv("MEDIAMTX_PORT", "9554")
        s = ServerSettings()
        assert s.web_ui_port == 8080
        assert s.mediamtx_port == 9554

    def test_invalid_port_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEB_UI_PORT", "99999")
        with pytest.raises(ValidationError):
            ServerSettings()

    def test_zero_port_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEB_UI_PORT", "0")
        with pytest.raises(ValidationError):
            ServerSettings()


class TestInferenceSettings:
    def test_defaults(self) -> None:
        s = InferenceSettings()
        assert s.default_model == "yolov8n.pt"
        assert s.confidence_threshold == 40
        assert s.motion_sensitivity == 50
        assert s.backend == "local"
        assert s.backend_url is None

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_DEFAULT_MODEL", "yolov8s.pt")
        monkeypatch.setenv("AI_CONFIDENCE_THRESHOLD", "60")
        monkeypatch.setenv("AI_BACKEND", "openai_compatible")
        monkeypatch.setenv("AI_BACKEND_URL", "http://gpu-server:8080/v1")
        s = InferenceSettings()
        assert s.default_model == "yolov8s.pt"
        assert s.confidence_threshold == 60
        assert s.backend == "openai_compatible"
        assert s.backend_url == "http://gpu-server:8080/v1"

    def test_confidence_clamped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_CONFIDENCE_THRESHOLD", "150")
        with pytest.raises(ValidationError):
            InferenceSettings()

    def test_confidence_floor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_CONFIDENCE_THRESHOLD", "0")
        with pytest.raises(ValidationError):
            InferenceSettings()


class TestStreamingSettings:
    def test_defaults(self) -> None:
        s = StreamingSettings()
        assert s.gf_video_bitrate == "2500k"
        assert s.gf_encoder_preset == "ultrafast"

    def test_valid_bitrate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GF_VIDEO_BITRATE", "5000k")
        s = StreamingSettings()
        assert s.gf_video_bitrate == "5000k"

    def test_invalid_bitrate_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GF_VIDEO_BITRATE", "abc")
        with pytest.raises(ValidationError):
            StreamingSettings()

    def test_valid_preset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GF_ENCODER_PRESET", "medium")
        s = StreamingSettings()
        assert s.gf_encoder_preset == "medium"

    def test_invalid_preset_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GF_ENCODER_PRESET", "turbo")
        with pytest.raises(ValidationError):
            StreamingSettings()


class TestSettings:
    def test_default_construction(self, tmp_path: pytest.TempPathFactory) -> None:
        s = Settings()
        assert s.debug is False
        assert s.log_format == "console"
        assert s.server.web_ui_port == 5552
        assert s.inference.default_model == "yolov8n.pt"
        assert s.streaming.gf_encoder_preset == "ultrafast"
