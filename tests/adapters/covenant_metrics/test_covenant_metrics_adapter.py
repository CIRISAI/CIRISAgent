"""
Comprehensive tests for CovenantMetricsAdapter.

Tests cover:
- Initialization with/without consent
- Service registration behavior
- Consent management
- Configuration and status reporting
- Adapter lifecycle
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_adapters.ciris_covenant_metrics.adapter import Adapter, CovenantMetricsAdapter
from ciris_adapters.ciris_covenant_metrics.services import CovenantMetricsService
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority_core import DeferralRequest


def make_deferral_request(
    thought_id: str = "thought-1",
    task_id: str = "task-1",
    reason: str = "Test deferral",
) -> DeferralRequest:
    """Helper to create DeferralRequest with defaults."""
    return DeferralRequest(
        thought_id=thought_id,
        task_id=task_id,
        reason=reason,
        defer_until=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_runtime():
    """Create a mock runtime with agent_id."""
    runtime = MagicMock()
    runtime.agent_id = "test-agent-123"
    return runtime


@pytest.fixture
def mock_runtime_no_agent_id():
    """Create a mock runtime without agent_id attribute."""
    return MagicMock(spec=[])


@pytest.fixture
def mock_context():
    """Create a mock context with agent_id."""
    context = MagicMock()
    context.agent_id = "context-agent-456"
    return context


class TestCovenantMetricsAdapterExports:
    """Tests for adapter exports."""

    def test_adapter_alias_export(self):
        """Test Adapter is exported for dynamic loading."""
        assert Adapter is CovenantMetricsAdapter

    def test_imports_from_package(self):
        """Test imports from package __init__."""
        from ciris_adapters.ciris_covenant_metrics import Adapter, CovenantMetricsAdapter, CovenantMetricsService

        assert Adapter is CovenantMetricsAdapter
        assert CovenantMetricsService is not None


class TestCovenantMetricsAdapterInit:
    """Tests for adapter initialization."""

    def test_init_without_consent(self, mock_runtime):
        """Test adapter initializes without consent."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        assert adapter._consent_given is False
        assert adapter._consent_timestamp is None
        assert adapter._running is False
        assert adapter.metrics_service is not None

    def test_init_with_consent(self, mock_runtime):
        """Test adapter initializes with consent."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={
                "consent_given": True,
                "consent_timestamp": "2025-01-01T00:00:00Z",
            },
        )

        assert adapter._consent_given is True
        assert adapter._consent_timestamp == "2025-01-01T00:00:00Z"

    def test_init_sets_agent_id_from_runtime(self, mock_runtime):
        """Test agent ID is set from runtime."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        # Agent ID should be hashed and set
        assert adapter.metrics_service._agent_id_hash is not None

    def test_init_sets_agent_id_from_context(self, mock_runtime_no_agent_id, mock_context):
        """Test agent ID is set from context if runtime lacks it."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime_no_agent_id,
            context=mock_context,
        )

        assert adapter.metrics_service._agent_id_hash is not None


class TestCovenantMetricsAdapterServiceRegistration:
    """Tests for service registration behavior."""

    def test_get_services_without_consent(self, mock_runtime):
        """Test no services registered without consent."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": False},
        )

        registrations = adapter.get_services_to_register()

        assert len(registrations) == 0

    def test_get_services_with_consent(self, mock_runtime):
        """Test service registered with consent."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        registrations = adapter.get_services_to_register()

        assert len(registrations) == 1
        reg = registrations[0]
        assert reg.service_type == ServiceType.WISE_AUTHORITY
        assert "send_deferral" in reg.capabilities
        assert "covenant_metrics" in reg.capabilities

    def test_service_provider_is_metrics_service(self, mock_runtime):
        """Test registered provider is the metrics service."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        registrations = adapter.get_services_to_register()

        assert registrations[0].provider is adapter.metrics_service


class TestCovenantMetricsAdapterConsent:
    """Tests for consent management."""

    def test_is_consent_given_false(self, mock_runtime):
        """Test is_consent_given returns False without consent."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        assert adapter.is_consent_given() is False

    def test_is_consent_given_true(self, mock_runtime):
        """Test is_consent_given returns True with consent."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        assert adapter.is_consent_given() is True

    def test_update_consent_grant(self, mock_runtime):
        """Test granting consent updates state."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        assert adapter._consent_given is False

        adapter.update_consent(True)

        assert adapter._consent_given is True
        assert adapter._consent_timestamp is not None
        # Service should also be updated
        assert adapter.metrics_service._consent_given is True

    def test_update_consent_revoke(self, mock_runtime):
        """Test revoking consent updates state."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        adapter.update_consent(False)

        assert adapter._consent_given is False
        assert adapter.metrics_service._consent_given is False


class TestCovenantMetricsAdapterConfig:
    """Tests for configuration reporting."""

    def test_get_config(self, mock_runtime):
        """Test getting adapter configuration."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={
                "consent_given": True,
                "consent_timestamp": "2025-01-01T00:00:00Z",
            },
        )
        adapter._running = True

        config = adapter.get_config()

        assert config.adapter_type == "ciris_covenant_metrics"
        assert config.enabled is True
        assert config.settings["consent_given"] is True
        assert config.settings["consent_timestamp"] == "2025-01-01T00:00:00Z"

    def test_get_config_disabled_without_consent(self, mock_runtime):
        """Test config shows disabled without consent."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )
        adapter._running = True

        config = adapter.get_config()

        assert config.enabled is False

    def test_get_config_includes_metrics(self, mock_runtime):
        """Test config includes event metrics."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        config = adapter.get_config()

        assert "events_received" in config.settings
        assert "events_sent" in config.settings
        assert "events_failed" in config.settings
        assert "events_queued" in config.settings


class TestCovenantMetricsAdapterStatus:
    """Tests for status reporting."""

    def test_get_status(self, mock_runtime):
        """Test getting adapter status."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )
        adapter._running = True

        status = adapter.get_status()

        assert status.adapter_id == "ciris_covenant_metrics"
        assert status.adapter_type == "ciris_covenant_metrics"
        assert status.is_running is True
        assert status.config_params is not None

    def test_get_status_not_running(self, mock_runtime):
        """Test status shows not running."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        status = adapter.get_status()

        assert status.is_running is False


class TestCovenantMetricsAdapterLifecycle:
    """Tests for adapter lifecycle (start/stop)."""

    @pytest.mark.asyncio
    async def test_start_without_consent(self, mock_runtime):
        """Test adapter starts without consent."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        await adapter.start()

        assert adapter._running is True
        assert adapter._started_at is not None

    @pytest.mark.asyncio
    async def test_start_with_consent(self, mock_runtime):
        """Test adapter starts with consent."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        await adapter.start()

        assert adapter._running is True
        # Service should have HTTP session
        assert adapter.metrics_service._session is not None

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_stop(self, mock_runtime):
        """Test adapter stops cleanly."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        await adapter.start()
        await adapter.stop()

        assert adapter._running is False
        assert adapter.metrics_service._session is None

    @pytest.mark.asyncio
    async def test_run_lifecycle(self, mock_runtime):
        """Test run_lifecycle waits for agent task."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        # Create a task that completes quickly
        async def quick_task():
            await asyncio.sleep(0.01)

        agent_task = asyncio.create_task(quick_task())

        await adapter.run_lifecycle(agent_task)

        # Adapter should have stopped after task completed
        assert adapter._running is False

    @pytest.mark.asyncio
    async def test_run_lifecycle_handles_cancellation(self, mock_runtime):
        """Test run_lifecycle handles cancellation gracefully."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        # Create a long-running task
        async def long_task():
            await asyncio.sleep(100)

        agent_task = asyncio.create_task(long_task())

        # Start lifecycle in background
        lifecycle_task = asyncio.create_task(adapter.run_lifecycle(agent_task))

        # Give it a moment to start
        await asyncio.sleep(0.01)

        # Cancel the agent task
        agent_task.cancel()

        # Wait for lifecycle to complete
        await lifecycle_task

        assert adapter._running is False


class TestCovenantMetricsAdapterIntegration:
    """Integration tests for adapter + service."""

    @pytest.mark.asyncio
    async def test_full_wbd_flow_with_consent(self, mock_runtime):
        """Test full WBD event flow with consent."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        # Get the registered service
        registrations = adapter.get_services_to_register()
        assert len(registrations) == 1

        service = registrations[0].provider
        assert isinstance(service, CovenantMetricsService)

        # Service should receive WBD events
        request = make_deferral_request()

        result = await service.send_deferral(request)

        assert "WBD event recorded" in result
        assert len(service._event_queue) == 1

    @pytest.mark.asyncio
    async def test_full_flow_without_consent(self, mock_runtime):
        """Test flow without consent doesn't leak data."""
        adapter = CovenantMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": False},
        )

        # No services registered
        registrations = adapter.get_services_to_register()
        assert len(registrations) == 0

        # Direct service access also blocks events
        request = make_deferral_request()

        await adapter.metrics_service.send_deferral(request)

        # Event dropped
        assert len(adapter.metrics_service._event_queue) == 0
