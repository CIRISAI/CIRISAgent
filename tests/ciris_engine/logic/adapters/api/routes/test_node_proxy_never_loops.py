"""The agent's node proxy must never forward a path the node proxies straight back.

The node reverse-proxies the brain prefixes (/v1/agent, /v1/telemetry, ...) onto
the agent's :8080. The agent's catch-all forwarded every unmatched /v1 path to
the node. So a brain path no brain route matched -- an absent route, such as a
newer client asking a 2.16.2 agent for /v1/agent/attachments/policy -- went
agent -> node -> agent -> ..., and every lap passed the rate limiter on the
caller's credential until the empty bucket's 429 ended it. One GET drained the
caller's minute (CIRISClient gate run 39820724677: 47 -> 0 in 1.5 s, and the
node logged the single GET twice).
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes import node_proxy
from ciris_engine.logic.runtime.brain_adapter import _BRAIN_PREFIXES


class _RecordingClient:
    calls: List[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_RecordingClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        _RecordingClient.calls.append(url)
        return httpx.Response(200, json={"ok": True})


@pytest.fixture()
def client():
    _RecordingClient.calls = []
    app = FastAPI()
    app.include_router(node_proxy.router, prefix="/v1")
    with patch.object(node_proxy.httpx, "AsyncClient", _RecordingClient):
        yield TestClient(app)


@pytest.mark.parametrize("prefix", _BRAIN_PREFIXES)
def test_an_absent_brain_route_is_a_404_and_never_leaves_the_agent(client, prefix):
    response = client.get(f"{prefix}/no-such-route")
    assert response.status_code == 404
    assert _RecordingClient.calls == [], "forwarded to the node, which would proxy it straight back"


def test_the_route_from_the_incident_is_not_forwarded(client):
    assert client.get("/v1/agent/attachments/policy").status_code == 404
    assert _RecordingClient.calls == []


@pytest.mark.parametrize("path", ["/v1/setup/owned-nodes", "/v1/federation/peers", "/v1/contacts"])
def test_node_routes_still_forward(client, path):
    assert client.get(path).status_code == 200
    assert _RecordingClient.calls == [f"http://127.0.0.1:{node_proxy.NODE_FOLD_PORT}{path}"]


def test_no_prefix_is_both_the_nodes_and_the_brains():
    for brain in _BRAIN_PREFIXES:
        for node in node_proxy.NODE_OWNED_PREFIXES:
            assert not (brain == node or brain.startswith(node + "/") or node.startswith(brain + "/")), (brain, node)
