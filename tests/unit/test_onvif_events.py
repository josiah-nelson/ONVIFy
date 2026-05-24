"""Tests for ONVIF event subscription and notification."""

from __future__ import annotations

from datetime import timedelta
from xml.etree.ElementTree import fromstring

import pytest

from onvify.services.onvif_events import (
    ONVIFEventManager,
    Subscription,
    _build_motion_notify,
    build_subscribe_response,
    parse_subscribe_request,
)

NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_WSNT = "http://docs.oasis-open.org/wsn/b-2"
NS_ONVIF_EVENT = "http://www.onvif.org/ver10/schema"


class TestSubscription:
    def test_not_expired_by_default(self) -> None:
        sub = Subscription(callback_url="http://nvr/callback", camera_id="cam-1")
        assert sub.is_expired is False

    def test_expired_with_past_ttl(self) -> None:
        sub = Subscription(callback_url="http://nvr/callback", camera_id="cam-1")
        sub.expires_at = sub.expires_at - timedelta(hours=2)
        assert sub.is_expired is True


@pytest.mark.asyncio
class TestONVIFEventManager:
    async def test_subscribe_and_list(self) -> None:
        mgr = ONVIFEventManager()
        sub = mgr.subscribe("http://nvr:8080/events", "cam-1")
        assert sub.callback_url == "http://nvr:8080/events"
        assert mgr.get_subscriptions("cam-1") == [sub]
        assert mgr.get_subscriptions("cam-2") == []

    async def test_unsubscribe(self) -> None:
        mgr = ONVIFEventManager()
        sub = mgr.subscribe("http://nvr:8080/events", "cam-1")
        assert mgr.unsubscribe(sub.id) is True
        assert mgr.get_subscriptions("cam-1") == []

    async def test_unsubscribe_unknown(self) -> None:
        mgr = ONVIFEventManager()
        assert mgr.unsubscribe("nonexistent") is False

    async def test_renew_extends_expiry(self) -> None:
        mgr = ONVIFEventManager()
        sub = mgr.subscribe("http://nvr:8080/events", "cam-1")
        original_expiry = sub.expires_at
        renewed = mgr.renew(sub.id, ttl=timedelta(hours=2))
        assert renewed is not None
        assert renewed.expires_at > original_expiry

    async def test_renew_unknown_returns_none(self) -> None:
        mgr = ONVIFEventManager()
        assert mgr.renew("nonexistent") is None

    async def test_expired_subscriptions_purged(self) -> None:
        mgr = ONVIFEventManager()
        sub = mgr.subscribe("http://nvr:8080/events", "cam-1")
        sub.expires_at = sub.expires_at - timedelta(hours=2)
        assert mgr.get_subscriptions("cam-1") == []

    async def test_notify_motion_no_subscribers(self) -> None:
        mgr = ONVIFEventManager()
        await mgr.start()
        await mgr.notify_motion("cam-1")
        await mgr.stop()


class TestBuildMotionNotify:
    def test_contains_motion_topic_and_data(self) -> None:
        xml = _build_motion_notify("cam-123", is_motion=True)
        root = fromstring(xml)
        body = root.find(f"{{{NS_SOAP}}}Body")
        assert body is not None
        notify = body.find(f"{{{NS_WSNT}}}Notify")
        assert notify is not None
        assert "Motion" in xml
        assert 'Value="true"' in xml

    def test_motion_false(self) -> None:
        xml = _build_motion_notify("cam-123", is_motion=False)
        assert 'Value="false"' in xml

    def test_contains_camera_id(self) -> None:
        xml = _build_motion_notify("cam-abc", is_motion=True)
        assert "cam-abc" in xml


class TestParseSubscribeRequest:
    def test_extracts_callback_url(self) -> None:
        body = """
        <wsnt:Subscribe>
            <wsnt:ConsumerReference>
                <wsa:Address>http://192.168.1.50:8080/onvif_events</wsa:Address>
            </wsnt:ConsumerReference>
        </wsnt:Subscribe>
        """
        result = parse_subscribe_request(body)
        assert result["callback_url"] == "http://192.168.1.50:8080/onvif_events"

    def test_extracts_ttl(self) -> None:
        body = """
        <wsnt:Subscribe>
            <wsnt:InitialTerminationTime>PT3600S</wsnt:InitialTerminationTime>
        </wsnt:Subscribe>
        """
        result = parse_subscribe_request(body)
        assert result["ttl_raw"] == "PT3600S"

    def test_handles_missing_fields(self) -> None:
        result = parse_subscribe_request("<wsnt:Subscribe></wsnt:Subscribe>")
        assert "callback_url" not in result


class TestBuildSubscribeResponse:
    def test_contains_subscription_reference(self) -> None:
        sub = Subscription(id="sub-001", callback_url="http://nvr/cb", camera_id="cam-1")
        xml = build_subscribe_response(sub, "192.168.1.100", 8001)
        root = fromstring(xml)
        assert "sub-001" in xml
        assert "SubscribeResponse" in xml
        body = root.find(f"{{{NS_SOAP}}}Body")
        assert body is not None
