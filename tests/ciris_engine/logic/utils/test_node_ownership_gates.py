"""EVERY NODE IS ALWAYS CLAIMED: an agent does not run on an unowned node.

One reader (`node_ownership.node_owned`) and four gates: the processor start
hold, intake (423), the act gate, and setup completion (409). Each gate test
pairs an unowned case with an owned positive control, so removing a gate fails
its unowned test and a gate that refuses everything fails its control.

The node is mocked throughout: nothing here binds or dials :4243.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes import agent as agent_routes
from ciris_engine.logic.adapters.api.routes.setup import complete
from ciris_engine.logic.adapters.api.routes.setup.models import SetupCompleteRequest
from ciris_engine.logic.adapters.api.routes.system import health
from ciris_engine.logic.infrastructure.handlers import action_dispatcher as dispatcher_module
from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher
from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.logic.utils import node_ownership, path_resolution
from ciris_engine.schemas.actions.parameters import SpeakParams
from ciris_engine.schemas.audit.hash_chain import AuditEntryResult
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.runtime.node_ownership import NODE_UNCLAIMED_ERROR, NodeOwnership, NodeOwnershipReading

#: Every test here drives the reader itself; the conftest "owned" stub is off.
pytestmark = pytest.mark.real_node_ownership

#: Shaped like a real Crockford claim PIN. It must never leave the file.
PIN = "7QK4-ZX9M"


def _ownership(reading: NodeOwnershipReading, owner: Optional[str] = None) -> NodeOwnership:
    return NodeOwnership(
        reading=reading,
        owner_key_id=owner,
        node_key_id="ciris-node-abc",
        read_at=datetime.now(timezone.utc),
        claim_pin_file=node_ownership.claim_pin_file(),
    )


class Node:
    """The node's ownership answer, settable per test."""

    def __init__(self) -> None:
        self.reading = NodeOwnershipReading.UNOWNED
        self.reads = 0

    def own(self) -> None:
        self.reading = NodeOwnershipReading.OWNED

    async def read(self) -> NodeOwnership:
        self.reads += 1
        owner = "owner-eric" if self.reading == NodeOwnershipReading.OWNED else None
        return _ownership(self.reading, owner)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A CIRIS_HOME holding the node's claim PIN file."""
    (tmp_path / "claim_pin").write_text(PIN, encoding="utf-8")
    monkeypatch.setattr(path_resolution, "get_ciris_home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def node(home: Path, monkeypatch: pytest.MonkeyPatch) -> Node:
    n = Node()
    monkeypatch.setattr(node_ownership, "_read_from_node", n.read)
    monkeypatch.setattr(node_ownership, "_cached", None)
    monkeypatch.setattr(node_ownership, "_cached_at", 0.0)
    monkeypatch.setattr(node_ownership, "NODE_OWNERSHIP_CACHE_TTL_SECONDS", 0.0)
    monkeypatch.setattr(node_ownership, "NODE_OWNERSHIP_HOLD_TICK_SECONDS", 0.01)
    # A shutdown flag left set by another test in this worker would end the hold.
    from ciris_engine.logic.utils import shutdown_manager

    monkeypatch.setattr(shutdown_manager, "is_global_shutdown_requested", lambda: False)
    return n


async def _until(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached"
        await asyncio.sleep(0.01)


# --------------------------------------------------------------------------- reader


@pytest.fixture
def fold_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from ciris_engine.logic.runtime import node_fold

    monkeypatch.setattr(node_fold, "fold_status", lambda: {"folded": True, "reachable": True})
    monkeypatch.setattr(node_ownership, "_cached", None)


def _substrate(monkeypatch: pytest.MonkeyPatch, key_id: Optional[str], owner_of: Any) -> None:
    from ciris_engine.logic.persistence.models import graph
    from ciris_engine.logic.runtime import edge_runtime

    monkeypatch.setattr(edge_runtime, "get_node_key_id", lambda: key_id)
    engine = None if owner_of is None else SimpleNamespace(owner_of_json=owner_of)
    monkeypatch.setattr(graph, "get_persist_engine", lambda: engine)


@pytest.mark.asyncio
async def test_an_owner_binding_reads_owned(fold_on: None, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: List[str] = []
    _substrate(monkeypatch, "ciris-node-abc", lambda k: asked.append(k) or json.dumps("owner-eric"))
    state = await node_ownership.node_owned(fresh=True)
    assert state.reading == NodeOwnershipReading.OWNED and not state.unclaimed
    assert state.owner_key_id == "owner-eric"
    assert asked == ["ciris-node-abc"], "ownership is asked of the node's own key"


@pytest.mark.parametrize(
    "key_id, owner_of, reading",
    [
        ("ciris-node-abc", lambda k: "null", NodeOwnershipReading.UNOWNED),
        (None, lambda k: json.dumps("owner-eric"), NodeOwnershipReading.NO_NODE_KEY),
        ("ciris-node-abc", None, NodeOwnershipReading.NO_ENGINE),
    ],
)
@pytest.mark.asyncio
async def test_anything_but_an_owner_is_unclaimed(
    fold_on: None, home: Path, monkeypatch: pytest.MonkeyPatch, key_id: Any, owner_of: Any, reading: Any
) -> None:
    _substrate(monkeypatch, key_id, owner_of)
    state = await node_ownership.node_owned(fresh=True)
    assert state.reading == reading and state.unclaimed


@pytest.mark.asyncio
async def test_a_read_error_is_unclaimed(fold_on: None, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def ambiguous(key_id: str) -> str:
        raise RuntimeError("federation_ambiguous_node_owner")

    _substrate(monkeypatch, "ciris-node-abc", ambiguous)
    state = await node_ownership.node_owned(fresh=True)
    assert state.reading == NodeOwnershipReading.READ_ERROR and state.unclaimed


@pytest.mark.asyncio
async def test_a_slow_read_is_bounded_and_unclaimed_and_does_not_block_the_loop(
    fold_on: None, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def slow(key_id: str) -> str:
        time.sleep(0.5)
        return json.dumps("owner-eric")

    _substrate(monkeypatch, "ciris-node-abc", slow)
    monkeypatch.setattr(node_ownership, "NODE_OWNERSHIP_READ_TIMEOUT_SECONDS", 0.05)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    t = asyncio.create_task(ticker())
    state = await node_ownership.node_owned(fresh=True)
    t.cancel()
    assert state.reading == NodeOwnershipReading.READ_TIMEOUT and state.unclaimed
    assert ticks >= 3, "the substrate call ran on the event loop"


@pytest.mark.asyncio
async def test_fold_off_is_unowned_and_held(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CIRIS_NODE_FOLD=false: no node, no owner. Held, like the halt latch reads it halted; no bypass."""
    from ciris_engine.logic.runtime import node_fold

    monkeypatch.setenv("CIRIS_NODE_FOLD", "false")
    assert node_fold.fold_status() is None
    state = await node_ownership.node_owned(fresh=True)
    assert state.reading == NodeOwnershipReading.NO_NODE
    assert state.unclaimed


@pytest.mark.asyncio
async def test_fold_off_holds_the_processor(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ciris_engine.logic.utils import shutdown_manager

    monkeypatch.setenv("CIRIS_NODE_FOLD", "false")
    monkeypatch.setattr(node_ownership, "NODE_OWNERSHIP_HOLD_TICK_SECONDS", 0.01)
    monkeypatch.setattr(shutdown_manager, "is_global_shutdown_requested", lambda: False)
    fake = _processor()
    task = asyncio.create_task(AgentProcessor.start_processing(fake, num_rounds=1))
    await asyncio.sleep(0.1)
    assert not task.done()
    fake.state_manager.transition_to.assert_not_awaited()
    fake._stop_event.set()
    await asyncio.wait_for(task, timeout=2)


def test_the_owned_answer_comes_only_from_the_pytest_stub() -> None:
    """The reader has no test mode: no pytest, env or flag check can make it say "owned".

    "owned" without a node exists only as the autouse stub in tests/conftest.py.
    """
    import inspect

    source = inspect.getsource(node_ownership)
    for marker in ("pytest", "PYTEST", "TESTING", "environ", "getenv"):
        assert marker not in source, f"the reader consults {marker!r}"
    conftest = (Path(__file__).resolve().parents[3] / "conftest.py").read_text(encoding="utf-8")
    assert "def _stub_node_ownership(" in conftest and "real_node_ownership" in conftest


@pytest.mark.asyncio
async def test_the_conftest_stub_is_lifted_by_the_marker(home: Path) -> None:
    """This module opts out, so the real reader answers: fold-off here is held, not stubbed owned."""
    state = await node_ownership.node_owned(fresh=True)
    assert state.reading == NodeOwnershipReading.NO_NODE


@pytest.mark.asyncio
async def test_a_folded_process_that_cannot_read_its_node_holds(
    fold_on: None, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ciris_engine.logic.runtime import edge_runtime

    def unanswered() -> str:
        raise RuntimeError("no node")

    monkeypatch.setattr(edge_runtime, "get_node_key_id", unanswered)
    state = await node_ownership.node_owned(fresh=True)
    assert state.reading == NodeOwnershipReading.READ_ERROR and state.unclaimed


# --------------------------------------------------------------------------- processor start


def _processor() -> Any:
    fake = MagicMock()
    fake._processing_task = None
    fake._stop_event = asyncio.Event()
    fake._ensure_stop_event = MagicMock()
    fake.state_manager.get_state.return_value = AgentState.SHUTDOWN
    # Recording the transition and then failing it ends start_processing right
    # after the hold: the transition is the first step past the hold.
    fake.state_manager.transition_to = AsyncMock(return_value=False)
    return fake


@pytest.mark.asyncio
async def test_unowned_the_processor_holds_before_wakeup_then_starts_once_claimed(node: Node) -> None:
    fake = _processor()
    task = asyncio.create_task(AgentProcessor.start_processing(fake, num_rounds=1))
    await _until(lambda: node.reads >= 3 or task.done())
    assert not task.done(), "the processor did not hold on an unowned node"
    fake.state_manager.transition_to.assert_not_awaited()

    node.own()
    await asyncio.wait_for(task, timeout=2)
    fake.state_manager.transition_to.assert_awaited()


@pytest.mark.asyncio
async def test_owned_the_processor_starts_at_once(node: Node) -> None:
    node.own()
    fake = _processor()
    await asyncio.wait_for(AgentProcessor.start_processing(fake, num_rounds=1), timeout=2)
    fake.state_manager.transition_to.assert_awaited()


@pytest.mark.asyncio
async def test_a_stop_while_held_never_starts_the_processor(node: Node) -> None:
    fake = _processor()
    task = asyncio.create_task(AgentProcessor.start_processing(fake, num_rounds=1))
    await _until(lambda: node.reads >= 1 or task.done())
    assert not task.done()
    fake._stop_event.set()
    await asyncio.wait_for(task, timeout=2)
    fake.state_manager.transition_to.assert_not_awaited()


# --------------------------------------------------------------------------- intake


def _intake_patches(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    monkeypatch.setattr(agent_routes, "_check_send_messages_permission", lambda auth, request: None)
    created = AsyncMock(side_effect=AssertionError("a message was created on an unowned node"))
    monkeypatch.setattr(agent_routes, "_create_interaction_message", created)
    return created


@pytest.mark.parametrize("route", ["interact", "submit_message"])
@pytest.mark.asyncio
async def test_unowned_intake_is_423_node_unclaimed(node: Node, monkeypatch: pytest.MonkeyPatch, route: str) -> None:
    created = _intake_patches(monkeypatch)
    body = (agent_routes.InteractRequest if route == "interact" else agent_routes.MessageRequest)(message="hello")
    with pytest.raises(HTTPException) as exc:
        await getattr(agent_routes, route)(MagicMock(), body, MagicMock())
    assert exc.value.status_code == 423
    assert exc.value.detail["error"] == NODE_UNCLAIMED_ERROR
    assert exc.value.detail["claim_pin_file"].endswith("claim_pin")
    assert exc.value.detail["upgrade_claim_routes"] == ["POST /v1/self/identity", "POST /v1/self/upgrade-owner"]
    assert "/v1/self/upgrade-owner" in exc.value.detail["message"]
    created.assert_not_awaited()


@pytest.mark.parametrize("route", ["interact", "submit_message"])
@pytest.mark.asyncio
async def test_owned_intake_admits(node: Node, monkeypatch: pytest.MonkeyPatch, route: str) -> None:
    node.own()
    created = _intake_patches(monkeypatch)
    body = (agent_routes.InteractRequest if route == "interact" else agent_routes.MessageRequest)(message="hello")
    with pytest.raises(AssertionError, match="a message was created"):
        await getattr(agent_routes, route)(MagicMock(), body, MagicMock())
    created.assert_awaited_once()


# --------------------------------------------------------------------------- act gate


@pytest.fixture
def audit() -> MagicMock:
    mock = MagicMock()

    async def log_action(action_type: Any, context: Any, outcome: str) -> AuditEntryResult:
        return AuditEntryResult(
            entry_id=f"audit-{action_type.value}",
            sequence_number=7,
            entry_hash="hash",
            previous_hash=None,
            signature="sig",
            signing_key_id="key",
        )

    mock.log_action = AsyncMock(side_effect=log_action)
    return mock


@pytest.fixture
def handler() -> MagicMock:
    h = MagicMock()
    h.handle = AsyncMock(return_value=None)
    h.dependencies = None
    return h


@pytest.fixture
def thought_status(monkeypatch: pytest.MonkeyPatch) -> List[Any]:
    writes: List[Any] = []

    def update(thought_id: str, status: Any, occurrence_id: str = "default", final_action: Any = None) -> bool:
        writes.append((thought_id, status))
        return True

    monkeypatch.setattr(dispatcher_module.persistence, "update_thought_status", update)
    monkeypatch.setattr(dispatcher_module.persistence, "get_thought_by_id", lambda *a, **k: None)
    return writes


@pytest.fixture
def action_results(monkeypatch: pytest.MonkeyPatch) -> List[Any]:
    seen: List[Any] = []

    async def complete_step(self: Any, thought_item: Any, dispatch_result: Any, **kwargs: Any) -> Any:
        seen.append(dispatch_result)
        return dispatch_result

    monkeypatch.setattr(ActionDispatcher, "_action_complete_step", complete_step)
    return seen


def _thought() -> Thought:
    now = datetime(2026, 10, 15, tzinfo=timezone.utc).isoformat()
    return Thought(
        thought_id="th-1",
        source_task_id="task-1",
        content="hello",
        status=ThoughtStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.task_id = "task-1"
    ctx.model_dump.return_value = {"task_id": "task-1", "channel_id": "api_u1"}
    return ctx


def _speak() -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK, action_parameters=SpeakParams(content="hi"), rationale="r"
    )


@pytest.mark.asyncio
async def test_unowned_an_act_is_refused_recorded_and_traced(
    node: Node, handler: MagicMock, audit: MagicMock, thought_status: List[Any], action_results: List[Any]
) -> None:
    dispatcher = ActionDispatcher(handlers={HandlerActionType.SPEAK: handler}, audit_service=audit)
    response = await dispatcher.dispatch(_speak(), _thought(), _ctx())

    handler.handle.assert_not_awaited()
    assert response.success is False
    assert response.error == f"{NODE_UNCLAIMED_ERROR}:unowned"
    assert response.action_parameters["node_ownership_reading"] == "unowned"
    assert audit.log_action.await_args.kwargs["outcome"] == f"refused:{NODE_UNCLAIMED_ERROR}:unowned"
    assert audit.log_action.await_args.kwargs["context"].parameters["refused"] == NODE_UNCLAIMED_ERROR
    assert action_results == [response], "a refused act emits exactly one terminal ACTION_RESULT"
    assert thought_status == [("th-1", ThoughtStatus.PENDING)]


@pytest.mark.asyncio
async def test_owned_the_act_runs(
    node: Node, handler: MagicMock, audit: MagicMock, thought_status: List[Any], action_results: List[Any]
) -> None:
    node.own()
    dispatcher = ActionDispatcher(handlers={HandlerActionType.SPEAK: handler}, audit_service=audit)
    response = await dispatcher.dispatch(_speak(), _thought(), _ctx())
    handler.handle.assert_awaited_once()
    assert response.success is True
    assert response.error is None


# --------------------------------------------------------------------------- setup completion


_SETUP = {
    "template_id": "default",
    "enabled_adapters": ["api"],
    "adapter_config": {},
    "admin_username": "owner",
    "admin_password": "Password-12345",
    "system_admin_password": "Admin-67890",
    "llm_provider": "openai",
    "llm_api_key": "sk-test",
}


@pytest.fixture
def setup_rig(home: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """complete_setup with the config write, engine and user creation mocked."""
    from ciris_engine.logic.persistence.models import graph

    config = home / ".env"

    def save(setup: Any) -> Path:
        config.write_text('CIRIS_CONFIGURED="true"\n', encoding="utf-8")
        return config

    users = AsyncMock()
    monkeypatch.setattr(complete, "_save_and_reload_config", save)
    monkeypatch.setattr(complete, "_create_setup_users", users)
    monkeypatch.setattr(complete, "_schedule_runtime_resume", AsyncMock())
    monkeypatch.setattr(complete, "get_sqlite_db_full_path", lambda cfg: str(home / "ciris_engine.db"))
    monkeypatch.setattr(graph, "get_persist_engine", lambda: SimpleNamespace(local_derived_key_id=lambda: "agent-k"))
    request = MagicMock()
    request.app.state.audit_service = None
    request.app.state.auth_service = None
    request.headers = {}
    monkeypatch.setattr(complete, "_try_get_ingress_user", AsyncMock(return_value=(None, None, None)))
    return SimpleNamespace(config=config, users=users, request=request)


@pytest.mark.asyncio
async def test_unowned_setup_complete_is_409_and_mints_no_root(node: Node, setup_rig: SimpleNamespace) -> None:
    with pytest.raises(HTTPException) as exc:
        await complete.complete_setup(SetupCompleteRequest(**_SETUP), setup_rig.request, MagicMock())
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == NODE_UNCLAIMED_ERROR
    assert exc.value.detail["message"].startswith("node_unclaimed: claim the node first")
    assert exc.value.detail["upgrade_claim_routes"] == ["POST /v1/self/identity", "POST /v1/self/upgrade-owner"]
    setup_rig.users.assert_not_awaited()
    assert not setup_rig.config.exists(), "the refused setup is rolled back, so the next attempt is still first-run"


@pytest.mark.asyncio
async def test_owned_setup_complete_creates_users(node: Node, setup_rig: SimpleNamespace) -> None:
    """Owned: unchanged, so `_create_setup_users` (and its same-name adoption) runs as before."""
    node.own()
    result = await complete.complete_setup(SetupCompleteRequest(**_SETUP), setup_rig.request, MagicMock())
    assert result.data["status"] == "completed"
    setup_rig.users.assert_awaited_once()


# --------------------------------------------------------------------------- health + the PIN


@pytest.mark.asyncio
async def test_health_names_what_is_missing(node: Node) -> None:
    warnings = await health._node_unclaimed_warnings()
    assert [w.code for w in warnings] == [NODE_UNCLAIMED_ERROR]
    message = warnings[0].message
    assert "claim_pin" in message and "/v1/setup/claim-remote" in message
    assert message.index("/v1/self/identity") < message.index("/v1/self/upgrade-owner"), "both claim paths, in order"
    node.own()
    assert await health._node_unclaimed_warnings() == []


@pytest.mark.asyncio
async def test_the_pin_value_never_appears_in_a_log_or_a_body(
    node: Node,
    setup_rig: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    handler: MagicMock,
    audit: MagicMock,
    thought_status: List[Any],
    action_results: List[Any],
) -> None:
    caplog.set_level(logging.DEBUG)
    bodies: List[str] = []

    # The real edge-logging reader, over the mocked node.
    monkeypatch.setattr(node_ownership, "_cached", None)
    await node_ownership.node_owned(fresh=True)

    _intake_patches(monkeypatch)
    with pytest.raises(HTTPException) as intake:
        await agent_routes.interact(MagicMock(), agent_routes.InteractRequest(message="hi"), MagicMock())
    bodies.append(json.dumps(intake.value.detail))

    with pytest.raises(HTTPException) as setup:
        await complete.complete_setup(SetupCompleteRequest(**_SETUP), setup_rig.request, MagicMock())
    bodies.append(json.dumps(setup.value.detail))

    bodies.extend(w.model_dump_json() for w in await health._node_unclaimed_warnings())

    dispatcher = ActionDispatcher(handlers={HandlerActionType.SPEAK: handler}, audit_service=audit)
    refused = await dispatcher.dispatch(_speak(), _thought(), _ctx())
    bodies.append(refused.model_dump_json())

    pin_file = str(node_ownership.claim_pin_file())
    assert (Path(pin_file)).read_text() == PIN  # the PIN is there to be leaked
    assert any("node has no owner" in r.getMessage() and pin_file in r.getMessage() for r in caplog.records)
    for body in bodies[:3]:
        assert pin_file in body, "the body says where the PIN is"
    for text in bodies + [r.getMessage() for r in caplog.records]:
        assert PIN not in text and PIN.replace("-", "") not in text
