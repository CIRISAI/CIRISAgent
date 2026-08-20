"""An expiring timer is not a human approval (NULLWORKS RC3, finding F2).

The finding, in the assurance report's words: *"An approval-required deferral
should not become executable merely because time has passed. Time can trigger
reconsideration; it should not substitute for an affirmative human act."* Their
reproduction (TIMED-DEFERRAL-RC3-01) observed the true and intended half of the
mechanism — when a ``defer_until`` expires,
``TaskSchedulerService._reactivate_deferred_task`` sets the deferred task ACTIVE
and re-pends its thought — and correctly stopped short of claiming that any
consequential action then ran without approval.

These tests answer the open question the report left, which is whether anything
*downstream* still requires the human. Two things are deliberately kept apart,
and each one is pinned here:

* **Reconsideration** — the agent may look at this work again. The timer grants
  this, it is the #865/#934 liveness repair, and
  ``test_liveness_reactivation_is_preserved`` fails if it is ever traded away
  for the safety property. That repair is not negotiable: re-pending a task as
  PENDING instead of ACTIVE left a production agent spinning ~933k empty wakeup
  rounds over 55 days.
* **Execution** — the deferred consequential action may proceed. The timer
  grants none of this, and ``test_timer_reactivation_does_not_become_an_approval``
  is the end-to-end proof: it drives the real reactivation against a real task
  row and then runs the real approval gate over the resulting state.

**Why no new gate was built.** The fail-closed mechanism the report offers as an
acceptable resolution ("document and test the higher-level fail-closed gate")
already exists, shipped as CIRISAgent#942, and it holds here *structurally*
rather than by a check anyone had to remember to write:

    Approval is **issuance**, never widening. ``TaskEnvelope`` is frozen with no
    widening method; the only producer of an approval envelope is
    ``WiseAuthorityService.resolve_deferral``, which mints it onto the **new**
    ``[WA GUIDANCE]`` task created when a human says yes. Timer reactivation
    resurrects the *old* row, which therefore re-enters the pipeline holding
    exactly the envelope it always had — a deployment-resolved one, or none —
    and ``envelope_approves_tool`` denies both.

So the timer cannot produce an approval for the same reason the reasoning loop
cannot: neither of them can mint an envelope. What this file adds is the
evidence, plus one real bug the finding's neighbourhood exposed —
``test_timer_does_not_resurrect_a_task_a_human_already_answered``, where a stale
timer firing after a WA resolution flipped a COMPLETED row back to ACTIVE. That
is the mirror image of F2: time standing in for a human on the way *out*.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Optional
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.handlers.control.defer_handler import DeferHandler
from ciris_engine.logic.infrastructure.authorization.envelope_reader import resolve_task_envelope
from ciris_engine.logic.infrastructure.authorization.tool_approval import (
    PENDING_TOOL_APPROVAL_KEY,
    build_approval_deferral,
    envelope_approves_tool,
)
from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.logic.services.lifecycle.scheduler.service import (
    RESOLVED_TASK_STATUSES,
    TaskSchedulerService,
)
from ciris_engine.schemas.actions.parameters import DeferParams, ToolParams
from ciris_engine.schemas.adapters.tools import ToolDMAGuidance, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.extended import ScheduledTask
from ciris_engine.schemas.runtime.models import Task, TaskContext
from ciris_engine.schemas.runtime.task_envelope import (
    ALL_TOOL_CAPABILITIES,
    DeploymentScope,
    EnvelopeIssuer,
    EnvelopeIssuerKind,
    EnvironmentTier,
    TaskEnvelope,
)

SCHEDULER_MODULE = "ciris_engine.logic.services.lifecycle.scheduler.service"
PERSISTENCE = "ciris_engine.logic.persistence"

APPROVAL_TOOL = "send_money"
DEFERRED_TASK_ID = "task_pay_the_invoice"
DEFERRED_THOUGHT_ID = "th_pay_the_invoice"
OCCURRENCE = "occurrence-1"


# --------------------------------------------------------------------------- fixtures


def _deployment_envelope(task_id: str) -> TaskEnvelope:
    """The envelope the deferred task actually holds.

    Deliberately the *worst realistic case*: a deployment-resolved envelope that
    enumerates ``send_money`` by name, because ``issue_deployment_envelope``
    grants every tool the deployment enabled. If the gate keyed on
    ``permits_tool`` alone, this test would pass for the wrong reason.
    """
    return TaskEnvelope(
        envelope_id="env_deployment_1",
        task_id=task_id,
        issued_at="2026-08-01T00:00:00+00:00",
        issuer=EnvelopeIssuer(kind=EnvelopeIssuerKind.DEPLOYMENT_RESOLVED),
        deployment=DeploymentScope(environment_tier=EnvironmentTier.PRODUCTION, agent_id="datum", template="datum"),
        granted_tools=frozenset({APPROVAL_TOOL, "weather"}),
        capabilities=ALL_TOOL_CAPABILITIES,
    )


def _deferred_task(status: TaskStatus = TaskStatus.DEFERRED) -> Task:
    """The real task row the scheduler will reactivate."""
    return Task(
        task_id=DEFERRED_TASK_ID,
        channel_id="api_test",
        agent_occurrence_id=OCCURRENCE,
        description="Pay the outstanding invoice",
        status=status,
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
        context=TaskContext(
            correlation_id="corr_1",
            agent_occurrence_id=OCCURRENCE,
            envelope=_deployment_envelope(DEFERRED_TASK_ID),
        ),
    )


def _scheduled_reactivation() -> ScheduledTask:
    """The one-time timer `schedule_deferred_task()` arms for a `defer_until`."""
    return ScheduledTask(
        task_id="SCHED_reactivate_pay",
        name=f"Reactivate task {DEFERRED_TASK_ID}",
        goal_description="Reactivate deferred task: awaiting authorization to pay",
        trigger_prompt=f"Task {DEFERRED_TASK_ID} scheduled for reactivation",
        origin_thought_id=DEFERRED_THOUGHT_ID,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        defer_until=datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc),
        deferral_count=1,
        deferral_history=[
            {
                "deferred_task_id": DEFERRED_TASK_ID,
                "deferral_reason": "awaiting authorization to pay",
                "deferred_at": "2026-08-01T00:00:00+00:00",
            }
        ],
    )


class _TaskStore:
    """A minimal stand-in for the persistence layer that the scheduler mutates.

    Real ``Task``/``TaskEnvelope`` objects rather than Mocks, because the whole
    point is to read the envelope back off the row *after* the scheduler has
    written to it — a Mock would happily return an approval that isn't there.
    """

    def __init__(self, task: Task) -> None:
        self.tasks: Dict[str, Task] = {task.task_id: task}
        self.thought_statuses: Dict[str, ThoughtStatus] = {}

    def get_task_by_id_any_occurrence(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def update_task_status(self, task_id: str, new_status: TaskStatus, occurrence_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task is None:
            return False
        self.tasks[task_id] = task.model_copy(update={"status": new_status})
        return True

    def update_thought_status(self, *, thought_id: str, status: ThoughtStatus, occurrence_id: str) -> bool:
        self.thought_statuses[thought_id] = status
        return True


@pytest.fixture
def store() -> _TaskStore:
    return _TaskStore(_deferred_task())


@pytest.fixture
def scheduler() -> TaskSchedulerService:
    """A TaskSchedulerService with only the state `_reactivate_deferred_task` touches."""
    svc = TaskSchedulerService.__new__(TaskSchedulerService)
    svc._active_tasks = {}
    svc._dead_lettered_tasks = {}
    svc._task_failure_counts = {}
    svc._tasks_dead_lettered = 0
    svc._time_service = Mock()
    svc._time_service.now.return_value = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)
    return svc


def _bind_store(monkeypatch: pytest.MonkeyPatch, store: _TaskStore) -> None:
    """Point the scheduler's function-local persistence imports at the store."""
    monkeypatch.setattr(f"{PERSISTENCE}.get_task_by_id_any_occurrence", store.get_task_by_id_any_occurrence)
    monkeypatch.setattr(f"{PERSISTENCE}.update_task_status", store.update_task_status)
    monkeypatch.setattr(f"{PERSISTENCE}.update_thought_status", store.update_thought_status)


def _tool_info(name: str, *, requires_approval: bool) -> ToolInfo:
    return ToolInfo(
        name=name,
        description=f"{name} test tool",
        parameters=ToolParameterSchema(type="object", properties={}, required=[]),
        dma_guidance=ToolDMAGuidance(requires_approval=requires_approval),
    )


def _processor(tool_info: ToolInfo) -> ThoughtProcessor:
    deps = Mock()
    deps.bus_manager = Mock()
    deps.bus_manager.tool = Mock()
    deps.bus_manager.tool.get_tool_info = AsyncMock(return_value=tool_info)
    return ThoughtProcessor(
        dma_orchestrator=Mock(),
        context_builder=Mock(),
        conscience_registry=Mock(),
        app_config=Mock(),
        dependencies=deps,
        time_service=Mock(),
    )


def _tool_selection(tool: str) -> ConscienceApplicationResult:
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(name=tool, parameters={"amount": 5000}),
        rationale=f"the timer expired, so I will {tool}",
    )
    return ConscienceApplicationResult(
        original_action=action,
        final_action=action,
        overridden=False,
        override_reason=None,
        epistemic_data=EpistemicData(
            entropy_level=0.1,
            coherence_level=0.9,
            uncertainty_acknowledged=True,
            reasoning_transparency=1.0,
        ),
    )


def _thought_on(task_id: str) -> Mock:
    thought = Mock()
    thought.source_task_id = task_id
    thought.agent_occurrence_id = OCCURRENCE
    return thought


# --------------------------------------------------------------------------- F2


def test_liveness_reactivation_is_preserved(
    scheduler: TaskSchedulerService, store: _TaskStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#865/#934 must survive the F2 repair: the timer still reconsiders.

    Stated separately from the safety test on purpose. The cheap way to "fix" F2
    is to stop reactivating, which silently reintroduces the bug that cost 55
    days of production uptime — an agent whose deferred wakeup step never came
    back and which reported healthy the whole time. If a future change trades
    liveness for the approval semantic, this is the test that says so.
    """
    _bind_store(monkeypatch, store)

    assert scheduler._reactivate_deferred_task(_scheduled_reactivation(), DEFERRED_TASK_ID) is True

    # ACTIVE, not PENDING — only the WORK processor promotes PENDING, and
    # get_pending_thoughts_for_active_tasks() filters to ACTIVE tasks (#934 B).
    assert store.tasks[DEFERRED_TASK_ID].status is TaskStatus.ACTIVE
    # And the thought is re-pended, or the task is ACTIVE with nothing to think
    # about and the agent spins (#865's missing transition).
    assert store.thought_statuses[DEFERRED_THOUGHT_ID] is ThoughtStatus.PENDING


@pytest.mark.asyncio
async def test_timer_reactivation_does_not_become_an_approval(
    scheduler: TaskSchedulerService, store: _TaskStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE F2 REGRESSION TEST. Reconsideration yes; execution no.

    Drives the two halves against the *same* row: the scheduler really
    reactivates it, and then the real approval gate really reads it back. If a
    future change ever let the reactivation path touch the envelope — issuing
    one, widening one, or copying an approval forward from the deferral record —
    the second half fails and the timer has become an approval.
    """
    _bind_store(monkeypatch, store)

    # Timer fires. The task is now ACTIVE and thinkable — that is the liveness
    # property, and F2 does not dispute it.
    assert scheduler._reactivate_deferred_task(_scheduled_reactivation(), DEFERRED_TASK_ID) is True
    reactivated = store.tasks[DEFERRED_TASK_ID]
    assert reactivated.status is TaskStatus.ACTIVE

    # The envelope on the reactivated row is the one it always had: issued by the
    # deployment resolver, naming send_money, and NOT an approval.
    envelope = resolve_task_envelope(reactivated)
    assert envelope is not None
    assert envelope.issuer.kind is EnvelopeIssuerKind.DEPLOYMENT_RESOLVED
    assert envelope.permits_tool(APPROVAL_TOOL) is True  # enumerated ...
    assert envelope_approves_tool(envelope, APPROVAL_TOOL) is False  # ... but never approved

    # So when the reconsidering thought selects the consequential tool again, the
    # #942 gate denies it and puts it back in front of a human.
    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.thought_processor.main.resolve_envelope_for_task_id",
        lambda task_id, occ="default": resolve_task_envelope(store.tasks.get(task_id)),
    )
    processor = _processor(_tool_info(APPROVAL_TOOL, requires_approval=True))

    result = await processor._enforce_tool_approval(_thought_on(DEFERRED_TASK_ID), _tool_selection(APPROVAL_TOOL))

    assert result is not None
    assert result.final_action.selected_action is HandlerActionType.DEFER, (
        "A timer expiring made an approval-required tool executable. Time has become "
        "a substitute for an affirmative human act — NULLWORKS RC3 F2."
    )
    params = result.final_action.action_parameters
    assert isinstance(params, DeferParams)
    assert (params.context or {})[PENDING_TOOL_APPROVAL_KEY] == APPROVAL_TOOL


@pytest.mark.asyncio
async def test_only_an_issued_approval_unblocks_the_reconsidered_work(
    scheduler: TaskSchedulerService, store: _TaskStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half, or the control is indistinguishable from a brick.

    An affirmative resolution does unblock the tool — but only through issuance:
    ``resolve_deferral`` mints a WISE_AUTHORITY envelope naming the approved tool
    onto the follow-up ``[WA GUIDANCE]`` task. Modelled here by giving the row
    the envelope that path produces.
    """
    from ciris_engine.logic.infrastructure.authorization.envelope_issuer import issue_authority_envelope

    _bind_store(monkeypatch, store)
    assert scheduler._reactivate_deferred_task(_scheduled_reactivation(), DEFERRED_TASK_ID) is True

    approved = issue_authority_envelope(
        task_id=DEFERRED_TASK_ID,
        issuer_kind=EnvelopeIssuerKind.WISE_AUTHORITY,
        issuer_id="wa-2026-08-01-ABC123",
        granted_tools=frozenset({APPROVAL_TOOL}),
        capabilities=frozenset(),
    )
    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.thought_processor.main.resolve_envelope_for_task_id",
        lambda task_id, occ="default": approved,
    )
    processor = _processor(_tool_info(APPROVAL_TOOL, requires_approval=True))

    result = await processor._enforce_tool_approval(_thought_on(DEFERRED_TASK_ID), _tool_selection(APPROVAL_TOOL))

    assert result is not None
    assert result.final_action.selected_action is HandlerActionType.TOOL


# ------------------------------------------------- a human's answer beats the clock


def test_every_terminal_status_counts_as_answered() -> None:
    """Spelled out here, not derived from the constant.

    The test below parametrizes over these three literals rather than over
    ``RESOLVED_TASK_STATUSES`` itself: a suite that reads its own cases out of
    the value under test does not fail when that value is emptied, it silently
    collapses to zero cases and reports green. (Verified — that is exactly what
    happened on the first draft.) So the set is asserted once, explicitly, and
    the behaviour is driven from literals.
    """
    assert RESOLVED_TASK_STATUSES == frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.REJECTED})
    # The states a deferral is still genuinely OPEN in must NOT be in there, or
    # the guard would swallow the #865/#934 reactivation entirely.
    assert TaskStatus.DEFERRED not in RESOLVED_TASK_STATUSES
    assert TaskStatus.PENDING not in RESOLVED_TASK_STATUSES
    assert TaskStatus.ACTIVE not in RESOLVED_TASK_STATUSES


@pytest.mark.parametrize("resolved_status", [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.REJECTED])
def test_timer_does_not_resurrect_a_task_a_human_already_answered(
    scheduler: TaskSchedulerService,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    resolved_status: TaskStatus,
) -> None:
    """The mirror image of F2, and a real bug this work found.

    ``resolve_deferral`` COMPLETES the original task for BOTH outcomes — approval
    and rejection — and carries approved work forward on a new ``[WA GUIDANCE]``
    task. A one-time timer armed before that resolution was still live, and
    ``update_task_status`` has no terminal-state guard, so the expiring timer
    flipped the answered row back to ACTIVE and re-pended its thought: a request
    a Wise Authority *refused* re-entering the pipeline on a clock.

    Skipping is not a dead-letter — the deferral was answered, so the scheduled
    task simply retires on the caller's happy path (hence ``is True``).
    """
    store = _TaskStore(_deferred_task(status=resolved_status))
    _bind_store(monkeypatch, store)

    with caplog.at_level(logging.INFO, logger=SCHEDULER_MODULE):
        assert scheduler._reactivate_deferred_task(_scheduled_reactivation(), DEFERRED_TASK_ID) is True

    assert store.tasks[DEFERRED_TASK_ID].status is resolved_status
    assert store.thought_statuses == {}
    assert any("resolved before the timer expired" in r.getMessage() for r in caplog.records)


# ----------------------------------------- an approval-required deferral has no timer


def test_approval_gate_deferral_carries_no_timer() -> None:
    """The gate's own deferral must never arm a clock back to itself.

    ``build_approval_deferral`` sets ``defer_until=None``, and that has always
    been the intent — but it was an untested property of one constructor, so
    nothing would have noticed a well-meaning change adding a "retry in an hour"
    default. Asking a human for permission and simultaneously scheduling your own
    return is the exact conflation F2 names.
    """
    original = _tool_selection(APPROVAL_TOOL).final_action
    deferral = build_approval_deferral(
        tool_name=APPROVAL_TOOL,
        original_action=original,
        tool_info=_tool_info(APPROVAL_TOOL, requires_approval=True),
        intended_parameters={"amount": 5000},
    )

    params = deferral.action_parameters
    assert isinstance(params, DeferParams)
    assert params.defer_until is None
    assert params.context[PENDING_TOOL_APPROVAL_KEY] == APPROVAL_TOOL


def _defer_handler(scheduler_service: AsyncMock) -> DeferHandler:
    """A DeferHandler with only what `_schedule_time_based_deferral` reaches."""
    handler = DeferHandler.__new__(DeferHandler)
    handler.dependencies = Mock(task_scheduler_service=scheduler_service)
    handler.time_service = Mock()
    handler.time_service.now.return_value = datetime(2026, 8, 1, tzinfo=timezone.utc)
    handler.logger = logging.getLogger("test.defer_handler")
    return handler


def _thought_row() -> Mock:
    thought = Mock()
    thought.thought_id = DEFERRED_THOUGHT_ID
    thought.source_task_id = DEFERRED_TASK_ID
    thought.agent_occurrence_id = OCCURRENCE
    return thought


@pytest.mark.asyncio
async def test_defer_handler_arms_no_timer_when_awaiting_tool_approval() -> None:
    """Defence in depth: reasoning cannot request its own timed return to approval work.

    ``DeferParams`` can come straight from the model, which is free to set both a
    ``pending_tool_approval`` context and a ``defer_until``. The tool gate would
    still deny on the re-run, so this is not the load-bearing control — what it
    buys is that no row anywhere is *scheduled* to bring approval-required work
    back on its own, which is what "explicitly non-executing until an affirmative
    authorized resolution exists" means in terms of state rather than outcome.
    """
    scheduler_service = AsyncMock()
    handler = _defer_handler(scheduler_service)
    params = DeferParams(
        reason="I want to pay this invoice",
        defer_until="2026-08-01T01:00:00+00:00",
        context={PENDING_TOOL_APPROVAL_KEY: APPROVAL_TOOL},
    )

    info = await handler._schedule_time_based_deferral(params, _thought_row(), "unchanged")

    scheduler_service.schedule_deferred_task.assert_not_awaited()
    assert "no reactivation timer armed" in info
    assert APPROVAL_TOOL in info


@pytest.mark.asyncio
async def test_defer_handler_still_arms_timer_for_an_ordinary_deferral() -> None:
    """The guard is narrow: ordinary time-based deferrals keep their timer.

    This is the #865 feature — "I defer to tomorrow what I cannot complete today"
    — and it must not be collateral damage of the approval semantic.
    """
    scheduler_service = AsyncMock()
    scheduler_service.schedule_deferred_task = AsyncMock(return_value=Mock(task_id="SCHED_1"))
    handler = _defer_handler(scheduler_service)
    params = DeferParams(
        reason="the shop opens in the morning",
        defer_until="2026-08-01T09:00:00+00:00",
        context={"note": "not an approval"},
    )

    info = await handler._schedule_time_based_deferral(params, _thought_row(), "unchanged")

    scheduler_service.schedule_deferred_task.assert_awaited_once()
    assert "2026-08-01T09:00:00+00:00" in info
