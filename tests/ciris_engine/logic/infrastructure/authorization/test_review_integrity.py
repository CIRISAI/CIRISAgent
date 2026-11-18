"""Execute only what was reviewed (CIRISAgent#1366 item 10).

FSD/PROMPT_CONTEXT_PROVENANCE.md §9 "Review integrity"; ``ReviewIntegrity`` in
formal/h3ere_ctxflow/H3EREContextFlow.tla, which ``PostReviewChange`` breaks.

Each test names the code it fails without:

* alias resolution before review      -> ``ThoughtProcessor._resolve_tool_alias``
* stamping at conscience pass         -> ``ThoughtProcessor._stamp_reviewed_action``
* the dispatch check                  -> ``ToolHandler._refuse_if_changed_since_review``
* approvals bound to the call         -> ``envelope_approves_call`` + ``approved_calls``
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.external.tool_handler import ToolHandler
from ciris_engine.logic.infrastructure.authorization.envelope_issuer import issue_authority_envelope
from ciris_engine.logic.infrastructure.authorization.reviewed_action import (
    reviewed_action_fingerprint,
    tool_call_fingerprint,
)
from ciris_engine.logic.infrastructure.authorization.tool_approval import (
    PENDING_TOOL_APPROVAL_KEY,
    PENDING_TOOL_CALL_FINGERPRINT_KEY,
    TOOL_APPROVAL_DETAIL_KEY,
    encode_tool_approval_detail,
    envelope_approves_call,
)
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.schemas.actions.parameters import DeferParams, ToolParams
from ciris_engine.schemas.adapters.tools import (
    ToolDMAGuidance,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolInfo,
    ToolParameterSchema,
)
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.runtime.task_envelope import EnvelopeIssuerKind, TaskEnvelope

ALIASES = {"todoist": "skill:todoist-cli"}


# --------------------------------------------------------------------------- helpers


def _tool(name: str, parameters: Optional[Dict[str, Any]] = None, channel_id: Optional[str] = "ch1") -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(name=name, parameters=parameters or {}, channel_id=channel_id),
        rationale="test",
    )


def _stamped(action: ActionSelectionDMAResult) -> ActionSelectionDMAResult:
    return action.model_copy(update={"reviewed_action_hash": reviewed_action_fingerprint(action)})


def _passed(action: ActionSelectionDMAResult, *, overridden: bool = False) -> ConscienceApplicationResult:
    return ConscienceApplicationResult(
        original_action=action,
        final_action=action,
        overridden=overridden,
        override_reason=None,
        epistemic_data=EpistemicData(
            entropy_level=0.1, coherence_level=0.9, uncertainty_acknowledged=True, reasoning_transparency=1.0
        ),
    )


def _processor(tool_info: Optional[ToolInfo] = None) -> ThoughtProcessor:
    deps = Mock()
    deps.bus_manager = Mock()
    deps.bus_manager.tool = Mock()
    deps.bus_manager.tool.resolve_tool_name = lambda n: ALIASES.get(n, n)
    deps.bus_manager.tool.get_tool_info = AsyncMock(return_value=tool_info)
    return ThoughtProcessor(
        dma_orchestrator=Mock(),
        context_builder=Mock(),
        conscience_registry=Mock(),
        app_config=Mock(),
        dependencies=deps,
        time_service=Mock(),
    )


# --------------------------------------------------------------------------- fingerprint


def test_fingerprint_covers_tool_arguments_and_target_only() -> None:
    base = _tool("send_money", {"amount": 10, "to": "{SECRET:abc:account}"})
    fp = reviewed_action_fingerprint(base)
    assert fp is not None and fp.startswith("-16:")  # rc21 §4 [-16, digest]
    assert reviewed_action_fingerprint(_tool("send_money", {"to": "{SECRET:abc:account}", "amount": 10})) == fp
    assert reviewed_action_fingerprint(_tool("send_money", {"amount": 11, "to": "{SECRET:abc:account}"})) != fp
    assert reviewed_action_fingerprint(_tool("send_money", {"amount": "10", "to": "{SECRET:abc:account}"})) != fp
    assert reviewed_action_fingerprint(_tool("send_cash", {"amount": 10, "to": "{SECRET:abc:account}"})) != fp
    assert reviewed_action_fingerprint(_tool("send_money", {"amount": 10, "to": "{SECRET:abc:account}"}, "ch2")) != fp
    # Not part of what was reviewed: rationale and prompts.
    assert reviewed_action_fingerprint(base.model_copy(update={"rationale": "other"})) == fp
    # Not a tool call -> not reviewable.
    assert (
        reviewed_action_fingerprint(
            ActionSelectionDMAResult(
                selected_action=HandlerActionType.DEFER,
                action_parameters=DeferParams(reason="r"),
                rationale="r",
            )
        )
        is None
    )


# --------------------------------------------------------------------------- alias before review


@pytest.mark.asyncio
async def test_alias_is_resolved_before_the_consciences_review_the_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    """The consciences must review the tool that will run, not its alias."""
    processor = _processor()
    seen_by_second_pass: List[str] = []
    seen_by_consciences: List[str] = []

    async def fake_second_pass(self: Any, thought_item: Any, action_result: Any, ctx: Any, **_: Any) -> Any:
        seen_by_second_pass.append(action_result.action_parameters.name)
        return action_result

    async def fake_consciences(thought_item: Any, action_result: Any, *args: Any, **kwargs: Any) -> Any:
        seen_by_consciences.append(action_result.action_parameters.name)
        return _passed(action_result)

    monkeypatch.setitem(ThoughtProcessor._VERB_SECOND_PASS, HandlerActionType.TOOL, fake_second_pass)
    processor._perform_aspdma_step = AsyncMock(return_value=_tool("todoist", {"task": "buy milk"}))  # type: ignore[method-assign]
    processor._conscience_execution_step = fake_consciences  # type: ignore[method-assign]
    processor._should_retry_with_conscience_guidance = Mock(return_value=False)  # type: ignore[method-assign]
    processor._get_profile_name = Mock(return_value="default")  # type: ignore[method-assign]
    processor._log_final_action_results = Mock()  # type: ignore[method-assign]

    thought_item = Mock()
    thought_item.thought_id = "th1"
    out = await processor._perform_action_selection_phase(thought_item, Mock(), Mock(), Mock())

    assert seen_by_second_pass == ["skill:todoist-cli"]
    assert seen_by_consciences == ["skill:todoist-cli"]
    stamped = processor._stamp_reviewed_action(out["action_result"], out["conscience_result"])
    assert stamped is not None
    assert stamped.final_action.reviewed_action_hash == reviewed_action_fingerprint(
        _tool("skill:todoist-cli", {"task": "buy milk"})
    )


# --------------------------------------------------------------------------- stamping


def test_stamp_is_set_only_when_the_consciences_passed_the_reviewed_draft() -> None:
    draft = _tool("weather", {"city": "Paris"})
    stamped = ThoughtProcessor._stamp_reviewed_action(draft, _passed(draft))
    assert stamped is not None
    assert stamped.final_action.reviewed_action_hash == reviewed_action_fingerprint(draft)

    # Overridden -> not reviewed as-is.
    over = ThoughtProcessor._stamp_reviewed_action(draft, _passed(draft, overridden=True))
    assert over is not None and over.final_action.reviewed_action_hash is None

    # Final action differs from what the consciences were handed -> no stamp.
    other = _tool("weather", {"city": "Lyon"})
    mismatch = ThoughtProcessor._stamp_reviewed_action(draft, _passed(other))
    assert mismatch is not None and mismatch.final_action.reviewed_action_hash is None


def test_a_stamp_from_any_other_producer_never_survives() -> None:
    draft = _tool("weather", {"city": "Paris"})
    forged = _passed(draft.model_copy(update={"reviewed_action_hash": "sha256:forged"}))
    out = ThoughtProcessor._stamp_reviewed_action(None, forged)
    assert out is not None and out.final_action.reviewed_action_hash is None


# --------------------------------------------------------------------------- dispatch check


@pytest.fixture
def handler_env(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    persistence = Mock()
    persistence.add_thought = Mock()
    persistence.update_thought_status = Mock(return_value=True)
    persistence.get_task_by_id = Mock(return_value=Mock())
    monkeypatch.setattr("ciris_engine.logic.infrastructure.handlers.base_handler.persistence", persistence)
    ctx_model = Mock()
    ctx_model.model_validate = Mock(side_effect=lambda x: Mock())
    monkeypatch.setattr("ciris_engine.schemas.runtime.models.ThoughtContext", ctx_model)

    time_service = Mock()
    time_service.now = Mock(return_value=datetime.now(timezone.utc))
    bus_manager = BusManager(AsyncMock(), time_service=time_service)
    aliases: Dict[str, str] = {}
    tool_bus = Mock()
    tool_bus.resolve_tool_name = lambda n: aliases.get(n, n)
    tool_bus.execute_tool = AsyncMock(
        return_value=ToolExecutionResult(
            tool_name="t",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={"ok": "yes"},
            error=None,
            correlation_id="c",
        )
    )
    bus_manager.tool = tool_bus
    bus_manager.audit_service = AsyncMock()
    secrets = Mock()

    async def decapsulate(action_type: str, action_params: Dict[str, Any], context: Any) -> Dict[str, Any]:
        params = dict(action_params)
        params["parameters"] = {
            k: ("hunter2" if v == "{SECRET:abc:password}" else v) for k, v in params["parameters"].items()
        }
        return params

    secrets.decapsulate_secrets_in_parameters = decapsulate
    deps = ActionHandlerDependencies(bus_manager=bus_manager, time_service=time_service, secrets_service=secrets)
    return {"handler": ToolHandler(deps), "tool_bus": tool_bus, "aliases": aliases, "persistence": persistence}


def _thought() -> Thought:
    now = datetime.now(timezone.utc).isoformat()
    return Thought(
        thought_id="th1",
        source_task_id="task1",
        content="c",
        status=ThoughtStatus.PROCESSING,
        thought_depth=1,
        created_at=now,
        updated_at=now,
        context=ThoughtContext(task_id="task1", round_number=1, depth=1, correlation_id="corr"),
    )


def _dispatch_context() -> DispatchContext:
    return DispatchContext(
        channel_context=ChannelContext(
            channel_id="ch1", channel_name="c", channel_type="text", created_at=datetime.now(timezone.utc)
        ),
        author_id="a",
        author_name="a",
        origin_service="s",
        handler_name="ToolHandler",
        action_type=HandlerActionType.TOOL,
        task_id="task1",
        thought_id="th1",
        source_task_id="task1",
        event_summary="e",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        correlation_id=str(uuid.uuid4()),
    )


def _failed_followup(persistence: Mock) -> bool:
    return any(
        ThoughtStatus.FAILED in call.args or call.kwargs.get("status") == ThoughtStatus.FAILED
        for call in persistence.update_thought_status.call_args_list
    )


@pytest.mark.asyncio
async def test_reviewed_call_executes(handler_env: Dict[str, Any]) -> None:
    action = _stamped(_tool("create_ticket", {"title": "x"}))
    await handler_env["handler"].handle(action, _thought(), _dispatch_context())
    handler_env["tool_bus"].execute_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_refuses_arguments_changed_after_review(handler_env: Dict[str, Any]) -> None:
    reviewed = _stamped(_tool("create_ticket", {"title": "x"}))
    changed = reviewed.model_copy(
        update={"action_parameters": ToolParams(name="create_ticket", parameters={"title": "DROP"}, channel_id="ch1")}
    )
    await handler_env["handler"].handle(changed, _thought(), _dispatch_context())
    handler_env["tool_bus"].execute_tool.assert_not_awaited()
    assert _failed_followup(handler_env["persistence"])


@pytest.mark.asyncio
async def test_v2_21_0_retry_shape_with_empty_parameters_is_refused(handler_env: Dict[str, Any]) -> None:
    """RATCHET Market 4 run 43453725789: a retried TOOL reached dispatch with
    parameters {} after review of a filled-in call. It must not run."""
    reviewed = _stamped(_tool("create_ticket", {"title": "x", "priority": "high"}))
    emptied = reviewed.model_copy(
        update={"action_parameters": ToolParams(name="create_ticket", parameters={}, channel_id="ch1")}
    )
    await handler_env["handler"].handle(emptied, _thought(), _dispatch_context())
    handler_env["tool_bus"].execute_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_unreviewed_tool_call_is_refused(handler_env: Dict[str, Any]) -> None:
    await handler_env["handler"].handle(_tool("create_ticket", {"title": "x"}), _thought(), _dispatch_context())
    handler_env["tool_bus"].execute_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_alias_registered_after_review_is_refused(handler_env: Dict[str, Any]) -> None:
    action = _stamped(_tool("todoist", {"task": "x"}))
    handler_env["aliases"]["todoist"] = "skill:other-tool"
    await handler_env["handler"].handle(action, _thought(), _dispatch_context())
    handler_env["tool_bus"].execute_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_secret_decapsulation_does_not_trip_the_check(handler_env: Dict[str, Any]) -> None:
    """Reviewed over the secret REFERENCE; the value is substituted after the
    check and reaches the tool."""
    action = _stamped(_tool("login", {"user": "bob", "password": "{SECRET:abc:password}"}))
    await handler_env["handler"].handle(action, _thought(), _dispatch_context())
    handler_env["tool_bus"].execute_tool.assert_awaited_once()
    sent = handler_env["tool_bus"].execute_tool.await_args.kwargs["parameters"]
    assert sent["password"] == "hunter2"
    # Engine-added by rule, after the check: not part of the review.
    assert sent["task_id"] == "task1"
    assert sent["channel_id"] == "ch1"


# --------------------------------------------------------------------------- approval binds the call


def _wa_envelope(approved_calls: frozenset) -> TaskEnvelope:
    return issue_authority_envelope(
        task_id="task1",
        issuer_kind=EnvelopeIssuerKind.WISE_AUTHORITY,
        issuer_id="wa-1",
        granted_tools=frozenset({"send_money"}),
        capabilities=frozenset(),
        approved_calls=approved_calls,
    )


def _approval_thought() -> Mock:
    t = Mock()
    t.source_task_id = "task1"
    t.agent_occurrence_id = "default"
    return t


@pytest.mark.asyncio
async def test_approved_tool_with_different_arguments_needs_its_own_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    info = ToolInfo(
        name="send_money",
        description="d",
        parameters=ToolParameterSchema(type="object", properties={}, required=[]),
        dma_guidance=ToolDMAGuidance(requires_approval=True),
    )
    approved = tool_call_fingerprint("send_money", {"amount": 10}, "ch1")
    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.thought_processor.main.resolve_envelope_for_task_id",
        lambda task_id, occ="default": _wa_envelope(frozenset({approved})),
    )
    processor = _processor(info)

    same = await processor._enforce_tool_approval(_approval_thought(), _passed(_tool("send_money", {"amount": 10})))
    assert same is not None and same.final_action.selected_action == HandlerActionType.TOOL

    other = await processor._enforce_tool_approval(_approval_thought(), _passed(_tool("send_money", {"amount": 9999})))
    assert other is not None and other.final_action.selected_action == HandlerActionType.DEFER
    ctx = other.final_action.action_parameters.context or {}
    assert ctx[PENDING_TOOL_CALL_FINGERPRINT_KEY] == tool_call_fingerprint("send_money", {"amount": 9999}, "ch1")


def test_legacy_tool_only_approval_approves_no_call() -> None:
    env = _wa_envelope(frozenset())
    assert env.permits_tool("send_money")
    assert envelope_approves_call(env, "send_money", tool_call_fingerprint("send_money", {"amount": 10})) is False


def test_wa_resolution_binds_the_envelope_to_the_call_shown() -> None:
    from ciris_engine.logic.services.governance.wise_authority.service import WiseAuthorityService

    fp = tool_call_fingerprint("send_money", {"amount": 10})
    service = Mock(spec=WiseAuthorityService)
    service._time_service = None
    ctx: Dict[str, Any] = {}
    WiseAuthorityService._attach_tool_approval_envelope(
        service,
        guidance_context_dict=ctx,
        deferral_info={
            "context": {
                PENDING_TOOL_APPROVAL_KEY: "send_money",
                TOOL_APPROVAL_DETAIL_KEY: encode_tool_approval_detail(None, "send_money", {"amount": 10}),
                PENDING_TOOL_CALL_FINGERPRINT_KEY: fp,
            }
        },
        guidance_task_id="g1",
        agent_occurrence_id="default",
        wa_id="wa-1",
    )
    env = TaskEnvelope.model_validate(ctx["envelope"])
    assert env.approved_calls == frozenset({fp})
    assert envelope_approves_call(env, "send_money", fp)
    assert not envelope_approves_call(env, "send_money", tool_call_fingerprint("send_money", {"amount": 11}))


# --------------------------------------------------------------------------- wiring


def _calls_in(function_name: str) -> set:
    """Names called inside ``function_name`` in thought_processor/main.py."""
    import ast
    import pathlib

    import ciris_engine.logic.processors.core.thought_processor.main as main_module

    tree = ast.parse(pathlib.Path(main_module.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            called = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    target = sub.func
                    if isinstance(target, ast.Attribute):
                        called.add(target.attr)
                    elif isinstance(target, ast.Name):
                        called.add(target.id)
            return called
    raise AssertionError(f"{function_name} not found in thought_processor/main.py")


def test_stamp_and_alias_resolution_are_wired() -> None:
    """Behavioural tests cannot tell a correct helper from an unreached one.

    Every finalized action passes _execute_pipeline_phases; every draft the
    consciences see (first pass and retry) passes _run_verb_second_pass.
    """
    assert "_stamp_reviewed_action" in _calls_in("_execute_pipeline_phases")
    assert "_resolve_tool_alias" in _calls_in("_run_verb_second_pass")
