"""
Federation SSE bridge — wraps an Edge ``subscribe_*`` async iterator in
a Server-Sent Events generator.

This module is intentionally route-agnostic: it knows nothing about
FastAPI ``Request`` objects or auth contexts. The route handler does
auth + channel-name validation and then hands off to
``stream_federation_channel`` which produces the SSE frame bytes.

Design contract
---------------

Producer/consumer split
    Edge yields events as fast as its broadcast bus dispatches; mobile
    clients on flaky cellular read as fast as their carrier permits.
    A producer task drains the Edge async-iterator into a bounded
    ``asyncio.Queue`` (maxsize=512). On overflow we DROP OLDEST — the
    SSE stream is for live-status UI surfaces (NetworkAnnouncesScreen,
    NetworkPathsScreen, NetworkDiagnosticsScreen). Mobile clients want
    "what's happening NOW", not a perfect replay of every event since
    the connection started. Backpressure that stalls the producer
    would block Edge's broadcast bus for every other consumer too.

Heartbeat
    Every 30 seconds of idle on the queue, the generator emits an SSE
    comment line (``: heartbeat\\n\\n``). This:
      - Keeps mobile carriers from idle-killing the TCP connection.
      - Lets the client detect a server-side hang (no heartbeat for
        > 60s => reconnect).
    SSE comment lines are ignored by EventSource clients, so they do
    not surface in the event stream.

Last-Event-ID / replay
    Edge ``subscribe_*`` channels do not support replay — they hand
    out a broadcast::Receiver that starts at the current bus head.
    We honor the ``Last-Event-ID`` header for OBSERVABILITY only:
    the generator emits a one-shot ``resume-notice`` SSE event on
    connect telling the client "you asked for X, we cannot replay,
    starting from live tail". The client decides what to do (e.g.
    flush its cache and re-fetch a snapshot from a non-streaming
    endpoint).

Cleanup
    The generator wraps the producer task in try/finally and on exit
    cancels the producer, drains the queue, and (best effort) calls
    ``.unsubscribe()`` on the Edge handle. Mobile clients close
    connections aggressively (app backgrounded, network swap, etc.)
    so cleanup MUST be deterministic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Final, Optional

from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log
from ciris_engine.schemas.runtime.federation_events import (
    CHANNEL_ANNOUNCES,
    CHANNEL_FEED,
    CHANNEL_INTERFACE_EVENTS,
    CHANNEL_LINK_EVENTS,
    CHANNEL_PATH_EVENTS,
    CHANNEL_RESOURCE_EVENTS,
    FederationEventEnvelope,
)

logger = logging.getLogger(__name__)

# Bounded queue size. 512 was chosen to match the reasoning-stream
# bridge's ratio of "well above expected steady-state, low enough that
# a stuck consumer doesn't OOM the process". One announce per second
# steady state means the mobile client would have to be wedged for
# ~8.5 minutes to overflow. At that point dropping oldest is correct.
QUEUE_MAXSIZE: Final[int] = 512

# Idle heartbeat cadence. 30s matches the reasoning-stream cadence and
# is well under mobile-carrier idle-kill timers (60-120s typical).
HEARTBEAT_INTERVAL_SECONDS: Final[float] = 30.0


# A factory mapping channel name -> coroutine returning an Edge
# subscription handle. Pulled out for testability — production wires
# it to ``ciris_edge.Edge``; tests wire it to a stub.
SubscriptionFactory = Callable[[Any, str], Awaitable[Any]]


def _network_event_to_dict(event: Any) -> Dict[str, Any]:
    """Project an Edge ``NetworkEvent`` PyObject into a JSON-safe dict.

    Edge 1.0 returns ``NetworkEvent`` instances for every channel
    except ``feed``. Each instance exposes ``kind`` / ``at`` /
    ``message`` / ``severity`` plus optional fields conditional on
    ``kind`` (``peer_key_id`` / ``transport_id`` / ``aspect`` /
    ``rssi_dbm`` / ``snr_db`` / ``lagged_count``) and three bytes
    accessors (``identity_hash()`` / ``app_data()`` / ``link_id()``).

    We hex-encode the bytes accessors so the JSON payload is wire-safe.
    Any AttributeError on a missing field is swallowed — the projection
    is forward-compatible with Edge adding new optional fields.
    """
    projection: Dict[str, Any] = {}

    for scalar_attr in (
        "at",
        "kind",
        "message",
        "severity",
        "peer_key_id",
        "transport_id",
        "aspect",
        "rssi_dbm",
        "snr_db",
        "lagged_count",
    ):
        try:
            value = getattr(event, scalar_attr, None)
            if value is not None:
                projection[scalar_attr] = value
        except Exception:  # pragma: no cover — defensive against Edge surface drift
            continue

    for bytes_method in ("identity_hash", "app_data", "link_id"):
        try:
            accessor = getattr(event, bytes_method, None)
            if accessor is None:
                continue
            raw = accessor() if callable(accessor) else accessor
            if raw is not None:
                projection[bytes_method] = raw.hex() if isinstance(raw, (bytes, bytearray)) else raw
        except Exception:  # pragma: no cover
            continue

    return projection


def _extract_event_type(channel: str, event: Any, payload: Dict[str, Any]) -> str:
    """Resolve the ``event_type`` discriminator for the envelope.

    For ``feed``, Edge's docstring guarantees ``message_type`` in the
    dict projection. For every other channel the projection includes
    ``kind`` from the ``NetworkEvent``. Fall back to "unknown" so we
    never emit a malformed envelope.
    """
    if channel == CHANNEL_FEED:
        message_type = payload.get("message_type")
        if isinstance(message_type, str):
            return message_type
        return "unknown"

    kind = payload.get("kind")
    if isinstance(kind, str):
        return kind
    return "unknown"


def _project_event(channel: str, event: Any) -> Dict[str, Any]:
    """Project a raw Edge event into a JSON-safe dict payload.

    ``subscribe_feed`` already yields a dict; pass it through. Every
    other channel yields a ``NetworkEvent`` PyObject — project via
    field-walk.
    """
    if isinstance(event, dict):
        # ``subscribe_feed`` documented shape.
        return dict(event)
    return _network_event_to_dict(event)


def _format_sse_event(event_name: str, data: Dict[str, Any], event_id: Optional[str] = None) -> str:
    """Serialize one SSE frame.

    Per the SSE wire format: optional ``id:`` line (used by browsers
    on reconnect via ``Last-Event-ID`` header), ``event:`` discriminator,
    ``data:`` payload (JSON), terminated by a blank line.
    """
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_name}")
    lines.append(f"data: {json.dumps(data, default=str)}")
    return "\n".join(lines) + "\n\n"


def _format_sse_comment(text: str) -> str:
    """Serialize an SSE comment line. EventSource clients ignore these."""
    return f": {text}\n\n"


async def _drain_subscription_into_queue(
    subscription: AsyncIterator[Any],
    queue: "asyncio.Queue[Any]",
    channel: str,
) -> None:
    """Producer: pull events off the Edge async iterator into the queue.

    On overflow, drop oldest (discard ``queue.get_nowait()`` then put).
    This is the inverse of an unbounded queue — we cap memory and bias
    toward fresh state for the mobile UI.
    """
    try:
        async for event in subscription:
            if queue.full():
                try:
                    queue.get_nowait()  # drop oldest
                    queue.task_done()
                except asyncio.QueueEmpty:  # pragma: no cover — race-only
                    pass
                logger.debug("federation SSE: queue overflow on channel=%s, dropped oldest", channel)
            await queue.put(event)
        # Subscription drained cleanly — signal stream end.
        await queue.put(_PRODUCER_END)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # pragma: no cover — surface Edge errors as terminal
        logger.warning("federation SSE: producer error on channel=%s: %s", sanitize_for_log(channel), exc)
        # Sentinel — generator translates this into a terminal SSE error frame
        await queue.put(_ProducerError(exc))


class _ProducerError:
    """Sentinel marking a fatal producer-side error.

    The consumer generator looks for ``isinstance(item, _ProducerError)``
    and emits a terminal ``error`` SSE frame, then exits.
    """

    __slots__ = ("exc",)

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


class _ProducerEnd:
    """Sentinel marking clean producer termination.

    Edge's broadcast::Receiver raises StopAsyncIteration when the
    sender side drops. In production this only happens at Edge shutdown;
    in tests it lets us terminate the stream cleanly. The consumer
    yields a terminal ``stream-closed`` SSE event and exits.
    """

    __slots__ = ()


_PRODUCER_END = _ProducerEnd()


async def _close_subscription(subscription: Any) -> None:
    """Best-effort close of an Edge subscription handle.

    ``SubscriptionHandle`` exposes a sync ``unsubscribe()``. Async
    iterators in Edge land own their broadcast::Receiver; dropping the
    Python ref is the documented cleanup path. We belt-and-suspenders
    both — call ``unsubscribe()`` if present, then let GC drop the
    receiver.
    """
    unsubscribe = getattr(subscription, "unsubscribe", None)
    if unsubscribe is None:
        return
    try:
        result = unsubscribe()
        if asyncio.iscoroutine(result):
            await result
    except Exception as exc:  # pragma: no cover — Edge surface drift
        logger.debug("federation SSE: subscription unsubscribe failed (non-fatal): %s", exc)


async def stream_federation_channel(
    edge: Any,
    channel: str,
    *,
    subscription_factory: Optional[SubscriptionFactory] = None,
    last_event_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """Async generator producing SSE frame strings for one channel.

    Args:
        edge: the live Edge instance (``ciris_edge.Edge``). Must expose
            the ``subscribe_<channel>`` async-iterator factory methods.
        channel: validated channel name (caller is responsible for
            rejecting unknown channels with 400 before calling us).
        subscription_factory: override for testing. Production passes
            ``None`` and the default ``_default_subscription_factory``
            dispatches on channel name.
        last_event_id: optional ``Last-Event-ID`` header value.
            Surfaced in the ``resume-notice`` event so the client
            knows replay isn't supported.

    Yields:
        Pre-encoded SSE frame strings. The caller wraps in
        ``StreamingResponse(media_type="text/event-stream")``.

    Lifecycle:
        - On connect: yields a ``connected`` event (and a
          ``resume-notice`` event if ``last_event_id`` was given).
        - During steady state: yields one ``federation_event`` per
          Edge emission and one heartbeat per 30s of idle.
        - On producer error: yields one terminal ``error`` event.
        - On client disconnect (``GeneratorExit`` from FastAPI): the
          finally block cancels the producer and unsubscribes.
    """
    factory = subscription_factory or _default_subscription_factory

    queue: "asyncio.Queue[Any]" = asyncio.Queue(maxsize=QUEUE_MAXSIZE)

    subscription: Any = None
    producer_task: Optional[asyncio.Task[None]] = None

    try:
        try:
            subscription = await factory(edge, channel)
        except Exception as exc:
            # Log full exception detail server-side; surface ONLY the
            # channel name to the client. CodeQL flagged interpolating
            # `{exc}` into the SSE frame as information exposure
            # (CIRISAgent#841 review) — raw exception strings can leak
            # stack frames, file paths, or Edge-side state to OBSERVER
            # callers. The channel name is already user-supplied, so
            # echoing it costs nothing.
            logger.warning("federation SSE: subscription factory failed for channel=%s: %s", sanitize_for_log(channel), exc)
            yield _format_sse_event(
                "error",
                {
                    "error": "EDGE_SUBSCRIPTION_FAILED",
                    "detail": f"Edge rejected subscribe_{channel} — see server logs",
                },
            )
            return

        producer_task = asyncio.create_task(
            _drain_subscription_into_queue(subscription, queue, channel),
            name=f"federation-sse-producer-{channel}",
        )

        yield _format_sse_event(
            "connected",
            {
                "status": "connected",
                "channel": channel,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        if last_event_id:
            yield _format_sse_event(
                "resume-notice",
                {
                    "requested_last_event_id": last_event_id,
                    "replay_supported": False,
                    "detail": (
                        "Edge subscription channels do not support replay; "
                        "starting from live tail. Client should resync any "
                        "cached snapshot via a non-streaming endpoint."
                    ),
                },
            )

        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                yield _format_sse_comment("heartbeat")
                continue

            if isinstance(item, _ProducerError):
                yield _format_sse_event(
                    "error",
                    {
                        "error": "EDGE_PRODUCER_ERROR",
                        "detail": str(item.exc),
                    },
                )
                return

            if isinstance(item, _ProducerEnd):
                yield _format_sse_event(
                    "stream-closed",
                    {
                        "channel": channel,
                        "reason": "edge_subscription_drained",
                    },
                )
                return

            try:
                payload = _project_event(channel, item)
                envelope = FederationEventEnvelope(
                    event_id=str(uuid.uuid4()),
                    channel=channel,
                    timestamp=datetime.now(timezone.utc),
                    event_type=_extract_event_type(channel, item, payload),
                    payload=payload,
                )
                yield _format_sse_event(
                    "federation_event",
                    envelope.model_dump(mode="json"),
                    event_id=envelope.event_id,
                )
            except Exception as exc:  # pragma: no cover — project_event is defensive
                logger.warning(
                    "federation SSE: projection failed on channel=%s: %s", sanitize_for_log(channel), exc
                )
                yield _format_sse_event(
                    "error",
                    {
                        "error": "EVENT_PROJECTION_FAILED",
                        "detail": str(exc),
                    },
                )
    finally:
        if producer_task is not None and not producer_task.done():
            producer_task.cancel()
            try:
                await producer_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if subscription is not None:
            await _close_subscription(subscription)


async def _default_subscription_factory(edge: Any, channel: str) -> AsyncIterator[Any]:
    """Production subscription factory: dispatch on channel name.

    Edge's seven subscribe methods are zero-arg; we call them
    synchronously and return the resulting async iterator.
    Wrapping in an ``async def`` lets tests provide a stub that
    talks to a fake Edge.
    """
    method_map: Dict[str, str] = {
        CHANNEL_ANNOUNCES: "subscribe_announces",
        CHANNEL_FEED: "subscribe_feed",
        CHANNEL_INTERFACE_EVENTS: "subscribe_interface_events",
        CHANNEL_LINK_EVENTS: "subscribe_link_events",
        CHANNEL_PATH_EVENTS: "subscribe_path_events",
        CHANNEL_RESOURCE_EVENTS: "subscribe_resource_events",
        "all": "subscribe_all",
    }
    method_name = method_map.get(channel)
    if method_name is None:
        raise ValueError(f"Unknown federation channel: {channel}")
    method = getattr(edge, method_name)
    return method()  # type: ignore[no-any-return]


__all__ = [
    "QUEUE_MAXSIZE",
    "HEARTBEAT_INTERVAL_SECONDS",
    "SubscriptionFactory",
    "stream_federation_channel",
]
