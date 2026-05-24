"""MJPEG stream input and output handlers.

Input: Pulls MJPEG streams from cameras via HTTP (multipart/x-mixed-replace).
Output: Serves MJPEG streams over HTTP for browser-native viewing.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

logger = structlog.get_logger()

_MJPEG_BOUNDARY = b"--frame"


async def pull_mjpeg_frames(
    url: str,
    timeout: float = 30.0,
) -> AsyncIterator[bytes]:
    """Pull JPEG frames from an MJPEG HTTP stream.

    Yields raw JPEG bytes for each frame in the multipart/x-mixed-replace stream.
    """
    async with httpx.AsyncClient(timeout=timeout) as client, client.stream("GET", url) as response:
        response.raise_for_status()
        buffer = b""
        async for chunk in response.aiter_bytes(chunk_size=8192):
            buffer += chunk
            while True:
                start = buffer.find(b"\xff\xd8")
                if start == -1:
                    break
                end = buffer.find(b"\xff\xd9", start + 2)
                if end == -1:
                    break
                yield buffer[start : end + 2]
                buffer = buffer[end + 2 :]


async def mjpeg_response_stream(
    frame_queue: asyncio.Queue[bytes],
    fps: float = 10.0,
) -> AsyncIterator[bytes]:
    """Generate an MJPEG multipart/x-mixed-replace HTTP response body.

    Reads JPEG frames from the queue and yields them formatted for browser consumption.
    """
    interval = 1.0 / fps
    while True:
        try:
            jpeg_bytes = await asyncio.wait_for(frame_queue.get(), timeout=5.0)
        except TimeoutError:
            continue

        yield (
            _MJPEG_BOUNDARY
            + b"\r\nContent-Type: image/jpeg\r\n"
            + f"Content-Length: {len(jpeg_bytes)}\r\n\r\n".encode()
            + jpeg_bytes
            + b"\r\n"
        )
        await asyncio.sleep(interval)


def decode_jpeg_frame(jpeg_bytes: bytes) -> npt.NDArray[np.uint8]:
    """Decode raw JPEG bytes into a BGR numpy array for the inference pipeline."""
    import cv2
    import numpy as np

    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        msg = "Failed to decode JPEG frame"
        raise ValueError(msg)
    return frame
