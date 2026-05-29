"""
Bootstrap peer seeder — agent-side framework for canonical + organic
peer discovery.

This module owns the "rock-solid + organic" half of the CIRIS federation
peer surface:

- **Rock-solid (canonical)**: peers shipped with the agent or pulled from
  the CIRISRegistry federation directory at boot. These always appear
  in the local peer list, are tagged ``canonical=True``, default to
  ``trust=TRUSTED``, and CANNOT be permanently removed — they reseed
  on every start. User-set trust state survives reseed.
- **Organic**: peers learned at runtime via Edge ANNOUNCE events
  (CIRISEdge#46). These start at ``trust=UNKNOWN`` and accumulate in
  local state. The user can promote them to TRUSTED later (T-E5 SAS
  verification, separate task).

Persistence: peer state is stored as ``NodeType.CONFIG`` graph nodes in
``GraphScope.LOCAL`` with deterministic IDs
``canonical_peer/<key_id>`` / ``organic_peer/<key_id>``. The persist
engine is queried directly (no memory bus dependency) — this is a
boot-time utility, not a runtime service. Mutations go through a
single asyncio lock for race safety.

Edge dependency (CIRISEdge#46): the seeder does NOT call Edge directly.
The hooks in ``edge_runtime.py`` (``_seed_bootstrap_peers_into_edge`` /
``register_organic_announce_subscriber``) are currently stubs that log
TODO — they will be wired up when Edge 1.0 ships the
``bootstrap_peers`` init param and the ``recent_events()`` ANNOUNCE
stream over UniFFI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from ciris_engine.constants import CIRIS_CANONICAL_BOOTSTRAP_PEERS
from ciris_engine.logic.persistence.models.graph import (
    add_graph_node,
    delete_graph_node,
    get_graph_node,
    get_nodes_by_type,
)
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.canonical_peer import (
    CanonicalBootstrapPeer,
    LocalPeerState,
    PeerAppearance,
    PeerTrustState,
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

logger = logging.getLogger(__name__)

# Persistence layout:
#   id="canonical_peer/<key_id>"  type=CONFIG  scope=LOCAL  -> canonical row
#   id="organic_peer/<key_id>"    type=CONFIG  scope=LOCAL  -> organic row
# We use NodeType.CONFIG because:
#   - It already exists (no schema-bloat).
#   - It's a LOCAL-scope kind, matching the "local-user-owned annotation"
#     semantics of peer trust + appearance.
# The id prefix doubles as a namespace ("canonical_peers" / "organic_peers"
# per spec) and lets us distinguish rows when scanning.
_CANONICAL_NS = "canonical_peer"
_ORGANIC_NS = "organic_peer"
_NODE_TYPE = NodeType.CONFIG
_NODE_SCOPE = GraphScope.LOCAL
_UPDATED_BY = "bootstrap_peer_seeder"

# Marker key inside attributes — lets us round-trip every persisted row
# through LocalPeerState without inspecting node.id format.
_ATTR_PAYLOAD = "local_peer_state"

# Backfill regex for the legacy "peer-{pubkey[:12]}" alias_override
# format used by the pre-pubkey-field organic-peer flow. Captures the
# 12-character truncated pubkey prefix so we can promote it onto the
# new required pubkey_ed25519_base64 field on load. This is a
# best-effort recovery — the recovered value is the truncated prefix,
# NOT the original full pubkey. We surface it as such so any wire-level
# signature check fails loudly rather than silently using a wrong key.
_LEGACY_ALIAS_PUBKEY_PATTERN = re.compile(r"^peer-(?P<prefix>[A-Za-z0-9+/=_-]{12})$")


def _node_id_for(key_id: str, *, canonical: bool) -> str:
    """Deterministic graph-node id for a peer."""
    return f"{_CANONICAL_NS if canonical else _ORGANIC_NS}/{key_id}"


def _state_to_node(state: LocalPeerState, time_service: TimeServiceProtocol) -> GraphNode:
    """Wrap a LocalPeerState into a GraphNode for persist."""
    return GraphNode(
        id=_node_id_for(state.key_id, canonical=state.canonical),
        type=_NODE_TYPE,
        scope=_NODE_SCOPE,
        attributes={
            _ATTR_PAYLOAD: state.model_dump(mode="json"),
        },
        updated_by=_UPDATED_BY,
        updated_at=time_service.now() if time_service else datetime.now(timezone.utc),
    )


def _state_from_node(node: GraphNode) -> Optional[LocalPeerState]:
    """Decode LocalPeerState from a graph node.

    Returns None on shape mismatch (missing payload, not-a-dict, etc).

    Migration: if the persisted payload predates the
    ``pubkey_ed25519_base64`` field (introduced in the fixup), backfill
    it from ``alias_override`` IFF it matches the legacy
    ``peer-{pubkey[:12]}`` shape used by ``record_organic_peer`` before
    the field existed. The backfilled value is the 12-char prefix —
    NOT the full pubkey — so any signature check downstream fails loud
    rather than silently using a wrong key. We deliberately do not
    fabricate a pubkey when no recovery shape matches: those rows
    raise so the caller sees the corruption rather than silently
    losing the peer.
    """
    attrs = node.attributes
    if hasattr(attrs, "model_dump"):
        attrs_dict = attrs.model_dump()
    elif isinstance(attrs, dict):
        attrs_dict = attrs
    else:
        return None
    payload = attrs_dict.get(_ATTR_PAYLOAD)
    if not isinstance(payload, dict):
        return None

    # Backfill missing pubkey from legacy alias_override pattern.
    if not payload.get("pubkey_ed25519_base64"):
        alias_override = payload.get("alias_override")
        if isinstance(alias_override, str):
            match = _LEGACY_ALIAS_PUBKEY_PATTERN.match(alias_override)
            if match:
                payload = {
                    **payload,
                    "pubkey_ed25519_base64": match.group("prefix"),
                }
                logger.info(
                    "Backfilled pubkey_ed25519_base64 from legacy alias_override for node %s "
                    "(recovered 12-char prefix — wire signature checks will fail until refreshed)",
                    node.id,
                )
            else:
                # No recovery shape — fail loud per spec migration concern.
                raise ValueError(
                    f"Persisted peer node {node.id!r} has no pubkey_ed25519_base64 "
                    "and alias_override does not match the legacy peer-{{prefix}} "
                    "format. Cannot safely load — refusing silent corruption."
                )

    try:
        return LocalPeerState.model_validate(payload)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not decode LocalPeerState from node %s: %s", node.id, exc)
        return None


class BootstrapPeerSeeder:
    """Agent-side seeder for canonical and organic peers.

    Construct one per runtime. Call ``fetch_from_registry()`` +
    ``seed_canonical_peers()`` during boot. Wire
    ``record_organic_peer()`` to the Edge ANNOUNCE subscriber when
    CIRISEdge#46 lands.
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        registry_fetch_url: Optional[str] = None,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        http_timeout_seconds: float = 5.0,
    ) -> None:
        """
        Args:
            time_service: Required for stamping first_seen / last_seen and
                for ``add_graph_node`` (which needs a TimeService for the
                upsert path).
            registry_fetch_url: Optional URL of the CIRISRegistry
                federation-directory endpoint. If None, ``fetch_from_registry``
                immediately falls back to constants.
            http_client: Optional injected httpx.AsyncClient (tests).
            http_timeout_seconds: HTTP read timeout — short by default
                because boot is on the critical path.

        Note:
            The spec mentions ``config_service`` in __init__. We
            persist via ``add_graph_node`` directly (same pattern as
            ``consent_service.py:154``) — no service injection needed.
            This is the simplest path that keeps the seeder a pure
            utility per the "no new services" quality bar.
        """
        self._time_service = time_service
        self._registry_fetch_url = registry_fetch_url
        self._http_client = http_client
        self._http_timeout_seconds = http_timeout_seconds
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Registry fetch with offline fallback to constants.
    # ------------------------------------------------------------------

    async def fetch_from_registry(self) -> List[CanonicalBootstrapPeer]:
        """Pull canonical peers from CIRISRegistry; fall back to constants.

        Falls back to ``CIRIS_CANONICAL_BOOTSTRAP_PEERS`` on:
            - No URL configured.
            - HTTP error (non-2xx, timeout, transport failure).
            - JSON parse error.
            - Pydantic validation error on any entry.

        Returns the merged list (registry-or-fallback). Errors are
        logged but never re-raised — boot must not block on this.
        """
        if not self._registry_fetch_url:
            logger.debug("No registry URL configured; using CIRIS_CANONICAL_BOOTSTRAP_PEERS constant")
            return list(CIRIS_CANONICAL_BOOTSTRAP_PEERS)

        url = self._registry_fetch_url
        try:
            if self._http_client is not None:
                resp = await self._http_client.get(url, timeout=self._http_timeout_seconds)
            else:
                async with httpx.AsyncClient(timeout=self._http_timeout_seconds) as client:
                    resp = await client.get(url)
        except Exception as exc:
            logger.warning(
                "Federation-directory fetch failed (%s); falling back to CIRIS_CANONICAL_BOOTSTRAP_PEERS",
                exc,
            )
            return list(CIRIS_CANONICAL_BOOTSTRAP_PEERS)

        if resp.status_code < 200 or resp.status_code >= 300:
            logger.warning(
                "Federation-directory fetch returned %d; falling back to CIRIS_CANONICAL_BOOTSTRAP_PEERS",
                resp.status_code,
            )
            return list(CIRIS_CANONICAL_BOOTSTRAP_PEERS)

        try:
            body = resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "Federation-directory returned invalid JSON (%s); falling back to constants",
                exc,
            )
            return list(CIRIS_CANONICAL_BOOTSTRAP_PEERS)

        # Accept either {"peers": [...]} or a bare list.
        if isinstance(body, dict) and "peers" in body:
            raw_peers = body["peers"]
        elif isinstance(body, list):
            raw_peers = body
        else:
            logger.warning(
                "Federation-directory body has unexpected shape (%s); falling back to constants",
                type(body).__name__,
            )
            return list(CIRIS_CANONICAL_BOOTSTRAP_PEERS)

        peers: List[CanonicalBootstrapPeer] = []
        for entry in raw_peers:
            if not isinstance(entry, dict):
                logger.warning("Skipping non-dict entry in federation directory: %r", entry)
                continue
            try:
                peers.append(CanonicalBootstrapPeer.model_validate(entry))
            except Exception as exc:
                logger.warning("Skipping malformed federation-directory entry: %s", exc)
                continue

        if not peers:
            logger.warning(
                "Federation-directory yielded zero valid entries; falling back to constants",
            )
            return list(CIRIS_CANONICAL_BOOTSTRAP_PEERS)

        return peers

    # ------------------------------------------------------------------
    # Seeding.
    # ------------------------------------------------------------------

    def seed_canonical_peers(self, peers: List[CanonicalBootstrapPeer]) -> int:
        """Merge canonical peers into local state.

        For each input peer:
            - If a canonical row exists, refresh canonical metadata
              (pubkey is overwritten from the seed source — that's
              authoritative) but preserve user trust + appearance +
              alias_override + notes.
            - If no row exists, create one with trust=TRUSTED.
            - If only an organic row exists for this key_id, leave it
              alone — the canonical row supersedes future ANNOUNCE
              learnings for the same key.

        Returns the count of canonical rows written/refreshed.
        """
        now = self._now()
        written = 0
        for peer in peers:
            existing_node = get_graph_node(
                _node_id_for(peer.key_id, canonical=True),
                _NODE_SCOPE,
            )
            existing_state = _state_from_node(existing_node) if existing_node else None

            if existing_state is not None:
                # Preserve user-controlled fields. Canonical metadata
                # (here: pubkey_ed25519_base64) is REFRESHED from the
                # seed source — that's the authoritative copy and a
                # rotation in the federation directory must propagate.
                # last_seen is left alone here; that's wire territory.
                merged = LocalPeerState(
                    key_id=peer.key_id,
                    pubkey_ed25519_base64=peer.pubkey_ed25519_base64,
                    canonical=True,
                    trust=existing_state.trust,
                    appearance=existing_state.appearance,
                    alias_override=existing_state.alias_override,
                    notes=existing_state.notes,
                    first_seen=existing_state.first_seen,
                    last_seen=existing_state.last_seen,
                )
            else:
                merged = LocalPeerState(
                    key_id=peer.key_id,
                    pubkey_ed25519_base64=peer.pubkey_ed25519_base64,
                    canonical=True,
                    trust=PeerTrustState.TRUSTED,
                    appearance=None,
                    alias_override=None,
                    notes=None,
                    first_seen=now,
                    last_seen=None,
                )

            self._persist(merged)
            written += 1

        logger.info("Seeded %d canonical bootstrap peers", written)
        return written

    # ------------------------------------------------------------------
    # Reads.
    # ------------------------------------------------------------------

    def get_local_state(self, key_id: str) -> Optional[LocalPeerState]:
        """Look up a peer's local state — checks canonical row first, then organic.

        Returns None if the key_id is not known locally.
        """
        # Canonical wins if both somehow exist.
        for canonical in (True, False):
            node = get_graph_node(_node_id_for(key_id, canonical=canonical), _NODE_SCOPE)
            if node is None:
                continue
            state = _state_from_node(node)
            if state is not None:
                return state
        return None

    def list_peers(self, canonical_only: bool = False) -> List[LocalPeerState]:
        """Return all local peer state rows, deduplicated by key_id.

        If a key_id has both a canonical and organic row (shouldn't
        happen in normal use), canonical wins.
        """
        rows = get_nodes_by_type(_NODE_TYPE.value, scope=_NODE_SCOPE)
        canonical: dict[str, LocalPeerState] = {}
        organic: dict[str, LocalPeerState] = {}
        for node in rows:
            if not (node.id.startswith(f"{_CANONICAL_NS}/") or node.id.startswith(f"{_ORGANIC_NS}/")):
                continue
            state = _state_from_node(node)
            if state is None:
                continue
            (canonical if state.canonical else organic)[state.key_id] = state

        if canonical_only:
            return list(canonical.values())

        merged = dict(organic)
        merged.update(canonical)  # canonical overrides organic on collision
        return list(merged.values())

    # ------------------------------------------------------------------
    # Mutations.
    # ------------------------------------------------------------------

    async def set_trust(self, key_id: str, trust: PeerTrustState) -> None:
        """Set the user trust state for a known peer.

        Raises:
            ValueError: if no canonical or organic row exists for key_id.
                We refuse to create rows from a bare set_trust — it would
                let the UI silently insert a peer the agent has never
                heard of, which is a security smell.
        """
        async with self._lock:
            state = self.get_local_state(key_id)
            if state is None:
                raise ValueError(
                    f"Cannot set trust on unknown peer {key_id!r}: not in canonical or organic state. "
                    "Call record_organic_peer() or seed_canonical_peers() first."
                )
            updated = state.model_copy(update={"trust": trust})
            self._persist(updated)

    async def set_appearance(self, key_id: str, appearance: PeerAppearance) -> None:
        """Set the local UI appearance for a known peer.

        Raises ValueError if the peer is unknown (same rationale as
        ``set_trust``).
        """
        async with self._lock:
            state = self.get_local_state(key_id)
            if state is None:
                raise ValueError(
                    f"Cannot set appearance on unknown peer {key_id!r}: not in canonical or organic state."
                )
            updated = state.model_copy(update={"appearance": appearance})
            self._persist(updated)

    async def record_organic_peer(
        self,
        key_id: str,
        pubkey_ed25519_base64: str,
        alias: Optional[str] = None,
    ) -> LocalPeerState:
        """Idempotently record an organically-discovered peer.

        Called from the Edge ANNOUNCE subscriber (CIRISEdge#46 — currently
        stubbed in ``edge_runtime.py``). Trust defaults to UNKNOWN.

        - If a canonical row exists for ``key_id``, refresh ``last_seen``
          on it and return it unchanged otherwise (canonical wins —
          canonical's pubkey is authoritative, never overwritten by an
          ANNOUNCE).
        - If an organic row exists, refresh ``last_seen`` and return it.
          ``alias_override``, ``appearance``, ``notes``, ``trust``, and
          ``pubkey_ed25519_base64`` are preserved (a pubkey rotation
          must come through a fresh canonical reseed or an explicit
          user action — silent overwrite via ANNOUNCE would let an
          attacker replace a known peer's key).
        - If no row exists, create an organic row at ``trust=UNKNOWN``
          with the supplied pubkey.
        """
        if not pubkey_ed25519_base64:
            raise ValueError("pubkey_ed25519_base64 is required and must be non-empty")

        async with self._lock:
            now = self._now()

            canonical_node = get_graph_node(_node_id_for(key_id, canonical=True), _NODE_SCOPE)
            if canonical_node is not None:
                state = _state_from_node(canonical_node)
                if state is not None:
                    # Refresh last_seen so the canonical peer surfaces
                    # as recently-active, but don't downgrade trust and
                    # don't overwrite the authoritative pubkey.
                    updated = state.model_copy(update={"last_seen": now})
                    self._persist(updated)
                    return updated

            organic_node = get_graph_node(_node_id_for(key_id, canonical=False), _NODE_SCOPE)
            existing = _state_from_node(organic_node) if organic_node else None
            if existing is not None:
                updated = existing.model_copy(update={"last_seen": now})
                self._persist(updated)
                return updated

            display_alias = alias  # may be None — that's fine
            new_state = LocalPeerState(
                key_id=key_id,
                pubkey_ed25519_base64=pubkey_ed25519_base64,
                canonical=False,
                trust=PeerTrustState.UNKNOWN,
                appearance=None,
                alias_override=display_alias,
                notes=None,
                first_seen=now,
                last_seen=now,
            )
            self._persist(new_state)
            return new_state

    # ------------------------------------------------------------------
    # Internals.
    # ------------------------------------------------------------------

    def _now(self) -> datetime:
        try:
            v = self._time_service.now()
            if isinstance(v, datetime):
                return v
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("time_service.now() failed (%s); using wall-clock", exc)
        return datetime.now(timezone.utc)

    def _persist(self, state: LocalPeerState) -> None:
        """Write a LocalPeerState to the graph. Sync — wrapped by _lock.

        The persist layer's ``add_graph_node`` merges attributes on
        upsert, so we wipe the marker before writing by passing the
        full payload under ``_ATTR_PAYLOAD``. Any earlier payload at
        that key is replaced atomically.
        """
        node = _state_to_node(state, self._time_service)
        add_graph_node(node, self._time_service)

    def delete_for_test(self, key_id: str) -> None:
        """Test-only helper to remove both canonical + organic rows for
        a key_id. Production code MUST NOT call this — canonical peers
        are intentionally non-removable. Used by the invariant test
        that simulates mid-state deletion before a reseed.
        """
        delete_graph_node(_node_id_for(key_id, canonical=True), _NODE_SCOPE)
        delete_graph_node(_node_id_for(key_id, canonical=False), _NODE_SCOPE)
