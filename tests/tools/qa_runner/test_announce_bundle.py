"""The announce-bundle check names which side is short (CIRISAgent#1144 Lesson 1)."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx
import pytest

from tools.qa_runner.announce_bundle import check_announce_bundle

_ROWS_OK = [
    {"role": "owner_key", "key_id": "k-owner"},
    {"role": "node_key", "key_id": "k-node"},
    {"role": "owner_binding", "key_id": "k-owner", "attestation_id": "att-ob", "cohort_scope": "federation"},
    {"role": "agent_binding", "key_id": "k-owner", "attestation_id": "att-ab", "cohort_scope": "federation"},
    {"role": "agent_key", "key_id": "k-agent"},
]


def _client(status: int, body: Optional[Dict[str, Any]] = None, *, raise_exc: bool = False) -> httpx.AsyncClient:
    seen: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        if raise_exc:
            raise httpx.ConnectError("refused")
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status, text="nope")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.seen = seen  # type: ignore[attr-defined]
    return client


@pytest.mark.asyncio
async def test_complete_bundle_is_ok_and_posts_the_owner_session_to_the_node() -> None:
    c = _client(200, {"bundle": _ROWS_OK, "bundle_expected": 5, "federation_discoverable": True, "promoted_owner_binding_attestation_id": None})
    check = await check_announce_bundle(c, "http://127.0.0.1:4243", {"Authorization": "Bearer t"})
    assert check.status == "ok" and check.passed and check.asserted
    assert c.seen["url"] == "http://127.0.0.1:4243/v1/federation/announce" and c.seen["auth"] == "Bearer t"  # type: ignore[attr-defined]
    assert "re-announce" in check.message and len(check.rows) == 5


@pytest.mark.asyncio
async def test_self_scoped_binding_is_incomplete_and_names_the_row() -> None:
    rows = json.loads(json.dumps(_ROWS_OK)); rows[2]["cohort_scope"] = "self"
    c = _client(200, {"bundle": rows, "bundle_expected": 5, "federation_discoverable": False})
    check = await check_announce_bundle(c, "http://127.0.0.1:4243", {})
    assert check.status == "incomplete" and not check.passed and check.asserted
    assert "owner_binding@self" in check.message and "P2P-only" in check.message


@pytest.mark.asyncio
async def test_superseded_self_row_beside_the_federation_one_is_still_discoverable() -> None:
    """Single-key node after a widening: the server counts the pre-promotion self row as a
    second agent (bundle_expected=7, discoverable=false); a peer never receives it."""
    rows = json.loads(json.dumps(_ROWS_OK))
    rows[2]["key_id"] = rows[3]["key_id"] = rows[4]["key_id"] = rows[1]["key_id"] = "k-node"
    rows += [
        {"role": "agent_binding", "key_id": "k-node", "attestation_id": "att-orig", "cohort_scope": "self"},
        {"role": "agent_key", "key_id": "k-node"},
    ]
    c = _client(200, {"bundle": rows, "bundle_expected": 7, "federation_discoverable": False})
    check = await check_announce_bundle(c, "http://127.0.0.1:4243", {})
    assert check.status == "ok" and check.passed and check.effective_discoverable is True
    assert check.expected == 7 and check.discoverable is False          # the server's verdict, kept
    assert len(check.shadowed_rows) == 2 and any("att-orig" in r for r in check.shadowed_rows)
    assert "1 superseded self-scoped binding(s) and 1 duplicate key row(s)" in check.message
    assert "double-count" in check.message and "bundle_expected=7" in check.message


@pytest.mark.asyncio
async def test_fabric_count_means_no_agent_in_the_bundle() -> None:
    c = _client(200, {"bundle": _ROWS_OK[:3], "bundle_expected": 3, "federation_discoverable": True})
    check = await check_announce_bundle(c, "http://127.0.0.1:4243", {})
    assert check.status == "incomplete" and "3 distinct rows, not 5" in check.message
    assert "missing agent_binding, agent_key" in check.message


@pytest.mark.asyncio
async def test_old_server_reports_nothing_and_is_not_asserted() -> None:
    c = _client(200, {"owner": "k-owner", "promoted_owner_binding_attestation_id": "att-1"})
    check = await check_announce_bundle(c, "http://127.0.0.1:4243", {})
    assert check.status == "not_reported" and not check.asserted and "0.5.197" in check.message
    assert check.promoted_attestation_id == "att-1"


@pytest.mark.asyncio
async def test_unauthorized_names_the_harness_session_not_delivery() -> None:
    check = await check_announce_bundle(_client(401), "http://127.0.0.1:4243", {})
    assert check.status == "unauthorized" and "OWNER's session" in check.message


@pytest.mark.asyncio
async def test_unreachable_node_port_is_named() -> None:
    check = await check_announce_bundle(_client(200, raise_exc=True), "http://127.0.0.1:4243", {})
    assert check.status == "unreachable" and "4243" in check.message


@pytest.mark.asyncio
async def test_no_federation_id_names_the_mint_step() -> None:
    body = {"error": "no federation ID on this node — announcing to the federation means the OWNER stating their ownership at a federation-wide audience, which requires their signing key here (POST /v1/self/identity)"}
    check = await check_announce_bundle(_client(503, body), "http://127.0.0.1:4243", {})
    assert check.status == "no_federation_id" and not check.passed and not check.asserted
    assert "/v1/self/identity" in check.message and "P2P-only" in check.message
