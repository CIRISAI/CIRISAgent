"""Every QA boot claims its node as qa-harness-user, the way the wizard does, or fails closed."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock

import httpx
import pytest

from tools.qa_runner import node_claim
from tools.qa_runner.config import QAConfig, QAModule
from tools.qa_runner.server import APIServerManager

BRAIN = "http://127.0.0.1:8080"
NODE = "http://127.0.0.1:4243"


class FakeAgent:
    """The brain and its node: records every call, in order."""

    def __init__(self, claim_status: int = 200) -> None:
        self.calls: List[str] = []
        self.claim_body: Any = None
        self.claim_status = claim_status

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(f"{request.method} {url}")
        if url == f"{BRAIN}/v1/self/identity":
            return httpx.Response(200, json={"key_id": "fed-qa", "hardware_type": "software", "fedcode": "FC"})
        if url == f"{BRAIN}/v1/federation/node-code":
            return httpx.Response(200, json={"data": {"node_code": "NODECODE-123"}})
        if url == f"{NODE}/v1/setup/claim-remote":
            self.claim_body = json.loads(request.content)
            if self.claim_status != 200:
                return httpx.Response(self.claim_status, json={"error": "pin_mismatch"})
            return httpx.Response(200, json={"owner": "qa-harness-user-person", "node": "n"})
        return httpx.Response(404)


async def _claim(home: Path, agent: FakeAgent, **kw: Any) -> node_claim.ClaimOutcome:
    async with httpx.AsyncClient(transport=httpx.MockTransport(agent.handler)) as client:
        return await node_claim.claim_like_the_wizard(
            client, BRAIN, [str(home)], node_claim.QA_HARNESS_USER, "pw", node_url=NODE, **kw
        )


@pytest.mark.asyncio
async def test_the_harness_user_claims_in_the_wizards_order(tmp_path):
    (tmp_path / node_claim.CLAIM_PIN_FILE).write_text("Q4YC-AZQA\n")
    agent = FakeAgent()
    outcome = await _claim(tmp_path, agent, pin_timeout_s=1)
    assert outcome.ok and outcome.owner == "qa-harness-user-person" and outcome.federation_key_id == "fed-qa"
    assert agent.calls == [
        f"POST {BRAIN}/v1/self/identity",
        f"GET {BRAIN}/v1/federation/node-code",
        f"POST {NODE}/v1/setup/claim-remote",
    ]
    assert agent.claim_body["claim_pin"] == "Q4YC-AZQA"
    assert agent.claim_body["owner_username"] == "qa-harness-user"
    assert agent.claim_body["node_code"] == "NODECODE-123"


@pytest.mark.asyncio
async def test_no_pin_fails_closed_and_sends_nothing(tmp_path):
    agent = FakeAgent()
    outcome = await _claim(tmp_path, agent, pin_timeout_s=0.3)
    assert not outcome.ok and outcome.step == "pin" and "No claim PIN" in outcome.detail
    assert agent.calls == []


@pytest.mark.asyncio
async def test_a_previous_runs_pin_is_not_this_boots(tmp_path):
    pin = tmp_path / node_claim.CLAIM_PIN_FILE
    pin.write_text("OLD0-PIN0")
    old = time.time() - 3600
    os.utime(pin, (old, old))
    outcome = await _claim(tmp_path, FakeAgent(), pin_timeout_s=0.3, since=time.time())
    assert not outcome.ok and outcome.step == "pin"


@pytest.mark.asyncio
async def test_a_refused_claim_is_a_failure(tmp_path):
    (tmp_path / node_claim.CLAIM_PIN_FILE).write_text('{"pin": "QCKE-AY69"}')
    outcome = await _claim(tmp_path, FakeAgent(claim_status=403), pin_timeout_s=1)
    assert not outcome.ok and "403" in outcome.detail


def _manager(tmp_path: Path) -> APIServerManager:
    manager = APIServerManager(QAConfig(base_url=BRAIN, api_port=8080, mock_llm=True), modules=[QAModule.AUTH])
    manager._backend_home = str(tmp_path)
    manager._launched_at = time.time() - 5
    return manager


def test_qa_setup_claims_before_it_completes(tmp_path, monkeypatch):
    """A QA boot ends with the node owner-bound: claim first, then /v1/setup/complete."""
    order: List[str] = []
    manager = _manager(tmp_path)
    monkeypatch.setattr(manager, "_claim_node_like_the_wizard", lambda: order.append("claim") or True)

    def post(url: str, json: Any = None, timeout: Any = None) -> Any:
        order.append(url.rsplit("/v1", 1)[1])
        assert json["admin_username"] == "qa-harness-user"
        response = MagicMock(status_code=200)
        response.json.return_value = {"data": {}}
        return response

    monkeypatch.setattr("tools.qa_runner.server.requests.post", post)
    assert manager._complete_qa_setup() is True
    assert order == ["claim", "/setup/complete"]


def test_qa_setup_never_completes_on_an_unowned_node(tmp_path, monkeypatch):
    manager = _manager(tmp_path)  # no claim_pin in the home: the node minted none
    posted: List[str] = []
    monkeypatch.setattr("tools.qa_runner.server.requests.post", lambda url, **kw: posted.append(url))
    monkeypatch.setattr(node_claim, "wait_for_claim_pin", _no_pin)
    assert manager._complete_qa_setup() is False
    assert posted == []  # fail closed: setup never ran


async def _no_pin(*args: Any, **kwargs: Any) -> Any:
    return None, None


def test_the_setup_user_is_not_the_run_kind():
    """The name is a real user's; QA-ness rides run_kind, which the user name never changes."""
    assert QAConfig().admin_username == node_claim.QA_HARNESS_USER
