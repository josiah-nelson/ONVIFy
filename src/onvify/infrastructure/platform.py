"""OS-specific platform abstraction.

Isolates platform-dependent behavior (service management, network interfaces,
hardware acceleration detection) behind a unified interface so the rest of the
codebase remains platform-agnostic.
"""

from __future__ import annotations

import platform
import subprocess
from typing import Literal


def get_platform() -> Literal["windows", "linux", "macos"]:
    """Detect the current operating system."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return "linux"


def is_apple_silicon() -> bool:
    return get_platform() == "macos" and platform.machine() == "arm64"


def get_local_ip() -> str:
    """Get the primary local IP address."""
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return str(ip)
    except Exception:
        return "127.0.0.1"


def check_binary_available(name: str) -> bool:
    """Check if an external binary is available on PATH."""
    try:
        result = subprocess.run(
            ["which" if get_platform() != "windows" else "where", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False
