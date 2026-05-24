"""Local YOLO inference backend.

Supports CPU, MPS (Apple Silicon), and CoreML (Apple Neural Engine) devices.
Ported from the fork's ai_device.py and coreml_cache.py modules.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from onvify.inference.protocol import BackendHealth, BackendStatus, InferenceBackend
from onvify.models.detection import BoundingBox, Detection, ObjectClass

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

logger = structlog.get_logger()

_YOLO_CLASS_MAP: dict[str, ObjectClass] = {
    "person": ObjectClass.PERSON,
    "car": ObjectClass.VEHICLE,
    "truck": ObjectClass.VEHICLE,
    "bus": ObjectClass.VEHICLE,
    "motorcycle": ObjectClass.VEHICLE,
    "bicycle": ObjectClass.VEHICLE,
    "cat": ObjectClass.ANIMAL,
    "dog": ObjectClass.ANIMAL,
    "bird": ObjectClass.ANIMAL,
    "horse": ObjectClass.ANIMAL,
}


def _select_device() -> str:
    """Select the best available inference device."""
    try:
        import torch

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            logger.info("inference_device_selected", device="mps")
            return "mps"
    except ImportError:
        pass

    logger.info("inference_device_selected", device="cpu")
    return "cpu"


def _configure_torch_threads(override: int | None = None) -> int:
    """Set PyTorch inter/intra-op thread count based on CPU cores."""
    try:
        import torch
    except ImportError:
        return 0

    if override is not None:
        count = max(1, override)
    else:
        cpu_count = os.cpu_count() or 2
        count = min(4, max(1, cpu_count // 2))

    torch.set_num_threads(count)
    torch.set_num_interop_threads(count)
    logger.info("torch_threads_configured", count=count)
    return count


def _get_coreml_model_path(model_name: str, cache_dir: Path) -> Path | None:
    """Check for a cached CoreML export; return None if not available."""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return None

    try:
        import coremltools  # noqa: F401
    except ImportError:
        return None

    stem = Path(model_name).stem
    cached = cache_dir / f"{stem}.mlpackage"
    if cached.exists():
        logger.info("coreml_cache_hit", model=model_name, path=str(cached))
        return cached

    return None


class LocalYOLOBackend:
    """YOLO inference running locally via ultralytics.

    Implements the InferenceBackend protocol.
    """

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        torch_threads: int | None = None,
        coreml_cache_dir: Path | None = None,
    ) -> None:
        self._model_name = model_name
        self._torch_threads = torch_threads
        self._coreml_cache_dir = coreml_cache_dir or Path(".coreml_cache")
        self._device = _select_device()
        self._model: Any = None
        _configure_torch_threads(torch_threads)

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        from ultralytics import YOLO

        coreml_path = _get_coreml_model_path(self._model_name, self._coreml_cache_dir)
        load_path = str(coreml_path) if coreml_path else self._model_name

        model = YOLO(load_path)
        logger.info("yolo_model_loaded", model=load_path, device=self._device)
        self._model = model
        return model

    async def detect(
        self,
        frame: npt.NDArray[np.uint8],
        confidence_threshold: float = 0.4,
    ) -> list[Detection]:
        model = self._load_model()
        results = model(frame, conf=confidence_threshold, device=self._device, verbose=False)

        detections: list[Detection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i])
                cls_name = result.names[cls_id]
                conf = float(boxes.conf[i])
                x1, y1, x2, y2 = boxes.xyxyn[i].tolist()
                object_class = _YOLO_CLASS_MAP.get(cls_name, ObjectClass.UNKNOWN)
                detections.append(
                    Detection(
                        object_class=object_class,
                        confidence=conf,
                        bbox=BoundingBox(x_min=x1, y_min=y1, x_max=x2, y_max=y2),
                        label=cls_name,
                    )
                )

        return detections

    async def health_check(self) -> BackendStatus:
        try:
            self._load_model()
            return BackendStatus(
                health=BackendHealth.HEALTHY,
                model_name=self._model_name,
                device=self._device,
            )
        except Exception as e:
            return BackendStatus(
                health=BackendHealth.UNAVAILABLE,
                model_name=self._model_name,
                device=self._device,
                message=str(e),
            )

    def supported_models(self) -> list[str]:
        return ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt", "yolo11n.pt"]
