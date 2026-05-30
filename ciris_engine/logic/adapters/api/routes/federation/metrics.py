"""
Federation metrics route.

``GET /v1/federation/metrics`` (OBSERVER+)

Wraps ``Edge.metrics_snapshot()`` plus
``Edge.inline_text_subscriber_count()`` into a typed
``FederationMetricsResponse``. Polled by the mobile client for the
network-health surface.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Mapping

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from ciris_engine.logic.adapters.api.dependencies.auth import (
    AuthContext,
    require_observer,
)
from ciris_engine.logic.runtime.edge_runtime import try_get_edge
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.federation_api import FederationMetricsResponse

from .common import EDGE_UNAVAILABLE_BODY

logger = logging.getLogger(__name__)

router = APIRouter()

AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]


def _coerce_int_map(value: Any) -> dict[str, int]:
    """Coerce a dict-like into ``{str: int}`` dropping invalid entries."""
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, int] = {}
    for k, v in value.items():
        if not isinstance(k, str):
            continue
        try:
            out[k] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def _coerce_float_map(value: Any) -> dict[str, float]:
    """Coerce a dict-like into ``{str: float}`` dropping invalid entries."""
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, float] = {}
    for k, v in value.items():
        if not isinstance(k, str):
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    return out


@router.get(
    "/metrics",
    responses={
        503: {"description": "Edge runtime is not available (degraded mode)"},
    },
)
async def get_federation_metrics(
    request: Request,
    auth: AuthObserverDep,
) -> Any:
    """Return a typed snapshot of Edge metrics. OBSERVER+."""
    edge = try_get_edge()
    if edge is None:
        return JSONResponse(status_code=503, content=EDGE_UNAVAILABLE_BODY)

    try:
        snapshot = edge.metrics_snapshot()
    except Exception as exc:
        logger.warning("edge.metrics_snapshot() failed: %s", exc)
        return JSONResponse(status_code=503, content=EDGE_UNAVAILABLE_BODY)

    try:
        subscriber_count = int(edge.inline_text_subscriber_count())
    except Exception as exc:
        logger.warning("edge.inline_text_subscriber_count() failed: %s", exc)
        subscriber_count = 0

    if not isinstance(snapshot, Mapping):
        logger.warning(
            "edge.metrics_snapshot() returned unexpected type %s; surfacing empty maps",
            type(snapshot).__name__,
        )
        snapshot = {}

    response = FederationMetricsResponse(
        envelopes_sent_total=_coerce_int_map(snapshot.get("envelopes_sent_total")),
        envelopes_received_total=_coerce_int_map(snapshot.get("envelopes_received_total")),
        send_failures_total=_coerce_int_map(snapshot.get("send_failures_total")),
        verify_failures_total=_coerce_int_map(snapshot.get("verify_failures_total")),
        durable_queue_depth=_coerce_int_map(snapshot.get("durable_queue_depth")),
        transport_bytes_in_total=_coerce_int_map(snapshot.get("transport_bytes_in_total")),
        transport_bytes_out_total=_coerce_int_map(snapshot.get("transport_bytes_out_total")),
        peer_reachability_ratio=_coerce_float_map(snapshot.get("peer_reachability_ratio")),
        inline_text_subscriber_count=subscriber_count,
    )
    return SuccessResponse(data=response)
