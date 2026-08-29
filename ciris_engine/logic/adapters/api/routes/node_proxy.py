"""Forward node-owned `/v1/*` routes to the folded node, so the agent is one surface.

WHY

`/v1/setup/*` is SPLIT between the two services and neither half is complete:

    /v1/setup/list-models   brain 422 (exists)   node 404
    /v1/setup/models        brain 405 (exists)   node 404
    /v1/setup/claim-remote  brain 404            node 401 (exists)
    /v1/setup/status        brain 405 (exists)   node 405 (exists)

The client sends its whole setup flow to one base URL. Sent to the node, BYOK
dies on `listModels -> 404` and the wizard never offers a model. Sent to the
brain, ownership claiming dies instead. There is no address that works, which is
why the desktop BYOK gate could not pass.

The node cannot fix this from its side: its proxy is prefix-catch-all
(`/v1/X/{*rest}`), and a proxied prefix cannot coexist with a node-native route
underneath it — the router panics. `/v1/setup` has native routes on BOTH sides,
so it can never be proxied wholesale from there. `brain_adapter.py` records this
as "4243 needs per-method proxying (follow-up)".

So the agent becomes the complete surface instead. FastAPI matches routes in
registration order, so this catch-all is mounted LAST: anything the brain serves
itself still wins, and only genuinely unmatched `/v1` paths are forwarded. The
node's response is returned verbatim — status, body and content type — so a
client cannot tell the difference, which is the point.

This is the same move as `routes/node_identity.py`, generalised: the agent
surfaces the node rather than handing the client a second address to know about.

DELIBERATELY NOT A GENERAL PROXY. It forwards only what the brain does not serve,
never rewrites, and adds no authentication of its own — the node applies its own
(claim-remote answers 401 without a session, and still does through here).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["node-proxy"])

#: The folded node's read-API port (`ciris_engine/logic/runtime/node_fold.py`).
NODE_FOLD_PORT = 4243

#: Generous enough for a model listing that reaches a real provider, short enough
#: that a wedged node does not hold a client request open indefinitely.
_TIMEOUT_SECONDS = 30.0

#: Hop-by-hop headers that must not be copied between connections.
_DROP = {"connection", "keep-alive", "transfer-encoding", "upgrade", "content-length", "host"}


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def forward_to_node(path: str, request: Request) -> Response:
    """Forward one unmatched `/v1` request to the node, verbatim both ways."""
    url = f"http://127.0.0.1:{NODE_FOLD_PORT}/v1/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP}
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            upstream = await client.request(
                request.method,
                url,
                content=body or None,
                headers=headers,
                params=request.query_params,
            )
    except Exception as e:
        # The node being unreachable is a DIFFERENT fact from the route not
        # existing, and a client that cannot tell them apart retries the wrong
        # thing. 502 says "the thing behind me did not answer".
        logger.warning("Node proxy: %s %s failed: %s: %s", request.method, url, type(e).__name__, e)
        return Response(
            content=f'{{"detail":"The folded node did not answer {request.method} /v1/{path}."}}',
            status_code=502,
            media_type="application/json",
        )

    passthrough: dict[str, Any] = {k: v for k, v in upstream.headers.items() if k.lower() not in _DROP}
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=passthrough,
        media_type=upstream.headers.get("content-type"),
    )
