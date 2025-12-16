"""
Comprehensive tests for CovenantMetricsService.

Tests cover:
- Initialization with various configs
- Consent state handling
- Agent ID anonymization
- Event queuing (with/without consent)
- WBD event handling
- PDMA decision recording
- Metrics collection
- Service lifecycle
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_adapters.ciris_covenant_metrics.services import CovenantMetricsService, SimpleCapabilities
from ciris_engine.schemas.services.authority_core import DeferralRequest


def make_deferral_request(
    thought_id: str = "thought-123",
    task_id: str = "task-456",
    reason: str = "Test reason",
    defer_until: datetime = None,
) -> DeferralRequest:
    """Helper to create DeferralRequest with defaults."""
    if defer_until is None:
        defer_until = datetime.now(timezone.utc)
    return DeferralRequest(
        thought_id=thought_id,
        task_id=task_id,
        reason=reason,
        defer_until=defer_until,
    )


class TestSimpleCapabilities:
    """Tests for SimpleCapabilities dataclass."""

    def test_simple_capabilities_creation(self):
        """Test creating SimpleCapabilities."""
        caps = SimpleCapabilities(
            actions=["send_deferral", "covenant_metrics"],
            scopes=["covenant_compliance"],
        )
        assert caps.actions == ["send_deferral", "covenant_metrics"]
        assert caps.scopes == ["covenant_compliance"]

    def test_simple_capabilities_empty(self):
        """Test creating empty SimpleCapabilities."""
        caps = SimpleCapabilities(actions=[], scopes=[])
        assert caps.actions == []
        assert caps.scopes == []


class TestCovenantMetricsServiceInit:
    """Tests for CovenantMetricsService initialization."""

    def test_default_initialization(self):
        """Test service initializes with defaults."""
        service = CovenantMetricsService()

        assert service._consent_given is False
        assert service._consent_timestamp is None
        assert service._endpoint_url == "https://lens.ciris.ai/v1"
        assert service._batch_size == 10
        assert service._flush_interval == 60.0
        assert service._events_received == 0
        assert service._events_sent == 0
        assert service._events_failed == 0

    def test_initialization_with_consent(self):
        """Test service initializes with consent."""
        config = {
            "consent_given": True,
            "consent_timestamp": "2025-01-01T00:00:00Z",
        }
        service = CovenantMetricsService(config=config)

        assert service._consent_given is True
        assert service._consent_timestamp == "2025-01-01T00:00:00Z"

    def test_initialization_with_custom_endpoint(self):
        """Test service initializes with custom endpoint."""
        config = {
            "endpoint_url": "https://custom.lens.ai/v1",
        }
        service = CovenantMetricsService(config=config)

        assert service._endpoint_url == "https://custom.lens.ai/v1"

    def test_initialization_with_custom_batch_settings(self):
        """Test service initializes with custom batch settings."""
        config = {
            "batch_size": 50,
            "flush_interval_seconds": 120.0,
        }
        service = CovenantMetricsService(config=config)

        assert service._batch_size == 50
        assert service._flush_interval == 120.0

    def test_initialization_with_string_batch_size(self):
        """Test service handles string batch_size."""
        config = {
            "batch_size": "25",
        }
        service = CovenantMetricsService(config=config)

        assert service._batch_size == 25

    def test_initialization_with_invalid_batch_size(self):
        """Test service handles invalid batch_size."""
        config = {
            "batch_size": [1, 2, 3],  # Invalid type
        }
        service = CovenantMetricsService(config=config)

        # Should use default
        assert service._batch_size == 10


class TestCovenantMetricsServiceCapabilities:
    """Tests for service capabilities."""

    def test_get_capabilities(self):
        """Test getting service capabilities."""
        service = CovenantMetricsService()
        caps = service.get_capabilities()

        assert isinstance(caps, SimpleCapabilities)
        assert "send_deferral" in caps.actions
        assert "covenant_metrics" in caps.actions
        assert "covenant_compliance" in caps.scopes


class TestCovenantMetricsServiceAnonymization:
    """Tests for agent ID anonymization."""

    def test_anonymize_agent_id(self):
        """Test agent ID is properly anonymized."""
        service = CovenantMetricsService()

        hashed = service._anonymize_agent_id("test-agent-123")

        # Should be 16 character hex string
        assert len(hashed) == 16
        assert all(c in "0123456789abcdef" for c in hashed)

    def test_anonymize_same_id_consistent(self):
        """Test same ID produces consistent hash."""
        service = CovenantMetricsService()

        hash1 = service._anonymize_agent_id("test-agent-123")
        hash2 = service._anonymize_agent_id("test-agent-123")

        assert hash1 == hash2

    def test_anonymize_different_ids_different_hashes(self):
        """Test different IDs produce different hashes."""
        service = CovenantMetricsService()

        hash1 = service._anonymize_agent_id("agent-1")
        hash2 = service._anonymize_agent_id("agent-2")

        assert hash1 != hash2

    def test_set_agent_id(self):
        """Test setting agent ID."""
        service = CovenantMetricsService()

        service.set_agent_id("my-agent")

        assert service._agent_id_hash is not None
        assert len(service._agent_id_hash) == 16


class TestCovenantMetricsServiceConsent:
    """Tests for consent management."""

    def test_set_consent_granted(self):
        """Test granting consent."""
        service = CovenantMetricsService()

        service.set_consent(True, "2025-01-01T12:00:00Z")

        assert service._consent_given is True
        assert service._consent_timestamp == "2025-01-01T12:00:00Z"

    def test_set_consent_revoked(self):
        """Test revoking consent."""
        service = CovenantMetricsService(config={"consent_given": True})

        service.set_consent(False, "2025-01-01T13:00:00Z")

        assert service._consent_given is False
        assert service._consent_timestamp == "2025-01-01T13:00:00Z"

    def test_set_consent_without_timestamp(self):
        """Test setting consent without timestamp generates one."""
        service = CovenantMetricsService()

        service.set_consent(True)

        assert service._consent_given is True
        assert service._consent_timestamp is not None


class TestCovenantMetricsServiceEventQueue:
    """Tests for event queuing."""

    @pytest.mark.asyncio
    async def test_queue_event_without_consent_drops(self):
        """Test events are dropped without consent."""
        service = CovenantMetricsService()  # No consent

        await service._queue_event({"test": "event"})

        assert len(service._event_queue) == 0
        assert service._events_received == 0

    @pytest.mark.asyncio
    async def test_queue_event_with_consent(self):
        """Test events are queued with consent."""
        service = CovenantMetricsService(config={"consent_given": True})

        await service._queue_event({"test": "event"})

        assert len(service._event_queue) == 1
        assert service._events_received == 1

    @pytest.mark.asyncio
    async def test_queue_multiple_events(self):
        """Test multiple events queue correctly."""
        service = CovenantMetricsService(config={"consent_given": True})

        for i in range(5):
            await service._queue_event({"event": i})

        assert len(service._event_queue) == 5
        assert service._events_received == 5


class TestCovenantMetricsServiceWBDEvents:
    """Tests for WBD event handling via send_deferral."""

    @pytest.mark.asyncio
    async def test_send_deferral_with_consent(self):
        """Test receiving WBD deferral events with consent."""
        service = CovenantMetricsService(config={"consent_given": True})
        service.set_agent_id("test-agent")

        request = make_deferral_request(
            thought_id="thought-123",
            task_id="task-456",
            reason="Ethical uncertainty - needs human wisdom",
        )

        result = await service.send_deferral(request)

        assert "WBD event recorded" in result
        assert len(service._event_queue) == 1

        event = service._event_queue[0]
        assert event["event_type"] == "wbd_deferral"
        assert event["thought_id"] == "thought-123"
        assert event["task_id"] == "task-456"
        assert event["reason"] == "Ethical uncertainty - needs human wisdom"

    @pytest.mark.asyncio
    async def test_send_deferral_without_consent(self):
        """Test WBD events are dropped without consent."""
        service = CovenantMetricsService()  # No consent

        request = make_deferral_request()

        result = await service.send_deferral(request)

        assert "WBD event recorded" in result
        assert len(service._event_queue) == 0  # Dropped

    @pytest.mark.asyncio
    async def test_send_deferral_truncates_long_reason(self):
        """Test long reasons are truncated."""
        service = CovenantMetricsService(config={"consent_given": True})

        long_reason = "x" * 500  # Much longer than 200 char limit

        request = make_deferral_request(reason=long_reason)

        await service.send_deferral(request)

        event = service._event_queue[0]
        assert len(event["reason"]) == 200

    @pytest.mark.asyncio
    async def test_send_deferral_with_defer_until(self):
        """Test WBD event with defer_until timestamp."""
        service = CovenantMetricsService(config={"consent_given": True})

        defer_time = datetime.now(timezone.utc)
        request = make_deferral_request(
            thought_id="thought-123",
            task_id="task-456",
            reason="Test",
            defer_until=defer_time,
        )

        await service.send_deferral(request)

        event = service._event_queue[0]
        assert event["defer_until"] == defer_time.isoformat()


class TestCovenantMetricsServicePDMAEvents:
    """Tests for PDMA decision event recording."""

    @pytest.mark.asyncio
    async def test_record_pdma_decision(self):
        """Test recording PDMA decision."""
        service = CovenantMetricsService(config={"consent_given": True})
        service.set_agent_id("test-agent")

        await service.record_pdma_decision(
            thought_id="thought-123",
            selected_action="SPEAK",
            rationale="User requested information",
            reasoning_summary="Short reasoning",
        )

        assert len(service._event_queue) == 1

        event = service._event_queue[0]
        assert event["event_type"] == "pdma_decision"
        assert event["thought_id"] == "thought-123"
        assert event["selected_action"] == "SPEAK"
        assert event["rationale"] == "User requested information"
        assert event["reasoning_summary"] == "Short reasoning"

    @pytest.mark.asyncio
    async def test_record_pdma_decision_truncates(self):
        """Test PDMA decision truncates long fields."""
        service = CovenantMetricsService(config={"consent_given": True})

        long_rationale = "r" * 300
        long_summary = "s" * 700

        await service.record_pdma_decision(
            thought_id="thought-123",
            selected_action="DEFER",
            rationale=long_rationale,
            reasoning_summary=long_summary,
        )

        event = service._event_queue[0]
        assert len(event["rationale"]) == 200
        assert len(event["reasoning_summary"]) == 500


class TestCovenantMetricsServiceStubMethods:
    """Tests for stub methods (fetch_guidance, get_guidance)."""

    @pytest.mark.asyncio
    async def test_fetch_guidance_returns_none(self):
        """Test fetch_guidance returns None."""
        service = CovenantMetricsService()

        result = await service.fetch_guidance({})

        assert result is None

    @pytest.mark.asyncio
    async def test_get_guidance_returns_empty(self):
        """Test get_guidance returns empty guidance."""
        service = CovenantMetricsService()

        result = await service.get_guidance("test question")

        assert result["guidance"] is None
        assert result["confidence"] == 0.0
        assert result["source"] == "covenant_metrics"


class TestCovenantMetricsServiceMetrics:
    """Tests for metrics collection."""

    def test_get_metrics_initial(self):
        """Test initial metrics."""
        service = CovenantMetricsService()

        metrics = service.get_metrics()

        assert metrics["consent_given"] is False
        assert metrics["events_received"] == 0
        assert metrics["events_sent"] == 0
        assert metrics["events_failed"] == 0
        assert metrics["events_queued"] == 0
        assert metrics["last_send_time"] is None

    @pytest.mark.asyncio
    async def test_get_metrics_after_events(self):
        """Test metrics after queuing events."""
        service = CovenantMetricsService(config={"consent_given": True})

        await service._queue_event({"test": 1})
        await service._queue_event({"test": 2})

        metrics = service.get_metrics()

        assert metrics["consent_given"] is True
        assert metrics["events_received"] == 2
        assert metrics["events_queued"] == 2


class TestCovenantMetricsServiceLifecycle:
    """Tests for service lifecycle (start/stop)."""

    @pytest.mark.asyncio
    async def test_start_without_consent(self):
        """Test service starts but doesn't initialize HTTP without consent."""
        service = CovenantMetricsService()

        await service.start()

        assert service._session is None
        assert service._flush_task is None

    @pytest.mark.asyncio
    async def test_start_with_consent(self):
        """Test service starts and initializes HTTP with consent."""
        service = CovenantMetricsService(config={"consent_given": True})

        await service.start()

        assert service._session is not None
        assert service._flush_task is not None

        # Cleanup
        await service.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_session(self):
        """Test stop closes HTTP session."""
        service = CovenantMetricsService(config={"consent_given": True})

        await service.start()
        assert service._session is not None

        await service.stop()
        assert service._session is None

    @pytest.mark.asyncio
    async def test_stop_cancels_flush_task(self):
        """Test stop cancels periodic flush task."""
        service = CovenantMetricsService(config={"consent_given": True})

        await service.start()
        flush_task = service._flush_task
        assert flush_task is not None

        await service.stop()
        assert flush_task.cancelled() or flush_task.done()


class TestCovenantMetricsServiceFlush:
    """Tests for event flushing."""

    @pytest.mark.asyncio
    async def test_flush_without_consent_noop(self):
        """Test flush does nothing without consent."""
        service = CovenantMetricsService()
        service._event_queue = [{"test": 1}]

        await service._flush_events()

        # Queue unchanged
        assert len(service._event_queue) == 1

    @pytest.mark.asyncio
    async def test_flush_without_session_noop(self):
        """Test flush does nothing without HTTP session."""
        service = CovenantMetricsService(config={"consent_given": True})
        # Don't call start() so no session
        service._event_queue = [{"test": 1}]

        await service._flush_events()

        # Queue unchanged
        assert len(service._event_queue) == 1

    @pytest.mark.asyncio
    async def test_flush_empty_queue_noop(self):
        """Test flush does nothing with empty queue."""
        service = CovenantMetricsService(config={"consent_given": True})
        await service.start()

        initial_sent = service._events_sent

        await service._flush_events()

        assert service._events_sent == initial_sent

        await service.stop()

    @pytest.mark.asyncio
    async def test_batch_triggers_at_threshold(self):
        """Test batch sends when threshold reached."""
        service = CovenantMetricsService(
            config={
                "consent_given": True,
                "batch_size": 3,
            }
        )

        # Mock the send method to avoid actual HTTP
        service._send_events_batch = AsyncMock()
        service._session = MagicMock()  # Fake session

        # Queue events up to threshold
        await service._queue_event({"event": 1})
        await service._queue_event({"event": 2})

        # Not sent yet
        service._send_events_batch.assert_not_called()

        # Third event triggers send
        await service._queue_event({"event": 3})

        service._send_events_batch.assert_called_once()
        assert service._events_sent == 3
