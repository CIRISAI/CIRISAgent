"""
Federation peer routes.

- ``PUT    /v1/federation/peers/{key_id}/trust``        (SYSTEM_ADMIN)
- ``PUT    /v1/federation/peers/{key_id}/appearance``   (SYSTEM_ADMIN)

The peer list + detail reads are served natively by the local
ciris-server node on port 4243 (shape-compatible superset); the Kotlin
client hits the node directly. Trust + appearance mutations remain here
and go through the seeder's locked write path.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from ciris_engine.logic.adapters.api.dependencies.auth import (
    AuthContext,
    require_system_admin,
)
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.federation_api import (
    FederationPeerAppearanceUpdateRequest,
    FederationPeerTrustUpdateRequest,
)

from .common import get_or_create_seeder

logger = logging.getLogger(__name__)

router = APIRouter()

AuthSystemAdminDep = Annotated[AuthContext, Depends(require_system_admin)]


_SEEDER_UNAVAILABLE_BODY = {
    "error": "BOOTSTRAP_SEEDER_UNAVAILABLE",
    "detail": (
        "BootstrapPeerSeeder is not wired (no time_service on app.state). "
        "Peer state cannot be read until the runtime has wired its services."
    ),
}


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
