"""Task identity reaches the tool bus (CIRISAgent#938, Phase 1).

Before this change, ``ToolBus.execute_tool(tool_name, parameters)`` took no
task or thought identity: the enforcement point could not see the subject it
would need to authorize, even in principle. These tests assert the subject now
arrives, that an identity-less call is *named* rather than silently accepted,
and that no behaviour changed for existing callers.

**Nothing here asserts a denial.** Phase 1 ships no gate — that is #905 Ask 1.
"""

import logging
from typing import List, Optional

import pytest

from ciris_engine.logic.buses.tool_bus import ToolBus
from ciris_engine.logic.infrastructure.authorization.enabled_tools import (
    cached_enabled_tools,
    prime_enabled_tools,
    reset_enabled_tools_cache,
)
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.task_envelope import (
    ALL_TOOL_CAPABILITIES,
    DeploymentScope,
    EnvelopeIssuer,
    EnvelopeIssuerKind,
    EnvironmentTier,
    TaskEnvelope,
    ToolCallOrigin,
    ToolInvocationSubject,
)


class FakeToolInfo:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeToolService:
    def __init__(self, names: Optional[List[str]] = None) -> None:
        self.names = names or ["weather"]
        self.calls: List[tuple] = []

    async def get_available_tools(self) -> List[str]:
        return list(self.names)

    async def get_all_tool_info(self) -> List[FakeToolInfo]:
        return [FakeToolInfo(n) for n in self.names]

    async def get_tool_info(self, tool_name: str) -> Optional[FakeToolInfo]:
        return FakeToolInfo(tool_name) if tool_name in self.names else None

    async def execute_tool(self, tool_name, parameters) -> ToolExecutionResult:
        self.calls.append((tool_name, parameters))
        return ToolExecutionResult(
            tool_name=tool_name,
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={"ok": True},
            error=None,
            correlation_id="corr-1",
        )


class FakeProvider:
    def __init__(self, instance) -> None:
        self.instance = instance


class FakeRegistry:
    def __init__(self, service) -> None:
        self._services = {ServiceType.TOOL: [FakeProvider(service)]}


class FakeTimeService:
    def now(self):
        import datetime

        return datetime.datetime(2026, 7, 30, tzinfo=datetime.timezone.utc)


@pytest.fixture(autouse=True)
def clean_enabled_tools():
    reset_enabled_tools_cache()
    yield
    reset_enabled_tools_cache()


@pytest.fixture
def bus_and_service():
    service = FakeToolService()
    bus = ToolBus(service_registry=FakeRegistry(service), time_service=FakeTimeService())
    return bus, service


def make_envelope(task_id: str = "task_1") -> TaskEnvelope:
    return TaskEnvelope(
        envelope_id="env_1",
        task_id=task_id,
        issued_at="2026-07-30T00:00:00+00:00",
        issuer=EnvelopeIssuer(kind=EnvelopeIssuerKind.DEPLOYMENT_RESOLVED),
        deployment=DeploymentScope(
            environment_tier=EnvironmentTier.PRODUCTION,
            agent_id="echo",
            template="echo",
            agent_occurrence_id="default",
        ),
        granted_tools=frozenset({"weather"}),
        capabilities=ALL_TOOL_CAPABILITIES,
    )


# ---------------------------------------------------- the subject reaches the bus


async def test_reasoning_subject_is_accepted_and_logged(bus_and_service, caplog):
    bus, service = bus_and_service
    subject = ToolInvocationSubject.for_task(
        task_id="task_1", thought_id="th_1", handler_name="ToolHandler", envelope=make_envelope()
    )
    with caplog.at_level(logging.DEBUG, logger="ciris_engine.logic.buses.tool_bus"):
        result = await bus.execute_tool("weather", {"city": "Austin"}, "ToolHandler", subject=subject)
    assert result.success is True
    assert service.calls == [("weather", {"city": "Austin"})]
    rendered = [rec.getMessage() for rec in caplog.records]
    assert any("task=task_1" in m and "thought=th_1" in m and "envelope=env_1" in m for m in rendered)
    # And no identity-less warning was emitted.
    assert not [rec for rec in caplog.records if rec.levelno >= logging.WARNING]


async def test_component_subject_is_accepted(bus_and_service):
    bus, service = bus_and_service
    subject = ToolInvocationSubject.for_component(
        origin=ToolCallOrigin.GOVERNANCE_SERVICE, component="DSARModificationOrchestrator"
    )
    result = await bus.execute_tool("weather", {}, "default", subject=subject)
    assert result.success is True


# --------------------------------------------- identity-less calls are named


async def test_identityless_call_warns_and_names_the_caller(bus_and_service, caplog):
    bus, _ = bus_and_service
    with caplog.at_level(logging.WARNING, logger="ciris_engine.logic.buses.tool_bus"):
        await bus.execute_tool("weather", {}, "SomeLegacyAdapter")
    warnings = [rec for rec in caplog.records if rec.levelno >= logging.WARNING]
    assert warnings, "an identity-less execute_tool must not be silent"
    rendered = warnings[0].getMessage()
    assert "SomeLegacyAdapter" in rendered
    assert "NO ToolInvocationSubject" in rendered


async def test_identityless_warning_is_once_per_caller_not_per_call(bus_and_service, caplog):
    """A per-call warning on a hot path gets muted, and a muted warning is the
    silent permissive path this work exists to remove."""
    bus, _ = bus_and_service
    with caplog.at_level(logging.WARNING, logger="ciris_engine.logic.buses.tool_bus"):
        for _ in range(5):
            await bus.execute_tool("weather", {}, "SomeLegacyAdapter")
        await bus.execute_tool("weather", {}, "AnotherAdapter")
    warned = [rec.getMessage() for rec in caplog.records if rec.levelno >= logging.WARNING]
    assert sum("SomeLegacyAdapter" in m for m in warned) == 1
    assert sum("AnotherAdapter" in m for m in warned) == 1


async def test_identityless_call_still_executes(bus_and_service):
    """Phase 1 observes; it does not deny. A gate here without the rest of the
    design would break every adapter that has not been updated yet."""
    bus, service = bus_and_service
    result = await bus.execute_tool("weather", {}, "SomeLegacyAdapter")
    assert result.success is True
    assert service.calls


# ----------------------------------------------- backwards compatibility


async def test_positional_call_signature_still_works(bus_and_service):
    bus, _ = bus_and_service
    result = await bus.execute_tool("weather", {"a": 1})
    assert result.success is True


async def test_correlation_id_behaviour_is_unchanged_on_not_found(bus_and_service):
    bus, _ = bus_and_service
    result = await bus.execute_tool("nonexistent_tool", {}, "ToolHandler")
    assert result.status is ToolExecutionStatus.NOT_FOUND
    assert result.success is False
    assert result.correlation_id  # still a fresh id, not empty


# ------------------------------------------- the bus is the enabled-tool source


async def test_tool_bus_registers_itself_as_the_enabled_tool_source():
    """Envelope issuance enumerates the deployment's tools from the live
    registry; the bus is that registry."""
    service = FakeToolService(["weather", "self_help", "discord_ban_user"])
    ToolBus(service_registry=FakeRegistry(service), time_service=FakeTimeService())
    resolved = await prime_enabled_tools()
    assert resolved == frozenset({"weather", "self_help", "discord_ban_user"})
    assert cached_enabled_tools() == resolved


# ------------------------------- the handler builds a subject with identity


async def test_tool_handler_passes_task_identity_to_the_bus(monkeypatch):
    """End of the thread: the handler's last step before the bus now carries
    task and thought identity, which is exactly what #938 said it did not."""
    from ciris_engine.logic.handlers.external import tool_handler as tool_handler_mod

    captured = {}

    class CapturingBus:
        async def execute_tool(self, tool_name, parameters, handler_name="default", subject=None):
            captured["subject"] = subject
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={},
                error=None,
                correlation_id="c",
            )

    class FakeBusManager:
        tool = CapturingBus()

    class FakeThought:
        thought_id = "th_42"
        source_task_id = "task_42"
        agent_occurrence_id = "default"

    class FakeDispatchContext:
        task_id = "task_42"

    # No task row exists, so the envelope resolves to None — a denial to Phase 2,
    # never "unconstrained". Identity must still arrive.
    monkeypatch.setattr(tool_handler_mod, "resolve_envelope_for_task_id", lambda *a, **k: None)

    handler = object.__new__(tool_handler_mod.ToolHandler)
    handler.bus_manager = FakeBusManager()
    handler.logger = logging.getLogger("test_tool_handler")

    from ciris_engine.schemas.actions import ToolParams

    ok, info = await handler._execute_tool(
        ToolParams(name="weather", parameters={"city": "Austin"}),
        FakeThought(),
        FakeDispatchContext(),
    )
    assert ok is True
    subject = captured["subject"]
    assert subject is not None
    assert subject.origin is ToolCallOrigin.REASONING
    assert subject.task_id == "task_42"
    assert subject.thought_id == "th_42"
    assert subject.envelope is None


# ------------------------------- task identity is handler-authoritative (#938)


def _handler():
    from ciris_engine.logic.handlers.external.tool_handler import ToolHandler

    handler = object.__new__(ToolHandler)
    handler.logger = logging.getLogger("test_tool_handler_authoritative")
    return handler


class _FakeThought:
    thought_id = "th_1"
    source_task_id = "task_REAL"
    agent_occurrence_id = "default"


def test_model_supplied_task_id_is_overwritten_by_the_handler():
    """A model-authored `task_id` must never survive into tool parameters.

    `authorize_spend` and anything else that authorizes on `task_id` reads it
    from the tool parameters. It used to be injected only when the model had not
    already set one, so the model could name whichever task it liked. The whole
    premise of the task envelope is a trustworthy task identity at the
    enforcement point.
    """
    from ciris_engine.schemas.actions import ToolParams

    params = ToolParams(name="send_money", parameters={"task_id": "task_ATTACKER_CHOSE", "amount": 100})
    built = _handler()._build_tool_params(params, _FakeThought())
    assert built["task_id"] == "task_REAL"
    assert built["amount"] == 100


def test_task_id_is_stamped_even_when_the_model_omits_it():
    from ciris_engine.schemas.actions import ToolParams

    built = _handler()._build_tool_params(ToolParams(name="web_search", parameters={"q": "x"}), _FakeThought())
    assert built["task_id"] == "task_REAL"


def test_unverifiable_task_id_is_dropped_not_passed_through():
    """With no source task there is nothing to vouch for, so the model value is
    removed rather than forwarded to a consumer that would trust it."""
    from ciris_engine.schemas.actions import ToolParams

    class NoTask(_FakeThought):
        source_task_id = ""

    built = _handler()._build_tool_params(
        ToolParams(name="send_money", parameters={"task_id": "task_ATTACKER_CHOSE"}), NoTask()
    )
    assert "task_id" not in built


# --------------------------- one dispatch point covers the enrichment path


async def test_dispatch_to_provider_is_the_single_execution_seam(bus_and_service):
    """`execute_tool` must reach a provider only through `dispatch_to_provider`.

    A Phase 2 gate placed in `execute_tool` alone would miss the
    context-enrichment path, which resolves providers itself and runs on every
    thought. Both now converge here.
    """
    bus, service = bus_and_service
    calls = []
    original = bus.dispatch_to_provider

    async def recording(*args, **kwargs):
        calls.append((args[1], kwargs.get("subject")))
        return await original(*args, **kwargs)

    bus.dispatch_to_provider = recording
    subject = ToolInvocationSubject.for_task(
        task_id="task_1", thought_id="th_1", handler_name="ToolHandler", envelope=make_envelope()
    )
    await bus.execute_tool("weather", {}, "ToolHandler", subject=subject)
    assert calls == [("weather", subject)]


async def test_dispatch_to_provider_records_the_subject(bus_and_service, caplog):
    bus, service = bus_and_service
    with caplog.at_level(logging.WARNING, logger="ciris_engine.logic.buses.tool_bus"):
        await bus.dispatch_to_provider(service, "weather", {}, handler_name="context_enrichment")
    warned = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("context_enrichment" in m for m in warned)


def _enrichment_tool():
    from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema

    return ToolInfo(
        name="weather",
        description="d",
        parameters=ToolParameterSchema(type="object", properties={}, required=[]),
        context_enrichment=True,
        context_enrichment_params={},
    )


async def test_context_enrichment_routes_through_the_bus(bus_and_service):
    """`_execute_enrichment_tool` dispatches via the bus, not via the instance."""
    from ciris_engine.logic.context.system_snapshot_helpers import _execute_enrichment_tool

    bus, service = bus_and_service
    seen = {}
    original = bus.dispatch_to_provider

    async def recording(svc, tool_name, params, **kwargs):
        seen["tool"] = tool_name
        seen["subject"] = kwargs.get("subject")
        seen["handler"] = kwargs.get("handler_name")
        return await original(svc, tool_name, params, **kwargs)

    bus.dispatch_to_provider = recording
    subject = ToolInvocationSubject.for_task(
        task_id="task_1",
        thought_id="th_1",
        handler_name="context_enrichment",
        origin=ToolCallOrigin.CONTEXT_ENRICHMENT,
    )
    _key, result = await _execute_enrichment_tool(
        [(service, "api")], "api", _enrichment_tool(), tool_bus=bus, subject=subject
    )
    assert seen["tool"] == "weather"
    assert seen["subject"] is subject
    assert seen["handler"] == "context_enrichment"
    assert result is not None


async def test_context_enrichment_still_works_without_a_bus(bus_and_service):
    """Startup cache population runs before the bus manager is wired; that path
    must keep working — a design that blocks weather lookups has failed."""
    from ciris_engine.logic.context.system_snapshot_helpers import _execute_enrichment_tool

    _, service = bus_and_service
    _key, result = await _execute_enrichment_tool([(service, "api")], "api", _enrichment_tool())
    assert result is not None
    assert service.calls
