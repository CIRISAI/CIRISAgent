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

It forwards only what the brain does not serve, never rewrites, and adds no
authentication of its own — the node applies its own (claim-remote answers 401
without a session, and still does through here).

TWO TIERS (CIRISAgent#1213). The allow-list below forwarded four prefixes, so
every newer node surface — drive, files, notes, contacts, families, communities,
safety and more — answered 404 on the agent's port, and the client read that,
correctly by contract, as "this node is too old for this feature". Enumerating
prefixes is the same mistake the `/v1/setup` comment warns about one level down:
a list of someone else's surface is wrong the moment they add a route.

  * KNOWN node prefixes: forwarded; an unreachable node is a 502 ("the thing
    behind me did not answer"), as before.
  * ANY OTHER `/v1` path the brain does not serve: also forwarded, and the
    node's answer returned verbatim — including its own 404, so an absent route
    is still a 404. If the node cannot be reached, the answer is 404, NOT 502.
    That keeps the property the catch-all once broke (see NODE_OWNED_PREFIXES):
    a route can never appear to exist merely because the node is down, so a
    check that proves a bypass route is absent still proves it.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket

logger = logging.getLogger(__name__)

router = APIRouter(tags=["node-proxy"])

#: The folded node's read-API port (`ciris_engine/logic/runtime/node_fold.py`).
NODE_FOLD_PORT = 4243

#: Generous enough for a model listing that reaches a real provider, short enough
#: that a wedged node does not hold a client request open indefinitely.
_TIMEOUT_SECONDS = 30.0

#: Hop-by-hop headers that must not be copied between connections.
_DROP = {"connection", "keep-alive", "transfer-encoding", "upgrade", "content-length", "host"}


#: The KNOWN node prefixes: forwarded, and a 502 when the node is unreachable.
#: Other unmatched `/v1` paths are forwarded too since #1213, but answer 404 when
#: the node cannot be reached — see the module docstring.
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
#:
#: `:` is in that set. Chat room ids are `chat:pair:v1:<hex>`, so without it
#: every `/v1/chat/<room>/...` read on this port answered 404 "Not Found"
#: while the node had the room keyed and Ready (gate run 40703589749). A colon
#: is an ordinary pchar (RFC 3986 §3.3); it can only be read as a scheme in the
#: FIRST segment of a relative reference, and the outbound URL is always the
#: absolute `http://127.0.0.1:<port>/v1/...`, so it never is.
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._~/:-]*$")


def _forwardable_headers(items: Iterable[Tuple[str, str]]) -> Dict[str, str]:
    """Headers safe to put back on the wire.

    WHY THIS IS NOT A DICT COMPREHENSION ANY MORE.

    On a first run the client sends `Authorization: Bearer ` — the scheme with no
    token, because no session exists yet. Forwarding that verbatim makes h11
    refuse to build the request:

        LocalProtocolError: Illegal header value b'Bearer '

    which this proxy then reported as "the folded node did not answer", blaming a
    node that was listening and healthy. The claim step failed, setup completed
    UNCLAIMED, and the run went red pointing at the wrong component entirely.

    It stayed hidden because client 0.5.195 posted /v1/self/identity DIRECTLY to
    the node and never came through here; 0.5.196 routes it via the brain
    (CIRISClient#26), so this path saw its first empty bearer.

    Two rules, both required by RFC 9110 §5.5 and enforced by h11:
      * a value carries no leading or trailing whitespace
      * a value that is empty after stripping is not sent at all — it conveys
        nothing, and `Authorization: Bearer` alone would be a malformed
        credential rather than an absent one
    """
    out: Dict[str, str] = {}
    for key, value in items:
        if key.lower() in _DROP:
            continue
        cleaned = value.strip() if isinstance(value, str) else value
        if not cleaned:
            continue
        # A CREDENTIAL SCHEME WITH NO CREDENTIAL IS NOT A CREDENTIAL. Stripping
        # alone turns `Bearer ` into `Bearer`, which h11 accepts and the node then
        # has to interpret — presenting a MALFORMED token where the honest wire
        # says nothing at all. On first run there is genuinely no session yet, and
        # `/v1/self/identity` is unauthenticated by design at that point, so the
        # header must be absent rather than empty.
        if key.lower() == "authorization" and len(cleaned.split()) < 2:
            continue
        out[key] = cleaned
    return out


def _is_node_owned(path: str) -> bool:
    """Does the node own `/v1/<path>`?"""
    full = f"/v1/{path}"
    return any(full == p or full.startswith(p + "/") for p in NODE_OWNED_PREFIXES)


def _is_brain_owned(path: str) -> bool:
    """Is `/v1/<path>` under a prefix the node proxies back to this listener?"""
    from ciris_engine.logic.runtime.brain_adapter import _BRAIN_PREFIXES

    full = f"/v1/{path}"
    return any(full == p or full.startswith(p + "/") for p in _BRAIN_PREFIXES)


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
    return quote(path, safe="/:")


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def forward_to_node(path: str, request: Request) -> Response:
    """Forward one node-owned `/v1` request to the node, verbatim both ways."""
    if _is_brain_owned(path):
        # NEVER FORWARD A BRAIN PATH. The node proxies these prefixes back onto
        # this listener (brain_adapter._BRAIN_PREFIXES), so a brain path that no
        # brain route matched -- an absent route, e.g. a newer client asking a
        # 2.16.2 agent for /v1/agent/attachments/policy -- went agent -> node ->
        # agent -> node ... and every lap passed the rate limiter on the same
        # credential, until the empty bucket's 429 broke the loop. One request
        # drained the caller's whole minute (47 -> 0 in 1.5 s, CIRISClient gate
        # run 39820724677, where the node logged the one GET twice). The brain
        # does not serve it, so it does not exist.
        raise HTTPException(status_code=404, detail="Not Found")
    known_node_prefix = _is_node_owned(path)

    safe_path = _safe_forward_path(path)
    if safe_path is None:
        # Traversal, an absolute path, or a character with no business in a REST
        # path. Not forwarded, and not echoed back either.
        if not known_node_prefix:
            # Not a path any route could have: it does not exist.
            raise HTTPException(status_code=404, detail="Not Found")
        logger.warning("Node proxy: refusing a malformed path (%d chars)", len(path))
        raise HTTPException(status_code=400, detail="Malformed path")

    url = f"http://127.0.0.1:{NODE_FOLD_PORT}/v1/{safe_path}"
    headers = _forwardable_headers(request.headers.items())
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
        if not known_node_prefix:
            # Neither the brain nor a reachable node serves this path. Claiming
            # "the node did not answer" would make an absent route look like an
            # infrastructure problem (and would let a route look present because
            # the node is down) -- the honest answer is that it does not exist.
            raise HTTPException(status_code=404, detail="Not Found")
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

    passthrough: Dict[str, str] = _forwardable_headers(upstream.headers.items())
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=passthrough,
        media_type=upstream.headers.get("content-type"),
    )


# ---------------------------------------------------------------------------
# WebSocket forwarding: a call's frames socket (2.23.2).
# ---------------------------------------------------------------------------

#: The node's socket paths a client opens on this listener. A call is an HTTP join (forwarded above) and then a
#: WebSocket at the path the join answers (``frames_socket``), by default ``/v1/chat/<room>/call/frames``, or
#: ``.../call/share/frames`` for a screen share, with a single-use ``?ticket=``. The desktop app points
#: CIRIS_NODE_URL at this listener (desktop_launcher), so without this every upgrade answered 403, the app left at
#: once, and every call ended ``why="left"`` with nothing published (Eric's laptop, 2026-11-21).
_NODE_SOCKET_PATH = re.compile(r"^chat/[A-Za-z0-9._~:-]+/call(?:/share)?/frames$")

#: Close codes that may not be sent on the wire (RFC 6455 section 7.4.1): reported locally, never sent.
_UNSENDABLE_CLOSE = {1005, 1006, 1015}

_SOCKET_OPEN_TIMEOUT_SECONDS = 10.0


def _sendable_close(code: Optional[int], fallback: int) -> int:
    if code is None or code in _UNSENDABLE_CLOSE:
        return fallback
    return code


async def _deny(websocket: WebSocket, status_code: int, detail: str) -> None:
    """Refuse the upgrade with an HTTP status the client can read (the node's own, when it refused)."""
    try:
        await websocket.send_denial_response(
            Response(content=json.dumps({"detail": detail}), status_code=status_code, media_type="application/json")
        )
    except Exception:  # noqa: BLE001 - a server without the denial extension: a plain close (the client sees 403)
        await websocket.close(code=1008)


@router.websocket("/{path:path}")
async def forward_socket_to_node(websocket: WebSocket, path: str) -> None:
    """Forward one node socket (a call's frames) to the node: frames both ways, close both ways, with its code.

    The query string (the single-use ticket) and the Authorization header go through unchanged. A close from the
    app reaches the node as a close (the node reads that as ``why="left"``; an error as ``lost``), and the node's
    close reaches the app with its code. A refused upgrade answers the node's own status (401 without a ticket).
    """
    import asyncio

    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed, InvalidStatus

    if _is_brain_owned(path) or not (_NODE_SOCKET_PATH.match(path) or _is_node_owned(path)):
        await _deny(websocket, 404, "Not Found")
        return
    safe_path = _safe_forward_path(path)
    if safe_path is None:
        logger.warning("Node proxy: refusing a malformed socket path (%d chars)", len(path))
        await _deny(websocket, 400, "Malformed path")
        return
    query = websocket.url.query
    url = f"ws://127.0.0.1:{NODE_FOLD_PORT}/v1/{safe_path}" + (f"?{query}" if query else "")
    auth = websocket.headers.get("authorization")
    headers = _forwardable_headers([("Authorization", auth)] if auth else [])
    subprotocols = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
    try:
        upstream = await connect(
            url,
            additional_headers=headers,
            subprotocols=subprotocols or None,  # type: ignore[arg-type]
            max_size=None,
            open_timeout=_SOCKET_OPEN_TIMEOUT_SECONDS,
            ping_interval=None,  # the app and the node keep their own liveness; this hop adds none
        )
    except InvalidStatus as refused:
        await _deny(websocket, refused.response.status_code, "The node refused the socket.")
        return
    except Exception as e:  # noqa: BLE001 - the node did not answer
        logger.warning("Node proxy: socket /v1/%s failed: %s", safe_path, type(e).__name__)
        await _deny(websocket, 502, f"The folded node did not answer the socket /v1/{safe_path}.")
        return

    await websocket.accept(subprotocol=upstream.subprotocol)

    async def app_to_node() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                await upstream.close(code=_sendable_close(message.get("code"), 1000), reason=message.get("reason") or "")
                return
            if message.get("bytes") is not None:
                await upstream.send(message["bytes"])
            elif message.get("text") is not None:
                await upstream.send(message["text"])

    async def node_to_app() -> None:
        try:
            async for frame in upstream:
                if isinstance(frame, (bytes, bytearray)):
                    await websocket.send_bytes(bytes(frame))
                else:
                    await websocket.send_text(frame)
        except ConnectionClosed:
            pass
        code = _sendable_close(upstream.close_code, 1011)
        try:
            await websocket.close(code=code, reason=upstream.close_reason or "")
        except Exception:  # noqa: BLE001 - the app already went
            pass

    tasks = [asyncio.ensure_future(app_to_node()), asyncio.ensure_future(node_to_app())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            if task.exception() is not None and not isinstance(task.exception(), ConnectionClosed):
                logger.warning("Node proxy: socket /v1/%s ended: %s", safe_path, type(task.exception()).__name__)
    finally:
        await upstream.close()
