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
"""

from __future__ import annotations

import logging
from typing import Dict

from fastapi import Request

from ciris_engine.logic.runtime.bootstrap_peers import BootstrapPeerSeeder

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
