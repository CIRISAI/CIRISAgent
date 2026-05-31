"""
Federation SAS route — Signal-style Short Authentication String for
verifying a peer key out-of-band.

``GET /v1/federation/peers/{key_id}/sas`` (OBSERVER+)

Returns BIP39-English words + numeric digits derived deterministically
by Edge from the ``(local_pub, peer_pub, protocol-constant)`` tuple.
Two operators displaying the same word list have confirmed they share
the same peer-key tuple (MITM-resistant verification).
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
from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.federation_api import FederationPeerSASResponse

from .common import EDGE_UNAVAILABLE_BODY

logger = logging.getLogger(__name__)

router = APIRouter()

AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]


@router.get(
    "/peers/{key_id}/sas",
    responses={
        404: {"description": "Peer not in federation directory"},
        503: {"description": "Edge runtime is not available (degraded mode)"},
    },
)
async def get_federation_peer_sas(
    request: Request,
    auth: AuthObserverDep,
    key_id: str,
) -> Any:
    """Return the SAS (words + digits) for a peer key. OBSERVER+."""
    edge = try_get_edge()
    if edge is None:
        return JSONResponse(status_code=503, content=EDGE_UNAVAILABLE_BODY)

    try:
        raw_words = edge.peer_sas(key_id)
        digits = edge.peer_sas_digits(key_id)
    except ValueError as exc:
        # Edge raises ValueError when the peer isn't in the federation
        # directory (or when the local signer key has the wrong shape).
        # Treat the former as 404, the latter as 503 — we can't
        # distinguish without parsing the message, so default to 404
        # which is the user-actionable case.
        logger.info("edge.peer_sas(%s) ValueError: %s", sanitize_for_log(key_id), exc)
        return JSONResponse(
            status_code=404,
            content={
                "error": "PEER_SAS_UNAVAILABLE",
                "key_id": key_id,
                "detail": str(exc),
            },
        )
    except Exception as exc:
        logger.warning("edge.peer_sas(%s) failed: %s", sanitize_for_log(key_id), exc)
        return JSONResponse(status_code=503, content=EDGE_UNAVAILABLE_BODY)

    # Normalize ``words`` to a list[str]. Edge returns a list-like; be
    # defensive against tuples or other iterables.
    if isinstance(raw_words, (list, tuple)):
        words = [str(w) for w in raw_words]
    else:
        words = [str(raw_words)]

    response = FederationPeerSASResponse(
        key_id=key_id,
        words=words,
        digits=str(digits),
    )
    return SuccessResponse(data=response)
