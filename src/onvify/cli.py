"""CLI entry point for ONVIFy."""

from __future__ import annotations

import argparse

import uvicorn

from onvify import __version__
from onvify.config import Settings
from onvify.infrastructure.logging import configure_logging


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="onvify",
        description="Enterprise ONVIF/RTSP virtual camera server",
    )
    parser.add_argument("--version", action="version", version=f"ONVIFy {__version__}")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="Web UI port (default: from config)")
    parser.add_argument("--log-format", choices=["json", "console"], default=None, help="Log output format")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = Settings()

    log_format = args.log_format or settings.log_format
    configure_logging(log_format=log_format)

    port = args.port or settings.server.web_ui_port
    debug = args.debug or settings.debug

    uvicorn.run(
        "onvify.api.app:create_app",
        factory=True,
        host=args.host,
        port=port,
        reload=debug,
        log_level="debug" if debug else "info",
    )


if __name__ == "__main__":
    main()
