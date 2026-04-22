"""Tests for /system/llm/* API endpoints.

These tests validate the LLMBus management API endpoints:
- GET /system/llm/status - Bus status and aggregate metrics
- GET /system/llm/providers - List all providers with status
- PUT /system/llm/distribution - Update distribution strategy
- POST /system/llm/providers/{name}/circuit-breaker/reset - Reset CB
- PUT /system/llm/providers/{name}/circuit-breaker/config - Update CB config
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

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
def mock_registry() -> MagicMock:
    """Create a mock registry with test providers."""
    from ciris_engine.logic.registries.base import Priority
    from ciris_engine.schemas.runtime.enums import ServiceType

    registry = MagicMock()

    # Create mock provider info objects
    provider1 = MagicMock()
    provider1.name = "test_provider"
    provider1.priority = Priority.NORMAL

    provider2 = MagicMock()
    provider2.name = "failing_provider"
    provider2.priority = Priority.NORMAL

    # Registry returns these providers for LLM service type
    registry._services = {ServiceType.LLM: [provider1, provider2]}
    registry.get_provider_by_name.return_value = provider1

    return registry


@pytest.fixture
def client(app_with_llm_routes: FastAPI, mock_registry: MagicMock) -> TestClient:
    """Create test client with first_run mocked to bypass auth."""
    # Patch is_first_run to return True (setup mode - no auth required)
    # Also patch the global registry to return our mock
    with patch(
        "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
    ), patch(
        "ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry", return_value=mock_registry
    ):
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
        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ):
            client = TestClient(app_with_llm_routes)
            response = client.get("/system/llm/status")

        assert response.status_code == 503

    def test_returns_503_when_bus_manager_unavailable(
        self, app_with_llm_routes: FastAPI, mock_runtime: MagicMock
    ) -> None:
        """Test that 503 is returned when bus_manager is unavailable."""
        mock_runtime.bus_manager = None
        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ):
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

    def test_resets_open_circuit_breaker(self, client: TestClient, mock_circuit_breaker_open: CircuitBreaker) -> None:
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
        response = client.post("/system/llm/providers/test_provider/circuit-breaker/reset", json={"force": True})

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
        response = client.post("/system/llm/providers/test_provider/circuit-breaker/reset", json={"force": False})

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

    def test_updates_failure_threshold(self, client: TestClient, mock_circuit_breaker: CircuitBreaker) -> None:
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

    def test_updates_multiple_config_values(self, client: TestClient, mock_circuit_breaker: CircuitBreaker) -> None:
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

    def test_ignores_null_values(self, client: TestClient, mock_circuit_breaker: CircuitBreaker) -> None:
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
        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ):
            client = TestClient(app_with_llm_routes)
            response = client.get("/system/llm/status")

        assert response.status_code == 200

    def test_circuit_breaker_accessed_directly(self, client: TestClient, mock_circuit_breaker: CircuitBreaker) -> None:
        """Test that circuit breakers are accessed directly from bus.circuit_breakers."""
        # Reset the CB
        response = client.post("/system/llm/providers/test_provider/circuit-breaker/reset", json={"force": True})

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


# ============================================================================
# Test: Provider Priority Management
# ============================================================================


class TestProviderPriorityEndpoint:
    """Tests for PUT /system/llm/providers/{name}/priority endpoint."""

    def test_update_priority_success(self, client: TestClient) -> None:
        """Test successful priority update."""
        from ciris_engine.logic.registries.base import Priority, ServiceProvider

        # Create a mock provider
        mock_provider = MagicMock(spec=ServiceProvider)
        mock_provider.name = "test_provider"
        mock_provider.priority = Priority.NORMAL

        with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry") as mock_registry:
            mock_reg = MagicMock()
            mock_reg.get_provider_by_name.return_value = mock_provider
            mock_reg.set_provider_priority.return_value = True
            mock_registry.return_value = mock_reg

            response = client.put(
                "/system/llm/providers/test_provider/priority",
                json={"priority": "high"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        assert data["data"]["provider_name"] == "test_provider"
        assert data["data"]["new_priority"] == "high"

    def test_update_priority_provider_not_found(self, client: TestClient) -> None:
        """Test priority update returns 404 for unknown provider."""
        with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry") as mock_registry:
            mock_reg = MagicMock()
            mock_reg.get_provider_by_name.return_value = None
            mock_registry.return_value = mock_reg

            response = client.put(
                "/system/llm/providers/nonexistent/priority",
                json={"priority": "high"},
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_update_priority_validates_priority_enum(self, client: TestClient) -> None:
        """Test that invalid priority values are rejected."""
        response = client.put(
            "/system/llm/providers/test_provider/priority",
            json={"priority": "invalid_priority"},
        )

        assert response.status_code == 422  # Validation error


class TestProviderDeleteEndpoint:
    """Tests for DELETE /system/llm/providers/{name} endpoint."""

    def test_delete_provider_success(self, client: TestClient) -> None:
        """Test successful provider deletion."""
        from ciris_engine.logic.registries.base import Priority, ServiceProvider

        mock_provider = MagicMock(spec=ServiceProvider)
        mock_provider.name = "test_provider"
        mock_provider.priority = Priority.NORMAL

        with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry") as mock_registry:
            mock_reg = MagicMock()
            mock_reg.get_provider_by_name.return_value = mock_provider
            mock_reg.unregister.return_value = True
            mock_registry.return_value = mock_reg

            response = client.delete("/system/llm/providers/test_provider")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        assert data["data"]["provider_name"] == "test_provider"

    def test_delete_provider_not_found(self, client: TestClient) -> None:
        """Test delete returns 404 for unknown provider."""
        with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry") as mock_registry:
            mock_reg = MagicMock()
            mock_reg.get_provider_by_name.return_value = None
            mock_registry.return_value = mock_reg

            response = client.delete("/system/llm/providers/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ============================================================================
# Test: ServiceRegistry Priority Methods
# ============================================================================


class TestServiceRegistryPriorityMethods:
    """Unit tests for ServiceRegistry priority management methods."""

    def test_set_provider_priority_success(self) -> None:
        """Test setting provider priority updates correctly."""
        from ciris_engine.logic.registries.base import Priority, ServiceRegistry
        from ciris_engine.schemas.runtime.enums import ServiceType

        registry = ServiceRegistry()
        mock_service = MagicMock()

        # Register a service
        name = registry.register_service(
            ServiceType.LLM,
            mock_service,
            priority=Priority.NORMAL,
        )

        # Update priority
        success = registry.set_provider_priority(name, Priority.HIGH, ServiceType.LLM)
        assert success is True

        # Verify priority changed
        provider = registry.get_provider_by_name(name, ServiceType.LLM)
        assert provider is not None
        assert provider.priority == Priority.HIGH

    def test_set_provider_priority_not_found(self) -> None:
        """Test setting priority for non-existent provider returns False."""
        from ciris_engine.logic.registries.base import Priority, ServiceRegistry
        from ciris_engine.schemas.runtime.enums import ServiceType

        registry = ServiceRegistry()

        success = registry.set_provider_priority("nonexistent", Priority.HIGH, ServiceType.LLM)
        assert success is False

    def test_get_provider_by_name_success(self) -> None:
        """Test getting provider by name."""
        from ciris_engine.logic.registries.base import Priority, ServiceRegistry
        from ciris_engine.schemas.runtime.enums import ServiceType

        registry = ServiceRegistry()
        mock_service = MagicMock()

        name = registry.register_service(
            ServiceType.LLM,
            mock_service,
            priority=Priority.NORMAL,
        )

        provider = registry.get_provider_by_name(name, ServiceType.LLM)
        assert provider is not None
        assert provider.name == name

    def test_get_provider_by_name_not_found(self) -> None:
        """Test getting non-existent provider returns None."""
        from ciris_engine.logic.registries.base import ServiceRegistry
        from ciris_engine.schemas.runtime.enums import ServiceType

        registry = ServiceRegistry()

        provider = registry.get_provider_by_name("nonexistent", ServiceType.LLM)
        assert provider is None

    def test_set_priority_reorders_providers(self) -> None:
        """Test that setting priority re-sorts the provider list."""
        from ciris_engine.logic.registries.base import Priority, ServiceRegistry
        from ciris_engine.schemas.runtime.enums import ServiceType

        registry = ServiceRegistry()

        # Register two services with different priorities
        mock_service_1 = MagicMock()
        mock_service_2 = MagicMock()

        name1 = registry.register_service(
            ServiceType.LLM,
            mock_service_1,
            priority=Priority.NORMAL,
        )
        name2 = registry.register_service(
            ServiceType.LLM,
            mock_service_2,
            priority=Priority.LOW,
        )

        # Verify initial order: NORMAL before LOW
        providers = registry._services[ServiceType.LLM]
        assert providers[0].name == name1
        assert providers[1].name == name2

        # Change second provider to HIGH (should now be first)
        registry.set_provider_priority(name2, Priority.HIGH, ServiceType.LLM)

        # Verify new order: HIGH before NORMAL
        providers = registry._services[ServiceType.LLM]
        assert providers[0].name == name2
        assert providers[1].name == name1


# ============================================================================
# Test: Add Provider Endpoint
# ============================================================================


class TestAddProviderEndpoint:
    """Tests for POST /system/llm/providers endpoint."""

    def test_add_provider_success(self, app_with_llm_routes: FastAPI) -> None:
        """Test successful provider addition."""
        # Add required services to app state
        app_with_llm_routes.state.telemetry_service = MagicMock()
        app_with_llm_routes.state.time_service = MagicMock()

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ):
            with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry") as mock_registry:
                mock_reg = MagicMock()
                mock_reg.get_provider_by_name.return_value = None  # Not existing
                mock_reg.register_service.return_value = "test_local"
                mock_registry.return_value = mock_reg

                # Mock the OpenAI client creation
                with patch(
                    "ciris_engine.logic.services.runtime.llm_service.service.OpenAICompatibleClient"
                ) as mock_client_class:
                    mock_client = MagicMock()
                    mock_client.start = AsyncMock()  # start() is async
                    mock_client_class.return_value = mock_client

                    client = TestClient(app_with_llm_routes)
                    response = client.post(
                        "/system/llm/providers",
                        json={
                            "provider_id": "local",
                            "name": "test_local",
                            "base_url": "http://192.168.1.100:11434/v1",
                            "model": "llama3.2",
                            "priority": "fallback",
                        },
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        assert data["data"]["provider_name"] == "test_local"
        assert data["data"]["provider_id"] == "local"
        assert data["data"]["priority"] == "fallback"

    def test_add_provider_generates_name(self, app_with_llm_routes: FastAPI) -> None:
        """Test that provider name is auto-generated if not provided."""
        app_with_llm_routes.state.telemetry_service = MagicMock()
        app_with_llm_routes.state.time_service = MagicMock()

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ):
            with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry") as mock_registry:
                mock_reg = MagicMock()
                mock_reg.get_provider_by_name.return_value = None
                mock_reg.register_service.return_value = "local_192.168.1.100_11434_v1"
                mock_registry.return_value = mock_reg

                with patch(
                    "ciris_engine.logic.services.runtime.llm_service.service.OpenAICompatibleClient"
                ) as mock_client_class:
                    mock_client = MagicMock()
                    mock_client.start = AsyncMock()  # start() is async
                    mock_client_class.return_value = mock_client

                    client = TestClient(app_with_llm_routes)
                    response = client.post(
                        "/system/llm/providers",
                        json={
                            "provider_id": "local",
                            "base_url": "http://192.168.1.100:11434/v1",
                            # No name provided
                        },
                    )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        # Name should be auto-generated from provider_id and url
        assert "local" in data["data"]["provider_name"]
        assert "192.168.1.100" in data["data"]["provider_name"]

    def test_add_provider_already_exists(self, app_with_llm_routes: FastAPI) -> None:
        """Test that adding existing provider returns 400."""
        from ciris_engine.logic.registries.base import Priority, ServiceProvider

        app_with_llm_routes.state.telemetry_service = MagicMock()
        app_with_llm_routes.state.time_service = MagicMock()

        mock_existing = MagicMock(spec=ServiceProvider)
        mock_existing.name = "existing_provider"
        mock_existing.priority = Priority.NORMAL

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ):
            with patch("ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry") as mock_registry:
                mock_reg = MagicMock()
                mock_reg.get_provider_by_name.return_value = mock_existing  # Already exists
                mock_registry.return_value = mock_reg

                client = TestClient(app_with_llm_routes)
                response = client.post(
                    "/system/llm/providers",
                    json={
                        "provider_id": "local",
                        "name": "existing_provider",
                        "base_url": "http://localhost:11434/v1",
                    },
                )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    def test_add_provider_missing_services(self, app_with_llm_routes: FastAPI) -> None:
        """Test that 503 is returned when required services are unavailable."""
        # Don't set telemetry_service and time_service
        app_with_llm_routes.state.telemetry_service = None
        app_with_llm_routes.state.time_service = None

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ):
            client = TestClient(app_with_llm_routes)
            response = client.post(
                "/system/llm/providers",
                json={
                    "provider_id": "local",
                    "name": "test",
                    "base_url": "http://localhost:11434/v1",
                },
            )

        assert response.status_code == 503
        assert "services" in response.json()["detail"].lower()

    def test_add_provider_validates_request(self, app_with_llm_routes: FastAPI) -> None:
        """Test that invalid request body returns 422."""
        app_with_llm_routes.state.telemetry_service = MagicMock()
        app_with_llm_routes.state.time_service = MagicMock()

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ):
            client = TestClient(app_with_llm_routes)
            # Missing required field: base_url
            response = client.post(
                "/system/llm/providers",
                json={
                    "provider_id": "local",
                    # No base_url
                },
            )

        assert response.status_code == 422  # Validation error

    def test_add_provider_with_all_priority_levels(self, app_with_llm_routes: FastAPI) -> None:
        """Test that all priority levels are accepted."""
        app_with_llm_routes.state.telemetry_service = MagicMock()
        app_with_llm_routes.state.time_service = MagicMock()

        priority_levels = ["critical", "high", "normal", "low", "fallback"]

        for priority in priority_levels:
            with patch(
                "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth",
                return_value=True,
            ):
                with patch(
                    "ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry"
                ) as mock_registry:
                    mock_reg = MagicMock()
                    mock_reg.get_provider_by_name.return_value = None
                    mock_registry.return_value = mock_reg

                    with patch(
                        "ciris_engine.logic.services.runtime.llm_service.service.OpenAICompatibleClient"
                    ) as mock_client_class:
                        mock_client = MagicMock()
                        mock_client.start = AsyncMock()  # start() is async
                        mock_client_class.return_value = mock_client

                        client = TestClient(app_with_llm_routes)
                        response = client.post(
                            "/system/llm/providers",
                            json={
                                "provider_id": "local",
                                "name": f"provider_{priority}",
                                "base_url": "http://localhost:11434/v1",
                                "priority": priority,
                            },
                        )

            assert response.status_code == 200, f"Failed for priority: {priority}"
            assert response.json()["data"]["priority"] == priority


# ============================================================================
# Test: CIRIS Services Disable/Enable/Status Endpoints
# ============================================================================


class TestCirisServicesEndpoints:
    """Tests for /system/llm/ciris-services/* endpoints.

    These endpoints control whether CIRIS hosted services are enabled:
    - POST /system/llm/ciris-services/disable - Disable CIRIS services
    - POST /system/llm/ciris-services/enable - Re-enable CIRIS services
    - GET /system/llm/ciris-services/status - Get current status

    Expected behavior:
    - Disable sets CIRIS_SERVICES_DISABLED=true in .env
    - Disable unregisters all CIRIS providers from registry
    - Enable sets CIRIS_SERVICES_DISABLED=false in .env
    - Status returns current disabled state
    """

    def test_disable_ciris_services_success(self, app_with_llm_routes: FastAPI) -> None:
        """Test disabling CIRIS services successfully.

        Expected:
        - Returns 200 with disabled=True
        - Message indicates providers were unregistered
        - set_ciris_services_disabled(True) is called
        - CIRIS providers are unregistered from registry
        """
        from ciris_engine.logic.registries.base import Priority
        from ciris_engine.schemas.runtime.enums import ServiceType

        # Create mock registry with CIRIS providers
        mock_reg = MagicMock()
        ciris_primary = MagicMock()
        ciris_primary.name = "ciris_primary"
        ciris_primary.priority = Priority.HIGH

        ciris_secondary = MagicMock()
        ciris_secondary.name = "ciris_secondary"
        ciris_secondary.priority = Priority.NORMAL

        local_provider = MagicMock()
        local_provider.name = "local_llm"
        local_provider.priority = Priority.FALLBACK

        mock_reg._services = {ServiceType.LLM: [ciris_primary, ciris_secondary, local_provider]}
        mock_reg.unregister.return_value = True

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ), patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry", return_value=mock_reg
        ), patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes.set_ciris_services_disabled", return_value=True
        ) as mock_set_disabled:
            client = TestClient(app_with_llm_routes)
            response = client.post("/system/llm/ciris-services/disable")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["disabled"] is True
        assert "2 provider" in data["message"]  # Should mention 2 CIRIS providers

        # Verify set_ciris_services_disabled was called with True
        mock_set_disabled.assert_called_once_with(True)

        # Verify CIRIS providers were unregistered (but not local_llm)
        assert mock_reg.unregister.call_count == 2
        unregistered_names = [call.args[0] for call in mock_reg.unregister.call_args_list]
        assert "ciris_primary" in unregistered_names
        assert "ciris_secondary" in unregistered_names
        assert "local_llm" not in unregistered_names

    def test_disable_ciris_services_no_providers(self, app_with_llm_routes: FastAPI) -> None:
        """Test disabling when no CIRIS providers exist.

        Expected:
        - Returns 200 with disabled=True
        - Message indicates 0 providers unregistered
        - Flag is still set in .env
        """
        from ciris_engine.schemas.runtime.enums import ServiceType

        mock_reg = MagicMock()
        local_provider = MagicMock()
        local_provider.name = "local_llm"  # Not a CIRIS provider
        mock_reg._services = {ServiceType.LLM: [local_provider]}

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ), patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry", return_value=mock_reg
        ), patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes.set_ciris_services_disabled", return_value=True
        ):
            client = TestClient(app_with_llm_routes)
            response = client.post("/system/llm/ciris-services/disable")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["disabled"] is True
        assert "0 provider" in data["message"]

    def test_disable_ciris_services_persist_fails(self, app_with_llm_routes: FastAPI) -> None:
        """Test when .env persistence fails.

        Expected:
        - Returns 500 error
        - Error message indicates persistence failure
        """
        from ciris_engine.schemas.runtime.enums import ServiceType

        mock_reg = MagicMock()
        mock_reg._services = {ServiceType.LLM: []}

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ), patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes.get_global_registry", return_value=mock_reg
        ), patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes.set_ciris_services_disabled",
            return_value=False,  # Persistence fails
        ):
            client = TestClient(app_with_llm_routes)
            response = client.post("/system/llm/ciris-services/disable")

        assert response.status_code == 500
        assert "persist" in response.json()["detail"].lower()

    def test_enable_ciris_services_success(self, app_with_llm_routes: FastAPI) -> None:
        """Test re-enabling CIRIS services.

        Expected:
        - Returns 200 with disabled=False
        - Message indicates services will be enabled on restart
        - set_ciris_services_disabled(False) is called
        """
        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ), patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes.set_ciris_services_disabled", return_value=True
        ) as mock_set_disabled:
            client = TestClient(app_with_llm_routes)
            response = client.post("/system/llm/ciris-services/enable")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["disabled"] is False
        assert "enabled" in data["message"].lower()
        assert "restart" in data["message"].lower()

        mock_set_disabled.assert_called_once_with(False)

    def test_enable_ciris_services_persist_fails(self, app_with_llm_routes: FastAPI) -> None:
        """Test when enable persistence fails.

        Expected:
        - Returns 500 error
        """
        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ), patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes.set_ciris_services_disabled", return_value=False
        ):
            client = TestClient(app_with_llm_routes)
            response = client.post("/system/llm/ciris-services/enable")

        assert response.status_code == 500

    def test_get_ciris_services_status_disabled(self, app_with_llm_routes: FastAPI) -> None:
        """Test getting status when CIRIS services are disabled.

        Expected:
        - Returns 200 with disabled=True
        - Message indicates disabled state
        """
        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ), patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes.get_ciris_services_disabled", return_value=True
        ):
            client = TestClient(app_with_llm_routes)
            response = client.get("/system/llm/ciris-services/status")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["disabled"] is True
        assert "disabled" in data["message"].lower()

    def test_get_ciris_services_status_enabled(self, app_with_llm_routes: FastAPI) -> None:
        """Test getting status when CIRIS services are enabled.

        Expected:
        - Returns 200 with disabled=False
        - Message indicates enabled state
        """
        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth", return_value=True
        ), patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes.get_ciris_services_disabled", return_value=False
        ):
            client = TestClient(app_with_llm_routes)
            response = client.get("/system/llm/ciris-services/status")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["disabled"] is False
        assert "enabled" in data["message"].lower()

    def test_ciris_services_requires_admin_auth(self, app_with_llm_routes: FastAPI) -> None:
        """Test that CIRIS services endpoints require admin auth when not in setup mode.

        Expected:
        - Returns 401 or 500 (auth infrastructure not available) when not in setup mode
        - Should NOT return 200 (success) without auth
        """
        with patch(
            "ciris_engine.logic.adapters.api.routes.system.llm_routes._is_setup_allowed_without_auth",
            return_value=False,  # Not in setup mode
        ):
            client = TestClient(app_with_llm_routes)

            # All endpoints should require auth - they should NOT succeed (200)
            # In test environment without full auth setup, we get 500 or 401
            response = client.post("/system/llm/ciris-services/disable")
            assert response.status_code in (401, 500)  # Auth required, fails without it

            response = client.post("/system/llm/ciris-services/enable")
            assert response.status_code in (401, 500)

            response = client.get("/system/llm/ciris-services/status")
            assert response.status_code in (401, 500)
