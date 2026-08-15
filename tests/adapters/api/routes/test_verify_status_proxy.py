"""`GET /v1/system/verify-status` must reach the node — verify never loaded without it.

THE BUG. The client polls CIRISVerify status every 30s. In agent mode it asks
`GET /v1/auth/attestation`, which the Python auth router served with a GET
handler until 2.9.14 deleted that router and proxied `/v1/auth/*` to the node.
The node's attestation route is POST-only, so the agent-mode GET became a 405 —
38 of them in a single session on a live install — and the verify card never
populated.

Measured on that install:

    :8080 /v1/auth/attestation      GET=405   <- what the client calls
    :4243 /v1/auth/attestation      GET=405   <- node: POST-only (the cause)
    :4243 /v1/system/verify-status  GET=200   <- where the data actually is
    :8080 /v1/system/verify-status  GET=404   <- no route exposed it

The data was one hop away. Verify is substrate-owned now, so the fix exposes the
node's read-only route rather than reinstating a Python attestation handler,
which would restore exactly the duplication #1028 removed.

The second test is the one that would catch a careless fix: `/v1/system/*` is
the BRAIN's prefix — agent, telemetry, runtime control all live there. A
catch-all proxy would have swallowed them, trading a broken verify card for a
broken everything-else.
"""

from __future__ import annotations

from typing import Any

import pytest


def test_exactly_one_system_path_is_proxied() -> None:
    """The proxy must claim ONE path, not the `/system/*` prefix.

    A `{path:path}` catch-all here would shadow the brain's own system routes.
    Asserting on the registered route rather than on behaviour, because the
    damage from getting this wrong shows up in unrelated endpoints that no test
    in this file would think to exercise.
    """
    from ciris_engine.logic.adapters.api.routes import auth_proxy

    system_routes = [
        r for r in auth_proxy.router.routes if "/system" in getattr(r, "path", "")
    ]
    assert len(system_routes) == 1, f"expected one system route, got {[r.path for r in system_routes]}"

    route = system_routes[0]
    assert route.path == "/system/verify-status", (
        "the proxy must name the exact path that moved to the substrate; a prefix "
        "or a {path:path} wildcard would shadow the brain's own /v1/system/* routes"
    )
    assert set(route.methods or set()) == {"GET"}, (
        f"read-only route; got {route.methods}. The node's verify-status is a GET, "
        "and accepting writes here would invent a surface the substrate does not have"
    )


@pytest.mark.asyncio
async def test_relays_the_nodes_answer_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    """Body and status pass through unchanged — no interpretation."""
    from ciris_engine.logic.adapters.api.routes import auth_proxy

    payload = b'{"verify_loaded":true,"key_id":"ciris-agent-bootstrap-xyz"}'
    seen: dict[str, Any] = {}

    class _Resp:
        content = payload
        status_code = 200
        headers = {"content-type": "application/json"}

    class _Client:
        def __init__(self, **kw: Any) -> None: ...
        async def __aenter__(self) -> "_Client":
            return self
        async def __aexit__(self, *a: Any) -> None: ...
        async def get(self, url: str, **kw: Any) -> _Resp:
            seen["url"] = url
            return _Resp()

    monkeypatch.setattr(auth_proxy.httpx, "AsyncClient", _Client)

    class _Req:
        method = "GET"
        headers: dict[str, str] = {}
        query_params: dict[str, str] = {}

    resp = await auth_proxy.proxy_verify_status_to_node(_Req())  # type: ignore[arg-type]

    assert seen["url"].endswith("/v1/system/verify-status")
    assert seen["url"].startswith(auth_proxy.NODE_UPSTREAM)
    assert resp.status_code == 200
    assert resp.body == payload


@pytest.mark.asyncio
async def test_unreachable_node_is_502_not_a_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """A node we cannot reach is infrastructure, not an attestation result.

    Answering 200-with-empty or 404 here would let the client render "not
    verified" for what is actually "could not ask" — the same collapse the auth
    proxy keeps 401 and 503 apart to avoid.
    """
    from ciris_engine.logic.adapters.api.routes import auth_proxy

    class _Boom:
        def __init__(self, **kw: Any) -> None: ...
        async def __aenter__(self) -> "_Boom":
            return self
        async def __aexit__(self, *a: Any) -> None: ...
        async def get(self, *a: Any, **kw: Any) -> Any:
            raise auth_proxy.httpx.ConnectError("node down")

    monkeypatch.setattr(auth_proxy.httpx, "AsyncClient", _Boom)

    class _Req:
        method = "GET"
        headers: dict[str, str] = {}
        query_params: dict[str, str] = {}

    resp = await auth_proxy.proxy_verify_status_to_node(_Req())  # type: ignore[arg-type]
    assert resp.status_code == 502


def test_the_failure_log_names_the_upstream_not_the_caller() -> None:
    """CWE-117: never log caller-controlled input.

    This route takes no path parameter, so there is nothing user-controlled to
    leak today — the guard is against someone adding one later and reaching for
    the request to make the message friendlier. Sonar S5145 was raised twice on
    this file already.
    """
    import inspect

    from ciris_engine.logic.adapters.api.routes import auth_proxy

    src = inspect.getsource(auth_proxy.proxy_verify_status_to_node)
    assert "NODE_UPSTREAM" in src
    assert "request.url" not in src and "request.path" not in src
