"""ONVIF event subscription and notification.

Manages WS-BaseNotification subscriptions from NVRs and forwards AI
detection events as ONVIF motion alarm notifications.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from xml.etree.ElementTree import Element, SubElement, fromstring, tostring

import httpx
import structlog

logger = structlog.get_logger()

NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_WSA = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
NS_WSNT = "http://docs.oasis-open.org/wsn/b-2"
NS_WSTOP = "http://docs.oasis-open.org/wsn/t-1"
NS_ONVIF_EVENT = "http://www.onvif.org/ver10/schema"

DEFAULT_SUBSCRIPTION_TTL = timedelta(minutes=60)
NOTIFY_TIMEOUT = 5.0


@dataclass
class Subscription:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    callback_url: str = ""
    camera_id: str = ""
    expires_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC) + DEFAULT_SUBSCRIPTION_TTL)

    @property
    def is_expired(self) -> bool:
        return datetime.now(tz=UTC) >= self.expires_at


class ONVIFEventManager:
    """Manages ONVIF event subscriptions and sends notifications."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, Subscription] = {}
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=NOTIFY_TIMEOUT)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._subscriptions.clear()

    def subscribe(self, callback_url: str, camera_id: str, ttl: timedelta | None = None) -> Subscription:
        if not _is_safe_callback_url(callback_url):
            msg = f"Callback URL rejected: {callback_url}"
            raise ValueError(msg)
        sub = Subscription(
            callback_url=callback_url,
            camera_id=camera_id,
            expires_at=datetime.now(tz=UTC) + (ttl or DEFAULT_SUBSCRIPTION_TTL),
        )
        self._subscriptions[sub.id] = sub
        logger.info(
            "onvif_event_subscribed",
            subscription_id=sub.id,
            camera_id=camera_id,
            callback=callback_url,
        )
        return sub

    def unsubscribe(self, subscription_id: str) -> bool:
        removed = self._subscriptions.pop(subscription_id, None)
        if removed:
            logger.info("onvif_event_unsubscribed", subscription_id=subscription_id)
        return removed is not None

    def renew(self, subscription_id: str, ttl: timedelta | None = None) -> Subscription | None:
        sub = self._subscriptions.get(subscription_id)
        if sub is None or sub.is_expired:
            self._subscriptions.pop(subscription_id, None)
            return None
        sub.expires_at = datetime.now(tz=UTC) + (ttl or DEFAULT_SUBSCRIPTION_TTL)
        return sub

    def get_subscriptions(self, camera_id: str) -> list[Subscription]:
        self._purge_expired()
        return [s for s in self._subscriptions.values() if s.camera_id == camera_id]

    async def notify_motion(self, camera_id: str, is_motion: bool = True) -> None:
        subs = self.get_subscriptions(camera_id)
        if not subs or not self._client:
            return

        message = _build_motion_notify(camera_id, is_motion)
        await asyncio.gather(
            *(self._send_notify(sub, message) for sub in subs),
            return_exceptions=True,
        )

    async def _send_notify(self, sub: Subscription, message: str) -> None:
        if not self._client:
            return
        try:
            resp = await self._client.post(
                sub.callback_url,
                content=message.encode("utf-8"),
                headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            )
            if resp.status_code >= 400:
                logger.warning(
                    "onvif_notify_failed",
                    subscription_id=sub.id,
                    status=resp.status_code,
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "onvif_notify_error",
                subscription_id=sub.id,
                error=str(exc),
            )

    def _purge_expired(self) -> None:
        expired = [sid for sid, sub in self._subscriptions.items() if sub.is_expired]
        for sid in expired:
            del self._subscriptions[sid]


def _build_motion_notify(camera_id: str, is_motion: bool) -> str:
    envelope = Element(f"{{{NS_SOAP}}}Envelope")
    envelope.set("xmlns:s", NS_SOAP)
    envelope.set("xmlns:wsnt", NS_WSNT)
    envelope.set("xmlns:tt", NS_ONVIF_EVENT)

    header = SubElement(envelope, f"{{{NS_SOAP}}}Header")
    action = SubElement(header, f"{{{NS_WSA}}}Action")
    action.text = f"{NS_WSNT}/Notify"

    body = SubElement(envelope, f"{{{NS_SOAP}}}Body")
    notify = SubElement(body, f"{{{NS_WSNT}}}Notify")
    msg = SubElement(notify, f"{{{NS_WSNT}}}NotificationMessage")

    topic = SubElement(msg, f"{{{NS_WSNT}}}Topic")
    topic.set("Dialect", f"{NS_WSTOP}/ConcreteSet")
    topic.text = "tns1:RuleEngine/CellMotionDetector/Motion"

    message_el = SubElement(msg, f"{{{NS_WSNT}}}Message")
    onvif_msg = SubElement(message_el, f"{{{NS_ONVIF_EVENT}}}Message")
    onvif_msg.set("UtcTime", datetime.now(tz=UTC).isoformat())

    source = SubElement(onvif_msg, f"{{{NS_ONVIF_EVENT}}}Source")
    source_item = SubElement(source, f"{{{NS_ONVIF_EVENT}}}SimpleItem")
    source_item.set("Name", "VideoSourceConfigurationToken")
    source_item.set("Value", camera_id)

    data = SubElement(onvif_msg, f"{{{NS_ONVIF_EVENT}}}Data")
    data_item = SubElement(data, f"{{{NS_ONVIF_EVENT}}}SimpleItem")
    data_item.set("Name", "IsMotion")
    data_item.set("Value", "true" if is_motion else "false")

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(envelope, encoding="unicode", xml_declaration=False)


def parse_subscribe_request(body: str) -> dict[str, Any]:
    """Extract callback URL and initial TTL from a Subscribe SOAP request."""
    result: dict[str, Any] = {}

    try:
        root = fromstring(body)
    except Exception:
        return result

    for addr_el in root.iter():
        if not addr_el.tag.endswith("}Address") and addr_el.tag != "Address":
            continue
        parent = _find_parent(root, addr_el)
        if (
            parent is not None
            and (parent.tag.endswith("}ConsumerReference") or parent.tag == "ConsumerReference")
            and addr_el.text
            and addr_el.text.strip().startswith("http")
        ):
            result["callback_url"] = addr_el.text.strip()
            break

    for el in root.iter():
        if el.tag.endswith("}InitialTerminationTime") or el.tag == "InitialTerminationTime":
            if el.text:
                result["ttl"] = _parse_iso8601_duration(el.text.strip())
            break

    return result


def _find_parent(root: Element, target: Element) -> Element | None:
    for parent in root.iter():
        if target in list(parent):
            return parent
    return None


_DURATION_PATTERN = re.compile(
    r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
)


def _parse_iso8601_duration(value: str) -> timedelta | None:
    match = _DURATION_PATTERN.search(value)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    if hours == 0 and minutes == 0 and seconds == 0:
        return None
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def _is_safe_callback_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (addr.is_loopback or addr.is_link_local or addr.is_reserved)


def build_subscribe_response(subscription: Subscription, host: str, port: int) -> str:
    envelope = Element(f"{{{NS_SOAP}}}Envelope")
    envelope.set("xmlns:s", NS_SOAP)
    envelope.set("xmlns:wsnt", NS_WSNT)

    header = SubElement(envelope, f"{{{NS_SOAP}}}Header")
    action = SubElement(header, f"{{{NS_WSA}}}Action")
    action.text = f"{NS_WSNT}/SubscribeResponse"

    body = SubElement(envelope, f"{{{NS_SOAP}}}Body")
    resp = SubElement(body, f"{{{NS_WSNT}}}SubscribeResponse")

    ref = SubElement(resp, f"{{{NS_WSNT}}}SubscriptionReference")
    addr = SubElement(ref, f"{{{NS_WSA}}}Address")
    addr.text = f"http://{host}:{port}/onvif/event_service/subscription/{subscription.id}"

    term_time = SubElement(resp, f"{{{NS_WSNT}}}CurrentTime")
    term_time.text = datetime.now(tz=UTC).isoformat()
    expires = SubElement(resp, f"{{{NS_WSNT}}}TerminationTime")
    expires.text = subscription.expires_at.isoformat()

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(envelope, encoding="unicode", xml_declaration=False)
