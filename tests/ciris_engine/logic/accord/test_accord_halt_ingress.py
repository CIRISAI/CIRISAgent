"""Accord-row ingress and the retired legacy path (CC 4.2.1.1, CIRISAgent#1231).

A v2 row is forwarded to the node once and byte for byte; nothing in the agent
writes the latch; the legacy `/accord-invocation` route is gone; and nothing on
the accord path can end the process.
"""

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.accord import ingress
from ciris_engine.logic.utils import halt_latch
from ciris_engine.schemas.runtime.accord_halt import AccordHaltReading, AccordHaltState, AccordRowForward
from ciris_engine.schemas.runtime.messages import IncomingMessage, MessageHandlingStatus

pytestmark = pytest.mark.real_halt_latch

ROOT = Path(__file__).resolve().parents[4]

ROW_OBJ = {
    "schema": "ciris.ceg.signed-object.v1",
    "kind": "accord_invocation",
    "key_id": "humanity-accord",
    "created_at": "2026-10-14T12:00:00.000Z",
    "body": {
        "family_key_id": "humanity-accord",
        "roster": [],
        "invocation": {
            "invocation_kind": "constitutional",
            "invocation_id": "halt-ingress-1",
            "nonce": "n",
            "asserted_at": "2026-10-14T12:00:00.000Z",
            "valid_until": "2026-10-15T12:00:00.000Z",
            "payload_sha256": "0" * 64,
        },
        "signatures": [{"member_id": "holder-a", "ed25519_signature_base64": "AAAA"}],
    },
}
# Deliberately not what json.dumps would produce: forwarding must not re-serialise.
ROW = '{"schema":"ciris.ceg.signed-object.v1",  "kind":"accord_invocation","key_id":"humanity-accord",' + (
    '"created_at":"2026-10-14T12:00:00.000Z","body":' + json.dumps(ROW_OBJ["body"]) + "}"
)


class Node:
    """The node's POST /v1/accord/message, mocked; records every request body."""

    def __init__(self) -> None:
        self.bodies: List[bytes] = []
        self.urls: List[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        self.bodies.append(request.content)
        return httpx.Response(
            200,
            json={
                "accepted": True,
                "invocation_kind": "constitutional",
                "invocation_id": "halt-ingress-1",
                "quorum_met": True,
                "valid_signers": ["holder-a"],
                "halted": True,
                "confirmed": False,
                "released": False,
                "refusal": None,
            },
        )


@pytest.fixture
def node(monkeypatch) -> Node:
    n = Node()
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        ingress.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(n.handler), **kw)
    )
    return n


def test_a_bare_or_fenced_row_is_recognised_as_received():
    assert ingress.extract_accord_row(ROW) == ROW
    assert ingress.extract_accord_row(f"  {ROW}\n") == ROW
    assert ingress.extract_accord_row(f"```json\n{ROW}\n```") == ROW


@pytest.mark.parametrize(
    "content",
    [
        "please halt",
        "{not json",
        json.dumps({"schema": "ciris.ceg.signed-object.v1", "kind": "self_login", "body": {}}),
        json.dumps({**ROW_OBJ, "schema": "something-else"}),
        json.dumps({**ROW_OBJ, "body": "not an object"}),
        "[" + ROW + "]",
        "x" * (ingress.MAX_ACCORD_ROW_BYTES + 1),
    ],
)
def test_anything_else_is_not_a_row(content):
    assert ingress.extract_accord_row(content) is None


#: The CodeQL py/polynomial-redos witnesses, as source so the probe subprocess
#: builds them itself. The trailing non-space survives the leading strip(); the
#: old fence regex took ~50 s on the first of these.
ADVERSARIAL_SOURCE = (
    '["```" + " " * 100_000 + "x", "```" + "\\n" * 100_000 + "x", "```json" + " " * 100_000 + "x", '
    '"```" + " \\n" * 50_000 + "x```", "```" + " " * 100_000]'
)


def test_adversarial_whitespace_extracts_in_bounded_time():
    """This runs first on every inbound message: it must stay linear on attacker-shaped input.

    In a subprocess with a hard timeout, because a backtracking regex holds the
    GIL inside C and no in-process timeout can interrupt it.
    """
    import subprocess
    import sys

    probe = (
        "import time\n"
        "from ciris_engine.logic.accord.ingress import extract_accord_row\n"
        f"cases = {ADVERSARIAL_SOURCE}\n"
        "t = time.perf_counter()\n"
        "for c in cases:\n"
        "    for _ in range(20):\n"
        "        assert extract_accord_row(c) is None\n"
        "print(time.perf_counter() - t)\n"
    )
    try:
        done = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        pytest.fail("extract_accord_row did not finish on adversarial whitespace: super-linear matching")
    assert done.returncode == 0, done.stderr[-2000:]
    assert float(done.stdout.strip().splitlines()[-1]) < 2.0


def test_input_is_bounded_before_any_parsing(monkeypatch):
    def must_not_run(text):
        raise AssertionError("parsed an oversized message")

    monkeypatch.setattr(ingress, "_unfence", must_not_run)
    assert ingress.extract_accord_row("```" + " " * ingress.MAX_ACCORD_ROW_BYTES) is None


def test_extraction_uses_no_regular_expression():
    import ast

    tree = ast.parse((ROOT / "ciris_engine/logic/accord/ingress.py").read_text())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert "re" not in imported and "regex" not in imported


def test_fence_variants_are_still_recognised():
    for wrapped in (
        f"```{ROW}```",
        f"```json{ROW}```",
        f"```json\n{ROW}\n```",
        f"```\n{ROW}\n```",
        f"  ```json\n  {ROW}  \n```  ",
    ):
        assert ingress.extract_accord_row(wrapped) == ROW, wrapped[:20]
    assert ingress.extract_accord_row("```") is None
    assert ingress.extract_accord_row("``````") is None


@pytest.mark.asyncio
async def test_a_row_is_forwarded_once_and_unchanged(node):
    result = await ingress.forward_accord_row(ROW)
    assert node.urls == [ingress.ACCORD_MESSAGE_URL]
    assert node.bodies == [ROW.encode("utf-8")]
    assert result.delivered and result.status_code == 200
    assert result.halted is True and result.invocation_id == "halt-ingress-1"


@pytest.mark.asyncio
async def test_an_unreachable_node_is_reported_not_raised(monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("refused")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        ingress.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(refuse), **kw)
    )
    result = await ingress.forward_accord_row(ROW)
    assert result.delivered is False and "ConnectError" in (result.error or "")


def _observer():
    from ciris_engine.logic.adapters.base_observer import BaseObserver

    class _Obs(BaseObserver[IncomingMessage]):
        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    obs = _Obs(on_observe=AsyncMock(), agent_id="agent", origin_service="api")
    obs._enforce_credit_policy = AsyncMock()  # type: ignore[method-assign]
    return obs


def _msg(content: str) -> IncomingMessage:
    return IncomingMessage(message_id="m1", author_id="u1", author_name="user", content=content, channel_id="d_1")


@pytest.mark.asyncio
async def test_observer_forwards_a_row_and_creates_no_task(node):
    obs = _observer()
    result = await obs.handle_incoming_message(_msg(ROW))
    assert result.status == MessageHandlingStatus.ACCORD_ROW_FORWARDED
    assert result.task_id is None
    assert result.accord_forward is not None and result.accord_forward.halted is True
    assert node.bodies == [ROW.encode("utf-8")]
    obs._enforce_credit_policy.assert_not_awaited()  # nothing past the forward ran


@pytest.mark.asyncio
async def test_observer_does_not_forward_ordinary_messages(node, monkeypatch):
    obs = _observer()
    forwarded = AsyncMock()
    monkeypatch.setattr(ingress, "forward_accord_row", forwarded)
    obs._refuse_if_shedding = Mock(return_value=Mock(status=MessageHandlingStatus.RESOURCE_SHED))  # type: ignore[method-assign]
    await obs.handle_incoming_message(_msg("hello there"))
    forwarded.assert_not_awaited()


@pytest.fixture
def api_app():
    from ciris_engine.logic.adapters.api.dependencies.auth import require_observer
    from ciris_engine.logic.adapters.api.routes import agent as agent_routes
    from ciris_engine.schemas.api.auth import AuthContext, Permission, UserRole

    app = FastAPI()
    app.include_router(agent_routes.router)
    app.state.on_message = AsyncMock()
    app.state.runtime = Mock(agent_processor=Mock(_is_paused=False, state_manager=Mock(current_state="WORK")))
    auth = AuthContext(
        user_id="admin_user",
        role=UserRole.ADMIN,
        permissions={Permission.SEND_MESSAGES},
        api_key_id="k",
        authenticated_at=datetime.now(timezone.utc),
    )

    async def _auth():
        return auth

    app.dependency_overrides[require_observer] = _auth
    return app


@pytest.mark.parametrize("path", ["/agent/message", "/agent/interact"])
def test_api_forwards_a_row_even_while_halted(node, api_app, monkeypatch, path):
    """A resumption row must get through the halt; it is delivery to the node, not work."""

    async def halted():
        return AccordHaltState(
            halted=True, reading=AccordHaltReading.IN_EFFECT, invocation_id="h", read_at=datetime.now(timezone.utc)
        )

    monkeypatch.setattr(halt_latch, "_read_from_node", halted)
    response = TestClient(api_app).post(path, json={"message": ROW})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["accord_forward"]["invocation_id"] == "halt-ingress-1"
    assert node.bodies == [ROW.encode("utf-8")]  # once, unchanged
    api_app.state.on_message.assert_not_awaited()  # never became a task


def test_legacy_accord_invocation_route_is_gone():
    from ciris_engine.logic.adapters.api.routes import system_extensions

    app = FastAPI()
    app.include_router(system_extensions.router)
    assert TestClient(app).post("/system/accord-invocation", json={}).status_code == 404
    assert not any(getattr(r, "path", "").endswith("/accord-invocation") for r in system_extensions.router.routes)


def test_legacy_modules_are_gone():
    for rel in (
        "ciris_engine/logic/accord/executor.py",
        "ciris_engine/logic/accord/extractor.py",
        "ciris_engine/logic/accord/handler.py",
        "ciris_engine/logic/accord/verifier.py",
        "ciris_engine/schemas/accord.py",
        "ciris_engine/logic/utils/hard_kill.py",
        "tools/security/accord_stego.py",
        "tools/security/accord_invoke.py",
    ):
        assert not (ROOT / rel).exists(), rel
    from ciris_engine.logic.buses.wise_bus import WiseBus

    assert not hasattr(WiseBus, "handle_accord_invocation")


def _production_files():
    for base in ("ciris_engine", "ciris_adapters"):
        yield from (p for p in (ROOT / base).rglob("*.py"))


def test_nothing_in_the_agent_writes_the_latch():
    """The node owns <home>/HUMANITY_ACCORD_HALT. No agent code names it at all."""
    offenders = [str(p.relative_to(ROOT)) for p in _production_files() if "HUMANITY_ACCORD_HALT" in p.read_text()]
    assert offenders == []


_ACCORD_PATH = [
    "ciris_engine/logic/accord/__init__.py",
    "ciris_engine/logic/accord/ingress.py",
    "ciris_engine/logic/accord/authorities.py",
    "ciris_engine/logic/utils/halt_latch.py",
    "ciris_engine/schemas/runtime/accord_halt.py",
]


def _process_enders(tree: ast.AST) -> List[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            text = ast.unparse(node.func)
            if text in {"os._exit", "os.kill", "sys.exit", "exit", "quit", "os.abort", "terminate_immediately"}:
                found.append(text)
        if isinstance(node, ast.Attribute) and node.attr in {"SIGKILL", "SIGTERM"}:
            found.append(ast.unparse(node))
    return found


def test_nothing_on_the_accord_path_can_end_the_process():
    for rel in _ACCORD_PATH + ["ciris_engine/logic/adapters/base_observer.py"]:
        tree = ast.parse((ROOT / rel).read_text())
        assert _process_enders(tree) == [], rel
    # And the hard-kill helper is gone from the whole agent.
    users = [str(p.relative_to(ROOT)) for p in _production_files() if "terminate_immediately" in p.read_text()]
    assert users == []


def test_the_process_ender_scan_is_not_vacuous():
    found = _process_enders(ast.parse("import os, signal\nos.kill(1, signal.SIGKILL)\nos._exit(1)"))
    assert sorted(found) == ["os._exit", "os.kill", "signal.SIGKILL"]
