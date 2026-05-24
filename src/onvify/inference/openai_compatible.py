"""OpenAI-compatible inference backend.

Calls any vision model served via an OpenAI-compatible API (vLLM, llama.cpp,
Ollama, TGI, or any custom server exposing /v1/chat/completions with vision).
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from onvify.inference.protocol import BackendHealth, BackendStatus
from onvify.models.detection import BoundingBox, Detection, ObjectClass

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

logger = structlog.get_logger()

_DETECTION_PROMPT = (
    "Analyze this camera frame for object detection. "
    "Return a JSON array of detected objects. Each object should have: "
    '"class" (one of: person, vehicle, animal, unknown), '
    '"confidence" (0.0-1.0), '
    '"bbox" {"x_min", "y_min", "x_max", "y_max"} as normalized 0.0-1.0 coordinates. '
    "Return only the JSON array, no other text."
)


def _frame_to_data_uri(frame: npt.NDArray[np.uint8]) -> str:
    """Encode a BGR frame as a base64 JPEG data URI."""
    import cv2

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _parse_detections(content: str) -> list[Detection]:
    """Parse the model's JSON response into Detection objects."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])

    items: list[dict[str, Any]] = json.loads(text)
    detections: list[Detection] = []
    for item in items:
        cls = item.get("class", "unknown")
        object_class = ObjectClass.UNKNOWN
        if cls in ("person", "human"):
            object_class = ObjectClass.PERSON
        elif cls in ("vehicle", "car", "truck", "bus"):
            object_class = ObjectClass.VEHICLE
        elif cls in ("animal", "cat", "dog", "bird"):
            object_class = ObjectClass.ANIMAL

        bbox_data = item.get("bbox", {})
        detections.append(
            Detection(
                object_class=object_class,
                confidence=float(item.get("confidence", 0.5)),
                bbox=BoundingBox(
                    x_min=float(bbox_data.get("x_min", 0.0)),
                    y_min=float(bbox_data.get("y_min", 0.0)),
                    x_max=float(bbox_data.get("x_max", 1.0)),
                    y_max=float(bbox_data.get("y_max", 1.0)),
                ),
                label=cls,
            )
        )
    return detections


class OpenAICompatibleBackend:
    """Inference via an OpenAI-compatible vision API.

    Implements the InferenceBackend protocol.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080/v1",
        model: str = "default",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(headers=headers, timeout=timeout)

    async def detect(
        self,
        frame: npt.NDArray[np.uint8],
        confidence_threshold: float = 0.4,
    ) -> list[Detection]:
        data_uri = _frame_to_data_uri(frame)
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _DETECTION_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            "max_tokens": 1024,
        }

        resp = await self._client.post(f"{self._base_url}/chat/completions", json=payload)
        resp.raise_for_status()
        body = resp.json()
        content = body["choices"][0]["message"]["content"]

        all_detections = _parse_detections(content)
        return [d for d in all_detections if d.confidence >= confidence_threshold]

    async def health_check(self) -> BackendStatus:
        try:
            resp = await self._client.get(f"{self._base_url}/models")
            resp.raise_for_status()
            return BackendStatus(
                health=BackendHealth.HEALTHY,
                model_name=self._model,
                device="remote",
            )
        except Exception as e:
            return BackendStatus(
                health=BackendHealth.UNAVAILABLE,
                model_name=self._model,
                device="remote",
                message=str(e),
            )

    def supported_models(self) -> list[str]:
        return [self._model]

    async def close(self) -> None:
        await self._client.aclose()
