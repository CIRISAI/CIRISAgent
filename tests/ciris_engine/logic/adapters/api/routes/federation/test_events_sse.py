"""Tests for ``/v1/federation/events/{channel}`` — SSE event-stream surface.

Covers:
- Unknown channel returns 400 with the valid-channel list.
- Edge unavailable returns 503.
- Happy-path single event: subscribe, emit one event, receive one
  ``federation_event`` SSE frame with a well-formed envelope.
- Channel multiplexing: each channel name dispatches to the
  corresponding ``subscribe_*`` method on Edge.
- Heartbeat: idle stream emits SSE comment heartbeat after the
  configured interval.
- Cleanup: client disconnect cancels the producer and unsubscribes
  the handle.
- ``Last-Event-ID`` header surfaces a ``resume-notice`` event.
- Backpressure: queue-overflow drops oldest, newest survives.
- ``NetworkEvent`` projection: bytes accessors hex-encoded; missing
  fields elided; ``kind`` becomes ``event_type``.
- ``subscribe_feed`` dict projection: ``message_type`` becomes
  ``event_type``.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import require_observer
from ciris_engine.logic.adapters.api.routes.federation import events as events_mod
from ciris_engine.logic.adapters.api.routes.federation.events import router as events_router
from ciris_engine.logic.adapters.api.sse import federation_sse_bridge as bridge_mod
from ciris_engine.schemas.runtime.federation_events import (
    CHANNEL_ALL,
    CHANNEL_ANNOUNCES,
    CHANNEL_FEED,
    CHANNEL_INTERFACE_EVENTS,
    CHANNEL_LINK_EVENTS,
    CHANNEL_PATH_EVENTS,
    CHANNEL_RESOURCE_EVENTS,
    VALID_CHANNELS,
    FederationEventEnvelope,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #


class FakeNetworkEvent:
    """Mimic Edge's NetworkEvent PyObject surface."""

    def __init__(
        self,
        *,
        kind: str,
        at: str = "2026-05-30T12:00:00Z",
        message: str = "test event",
        severity: str = "info",
        peer_key_id: Optional[str] = None,
        transport_id: Optional[str] = None,
        identity_hash: Optional[bytes] = None,
        link_id: Optional[bytes] = None,
    ) -> None:
        self.kind = kind
        self.at = at
        self.message = message
        self.severity = severity
        self.peer_key_id = peer_key_id
        self.transport_id = transport_id
        self.aspect = None
        self.rssi_dbm = None
        self.snr_db = None
        self.lagged_count = None
        self._identity_hash = identity_hash
        self._app_data = None
        self._link_id = link_id

    def identity_hash(self) -> Optional[bytes]:
        return self._identity_hash

    def app_data(self) -> Optional[bytes]:
        return self._app_data

    def link_id(self) -> Optional[bytes]:
        return self._link_id


class FakeSubscriptionHandle:
    """Mimic Edge's ``NetworkEventSubscription`` / ``VerifiedFeedSubscription``.

    Implements ``__aiter__`` / ``__anext__`` plus ``unsubscribe``. Tests
    push events via ``push()``; ``close()`` raises ``StopAsyncIteration``
    on the next ``__anext__``.

    We avoid ``asyncio.Queue`` here because the TestClient runs the
    request handler in a separate thread / event loop, and ``Queue``
    is bound to its construction loop. Use a thread-safe list + an
    asyncio.Event keyed off the consumer's loop on first ``__anext__``.
    """

    def __init__(self) -> None:
        self._items: list[Any] = []
        self._closed = False
        self.unsubscribe_called = False
        # Lazily-initialized in the consumer's loop.
        self._event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def push(self, event: Any) -> None:
        self._items.append(event)
        self._signal()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._signal()

    def unsubscribe(self) -> None:
        self.unsubscribe_called = True
        self.close()

    def _signal(self) -> None:
        # If the consumer hasn't started iterating yet, just leave the
        # items in the list — they'll be picked up on first __anext__.
        if self._event is None or self._loop is None:
            return
        if self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._event.set)

    def __aiter__(self) -> "FakeSubscriptionHandle":
        return self

    async def __anext__(self) -> Any:
        if self._event is None:
            self._event = asyncio.Event()
            self._loop = asyncio.get_running_loop()
            # If items were pushed before iteration started, signal now.
            if self._items or self._closed:
                self._event.set()
        while True:
            if self._items:
                return self._items.pop(0)
            if self._closed:
                raise StopAsyncIteration
            self._event.clear()
            await self._event.wait()


class FakeEdgeWithStreams:
    """Edge double that hands out FakeSubscriptionHandle per channel."""

    def __init__(self) -> None:
        self.handles: Dict[str, FakeSubscriptionHandle] = {}

    def _get(self, channel: str) -> FakeSubscriptionHandle:
        if channel not in self.handles:
            self.handles[channel] = FakeSubscriptionHandle()
        return self.handles[channel]

    def subscribe_announces(self) -> FakeSubscriptionHandle:
        return self._get(CHANNEL_ANNOUNCES)

    def subscribe_feed(self) -> FakeSubscriptionHandle:
        return self._get(CHANNEL_FEED)

    def subscribe_interface_events(self) -> FakeSubscriptionHandle:
        return self._get(CHANNEL_INTERFACE_EVENTS)

    def subscribe_link_events(self) -> FakeSubscriptionHandle:
        return self._get(CHANNEL_LINK_EVENTS)

    def subscribe_path_events(self) -> FakeSubscriptionHandle:
        return self._get(CHANNEL_PATH_EVENTS)

    def subscribe_resource_events(self) -> FakeSubscriptionHandle:
        return self._get(CHANNEL_RESOURCE_EVENTS)

    def subscribe_all(self) -> FakeSubscriptionHandle:
        return self._get(CHANNEL_ALL)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _observer_auth() -> object:
    return MagicMock(user_id="obs", role="OBSERVER")


@pytest.fixture
def fake_edge() -> FakeEdgeWithStreams:
    return FakeEdgeWithStreams()


@pytest.fixture
def make_app(monkeypatch, fake_edge):
    """Build a TestClient with the events router and edge_runtime patched.

    ``edge_available`` lets tests force the 503 path.
    """

    def _factory(*, edge_available: bool = True) -> TestClient:
        monkeypatch.setattr(events_mod.edge_runtime, "is_available", lambda: edge_available)
        if edge_available:
            monkeypatch.setattr(events_mod.edge_runtime, "get_edge", lambda: fake_edge)
        else:

            def _raise() -> Any:
                raise RuntimeError("Edge runtime not initialized.")

            monkeypatch.setattr(events_mod.edge_runtime, "get_edge", _raise)
        app = FastAPI()
        app.include_router(events_router, prefix="/v1/federation")
        app.dependency_overrides[require_observer] = _observer_auth
        return TestClient(app)

    return _factory


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _parse_sse_frames(text: str) -> List[Dict[str, Any]]:
    """Parse a buffer of SSE frames into [{event, data, comment?, id?}]."""
    frames: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    for line in text.split("\n"):
        if line == "":
            if current:
                frames.append(current)
                current = {}
            continue
        if line.startswith(":"):
            current.setdefault("comments", []).append(line[1:].strip())
            continue
        if line.startswith("event: "):
            current["event"] = line[len("event: ") :]
        elif line.startswith("data: "):
            current["data"] = line[len("data: ") :]
        elif line.startswith("id: "):
            current["id"] = line[len("id: ") :]
    if current:
        frames.append(current)
    return frames


# --------------------------------------------------------------------------- #
# 400 / 503 paths
# --------------------------------------------------------------------------- #


class TestEnvelopeValidation:
    def test_unknown_channel_returns_400(self, make_app):
        client = make_app()
        resp = client.get("/v1/federation/events/not-a-channel")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "UNKNOWN_CHANNEL"
        assert "not-a-channel" in body["detail"]
        # All seven canonical channels are echoed back.
        assert set(body["valid_channels"]) == set(VALID_CHANNELS)

    def test_edge_unavailable_returns_503(self, make_app):
        client = make_app(edge_available=False)
        resp = client.get("/v1/federation/events/announces")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "EDGE_UNAVAILABLE"


# --------------------------------------------------------------------------- #
# Happy paths
# --------------------------------------------------------------------------- #


class TestSinglEvent:
    def test_single_announce_event_round_trip(self, make_app, fake_edge):
        client = make_app()

        # Push one event then close so the stream terminates.
        sub = fake_edge._get(CHANNEL_ANNOUNCES)
        sub.push(
            FakeNetworkEvent(
                kind="announce_received",
                peer_key_id="agent-bob",
                transport_id="reticulum-rs",
                identity_hash=bytes.fromhex("00112233445566778899aabbccddeeff"),
            )
        )
        sub.close()

        with client.stream("GET", "/v1/federation/events/announces") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = "".join(resp.iter_text())

        frames = _parse_sse_frames(body)
        events_by_name = {f.get("event"): f for f in frames if "event" in f}

        # connected ack
        assert "connected" in events_by_name
        connected = json.loads(events_by_name["connected"]["data"])
        assert connected["channel"] == CHANNEL_ANNOUNCES

        # federation_event with our envelope
        assert "federation_event" in events_by_name
        envelope_dict = json.loads(events_by_name["federation_event"]["data"])
        envelope = FederationEventEnvelope.model_validate(envelope_dict)
        assert envelope.channel == CHANNEL_ANNOUNCES
        assert envelope.event_type == "announce_received"
        assert envelope.payload["kind"] == "announce_received"
        assert envelope.payload["peer_key_id"] == "agent-bob"
        # bytes accessor hex-encoded
        assert envelope.payload["identity_hash"] == "00112233445566778899aabbccddeeff"

        # event id surfaces on the SSE id: line for Last-Event-ID resume
        assert events_by_name["federation_event"].get("id") == envelope.event_id

    def test_feed_channel_uses_message_type_as_event_type(self, make_app, fake_edge):
        client = make_app()

        sub = fake_edge._get(CHANNEL_FEED)
        # subscribe_feed yields dicts (per Edge docstring).
        sub.push(
            {
                "message_type": "InlineText",
                "signing_key_id": "agent-bob",
                "destination_key_id": "agent-self",
                "body_sha256_prefix": "abc12345",
                "transport_id": "reticulum-rs",
                "received_at_ms": 1748392832000,
            }
        )
        sub.close()

        with client.stream("GET", "/v1/federation/events/feed") as resp:
            body = "".join(resp.iter_text())

        frames = _parse_sse_frames(body)
        fed_event = next(f for f in frames if f.get("event") == "federation_event")
        envelope = FederationEventEnvelope.model_validate(json.loads(fed_event["data"]))
        assert envelope.channel == CHANNEL_FEED
        assert envelope.event_type == "InlineText"
        assert envelope.payload["signing_key_id"] == "agent-bob"
        assert envelope.payload["body_sha256_prefix"] == "abc12345"


# --------------------------------------------------------------------------- #
# Channel multiplexing
# --------------------------------------------------------------------------- #


class TestChannelMultiplexing:
    @pytest.mark.parametrize(
        "channel,subscribe_method",
        [
            (CHANNEL_ANNOUNCES, "subscribe_announces"),
            (CHANNEL_FEED, "subscribe_feed"),
            (CHANNEL_INTERFACE_EVENTS, "subscribe_interface_events"),
            (CHANNEL_LINK_EVENTS, "subscribe_link_events"),
            (CHANNEL_PATH_EVENTS, "subscribe_path_events"),
            (CHANNEL_RESOURCE_EVENTS, "subscribe_resource_events"),
            (CHANNEL_ALL, "subscribe_all"),
        ],
    )
    def test_channel_dispatches_to_right_subscribe_method(
        self, make_app, fake_edge, channel, subscribe_method
    ):
        client = make_app()

        # Spy on the chosen subscribe method.
        original = getattr(fake_edge, subscribe_method)
        called: List[bool] = []

        def _spy() -> Any:
            called.append(True)
            handle = original()
            handle.close()  # terminate immediately
            return handle

        setattr(fake_edge, subscribe_method, _spy)

        with client.stream("GET", f"/v1/federation/events/{channel}") as resp:
            list(resp.iter_text())

        assert called == [True], (
            f"channel={channel} should have dispatched to {subscribe_method}"
        )


# --------------------------------------------------------------------------- #
# Last-Event-ID resume-notice
# --------------------------------------------------------------------------- #


class TestResumeNotice:
    def test_last_event_id_header_produces_resume_notice(self, make_app, fake_edge):
        client = make_app()

        sub = fake_edge._get(CHANNEL_ANNOUNCES)
        sub.close()

        with client.stream(
            "GET",
            "/v1/federation/events/announces",
            headers={"Last-Event-ID": "prev-uuid-1234"},
        ) as resp:
            body = "".join(resp.iter_text())

        frames = _parse_sse_frames(body)
        events_by_name = {f.get("event"): f for f in frames if "event" in f}
        assert "resume-notice" in events_by_name
        notice = json.loads(events_by_name["resume-notice"]["data"])
        assert notice["requested_last_event_id"] == "prev-uuid-1234"
        assert notice["replay_supported"] is False

    def test_no_last_event_id_no_resume_notice(self, make_app, fake_edge):
        client = make_app()
        sub = fake_edge._get(CHANNEL_ANNOUNCES)
        sub.close()

        with client.stream("GET", "/v1/federation/events/announces") as resp:
            body = "".join(resp.iter_text())

        frames = _parse_sse_frames(body)
        events_by_name = {f.get("event"): f for f in frames if "event" in f}
        assert "resume-notice" not in events_by_name


# --------------------------------------------------------------------------- #
# Heartbeat on idle
# --------------------------------------------------------------------------- #


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_fires_on_idle(self, monkeypatch):
        """Idle queue triggers an SSE comment heartbeat.

        Drives the generator directly (not via TestClient) so we can
        shrink the heartbeat interval to make the test fast.
        """
        # Shrink heartbeat interval to 50ms so the test stays fast.
        monkeypatch.setattr(bridge_mod, "HEARTBEAT_INTERVAL_SECONDS", 0.05)

        edge = FakeEdgeWithStreams()
        # Don't push any event. Close subscription only after we collect
        # a heartbeat.
        gen = bridge_mod.stream_federation_channel(edge, CHANNEL_ANNOUNCES)

        connected = await gen.__anext__()
        assert connected.startswith("id:") or connected.startswith("event: connected")

        # Next yield should be a heartbeat comment.
        heartbeat = await gen.__anext__()
        assert heartbeat.startswith(":") and "heartbeat" in heartbeat

        # Cleanup: close the gen so the producer task cancellation runs.
        await gen.aclose()


# --------------------------------------------------------------------------- #
# Cleanup on client disconnect
# --------------------------------------------------------------------------- #


class TestCleanupOnDisconnect:
    @pytest.mark.asyncio
    async def test_gen_aclose_unsubscribes_handle(self, monkeypatch):
        """When the SSE generator is closed mid-stream, the Edge handle
        is unsubscribed and the producer task is cancelled."""
        monkeypatch.setattr(bridge_mod, "HEARTBEAT_INTERVAL_SECONDS", 0.05)

        edge = FakeEdgeWithStreams()
        sub = edge._get(CHANNEL_ANNOUNCES)
        # Do NOT call sub.close() — we want the stream to be live when
        # we close the generator.

        gen = bridge_mod.stream_federation_channel(edge, CHANNEL_ANNOUNCES)
        # Drain the connected ack
        await gen.__anext__()

        # Close the generator mid-stream
        await gen.aclose()

        # Yield once to let the cleanup tasks complete
        await asyncio.sleep(0.05)

        assert sub.unsubscribe_called, "Edge subscription handle should be unsubscribed"


# --------------------------------------------------------------------------- #
# Backpressure
# --------------------------------------------------------------------------- #


class TestBackpressure:
    @pytest.mark.asyncio
    async def test_overflow_drops_oldest(self, monkeypatch):
        """Producer-side queue overflow drops the OLDEST event (FIFO front)."""
        # Shrink queue to 2 so we can test overflow in 4 pushes.
        monkeypatch.setattr(bridge_mod, "QUEUE_MAXSIZE", 2)
        monkeypatch.setattr(bridge_mod, "HEARTBEAT_INTERVAL_SECONDS", 5.0)

        edge = FakeEdgeWithStreams()
        sub = edge._get(CHANNEL_ANNOUNCES)
        for i in range(4):
            sub.push(FakeNetworkEvent(kind="announce_received", message=f"evt-{i}"))
        sub.close()

        gen = bridge_mod.stream_federation_channel(edge, CHANNEL_ANNOUNCES)
        frames: List[str] = []
        try:
            async for frame in gen:
                frames.append(frame)
        finally:
            await gen.aclose()

        # Collect the messages that survived. Order: connected ack +
        # surviving federation_events.
        kept_messages = []
        for frame in frames:
            if "federation_event" in frame:
                # Parse the JSON data line
                for line in frame.split("\n"):
                    if line.startswith("data: "):
                        payload = json.loads(line[len("data: "):])
                        kept_messages.append(payload["payload"]["message"])

        # Newest (evt-2, evt-3) survives. evt-0 and evt-1 dropped.
        assert "evt-3" in kept_messages
        assert "evt-2" in kept_messages
        assert "evt-0" not in kept_messages


# --------------------------------------------------------------------------- #
# NetworkEvent projection
# --------------------------------------------------------------------------- #


class TestNetworkEventProjection:
    def test_missing_fields_elided(self):
        event = FakeNetworkEvent(kind="transport_up", peer_key_id=None, transport_id="reticulum-rs")
        projection = bridge_mod._network_event_to_dict(event)
        assert "peer_key_id" not in projection  # None values dropped
        assert projection["transport_id"] == "reticulum-rs"
        assert projection["kind"] == "transport_up"

    def test_bytes_accessors_hex_encoded(self):
        event = FakeNetworkEvent(
            kind="link_established",
            link_id=bytes(range(16)),
        )
        projection = bridge_mod._network_event_to_dict(event)
        assert projection["link_id"] == "000102030405060708090a0b0c0d0e0f"

    def test_dict_passthrough_for_feed(self):
        feed_event = {
            "message_type": "InlineText",
            "signing_key_id": "agent-x",
            "body_sha256_prefix": "deadbeef",
        }
        projection = bridge_mod._project_event(CHANNEL_FEED, feed_event)
        # Pass-through copy (not the same dict)
        assert projection == feed_event
        assert projection is not feed_event
