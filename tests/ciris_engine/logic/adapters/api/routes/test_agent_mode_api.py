"""Tests for /v1/system/agent-mode API endpoints.

Covers:
- GET requires OBSERVER+ (or above), returns AgentModeStatus.
- PUT requires SYSTEM_ADMIN, performs a transition.
- PUT to SERVER with insufficient disk returns 400 with structured error.
"""

from __future__ import annotations

from collections import namedtuple
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.constants import SERVER_MINIMUM_DISK_BYTES
from ciris_engine.logic.adapters.api.dependencies.auth import require_observer, require_system_admin
from ciris_engine.logic.adapters.api.routes.system.agent_mode import router
from ciris_engine.logic.utils.agent_mode_broker import get_agent_mode_broker
from ciris_engine.schemas.runtime.agent_mode import AgentMode

# Minimal fake of shutil.disk_usage's return type.
_Usage = namedtuple("_Usage", ["total", "used", "free"])


# ----------------------------- Fixtures ----------------------------- #


def _observer_auth() -> object:
    return MagicMock(user_id="obs", role="OBSERVER")


def _admin_auth() -> object:
    return MagicMock(user_id="root", role="SYSTEM_ADMIN")


@pytest.fixture(autouse=True)
def reset_singleton_broker() -> None:
    """Make sure the module-level broker is in a known state for each test."""
    broker = get_agent_mode_broker()
    broker.reset_for_tests(mode=AgentMode.PROXY)
    yield
    broker.reset_for_tests(mode=AgentMode.PROXY)


def _make_app(resource_monitor: object | None) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/system")
    app.state.resource_monitor = resource_monitor
    # Always override observer auth (PUT additionally overrides system_admin).
    app.dependency_overrides[require_observer] = _observer_auth
    app.dependency_overrides[require_system_admin] = _admin_auth
    return app


@pytest.fixture
def healthy_resource_monitor() -> MagicMock:
    """Resource monitor reporting enough disk for SERVER mode."""
    m = MagicMock()
    m.get_available_disk_bytes.return_value = SERVER_MINIMUM_DISK_BYTES + 1
    m.is_server_mode_eligible.return_value = True
    return m


@pytest.fixture
def starving_resource_monitor() -> MagicMock:
    """Resource monitor reporting too little disk for SERVER mode."""
    m = MagicMock()
    m.get_available_disk_bytes.return_value = 1024  # 1 KiB
    m.is_server_mode_eligible.return_value = False
    return m


# ----------------------------- GET tests ----------------------------- #


class TestGetAgentMode:
    def test_returns_current_mode_and_disk_facts(self, healthy_resource_monitor: MagicMock) -> None:
        app = _make_app(healthy_resource_monitor)
        client = TestClient(app)

        response = client.get("/system/agent-mode")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["mode"] == "proxy"
        assert data["server_minimum_disk_bytes"] == SERVER_MINIMUM_DISK_BYTES
        assert data["server_eligible"] is True
        assert data["available_disk_bytes"] == SERVER_MINIMUM_DISK_BYTES + 1
        assert isinstance(data["data_dir"], str)

    def test_reflects_broker_state(self, healthy_resource_monitor: MagicMock) -> None:
        broker = get_agent_mode_broker()
        broker._mode = AgentMode.CLIENT  # direct state mutation OK for read test

        app = _make_app(healthy_resource_monitor)
        client = TestClient(app)
        response = client.get("/system/agent-mode")
        assert response.status_code == 200
        assert response.json()["data"]["mode"] == "client"

    def test_falls_back_to_shutil_when_monitor_absent(self) -> None:
        app = _make_app(None)
        client = TestClient(app)

        fake = _Usage(
            total=2 * SERVER_MINIMUM_DISK_BYTES,
            used=0,
            free=SERVER_MINIMUM_DISK_BYTES + 1,
        )
        with patch(
            "ciris_engine.logic.adapters.api.routes.system.agent_mode.shutil.disk_usage",
            return_value=fake,
        ):
            response = client.get("/system/agent-mode")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["available_disk_bytes"] == SERVER_MINIMUM_DISK_BYTES + 1
        assert data["server_eligible"] is True


# ----------------------------- PUT tests ----------------------------- #


class TestPutAgentMode:
    def test_switches_mode_and_returns_status(self, healthy_resource_monitor: MagicMock) -> None:
        app = _make_app(healthy_resource_monitor)
        client = TestClient(app)
        response = client.put("/system/agent-mode", json={"mode": "client"})
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["mode"] == "client"
        assert body["requires_restart"] is True
        assert get_agent_mode_broker().current_mode() is AgentMode.CLIENT

    def test_switch_to_server_when_disk_sufficient(self, healthy_resource_monitor: MagicMock) -> None:
        app = _make_app(healthy_resource_monitor)
        client = TestClient(app)
        response = client.put("/system/agent-mode", json={"mode": "server"})
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["mode"] == "server"
        assert body["data"]["server_eligible"] is True
        assert get_agent_mode_broker().current_mode() is AgentMode.SERVER

    def test_switch_to_server_with_insufficient_disk_returns_400(self, starving_resource_monitor: MagicMock) -> None:
        app = _make_app(starving_resource_monitor)
        client = TestClient(app)
        response = client.put("/system/agent-mode", json={"mode": "server"})
        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "INSUFFICIENT_DISK"
        assert body["available_bytes"] == 1024
        assert body["required_bytes"] == SERVER_MINIMUM_DISK_BYTES
        # Mode must NOT have been mutated.
        assert get_agent_mode_broker().current_mode() is AgentMode.PROXY

    def test_disk_gate_does_not_apply_to_client_or_proxy(self, starving_resource_monitor: MagicMock) -> None:
        app = _make_app(starving_resource_monitor)
        client = TestClient(app)

        # Switching to CLIENT works even with 1 KiB free.
        response = client.put("/system/agent-mode", json={"mode": "client"})
        assert response.status_code == 200
        assert response.json()["data"]["mode"] == "client"

        # And back to PROXY likewise.
        response = client.put("/system/agent-mode", json={"mode": "proxy"})
        assert response.status_code == 200
        assert response.json()["data"]["mode"] == "proxy"

    def test_invalid_mode_in_body_returns_422(self, healthy_resource_monitor: MagicMock) -> None:
        app = _make_app(healthy_resource_monitor)
        client = TestClient(app)
        response = client.put("/system/agent-mode", json={"mode": "listener"})
        assert response.status_code == 422

    def test_put_requires_system_admin(self) -> None:
        """Without overriding the system_admin dependency, an unauthenticated
        PUT must fail at the auth layer (not 200, not 400).

        The exact status depends on whether the auth service is wired into
        app.state — missing service yields 500, real auth with no token
        yields 401. Either way the handler does NOT run, which is the
        invariant we care about: the broker stays in PROXY mode.
        """
        app = FastAPI()
        app.include_router(router, prefix="/system")
        # Only observer override; system_admin stays real.
        app.dependency_overrides[require_observer] = _observer_auth
        client = TestClient(app)
        response = client.put("/system/agent-mode", json={"mode": "client"})
        assert response.status_code != 200, "auth must block the call"
        assert get_agent_mode_broker().current_mode() is AgentMode.PROXY
