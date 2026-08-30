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

import json
import logging
import re
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["node-proxy"])

#: The folded node's read-API port (`ciris_engine/logic/runtime/node_fold.py`).
NODE_FOLD_PORT = 4243

#: Generous enough for a model listing that reaches a real provider, short enough
#: that a wedged node does not hold a client request open indefinitely.
_TIMEOUT_SECONDS = 30.0

#: Hop-by-hop headers that must not be copied between connections.
_DROP = {"connection", "keep-alive", "transfer-encoding", "upgrade", "content-length", "host"}


#: The ONLY paths forwarded. Everything else keeps answering 404.
#:
#: This started as a catch-all over `/v1/{path:path}` and that was wrong. Every
#: unknown path then answered 502 instead of 404, which broke two tests and, more
#: importantly, one of them for a real reason:
#:
#:     tests/adapters/api/test_partnership_endpoint.py
#:         TestNoBypassEndpoints::test_no_manual_defer_endpoint
#:
#: That test asserts a manual-defer endpoint DOES NOT EXIST. With a catch-all,
#: "this endpoint is absent" and "this endpoint exists but the node is down"
#: produce the same answer — so a check whose whole job is proving a bypass route
#: is missing could no longer prove anything. A safety assertion that cannot
#: distinguish absent from unreachable is not a safety assertion.
#:
#: So: an allow-list of the substrate's own surface, mirroring
#: `brain_adapter._SUBSTRATE_PREFIXES` (which is the node's side of the same
#: split). `/v1/system/health` is deliberately NOT here — the brain serves that
#: itself and must keep serving it, because it is where `role: agent` comes from.
NODE_OWNED_PREFIXES = (
    "/v1/federation",
    "/v1/self",
    "/v1/accord",
    # `/v1/setup` is the SPLIT prefix: the brain owns list-models/models/status,
    # the node owns claim-remote/owned-nodes. Registration order settles it —
    # every brain setup route is mounted before this catch-all and wins — so
    # "unmatched under /v1/setup" means "the node's".
    #
    # Listed as the whole prefix rather than route by route on purpose. The first
    # version named `/v1/setup/claim-remote` alone; `/v1/setup/owned-nodes`
    # existed too, was not in the list, and 404'd — which left the app stuck on
    # the Setup screen forever on the SECOND boot, because ownership could not be
    # probed. Enumerating one half of a split someone else controls is a list
    # that is wrong the moment they add a route.
    "/v1/setup",
)


#: A forwardable path segment. Deliberately strict: the set a REST route needs
#: and nothing else.
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._~/-]*$")


def _is_node_owned(path: str) -> bool:
    """Does the node own `/v1/<path>`?"""
    full = f"/v1/{path}"
    return any(full == p or full.startswith(p + "/") for p in NODE_OWNED_PREFIXES)


def _safe_forward_path(path: str) -> Optional[str]:
    """The path to forward, or None when it must not be forwarded at all.

    The prefix check alone is not enough to make this safe. `/v1/setup/../../x`
    starts with `/v1/setup/` and so passes it, and the traversal then resolves on
    the way out — the request reaches a node route the prefix was supposed to
    fence off. Sonar flagged the same shape as "do not construct the URL's path
    from user-controlled data", and it is right: this builds an outbound URL from
    the inbound one.

    Two defences, because either alone is thin:
      * REJECT any `..` segment, absolute path, or character outside a
        conservative REST set — no encoded separators, no CR/LF (request
        splitting), no scheme-ish content.
      * PERCENT-ENCODE what survives, so nothing that does get through is
        re-interpreted as structure by the node's router.

    The host is a hardcoded loopback literal and never derived from input; this
    guards the PATH, which is the half that is.
    """
    if not _SAFE_PATH.match(path):
        return None
    if path.startswith("/") or ".." in path.split("/"):
        return None
    return quote(path, safe="/")


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def forward_to_node(path: str, request: Request) -> Response:
    """Forward one node-owned `/v1` request to the node, verbatim both ways."""
    if not _is_node_owned(path):
        # Not ours and not the node's: the honest answer is that it does not
        # exist. Returning anything else makes every absent route look like an
        # infrastructure problem.
        raise HTTPException(status_code=404, detail="Not Found")

    safe_path = _safe_forward_path(path)
    if safe_path is None:
        # Traversal, an absolute path, or a character with no business in a REST
        # path. Not forwarded, and not echoed back either.
        logger.warning("Node proxy: refusing a malformed path (%d chars)", len(path))
        raise HTTPException(status_code=400, detail="Malformed path")

    url = f"http://127.0.0.1:{NODE_FOLD_PORT}/v1/{safe_path}"
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
        # Log the VALIDATED path, not the raw one: this line lands in a shared
        # log and the input is attacker-shaped by definition (Sonar: "do not log
        # user-controlled data"). safe_path is charset-checked and encoded.
        logger.warning("Node proxy: %s /v1/%s failed: %s: %s", request.method, safe_path, type(e).__name__, e)
        return Response(
            content=json.dumps({"detail": f"The folded node did not answer {request.method} /v1/{safe_path}."}),
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
