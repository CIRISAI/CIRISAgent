"""Resource pressure acts: each action engages, the subscriber acts, and it lifts.

The monitor used to emit its signals into a bus nobody but itself listened to.
These tests drive a real ResourceMonitorService through its levels and assert
on what the acting components do -- the work loop's round delay, task
activation, the observer's intake, the API status code, and the shutdown path.
"""

import os
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ciris_engine.logic.adapters.api.dependencies.auth import require_observer
from ciris_engine.logic.adapters.api.routes import agent as agent_routes
from ciris_engine.logic.adapters.base_observer import BaseObserver
from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.logic.processors.states.work_processor import WorkProcessor
from ciris_engine.logic.services.infrastructure.resource_monitor import ResourceMonitorService
from ciris_engine.logic.services.infrastructure.resource_monitor import service as rm_service
from ciris_engine.logic.services.infrastructure.resource_monitor.pressure import (
    MAX_THROTTLE_EXTRA_SECONDS,
    SHED_RETRY_AFTER_SECONDS,
    actions_for_level,
    pressure_gate_of,
)
from ciris_engine.logic.services.lifecycle.shutdown import ShutdownService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.logic.utils import shutdown_manager
from ciris_engine.schemas.api.auth import AuthContext, Permission, UserRole
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.messages import IncomingMessage, MessageHandlingStatus
from ciris_engine.schemas.services.resources_core import (
    MemoryReleaseResult,
    PressureLevel,
    ResourceAction,
    ResourceBudget,
    ResourceLimit,
)


def _fill_cpu_window(m) -> None:
    """A full minute of idle CPU samples, as after the first 60 s of uptime."""
    m._cpu_history.extend([0.0] * (m._cpu_history.maxlen or 0))


def _fake_release(trigger: str) -> MemoryReleaseResult:
    return MemoryReleaseResult(
        trigger=trigger,
        platform_call="malloc_trim",
        rss_before_mb=0,
        rss_after_mb=0,
        reclaimed_mb=0,
        gc_collected=0,
        duration_ms=0,
    )


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.setattr(rm_service, "_release_process_memory", _fake_release)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    m = ResourceMonitorService(budget=ResourceBudget(), db_path=db_path, time_service=TimeService())
    _fill_cpu_window(m)
    yield m
    os.unlink(db_path)


async def _set_thoughts(monitor: ResourceMonitorService, value: int) -> None:
    monitor.snapshot.thoughts_active = value
    await monitor._check_limits()


def _gate(monitor):
    gate = pressure_gate_of(monitor)
    assert gate is not None
    return gate


# --------------------------------------------------------------------------- #
# The ladder
# --------------------------------------------------------------------------- #


def _limits(budget: ResourceBudget) -> dict:
    return {n: getattr(budget, n) for n in type(budget).model_fields if isinstance(getattr(budget, n), ResourceLimit)}


def _limit(cap: ResourceAction, elevated: ResourceAction = ResourceAction.WARN) -> ResourceLimit:
    return ResourceLimit(limit=100, warning=60, critical=80, action=cap, elevated_action=elevated)


def test_default_ladder_and_caps():
    memory = _limit(ResourceAction.SHED, ResourceAction.RECLAIM)
    assert actions_for_level(PressureLevel.NORMAL, memory) == []
    assert actions_for_level(PressureLevel.ELEVATED, memory) == [ResourceAction.RECLAIM]
    assert actions_for_level(PressureLevel.HIGH, memory) == [ResourceAction.RECLAIM, ResourceAction.THROTTLE]
    assert actions_for_level(PressureLevel.CRITICAL, memory) == [
        ResourceAction.RECLAIM,
        ResourceAction.THROTTLE,
        ResourceAction.SHED,
    ]
    # Non-memory resources: ELEVATED is non-acting, the ladder starts at THROTTLE
    thoughts = _limit(ResourceAction.SHED)
    assert actions_for_level(PressureLevel.ELEVATED, thoughts) == []
    assert actions_for_level(PressureLevel.CRITICAL, thoughts) == [ResourceAction.THROTTLE, ResourceAction.SHED]
    # cpu is capped at THROTTLE; WARN only logs; DRAIN joins only when it is the cap
    assert actions_for_level(PressureLevel.CRITICAL, _limit(ResourceAction.THROTTLE)) == [ResourceAction.THROTTLE]
    assert actions_for_level(PressureLevel.CRITICAL, _limit(ResourceAction.WARN, ResourceAction.RECLAIM)) == []
    assert ResourceAction.DRAIN in actions_for_level(PressureLevel.CRITICAL, _limit(ResourceAction.DRAIN))
    assert ResourceAction.DRAIN not in actions_for_level(PressureLevel.HIGH, _limit(ResourceAction.DRAIN))


def test_elevated_rung_cannot_be_an_admission_or_shutdown_action():
    for action in (ResourceAction.THROTTLE, ResourceAction.SHED, ResourceAction.DRAIN):
        with pytest.raises(ValidationError):
            _limit(ResourceAction.SHED, action)


def test_only_memory_reclaims_by_default():
    budget = ResourceBudget()
    reclaiming = [n for n, limit in _limits(budget).items() if limit.elevated_action == ResourceAction.RECLAIM]
    assert reclaiming == ["memory_mb"]


def test_no_default_uses_drain_and_caps_match_the_ruling():
    budget = ResourceBudget()
    caps = {name: limit.action for name, limit in _limits(budget).items()}
    assert ResourceAction.DRAIN not in caps.values()
    assert caps["cpu_percent"] == ResourceAction.THROTTLE
    # No token budget by default (user ruling): the windows are not budgeted at all
    assert budget.tokens_hour is None and budget.tokens_day is None
    assert "tokens_hour" not in caps and "tokens_day" not in caps
    assert caps["memory_mb"] == ResourceAction.SHED
    assert caps["thoughts_active"] == ResourceAction.SHED
    assert caps["disk_mb"] == ResourceAction.WARN


@pytest.mark.asyncio
async def test_levels_rise_at_once_and_fall_with_hysteresis(monitor):
    await _set_thoughts(monitor, 50)
    assert monitor.get_pressure_levels() == {"thoughts_active": PressureLevel.CRITICAL}
    await _set_thoughts(monitor, 49)  # below limit 50, but not clearly (band = 2)
    assert monitor.get_pressure_levels()["thoughts_active"] == PressureLevel.CRITICAL
    await _set_thoughts(monitor, 47)  # < 50 - 2 -> HIGH (still >= 48 - 2)
    assert monitor.get_pressure_levels()["thoughts_active"] == PressureLevel.HIGH
    await _set_thoughts(monitor, 10)  # clearly below everything
    assert monitor.get_pressure_levels() == {}


@pytest.mark.asyncio
async def test_disk_is_not_checked(monitor):
    monitor.snapshot.disk_used_mb = 10_000_000
    await monitor._check_limits()
    assert "disk_mb" not in monitor.get_pressure_levels()
    assert monitor.snapshot.healthy is True


# --------------------------------------------------------------------------- #
# RECLAIM
# --------------------------------------------------------------------------- #


async def _set_memory(monitor: ResourceMonitorService, value: int) -> None:
    monitor.snapshot.memory_mb = value
    await monitor._check_limits()


@pytest.mark.asyncio
async def test_reclaim_engages_at_elevated_memory_and_lifts(monitor, monkeypatch):
    calls = []
    monkeypatch.setattr(rm_service, "_release_process_memory", lambda t: calls.append(t) or _fake_release(t))
    monitor.budget.memory_mb.cooldown_seconds = 0

    elevated = monitor.budget.memory_mb.warning
    await _set_memory(monitor, elevated)  # ELEVATED
    assert calls == ["resource_monitor:reclaim"]
    await _set_memory(monitor, elevated)  # stays ELEVATED: reclaims again once the cooldown allows
    assert len(calls) == 2

    await _set_memory(monitor, 100)  # back to NORMAL
    await _set_memory(monitor, 100)
    assert len(calls) == 2
    assert monitor._collect_custom_metrics()["resource_signal_reclaim_total"] == 2.0


@pytest.mark.asyncio
async def test_cpu_and_thoughts_never_release_memory(monitor, monkeypatch):
    """Releasing heap does nothing for CPU or thought counts and costs CPU:
    neither reclaims at ELEVATED, nor at any higher level."""
    calls = []
    monkeypatch.setattr(rm_service, "_release_process_memory", lambda t: calls.append(t) or _fake_release(t))
    monitor.budget.cpu_percent.cooldown_seconds = 0
    monitor.budget.thoughts_active.cooldown_seconds = 0

    monitor.snapshot.cpu_average_1m = 60  # ELEVATED
    await _set_thoughts(monitor, 40)  # ELEVATED
    assert monitor.get_pressure_levels() == {
        "cpu_percent": PressureLevel.ELEVATED,
        "thoughts_active": PressureLevel.ELEVATED,
    }
    await _set_thoughts(monitor, 40)  # repeat tick within the level
    assert not _gate(monitor).is_active(ResourceAction.THROTTLE)

    monitor.snapshot.cpu_average_1m = 100  # CRITICAL (capped at THROTTLE)
    await _set_thoughts(monitor, 50)  # CRITICAL
    assert _gate(monitor).is_active(ResourceAction.THROTTLE)

    assert calls == []
    assert "resource_signal_reclaim_total" not in monitor._collect_custom_metrics()


# --------------------------------------------------------------------------- #
# THROTTLE -> AgentProcessor round delay
# --------------------------------------------------------------------------- #


def _round_delay(monitor, state=AgentState.WORK) -> float:
    fake = SimpleNamespace(
        app_config=SimpleNamespace(mock_llm=False), services=SimpleNamespace(resource_monitor=monitor)
    )
    return AgentProcessor._calculate_round_delay(fake, state)


@pytest.mark.asyncio
async def test_throttle_slows_the_loop_and_lifts(monitor):
    assert _round_delay(monitor) == 3.0

    await _set_thoughts(monitor, 48)  # HIGH -> THROTTLE
    assert _gate(monitor).resources(ResourceAction.THROTTLE) == ["thoughts_active"]
    throttled = _round_delay(monitor)
    assert 3.0 < throttled <= 3.0 + MAX_THROTTLE_EXTRA_SECONDS
    assert _round_delay(monitor, AgentState.SHUTDOWN) == 1.0  # never slows shutdown

    await _set_thoughts(monitor, 0)
    assert not _gate(monitor).is_active(ResourceAction.THROTTLE)
    assert _round_delay(monitor) == 3.0
    metrics = monitor._collect_custom_metrics()
    assert metrics["resource_signal_throttle_total"] == 1.0
    assert metrics["resource_signal_throttle_lifted_total"] == 1.0
    assert metrics["resource_pressure_throttled_rounds_total"] == 1.0


@pytest.mark.asyncio
async def test_cpu_never_sheds(monitor):
    monitor.snapshot.cpu_average_1m = 100
    await monitor._check_limits()
    assert _gate(monitor).is_active(ResourceAction.THROTTLE)
    assert not _gate(monitor).is_active(ResourceAction.SHED)


# --------------------------------------------------------------------------- #
# SHED -> WorkProcessor task activation
# --------------------------------------------------------------------------- #


async def _activate(monitor, task_manager) -> int:
    fake = SimpleNamespace(
        resource_monitor=monitor, task_manager=task_manager, _discover_incomplete_tickets=AsyncMock(return_value=0)
    )
    _tickets, activated = await WorkProcessor._admit_new_work(fake)
    return activated


@pytest.mark.asyncio
async def test_shed_stops_task_activation_and_lifts(monitor):
    task_manager = Mock()
    task_manager.activate_pending_tasks = Mock(return_value=2)
    assert await _activate(monitor, task_manager) == 2

    await _set_thoughts(monitor, 50)  # CRITICAL -> SHED
    task_manager.activate_pending_tasks.reset_mock()
    assert await _activate(monitor, task_manager) == 0
    task_manager.activate_pending_tasks.assert_not_called()

    await _set_thoughts(monitor, 0)
    assert await _activate(monitor, task_manager) == 2
    metrics = monitor._collect_custom_metrics()
    assert metrics["resource_pressure_shed_rounds_total"] == 1.0
    assert metrics["resource_signal_shed_lifted_total"] == 1.0


# --------------------------------------------------------------------------- #
# SHED -> observer intake -> API 503
# --------------------------------------------------------------------------- #


class _Observer(BaseObserver[IncomingMessage]):
    async def start(self) -> None:  # pragma: no cover
        pass

    async def stop(self) -> None:  # pragma: no cover
        pass


def _observer(monitor) -> _Observer:
    obs = _Observer(on_observe=AsyncMock(), agent_id="agent", origin_service="api", resource_monitor=monitor)
    obs._check_for_accord = AsyncMock()  # type: ignore[method-assign]
    obs._enforce_credit_policy = AsyncMock()  # type: ignore[method-assign]
    return obs


def _msg() -> IncomingMessage:
    return IncomingMessage(message_id="m1", author_id="u1", author_name="user", content="hi", channel_id="api_u1")


@pytest.mark.asyncio
async def test_shed_refuses_at_intake_before_credit_and_lifts(monitor):
    obs = _observer(monitor)
    await _set_thoughts(monitor, 50)

    result = await obs.handle_incoming_message(_msg())
    assert result.status == MessageHandlingStatus.RESOURCE_SHED
    assert result.shed_resources == ["thoughts_active"]
    obs._check_for_accord.assert_awaited_once()  # the accord check still runs first
    obs._enforce_credit_policy.assert_not_awaited()  # nobody is charged for refused work

    await _set_thoughts(monitor, 0)
    assert obs._refuse_if_shedding(_msg(), "m1", "api_u1") is None
    assert monitor._collect_custom_metrics()["resource_pressure_shed_refusals_total"] == 1.0


@pytest.fixture
def api_app(monitor):
    app = FastAPI()
    app.include_router(agent_routes.router)
    app.state.auth_service = Mock(get_user=Mock(return_value=None), _users={})
    processor = Mock(_is_paused=False, state_manager=Mock(current_state="WORK"))
    app.state.runtime = Mock(agent_processor=processor, agent_identity=Mock(agent_id="agent", name="Agent"))
    app.state.api_config = Mock(interaction_timeout=1.0)
    app.state.consent_manager = AsyncMock()
    app.state.consent_manager.get_consent = AsyncMock(return_value=Mock(user_id="admin_user"))
    app.state.resource_monitor = Mock(spec=[])
    app.state.on_message = _observer(monitor).handle_incoming_message

    auth = AuthContext(
        user_id="admin_user",
        role=UserRole.ADMIN,
        permissions={Permission.SEND_MESSAGES, Permission.VIEW_MESSAGES},
        api_key_id="k",
        authenticated_at=datetime.now(timezone.utc),
    )

    async def _auth():
        return auth

    app.dependency_overrides[require_observer] = _auth
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/agent/message", "/agent/interact"])
async def test_shed_surfaces_as_503_with_retry_after(monitor, api_app, path):
    await _set_thoughts(monitor, 50)
    response = TestClient(api_app).post(path, json={"message": "hello"})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == str(SHED_RETRY_AFTER_SECONDS)
    detail = response.json()["detail"]
    assert detail["error"] == "resource_shed"
    assert detail["reason"] == "RESOURCE_SHED"
    assert detail["resources"] == ["thoughts_active"]


def test_raise_if_shed_ignores_other_statuses():
    agent_routes._raise_if_shed(SimpleNamespace(status=MessageHandlingStatus.TASK_CREATED), "m", Mock())
    with pytest.raises(HTTPException) as exc:
        agent_routes._raise_if_shed(
            SimpleNamespace(status=MessageHandlingStatus.RESOURCE_SHED, shed_resources=["memory_mb"]), "m", Mock()
        )
    assert exc.value.status_code == 503


# --------------------------------------------------------------------------- #
# DRAIN -> the graceful shutdown path, and nothing harsher
# --------------------------------------------------------------------------- #


@pytest.fixture
def fresh_global_shutdown():
    shutdown_manager.reset_global_shutdown_service()
    yield
    shutdown_manager.reset_global_shutdown_service()


@pytest.mark.asyncio
async def test_drain_requests_graceful_shutdown_only(monitor, monkeypatch, fresh_global_shutdown):
    forbidden = Mock(side_effect=AssertionError("harsh exit path called"))
    monkeypatch.setattr(os, "_exit", forbidden)
    monkeypatch.setattr(os, "kill", forbidden)
    monkeypatch.setattr(os, "execv", forbidden)
    monkeypatch.setattr(os, "execvp", forbidden)
    emergency = AsyncMock()
    force_kill = AsyncMock()
    monkeypatch.setattr(ShutdownService, "emergency_shutdown", emergency)
    monkeypatch.setattr(ShutdownService, "_force_kill_after_timeout", force_kill)
    runtime_handler = Mock(
        __name__="runtime_request_shutdown"
    )  # stands in for component_builder's runtime.request_shutdown hook
    shutdown_manager.register_global_shutdown_handler(runtime_handler)

    monitor.budget.thoughts_active.action = ResourceAction.DRAIN
    await _set_thoughts(monitor, 48)  # HIGH: drain must wait for CRITICAL
    assert not shutdown_manager.is_global_shutdown_requested()

    await _set_thoughts(monitor, 50)
    assert shutdown_manager.is_global_shutdown_requested()
    assert "thoughts_active" in (shutdown_manager.get_global_shutdown_reason() or "")
    runtime_handler.assert_called_once()
    await _set_thoughts(monitor, 0)
    await _set_thoughts(monitor, 50)  # one-shot: a second crossing does not re-request
    runtime_handler.assert_called_once()
    assert monitor._collect_custom_metrics()["resource_pressure_drain_requested"] == 1.0

    forbidden.assert_not_called()
    emergency.assert_not_awaited()
    force_kill.assert_not_awaited()
    assert _gate(monitor).get_state().drain_requested is not None


def test_pressure_gate_of_ignores_mocks():
    assert pressure_gate_of(Mock()) is None
    assert pressure_gate_of(None) is None


# --------------------------------------------------------------------------- #
# Codex review of #1242
# --------------------------------------------------------------------------- #

from ciris_adapters.reddit.observer import RedditObserver  # noqa: E402
from ciris_adapters.reddit.schemas import RedditCredentials  # noqa: E402
from ciris_engine.logic.adapters.api.api_observer import APIObserver  # noqa: E402
from ciris_engine.logic.adapters.cli.cli_observer import CLIObserver  # noqa: E402
from ciris_engine.logic.adapters.discord.discord_observer import DiscordObserver  # noqa: E402
from ciris_engine.logic.buses.bus_manager import BusManager  # noqa: E402
from ciris_engine.logic.buses.llm_bus import LLMBus  # noqa: E402
from ciris_engine.logic.runtime.device_class import DEVICE_CLASS_ENV, resolve_device_class  # noqa: E402
from ciris_engine.schemas.runtime.messages import DiscordMessage  # noqa: E402
from ciris_engine.schemas.runtime.resources import ResourceUsage  # noqa: E402
from ciris_engine.schemas.services.resources_core import DeviceClass  # noqa: E402


def _late_bound(monitor):
    """What the runtime gives every adapter: a BusManager carrying the monitor."""
    return lambda: SimpleNamespace(resource_monitor=monitor)


def _stub_intake(obs):
    obs._check_for_accord = AsyncMock()  # type: ignore[method-assign]
    obs._enforce_credit_policy = AsyncMock()  # type: ignore[method-assign]
    return obs


def _cli(monitor):
    return CLIObserver(on_observe=AsyncMock(), bus_manager_provider=_late_bound(monitor), agent_id="agent")


def _discord(monitor):
    return DiscordObserver(agent_id="agent", bus_manager_provider=_late_bound(monitor))


def _api(monitor):
    return APIObserver(
        on_observe=AsyncMock(), bus_manager_provider=_late_bound(monitor), agent_id="agent", origin_service="api"
    )


def _reddit(monitor):
    creds = RedditCredentials(
        client_id="i", client_secret="s", username="u", password="p", user_agent="ua", subreddit="ciris"
    )
    obs = RedditObserver(credentials=creds, agent_id="agent")
    obs.bus_manager = SimpleNamespace(resource_monitor=monitor)  # Reddit passes bus_manager directly
    return obs


@pytest.mark.asyncio
@pytest.mark.parametrize("make", [_cli, _discord, _api, _reddit], ids=["cli", "discord", "api", "reddit"])
async def test_shed_reaches_observers_built_without_a_monitor(monitor, make):
    """CLI, Discord and Reddit are constructed without a resource monitor;
    admission control late-binds it from the runtime's BusManager."""
    obs = _stub_intake(make(monitor))
    assert obs.resource_monitor is None
    msg_cls = DiscordMessage if isinstance(obs, DiscordObserver) else IncomingMessage
    msg = msg_cls(message_id="m1", author_id="u1", author_name="user", content="hi", channel_id="c1")

    await _set_thoughts(monitor, 50)
    result = await obs.handle_incoming_message(msg)
    assert result.status == MessageHandlingStatus.RESOURCE_SHED
    obs._enforce_credit_policy.assert_not_awaited()

    await _set_thoughts(monitor, 0)
    assert obs._refuse_if_shedding(msg, "m1", "c1") is None


def test_api_adapter_reads_the_runtime_monitor_attribute():
    """The runtime exposes `resource_monitor`; `resource_monitor_service` does not exist on it."""
    import inspect

    from ciris_engine.logic.adapters.api import adapter as api_adapter
    from ciris_engine.logic.runtime.service_property_mixin import ServicePropertyMixin

    assert isinstance(inspect.getattr_static(ServicePropertyMixin, "resource_monitor"), property)
    source = inspect.getsource(api_adapter)
    assert 'getattr(self.runtime, "resource_monitor", None)' in source
    assert 'getattr(self.runtime, "resource_monitor_service"' not in source


@pytest.mark.asyncio
async def test_one_llm_call_moves_tokens_used_hour_by_its_tokens(monitor):
    telemetry = SimpleNamespace(record_metric=AsyncMock())
    bus = BusManager(Mock(), TimeService(), telemetry_service=telemetry, resource_monitor=monitor).llm
    assert bus.resource_monitor is monitor

    await monitor._update_snapshot()
    before = monitor.snapshot.tokens_used_hour
    usage = ResourceUsage(tokens_used=1234, tokens_input=1000, tokens_output=234, model_used="m")
    await bus._record_resource_telemetry("svc", "handler", usage, 10.0)
    await monitor._update_snapshot()

    assert monitor.snapshot.tokens_used_hour - before == 1234
    assert monitor.snapshot.tokens_used_day - before == 1234
    canonical = [c for c in telemetry.record_metric.await_args_list if c.kwargs["metric_name"] == "llm.tokens.total"]
    assert [c.kwargs["value"] for c in canonical] == [1234.0]  # same fact, written once


@pytest.mark.asyncio
async def test_tokens_recorded_even_without_telemetry(monitor):
    bus = LLMBus(Mock(), TimeService(), resource_monitor=monitor)
    await bus._record_resource_telemetry("svc", "h", ResourceUsage(tokens_used=7, model_used="m"), 1.0)
    await monitor._update_snapshot()
    assert monitor.snapshot.tokens_used_hour == 7


def test_thought_count_is_scoped_to_the_occurrence(monitor, monkeypatch):
    from ciris_engine.logic.persistence.models import thoughts as thoughts_model

    seen = []

    def fake(status, occurrence_id="default", limit=None):
        seen.append(occurrence_id)
        return [object()] * (3 if occurrence_id == "occurrence-7" else 99)

    monkeypatch.setattr(thoughts_model, "get_thoughts_by_status", fake)
    scoped = ResourceMonitorService(
        budget=ResourceBudget(), db_path=monitor.db_path, time_service=TimeService(), agent_occurrence_id="occurrence-7"
    )
    assert scoped._count_active_thoughts() == 6  # PENDING + PROCESSING for occurrence-7 only
    assert seen == ["occurrence-7", "occurrence-7"]


@pytest.mark.parametrize(
    "device_class, expected",
    [
        (DeviceClass.PHONE, (768, 960, 1024)),
        (DeviceClass.LAPTOP, (3072, 3840, 4096)),
        (DeviceClass.SERVER, (3072, 3840, 4096)),
    ],
)
def test_memory_budget_is_device_sized(device_class, expected):
    budget = ResourceBudget.for_device_class(device_class)
    memory = budget.memory_mb
    assert (memory.warning, memory.critical, memory.limit) == expected
    assert budget.device_class == device_class
    assert budget.thoughts_active == ResourceBudget().thoughts_active  # only memory differs


def test_resolve_device_class(monkeypatch):
    from ciris_engine.logic.runtime import device_class as dc

    monkeypatch.setattr(dc, "is_android", lambda: False)
    monkeypatch.setattr(dc, "is_ios", lambda: False)
    monkeypatch.delenv(DEVICE_CLASS_ENV, raising=False)
    assert resolve_device_class() == DeviceClass.SERVER
    monkeypatch.setenv(DEVICE_CLASS_ENV, "laptop")
    assert resolve_device_class() == DeviceClass.LAPTOP
    monkeypatch.setenv(DEVICE_CLASS_ENV, "bogus")
    assert resolve_device_class() == DeviceClass.SERVER
    monkeypatch.setattr(dc, "is_android", lambda: True)
    assert resolve_device_class() == DeviceClass.PHONE


@pytest.mark.asyncio
async def test_published_limits_are_the_acting_budget(monitor, api_app):
    """/v1/system/resources and the telemetry resource view report the monitor's own budget."""
    from ciris_engine.logic.adapters.api.routes import telemetry as telemetry_routes
    from ciris_engine.logic.adapters.api.routes.system import services as system_services

    monitor.budget = ResourceBudget.for_device_class(DeviceClass.PHONE)
    api_app.include_router(system_services.router)
    api_app.include_router(telemetry_routes.router)
    api_app.state.resource_monitor = monitor
    api_app.state.telemetry_service = SimpleNamespace(query_metrics=AsyncMock(return_value=[]))
    client = TestClient(api_app)

    limits = client.get("/resources").json()["data"]["limits"]
    assert limits["memory_mb"]["limit"] == 1024
    assert limits["device_class"] == "phone"
    tele = client.get("/telemetry/resources").json()["data"]["limits"]
    assert tele["max_memory_mb"] == 1024.0
    assert tele["max_cpu_percent"] == float(monitor.budget.cpu_percent.limit)


@pytest.mark.asyncio
async def test_shed_claims_no_shared_ticket(monitor, monkeypatch):
    """A pressured occurrence must not take shared work a healthy peer could do."""
    from ciris_engine.logic.persistence.models import tickets as tickets_model

    claims = []
    shared = {"ticket_id": "T-1", "agent_occurrence_id": "__shared__", "status": "pending"}
    monkeypatch.setattr(
        tickets_model, "list_tickets", lambda status=None, **kw: [shared] if status == "pending" else []
    )
    monkeypatch.setattr(tickets_model, "update_ticket_status", lambda *a, **kw: claims.append(a) or True)

    wp = WorkProcessor.__new__(WorkProcessor)
    wp.resource_monitor = monitor
    wp.agent_occurrence_id = "occurrence-1"
    wp.task_manager = Mock(activate_pending_tasks=Mock(return_value=0))
    wp._create_seed_task_for_ticket = Mock(return_value=True)  # type: ignore[method-assign]

    await _set_thoughts(monitor, 50)  # SHED
    assert await wp._admit_new_work() == (0, 0)
    assert claims == []

    await _set_thoughts(monitor, 0)  # lifted
    tickets, _ = await wp._admit_new_work()
    assert tickets == 1
    assert claims and claims[0][:2] == ("T-1", "assigned")


@pytest.mark.asyncio
async def test_round_delay_uses_the_state_after_this_rounds_transitions(monitor):
    """A round that moved to SHUTDOWN (e.g. a DRAIN) is not slowed by THROTTLE."""
    await _set_thoughts(monitor, 48)  # HIGH -> THROTTLE
    states = iter([AgentState.WORK, AgentState.SHUTDOWN])
    delays = []

    ap = AgentProcessor.__new__(AgentProcessor)
    ap.app_config = SimpleNamespace(mock_llm=False)
    ap.services = SimpleNamespace(resource_monitor=monitor)
    ap.current_round_number = 0
    ap.state_manager = Mock(get_state=Mock(side_effect=lambda: next(states)))
    ap._should_stop_after_target_rounds = Mock(return_value=False)  # type: ignore[method-assign]
    ap._check_pause_state = AsyncMock(return_value=True)  # type: ignore[method-assign]
    ap._handle_shutdown_transitions = AsyncMock(return_value=True)  # type: ignore[method-assign]
    ap._process_current_state = AsyncMock(return_value=(1, 0, False))  # type: ignore[method-assign]

    async def capture(delay):
        delays.append(delay)
        return True

    ap._handle_delay_with_stop_check = capture  # type: ignore[method-assign]
    await AgentProcessor._process_single_round(ap, 0, 0, 5, None)

    assert delays == [1.0]  # SHUTDOWN base delay, no throttle extra
    assert ap._process_current_state.await_args.args[3] == AgentState.WORK


# --------------------------------------------------------------------------- #
# Staged QA run 37723851128: SHED engaged at boot
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_default_token_windows_are_unbudgeted(monitor, caplog, api_app):
    """No token budget by default: usage is recorded and reported, nothing is
    evaluated -- no level, no log line, no warning, no alert, no limit published."""
    from ciris_engine.logic.adapters.api.routes.system import services as system_services
    from ciris_engine.logic.context.system_snapshot_helpers import _collect_resource_alerts

    monitor.snapshot.tokens_used_hour = 30_527
    monitor.snapshot.tokens_used_day = 183_150  # the values from staged QA run 37723851128
    with caplog.at_level("DEBUG", logger="ciris_engine.logic.services.infrastructure.resource_monitor"):
        await monitor._check_limits()

    assert monitor.get_pressure_levels() == {}
    assert not _gate(monitor).is_active(ResourceAction.THROTTLE)
    assert not _gate(monitor).is_active(ResourceAction.SHED)
    assert monitor.snapshot.warnings == [] and monitor.snapshot.critical == []
    assert monitor.snapshot.healthy is True
    assert _collect_resource_alerts(monitor) == []
    assert not [r for r in caplog.records if "tokens_" in r.getMessage()]
    metrics = monitor._collect_custom_metrics()
    assert "resource_pressure_level_tokens_hour" not in metrics
    assert metrics["tokens_used_hour"] == 30_527.0  # usage still reported

    api_app.include_router(system_services.router)
    api_app.state.resource_monitor = monitor
    limits = TestClient(api_app).get("/resources").json()["data"]["limits"]
    assert limits["tokens_hour"] is None and limits["tokens_day"] is None


@pytest.mark.asyncio
async def test_an_operator_token_budget_acts(monitor):
    """The ladder is kept: a configured budget acts."""
    await monitor.set_token_budget(
        "tokens_day", ResourceLimit(limit=100, warning=80, critical=95, action=ResourceAction.SHED)
    )
    monitor.snapshot.tokens_used_day = 100
    await monitor._check_limits()
    assert _gate(monitor).resources(ResourceAction.SHED) == ["tokens_day"]
    assert monitor.snapshot.healthy is False


@pytest.mark.asyncio
async def test_tokens_accumulate_once_per_call_in_both_windows(monitor):
    """Each call adds exactly its tokens_used once; hour and day read the same history."""
    bus = LLMBus(Mock(), TimeService(), resource_monitor=monitor)
    for tokens in (15_000, 20_350, 22_000):
        await bus._record_resource_telemetry("svc", "h", ResourceUsage(tokens_used=tokens, model_used="m"), 1.0)
    await monitor._update_snapshot()
    assert monitor.snapshot.tokens_used_hour == 57_350
    assert monitor.snapshot.tokens_used_day == 57_350


@pytest.mark.asyncio
async def test_cpu_cannot_engage_before_a_full_minute(monkeypatch):
    """At boot cpu_average_1m averages a few startup samples; it must not throttle on them."""
    monkeypatch.setattr(rm_service, "_release_process_memory", _fake_release)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        m = ResourceMonitorService(budget=ResourceBudget(), db_path=db_path, time_service=TimeService())
        monkeypatch.setattr(m._process, "cpu_percent", lambda interval=0: 94.0)  # the boot reading from the run

        for _ in range(3):  # three seconds after start
            await m._update_snapshot()
            await m._check_limits()
        assert m.snapshot.cpu_average_1m == 94
        assert not m.cpu_window_full
        assert "cpu_percent" not in m.get_pressure_levels()
        assert not _gate(m).is_active(ResourceAction.THROTTLE)

        for _ in range(57):  # the window fills at 60 samples
            await m._update_snapshot()
        await m._check_limits()
        assert m.cpu_window_full
        assert m.get_pressure_levels()["cpu_percent"] == PressureLevel.CRITICAL
        assert _gate(m).is_active(ResourceAction.THROTTLE)
    finally:
        os.unlink(db_path)


# --------------------------------------------------------------------------- #
# Token budgets from the config graph (user ruling: none by default)
# --------------------------------------------------------------------------- #

import pytest_asyncio  # noqa: E402

from ciris_engine.logic.persistence.db import initialize_database  # noqa: E402
from ciris_engine.logic.services.graph.config_service import GraphConfigService  # noqa: E402
from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService  # noqa: E402

DAY_KEY = "resources.token_budget.day"
HOUR_KEY = "resources.token_budget.hour"


@pytest_asyncio.fixture
async def config_service():
    """A real GraphConfigService on a temp graph (the agent's config bus)."""
    from ciris_engine.logic.persistence.models import graph as _graph_mod
    from ciris_engine.logic.secrets.service import SecretsService

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    prior_engine, prior_dsn = _graph_mod._engine, _graph_mod._engine_dsn
    initialize_database(db_path)
    time_service = TimeService()
    secrets = SecretsService(db_path=db_path.replace(".db", "_secrets.db"), time_service=time_service)
    await secrets.start()
    memory = LocalGraphMemoryService(db_path=db_path, secrets_service=secrets, time_service=time_service)
    await memory.start()
    service = GraphConfigService(graph_memory_service=memory, time_service=time_service)
    await service.start()
    yield service
    _graph_mod._engine, _graph_mod._engine_dsn = prior_engine, prior_dsn
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_budget_is_read_from_the_config_graph_at_startup(monitor, config_service):
    await config_service.set_config(
        DAY_KEY, {"warning": 800, "critical": 900, "limit": 1000, "action": "shed"}, updated_by="admin"
    )
    await monitor.attach_config_service(config_service)

    assert monitor.budget.tokens_day is not None
    assert (monitor.budget.tokens_day.warning, monitor.budget.tokens_day.limit) == (800, 1000)
    assert monitor.budget.tokens_hour is None  # only the configured window is budgeted

    monitor.snapshot.tokens_used_day = 1000
    await monitor._check_limits()
    assert _gate(monitor).resources(ResourceAction.SHED) == ["tokens_day"]


@pytest.mark.asyncio
async def test_budget_changes_apply_live_and_removal_reverts(monitor, config_service):
    await monitor.attach_config_service(config_service)
    assert monitor.budget.tokens_hour is None

    # set: THROTTLE engages at the configured values
    await config_service.set_config(HOUR_KEY, {"warning": 50, "critical": 60, "limit": 70}, updated_by="admin")
    monitor.snapshot.tokens_used_hour = 60
    await monitor._check_limits()
    assert monitor.get_pressure_levels()["tokens_hour"] == PressureLevel.HIGH
    assert _gate(monitor).resources(ResourceAction.THROTTLE) == ["tokens_hour"]

    # change: raise the thresholds -> the old level is released, the window is re-evaluated
    await config_service.set_config(HOUR_KEY, {"warning": 500, "critical": 600, "limit": 700}, updated_by="admin")
    assert not _gate(monitor).is_active(ResourceAction.THROTTLE)
    await monitor._check_limits()
    assert "tokens_hour" not in monitor.get_pressure_levels()

    # change the cap to SHED and cross the limit
    await config_service.set_config(
        HOUR_KEY, {"warning": 500, "critical": 600, "limit": 700, "action": "shed"}, updated_by="admin"
    )
    monitor.snapshot.tokens_used_hour = 700
    await monitor._check_limits()
    assert _gate(monitor).resources(ResourceAction.SHED) == ["tokens_hour"]

    # remove (what DELETE /v1/config/{key} does): back to unbudgeted, SHED lifts
    await config_service.set_config(HOUR_KEY, None, updated_by="admin")
    assert monitor.budget.tokens_hour is None
    assert not _gate(monitor).is_active(ResourceAction.SHED)
    await monitor._check_limits()
    assert monitor.get_pressure_levels() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        {"warning": 900, "critical": 800, "limit": 1000},  # out of order
        {"warning": 1, "critical": 2, "limit": 3, "action": "drain"},  # not a token action
        {"warning": 1, "critical": 2, "limit": 3, "surprise": True},  # unknown field
        {"warning": -1, "critical": 2, "limit": 3},  # not positive
        "lots",  # not an object
    ],
)
async def test_invalid_budget_is_logged_and_ignored(monitor, config_service, caplog, bad):
    await monitor.attach_config_service(config_service)
    with caplog.at_level("WARNING"):
        await config_service.set_config(DAY_KEY, bad, updated_by="admin")
    assert monitor.budget.tokens_day is None  # stays unbudgeted
    assert any("Invalid token budget" in r.getMessage() for r in caplog.records)
    monitor.snapshot.tokens_used_day = 10**9
    await monitor._check_limits()  # never crashes
    assert monitor.get_pressure_levels() == {}


@pytest.mark.asyncio
async def test_invalid_change_keeps_the_budget_in_force(monitor, config_service, caplog):
    await monitor.attach_config_service(config_service)
    await config_service.set_config(DAY_KEY, {"warning": 1, "critical": 2, "limit": 3}, updated_by="admin")
    with caplog.at_level("WARNING"):
        await config_service.set_config(DAY_KEY, {"warning": 3, "critical": 2, "limit": 1}, updated_by="admin")
    assert monitor.budget.tokens_day is not None and monitor.budget.tokens_day.limit == 3
    assert any("Invalid token budget" in r.getMessage() for r in caplog.records)


def test_budget_keys_follow_the_config_naming_and_are_not_sensitive():
    from ciris_engine.schemas.api.config_security import ConfigSecurity
    from ciris_engine.schemas.services.resources_core import TOKEN_BUDGET_CONFIG_KEYS

    assert set(TOKEN_BUDGET_CONFIG_KEYS) == {HOUR_KEY, DAY_KEY}
    for key in TOKEN_BUDGET_CONFIG_KEYS:
        assert not ConfigSecurity.is_sensitive(key)  # settable by an ADMIN through PUT /v1/config/{key}
        assert not key.startswith("system.")
