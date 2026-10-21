"""POST /system/runtime/memory/release — the operator/QA trigger for the give-back chain."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import require_admin
from ciris_engine.logic.adapters.api.routes.system.runtime import router
from ciris_engine.schemas.services.resources_core import MemoryReleaseResult


def _result(trigger: str = "api:admin") -> MemoryReleaseResult:
    return MemoryReleaseResult(
        trigger=trigger,
        platform_call="malloc_trim",
        rss_before_mb=800,
        rss_after_mb=520,
        reclaimed_mb=280,
        gc_collected=12,
        duration_ms=21,
    )


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/system")
    app.dependency_overrides[require_admin] = lambda: MagicMock()
    app.state.runtime = None
    return app


def test_release_uses_the_monitor_on_app_state(app: FastAPI):
    monitor = MagicMock()
    monitor.release_memory = AsyncMock(return_value=_result())
    app.state.resource_monitor = monitor

    response = TestClient(app).post("/system/runtime/memory/release")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["reclaimed_mb"] == 280
    assert data["platform_call"] == "malloc_trim"
    monitor.release_memory.assert_awaited_once_with(trigger="api:admin")


def test_release_falls_back_to_the_runtime_service(app: FastAPI):
    monitor = MagicMock()
    monitor.release_memory = AsyncMock(return_value=_result())
    app.state.resource_monitor = None
    app.state.runtime = MagicMock(resource_monitor_service=monitor)

    response = TestClient(app).post("/system/runtime/memory/release")

    assert response.status_code == 200, response.text
    monitor.release_memory.assert_awaited_once()


def test_release_is_503_without_a_monitor(app: FastAPI):
    app.state.resource_monitor = None
    app.state.runtime = None

    response = TestClient(app).post("/system/runtime/memory/release")

    assert response.status_code == 503


def test_release_is_not_swallowed_by_the_generic_runtime_action_route(app: FastAPI):
    """`/runtime/{action}` must not capture `/runtime/memory/release` and 400 it."""
    monitor = MagicMock()
    monitor.release_memory = AsyncMock(return_value=_result())
    app.state.resource_monitor = monitor

    response = TestClient(app).post("/system/runtime/memory/release")

    assert response.status_code == 200, response.text


def test_release_requires_admin():
    """Without the admin dependency satisfied the handler is never reached."""
    app = FastAPI()
    app.include_router(router, prefix="/system")
    monitor = MagicMock()
    monitor.release_memory = AsyncMock(return_value=_result())
    app.state.resource_monitor = monitor

    response = TestClient(app).post("/system/runtime/memory/release")

    assert response.status_code != 200, response.text
    monitor.release_memory.assert_not_awaited()


def test_release_failure_is_a_500_with_the_reason(app: FastAPI):
    monitor = MagicMock()
    monitor.release_memory = AsyncMock(side_effect=RuntimeError("allocator exploded"))
    app.state.resource_monitor = monitor

    response = TestClient(app).post("/system/runtime/memory/release")

    assert response.status_code == 500
    assert "allocator exploded" in response.json()["detail"]
