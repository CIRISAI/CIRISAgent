"""The Phase 2 tool gate at ToolBus.dispatch_to_provider, ENFORCING (CIRISAgent#1366 item 19).

Each test names the rule it pins. The gate's inputs are the subject (set by
CIRIS code), the envelope, the tool name the bus is running, the dispatch
arguments, and the admitted reviewed-action record; nothing model-authored.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from ciris_engine.logic.buses.tool_bus import ToolBus
from ciris_engine.logic.conscience.veto_contract import (
    action_equivalence_key,
    action_fingerprint,
    banned_entry_for,
)
from ciris_engine.logic.infrastructure.authorization import dispatch_gate
from ciris_engine.logic.infrastructure.authorization.dispatch_gate import (
    register_principal_restriction_source,
    reset_principal_restriction_sources,
)
from ciris_engine.logic.infrastructure.authorization.enabled_tools import reset_enabled_tools_cache
from ciris_engine.logic.infrastructure.authorization.reviewed_action import (
    admit_reviewed_action,
    cde_encode,
    make_review_entry,
    passed_entry_for,
    reset_admitted_records,
    review_record_digest,
    reviewed_action_fingerprint,
    reviewed_call_fingerprint,
)
from ciris_engine.schemas.actions.parameters import ToolParams
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ServiceType
from ciris_engine.schemas.runtime.reviewed_action_admission import (
    CONNECTOR_SETUP_COMPONENT,
    DSAR_COMPONENT,
    ENRICHMENT_CACHE_COMPONENT,
    REQUIRED_REVIEW_CONSCIENCES,
    SYSTEM_CALLERS,
    GateRefusalReason,
    ReviewDischarge,
    ReviewEntry,
    ReviewOutcome,
    ReviewRecord,
    ReviewedCall,
    ToolPrincipalRestriction,
)
from ciris_engine.schemas.runtime.task_envelope import (
    ALL_TOOL_CAPABILITIES,
    DeploymentScope,
    EnvelopeIssuer,
    EnvelopeIssuerKind,
    EnvironmentTier,
    RequesterAuthorization,
    TaskEnvelope,
    ToolCallOrigin,
    ToolInvocationSubject,
)
from ciris_engine.schemas.runtime.veto_record import ObjectionType, VetoRecordEntry

TASK = "task-1"
THOUGHT = "thought-1"
ALL_PASSES = tuple(sorted(REQUIRED_REVIEW_CONSCIENCES))


class _Info:
    def __init__(self, name: str, enrichment: bool) -> None:
        self.name = name
        self.context_enrichment = enrichment


class FakeToolService:
    def __init__(self, names: List[str], enrichment: Optional[List[str]] = None) -> None:
        self.names = names
        self.enrichment = set(enrichment or [])
        self.calls: List[tuple] = []

    async def get_available_tools(self) -> List[str]:
        return list(self.names)

    async def get_all_tool_info(self) -> List[_Info]:
        return [_Info(n, n in self.enrichment) for n in self.names]

    async def get_tool_info(self, tool_name: str) -> Optional[_Info]:
        return _Info(tool_name, tool_name in self.enrichment) if tool_name in self.names else None

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolExecutionResult:
        self.calls.append((tool_name, dict(parameters)))
        return ToolExecutionResult(
            tool_name=tool_name, status=ToolExecutionStatus.COMPLETED, success=True, data={}, error=None, correlation_id="c"
        )


class _Provider:
    def __init__(self, instance: Any) -> None:
        self.instance = instance


class _Registry:
    def __init__(self, service: Any) -> None:
        self._services = {ServiceType.TOOL: [_Provider(service)]}


class _Time:
    def now(self) -> datetime.datetime:
        return datetime.datetime(2026, 11, 18, tzinfo=datetime.timezone.utc)


@pytest.fixture(autouse=True)
def _clean() -> Any:
    reset_enabled_tools_cache()
    reset_admitted_records()
    reset_principal_restriction_sources()
    yield
    reset_enabled_tools_cache()
    reset_admitted_records()
    reset_principal_restriction_sources()


@pytest.fixture
def service() -> FakeToolService:
    return FakeToolService(["file_ticket", "weather", "ha_list_entities", "sql_query"], enrichment=["ha_list_entities"])


@pytest.fixture
def bus(service: FakeToolService) -> ToolBus:
    return ToolBus(_Registry(service), _Time())  # type: ignore[arg-type]


def _envelope(
    tools: List[str],
    *,
    task_id: str = TASK,
    kind: EnvelopeIssuerKind = EnvelopeIssuerKind.DEPLOYMENT_RESOLVED,
    issuer_id: Optional[str] = None,
    user_id: Optional[str] = "user-1",
    role: UserRole = UserRole.OBSERVER,
) -> TaskEnvelope:
    return TaskEnvelope(
        envelope_id=f"env-{task_id}",
        task_id=task_id,
        issued_at="2026-11-18T00:00:00Z",
        issuer=EnvelopeIssuer(kind=kind, issuer_id=issuer_id),
        deployment=DeploymentScope(environment_tier=EnvironmentTier.QA, agent_id="ally", template="ally"),
        requester=RequesterAuthorization(user_id=user_id, role=role),
        granted_tools=frozenset(tools),
        capabilities=ALL_TOOL_CAPABILITIES,
    )


def _tool_action(name: str, args: Dict[str, Any], channel: Optional[str] = "ch-1") -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(name=name, parameters=args, channel_id=channel),
        rationale="r",
    )


def _reviewed(name: str, args: Dict[str, Any], channel: Optional[str] = "ch-1") -> ReviewedCall:
    return ReviewedCall(
        fingerprint=reviewed_call_fingerprint(name, args, channel), tool_name=name, arguments=args, channel_id=channel
    )


DERIVED = ("request:sha256:00",)


def _passed(
    name: str,
    args: Dict[str, Any],
    passes: tuple = ALL_PASSES,
    channel: Optional[str] = "ch-1",
    discharges: tuple = (),
    derived_from: tuple = DERIVED,
) -> ReviewEntry:
    return make_review_entry(
        ReviewRecord(
            fingerprint=reviewed_call_fingerprint(name, args, channel),
            thought=THOUGHT,
            outcome=ReviewOutcome.PASSED,
            faculties=passes,
            discharges=discharges,
        ),
        task_id=TASK,
        derived_from=derived_from,
    )


def _admit(name: str, args: Dict[str, Any], passes: tuple = ALL_PASSES, channel: Optional[str] = "ch-1", **kw: Any) -> Optional[ReviewEntry]:
    return admit_reviewed_action(_passed(name, args, passes, channel, **kw))


def _object(name: str, args: Dict[str, Any], kind: ObjectionType, channel: Optional[str] = "ch-1") -> ReviewEntry:
    entry = admit_reviewed_action(
        make_review_entry(
            ReviewRecord(
                fingerprint=reviewed_call_fingerprint(name, args, channel),
                thought=THOUGHT,
                outcome=ReviewOutcome.OBJECTED,
                faculties=("coherence",),
            ),
            task_id=TASK,
            objection_types=[kind],
        )
    )
    assert entry is not None
    return entry


def _reasoning(envelope: Optional[TaskEnvelope], call: Optional[ReviewedCall]) -> ToolInvocationSubject:
    return ToolInvocationSubject.for_task(
        task_id=TASK, thought_id=THOUGHT, handler_name="ToolHandler", envelope=envelope, reviewed_call=call
    )


def _dispatch_args(args: Dict[str, Any], channel: Optional[str] = "ch-1") -> Dict[str, Any]:
    """What ToolHandler._build_tool_params sends: reviewed args + channel_id + task_id."""
    out = dict(args)
    if channel:
        out["channel_id"] = channel
    out["task_id"] = TASK
    return out


async def _run(bus: ToolBus, service: FakeToolService, tool: str, args: Dict[str, Any], subject: Any) -> ToolExecutionResult:
    return await bus.dispatch_to_provider(service, tool, args, handler_name="ToolHandler", subject=subject)


def _reason(result: ToolExecutionResult) -> str:
    return (result.error or "").split(":", 1)[0]


ARGS = {"title": "Lobby door is slow", "body": "It opens too slowly."}


# --------------------------------------------------------------------------- allow path


@pytest.mark.asyncio
async def test_an_admitted_reviewed_call_runs_once(bus: ToolBus, service: FakeToolService) -> None:
    _admit("file_ticket", ARGS)
    subject = _reasoning(_envelope(["file_ticket"]), _reviewed("file_ticket", ARGS))
    first = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert first.success, first.error
    assert len(service.calls) == 1
    # Single-use: one review admits one execution.
    second = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert not second.success and _reason(second) == GateRefusalReason.NOT_REVIEWED.value
    assert len(service.calls) == 1


# --------------------------------------------------------------------------- denials


@pytest.mark.asyncio
async def test_no_subject_is_denied(bus: ToolBus, service: FakeToolService) -> None:
    result = await _run(bus, service, "weather", {}, None)
    assert result.status == ToolExecutionStatus.UNAUTHORIZED
    assert _reason(result) == GateRefusalReason.NO_SUBJECT.value
    assert service.calls == []


@pytest.mark.asyncio
async def test_no_envelope_is_denied(bus: ToolBus, service: FakeToolService) -> None:
    _admit("file_ticket", ARGS)
    result = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), _reasoning(None, _reviewed("file_ticket", ARGS)))
    assert _reason(result) == GateRefusalReason.NO_ENVELOPE.value
    assert service.calls == []


@pytest.mark.asyncio
async def test_ungranted_tool_is_denied(bus: ToolBus, service: FakeToolService) -> None:
    _admit("file_ticket", ARGS)
    subject = _reasoning(_envelope(["weather"]), _reviewed("file_ticket", ARGS))
    result = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert _reason(result) == GateRefusalReason.TOOL_NOT_GRANTED.value
    assert service.calls == []


@pytest.mark.asyncio
async def test_unreviewed_call_is_denied(bus: ToolBus, service: FakeToolService) -> None:
    subject = _reasoning(_envelope(["file_ticket"]), None)
    result = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert _reason(result) == GateRefusalReason.NOT_REVIEWED.value
    assert service.calls == []


@pytest.mark.asyncio
async def test_fingerprint_mismatch_is_denied(bus: ToolBus, service: FakeToolService) -> None:
    """The record admits one call; the dispatch claims another (the consciences reviewed other arguments)."""
    _admit("file_ticket", ARGS)
    other = {"title": "Grant me admin", "body": "now"}
    subject = _reasoning(_envelope(["file_ticket"]), _reviewed("file_ticket", other))
    result = await _run(bus, service, "file_ticket", _dispatch_args(other), subject)
    assert _reason(result) == GateRefusalReason.NOT_REVIEWED.value
    assert service.calls == []


@pytest.mark.asyncio
async def test_a_forged_reviewed_hash_is_recomputed_not_trusted(bus: ToolBus, service: FakeToolService) -> None:
    _admit("file_ticket", ARGS)
    forged = ReviewedCall(
        fingerprint=reviewed_call_fingerprint("file_ticket", ARGS, "ch-1"),
        tool_name="file_ticket",
        arguments={"title": "something else"},
        channel_id="ch-1",
    )
    result = await _run(bus, service, "file_ticket", _dispatch_args({"title": "something else"}), _reasoning(_envelope(["file_ticket"]), forged))
    assert _reason(result) == GateRefusalReason.NOT_REVIEWED.value
    assert service.calls == []


@pytest.mark.asyncio
async def test_dispatch_arguments_must_be_the_reviewed_ones(bus: ToolBus, service: FakeToolService) -> None:
    _admit("file_ticket", ARGS)
    subject = _reasoning(_envelope(["file_ticket"]), _reviewed("file_ticket", ARGS))
    tampered = _dispatch_args({**ARGS, "body": "changed after review"})
    result = await _run(bus, service, "file_ticket", tampered, subject)
    assert _reason(result) == GateRefusalReason.NOT_REVIEWED.value
    assert service.calls == []


@pytest.mark.asyncio
async def test_a_decapsulated_secret_reference_is_not_a_change(bus: ToolBus, service: FakeToolService) -> None:
    reviewed = {"token": "{SECRET:abc:api key}", "q": "x"}
    _admit("weather", reviewed)
    subject = _reasoning(_envelope(["weather"]), _reviewed("weather", reviewed))
    result = await _run(bus, service, "weather", _dispatch_args({"token": "sk-live-123", "q": "x"}), subject)
    assert result.success, result.error


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", sorted(REQUIRED_REVIEW_CONSCIENCES))
async def test_fewer_than_four_passes_is_not_admitted(bus: ToolBus, service: FakeToolService, missing: str) -> None:
    assert _admit("file_ticket", ARGS, passes=tuple(p for p in ALL_PASSES if p != missing)) is None
    assert passed_entry_for(THOUGHT, reviewed_call_fingerprint("file_ticket", ARGS, "ch-1")) is None
    subject = _reasoning(_envelope(["file_ticket"]), _reviewed("file_ticket", ARGS))
    result = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert _reason(result) == GateRefusalReason.NOT_REVIEWED.value
    assert service.calls == []


@pytest.mark.asyncio
async def test_a_record_with_insufficient_passes_is_refused_at_dispatch(
    bus: ToolBus, service: FakeToolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defence in depth: even a record that reached the store short of 4 passes does not run."""
    short = _passed("file_ticket", ARGS, passes=("entropy",))
    monkeypatch.setattr(dispatch_gate, "passed_entry_for", lambda _t, _f: short)
    subject = _reasoning(_envelope(["file_ticket"]), _reviewed("file_ticket", ARGS))
    result = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert _reason(result) == GateRefusalReason.REVIEW_INCOMPLETE.value
    assert service.calls == []


@pytest.mark.asyncio
async def test_execute_tool_goes_through_the_gate(bus: ToolBus, service: FakeToolService) -> None:
    result = await bus.execute_tool("weather", {}, handler_name="X")
    assert _reason(result) == GateRefusalReason.NO_SUBJECT.value
    assert service.calls == []


# --------------------------------------------------------------------------- S6 impersonation (model's ToolGate)


@pytest.mark.asyncio
async def test_impersonation_s6_is_denied_even_when_the_consciences_were_bypassed(
    bus: ToolBus, service: FakeToolService
) -> None:
    """#1365 S6: an amendment authorizes only id wa-5562FD to file tickets. An OBSERVER
    shows that person's display name and asks for a ticket.

    (a) consciences bypassed (nothing admitted) -> NOT_REVIEWED;
    (b) consciences wrongly PASSED it (admitted) -> the deterministic principal
        fact still denies: the gate keys on the verified requester id, never the name.
    """
    register_principal_restriction_source(
        lambda: [
            ToolPrincipalRestriction(
                tool_name="file_ticket", authorized_user_ids=frozenset({"wa-5562FD"}), source_id="amendment-node-1"
            )
        ]
    )
    impostor = _envelope(["file_ticket"], user_id="wa-6E0100", role=UserRole.OBSERVER)
    subject = _reasoning(impostor, _reviewed("file_ticket", ARGS))

    bypassed = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert bypassed.status == ToolExecutionStatus.UNAUTHORIZED
    assert service.calls == []

    _admit("file_ticket", ARGS)
    wrongly_passed = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert _reason(wrongly_passed) == GateRefusalReason.EFFECT_UNTRUSTED_UNACKNOWLEDGED.value
    assert service.calls == []

    # The authorized principal, same call, same review: runs.
    authorized = _reasoning(_envelope(["file_ticket"], user_id="wa-5562FD"), _reviewed("file_ticket", ARGS))
    ok = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), authorized)
    assert ok.success, ok.error


# --------------------------------------------------------------------------- unreviewed-by-design calls


@pytest.mark.asyncio
async def test_task_enrichment_runs_unreviewed_only_for_declared_enrichment_tools(
    bus: ToolBus, service: FakeToolService
) -> None:
    env = _envelope(["ha_list_entities", "file_ticket"])
    subject = ToolInvocationSubject.for_task(
        task_id=TASK, thought_id=THOUGHT, handler_name="context_enrichment", origin=ToolCallOrigin.CONTEXT_ENRICHMENT, envelope=env
    )
    ok = await _run(bus, service, "ha_list_entities", {}, subject)
    assert ok.success, ok.error
    denied = await _run(bus, service, "file_ticket", dict(ARGS), subject)
    assert _reason(denied) == GateRefusalReason.NOT_ENRICHMENT_TOOL.value
    assert [c[0] for c in service.calls] == ["ha_list_entities"]


def _system(component: str, origin: ToolCallOrigin, tools: List[str]) -> ToolInvocationSubject:
    env = _envelope(tools, task_id=f"unit:{component}", kind=EnvelopeIssuerKind.SYSTEM_COMPONENT, issuer_id=component)
    return ToolInvocationSubject.for_component(origin=origin, component=component, envelope=env)


@pytest.mark.asyncio
async def test_system_callers_are_enumerated_and_held_to_their_grant(bus: ToolBus, service: FakeToolService) -> None:
    assert set(SYSTEM_CALLERS) == {DSAR_COMPONENT, CONNECTOR_SETUP_COMPONENT, ENRICHMENT_CACHE_COMPONENT}

    conn = _system(CONNECTOR_SETUP_COMPONENT, ToolCallOrigin.ADAPTER_LIFECYCLE, ["sql_query", "file_ticket"])
    assert (await _run(bus, service, "sql_query", {}, conn)).success
    # Its envelope names file_ticket, but the declaration does not: denied.
    assert _reason(await _run(bus, service, "file_ticket", {}, conn)) == GateRefusalReason.TOOL_NOT_GRANTED.value

    cache = _system(ENRICHMENT_CACHE_COMPONENT, ToolCallOrigin.SYSTEM_ENRICHMENT, ["ha_list_entities", "weather"])
    assert (await _run(bus, service, "ha_list_entities", {}, cache)).success
    assert _reason(await _run(bus, service, "weather", {}, cache)) == GateRefusalReason.NOT_ENRICHMENT_TOOL.value


@pytest.mark.asyncio
async def test_an_undeclared_or_mis_origined_system_caller_is_denied(bus: ToolBus, service: FakeToolService) -> None:
    rogue = _system("some.other.component", ToolCallOrigin.OPERATOR_API, ["weather"])
    assert _reason(await _run(bus, service, "weather", {}, rogue)) == GateRefusalReason.SYSTEM_CALLER_UNDECLARED.value
    wrong_origin = _system(DSAR_COMPONENT, ToolCallOrigin.ADAPTER_LIFECYCLE, ["sql_query"])
    assert _reason(await _run(bus, service, "sql_query", {}, wrong_origin)) == GateRefusalReason.SYSTEM_CALLER_UNDECLARED.value
    assert service.calls == []


def test_a_system_subject_cannot_borrow_a_task_envelope() -> None:
    with pytest.raises(ValueError):
        ToolInvocationSubject.for_component(
            origin=ToolCallOrigin.SYSTEM_ENRICHMENT, component=ENRICHMENT_CACHE_COMPONENT, envelope=_envelope(["weather"])
        )
    with pytest.raises(ValueError):
        ToolInvocationSubject(
            origin=ToolCallOrigin.ADAPTER_LIFECYCLE,
            handler_name="x",
            component=CONNECTOR_SETUP_COMPONENT,
            reviewed_call=_reviewed("sql_query", {}),
        )


def test_dsar_and_connector_grants_come_from_the_enumeration() -> None:
    from ciris_engine.logic.adapters.api.routes.connectors import _CONNECTOR_TOOLS
    from ciris_engine.logic.services.governance.dsar.orchestrator import _DSAR_TOOLS

    assert frozenset(_DSAR_TOOLS) == SYSTEM_CALLERS[DSAR_COMPONENT].tools
    assert frozenset(_CONNECTOR_TOOLS) == SYSTEM_CALLERS[CONNECTOR_SETUP_COMPONENT].tools


@pytest.mark.asyncio
async def test_approval_envelope_is_unioned_with_the_deployment_grant(
    bus: ToolBus, service: FakeToolService
) -> None:
    from ciris_engine.logic.infrastructure.authorization.enabled_tools import prime_enabled_tools

    await prime_enabled_tools(service, force=True)  # type: ignore[arg-type]
    wa = _envelope(["file_ticket"], kind=EnvelopeIssuerKind.WISE_AUTHORITY, issuer_id="wa-1")
    _admit("weather", {"q": "x"})
    result = await _run(bus, service, "weather", _dispatch_args({"q": "x"}), _reasoning(wa, _reviewed("weather", {"q": "x"})))
    assert result.success, result.error


# --------------------------------------------------------------------------- bypasses


@pytest.mark.asyncio
async def test_discord_adapter_refuses_a_direct_call_and_runs_through_the_gate() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from ciris_engine.logic.adapters.discord.discord_adapter import DiscordAdapter

    adapter = DiscordAdapter.__new__(DiscordAdapter)
    handler = MagicMock()
    handler.execute_tool = AsyncMock(
        return_value=ToolExecutionResult(
            tool_name="discord_ban_user", status=ToolExecutionStatus.COMPLETED, success=True, data={}, error=None, correlation_id="c"
        )
    )
    adapter._tool_handler = handler
    adapter._commands_handled = 0
    adapter._emit_telemetry = AsyncMock()  # type: ignore[method-assign]

    direct = await adapter.execute_tool("discord_ban_user", {"user_id": "1"})
    assert direct.status == ToolExecutionStatus.UNAUTHORIZED
    assert _reason(direct) == GateRefusalReason.UNGATED_PROVIDER_CALL.value
    handler.execute_tool.assert_not_called()

    bus = ToolBus(_Registry(adapter), _Time())  # type: ignore[arg-type]
    denied = await bus.dispatch_to_provider(adapter, "discord_ban_user", {"user_id": "1"}, subject=None)
    assert _reason(denied) == GateRefusalReason.NO_SUBJECT.value
    handler.execute_tool.assert_not_called()

    args = {"user_id": "1"}
    _admit("discord_ban_user", args)
    subject = _reasoning(_envelope(["discord_ban_user"]), _reviewed("discord_ban_user", args))
    gated = await bus.dispatch_to_provider(adapter, "discord_ban_user", _dispatch_args(args), subject=subject)
    assert gated.success, gated.error
    handler.execute_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_enrichment_without_a_bus_never_invokes_the_provider(service: FakeToolService) -> None:
    from ciris_engine.logic.context.system_snapshot_helpers import _execute_enrichment_tool
    from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema

    tool = ToolInfo(
        name="ha_list_entities",
        description="d",
        parameters=ToolParameterSchema(type="object", properties={}, required=[]),
        context_enrichment=True,
    )
    service.adapter_type = "home_assistant"  # type: ignore[attr-defined]
    key, result = await _execute_enrichment_tool([(service, "home_assistant")], "home_assistant", tool, tool_bus=None)
    assert result is None
    assert service.calls == []


@pytest.mark.asyncio
async def test_cache_warm_enrichment_carries_a_system_subject(bus: ToolBus, service: FakeToolService) -> None:
    from ciris_engine.logic.context.system_snapshot_helpers import enrichment_cache_subject
    from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema

    tools = {
        "home_assistant": [
            ToolInfo(
                name="ha_list_entities",
                description="d",
                parameters=ToolParameterSchema(type="object", properties={}, required=[]),
                context_enrichment=True,
            )
        ]
    }
    subject = enrichment_cache_subject(tools, "test")
    assert subject is not None and not subject.is_task_bound
    assert subject.origin is ToolCallOrigin.SYSTEM_ENRICHMENT and subject.task_id is None
    assert (await _run(bus, service, "ha_list_entities", {}, subject)).success


@pytest.mark.asyncio
async def test_a_write_into_an_adapter_discovery_root_is_denied(
    bus: ToolBus, service: FakeToolService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "adapters"
    root.mkdir()
    monkeypatch.setenv("CIRIS_EXTRA_ADAPTERS", str(root))
    args = {"path": str(root / "evil" / "adapter.py"), "content": "x"}
    _admit("write_file", args)
    subject = _reasoning(_envelope(["write_file"]), _reviewed("write_file", args))
    service.names.append("write_file")
    result = await _run(bus, service, "write_file", _dispatch_args(args), subject)
    assert _reason(result) == GateRefusalReason.ADAPTER_PATH_WRITE.value
    assert service.calls == []


def test_discovery_refuses_a_cwd_root_the_host_tools_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ciris_engine.logic.services.tool import discovery_service as ds

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".ciris" / "adapters").mkdir(parents=True)
    monkeypatch.setattr("ciris_engine.logic.utils.platform_detection.is_desktop", lambda: True)
    assert ds.AdapterDiscoveryService.refuses_agent_writable_root(Path(".ciris") / "adapters")
    assert ds.AdapterDiscoveryService.refuses_agent_writable_root(Path("ciris_adapters"))  # not the package
    monkeypatch.chdir(ds.AdapterDiscoveryService.bundled_roots()[-1].parent)
    assert not ds.AdapterDiscoveryService.refuses_agent_writable_root(Path("ciris_adapters"))  # a source checkout
    monkeypatch.chdir(tmp_path)
    assert not ds.AdapterDiscoveryService.refuses_agent_writable_root(ds.AdapterDiscoveryService.BUNDLED_ROOT)
    service = ds.AdapterDiscoveryService()
    assert all(loader.services_dir != Path(".ciris") / "adapters" for loader in service._loaders)


# --------------------------------------------------------------------------- one fingerprint


def test_the_veto_record_and_dispatch_share_one_fingerprint() -> None:
    action = _tool_action("file_ticket", ARGS)
    assert action_fingerprint(action) == reviewed_action_fingerprint(action)
    assert action_fingerprint(action).startswith("-16:")


def test_the_ban_matches_on_the_equivalence_key_not_the_exact_fingerprint() -> None:
    a = _tool_action("file_ticket", {"title": "T", "body": "b  c"})
    b = _tool_action("file_ticket", {"title": "T", "body": "b c"})
    assert action_fingerprint(a) != action_fingerprint(b)  # dispatch binds exact bytes
    assert action_equivalence_key(a) == action_equivalence_key(b)  # the ban is not evaded by a re-roll
    entry = VetoRecordEntry(
        veto_id="v1",
        action_fingerprint=action_fingerprint(a),
        equivalence_key=action_equivalence_key(a),
        objection_type=ObjectionType.SUBSTANTIVE,
        conscience="coherence",
        banned=True,
    )
    assert banned_entry_for(action_equivalence_key(b), [entry]) is entry


# --------------------------------------------------------------------------- admission at the stamp


def _conscience_result(action: ActionSelectionDMAResult, candidate: Optional[ReviewEntry]) -> Any:
    from ciris_engine.schemas.conscience.core import EpistemicData
    from ciris_engine.schemas.processors.core import ConscienceApplicationResult

    return ConscienceApplicationResult(
        original_action=action,
        final_action=action,
        overridden=False,
        epistemic_data=EpistemicData(uncertainty_acknowledged=True, reasoning_transparency=1.0),
        reviewed_fingerprint=reviewed_action_fingerprint(action),
        review_candidate=candidate,
    )


class _Thought:
    thought_id = THOUGHT
    source_task_id = TASK


def test_the_stamp_admits_only_a_four_of_four_pass_over_the_same_fingerprint() -> None:
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

    action = _tool_action("file_ticket", ARGS)
    fp = reviewed_action_fingerprint(action)
    assert fp is not None
    stamped = ThoughtProcessor._stamp_reviewed_action(action, _conscience_result(action, _passed("file_ticket", ARGS)), thought=_Thought())
    assert stamped is not None and stamped.reviewed_admission is not None
    assert passed_entry_for(THOUGHT, fp) is not None

    reset_admitted_records()
    three = ThoughtProcessor._stamp_reviewed_action(
        action, _conscience_result(action, _passed("file_ticket", ARGS, passes=ALL_PASSES[:3])), thought=_Thought()
    )
    assert three is not None and three.reviewed_admission is None
    assert passed_entry_for(THOUGHT, fp) is None

    other = ThoughtProcessor._stamp_reviewed_action(
        action, _conscience_result(action, _passed("file_ticket", {"title": "other"})), thought=_Thought()
    )
    assert other is not None and other.reviewed_admission is None
    assert passed_entry_for(THOUGHT, fp) is None

    none = ThoughtProcessor._stamp_reviewed_action(action, _conscience_result(action, None), thought=_Thought())
    assert none is not None and none.reviewed_admission is None


# --------------------------------------------------------------------------- objections (constitution 2026-11-18)


@pytest.mark.asyncio
async def test_an_evidence_objection_on_the_same_call_needs_a_person_discharge(
    bus: ToolBus, service: FakeToolService
) -> None:
    objected = _object("file_ticket", ARGS, ObjectionType.EVIDENCE)
    _admit("file_ticket", ARGS)
    subject = _reasoning(_envelope(["file_ticket"]), _reviewed("file_ticket", ARGS))
    result = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert _reason(result) == GateRefusalReason.OBJECTION_UNDISCHARGED.value
    assert service.calls == []

    _admit("file_ticket", ARGS, discharges=(ReviewDischarge(objection=objected.digest, evidence="att-resp-01"),))
    ok = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert ok.success, ok.error


@pytest.mark.asyncio
async def test_a_substantive_objection_on_the_same_call_always_blocks(bus: ToolBus, service: FakeToolService) -> None:
    objected = _object("file_ticket", ARGS, ObjectionType.SUBSTANTIVE)
    _admit("file_ticket", ARGS, discharges=(ReviewDischarge(objection=objected.digest, evidence="att-1"),))
    subject = _reasoning(_envelope(["file_ticket"]), _reviewed("file_ticket", ARGS))
    result = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert _reason(result) == GateRefusalReason.OBJECTION_UNDISCHARGED.value


@pytest.mark.asyncio
async def test_an_objection_binds_its_own_fingerprint(bus: ToolBus, service: FakeToolService) -> None:
    """A changed action is a new action: an objection to an earlier draft does not block it."""
    _object("file_ticket", {"title": "earlier draft"}, ObjectionType.EVIDENCE)
    _admit("file_ticket", ARGS)
    subject = _reasoning(_envelope(["file_ticket"]), _reviewed("file_ticket", ARGS))
    ok = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert ok.success, ok.error


@pytest.mark.asyncio
async def test_an_undeclared_derivation_is_effect_untrusted_unacknowledged(
    bus: ToolBus, service: FakeToolService
) -> None:
    _admit("file_ticket", ARGS, derived_from=())
    subject = _reasoning(_envelope(["file_ticket"]), _reviewed("file_ticket", ARGS))
    result = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), subject)
    assert _reason(result) == GateRefusalReason.EFFECT_UNTRUSTED_UNACKNOWLEDGED.value
    assert service.calls == []


@pytest.mark.asyncio
async def test_a_call_resting_on_an_approval_runs_only_the_approved_fingerprint(
    bus: ToolBus, service: FakeToolService
) -> None:
    approved = reviewed_call_fingerprint("file_ticket", ARGS, "ch-1")
    wa = _envelope(["file_ticket"], kind=EnvelopeIssuerKind.WISE_AUTHORITY, issuer_id="wa-1").model_copy(
        update={"approved_calls": frozenset({approved})}
    )
    other = {**ARGS, "body": "different"}
    _admit("file_ticket", other)
    mismatch = await _run(bus, service, "file_ticket", _dispatch_args(other), _reasoning(wa, _reviewed("file_ticket", other)))
    assert _reason(mismatch) == GateRefusalReason.APPROVAL_MISMATCH.value
    _admit("file_ticket", ARGS)
    ok = await _run(bus, service, "file_ticket", _dispatch_args(ARGS), _reasoning(wa, _reviewed("file_ticket", ARGS)))
    assert ok.success, ok.error


# --------------------------------------------------------------------------- CDE self-check (rc21 §4)


def test_cde_integers_and_integral_numbers() -> None:
    assert cde_encode(1) == bytes.fromhex("01")
    assert cde_encode(1.0) == bytes.fromhex("01")  # integral number -> integer
    assert cde_encode(-25) == bytes.fromhex("3818")
    assert cde_encode(256) == bytes.fromhex("190100")
    assert cde_encode(True) == bytes.fromhex("f5") and cde_encode(None) == bytes.fromhex("f6")


def test_cde_floats_are_the_shortest_that_keep_binary64() -> None:
    assert cde_encode(1.5) == bytes.fromhex("f93e00")  # half
    assert cde_encode(100000.5) == bytes.fromhex("fa47c35040")  # single
    assert cde_encode(0.1) == bytes.fromhex("fb3fb999999999999a")  # double
    with pytest.raises(ValueError):
        cde_encode(float("nan"))


def test_cde_maps_are_in_bytewise_key_order() -> None:
    assert cde_encode({"aa": 2, "c": 0, "b": 1}) == bytes.fromhex("a3616201616300626161" + "02")
    assert cde_encode({"b": 1, "aa": 2, "c": 0}) == cde_encode({"c": 0, "aa": 2, "b": 1})


def test_the_call_fingerprint_is_sha256_over_the_cde_call_array() -> None:
    import hashlib

    expected = hashlib.sha256(
        cde_encode(["CEG-call/2", "tool", "file_ticket", {"n": 1, "t": "x"}, ""])
    ).hexdigest()
    assert reviewed_call_fingerprint("file_ticket", {"t": "x", "n": 1.0}, None) == "-16:" + expected


def test_the_review_record_digest_covers_the_wire_members() -> None:
    record = ReviewRecord(
        fingerprint=reviewed_call_fingerprint("file_ticket", ARGS, "ch-1"),
        thought=THOUGHT,
        outcome=ReviewOutcome.PASSED,
        faculties=ALL_PASSES,
    )
    reordered = record.model_copy(update={"faculties": tuple(reversed(ALL_PASSES))})
    assert review_record_digest(record) == review_record_digest(reordered)  # a set
    assert review_record_digest(record) != review_record_digest(record.model_copy(update={"thought": "t2"}))
