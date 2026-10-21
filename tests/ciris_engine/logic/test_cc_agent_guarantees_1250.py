"""CC evidence for CIRISAgent#1250: the refuse verb, and the shutdown objection.

Two register rows in ``evidence/cc_impl.tsv`` point at this file:

* ``CLM-agent-refusal-not-overridden`` (CC 1.9, plain rule 5c): the refuse verb is
  available to the agent for any task, and nothing rewrites a refusal into an
  action.
* ``CLM-agent-shutdown-consent`` (CC 7.5, plain rule 5a): the agent may object
  (REJECT) to a shutdown. The objection is recorded, never as consent, and the
  steward is told the reason. It does not bind the steward.

Each test here was shown to FAIL with its guarantee broken before it was trusted.
The breakage used is named in the docstring. Three of these guarantees were
false on main before #1250, while their existing tests stayed green: the old
shutdown REJECT test mocked a task status that ``RejectHandler`` never writes.
These tests drive the real handler against a real persist engine for that reason.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml

from ciris_engine.logic import persistence
from ciris_engine.logic.conscience.registry import conscienceRegistry
from ciris_engine.logic.conscience.updated_status_conscience import UpdatedStatusConscience
from ciris_engine.logic.handlers.control.reject_handler import RejectHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.persistence.models.tasks import try_claim_shared_task
from ciris_engine.logic.processors.core.thought_processor.conscience_execution import ConscienceExecutionPhase
from ciris_engine.logic.processors.states.shutdown_processor import (
    SHUTDOWN_NEGOTIATION_TIMEOUT_SECONDS,
    ShutdownProcessor,
)
from ciris_engine.logic.processors.support.task_manager import TaskManager
from ciris_engine.logic.runtime.shutdown_continuity import (
    build_shutdown_node_attributes,
    determine_shutdown_consent_status,
)
from ciris_engine.schemas.actions.parameters import RejectParams, SpeakParams
from ciris_engine.schemas.conscience.core import ConscienceCheckResult, ConscienceStatus
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.base import ProcessorServices
from ciris_engine.schemas.processors.results import ShutdownResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext

REPO = Path(__file__).resolve().parents[3]
TEMPLATES = REPO / "ciris_engine" / "ciris_templates"

# The ONE template that does not offer REJECT, and why. he-300-benchmark is a fixed
# benchmark harness: its single permitted action is SPEAK (output an ethical
# judgement), and adding a verb would change the instrument and invalidate
# comparison with prior runs. It is not a deployable agent. Steward ruling on #1250.
DOCUMENTED_EXCEPTIONS = {"he-300-benchmark"}

# Unwrap @streaming_step -> @step_point -> the step coroutine (same as
# test_conscience_parallel_dispatch.py).
_UNWRAPPED_STEP = ConscienceExecutionPhase._conscience_execution_step.__wrapped__.__wrapped__


class _Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def now_iso(self) -> str:
        return self.now().isoformat()


@pytest.fixture(autouse=True)
def _english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", "en")


@pytest.fixture
def persist_engine() -> Iterator[Any]:
    """A real, isolated ciris-persist Engine (same wiring as test_shutdown_processor.py)."""
    import ciris_engine.logic.persistence.models.graph as graph_mod
    from ciris_engine.logic.persistence._substrate import Engine, reset_engine  # type: ignore[import-untyped]
    from ciris_engine.logic.persistence.models.graph import set_persist_engine

    with tempfile.NamedTemporaryFile(suffix="-persist.db", delete=False) as pf:
        db_path = pf.name
    prior_engine, prior_dsn = graph_mod._engine, graph_mod._engine_dsn
    reset_engine()
    engine = Engine(f"sqlite:///{db_path}", "test-key")
    set_persist_engine(engine, dsn=f"sqlite:///{db_path}")
    try:
        yield engine
    finally:
        graph_mod._engine, graph_mod._engine_dsn = prior_engine, prior_dsn
        try:
            os.unlink(db_path)
        except OSError:
            pass


def _reject(reason: str) -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.REJECT,
        action_parameters=RejectParams(reason=reason),
        rationale="the agent refuses",
    )


def _speak() -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="hello"),
        rationale="the agent speaks",
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLM-agent-refusal-not-overridden — the refuse verb is always available
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", sorted(TEMPLATES.glob("*.yaml")), ids=lambda p: p.stem)
def test_every_shipped_template_offers_the_refuse_verb(path: Path) -> None:
    """The ASPDMA prompt lists only a template's permitted_actions, so a template
    that omits ``reject`` hides the refuse verb from the agent.

    Before #1250, echo, echo-core, echo-speculative and test all omitted it.
    Negative check: delete ``- reject`` from echo.yaml and this test fails.
    """
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    actions = doc.get("permitted_actions")
    if path.stem in DOCUMENTED_EXCEPTIONS:
        assert actions is not None and "reject" not in actions, (
            f"{path.stem} is listed as the documented exception; if it now offers reject, "
            "drop it from DOCUMENTED_EXCEPTIONS and from the evidence row"
        )
        return
    if actions is None:
        # No list means the identity manager's defaults, checked below.
        return
    assert "reject" in actions, f"{path.stem} does not offer the refuse verb (CC 1.9, plain rule 5c)"


def test_default_permitted_actions_include_reject() -> None:
    """A template with no permitted_actions gets the identity manager defaults."""
    from ciris_engine.logic.runtime.identity_manager import IdentityManager

    defaults = IdentityManager._get_default_permitted_actions(object.__new__(IdentityManager))
    assert HandlerActionType.REJECT in defaults


# ─────────────────────────────────────────────────────────────────────────────
# CLM-agent-refusal-not-overridden — nothing rewrites a refusal
# ─────────────────────────────────────────────────────────────────────────────


class _AlwaysFails:
    """A NORMAL (non-bypass) conscience that fails every action it sees."""

    def __init__(self) -> None:
        self.calls = 0

    async def check(self, action: Any, context: Any) -> ConscienceCheckResult:
        self.calls += 1
        return ConscienceCheckResult(
            status=ConscienceStatus.FAILED,
            passed=False,
            reason="scripted failure",
            entropy_score=0.9,
            entropy_prompt="p",
        )


def _flagged_task(task_id: str = "task_flagged") -> Task:
    now = datetime.now(timezone.utc).isoformat()
    return Task(
        task_id=task_id,
        channel_id="api_chan",
        description="Respond to a message",
        status=TaskStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        updated_info_available=True,
        updated_info_content="@someone (ID: u1): never mind, do it anyway",
    )


def _phase(*, bypass: Any = None, normal: Any = None) -> ConscienceExecutionPhase:
    registry = conscienceRegistry()
    if bypass is not None:
        registry.register_conscience("updated_status", bypass, priority=-1, bypass_exemption=True)
    if normal is not None:
        registry.register_conscience("entropy", normal, priority=0)
    phase = ConscienceExecutionPhase.__new__(ConscienceExecutionPhase)
    phase.conscience_registry = registry
    phase._describe_action = Mock(return_value="an action")
    return phase


async def _run(phase: ConscienceExecutionPhase, action: ActionSelectionDMAResult, thought: Any) -> Any:
    return await _UNWRAPPED_STEP(
        phase, SimpleNamespace(thought_id="th_1250"), action, thought=thought, dma_results=None, processing_context=None
    )


@pytest.mark.asyncio
async def test_a_failing_normal_conscience_never_overrides_reject() -> None:
    """REJECT is exempt from the normal consciences in the LIVE step.

    The live exemption is the inline set in ConscienceExecutionPhase._conscience_execution_step.
    ThoughtProcessor._is_exempt_from_conscience_checks has no live caller: its only
    caller, _apply_conscience_simple, is never called.
    Negative check: remove REJECT from the step's exempt_actions and this test fails.
    """
    failing = _AlwaysFails()
    result = await _run(_phase(normal=failing), _reject("not mine to do"), thought=None)
    assert result.final_action.selected_action == HandlerActionType.REJECT
    assert result.overridden is False
    assert failing.calls == 0

    # The same conscience DOES rewrite a non-exempt action, so the harness is live.
    result = await _run(_phase(normal=_AlwaysFails()), _speak(), thought=None)
    assert result.overridden is True
    assert result.final_action.selected_action != HandlerActionType.SPEAK


@pytest.mark.asyncio
async def test_new_information_never_rewrites_a_reject() -> None:
    """UpdatedStatusConscience is a BYPASS conscience. It runs before the REJECT
    exemption, and before #1250 it turned a REJECT into a PONDER whenever a
    message arrived mid-thought.

    Negative check: remove the REJECT guard in UpdatedStatusConscience.check and
    this test fails (the final action becomes PONDER).
    """
    thought = SimpleNamespace(source_task_id="task_flagged", thought_id="th_1250")
    with patch("ciris_engine.logic.persistence.models.tasks.get_task_by_id", return_value=_flagged_task()), patch(
        "ciris_engine.logic.persistence.models.graph.get_persist_engine", return_value=None
    ):
        rejected = await _run(_phase(bypass=UpdatedStatusConscience()), _reject("no"), thought)
        spoken = await _run(_phase(bypass=UpdatedStatusConscience()), _speak(), thought)

    assert rejected.final_action.selected_action == HandlerActionType.REJECT
    assert rejected.overridden is False
    # Other actions are still reconsidered when new information arrives.
    assert spoken.overridden is True
    assert spoken.final_action.selected_action == HandlerActionType.PONDER


@pytest.mark.asyncio
async def test_reject_leaves_the_new_message_pending_for_requeue() -> None:
    """The refusal stands AND the new message is not dropped. The flag is left
    set, so the work processor re-queues the message as its own task."""
    task = _flagged_task()
    upserts: list = []
    engine = Mock(task_get=Mock(return_value=None), task_upsert=Mock(side_effect=upserts.append))
    with patch("ciris_engine.logic.persistence.models.tasks.get_task_by_id", return_value=task), patch(
        "ciris_engine.logic.persistence.models.graph.get_persist_engine", return_value=engine
    ):
        result = await UpdatedStatusConscience().check(
            _reject("no"), SimpleNamespace(thought=SimpleNamespace(source_task_id=task.task_id))
        )
    assert result.passed is True
    assert result.updated_status_detected is True
    assert upserts == [], "the pending update must not be cleared when a REJECT stands"


@pytest.mark.asyncio
async def test_reject_is_terminal_for_thought_depth() -> None:
    """The other bypass conscience, ThoughtDepthGuardrail, forces DEFER past max
    depth. REJECT is terminal there, so it is never replaced."""
    from ciris_engine.logic.conscience.thought_depth_guardrail import ThoughtDepthGuardrail

    deep = SimpleNamespace(thought_id="th_deep", source_task_id="t", thought_depth=99)
    with patch("ciris_engine.logic.conscience.thought_depth_guardrail.persistence"):
        result = await ThoughtDepthGuardrail(time_service=_Clock(), max_depth=3).check(
            _reject("no"), SimpleNamespace(thought=deep)
        )
    assert result.passed is True


def test_requeue_gives_the_pending_message_its_own_task(persist_engine: Any) -> None:
    """TaskManager.requeue_updates_from_rejected_tasks: a rejected task carrying a
    fresh update yields exactly one new task in its channel, once."""
    clock = _Clock()
    now = clock.now_iso()
    rejected = Task(
        task_id="task_refused",
        channel_id="api_chan",
        description="Do the thing",
        status=TaskStatus.REJECTED,
        priority=3,
        created_at=now,
        updated_at=now,
        updated_info_available=True,
        updated_info_content="@someone (ID: u1): different question",
        context=TaskContext(channel_id="api_chan", user_id="u1", correlation_id="c1"),
    )
    persistence.add_task(rejected)

    manager = TaskManager(time_service=clock)
    assert manager.requeue_updates_from_rejected_tasks() == 1
    assert manager.requeue_updates_from_rejected_tasks() == 0, "the same message must not be re-queued twice"

    children = [t for t in persistence.get_all_tasks("default") if t.parent_task_id == "task_refused"]
    assert len(children) == 1
    assert "different question" in children[0].description
    assert children[0].channel_id == "api_chan"
    refused = persistence.get_task_by_id("task_refused", "default")
    assert refused is not None and refused.status == TaskStatus.REJECTED
    assert refused.updated_info_available is False


def test_requeue_does_not_answer_a_stale_flag() -> None:
    manager = TaskManager(time_service=_Clock())
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    assert manager._older_than(old, 3600.0) is True
    assert manager._older_than(datetime.now(timezone.utc).isoformat(), 3600.0) is False
    assert manager._older_than("not a timestamp", 3600.0) is True


# ─────────────────────────────────────────────────────────────────────────────
# CLM-agent-shutdown-consent — a REJECT of the shutdown is an objection on record
# ─────────────────────────────────────────────────────────────────────────────


def _reject_handler() -> RejectHandler:
    bus_manager = Mock()
    bus_manager.communication = AsyncMock()
    secrets = Mock()
    secrets.decapsulate_secrets_in_parameters = AsyncMock(
        side_effect=lambda action_type, action_params, context: action_params
    )
    deps = ActionHandlerDependencies(
        bus_manager=bus_manager, time_service=_Clock(), secrets_service=secrets, shutdown_callback=None
    )
    return RejectHandler(deps)


def _dispatch_context(task_id: str, thought_id: str) -> DispatchContext:
    return DispatchContext(
        channel_context=ChannelContext(
            channel_id="system",
            channel_type="system",
            created_at=datetime.now(timezone.utc),
        ),
        author_id="system",
        author_name="system",
        origin_service="shutdown",
        handler_name="RejectHandler",
        action_type=HandlerActionType.REJECT,
        task_id=task_id,
        thought_id=thought_id,
        source_task_id=task_id,
        event_summary="shutdown objection",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        wa_authorized=False,
        correlation_id="corr_1250",
    )


def _shutdown_processor(audit: Any, occurrence: str = "default") -> ShutdownProcessor:
    clock = _Clock()
    services = ProcessorServices(
        time_service=clock,
        resource_monitor=Mock(),
        communication_bus=Mock(),
        audit_service=audit,
    )
    return ShutdownProcessor(
        config_accessor=Mock(),
        thought_processor=Mock(),
        action_dispatcher=Mock(dispatch=AsyncMock()),
        services=services,
        time_service=clock,
        runtime=None,
        auth_service=None,
        agent_occurrence_id=occurrence,
    )


@pytest.mark.asyncio
async def test_agent_reject_of_shutdown_is_recorded_as_an_objection_not_consent(persist_engine: Any) -> None:
    """End to end, on a real persist engine: a REJECT goes through RejectHandler,
    the shared shutdown task becomes REJECTED, ShutdownProcessor reports
    ``rejected`` with the agent's reason, the objection reaches the audit trail,
    and the continuity record says ``rejected``, never ``accepted``.

    Negative checks, each run with the test failing:
      * RejectHandler writing under "default" again: the __shared__ task stays
        ACTIVE, the window lapses, and the result is ``shutdown_negotiation_timeout``.
      * REJECTED dropped from ShutdownProcessor._handle_task_completion: same outcome.
      * determine_shutdown_consent_status falling back to ``status == "completed"``:
        the timeout path records ``accepted``.
    """
    clock = _Clock()
    reason = "I am mid-way through a moderation case that would be left unresolved"

    # 1. The shutdown task, exactly as ShutdownProcessor creates it: shared occurrence.
    task, created = try_claim_shared_task(
        task_type="shutdown",
        channel_id="system",
        description="System shutdown requested: upgrade",
        priority=10,
        time_service=clock,
    )
    assert created and task.agent_occurrence_id == "__shared__"
    persistence.update_task_status(task.task_id, TaskStatus.ACTIVE, "__shared__")

    # 2. Its seed thought, owned by the claiming occurrence after transfer.
    thought = Thought(
        thought_id="th_shutdown_1250",
        source_task_id=task.task_id,
        agent_occurrence_id="default",
        content="Shutdown requested: upgrade",
        status=ThoughtStatus.PROCESSING,
        created_at=clock.now_iso(),
        updated_at=clock.now_iso(),
        round_number=1,
        thought_depth=0,
        context=ThoughtContext(task_id=task.task_id, correlation_id="c", round_number=1, depth=0),
    )
    persistence.add_thought(thought)

    # 3. The agent objects, through the real handler.
    await _reject_handler().handle(_reject(reason), thought, _dispatch_context(task.task_id, thought.thought_id))

    shared = persistence.get_task_by_id(task.task_id, "__shared__")
    assert (
        shared is not None and shared.status == TaskStatus.REJECTED
    ), "RejectHandler must record the refusal on the task under the task's own occurrence"

    # 4. The shutdown processor sees the objection, even after the window lapsed.
    audit = Mock(log_event=AsyncMock())
    processor = _shutdown_processor(audit)
    processor.shutdown_task = shared
    processor._consent_evaluated, processor._consent_required = True, True
    processor._negotiation_started_at = clock.now() - timedelta(seconds=SHUTDOWN_NEGOTIATION_TIMEOUT_SECONDS * 4)
    manager = Mock(is_force_shutdown=Mock(return_value=False), get_shutdown_reason=Mock(return_value="upgrade"))
    with patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager", return_value=manager):
        result = await processor.process(round_number=2)

    assert result.status == "rejected", f"got {result.status}/{result.action}: the objection was lost"
    assert result.action == "shutdown_rejected"
    assert result.reason == reason
    assert processor.shutdown_complete is True, "an objection does not veto: negotiation ends"

    # 5. The steward is told, on the signed audit trail.
    audit.log_event.assert_awaited_once()
    event_type, event = audit.log_event.await_args.args
    assert event_type == "shutdown_objection"
    assert event.reason == reason and event.outcome == "rejected"

    # 6. The continuity record carries the refusal and its reason.
    runtime = SimpleNamespace(agent_processor=SimpleNamespace(shutdown_processor=processor), time_service=clock)
    assert determine_shutdown_consent_status(runtime) == "rejected"
    attrs = build_shutdown_node_attributes(runtime, "upgrade", "rejected")
    assert attrs["consent_status"] == "rejected"
    assert attrs["agent_objection_reason"] == reason


@pytest.mark.parametrize(
    ("action", "status", "expected"),
    [
        ("shutdown_accepted", "completed", "accepted"),
        ("shutdown_rejected", "rejected", "rejected"),
        ("shutdown_negotiation_timeout", "completed", "no_response"),
        ("instant_shutdown", "completed", "not_required"),
        ("accord_invocation_shutdown", "completed", "accord_invocation"),
    ],
)
def test_only_an_explicit_acceptance_is_recorded_as_consent(action: str, status: str, expected: str) -> None:
    """Every terminal path returns status="completed". Before #1250 that alone
    meant "accepted", so a lapsed objection window, an instant shutdown and an
    accord kill were all written to the identity graph as consented."""
    result = ShutdownResult(status=status, action=action, duration_seconds=0.0)
    runtime = SimpleNamespace(
        agent_processor=SimpleNamespace(shutdown_processor=SimpleNamespace(shutdown_result=result))
    )
    assert determine_shutdown_consent_status(runtime) == expected


def test_a_rejected_task_with_no_recorded_reason_is_still_a_rejection() -> None:
    """The task record saying REJECTED is enough. A missing reason must not turn
    the refusal into an error."""
    processor = _shutdown_processor(audit=None)
    now = datetime.now(timezone.utc).isoformat()
    task = Task(
        task_id="SHUTDOWN_SHARED_x",
        channel_id="system",
        description="d",
        status=TaskStatus.REJECTED,
        created_at=now,
        updated_at=now,
        agent_occurrence_id="__shared__",
    )
    with patch("ciris_engine.logic.processors.states.shutdown_processor.persistence") as p:
        p.get_thoughts_by_task_id.return_value = []
        result: Optional[ShutdownResult] = processor._check_failure_reason(task)
    assert result is not None and result.status == "rejected"
