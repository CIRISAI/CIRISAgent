"""
Comprehensive tests for AccordMetricsAdapter — post-LensCore-fold (#866).

Tests cover:
- Initialization with/without consent
- Service registration behavior (UNCONDITIONAL as of 2.9.6 — consent gates
  sharing at the substrate's CEG seal, not registration)
- Consent management (update_consent -> set_consent +
  queue_lens_deletion_on_revoke)
- Configuration and status reporting
- Adapter lifecycle (metrics service start mocked at the substrate seam)
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ciris_adapters.ciris_accord_metrics.adapter import AccordMetricsAdapter, Adapter
from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority_core import DeferralRequest

from .test_accord_metrics_service import FakeLensClient


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


@pytest.fixture(autouse=True)
def _clean_metrics_env(monkeypatch):
    """Keep adapter construction deterministic regardless of the host env."""
    for name in (
        "CONSENT",
        "CONSENT_TIMESTAMP",
        "TRACE_LEVEL",
        "LOCAL_COPY_DIR",
        "FLUSH_INTERVAL",
        "ORPHAN_MAX_AGE",
        "CAPTURE_DEFERRALS",
    ):
        monkeypatch.delenv(f"CIRIS_ACCORD_METRICS_{name}", raising=False)
        monkeypatch.delenv(f"CIRIS_COVENANT_METRICS_{name}", raising=False)


@pytest.fixture
def mock_runtime():
    """Create a mock runtime with agent_id (legacy pattern)."""
    runtime = MagicMock()
    # Set agent_identity to None to trigger legacy fallback to agent_id
    runtime.agent_identity = None
    runtime.agent_id = "test-agent-123"
    return runtime


@pytest.fixture
def mock_runtime_no_agent_id():
    """Create a mock runtime without agent_id attribute."""
    runtime = MagicMock(spec=[])
    runtime.agent_identity = None
    return runtime


@pytest.fixture
def mock_context():
    """Create a mock context with agent_id."""
    context = MagicMock()
    context.agent_id = "context-agent-456"
    return context


def _mock_substrate(adapter: AccordMetricsAdapter) -> FakeLensClient:
    """Patch the REQUIRED substrate seam so adapter.start() succeeds in
    unit tests (the real LensClient needs the persist Engine singleton)."""
    fake = FakeLensClient()
    adapter.metrics_service._build_lens_client = lambda: fake  # type: ignore[method-assign]
    return fake


class TestAccordMetricsAdapterExports:
    """Tests for adapter exports."""

    def test_adapter_alias_export(self):
        """Test Adapter is exported for dynamic loading."""
        assert Adapter is AccordMetricsAdapter

    def test_imports_from_package(self):
        """Test imports from package __init__."""
        from ciris_adapters.ciris_accord_metrics import AccordMetricsAdapter, AccordMetricsService, Adapter

        assert Adapter is AccordMetricsAdapter
        assert AccordMetricsService is not None


class TestAccordMetricsAdapterInit:
    """Tests for adapter initialization."""

    def test_init_without_consent(self, mock_runtime):
        """Test adapter initializes without consent."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        assert adapter._consent_given is False
        assert adapter._consent_timestamp is None
        assert adapter._running is False
        assert adapter.metrics_service is not None

    def test_init_with_consent(self, mock_runtime):
        """Test adapter initializes with consent."""
        adapter = AccordMetricsAdapter(
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
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        # Agent ID should be hashed and set
        assert adapter.metrics_service._agent_id_hash is not None

    def test_init_sets_agent_id_from_context(self, mock_runtime_no_agent_id, mock_context):
        """Test agent ID is set from context if runtime lacks it."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime_no_agent_id,
            context=mock_context,
        )

        assert adapter.metrics_service._agent_id_hash is not None


class TestAccordMetricsAdapterServiceRegistration:
    """Registration is UNCONDITIONAL as of 2.9.6 (#866): the adapter is the
    agent's observability spine. Consent never gated whether the pipeline
    exists — it gates SHARING, enforced by lens-core's CEG consent gate at
    every seal."""

    def test_get_services_without_consent_still_registers(self, mock_runtime):
        """No-consent must NOT suppress registration (capture still runs;
        every seal resolves consent_blocked at the substrate)."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": False},
        )

        registrations = adapter.get_services_to_register()

        assert len(registrations) == 1
        assert registrations[0].service_type == ServiceType.WISE_AUTHORITY

    def test_get_services_with_consent(self, mock_runtime):
        """Test service registered with consent."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        registrations = adapter.get_services_to_register()

        assert len(registrations) == 1
        reg = registrations[0]
        assert reg.service_type == ServiceType.WISE_AUTHORITY
        assert "send_deferral" in reg.capabilities
        assert "accord_metrics" in reg.capabilities

    def test_registration_identical_regardless_of_consent(self, mock_runtime):
        """The registration payload must not vary with consent state."""
        with_consent = AccordMetricsAdapter(
            runtime=mock_runtime, context=None, adapter_config={"consent_given": True}
        ).get_services_to_register()
        without_consent = AccordMetricsAdapter(
            runtime=mock_runtime, context=None, adapter_config={"consent_given": False}
        ).get_services_to_register()

        assert len(with_consent) == len(without_consent) == 1
        assert with_consent[0].service_type == without_consent[0].service_type
        assert with_consent[0].capabilities == without_consent[0].capabilities
        assert with_consent[0].priority == without_consent[0].priority

    def test_service_provider_is_metrics_service(self, mock_runtime):
        """Test registered provider is the metrics service."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        registrations = adapter.get_services_to_register()

        assert registrations[0].provider is adapter.metrics_service


class TestAccordMetricsAdapterConsent:
    """Tests for consent management."""

    def test_is_consent_given_false(self, mock_runtime):
        """Test is_consent_given returns False without consent."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        assert adapter.is_consent_given() is False

    def test_is_consent_given_true(self, mock_runtime):
        """Test is_consent_given returns True with consent."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        assert adapter.is_consent_given() is True

    def test_update_consent_grant(self, mock_runtime):
        """Test granting consent updates state."""
        adapter = AccordMetricsAdapter(
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
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        adapter.update_consent(False)

        assert adapter._consent_given is False
        assert adapter.metrics_service._consent_given is False

    def test_update_consent_calls_set_consent(self, mock_runtime):
        """update_consent must thread state through service.set_consent."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )
        adapter.metrics_service.set_consent = MagicMock()

        adapter.update_consent(True)

        adapter.metrics_service.set_consent.assert_called_once_with(True, adapter._consent_timestamp)

    def test_update_consent_revoke_with_lens_deletion(self, mock_runtime):
        """Revocation with request_lens_deletion=True triggers the DSAR hook
        (log-only post-fold; the CEG recant cascade owns actual deletion)."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )
        adapter.metrics_service.queue_lens_deletion_on_revoke = MagicMock()

        adapter.update_consent(False, request_lens_deletion=True)

        adapter.metrics_service.queue_lens_deletion_on_revoke.assert_called_once()

    def test_update_consent_revoke_without_lens_deletion(self, mock_runtime):
        """Revocation without the flag must NOT trigger the DSAR hook."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )
        adapter.metrics_service.queue_lens_deletion_on_revoke = MagicMock()

        adapter.update_consent(False)

        adapter.metrics_service.queue_lens_deletion_on_revoke.assert_not_called()


class TestAccordMetricsAdapterConfig:
    """Tests for configuration reporting."""

    def test_get_config(self, mock_runtime):
        """Test getting adapter configuration."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={
                "consent_given": True,
                "consent_timestamp": "2025-01-01T00:00:00Z",
            },
        )
        adapter._running = True

        config = adapter.get_config()

        assert config.adapter_type == "ciris_accord_metrics"
        assert config.enabled is True
        assert config.settings["consent_given"] is True
        assert config.settings["consent_timestamp"] == "2025-01-01T00:00:00Z"

    def test_get_config_disabled_without_consent(self, mock_runtime):
        """Test config shows disabled without consent."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )
        adapter._running = True

        config = adapter.get_config()

        assert config.enabled is False

    def test_get_config_includes_metrics(self, mock_runtime):
        """Test config includes event metrics."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        config = adapter.get_config()

        assert "events_received" in config.settings
        assert "events_sent" in config.settings
        assert "events_failed" in config.settings
        # No agent-side queue post-fold — reported as 0
        assert config.settings["events_queued"] == 0


class TestAccordMetricsAdapterStatus:
    """Tests for status reporting."""

    def test_get_status(self, mock_runtime):
        """Test getting adapter status."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )
        adapter._running = True

        status = adapter.get_status()

        assert status.adapter_id == "ciris_accord_metrics"
        assert status.adapter_type == "ciris_accord_metrics"
        assert status.is_running is True
        assert status.config_params is not None

    def test_get_status_not_running(self, mock_runtime):
        """Test status shows not running."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        status = adapter.get_status()

        assert status.is_running is False


class TestAccordMetricsAdapterLifecycle:
    """Tests for adapter lifecycle (start/stop).

    The substrate seam (_build_lens_client) is patched: lens-core is a
    REQUIRED leg in 2.9.6+ and the real client needs the persist Engine
    singleton (see test_lens_fold_integration.py for the real path).
    """

    @pytest.mark.asyncio
    async def test_start_without_consent(self, mock_runtime):
        """Adapter starts without consent — capture runs, seals are
        consent_blocked at the substrate."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )
        fake = _mock_substrate(adapter)

        await adapter.start()

        assert adapter._running is True
        assert adapter._started_at is not None
        assert adapter.metrics_service._lens is fake

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_start_with_consent(self, mock_runtime):
        """Test adapter starts with consent."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )
        fake = _mock_substrate(adapter)

        await adapter.start()

        assert adapter._running is True
        assert adapter.metrics_service._lens is fake

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_start_raises_when_substrate_unavailable(self, mock_runtime, monkeypatch):
        """lens-core is REQUIRED — a missing substrate blocks adapter start
        the same way a missing persist blocks boot."""
        import sys

        monkeypatch.setitem(sys.modules, "ciris_lens_core", None)
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
        )

        with pytest.raises(RuntimeError, match="ciris-lens-core is REQUIRED"):
            await adapter.start()

    @pytest.mark.asyncio
    async def test_stop(self, mock_runtime):
        """Test adapter stops cleanly."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )
        _mock_substrate(adapter)

        await adapter.start()
        await adapter.stop()

        assert adapter._running is False
        assert adapter.metrics_service._reasoning_task.done()
        assert adapter.metrics_service._sweep_task.done()

    @pytest.mark.asyncio
    async def test_run_lifecycle(self, mock_runtime):
        """Test run_lifecycle waits for agent task."""
        adapter = AccordMetricsAdapter(
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
        adapter = AccordMetricsAdapter(
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


class TestAccordMetricsAdapterIntegration:
    """Integration tests for adapter + service."""

    @pytest.mark.asyncio
    async def test_full_wbd_flow_with_consent(self, mock_runtime, monkeypatch):
        """WBD deferrals ride the substrate capture path: DEFERRAL_ROUTED
        joins the deferring thought's in-flight trace ('no second shipping
        mechanism' — #857). Opt-in env: capture is held by default until
        the persist floor ships the variant (CIRISPersist#203)."""
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_CAPTURE_DEFERRALS", "true")
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": True},
        )

        # Get the registered service
        registrations = adapter.get_services_to_register()
        assert len(registrations) == 1

        service = registrations[0].provider
        assert isinstance(service, AccordMetricsService)

        fake = FakeLensClient(outcomes=[{"outcome": "opened"}])
        service._lens = fake

        request = make_deferral_request()
        result = await service.send_deferral(request)

        assert result.startswith(f"wbd-{request.thought_id}-")
        component = fake.captured[0]
        assert component["event_type"] == "DEFERRAL_ROUTED"
        assert component["thought_id"] == request.thought_id
        assert component["task_id"] == request.task_id

    @pytest.mark.asyncio
    async def test_full_flow_without_consent(self, mock_runtime):
        """Without consent the service is STILL registered (capture is
        unconditional); nothing reaches the substrate before start(), and
        post-start every seal is consent_blocked by the CEG gate."""
        adapter = AccordMetricsAdapter(
            runtime=mock_runtime,
            context=None,
            adapter_config={"consent_given": False},
        )

        # Registration is unconditional post-fold
        registrations = adapter.get_services_to_register()
        assert len(registrations) == 1

        # Before start() there is no substrate handle — deferral is a no-op
        # that still returns a deferral id (WiseBus contract).
        request = make_deferral_request()
        result = await adapter.metrics_service.send_deferral(request)

        assert result.startswith(f"wbd-{request.thought_id}-")
        assert adapter.metrics_service._open_thoughts == {}
