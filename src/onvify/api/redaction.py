"""Helpers for removing secrets from API response values."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def redact_url(url: str | None) -> str | None:
    """Strip URL userinfo, query strings, and fragments before returning URLs."""
    if url is None:
        return None

    parsed = urlparse(url)
    if parsed.username is None and parsed.password is None and not parsed.query and not parsed.fragment:
        return url

    netloc = parsed.netloc
    if parsed.username is not None or parsed.password is not None:
        hostport = parsed.netloc.rsplit("@", 1)[-1]
        netloc = f"***@{hostport}"

    redacted = parsed._replace(netloc=netloc, query="", fragment="")
    return urlunparse(redacted)
