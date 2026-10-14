"""The API under a constitutional halt (CC 4.2.1.1, CIRISAgent#1231).

`/v1/agent/interact` and `/v1/agent/message` answer 423 `accord_halt_in_effect`,
ahead of SHED's 503; nothing reaches the observer. Status reports the halt.
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import require_observer
from ciris_engine.logic.adapters.api.routes import agent as agent_routes
from ciris_engine.logic.utils import halt_latch
from ciris_engine.schemas.api.auth import AuthContext, Permission, UserRole
from ciris_engine.schemas.runtime.accord_halt import AccordHaltReading, AccordHaltState
from ciris_engine.schemas.runtime.messages import MessageHandlingStatus

pytestmark = pytest.mark.real_halt_latch


def _state(halted: bool, reading: AccordHaltReading, invocation_id: Any = None) -> AccordHaltState:
    return AccordHaltState(
        halted=halted, reading=reading, invocation_id=invocation_id, read_at=datetime.now(timezone.utc)
    )


HALTED = _state(True, AccordHaltReading.IN_EFFECT, "inv-api")
NOT_HALTED = _state(False, AccordHaltReading.NOT_HALTED)


class Latch:
    def __init__(self, state: AccordHaltState) -> None:
        self.state = state

    async def read(self) -> AccordHaltState:
        return self.state


@pytest.fixture
def latch(monkeypatch):
    lt = Latch(HALTED)
    monkeypatch.setattr(halt_latch, "_read_from_node", lt.read)
    monkeypatch.setattr(halt_latch, "HALT_READ_CACHE_TTL_SECONDS", 0.0)
    return lt


@pytest.fixture
def on_message():
    """The observer intake. While halted it must never be reached; when reached it SHEDs."""
    return AsyncMock(return_value=Mock(status=MessageHandlingStatus.RESOURCE_SHED, shed_resources=["memory_mb"]))


@pytest.fixture
def api_app(on_message):
    app = FastAPI()
    app.include_router(agent_routes.router)
    app.state.auth_service = Mock(get_user=Mock(return_value=None), _users={})
    processor = Mock(_is_paused=False, state_manager=Mock(current_state="WORK"))
    app.state.runtime = Mock(agent_processor=processor, agent_identity=Mock(agent_id="agent", name="Agent"))
    app.state.api_config = Mock(interaction_timeout=1.0)
    app.state.consent_manager = AsyncMock()
    app.state.consent_manager.get_consent = AsyncMock(return_value=Mock(user_id="admin_user"))
    app.state.resource_monitor = Mock(spec=[])
    app.state.on_message = on_message

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


@pytest.mark.parametrize("path", ["/agent/message", "/agent/interact"])
def test_halt_answers_423_ahead_of_shed(latch, api_app, on_message, path):
    response = TestClient(api_app).post(path, json={"message": "hello"})

    assert response.status_code == 423
    assert "Retry-After" not in response.headers
    detail = response.json()["detail"]
    assert detail["error"] == "accord_halt_in_effect"
    assert detail["reason"] == "ACCORD_HALT"
    assert detail["halt"]["invocation_id"] == "inv-api"
    assert detail["halt"]["reading"] == "in_effect"
    on_message.assert_not_awaited()  # refused before intake


@pytest.mark.parametrize("path", ["/agent/message", "/agent/interact"])
def test_without_a_halt_the_same_request_reaches_intake(latch, api_app, on_message, path):
    """Positive control: with no halt, SHED's own 503 answers."""
    latch.state = NOT_HALTED
    response = TestClient(api_app).post(path, json={"message": "hello"})
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "resource_shed"
    on_message.assert_awaited_once()


def test_fail_closed_reading_also_refuses(latch, api_app):
    latch.state = _state(True, AccordHaltReading.NO_NODE)
    response = TestClient(api_app).post("/agent/interact", json={"message": "hello"})
    assert response.status_code == 423
    assert response.json()["detail"]["halt"]["reading"] == "no_node"


def test_status_reports_the_halt_and_still_answers(latch, api_app, monkeypatch):
    api_app.state.service_registry = None
    monkeypatch.setattr(agent_routes, "_get_current_task_info", lambda request: None)
    monkeypatch.setattr(agent_routes, "_count_wakeup_tasks", lambda uptime: 0)
    monkeypatch.setattr(agent_routes, "_get_agent_identity_info", lambda runtime: ("agent", "Agent"))
    response = TestClient(api_app).get("/agent/status")
    assert response.status_code == 200, response.text
    halt = response.json()["data"]["accord_halt"]
    assert halt["halted"] is True
    assert halt["invocation_id"] == "inv-api"


@pytest.mark.asyncio
async def test_health_reports_the_halt_and_still_answers(latch, monkeypatch):
    """A halt is not ill health: `status` is the health verdict, the halt rides beside it."""
    from types import SimpleNamespace

    from ciris_engine.logic.adapters.api.routes.system import health

    monkeypatch.setattr(health, "get_system_uptime", lambda request: 1.0)
    monkeypatch.setattr(health, "get_current_time", lambda request: datetime.now(timezone.utc))
    monkeypatch.setattr(health, "get_cognitive_state_safe", lambda request: "WORK")
    monkeypatch.setattr(health, "check_initialization_status", lambda request: True)
    monkeypatch.setattr(health, "collect_service_health", AsyncMock(return_value={}))
    monkeypatch.setattr(health, "check_processor_health", AsyncMock(return_value=True))
    monkeypatch.setattr(health, "collect_system_warnings", AsyncMock(return_value=(False, [])))
    monkeypatch.setattr(health, "determine_overall_status", lambda *a: "healthy")
    monkeypatch.setattr(health, "collect_agent_capabilities", lambda *a, **k: [])
    monkeypatch.setattr(health, "collect_node_fold_state", lambda: None)
    monkeypatch.setattr(health, "_is_first_run_setup", lambda: False)

    result = await health.get_system_health(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())), None)
    assert result.data.status == "healthy"
    assert result.data.accord_halt is not None
    assert result.data.accord_halt.halted is True
    assert result.data.accord_halt.invocation_id == "inv-api"
