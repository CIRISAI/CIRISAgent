"""`GET /v1/identity` — the node identity, surfaced by the agent.

WHY THIS LIVES ON THE BRAIN

The published CIRIS client boots against `GET /v1/identity`. That is a NODE
route: the folded node serves it on 4243, and until now the brain answered 404,
so a client pointed at the agent looped its readiness probe forever, never left
the Startup screen, and composed no UI at all.

The obvious workaround — point the client at 4243 instead — trades one break for
a worse one. `/v1/system` is NOT in the node's proxied brain prefixes
(`brain_adapter._BRAIN_PREFIXES`), so the node answers `/v1/system/health`
NATIVELY with a node-shaped document that has no `role` field. The client keys
its surface on `role`, and an agent that cannot say `role: "agent"` is rendered
as a bare node: no LLM configuration screen, because a node has no brain to
configure. We ARE the AI; that screen is required, not optional.

So the client points at the agent, and the agent surfaces the node fact it needs.
That is the layering this codebase already follows elsewhere — the fabric
produces, the agent surfaces. The alternative (proxying `/v1/system` onto 4243)
cannot work as a prefix catch-all anyway: it would collide with the node's own
native routes under that prefix and panic the router.

FAILS HONESTLY. If the node is not reachable this returns 503 rather than a
synthesised identity. A readiness probe that succeeds against a node that is not
there is worse than one that fails: the client would proceed to a surface whose
backing service does not exist.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["identity"])

#: The folded node's read-API port (`ciris_engine/logic/runtime/node_fold.py`).
NODE_FOLD_PORT = 4243

#: Short: this is a liveness probe on a loopback socket, not a data fetch. A
#: client blocked on it renders nothing, so a slow answer is as bad as no answer.
_NODE_TIMEOUT_SECONDS = 5.0


@router.get("/identity")
async def get_node_identity(request: Request) -> Dict[str, Any]:
    """The folded node's identity aggregate.

    Deliberately UNAUTHENTICATED, like the node's own `/v1/identity`: it is the
    first call a client makes, before any session exists, and gating it would
    make readiness depend on credentials the client cannot have yet. The payload
    is public key material and wire metadata — what a peer would receive anyway.
    """
    url = f"http://127.0.0.1:{NODE_FOLD_PORT}/v1/identity"
    try:
        async with httpx.AsyncClient(timeout=_NODE_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except Exception as e:
        logger.warning("Node identity unreachable at %s: %s: %s", url, type(e).__name__, e)
        raise HTTPException(
            status_code=503,
            detail=(
                "The folded node is not reachable. This agent carries a node; if the "
                "node fold is disabled (CIRIS_NODE_FOLD=false) or still booting, there "
                "is no identity to report yet."
            ),
        ) from e

    if response.status_code != 200:
        logger.warning("Node identity returned HTTP %s from %s", response.status_code, url)
        raise HTTPException(
            status_code=503,
            detail=f"The folded node answered HTTP {response.status_code} for its identity.",
        )

    payload: Dict[str, Any] = response.json()
    return payload
