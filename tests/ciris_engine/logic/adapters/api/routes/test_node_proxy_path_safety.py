"""The node proxy builds an outbound URL from an inbound one. Guard the path.

Sonar flagged this as MAJOR — "do not construct the URL's path from
user-controlled data" — and it was right. The prefix allow-list alone is not
enough: `/v1/setup/../../admin` starts with `/v1/setup/` and so passes it, and
the traversal then resolves on the way out, reaching a node route the prefix was
supposed to fence off.

The host is a hardcoded loopback literal and is never derived from input. This
file is about the PATH, which is the half that is.

There is a second reason to keep these cases: the proxy's whole purpose is to
make the agent one address, so anything that gets through here reaches the
substrate's own surface — federation, self, accord, and the ownership claim.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.adapters.api.routes.node_proxy import _is_node_owned, _safe_forward_path


@pytest.mark.parametrize(
    "path",
    [
        "setup/owned-nodes",
        "setup/claim-remote",
        "federation/consent",
        "self/identity",
        "accord/canonical/servers",
        "federation/keys/abc-123_x.y~z",
    ],
)
def test_ordinary_routes_forward_unchanged(path: str) -> None:
    """A real REST path must survive exactly, or the proxy breaks the product."""
    assert _safe_forward_path(path) == path


@pytest.mark.parametrize(
    ("path", "why"),
    [
        ("setup/../../admin", "traversal that still satisfies the prefix check"),
        ("../secrets", "traversal from the root"),
        ("setup/..", "bare parent segment"),
        ("/etc/passwd", "absolute path"),
        ("setup/x?a=b", "query injection into the outbound URL"),
        ("setup/x#frag", "fragment injection"),
        ("setup/x\r\nHost: evil", "CRLF request splitting"),
        ("setup/x\nY: z", "bare LF"),
        ("setup/x%2F..%2Fy", "percent-encoded separator, decoded downstream"),
        ("setup/a b", "space"),
        ("setup/<script>", "angle brackets"),
        ("setup/x@evil.com", "authority-shaped content"),
        ("setup/x\x00y", "NUL"),
    ],
)
def test_dangerous_paths_are_refused(path: str, why: str) -> None:
    """None means the request is rejected outright, never forwarded."""
    assert _safe_forward_path(path) is None, why


def test_the_prefix_check_alone_would_have_allowed_the_traversal() -> None:
    """Why both checks exist.

    This is the case that makes the point: the allow-list says yes, and only the
    path validator says no. Remove either and the other does not cover it.
    """
    traversal = "setup/../../admin"
    assert _is_node_owned(traversal) is True, "the prefix check passes it"
    assert _safe_forward_path(traversal) is None, "the path check must catch it"


@pytest.mark.parametrize(
    ("path", "owned"),
    [
        ("setup/owned-nodes", True),
        ("federation/consent", True),
        ("self/identity", True),
        ("system/health", False),
        ("wa/manual-defer", False),
        ("definitely-not-a-route", False),
    ],
)
def test_only_the_substrate_surface_is_forwarded(path: str, owned: bool) -> None:
    """Which prefixes are KNOWN node surface (502 when the node is down).

    Since #1213 other unmatched paths are forwarded too, but answer 404 when the
    node cannot be reached -- see TestUnmatchedPathsReachTheNode.

    `wa/manual-defer` is not arbitrary: TestNoBypassEndpoints asserts that route
    does NOT exist. When this proxy was a catch-all it answered 502 for it, and
    a check whose purpose is proving a bypass route is absent could no longer
    tell absent from unreachable.
    """
    assert _is_node_owned(path) is owned


class TestHeaderForwarding:
    """`Authorization: Bearer ` on first run made the proxy blame the node.

    Client 0.5.196 routes `POST /v1/self/identity` through the brain instead of
    posting straight to :4243 (CIRISClient#26), so this proxy saw its first
    request carrying a bearer scheme with no token — there is no session yet on a
    first run. h11 refuses to put that on the wire:

        LocalProtocolError: Illegal header value b'Bearer '

    which this proxy reported as "the folded node did not answer", against a node
    that was listening and healthy. Setup then completed UNCLAIMED and the run
    went red pointing at the wrong component.

    The lesson worth pinning is not the strip: it is that a proxy must not blame
    upstream for a request it never managed to send.
    """

    def test_the_exact_header_that_broke_it(self) -> None:
        from ciris_engine.logic.adapters.api.routes.node_proxy import _forwardable_headers

        out = _forwardable_headers([("Authorization", "Bearer "), ("Content-Type", "application/json")])
        assert "Authorization" not in out, "a bearer scheme with no token must not be forwarded"
        assert out["Content-Type"] == "application/json", "unrelated headers must survive"

    def test_a_real_token_is_untouched(self) -> None:
        from ciris_engine.logic.adapters.api.routes.node_proxy import _forwardable_headers

        assert _forwardable_headers([("Authorization", "Bearer abc123")]) == {"Authorization": "Bearer abc123"}

    def test_basic_auth_survives(self) -> None:
        """The rule is 'scheme with no credential', not 'anything that isn't Bearer'."""
        from ciris_engine.logic.adapters.api.routes.node_proxy import _forwardable_headers

        creds = "Basic dXNlcjpwdw=="
        assert _forwardable_headers([("Authorization", creds)]) == {"Authorization": creds}

    def test_whitespace_only_and_empty_values_are_dropped(self) -> None:
        """h11 rejects leading/trailing whitespace; an empty value carries nothing."""
        from ciris_engine.logic.adapters.api.routes.node_proxy import _forwardable_headers

        out = _forwardable_headers([("X-Empty", ""), ("X-Spaces", "   "), ("Accept", " */* ")])
        assert out == {"Accept": "*/*"}

    def test_hop_by_hop_headers_still_dropped(self) -> None:
        from ciris_engine.logic.adapters.api.routes.node_proxy import _forwardable_headers

        out = _forwardable_headers([("Host", "x"), ("Connection", "keep-alive"), ("Accept", "*/*")])
        assert out == {"Accept": "*/*"}


class TestUnmatchedPathsReachTheNode:
    """#1213: the node's newer surfaces (drive, notes, contacts, families...) 404'd on
    the agent's port, so the client told people their node was too old. Unmatched
    `/v1` paths now reach the node -- without ever letting a route look present
    because the node is down."""

    @staticmethod
    def _client(monkeypatch, *, node_status=None, node_down=False):
        import httpx
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from ciris_engine.logic.adapters.api.routes import node_proxy

        seen = []

        class _FakeAsyncClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def request(self, method, url, **kwargs):
                seen.append((method, url))
                if node_down:
                    raise httpx.ConnectError("connection refused")
                return httpx.Response(node_status, json={"from": "node"}, headers={"content-type": "application/json"})

        monkeypatch.setattr(node_proxy.httpx, "AsyncClient", _FakeAsyncClient)
        app = FastAPI()
        app.include_router(node_proxy.router, prefix="/v1")
        return TestClient(app), seen

    @pytest.mark.parametrize(
        "path", ["drive/list", "notes", "contacts", "families/abc", "communities", "safety/moderation"]
    )
    def test_node_surfaces_are_forwarded(self, monkeypatch, path):
        client, seen = self._client(monkeypatch, node_status=200)
        r = client.get(f"/v1/{path}")
        assert r.status_code == 200 and r.json() == {"from": "node"}
        assert seen == [("GET", f"http://127.0.0.1:4243/v1/{path}")]

    def test_the_nodes_own_404_comes_back_as_404(self, monkeypatch):
        client, _ = self._client(monkeypatch, node_status=404)
        assert client.post("/v1/partnership/discord_123/defer", json={}).status_code == 404

    def test_an_unreachable_node_never_makes_an_unknown_route_look_present(self, monkeypatch):
        """The property the old catch-all broke: absent must not become 502."""
        client, _ = self._client(monkeypatch, node_down=True)
        assert client.post("/v1/partnership/discord_123/defer", json={}).status_code == 404
        assert client.get("/v1/drive/list").status_code == 404

    def test_a_known_node_prefix_still_reports_the_node_as_down(self, monkeypatch):
        client, _ = self._client(monkeypatch, node_down=True)
        assert client.get("/v1/setup/owned-nodes").status_code == 502

    def test_a_malformed_unknown_path_is_absent_not_forwarded(self, monkeypatch):
        client, seen = self._client(monkeypatch, node_status=200)
        assert client.get("/v1/drive/a b").status_code == 404
        assert seen == []
