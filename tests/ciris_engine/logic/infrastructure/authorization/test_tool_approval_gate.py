"""The ``requires_approval`` gate is a real control (CIRISAgent#942).

This repo has shipped declared-but-uncalled controls before — ``requires_approval``
itself was one for its whole life, read only by a prompt renderer and a consent
label. So these tests are written to fail in the two distinct ways that matter:

* **Behavioural** — ``_enforce_tool_approval`` must rewrite an unapproved
  approval-requiring tool selection into ``DEFER``.
* **Wiring** — ``_execute_pipeline_phases`` must actually *call* it. A gate that
  is correct and unreachable is the exact failure mode being guarded against, and
  a behavioural test alone cannot see it.

``test_gate_is_wired_into_the_pipeline`` is the one that fails if the gate is
deleted from the pipeline; ``test_unapproved_tool_is_deferred`` is the one that
fails if the gate stops denying.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Optional
from unittest.mock import AsyncMock, Mock

import pytest

import ciris_engine.logic.processors.core.thought_processor.main as _thought_processor_main
from ciris_engine.logic.infrastructure.authorization.envelope_issuer import (
    issue_authority_envelope,
    issue_system_component_envelope,
)
from ciris_engine.logic.infrastructure.authorization.tool_approval import (
    PENDING_TOOL_APPROVAL_KEY,
    build_approval_deferral,
    envelope_approves_tool,
    pending_tool_from_deferral_context,
    tool_requires_approval,
)
from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.schemas.actions.parameters import DeferParams, ToolParams
from ciris_engine.schemas.adapters.tools import ToolDMAGuidance, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.task_envelope import (
    ALL_TOOL_CAPABILITIES,
    DeploymentScope,
    EnvelopeIssuer,
    EnvelopeIssuerKind,
    EnvironmentTier,
    TaskEnvelope,
)
from ciris_engine.schemas.services.deferral_taxonomy import DeferralOperationalReason

# Resolve from the imported module rather than by counting `parents[...]` — a
# relocated test file must not silently turn this into a no-op.
MAIN_PY = pathlib.Path(_thought_processor_main.__file__).resolve()

APPROVAL_TOOL = "send_money"
OTHER_APPROVAL_TOOL = "shell_command"
PLAIN_TOOL = "weather"


# --------------------------------------------------------------------------- helpers


def _tool_info(name: str, *, guidance: Optional[ToolDMAGuidance]) -> ToolInfo:
    return ToolInfo(
        name=name,
        description=f"{name} test tool",
        parameters=ToolParameterSchema(type="object", properties={}, required=[]),
        dma_guidance=guidance,
    )


def _deployment_envelope(task_id: str, granted: frozenset) -> TaskEnvelope:
    """A deployment-resolved envelope that *does* enumerate the tool by name.

    This is the real shape: ``issue_deployment_envelope`` grants every tool the
    deployment enabled, ``send_money`` included. If the gate keyed on
    ``permits_tool`` alone it would pass here and never fire — which is why the
    gate keys on the issuer kind as well.
    """
    return TaskEnvelope(
        envelope_id="env_deployment",
        task_id=task_id,
        issued_at="2026-08-01T00:00:00+00:00",
        issuer=EnvelopeIssuer(kind=EnvelopeIssuerKind.DEPLOYMENT_RESOLVED),
        deployment=DeploymentScope(environment_tier=EnvironmentTier.PRODUCTION, agent_id="datum", template="datum"),
        granted_tools=granted,
        capabilities=ALL_TOOL_CAPABILITIES,
    )


def _wa_envelope(task_id: str, tool: str) -> TaskEnvelope:
    return issue_authority_envelope(
        task_id=task_id,
        issuer_kind=EnvelopeIssuerKind.WISE_AUTHORITY,
        issuer_id="wa-2026-08-01-ABC123",
        granted_tools=frozenset({tool}),
        capabilities=frozenset(),
    )


def _processor(tool_info: Optional[ToolInfo]) -> ThoughtProcessor:
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


def _thought(task_id: str = "task_1") -> Mock:
    thought = Mock()
    thought.source_task_id = task_id
    thought.agent_occurrence_id = "default"
    return thought


def _tool_selection(tool: str) -> ConscienceApplicationResult:
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(name=tool, parameters={"amount": 100}),
        rationale=f"use {tool}",
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


# --------------------------------------------------------------------------- predicates


def test_tool_requires_approval_reads_dma_guidance() -> None:
    assert tool_requires_approval(_tool_info(APPROVAL_TOOL, guidance=ToolDMAGuidance(requires_approval=True)))
    assert not tool_requires_approval(_tool_info(PLAIN_TOOL, guidance=ToolDMAGuidance(requires_approval=False)))
    assert not tool_requires_approval(_tool_info("discord_ban_user", guidance=None))
    assert not tool_requires_approval(None)


def test_deployment_envelope_never_approves_even_when_it_grants_the_tool() -> None:
    """The load-bearing distinction: enumerated != approved.

    ``issue_deployment_envelope`` deliberately includes consequential tools. If
    that counted as approval, the gate could never fire.
    """
    env = _deployment_envelope("task_1", frozenset({APPROVAL_TOOL, PLAIN_TOOL}))
    assert env.permits_tool(APPROVAL_TOOL) is True
    assert envelope_approves_tool(env, APPROVAL_TOOL) is False


def test_wa_envelope_approves_only_the_named_tool() -> None:
    env = _wa_envelope("task_1", APPROVAL_TOOL)
    assert envelope_approves_tool(env, APPROVAL_TOOL) is True
    assert envelope_approves_tool(env, OTHER_APPROVAL_TOOL) is False


def test_absent_envelope_is_denial() -> None:
    assert envelope_approves_tool(None, APPROVAL_TOOL) is False


def test_system_component_envelope_is_not_an_approval() -> None:
    """A code-minted component grant is not a human saying yes."""
    env = issue_system_component_envelope(
        component="dsar_orchestrator",
        work_unit_id="dsar_1",
        granted_tools=frozenset({APPROVAL_TOOL}),
        capabilities=frozenset(),
    )
    assert envelope_approves_tool(env, APPROVAL_TOOL) is False


# --------------------------------------------------------------------------- the gate


@pytest.mark.asyncio
async def test_unapproved_tool_is_deferred(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control itself. Remove the gate body and this fails."""
    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.thought_processor.main.resolve_envelope_for_task_id",
        lambda task_id, occ="default": _deployment_envelope(task_id, frozenset({APPROVAL_TOOL})),
    )
    processor = _processor(_tool_info(APPROVAL_TOOL, guidance=ToolDMAGuidance(requires_approval=True)))

    result = await processor._enforce_tool_approval(_thought(), _tool_selection(APPROVAL_TOOL))

    assert result is not None
    assert result.final_action.selected_action == HandlerActionType.DEFER
    assert result.overridden is True
    params = result.final_action.action_parameters
    assert isinstance(params, DeferParams)
    assert params.reason_code == DeferralOperationalReason.CONSENT_OR_AUTHORITY_REQUIRED
    assert (params.context or {})[PENDING_TOOL_APPROVAL_KEY] == APPROVAL_TOOL
    # The pre-gate selection is preserved for the audit trail.
    assert result.original_action.selected_action == HandlerActionType.TOOL


@pytest.mark.asyncio
async def test_wa_approved_tool_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half: approval must actually unblock, or the feature is a brick."""
    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.thought_processor.main.resolve_envelope_for_task_id",
        lambda task_id, occ="default": _wa_envelope(task_id, APPROVAL_TOOL),
    )
    processor = _processor(_tool_info(APPROVAL_TOOL, guidance=ToolDMAGuidance(requires_approval=True)))

    result = await processor._enforce_tool_approval(_thought(), _tool_selection(APPROVAL_TOOL))

    assert result is not None
    assert result.final_action.selected_action == HandlerActionType.TOOL


@pytest.mark.asyncio
async def test_approval_for_one_tool_does_not_approve_another(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.thought_processor.main.resolve_envelope_for_task_id",
        lambda task_id, occ="default": _wa_envelope(task_id, APPROVAL_TOOL),
    )
    processor = _processor(_tool_info(OTHER_APPROVAL_TOOL, guidance=ToolDMAGuidance(requires_approval=True)))

    result = await processor._enforce_tool_approval(_thought(), _tool_selection(OTHER_APPROVAL_TOOL))

    assert result is not None
    assert result.final_action.selected_action == HandlerActionType.DEFER


@pytest.mark.asyncio
async def test_ordinary_tool_is_untouched_even_with_no_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """#942 is not #938 Phase 2. Tools that do not require approval never consult
    the envelope, so a task with no envelope at all still runs them."""
    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.thought_processor.main.resolve_envelope_for_task_id",
        lambda task_id, occ="default": None,
    )
    processor = _processor(_tool_info(PLAIN_TOOL, guidance=ToolDMAGuidance(requires_approval=False)))

    result = await processor._enforce_tool_approval(_thought(), _tool_selection(PLAIN_TOOL))

    assert result is not None
    assert result.final_action.selected_action == HandlerActionType.TOOL


@pytest.mark.asyncio
async def test_moderation_tools_are_not_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standing ruling on ``ToolCapability.MODERATE_CHANNEL``: kick/ban declare no
    ``dma_guidance`` and their control is the conscience layer judging the specific
    content. Gating them on a static envelope would let a bad actor run amok."""
    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.thought_processor.main.resolve_envelope_for_task_id",
        lambda task_id, occ="default": None,
    )
    processor = _processor(_tool_info("discord_ban_user", guidance=None))

    result = await processor._enforce_tool_approval(_thought(), _tool_selection("discord_ban_user"))

    assert result is not None
    assert result.final_action.selected_action == HandlerActionType.TOOL


@pytest.mark.asyncio
async def test_non_tool_actions_pass_through() -> None:
    processor = _processor(None)
    speak = ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=DeferParams(reason="n/a"),
        rationale="speak",
    )
    conscience = ConscienceApplicationResult(
        original_action=speak,
        final_action=speak,
        overridden=False,
        override_reason=None,
        epistemic_data=EpistemicData(
            entropy_level=0.1,
            coherence_level=0.9,
            uncertainty_acknowledged=True,
            reasoning_transparency=1.0,
        ),
    )
    assert await processor._enforce_tool_approval(_thought(), conscience) is conscience
    assert await processor._enforce_tool_approval(_thought(), None) is None


# --------------------------------------------------------------------------- wiring


def _called_functions(func: ast.AST) -> set:
    names = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute):
                names.add(target.attr)
            elif isinstance(target, ast.Name):
                names.add(target.id)
    return names


def test_gate_is_wired_into_the_pipeline() -> None:
    """The gate must be REACHED, not merely defined.

    ``requires_approval`` spent its entire life as a correct-looking declaration
    with no enforcing caller. A behavioural test on ``_enforce_tool_approval``
    cannot distinguish "wired" from "dead code", so assert the call site directly:
    ``_execute_pipeline_phases`` — the one funnel every finalized action passes
    through — must call it.
    """
    tree = ast.parse(MAIN_PY.read_text())
    targets = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_execute_pipeline_phases"
    ]
    assert targets, "_execute_pipeline_phases not found in thought_processor/main.py"
    called = _called_functions(targets[0])
    assert "_enforce_tool_approval" in called, (
        "The #942 approval gate is no longer called from _execute_pipeline_phases. "
        "requires_approval is back to being a label with no enforcement."
    )
    # It must run before finalization, or the unapproved action is already final.
    assert "_finalize_action_step" in called


# --------------------------------------------------------------------------- handoff


def test_deferral_carries_the_tool_name_to_the_wa_and_back() -> None:
    """Both ends of the long string-map route agree on the key."""
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(name=APPROVAL_TOOL, parameters={}),
        rationale="pay the invoice",
    )
    defer = build_approval_deferral(tool_name=APPROVAL_TOOL, original_action=action)
    params = defer.action_parameters
    assert isinstance(params, DeferParams)

    # Hop 1: DeferHandler flattens DeferParams.context into Dict[str, str].
    from ciris_engine.logic.handlers.control.defer_handler import DeferHandler

    metadata: dict = {}
    # Real handler instance (no __init__ — the method is pure), so the real
    # _stringify_metadata_value runs rather than a Mock returning a Mock.
    handler = DeferHandler.__new__(DeferHandler)
    DeferHandler._add_context_metadata(handler, metadata, params.context)
    assert metadata[PENDING_TOOL_APPROVAL_KEY] == APPROVAL_TOOL

    # Hop 2: that map is what lands in context["deferral"]["context"], which is
    # what resolve_deferral reads.
    assert pending_tool_from_deferral_context(metadata) == APPROVAL_TOOL


def test_deferral_shows_the_human_what_they_are_approving() -> None:
    """The big ask: an approval must describe the tool, not just name it.

    A deferral that says only "approve this" asks a human to approve a sentence.
    The detail blob carries the tool's description, the capability flags the
    consent wizard already renders, and the arguments the agent intends to pass.
    """
    import json

    from ciris_engine.logic.infrastructure.authorization.tool_approval import TOOL_APPROVAL_DETAIL_KEY
    from ciris_engine.schemas.adapters.tools import ToolCapabilityFlag

    tool = ToolInfo(
        name=OTHER_APPROVAL_TOOL,
        description="Run a shell command on this device",
        parameters=ToolParameterSchema(type="object", properties={"command": {"type": "string"}}, required=["command"]),
        dma_guidance=ToolDMAGuidance(requires_approval=True),
    )
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(name=OTHER_APPROVAL_TOOL, parameters={"command": "rm -rf /tmp/x"}),
        rationale="clean up",
    )
    defer = build_approval_deferral(
        tool_name=OTHER_APPROVAL_TOOL,
        original_action=action,
        tool_info=tool,
        intended_parameters={"command": "rm -rf /tmp/x"},
    )
    params = defer.action_parameters
    assert isinstance(params, DeferParams)
    detail = json.loads((params.context or {})[TOOL_APPROVAL_DETAIL_KEY])

    assert detail["name"] == OTHER_APPROVAL_TOOL
    assert detail["tool"]["description"] == "Run a shell command on this device"
    flags = detail["tool"]["capability_flags"]
    # Derived structurally by tool_disclosure, same as the consent wizard.
    assert ToolCapabilityFlag.REQUIRES_APPROVAL.value in flags
    assert ToolCapabilityFlag.SHELL_EXECUTION.value in flags
    # The arguments the agent intends to pass — the thing a consent disclosure
    # cannot show and an approval must.
    assert detail["parameters"]["command"] == "rm -rf /tmp/x"


def test_detail_survives_the_ui_context_truncation() -> None:
    """``_build_ui_context`` clips context values to 200 chars. The detail blob is
    JSON and would become unparseable; it must be exempted."""
    import json

    from ciris_engine.logic.infrastructure.authorization.tool_approval import (
        TOOL_APPROVAL_DETAIL_KEY,
        encode_tool_approval_detail,
    )
    from ciris_engine.logic.services.governance.wise_authority.service import WiseAuthorityService

    tool = ToolInfo(
        name=OTHER_APPROVAL_TOOL,
        description="X" * 400,
        parameters=ToolParameterSchema(type="object", properties={"command": {"type": "string"}}, required=["command"]),
        dma_guidance=ToolDMAGuidance(requires_approval=True),
    )
    encoded = encode_tool_approval_detail(tool, OTHER_APPROVAL_TOOL, {"command": "echo hi"})
    assert len(encoded) > 200, "test is vacuous unless the blob exceeds the generic UI clip"

    ui = WiseAuthorityService._build_ui_context(
        Mock(spec=WiseAuthorityService),
        "a task",
        {"context": {TOOL_APPROVAL_DETAIL_KEY: encoded, "other": "y" * 400}},
    )
    # Parses -> the approval screen can render structure, not a truncated string.
    assert json.loads(ui[TOOL_APPROVAL_DETAIL_KEY])["name"] == OTHER_APPROVAL_TOOL
    # Everything else keeps the existing 200-char UI budget.
    assert len(ui["other"]) == 200


def test_oversized_arguments_are_dropped_not_truncated_into_invalid_json() -> None:
    import json

    from ciris_engine.logic.infrastructure.authorization.tool_approval import (
        TOOL_APPROVAL_DETAIL_MAX_CHARS,
        encode_tool_approval_detail,
    )

    tool = ToolInfo(
        name=APPROVAL_TOOL,
        description="pay",
        parameters=ToolParameterSchema(type="object", properties={}, required=[]),
        dma_guidance=ToolDMAGuidance(requires_approval=True),
    )
    huge = {f"arg{i}": "z" * 300 for i in range(100)}
    encoded = encode_tool_approval_detail(tool, APPROVAL_TOOL, huge)
    assert len(encoded) <= TOOL_APPROVAL_DETAIL_MAX_CHARS
    payload = json.loads(encoded)  # must still be valid JSON
    assert payload["parameters_omitted"] == "true"
    assert payload["name"] == APPROVAL_TOOL


def test_pending_tool_extraction_fails_closed() -> None:
    assert pending_tool_from_deferral_context(None) is None
    assert pending_tool_from_deferral_context({}) is None
    assert pending_tool_from_deferral_context({PENDING_TOOL_APPROVAL_KEY: "  "}) is None
    assert pending_tool_from_deferral_context("not a map") is None


def test_wa_service_issues_a_narrow_approval_envelope() -> None:
    """``resolve_deferral``'s helper mints an envelope the gate will accept, and
    persists it in the shape ``_persist_row_to_task`` decodes."""
    from ciris_engine.logic.services.governance.wise_authority.service import WiseAuthorityService

    service = Mock(spec=WiseAuthorityService)
    service._time_service = None
    ctx: dict = {}
    WiseAuthorityService._attach_tool_approval_envelope(
        service,
        guidance_context_dict=ctx,
        deferral_info={"context": {PENDING_TOOL_APPROVAL_KEY: APPROVAL_TOOL}},
        guidance_task_id="guidance_task_1",
        agent_occurrence_id="default",
        wa_id="wa-2026-08-01-ABC123",
    )

    assert "envelope" in ctx, "no approval envelope was bound to the guidance task"
    decoded = TaskEnvelope.model_validate(ctx["envelope"])
    assert decoded.task_id == "guidance_task_1"
    assert decoded.issuer.kind is EnvelopeIssuerKind.WISE_AUTHORITY
    assert decoded.issuer.issuer_id == "wa-2026-08-01-ABC123"
    # Narrow: approving one tool must not approve the rest of the deployment.
    assert decoded.granted_tools == frozenset({APPROVAL_TOOL})
    assert envelope_approves_tool(decoded, APPROVAL_TOOL) is True
    assert envelope_approves_tool(decoded, OTHER_APPROVAL_TOOL) is False


def test_no_envelope_issued_when_the_deferral_was_not_an_approval_request() -> None:
    """An ordinary ethical deferral must not hand out a tool grant."""
    from ciris_engine.logic.services.governance.wise_authority.service import WiseAuthorityService

    service = Mock(spec=WiseAuthorityService)
    service._time_service = None
    for deferral_info in (None, {}, {"context": {}}, {"context": {"something_else": "x"}}):
        ctx: dict = {}
        WiseAuthorityService._attach_tool_approval_envelope(
            service,
            guidance_context_dict=ctx,
            deferral_info=deferral_info,
            guidance_task_id="guidance_task_1",
            agent_occurrence_id="default",
            wa_id="wa-2026-08-01-ABC123",
        )
        assert ctx == {}, f"unexpected grant issued for deferral_info={deferral_info!r}"
