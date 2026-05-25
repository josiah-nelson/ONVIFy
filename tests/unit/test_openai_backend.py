"""Tests for the OpenAI-compatible inference backend.

Uses httpx.MockTransport to simulate an OpenAI-compatible vision API server,
validating request format, response parsing, and error handling.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from onvify.inference.openai_compatible import (
    OpenAICompatibleBackend,
    _parse_detections,
)
from onvify.inference.protocol import BackendHealth
from onvify.models.detection import ObjectClass

FAKE_DATA_URI = "data:image/jpeg;base64,/9j/fake"
FAKE_FRAME = object()  # sentinel — _frame_to_data_uri is mocked so the value is unused


def _chat_response(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }


def _detections_json(detections: list[dict[str, Any]]) -> str:
    return json.dumps(detections)


PERSON_DETECTION = {
    "class": "person",
    "confidence": 0.92,
    "bbox": {"x_min": 0.1, "y_min": 0.2, "x_max": 0.5, "y_max": 0.9},
}
VEHICLE_DETECTION = {
    "class": "vehicle",
    "confidence": 0.85,
    "bbox": {"x_min": 0.6, "y_min": 0.3, "x_max": 0.95, "y_max": 0.7},
}
LOW_CONFIDENCE_DETECTION = {
    "class": "animal",
    "confidence": 0.15,
    "bbox": {"x_min": 0.0, "y_min": 0.0, "x_max": 0.1, "y_max": 0.1},
}


class TestParseDetections:
    def test_empty_array(self) -> None:
        result = _parse_detections("[]")
        assert result == []

    def test_single_person(self) -> None:
        result = _parse_detections(_detections_json([PERSON_DETECTION]))
        assert len(result) == 1
        assert result[0].object_class == ObjectClass.PERSON
        assert result[0].confidence == 0.92
        assert result[0].bbox.x_min == 0.1
        assert result[0].bbox.y_max == 0.9

    def test_multiple_detections(self) -> None:
        result = _parse_detections(_detections_json([PERSON_DETECTION, VEHICLE_DETECTION]))
        assert len(result) == 2
        assert result[0].object_class == ObjectClass.PERSON
        assert result[1].object_class == ObjectClass.VEHICLE

    def test_markdown_code_block_stripped(self) -> None:
        wrapped = f"```json\n{_detections_json([PERSON_DETECTION])}\n```"
        result = _parse_detections(wrapped)
        assert len(result) == 1
        assert result[0].object_class == ObjectClass.PERSON

    @pytest.mark.parametrize(
        ("class_name", "expected"),
        [
            ("person", ObjectClass.PERSON),
            ("human", ObjectClass.PERSON),
            ("vehicle", ObjectClass.VEHICLE),
            ("car", ObjectClass.VEHICLE),
            ("truck", ObjectClass.VEHICLE),
            ("bus", ObjectClass.VEHICLE),
            ("animal", ObjectClass.ANIMAL),
            ("cat", ObjectClass.ANIMAL),
            ("dog", ObjectClass.ANIMAL),
            ("bird", ObjectClass.ANIMAL),
            ("unknown", ObjectClass.UNKNOWN),
            ("helicopter", ObjectClass.UNKNOWN),
        ],
    )
    def test_class_name_mapping(self, class_name: str, expected: ObjectClass) -> None:
        det = {**PERSON_DETECTION, "class": class_name}
        result = _parse_detections(_detections_json([det]))
        assert result[0].object_class == expected

    def test_missing_class_defaults_to_unknown(self) -> None:
        det = {"confidence": 0.5, "bbox": {"x_min": 0, "y_min": 0, "x_max": 1, "y_max": 1}}
        result = _parse_detections(_detections_json([det]))
        assert result[0].object_class == ObjectClass.UNKNOWN

    def test_missing_confidence_defaults(self) -> None:
        det = {"class": "person", "bbox": {"x_min": 0, "y_min": 0, "x_max": 1, "y_max": 1}}
        result = _parse_detections(_detections_json([det]))
        assert result[0].confidence == 0.5

    def test_missing_bbox_defaults(self) -> None:
        det = {"class": "person", "confidence": 0.9}
        result = _parse_detections(_detections_json([det]))
        assert result[0].bbox.x_min == 0.0
        assert result[0].bbox.y_max == 1.0

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_detections("not json at all")

    def test_label_preserved(self) -> None:
        result = _parse_detections(_detections_json([PERSON_DETECTION]))
        assert result[0].label == "person"


class TestDetect:
    @pytest.fixture
    def captured_requests(self) -> list[httpx.Request]:
        return []

    def _make_backend(
        self,
        captured_requests: list[httpx.Request],
        response_content: str,
        *,
        status_code: int = 200,
        model: str = "test-vision",
        api_key: str | None = None,
    ) -> OpenAICompatibleBackend:
        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            body = _chat_response(response_content)
            return httpx.Response(status_code, json=body)

        backend = OpenAICompatibleBackend(
            base_url="http://mock-server/v1",
            model=model,
            api_key=api_key,
        )
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers=dict(backend._client.headers),
        )
        return backend

    async def test_request_format(self, captured_requests: list[httpx.Request]) -> None:
        backend = self._make_backend(captured_requests, _detections_json([PERSON_DETECTION]))

        with patch("onvify.inference.openai_compatible._frame_to_data_uri", return_value=FAKE_DATA_URI):
            await backend.detect(FAKE_FRAME)

        assert len(captured_requests) == 1
        req = captured_requests[0]
        assert req.method == "POST"
        assert str(req.url) == "http://mock-server/v1/chat/completions"

        payload = json.loads(req.content)
        assert payload["model"] == "test-vision"
        assert payload["max_tokens"] == 1024

        messages = payload["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

        content = messages[0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert "object detection" in content[0]["text"]
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == FAKE_DATA_URI

    async def test_detections_returned(self, captured_requests: list[httpx.Request]) -> None:
        backend = self._make_backend(captured_requests, _detections_json([PERSON_DETECTION, VEHICLE_DETECTION]))

        with patch("onvify.inference.openai_compatible._frame_to_data_uri", return_value=FAKE_DATA_URI):
            result = await backend.detect(FAKE_FRAME)

        assert len(result) == 2
        assert result[0].object_class == ObjectClass.PERSON
        assert result[1].object_class == ObjectClass.VEHICLE

    async def test_confidence_threshold_filters(self, captured_requests: list[httpx.Request]) -> None:
        backend = self._make_backend(
            captured_requests,
            _detections_json([PERSON_DETECTION, LOW_CONFIDENCE_DETECTION]),
        )

        with patch("onvify.inference.openai_compatible._frame_to_data_uri", return_value=FAKE_DATA_URI):
            result = await backend.detect(FAKE_FRAME, confidence_threshold=0.4)

        assert len(result) == 1
        assert result[0].object_class == ObjectClass.PERSON

    async def test_http_error_propagates(self, captured_requests: list[httpx.Request]) -> None:
        backend = self._make_backend(captured_requests, "[]", status_code=500)

        with (
            patch("onvify.inference.openai_compatible._frame_to_data_uri", return_value=FAKE_DATA_URI),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await backend.detect(FAKE_FRAME)

    async def test_api_key_sent_as_bearer(self, captured_requests: list[httpx.Request]) -> None:
        backend = self._make_backend(captured_requests, _detections_json([]), api_key="sk-test-key-123")

        with patch("onvify.inference.openai_compatible._frame_to_data_uri", return_value=FAKE_DATA_URI):
            await backend.detect(FAKE_FRAME)

        assert captured_requests[0].headers.get("authorization") == "Bearer sk-test-key-123"

    async def test_no_auth_header_without_api_key(self, captured_requests: list[httpx.Request]) -> None:
        backend = self._make_backend(captured_requests, _detections_json([]))

        with patch("onvify.inference.openai_compatible._frame_to_data_uri", return_value=FAKE_DATA_URI):
            await backend.detect(FAKE_FRAME)

        assert "authorization" not in captured_requests[0].headers


class TestHealthCheck:
    def _make_backend(self, *, status_code: int = 200, raise_error: Exception | None = None) -> OpenAICompatibleBackend:
        def handler(request: httpx.Request) -> httpx.Response:
            if raise_error:
                raise raise_error
            return httpx.Response(status_code, json={"data": [{"id": "test-model"}]})

        backend = OpenAICompatibleBackend(base_url="http://mock-server/v1", model="test-model")
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers=dict(backend._client.headers),
        )
        return backend

    async def test_healthy_when_models_endpoint_succeeds(self) -> None:
        backend = self._make_backend()
        status = await backend.health_check()
        assert status.health == BackendHealth.HEALTHY
        assert status.model_name == "test-model"
        assert status.device == "remote"
        assert status.message is None

    async def test_unavailable_on_server_error(self) -> None:
        backend = self._make_backend(status_code=500)
        status = await backend.health_check()
        assert status.health == BackendHealth.UNAVAILABLE
        assert status.message is not None

    async def test_unavailable_on_connection_error(self) -> None:
        backend = self._make_backend(raise_error=httpx.ConnectError("Connection refused"))
        status = await backend.health_check()
        assert status.health == BackendHealth.UNAVAILABLE
        assert "Connection refused" in (status.message or "")

    async def test_supported_models(self) -> None:
        backend = self._make_backend()
        assert backend.supported_models() == ["test-model"]
