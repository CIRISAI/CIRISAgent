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

    def __init__(self, claim_status: int = 200, booting_502s: int = 0, identity_status: int = 200) -> None:
        self.booting_502s = booting_502s  # identity answers 502 this many times: the node is still binding
        self.identity_status = identity_status
        self.calls: List[str] = []
        self.claim_body: Any = None
        self.claim_status = claim_status

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(f"{request.method} {url}")
        if url == f"{BRAIN}/v1/self/identity":
            if self.booting_502s:
                self.booting_502s -= 1
                return httpx.Response(502, json={"detail": "The folded node did not answer POST /v1/self/identity."})
            if self.identity_status != 200:
                return httpx.Response(self.identity_status, json={"error": "refused"})
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


@pytest.mark.asyncio
async def test_the_node_boot_window_is_waited_out(tmp_path):
    """Staged QA on #1276: the PIN appears before :4243 answers; the proxy 502s in between."""
    (tmp_path / node_claim.CLAIM_PIN_FILE).write_text("Q4YC-AZQA")
    agent = FakeAgent(booting_502s=3)
    outcome = await _claim(tmp_path, agent, pin_timeout_s=1, ready_timeout_s=10)
    assert outcome.ok
    assert agent.calls.count(f"POST {BRAIN}/v1/self/identity") == 4


@pytest.mark.asyncio
async def test_a_node_that_never_answers_still_fails_closed(tmp_path):
    (tmp_path / node_claim.CLAIM_PIN_FILE).write_text("Q4YC-AZQA")
    agent = FakeAgent(booting_502s=10_000)
    outcome = await _claim(tmp_path, agent, pin_timeout_s=1, ready_timeout_s=1.5)
    assert not outcome.ok and outcome.step == "mint" and "502" in outcome.detail
    assert f"POST {NODE}/v1/setup/claim-remote" not in agent.calls


@pytest.mark.asyncio
async def test_a_4xx_is_the_nodes_answer_and_never_retried(tmp_path):
    (tmp_path / node_claim.CLAIM_PIN_FILE).write_text("Q4YC-AZQA")
    agent = FakeAgent(identity_status=403)
    outcome = await _claim(tmp_path, agent, pin_timeout_s=1, ready_timeout_s=10)
    assert not outcome.ok and "403" in outcome.detail
    assert agent.calls.count(f"POST {BRAIN}/v1/self/identity") == 1


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


@pytest.mark.asyncio
async def test_desktop_up_claims_before_it_completes_setup(tmp_path, monkeypatch):
    """#1277 desktop-ui: desktop-up posted /v1/setup/complete unclaimed and got 409 node_unclaimed."""
    from tools.qa_runner.modules.web_ui import __main__ as web_ui

    order: List[str] = []

    async def claimed(*args: Any, **kwargs: Any) -> node_claim.ClaimOutcome:
        order.append("claim")
        return node_claim.ClaimOutcome(True, "claim", "node claimed", pin_file=tmp_path / "claim_pin")

    def post(url: str, json: Any = None, timeout: Any = None) -> Any:
        order.append(url.rsplit("/v1", 1)[1])
        return MagicMock(status_code=200)

    monkeypatch.setattr(node_claim, "claim_like_the_wizard", claimed)
    monkeypatch.setattr(web_ui.requests, "post", post)
    assert await web_ui._complete_setup(BRAIN, True, str(tmp_path)) is True
    assert order == ["claim", "/setup/complete"]


@pytest.mark.asyncio
async def test_desktop_up_never_completes_setup_on_an_unowned_node(tmp_path, monkeypatch):
    from tools.qa_runner.modules.web_ui import __main__ as web_ui

    posted: List[str] = []
    monkeypatch.setattr(node_claim, "wait_for_claim_pin", _no_pin)
    monkeypatch.setattr(web_ui.requests, "post", lambda url, **kw: posted.append(url))
    assert await web_ui._complete_setup(BRAIN, True, str(tmp_path)) is False
    assert posted == []


def _api_only_browser() -> Any:
    """A setup page with no account step and no Continue button: the flow takes its API path."""
    from unittest.mock import AsyncMock

    browser = MagicMock()
    browser.goto = AsyncMock()
    browser.wait = AsyncMock()
    browser.screenshot = AsyncMock(return_value=MagicMock(path="shot.png"))
    browser.get_page_content = AsyncMock(return_value="<html>setup</html>")
    locator = MagicMock()
    locator.count = AsyncMock(return_value=0)
    locator.filter.return_value = locator
    browser.page.locator.return_value = locator
    return browser


@pytest.mark.asyncio
@pytest.mark.parametrize("claim_ok", [True, False])
async def test_licensed_flow_api_path_claims_before_setup(tmp_path, monkeypatch, claim_ok):
    from tools.qa_runner.modules.web_ui import licensed_agent_flow as flow

    order: List[str] = []

    async def claim(client: Any, base_url: str, homes: Any, *args: Any, **kwargs: Any) -> node_claim.ClaimOutcome:
        order.append("claim")
        assert homes == [str(tmp_path)]
        return node_claim.ClaimOutcome(claim_ok, "pin", "node claimed" if claim_ok else "No claim PIN readable")

    def post(url: str, **kw: Any) -> Any:
        order.append(url.rsplit("/v1", 1)[1])
        return MagicMock(status_code=200)

    monkeypatch.setattr(node_claim, "claim_like_the_wizard", claim)
    monkeypatch.setattr(flow.requests, "post", post)
    config = flow.LicensedAgentConfig(base_url=BRAIN, llm_api_key="", node_home=str(tmp_path))
    report = await flow.test_complete_licensed_setup(_api_only_browser(), config, {})
    if claim_ok:
        assert order == ["claim", "/setup/complete"] and report.result == flow.TestResult.PASSED
    else:
        assert order == ["claim"] and report.result == flow.TestResult.FAILED
        assert "setup not attempted" in report.message


@pytest.mark.parametrize("simulator", [True, False])
def test_ios_reads_the_claim_pin_from_the_app_container(tmp_path, monkeypatch, simulator):
    """Simulator: the container in place; device: devicectl copies the file. Never a log."""
    from tools.qa_runner.modules.web_ui import __main__ as web_ui

    container = tmp_path / "container"
    (container / "Documents" / "ciris").mkdir(parents=True)
    (container / "Documents" / "ciris" / "claim_pin").write_text("Q4YC-AZQA")
    dest = tmp_path / "dest"
    dest.mkdir()
    seen: List[Any] = []

    def simctl(args: List[str], timeout: int = 120) -> Any:
        seen.append(args)
        return MagicMock(stdout=f"{container}\n", stderr="")

    def run(cmd: List[str], **kw: Any) -> Any:
        seen.append(cmd)
        src = cmd[cmd.index("--source") + 1]
        Path(cmd[cmd.index("--destination") + 1]).write_text((container / src).read_text())
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(web_ui, "_simctl", simctl)
    monkeypatch.setattr(web_ui.subprocess, "run", run)
    home, why = web_ui._ios_fetch_claim_pin_home("UDID", "ai.ciris.mobile", simulator=simulator, dest=dest)
    assert why == "" and home is not None
    assert node_claim.find_claim_pin([home])[0] == "Q4YC-AZQA"
    if simulator:
        assert seen == [["get_app_container", "UDID", "ai.ciris.mobile", "data"]]
    else:
        assert seen[0][:5] == ["xcrun", "devicectl", "device", "copy", "from"]
        assert "appDataContainer" in seen[0] and "Documents/ciris/claim_pin" in seen[0]


@pytest.mark.parametrize("simulator", [True, False])
def test_ios_unreachable_pin_fails_closed(tmp_path, monkeypatch, simulator):
    from tools.qa_runner.modules.web_ui import __main__ as web_ui

    monkeypatch.setattr(web_ui, "_simctl", lambda args, timeout=120: MagicMock(stdout="", stderr="No such app"))
    monkeypatch.setattr(
        web_ui.subprocess, "run", lambda cmd, **kw: MagicMock(returncode=1, stdout="", stderr="file not found")
    )
    home, why = web_ui._ios_fetch_claim_pin_home(
        "UDID", "ai.ciris.mobile", simulator=simulator, dest=tmp_path, timeout_s=0.1, poll_s=0.05
    )
    assert home is None and why


@pytest.mark.asyncio
async def test_ios_setup_is_never_completed_without_the_pin(monkeypatch):
    from tools.qa_runner.modules.web_ui import __main__ as web_ui

    posted: List[str] = []
    monkeypatch.setattr(
        web_ui.requests, "get", lambda url, **kw: MagicMock(status_code=200, json=lambda: {"data": {"first_run": True}})
    )
    monkeypatch.setattr(web_ui.requests, "post", lambda url, **kw: posted.append(url))
    monkeypatch.setattr(web_ui, "_ios_fetch_claim_pin_home", lambda *a, **k: (None, "devicectl copy failed"))
    ok = await web_ui._ios_complete_setup_if_needed("http://localhost:18080", "UDID", "ai.ciris.mobile", "t", "a")
    assert ok is False and posted == []
