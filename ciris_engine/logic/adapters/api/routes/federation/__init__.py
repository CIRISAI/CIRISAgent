"""
Federation API routes — synchronous REST surface that proxies the
CIRISEdge 1.0 PyO3 calls (via ``edge_runtime.get_edge()``) plus the
``BootstrapPeerSeeder`` state to mobile clients.

Surface (all under ``/v1/federation``):

- ``GET    /identity``                          (OBSERVER+)
- ``GET    /peers``                             (OBSERVER+)
- ``GET    /peers/{key_id}``                    (OBSERVER+)
- ``GET    /peers/{key_id}/sas``                (OBSERVER+)
- ``PUT    /peers/{key_id}/trust``              (SYSTEM_ADMIN)
- ``PUT    /peers/{key_id}/appearance``         (SYSTEM_ADMIN)
- ``GET    /metrics``                           (OBSERVER+)
- ``POST   /content/{content_id}``              (SYSTEM_ADMIN)
- ``GET    /events/{channel}``                  (OBSERVER+, SSE long-poll)

The router is exported as ``router`` and registered in
``routes/__init__.py`` so ``app.py`` includes it with the standard
``/v1`` prefix.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from . import content, identity, metrics, peers, sas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/federation", tags=["federation"])

router.include_router(identity.router)
router.include_router(peers.router)
router.include_router(sas.router)
router.include_router(metrics.router)
router.include_router(content.router)

# The SSE events module is owned by the parallel T-E-SSE task and may not
# be present in every checkout. Mount it if importable; skip silently
# otherwise — the synchronous T-E-API surface above remains complete on
# its own.
try:
    from . import events as _events_module
except ImportError as _events_import_exc:  # pragma: no cover - import-time
    logger.debug(
        "Federation events SSE module not available (%s); "
        "synchronous federation routes registered without it.",
        _events_import_exc,
    )
else:
    router.include_router(_events_module.router)

__all__ = ["router"]
