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
