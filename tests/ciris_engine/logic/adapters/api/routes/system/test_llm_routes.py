"""Tests for /system/llm/* API endpoints.

These tests validate the LLMBus management API endpoints:
- GET /system/llm/status - Bus status and aggregate metrics
- GET /system/llm/providers - List all providers with status
- PUT /system/llm/distribution - Update distribution strategy
- POST /system/llm/providers/{name}/circuit-breaker/reset - Reset CB
- PUT /system/llm/providers/{name}/circuit-breaker/config - Update CB config
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.registries.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_circuit_breaker() -> CircuitBreaker:
    """Create a mock circuit breaker with test data."""
    cb = CircuitBreaker("test_provider", CircuitBreakerConfig())
    cb.total_calls = 100
    cb.total_successes = 95
    cb.total_failures = 5
    cb.failure_count = 0
    cb.success_count = 3
    return cb


@pytest.fixture
def mock_circuit_breaker_open() -> CircuitBreaker:
    """Create a mock circuit breaker in OPEN state."""
    cb = CircuitBreaker("failing_provider", CircuitBreakerConfig())
    cb.state = CircuitState.OPEN
    cb.total_calls = 50
    cb.total_failures = 10
    cb.failure_count = 5
    cb.consecutive_failures = 5
    cb.last_failure_time = 1000.0
    return cb


@pytest.fixture
def mock_llm_bus(mock_circuit_breaker: CircuitBreaker, mock_circuit_breaker_open: CircuitBreaker) -> MagicMock:
    """Create a mock LLMBus with test data."""
    from ciris_engine.logic.buses.llm_bus import DistributionStrategy

    bus = MagicMock()
    bus.distribution_strategy = DistributionStrategy.LATENCY_BASED

    # Mock service_metrics
    mock_metrics_healthy = MagicMock()
    mock_metrics_healthy.total_requests = 100
    mock_metrics_healthy.failed_requests = 5
    mock_metrics_healthy.total_latency_ms = 65000.0
    mock_metrics_healthy.consecutive_failures = 0
    mock_metrics_healthy.last_request_time = datetime.now(timezone.utc)
    mock_metrics_healthy.last_failure_time = None

    mock_metrics_failing = MagicMock()
    mock_metrics_failing.total_requests = 50
    mock_metrics_failing.failed_requests = 10
    mock_metrics_failing.total_latency_ms = 25000.0
    mock_metrics_failing.consecutive_failures = 5
    mock_metrics_failing.last_request_time = datetime.now(timezone.utc)
    mock_metrics_failing.last_failure_time = datetime.now(timezone.utc)

    bus.service_metrics = {
        "test_provider": mock_metrics_healthy,
        "failing_provider": mock_metrics_failing,
    }

    # Mock circuit_breakers
    bus.circuit_breakers = {
        "test_provider": mock_circuit_breaker,
        "failing_provider": mock_circuit_breaker_open,
    }

    # Mock _rate_limited_until
    bus._rate_limited_until = {}

    # Mock _start_time
    bus._start_time = datetime.now(timezone.utc)

    # Mock get_service_stats
    bus.get_service_stats.return_value = {
        "test_provider": {
            "total_requests": 100,
            "failed_requests": 5,
            "average_latency_ms": 650.0,
            "failure_rate": 0.05,
            "circuit_state": "closed",
        },
        "failing_provider": {
            "total_requests": 50,
            "failed_requests": 10,
            "average_latency_ms": 500.0,
            "failure_rate": 0.2,
            "circuit_state": "open",
        },
    }

    # Mock get_stats
    bus.get_stats.return_value = {
        "distribution_strategy": "latency_based",
        "service_stats": bus.get_service_stats.return_value,
    }

    return bus


@pytest.fixture
def mock_bus_manager(mock_llm_bus: MagicMock) -> MagicMock:
    """Create a mock BusManager."""
    bus_manager = MagicMock()
    bus_manager.llm = mock_llm_bus
    return bus_manager


@pytest.fixture
def mock_runtime(mock_bus_manager: MagicMock) -> MagicMock:
    """Create a mock runtime with bus_manager."""
    runtime = MagicMock()
    runtime.bus_manager = mock_bus_manager
    return runtime


@pytest.fixture
def app_with_llm_routes(mock_runtime: MagicMock) -> FastAPI:
    """Create FastAPI app with LLM routes and mocked runtime.

    Patches is_first_run to return True so auth is bypassed (setup mode).
    """
    from ciris_engine.logic.adapters.api.routes.system.llm_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/system")
    app.state.runtime = mock_runtime
    return app


@pytest.fixture
def client(app_with_llm_routes: FastAPI) -> TestClient:
    """Create test client with first_run mocked to bypass auth."""
    # Patch is_first_run to return True (setup mode - no auth required)
    with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True):
        yield TestClient(app_with_llm_routes)


# ============================================================================
# Test: GET /system/llm/status
# ============================================================================


class TestGetLLMStatus:
    """Tests for GET /system/llm/status endpoint."""

    def test_returns_bus_status(self, client: TestClient, mock_llm_bus: MagicMock) -> None:
        """Test that status endpoint returns bus status."""
        response = client.get("/system/llm/status")

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["distribution_strategy"] == "latency_based"
        assert data["providers_total"] == 2
        assert "timestamp" in data

    def test_counts_circuit_breaker_states(self, client: TestClient) -> None:
        """Test that CB states are counted correctly."""
        response = client.get("/system/llm/status")

        assert response.status_code == 200
        data = response.json()["data"]

        # 1 CLOSED, 1 OPEN
        assert data["circuit_breakers_closed"] == 1
        assert data["circuit_breakers_open"] == 1
        assert data["circuit_breakers_half_open"] == 0

    def test_calculates_aggregate_metrics(self, client: TestClient) -> None:
        """Test that aggregate metrics are calculated."""
        response = client.get("/system/llm/status")

        assert response.status_code == 200
        data = response.json()["data"]

        # 100 + 50 = 150 total requests
        assert data["total_requests"] == 150
        # 5 + 10 = 15 failed
        assert data["failed_requests"] == 15

    def test_returns_503_when_runtime_unavailable(self, app_with_llm_routes: FastAPI) -> None:
        """Test that 503 is returned when runtime is unavailable."""
        app_with_llm_routes.state.runtime = None
        with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True):
            client = TestClient(app_with_llm_routes)
            response = client.get("/system/llm/status")

        assert response.status_code == 503

    def test_returns_503_when_bus_manager_unavailable(
        self, app_with_llm_routes: FastAPI, mock_runtime: MagicMock
    ) -> None:
        """Test that 503 is returned when bus_manager is unavailable."""
        mock_runtime.bus_manager = None
        with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True):
            client = TestClient(app_with_llm_routes)
            response = client.get("/system/llm/status")

        assert response.status_code == 503


# ============================================================================
# Test: GET /system/llm/providers
# ============================================================================


class TestGetLLMProviders:
    """Tests for GET /system/llm/providers endpoint."""

    def test_returns_all_providers(self, client: TestClient) -> None:
        """Test that all providers are returned."""
        response = client.get("/system/llm/providers")

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["total_count"] == 2
        assert len(data["providers"]) == 2

    def test_includes_provider_metrics(self, client: TestClient) -> None:
        """Test that provider metrics are included."""
        response = client.get("/system/llm/providers")

        assert response.status_code == 200
        providers = response.json()["data"]["providers"]

        # Find test_provider
        test_provider = next((p for p in providers if p["name"] == "test_provider"), None)
        assert test_provider is not None
        assert test_provider["metrics"]["total_requests"] == 100
        assert test_provider["metrics"]["failed_requests"] == 5

    def test_includes_circuit_breaker_status(self, client: TestClient) -> None:
        """Test that CB status is included."""
        response = client.get("/system/llm/providers")

        assert response.status_code == 200
        providers = response.json()["data"]["providers"]

        # test_provider should be CLOSED
        test_provider = next((p for p in providers if p["name"] == "test_provider"), None)
        assert test_provider["circuit_breaker"]["state"] == "closed"

        # failing_provider should be OPEN
        failing_provider = next((p for p in providers if p["name"] == "failing_provider"), None)
        assert failing_provider["circuit_breaker"]["state"] == "open"

    def test_healthy_flag_reflects_cb_state(self, client: TestClient) -> None:
        """Test that healthy flag reflects CB state."""
        response = client.get("/system/llm/providers")

        assert response.status_code == 200
        providers = response.json()["data"]["providers"]

        test_provider = next((p for p in providers if p["name"] == "test_provider"), None)
        failing_provider = next((p for p in providers if p["name"] == "failing_provider"), None)

        assert test_provider["healthy"] is True
        assert failing_provider["healthy"] is False


# ============================================================================
# Test: PUT /system/llm/distribution
# ============================================================================


class TestUpdateDistributionStrategy:
    """Tests for PUT /system/llm/distribution endpoint."""

    def test_updates_strategy(self, client: TestClient, mock_llm_bus: MagicMock) -> None:
        """Test that distribution strategy is updated."""
        response = client.put("/system/llm/distribution", json={"strategy": "round_robin"})

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["success"] is True
        assert data["previous_strategy"] == "latency_based"
        assert data["new_strategy"] == "round_robin"

    def test_rejects_invalid_strategy(self, client: TestClient) -> None:
        """Test that invalid strategy is rejected."""
        response = client.put("/system/llm/distribution", json={"strategy": "invalid_strategy"})

        assert response.status_code == 422  # Validation error

    def test_accepts_all_valid_strategies(self, client: TestClient, mock_llm_bus: MagicMock) -> None:
        """Test that all valid strategies are accepted."""
        strategies = ["round_robin", "latency_based", "random", "least_loaded"]

        for strategy in strategies:
            # Reset for each test
            from ciris_engine.logic.buses.llm_bus import DistributionStrategy

            mock_llm_bus.distribution_strategy = DistributionStrategy.LATENCY_BASED

            response = client.put("/system/llm/distribution", json={"strategy": strategy})
            assert response.status_code == 200, f"Strategy {strategy} should be valid"


# ============================================================================
# Test: POST /system/llm/providers/{name}/circuit-breaker/reset
# ============================================================================


class TestResetCircuitBreaker:
    """Tests for POST /system/llm/providers/{name}/circuit-breaker/reset endpoint."""

    def test_resets_open_circuit_breaker(
        self, client: TestClient, mock_circuit_breaker_open: CircuitBreaker
    ) -> None:
        """Test that OPEN circuit breaker is reset."""
        response = client.post("/system/llm/providers/failing_provider/circuit-breaker/reset")

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["success"] is True
        assert data["provider_name"] == "failing_provider"
        assert data["previous_state"] == "open"
        assert data["new_state"] == "closed"

    def test_resets_closed_circuit_breaker_with_force(
        self, client: TestClient, mock_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that CLOSED circuit breaker is reset with force flag."""
        response = client.post(
            "/system/llm/providers/test_provider/circuit-breaker/reset", json={"force": True}
        )

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["success"] is True
        assert data["new_state"] == "closed"

    def test_returns_404_for_unknown_provider(self, client: TestClient) -> None:
        """Test that 404 is returned for unknown provider."""
        response = client.post("/system/llm/providers/unknown_provider/circuit-breaker/reset")

        assert response.status_code == 404

    def test_skips_reset_for_closed_cb_without_force(
        self, client: TestClient, mock_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that CLOSED CB is not reset without force flag."""
        response = client.post(
            "/system/llm/providers/test_provider/circuit-breaker/reset", json={"force": False}
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # Should succeed but not actually reset (already closed)
        assert data["success"] is True
        assert data["message"] == "Circuit breaker already closed"


# ============================================================================
# Test: PUT /system/llm/providers/{name}/circuit-breaker/config
# ============================================================================


class TestUpdateCircuitBreakerConfig:
    """Tests for PUT /system/llm/providers/{name}/circuit-breaker/config endpoint."""

    def test_updates_failure_threshold(
        self, client: TestClient, mock_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that failure_threshold is updated."""
        response = client.put(
            "/system/llm/providers/test_provider/circuit-breaker/config",
            json={"failure_threshold": 10},
        )

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["success"] is True
        assert data["new_config"]["failure_threshold"] == 10
        assert mock_circuit_breaker.config.failure_threshold == 10

    def test_updates_multiple_config_values(
        self, client: TestClient, mock_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that multiple config values are updated."""
        response = client.put(
            "/system/llm/providers/test_provider/circuit-breaker/config",
            json={
                "failure_threshold": 10,
                "recovery_timeout_seconds": 30.0,
                "success_threshold": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["success"] is True
        assert data["new_config"]["failure_threshold"] == 10
        assert data["new_config"]["recovery_timeout_seconds"] == 30.0
        assert data["new_config"]["success_threshold"] == 5

    def test_returns_404_for_unknown_provider(self, client: TestClient) -> None:
        """Test that 404 is returned for unknown provider."""
        response = client.put(
            "/system/llm/providers/unknown_provider/circuit-breaker/config",
            json={"failure_threshold": 10},
        )

        assert response.status_code == 404

    def test_ignores_null_values(
        self, client: TestClient, mock_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that null values are ignored."""
        original_recovery_timeout = mock_circuit_breaker.config.recovery_timeout

        response = client.put(
            "/system/llm/providers/test_provider/circuit-breaker/config",
            json={"failure_threshold": 10, "recovery_timeout_seconds": None},
        )

        assert response.status_code == 200

        # recovery_timeout should be unchanged
        assert mock_circuit_breaker.config.recovery_timeout == original_recovery_timeout


# ============================================================================
# Test: Runtime Access Patterns
# ============================================================================


class TestRuntimeAccessPatterns:
    """Tests for runtime access through request.app.state."""

    def test_accesses_llm_bus_via_bus_manager(
        self, app_with_llm_routes: FastAPI, mock_runtime: MagicMock, mock_llm_bus: MagicMock
    ) -> None:
        """Test that LLMBus is accessed via runtime.bus_manager.llm."""
        with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True):
            client = TestClient(app_with_llm_routes)
            response = client.get("/system/llm/status")

        assert response.status_code == 200

    def test_circuit_breaker_accessed_directly(
        self, client: TestClient, mock_circuit_breaker: CircuitBreaker
    ) -> None:
        """Test that circuit breakers are accessed directly from bus.circuit_breakers."""
        # Reset the CB
        response = client.post(
            "/system/llm/providers/test_provider/circuit-breaker/reset", json={"force": True}
        )

        assert response.status_code == 200
        # The mock CB should have been accessed directly


# ============================================================================
# Test: Integration with Real CircuitBreaker
# ============================================================================


class TestCircuitBreakerIntegration:
    """Integration tests with real CircuitBreaker objects."""

    def test_reset_actually_resets_cb(self) -> None:
        """Test that reset() actually resets the CB state."""
        cb = CircuitBreaker("test", CircuitBreakerConfig())

        # Put CB in OPEN state
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Reset it
        cb.reset()

        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_config_is_mutable(self) -> None:
        """Test that CB config can be modified at runtime."""
        cb = CircuitBreaker("test", CircuitBreakerConfig())

        assert cb.config.failure_threshold == 5

        # Modify config
        cb.config.failure_threshold = 10

        assert cb.config.failure_threshold == 10

    def test_force_open_works(self) -> None:
        """Test that force_open() immediately opens the CB."""
        cb = CircuitBreaker("test", CircuitBreakerConfig())

        assert cb.state == CircuitState.CLOSED

        # Force open
        cb.force_open(reason="test")

        assert cb.state == CircuitState.OPEN
