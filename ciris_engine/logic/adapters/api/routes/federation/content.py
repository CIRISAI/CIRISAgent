"""
Federation content route.

``POST /v1/federation/content/{content_id}`` (SYSTEM_ADMIN)

Body picks the peer to ask + per-fetch timeout. Wraps
``Edge.fetch_content(peer_key_id, sha256, timeout_ms)`` and returns
either the base64-encoded payload (200) or a structured error
envelope (404/503).

``content_id`` is the URL-path SHA-256 (64 chars of hex).
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Mapping

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from ciris_engine.logic.adapters.api.dependencies.auth import (
    AuthContext,
    require_system_admin,
)
from ciris_engine.logic.runtime.edge_runtime import try_get_edge
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.federation_api import (
    FederationContentFetchRequest,
    FederationContentResponse,
)

from .common import EDGE_UNAVAILABLE_BODY

logger = logging.getLogger(__name__)

router = APIRouter()

AuthSystemAdminDep = Annotated[AuthContext, Depends(require_system_admin)]

_SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")


@router.post(
    "/content/{content_id}",
    responses={
        400: {"description": "content_id is not a 64-char hex SHA-256"},
        404: {"description": "Peer reported content_miss"},
        503: {"description": "Edge runtime is not available or fetch transport failed"},
    },
)
async def fetch_federation_content(
    request: Request,
    auth: AuthSystemAdminDep,
    content_id: str,
    payload: FederationContentFetchRequest,
) -> Any:
    """Fetch content from a peer by SHA-256 content id. SYSTEM_ADMIN only."""
    if not _SHA256_HEX.match(content_id):
        return JSONResponse(
            status_code=400,
            content={
                "error": "INVALID_CONTENT_ID",
                "detail": "content_id must be a 64-character hex SHA-256 digest.",
            },
        )

    edge = try_get_edge()
    if edge is None:
        return JSONResponse(status_code=503, content=EDGE_UNAVAILABLE_BODY)

    try:
        result = edge.fetch_content(
            peer_key_id=payload.peer_key_id,
            sha256=content_id,
            timeout_ms=payload.timeout_ms,
        )
    except ValueError as exc:
        # Edge raises ValueError for malformed sha256 — we already
        # validated, so this is "shouldn't happen". Surface as 400.
        logger.info("edge.fetch_content rejected sha256=%s: %s", content_id, exc)
        return JSONResponse(
            status_code=400,
            content={
                "error": "INVALID_CONTENT_ID",
                "detail": str(exc),
            },
        )
    except Exception as exc:
        # Timeout / transport failure.
        logger.warning("edge.fetch_content(%s) failed: %s", content_id, exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": "FETCH_FAILED",
                "detail": str(exc),
            },
        )

    if not isinstance(result, Mapping):
        logger.warning(
            "edge.fetch_content returned unexpected type %s",
            type(result).__name__,
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": "FETCH_FAILED",
                "detail": "Edge returned an unexpected fetch_content shape.",
            },
        )

    kind = result.get("kind")
    if kind == "content_miss":
        return JSONResponse(
            status_code=404,
            content={
                "error": "CONTENT_MISS",
                "content_id": content_id,
                "peer_key_id": payload.peer_key_id,
                "reason": str(result.get("reason", "unknown")),
            },
        )

    if kind != "bytes":
        return JSONResponse(
            status_code=503,
            content={
                "error": "FETCH_FAILED",
                "detail": f"Edge returned unknown fetch_content kind: {kind!r}",
            },
        )

    raw_bytes = result.get("bytes")
    if not isinstance(raw_bytes, (bytes, bytearray)):
        return JSONResponse(
            status_code=503,
            content={
                "error": "FETCH_FAILED",
                "detail": "Edge fetch_content returned non-bytes payload.",
            },
        )

    payload_b64 = base64.b64encode(bytes(raw_bytes)).decode("ascii")
    response = FederationContentResponse(
        content_id=content_id,
        content_type=None,
        payload_base64=payload_b64,
        size_bytes=len(raw_bytes),
        fetched_at=datetime.now(timezone.utc),
    )
    return SuccessResponse(data=response)
