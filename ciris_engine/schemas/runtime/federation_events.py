"""
Federation event envelope schemas (CIRISAgent 2.9.4).

Edge 1.0 GA exposes seven async iterator subscription channels:

- ``subscribe_announces``        — peer-announce events
- ``subscribe_feed``             — verified content feed
- ``subscribe_interface_events`` — Reticulum interface state changes
- ``subscribe_link_events``      — RNS link state (per-peer)
- ``subscribe_path_events``      — RNS path-learning events
- ``subscribe_resource_events``  — bulk-resource transfer events
- ``subscribe_all``              — multiplexed superstream of everything

The Edge yields native ``dict`` projections for ``subscribe_feed``
(``VerifiedFeedSubscription`` — see ``Edge.subscribe_feed`` docstring)
and ``NetworkEvent`` objects for every other channel
(``NetworkEventSubscription`` — single ``kind``-discriminated union).

The SSE route ``GET /v1/federation/events/{channel}`` wraps every
arriving Edge event in a ``FederationEventEnvelope`` and ships it to the
client as a JSON-encoded ``text/event-stream`` frame. The envelope is
the stable mobile-client contract — it is decoupled from Edge's
internal event shape, so Edge wire upgrades do not break the mobile
contract.

Mobile clients route on ``channel`` + ``event_type``; ``event_id`` is
the per-event UUID used for client-side dedup on reconnect; ``payload``
is the channel-specific projection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

# Channel-name constants — kept here so both the route and the bridge
# utility (and tests / mobile codegen) reach for ONE source of truth.

CHANNEL_ANNOUNCES = "announces"
CHANNEL_FEED = "feed"
CHANNEL_INTERFACE_EVENTS = "interface_events"
CHANNEL_LINK_EVENTS = "link_events"
CHANNEL_PATH_EVENTS = "path_events"
CHANNEL_RESOURCE_EVENTS = "resource_events"
CHANNEL_ALL = "all"

VALID_CHANNELS: List[str] = [
    CHANNEL_ANNOUNCES,
    CHANNEL_FEED,
    CHANNEL_INTERFACE_EVENTS,
    CHANNEL_LINK_EVENTS,
    CHANNEL_PATH_EVENTS,
    CHANNEL_RESOURCE_EVENTS,
    CHANNEL_ALL,
]


class FederationEventEnvelope(BaseModel):
    """Stable mobile-facing wire shape for one Edge subscription event.

    Every SSE ``data:`` frame on ``/v1/federation/events/{channel}``
    JSON-encodes one of these.

    The envelope's identity fields (``event_id``, ``channel``,
    ``timestamp``, ``event_type``) are statically typed. The
    channel-specific projection lives in ``payload``.

    Why ``payload`` is ``Dict[str, Any]``:
        Edge ships seven distinct event taxonomies behind a single
        async iterator surface. ``NetworkEvent`` is the union shape
        with ~12 ``kind`` discriminators; ``VerifiedFeedSubscription``
        yields a separate envelope projection. Statically typing
        every discriminator at the API boundary would either:
          (a) lock the mobile contract to Edge's internal union (bad
              — Edge can rev the union), or
          (b) require a per-discriminator Pydantic class hierarchy
              that we have to mirror by hand whenever Edge ships a
              new kind (bad — silent drift).
        We pick the lesser evil: keep the envelope statically typed
        and document the per-channel payload shape here. Mobile
        decodes per channel via its own per-channel domain model.
        Tracking issue: CIRISAgent#NNN (mobile typed projections).
    """

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(
        ...,
        description=(
            "UUID4 generated server-side per event. Mobile clients "
            "dedup on this when reconnecting via Last-Event-ID."
        ),
    )
    channel: str = Field(
        ...,
        description=(
            "Source channel: one of announces / feed / interface_events / "
            "link_events / path_events / resource_events / all. For "
            "``all`` the original sub-channel name is also surfaced in "
            "``payload._origin_channel`` when known."
        ),
    )
    timestamp: datetime = Field(
        ...,
        description="UTC wall-clock timestamp the SSE bridge observed this event.",
    )
    event_type: str = Field(
        ...,
        description=(
            "Taxonomy-specific event_type. Examples per channel:\n"
            "  - announces / link_events / interface_events / path_events / "
            "resource_events / all: NetworkEvent.kind value, one of "
            "{announce_received, announce_sent, path_discovered, path_lost, "
            "link_established, link_dropped, transport_up, transport_down, "
            "key_rotated, signature_failure, policy_block, lagged}\n"
            "  - feed: VerifiedFeedSubscription.message_type "
            "(e.g. InlineText, DurableInlineText)"
        ),
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Channel-specific event projection. Per-channel shapes:\n"
            "  - announces / link_events / interface_events / path_events / "
            "resource_events / all (NetworkEvent fields): at, kind, message, "
            "severity, peer_key_id?, transport_id?, aspect?, rssi_dbm?, "
            "snr_db?, lagged_count?, identity_hash? (hex), app_data? (hex), "
            "link_id? (hex)\n"
            "  - feed (VerifiedFeedSubscription fields): message_type, "
            "signing_key_id, destination_key_id, body_sha256_prefix, "
            "transport_id, received_at_ms"
        ),
    )


class FederationEventErrorEnvelope(BaseModel):
    """Error response body when ``/v1/federation/events/{channel}`` rejects.

    Distinct from the in-stream SSE error frame — this is the JSON
    body for HTTP 400 / 503 responses.
    """

    model_config = ConfigDict(frozen=True)

    error: str = Field(..., description="Stable machine error code.")
    detail: str = Field(..., description="Human-readable explanation.")
    valid_channels: List[str] = Field(
        default_factory=lambda: list(VALID_CHANNELS),
        description="The canonical valid-channel list (returned on UNKNOWN_CHANNEL).",
    )


__all__ = [
    "CHANNEL_ANNOUNCES",
    "CHANNEL_FEED",
    "CHANNEL_INTERFACE_EVENTS",
    "CHANNEL_LINK_EVENTS",
    "CHANNEL_PATH_EVENTS",
    "CHANNEL_RESOURCE_EVENTS",
    "CHANNEL_ALL",
    "VALID_CHANNELS",
    "FederationEventEnvelope",
    "FederationEventErrorEnvelope",
]
