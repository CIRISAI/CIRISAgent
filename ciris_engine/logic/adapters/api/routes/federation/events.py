"""
Federation event SSE route — ``GET /v1/federation/events/{channel}``.

Exposes Edge 1.0's seven ``subscribe_*`` channels as a single
long-poll SSE endpoint for mobile clients. The mobile UI surfaces
that consume this (``NetworkAnnouncesScreen``,
``NetworkPathsScreen``, ``NetworkDiagnosticsScreen``) maintain a
per-screen subscription and reconnect on backgrounding.

OBSERVER role is sufficient — federation network state is
non-sensitive operational telemetry. The verified-feed channel
surfaces ``signing_key_id`` / ``destination_key_id`` / message-type
metadata only (no message bodies), so OBSERVER access does not leak
content.

See ``ciris_engine.logic.adapters.api.sse.federation_sse_bridge`` for
the SSE plumbing contract (backpressure, heartbeat, cleanup).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, Path, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ciris_engine.logic.adapters.api.routes._common import AuthObserverDep
from ciris_engine.logic.adapters.api.sse.federation_sse_bridge import (
    stream_federation_channel,
)
from ciris_engine.logic.runtime import edge_runtime
from ciris_engine.schemas.runtime.federation_events import (
    VALID_CHANNELS,
    FederationEventErrorEnvelope,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _unknown_channel_response(channel: str) -> JSONResponse:
    """400 body for an unknown channel name. Not 404 — route exists."""
    body = FederationEventErrorEnvelope(
        error="UNKNOWN_CHANNEL",
        detail=(
            f"Channel '{channel}' is not a recognized federation "
            f"event channel. Valid channels: {', '.join(VALID_CHANNELS)}."
        ),
    )
    return JSONResponse(status_code=400, content=body.model_dump())


def _edge_unavailable_response(reason: str) -> JSONResponse:
    """503 body when the Edge runtime singleton is not live."""
    body = FederationEventErrorEnvelope(
        error="EDGE_UNAVAILABLE",
        detail=reason,
        valid_channels=list(VALID_CHANNELS),
    )
    return JSONResponse(status_code=503, content=body.model_dump())


@router.get(
    "/events/{channel}",
    responses={
        200: {
            "description": (
                "Server-Sent Events stream of FederationEventEnvelope frames "
                "for the requested channel."
            ),
            "content": {"text/event-stream": {}},
        },
        400: {"description": "Unknown channel name."},
        503: {"description": "Edge runtime not available."},
    },
)
async def federation_events_stream(
    request: Request,
    auth: AuthObserverDep,
    channel: str = Path(
        ...,
        description=(
            "Federation event channel to subscribe to. One of: "
            "announces, feed, interface_events, link_events, path_events, "
            "resource_events, all."
        ),
    ),
    last_event_id: Optional[str] = Header(
        default=None,
        alias="Last-Event-ID",
        description=(
            "SSE reconnect header. Edge does not support replay; the bridge "
            "emits a one-shot resume-notice when this is present."
        ),
    ),
) -> Any:
    """Long-poll SSE endpoint surfacing one Edge subscription channel.

    Returns ``text/event-stream`` with three event names:
        - ``connected``         — one-shot on connect, ack the stream.
        - ``resume-notice``     — one-shot if ``Last-Event-ID`` was set.
        - ``federation_event``  — per-emission envelope.
        - ``error``             — terminal, indicates server-side fault.

    Plus periodic SSE comment heartbeats (``: heartbeat``) every 30s of
    idle, ignored by EventSource clients.
    """
    if channel not in VALID_CHANNELS:
        logger.info(
            "federation events: rejected unknown channel=%r from user_id=%s",
            channel,
            getattr(auth, "user_id", "?"),
        )
        return _unknown_channel_response(channel)

    if not edge_runtime.is_available():
        logger.info(
            "federation events: Edge unavailable, rejecting channel=%s user_id=%s",
            channel,
            getattr(auth, "user_id", "?"),
        )
        return _edge_unavailable_response(
            "Edge runtime is not initialized or is in degraded state. "
            "Federation event streaming requires a live Edge runtime."
        )

    try:
        edge = edge_runtime.get_edge()
    except RuntimeError as exc:
        return _edge_unavailable_response(str(exc))

    logger.debug(
        "federation events: opening stream channel=%s user_id=%s last_event_id=%r",
        channel,
        getattr(auth, "user_id", "?"),
        last_event_id,
    )

    return StreamingResponse(
        stream_federation_channel(
            edge,
            channel,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # CORS — mobile clients hit this from the app webview.
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control, Last-Event-ID",
            # Disable proxy buffering — SSE requires immediate flush.
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
