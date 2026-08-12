"""`/v1/auth/*` — served by the NODE, reverse-proxied from the brain's listener.

NOT MOUNTED YET. Held for ciris-server 0.5.168 — see CIRISServer#389. This is
written and verified faithful (direct-to-node and through-this-proxy return
byte-identical responses), but the node refuses the owner credential the Python
accepts, and a failed login on the node writes NOTHING to the log, so the
failing branch cannot be localized: `resolve_login` miss and hash mismatch are
the same string on the wire (correctly — not leaking account existence is the
point) and neither leaves a trace anywhere else. Mounting this today would trade
a working login for one nobody can debug. Re-mount is two lines in `app.py`.

CIRISAgent#1028 / ciris-server 0.5.165 finished the Rust port of this surface, so
the 2752 lines of `routes/auth.py` this module replaces were a second
implementation of something the node already owned. The node is authoritative for
identity — `brain_adapter._SUBSTRATE_PREFIXES` has said so, listing `/v1/auth`
with the note "node owns identity" — but the client never reached it, because the
client's front door is the brain's :8080 and the node's surface is :4243. Two
implementations, and the one users met was the copy.

Measured on a set-up instance before this change:

    :8080  /v1/auth/oauth/providers -> 401   (Python's)     <- what the client got
    :4243  /v1/auth/oauth/providers -> 200   (the node's)   <- what was authoritative

That gap is not academic. The Python's `create_oauth_user` wrote `pubkey: ""`,
which persist refuses, so OAuth users lived in an in-memory dict with no key and
did not survive a restart; and `_decode_google_jwt_locally` read a Google JWT's
claims WITHOUT verifying its signature. Both are fixed in the node's port, and
neither could be fixed by us as long as the copy kept being the one that ran.

So this forwards rather than reimplements. Nothing here should ever grow a
decision — the moment this module starts deciding something about identity, the
duplication is back.

WHY A PROXY AND NOT A PORT CHANGE: pointing the client at :4243 is the topology
the fold is heading for, but it is a client-visible move (base URL, bundled
profiles, every saved node) and this release is not the place. The prefix arrives
at :8080 and leaves for the node; when the front door moves, this module is
deleted rather than rewritten.

REDIRECTS ARE RESPONSES HERE. `/v1/auth/oauth/{provider}/login` answers 307 with a
`Location` pointing at Google. An HTTP client that follows redirects by default
would chase it, and the caller would receive Google's HTML instead of the
redirect it must hand to a browser. `follow_redirects=False` is load-bearing.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Set

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

#: The node's substrate listener. Fixed at 4243 by the fold (``node_fold``); the
#: env var exists for tests that stand the node up elsewhere.
NODE_UPSTREAM = os.environ.get("CIRIS_NODE_HTTP_URL", "http://127.0.0.1:4243")

#: Hop-by-hop headers, which describe THIS connection and must not be relayed
#: onto another one (RFC 9110 §7.6.1). `host` must be recomputed for the upstream
#: and `content-length` re-derived from the body httpx actually sends — relaying
#: a stale one truncates or hangs the request.
_HOP_BY_HOP: Set[str] = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

#: A single `/v1/auth/*` sub-path. Deliberately narrow: the node's auth surface is
#: `login`, `me`, `refresh`, `logout`, `attestation`, `owner-hint`, `api-keys/{id}`,
#: `oauth/{provider}/login|callback`, `native/{google,apple}`, `device/*`.
#: Everything in that set is [a-z0-9], `-`, `_`, `.` and `/`.
_SAFE_SUBPATH = re.compile(r"^[A-Za-z0-9._~/-]*$")


def _safe_subpath(path: str) -> str:
    """Validate the caller-supplied sub-path before it becomes an upstream URL.

    This handler forwards `/v1/auth/{path:path}`, so `path` is user-controlled and
    is concatenated into the node's URL. Without this, `..` segments escape the
    `/v1/auth/` prefix — httpx normalises them — and the proxy becomes a way to
    reach ANY node endpoint through a route that authenticates nothing. The node
    would answer as if we had asked. (Sonar S7044.)

    An allowlist, not a denylist: `..` alone is not enough, because encodings and
    backslashes reach the same place by other spellings. Anything outside the
    character set the node's own auth paths use is refused.
    """
    if not _SAFE_SUBPATH.match(path) or ".." in path or path.startswith("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid auth path")
    return path


@router.api_route(
    "/auth/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy_auth_to_node(path: str, request: Request) -> Response:
    """Relay one `/v1/auth/*` call to the node and return what it says.

    Deliberately opaque: no status interpretation, no body parsing, no schema.
    Whatever the node decides about identity is what the caller sees, including
    its errors — a proxy that "helpfully" rewrites an upstream failure is how the
    two implementations diverge again.
    """
    url = f"{NODE_UPSTREAM}/v1/auth/{_safe_subpath(path)}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            upstream = await client.request(
                request.method,
                url,
                params=request.query_params,
                headers=headers,
                content=await request.body(),
            )
    except httpx.RequestError as exc:
        # The node not being reachable is an infrastructure failure, not an auth
        # decision. 502 says so; 401 would tell the caller their credentials were
        # rejected by something that never saw them.
        # Log the UPSTREAM, never the caller's path — it is user-controlled, and a
        # CRLF in it forges log lines (Sonar S5145). The path is already validated
        # above, but a log statement should not depend on a check elsewhere staying
        # correct. The exception text is the diagnostic value here anyway.
        logger.error("auth proxy could not reach the node at %s: %s", NODE_UPSTREAM, exc)
        return Response(
            content=b'{"detail":"identity service unavailable"}',
            status_code=502,
            media_type="application/json",
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP},
    )
