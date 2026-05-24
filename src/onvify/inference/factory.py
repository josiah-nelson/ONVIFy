"""Inference backend factory.

Instantiates the correct backend based on configuration.
"""

from __future__ import annotations

import structlog

from onvify.config import InferenceSettings
from onvify.inference.protocol import InferenceBackend

logger = structlog.get_logger()


def create_inference_backend(settings: InferenceSettings) -> InferenceBackend:
    """Create an inference backend based on the configured backend type."""
    if settings.backend == "openai_compatible":
        from onvify.inference.openai_compatible import OpenAICompatibleBackend

        if not settings.backend_url:
            msg = "AI_BACKEND_URL is required when AI_BACKEND=openai_compatible"
            raise ValueError(msg)
        backend: InferenceBackend = OpenAICompatibleBackend(
            base_url=settings.backend_url,
        )
        logger.info("inference_backend_created", backend="openai_compatible", url=settings.backend_url)
        return backend

    if settings.backend == "local":
        from onvify.inference.local_yolo import LocalYOLOBackend

        backend = LocalYOLOBackend(
            model_name=settings.default_model,
            torch_threads=settings.torch_threads,
        )
        logger.info("inference_backend_created", backend="local_yolo", model=settings.default_model)
        return backend

    msg = f"Unsupported inference backend: {settings.backend!r}. Use 'local' or 'openai_compatible'."
    raise ValueError(msg)
