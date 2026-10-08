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
    reclaiming = [n for n in type(budget).model_fields if getattr(budget, n).elevated_action == ResourceAction.RECLAIM]
    assert reclaiming == ["memory_mb"]


def test_no_default_uses_drain_and_caps_match_the_ruling():
    budget = ResourceBudget()
    caps = {name: getattr(budget, name).action for name in type(budget).model_fields}
    assert ResourceAction.DRAIN not in caps.values()
    assert caps["cpu_percent"] == ResourceAction.THROTTLE
    assert caps["tokens_day"] == ResourceAction.SHED
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

    await _set_memory(monitor, 768)  # ELEVATED
    assert calls == ["resource_monitor:reclaim"]
    await _set_memory(monitor, 768)  # stays ELEVATED: reclaims again once the cooldown allows
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


def _activate(monitor, task_manager) -> int:
    fake = SimpleNamespace(resource_monitor=monitor, task_manager=task_manager)
    return WorkProcessor._activate_pending_tasks_unless_shedding(fake)


@pytest.mark.asyncio
async def test_shed_stops_task_activation_and_lifts(monitor):
    task_manager = Mock()
    task_manager.activate_pending_tasks = Mock(return_value=2)
    assert _activate(monitor, task_manager) == 2

    await _set_thoughts(monitor, 50)  # CRITICAL -> SHED
    task_manager.activate_pending_tasks.reset_mock()
    assert _activate(monitor, task_manager) == 0
    task_manager.activate_pending_tasks.assert_not_called()

    await _set_thoughts(monitor, 0)
    assert _activate(monitor, task_manager) == 2
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
