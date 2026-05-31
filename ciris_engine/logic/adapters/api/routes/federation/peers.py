"""
Federation peer routes.

- ``GET    /v1/federation/peers``                       (OBSERVER+)
- ``GET    /v1/federation/peers/{key_id}``              (OBSERVER+)
- ``PUT    /v1/federation/peers/{key_id}/trust``        (SYSTEM_ADMIN)
- ``PUT    /v1/federation/peers/{key_id}/appearance``   (SYSTEM_ADMIN)

The list + detail endpoints surface ``LocalPeerState`` rows from
``BootstrapPeerSeeder``. Detail enriches with the Edge per-medium
reachability snapshot. Trust + appearance mutations go through the
seeder's locked write path.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import JSONResponse

from ciris_engine.logic.adapters.api.dependencies.auth import (
    AuthContext,
    require_observer,
    require_system_admin,
)
from ciris_engine.logic.runtime.edge_runtime import try_get_edge
from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.canonical_peer import PeerTrustState
from ciris_engine.schemas.runtime.federation_api import (
    FederationPeerAppearanceUpdateRequest,
    FederationPeerDetailResponse,
    FederationPeerListResponse,
    FederationPeerTrustUpdateRequest,
)

from .common import (
    EDGE_UNAVAILABLE_BODY,
    get_or_create_seeder,
    parse_edge_reachability,
)

logger = logging.getLogger(__name__)

router = APIRouter()

AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]
AuthSystemAdminDep = Annotated[AuthContext, Depends(require_system_admin)]


_SEEDER_UNAVAILABLE_BODY = {
    "error": "BOOTSTRAP_SEEDER_UNAVAILABLE",
    "detail": (
        "BootstrapPeerSeeder is not wired (no time_service on app.state). "
        "Peer state cannot be read until the runtime has wired its services."
    ),
}


@router.get(
    "/peers",
    responses={
        503: {"description": "BootstrapPeerSeeder is not yet wired"},
    },
)
async def list_federation_peers(
    request: Request,
    auth: AuthObserverDep,
    canonical_only: bool = Query(
        False,
        description="If true, return only canonical (rock-solid) peers.",
    ),
    trust: Optional[PeerTrustState] = Query(
        None,
        description="If set, only return peers in this trust state.",
    ),
) -> Any:
    """List all known peers (canonical + organic), optionally filtered."""
    try:
        seeder = get_or_create_seeder(request)
    except RuntimeError:
        return JSONResponse(status_code=503, content=_SEEDER_UNAVAILABLE_BODY)

    peers = seeder.list_peers(canonical_only=canonical_only)
    if trust is not None:
        peers = [p for p in peers if p.trust == trust]

    response = FederationPeerListResponse(peers=peers, total=len(peers))
    return SuccessResponse(data=response)


@router.get(
    "/peers/{key_id}",
    responses={
        404: {"description": "Peer not in local state"},
        503: {"description": "Edge runtime is not available (degraded mode)"},
    },
)
async def get_federation_peer(
    request: Request,
    auth: AuthObserverDep,
    key_id: str,
) -> Any:
    """Return the local state + Edge reachability for a single peer."""
    try:
        seeder = get_or_create_seeder(request)
    except RuntimeError:
        return JSONResponse(status_code=503, content=_SEEDER_UNAVAILABLE_BODY)

    state = seeder.get_local_state(key_id)
    if state is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "PEER_NOT_FOUND",
                "key_id": key_id,
                "detail": "No canonical or organic peer with this key_id is known locally.",
            },
        )

    edge = try_get_edge()
    if edge is None:
        return JSONResponse(status_code=503, content=EDGE_UNAVAILABLE_BODY)

    try:
        raw_reach = edge.peer_reachability(key_id)
    except Exception as exc:
        logger.warning("edge.peer_reachability(%s) failed: %s", sanitize_for_log(key_id), exc)
        return JSONResponse(status_code=503, content=EDGE_UNAVAILABLE_BODY)

    reachability = parse_edge_reachability(raw_reach)
    response = FederationPeerDetailResponse(peer=state, reachability=reachability)
    return SuccessResponse(data=response)


@router.put(
    "/peers/{key_id}/trust",
    responses={
        404: {"description": "Peer not in local state"},
        503: {"description": "BootstrapPeerSeeder is not yet wired"},
    },
)
async def set_federation_peer_trust(
    request: Request,
    auth: AuthSystemAdminDep,
    key_id: str,
    payload: FederationPeerTrustUpdateRequest,
) -> Any:
    """Set the user trust state on a known peer. SYSTEM_ADMIN only."""
    try:
        seeder = get_or_create_seeder(request)
    except RuntimeError:
        return JSONResponse(status_code=503, content=_SEEDER_UNAVAILABLE_BODY)

    try:
        await seeder.set_trust(key_id, payload.trust)
    except ValueError as exc:
        return JSONResponse(
            status_code=404,
            content={
                "error": "PEER_NOT_FOUND",
                "key_id": key_id,
                "detail": str(exc),
            },
        )

    updated = seeder.get_local_state(key_id)
    if updated is None:  # pragma: no cover - defensive: seeder just wrote it
        return JSONResponse(
            status_code=404,
            content={
                "error": "PEER_NOT_FOUND",
                "key_id": key_id,
                "detail": "Peer disappeared between set_trust and re-read.",
            },
        )
    return SuccessResponse(data=updated)


@router.put(
    "/peers/{key_id}/appearance",
    responses={
        404: {"description": "Peer not in local state"},
        503: {"description": "BootstrapPeerSeeder is not yet wired"},
    },
)
async def set_federation_peer_appearance(
    request: Request,
    auth: AuthSystemAdminDep,
    key_id: str,
    payload: FederationPeerAppearanceUpdateRequest,
) -> Any:
    """Set the local UI appearance for a known peer. SYSTEM_ADMIN only."""
    try:
        seeder = get_or_create_seeder(request)
    except RuntimeError:
        return JSONResponse(status_code=503, content=_SEEDER_UNAVAILABLE_BODY)

    try:
        await seeder.set_appearance(key_id, payload.appearance)
    except ValueError as exc:
        return JSONResponse(
            status_code=404,
            content={
                "error": "PEER_NOT_FOUND",
                "key_id": key_id,
                "detail": str(exc),
            },
        )

    updated = seeder.get_local_state(key_id)
    if updated is None:  # pragma: no cover - defensive: seeder just wrote it
        return JSONResponse(
            status_code=404,
            content={
                "error": "PEER_NOT_FOUND",
                "key_id": key_id,
                "detail": "Peer disappeared between set_appearance and re-read.",
            },
        )
    return SuccessResponse(data=updated)
