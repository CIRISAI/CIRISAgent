"""
Federation identity route — exposes the local agent's federation
``signer_key_id`` + Edge crate version + local peer counts.

OBSERVER+ readable. Mirrors the existing ``/v1/system/agent-mode``
shape: deliberately small, polled by the mobile client on the home
tab to surface "your federation address is X" + crate version + peer
counts.

If Edge is unavailable (degraded mode — see CIRISEdge#22), returns 503
with a stable error envelope so the client can fall back to the offline
UI surface.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from ciris_engine.logic.adapters.api.dependencies.auth import (
    AuthContext,
    require_observer,
)
from ciris_engine.logic.runtime.edge_runtime import try_get_edge
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.federation_api import FederationIdentityResponse

from .common import EDGE_UNAVAILABLE_BODY, get_or_create_seeder

logger = logging.getLogger(__name__)

router = APIRouter()

AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]


# Stable list of capabilities the federation surface advertises. Bumped
# in lock-step with new routes — keep this in sync with the actual
# router includes in ``federation/__init__.py``.
_FEDERATION_CAPABILITIES = [
    "sas",
    "fetch_content",
    "metrics",
    "subscribe_events",
    "inline_text",
]


@router.get(
    "/identity",
    responses={
        503: {"description": "Edge runtime is not available (degraded mode)"},
    },
)
async def get_federation_identity(
    request: Request,
    auth: AuthObserverDep,
) -> Any:
    """Return signer_key_id + crate_version + local peer counts."""
    edge = try_get_edge()
    if edge is None:
        return JSONResponse(status_code=503, content=EDGE_UNAVAILABLE_BODY)

    try:
        signer_key_id = edge.signer_key_id()
        crate_version = edge.crate_version()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Edge identity query failed: %s", exc)
        return JSONResponse(status_code=503, content=EDGE_UNAVAILABLE_BODY)

    try:
        seeder = get_or_create_seeder(request)
        all_peers = seeder.list_peers()
        canonical_peers = seeder.list_peers(canonical_only=True)
        peer_count_total = len(all_peers)
        peer_count_canonical = len(canonical_peers)
    except RuntimeError as exc:
        # Seeder not yet wired (no time_service on app.state). We still
        # have a working Edge identity to return; surface zero peer
        # counts rather than blanket-503-ing the whole call.
        logger.debug("BootstrapPeerSeeder not available for identity route: %s", exc)
        peer_count_total = 0
        peer_count_canonical = 0

    response = FederationIdentityResponse(
        signer_key_id=signer_key_id,
        crate_version=crate_version,
        peer_count_total=peer_count_total,
        peer_count_canonical=peer_count_canonical,
        capabilities=list(_FEDERATION_CAPABILITIES),
    )
    return SuccessResponse(data=response)
