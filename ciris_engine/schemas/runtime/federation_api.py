"""
Federation API schemas — pydantic models for the synchronous federation
REST surface (``/v1/federation/*``).

These wrap CIRISEdge 1.0 PyO3 calls (via
``ciris_engine.logic.runtime.edge_runtime.get_edge()``) plus
``BootstrapPeerSeeder`` state into typed responses for Compose
Multiplatform mobile clients (and any other API consumer).

Shapes are intentionally close to the Rust-side return values so the
JSON wire format is stable and round-trippable. See ``T-E-API`` in
``release/2.9.4`` for the route surface that consumes these.

Key shapes mirrored from Edge:

- ``EdgePeerReachability``: keyed dict from
  ``Edge.peer_reachability(key_id)`` — one entry per transport medium
  (``reticulum-rs``, ``http``, ...). Each entry has a rolling-window
  success ratio (``[0.0, 1.0]``) plus ``last_ok_ts`` (wall-clock ms).
- ``EdgeMetricsSnapshot``: ``Edge.metrics_snapshot()`` returns nested
  dicts keyed first by metric family (e.g. ``envelopes_sent_total``),
  then by sub-key (e.g. ``InlineText``). We mirror the families
  explicitly to keep the wire schema stable, and accept arbitrary
  sub-keys per family (their union is open-ended — new envelope kinds
  and transport mediums show up across Edge releases).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.canonical_peer import (
    LocalPeerState,
    PeerAppearance,
    PeerTrustState,
)


# ---------------------------------------------------------------------------
# /v1/federation/identity
# ---------------------------------------------------------------------------


class FederationIdentityResponse(BaseModel):
    """Local agent's federation identity + crate version + peer counts.

    Does NOT include ``agent_mode`` — that lives on the existing
    ``/v1/system/agent-mode`` route. Clients hit both surfaces.
    """

    signer_key_id: str = Field(
        ...,
        description="Local agent's Ed25519 signer_key_id (federation address)",
    )
    crate_version: str = Field(
        ...,
        description="CIRISEdge crate version backing this runtime",
    )
    peer_count_total: int = Field(
        ...,
        ge=0,
        description="Total local peer count (canonical + organic, deduplicated)",
    )
    peer_count_canonical: int = Field(
        ...,
        ge=0,
        description="Count of canonical (rock-solid) peers in local state",
    )
    capabilities: List[str] = Field(
        ...,
        description=(
            "Federation surface capabilities advertised to the client. Currently a "
            "fixed literal list mirroring the Edge 1.0 surface."
        ),
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


# ---------------------------------------------------------------------------
# /v1/federation/peers (list + detail)
# ---------------------------------------------------------------------------


class FederationPeerListResponse(BaseModel):
    """List of local peers (canonical + organic) — optionally filtered."""

    peers: List[LocalPeerState] = Field(
        ...,
        description="LocalPeerState rows matching the supplied filters",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total count of returned peers (==len(peers))",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class EdgeReachabilityEntry(BaseModel):
    """Per-transport reachability snapshot for a single peer.

    Mirrors the Rust-side tuple ``(ratio, last_ok_ts)`` returned by
    ``Edge.peer_reachability(key_id)[medium]``. ``ratio`` is the
    rolling-window ``successes / attempts`` ratio in ``[0.0, 1.0]``;
    ``last_ok_ts`` is the wall-clock millisecond timestamp of the most
    recent successful attempt (0 if no successes have been recorded).
    """

    ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Rolling-window successes/attempts in [0.0, 1.0]",
    )
    last_ok_ts: int = Field(
        ...,
        ge=0,
        description="Wall-clock millisecond timestamp of most recent OK (0 if none)",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class EdgePeerReachability(BaseModel):
    """Per-medium reachability map for a peer.

    Empty ``by_medium`` means "no measurement yet" — the client SHOULD
    render "unknown" rather than "0.0%". Mediums are open-ended strings
    (``reticulum-rs``, ``http``, future transports).
    """

    by_medium: Dict[str, EdgeReachabilityEntry] = Field(
        default_factory=dict,
        description=(
            "Map of transport medium name -> reachability entry. Empty means "
            "'no measurement yet recorded'."
        ),
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class FederationPeerDetailResponse(BaseModel):
    """Detail view for a single peer: local state + Edge reachability."""

    peer: LocalPeerState = Field(
        ...,
        description="Local persisted state for this peer",
    )
    reachability: Optional[EdgePeerReachability] = Field(
        None,
        description=(
            "Per-transport reachability snapshot from Edge. None if Edge is "
            "unavailable AND the route still chose to return the local state "
            "(currently the route returns 503 instead, so this is always "
            "populated when status==200)."
        ),
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


# ---------------------------------------------------------------------------
# /v1/federation/peers/{key_id}/sas
# ---------------------------------------------------------------------------


class FederationPeerSASResponse(BaseModel):
    """Signal-style Short Authentication String for verifying a peer key.

    Both ``words`` and ``digits`` are derived deterministically by Edge
    from the ``(local_pub, peer_pub, protocol-constant)`` tuple — sorted
    so both sides of the call see the same value.
    """

    key_id: str = Field(
        ...,
        description="Peer's Ed25519 signer_key_id this SAS was derived against",
    )
    words: List[str] = Field(
        ...,
        description="BIP39-English word list (default 5 words from Edge)",
    )
    digits: str = Field(
        ...,
        description="Zero-padded decimal digit string (default 6 digits from Edge)",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


# ---------------------------------------------------------------------------
# /v1/federation/peers/{key_id}/trust + /appearance (PUT bodies)
# ---------------------------------------------------------------------------


class FederationPeerTrustUpdateRequest(BaseModel):
    """Body for ``PUT /v1/federation/peers/{key_id}/trust``."""

    trust: PeerTrustState = Field(
        ...,
        description="New trust state to apply to the peer",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class FederationPeerAppearanceUpdateRequest(BaseModel):
    """Body for ``PUT /v1/federation/peers/{key_id}/appearance``."""

    appearance: PeerAppearance = Field(
        ...,
        description="New PeerAppearance to apply to the peer (local-user-owned)",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


# ---------------------------------------------------------------------------
# /v1/federation/metrics
# ---------------------------------------------------------------------------


class FederationMetricsResponse(BaseModel):
    """Edge metrics snapshot — wraps ``Edge.metrics_snapshot()``.

    Each family is a string->int (or string->float for ratios) map.
    Family keys are stable; sub-keys (e.g. envelope kinds, transport
    mediums, failure reasons) are open-ended across Edge releases.
    """

    envelopes_sent_total: Dict[str, int] = Field(
        default_factory=dict,
        description="Counter map: envelope kind -> total sent",
    )
    envelopes_received_total: Dict[str, int] = Field(
        default_factory=dict,
        description="Counter map: envelope kind -> total received",
    )
    send_failures_total: Dict[str, int] = Field(
        default_factory=dict,
        description="Counter map: '<transport>:<reason>' -> total send failures",
    )
    verify_failures_total: Dict[str, int] = Field(
        default_factory=dict,
        description="Counter map: failure reason -> total verify failures",
    )
    durable_queue_depth: Dict[str, int] = Field(
        default_factory=dict,
        description="Gauge map: queue kind -> current depth",
    )
    transport_bytes_in_total: Dict[str, int] = Field(
        default_factory=dict,
        description="Counter map: transport -> total inbound bytes",
    )
    transport_bytes_out_total: Dict[str, int] = Field(
        default_factory=dict,
        description="Counter map: transport -> total outbound bytes",
    )
    peer_reachability_ratio: Dict[str, float] = Field(
        default_factory=dict,
        description="Gauge map: '<peer_key>:<medium>' -> success ratio in [0,1]",
    )
    inline_text_subscriber_count: int = Field(
        0,
        ge=0,
        description="Number of live inline-text subscribers (diagnostics helper)",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


# ---------------------------------------------------------------------------
# /v1/federation/content/{content_id}
# ---------------------------------------------------------------------------


class FederationContentFetchRequest(BaseModel):
    """Body for ``POST /v1/federation/content/{content_id}``.

    ``content_id`` is the URL-path SHA-256 (64-char hex). The body picks
    which peer to ask for the content and how long to wait. Both fields
    are required: there is no global "content directory" today — the
    caller must already know a candidate holder.
    """

    peer_key_id: str = Field(
        ...,
        min_length=1,
        description="Peer to ask for the content (Ed25519 signer_key_id)",
    )
    timeout_ms: int = Field(
        30000,
        ge=1,
        le=300_000,
        description="Per-fetch timeout in milliseconds (1ms..5min)",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class FederationContentResponse(BaseModel):
    """Response for ``POST /v1/federation/content/{content_id}``.

    ``payload_base64`` carries the raw bytes from Edge's
    ``fetch_content`` (kind=="bytes" branch). The SHA-256 invariant
    (``sha256(payload_base64_decoded) == content_id``) is enforced
    Rust-side by Edge before the bytes ever cross the FFI boundary.

    A peer-side ``content_miss`` is surfaced via HTTP 404 with an
    error body rather than a 200; this response is only the success
    branch.
    """

    content_id: str = Field(
        ...,
        description="SHA-256 hex digest (64 chars) of the fetched payload",
    )
    content_type: Optional[str] = Field(
        None,
        description=(
            "Best-effort MIME type if Edge supplied one in the fetch result. "
            "Today Edge's fetch_content does not return a content_type so this "
            "is always None — reserved for forward compatibility."
        ),
    )
    payload_base64: str = Field(
        ...,
        description="Raw payload bytes, base64-encoded",
    )
    size_bytes: int = Field(
        ...,
        ge=0,
        description="Decoded payload size in bytes",
    )
    fetched_at: datetime = Field(
        ...,
        description="UTC timestamp when this fetch completed",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


__all__ = [
    "EdgeMetricsSnapshot",
    "EdgePeerReachability",
    "EdgeReachabilityEntry",
    "FederationContentFetchRequest",
    "FederationContentResponse",
    "FederationIdentityResponse",
    "FederationMetricsResponse",
    "FederationPeerAppearanceUpdateRequest",
    "FederationPeerDetailResponse",
    "FederationPeerListResponse",
    "FederationPeerSASResponse",
    "FederationPeerTrustUpdateRequest",
]


# Backwards-compatible alias: route + tests use FederationMetricsResponse,
# but schema_module exports EdgeMetricsSnapshot in __all__ via a side-by-side
# alias to keep the typed-Edge name available to inspection callers.
EdgeMetricsSnapshot = FederationMetricsResponse
