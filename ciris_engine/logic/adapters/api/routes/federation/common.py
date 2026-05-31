"""
Common helpers shared by the federation route modules.

- ``get_or_create_seeder``: resolve the ``BootstrapPeerSeeder`` from
  ``app.state`` (test-injectable) or lazily construct one bound to the
  app's ``time_service``. Mirrors the pattern in
  ``routes/system/peers.py``.
- ``EDGE_UNAVAILABLE_BODY``: the canonical 503 envelope every federation
  route uses when ``edge_runtime.try_get_edge()`` returns ``None``. We
  fix the shape here so the mobile client only has to recognize one
  error envelope across the whole surface.
- ``parse_edge_reachability``: turn the raw dict returned by
  ``edge.peer_reachability(key_id)`` into a typed
  ``EdgePeerReachability``. Tolerant to missing fields and unexpected
  shapes — Edge ships new transport mediums periodically.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping

from fastapi import Request

from ciris_engine.logic.runtime.bootstrap_peers import BootstrapPeerSeeder
from ciris_engine.schemas.runtime.federation_api import (
    EdgePeerReachability,
    EdgeReachabilityEntry,
)

logger = logging.getLogger(__name__)


# Canonical 503 body used by every federation route when Edge isn't live.
# Keep this fixed: mobile clients pattern-match on ``error`` to fall back
# to the offline UI surface.
EDGE_UNAVAILABLE_BODY: Dict[str, str] = {
    "error": "EDGE_UNAVAILABLE",
    "detail": (
        "CIRISEdge runtime is not available (degraded boot). "
        "Federation surface is offline until Edge initializes."
    ),
}


_SEEDER_STATE_KEY = "bootstrap_peer_seeder"


def get_or_create_seeder(request: Request) -> BootstrapPeerSeeder:
    """Resolve the BootstrapPeerSeeder from app.state, creating one if needed.

    Tests can pre-populate ``request.app.state.bootstrap_peer_seeder``
    to inject a custom seeder. In production it is created lazily on
    first use, bound to whichever ``time_service`` is wired onto
    ``app.state``.

    Raises:
        RuntimeError: if no time_service is wired (route caller is
            expected to surface this as a 503 to the client).
    """
    existing = getattr(request.app.state, _SEEDER_STATE_KEY, None)
    if existing is not None:
        # `getattr` returns Any; narrow to the declared return type so
        # mypy's [no-any-return] check is satisfied without changing
        # runtime behavior.
        assert isinstance(existing, BootstrapPeerSeeder)
        return existing

    time_service = getattr(request.app.state, "time_service", None)
    if time_service is None:
        raise RuntimeError(
            "Cannot create BootstrapPeerSeeder: time_service not wired on app.state"
        )

    seeder = BootstrapPeerSeeder(time_service=time_service, registry_fetch_url=None)
    # Seed the canonical CIRIS infrastructure peers on first construction so
    # /v1/federation/peers and the identity peer counters reflect them on a
    # fresh production agent. Without this the seeder was created but never
    # populated (CIRISAgent#841 review — Codex P2). The constant is currently
    # empty (T-C placeholder until canonical CIRIS addresses are published);
    # once it's populated, every API caller after Edge boot sees the
    # `CIRIS_CANONICAL` badge without an explicit reseed step.
    from ciris_engine.constants import CIRIS_CANONICAL_BOOTSTRAP_PEERS

    if CIRIS_CANONICAL_BOOTSTRAP_PEERS:
        try:
            seeder.seed_canonical_peers(CIRIS_CANONICAL_BOOTSTRAP_PEERS)
        except Exception as exc:  # pragma: no cover - defensive
            # Don't block the API call; a failed seed should surface
            # via empty peer lists rather than a 500 to the client.
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "BootstrapPeerSeeder: canonical seed failed on lazy-create: %s", exc
            )
    setattr(request.app.state, _SEEDER_STATE_KEY, seeder)
    return seeder


def parse_edge_reachability(raw: Any) -> EdgePeerReachability:
    """Coerce a raw ``edge.peer_reachability(...)`` return into a typed model.

    The Rust-side shape is a ``dict[medium_name -> dict{ratio,
    last_ok_ts}]``. We accept any Mapping-shaped input and drop any
    entry whose value isn't a Mapping-with-fields. Missing entries
    surface as the model's default empty map, which the client SHOULD
    render as "unknown".
    """
    if not isinstance(raw, Mapping):
        return EdgePeerReachability()

    by_medium: Dict[str, EdgeReachabilityEntry] = {}
    for medium, entry in raw.items():
        if not isinstance(medium, str) or not isinstance(entry, Mapping):
            continue
        try:
            ratio_raw = entry.get("ratio")
            last_ok_raw = entry.get("last_ok_ts")
            # Reject negative / out-of-range values rather than clamping;
            # surface the corruption as "no entry for this medium".
            ratio = float(ratio_raw) if ratio_raw is not None else 0.0
            last_ok = int(last_ok_raw) if last_ok_raw is not None else 0
            if ratio < 0.0 or ratio > 1.0 or last_ok < 0:
                logger.debug(
                    "Dropping out-of-range reachability entry for %s: %r",
                    medium,
                    entry,
                )
                continue
            by_medium[medium] = EdgeReachabilityEntry(ratio=ratio, last_ok_ts=last_ok)
        except (TypeError, ValueError) as exc:
            logger.debug("Skipping unparseable reachability entry %s=%r (%s)", medium, entry, exc)
            continue

    return EdgePeerReachability(by_medium=by_medium)
