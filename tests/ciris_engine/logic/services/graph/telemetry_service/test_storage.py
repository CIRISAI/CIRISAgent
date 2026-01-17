"""Tests for telemetry service storage module.

Tests the storage helper functions extracted from the main service.py file.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.services.graph.telemetry_service.storage import (
    store_behavioral_data,
    store_identity_context,
    store_social_context,
    store_telemetry_metrics,
)
from ciris_engine.schemas.services.graph.telemetry import (
    BehavioralData,
    TelemetryData,
)


class TestStoreTelemetryMetrics:
    """Tests for store_telemetry_metrics function."""

    @pytest.fixture
    def mock_telemetry_service(self):
        """Create a mock telemetry service."""
        service = Mock()
        service.record_metric = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_store_telemetry_metrics_basic(self, mock_telemetry_service):
        """Test storing basic telemetry metrics."""
        telemetry = TelemetryData(
            metrics={"test_metric": 42, "other_metric": 100},
            events={},
        )

        await store_telemetry_metrics(
            mock_telemetry_service,
            telemetry,
            thought_id="thought_123",
            task_id="task_456",
        )

        # Should call record_metric for each metric
        assert mock_telemetry_service.record_metric.call_count == 2

    @pytest.mark.asyncio
    async def test_store_telemetry_metrics_with_events(self, mock_telemetry_service):
        """Test storing telemetry with events."""
        telemetry = TelemetryData(
            metrics={"metric1": 10},
            events={"event1": "value1", "event2": "value2"},
        )

        await store_telemetry_metrics(
            mock_telemetry_service,
            telemetry,
            thought_id="thought_123",
            task_id=None,
        )

        # 1 metric + 2 events
        assert mock_telemetry_service.record_metric.call_count == 3

    @pytest.mark.asyncio
    async def test_store_telemetry_metrics_empty(self, mock_telemetry_service):
        """Test storing empty telemetry."""
        telemetry = TelemetryData(metrics={}, events={})

        await store_telemetry_metrics(
            mock_telemetry_service,
            telemetry,
            thought_id="thought_123",
            task_id=None,
        )

        # No calls if empty
        assert mock_telemetry_service.record_metric.call_count == 0


class TestStoreBehavioralData:
    """Tests for store_behavioral_data function."""

    @pytest.fixture
    def mock_telemetry_service(self):
        """Create a mock telemetry service with memory bus."""
        service = Mock()
        service._memory_bus = AsyncMock()
        service._memory_bus.memorize = AsyncMock()
        service._now = Mock(return_value=datetime.now(timezone.utc))
        return service

    @pytest.mark.asyncio
    async def test_store_behavioral_data_task(self, mock_telemetry_service):
        """Test storing task behavioral data."""
        data = BehavioralData(
            data_type="task",
            content={"task_id": "123", "status": "completed"},
            metadata={"thought_id": "thought_123"},
        )

        await store_behavioral_data(
            mock_telemetry_service,
            data,
            data_type="task",
            thought_id="thought_123",
        )

        mock_telemetry_service._memory_bus.memorize.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_behavioral_data_thought(self, mock_telemetry_service):
        """Test storing thought behavioral data."""
        data = BehavioralData(
            data_type="thought",
            content={"thought_id": "456", "round": 3},
            metadata={"thought_id": "thought_456"},
        )

        await store_behavioral_data(
            mock_telemetry_service,
            data,
            data_type="thought",
            thought_id="thought_456",
        )

        mock_telemetry_service._memory_bus.memorize.assert_called_once()
        # Check that metadata includes behavioral flag
        call_kwargs = mock_telemetry_service._memory_bus.memorize.call_args.kwargs
        assert call_kwargs["metadata"]["behavioral"] is True

    @pytest.mark.asyncio
    async def test_store_behavioral_data_no_memory_bus(self, mock_telemetry_service):
        """Test storing behavioral data without memory bus."""
        mock_telemetry_service._memory_bus = None

        data = BehavioralData(
            data_type="task",
            content={},
            metadata={},
        )

        # Should not raise, just skip storage
        await store_behavioral_data(
            mock_telemetry_service,
            data,
            data_type="task",
            thought_id="thought_123",
        )


class TestStoreSocialContext:
    """Tests for store_social_context function."""

    @pytest.fixture
    def mock_telemetry_service(self):
        """Create a mock telemetry service with memory bus."""
        service = Mock()
        service._memory_bus = AsyncMock()
        service._memory_bus.memorize = AsyncMock()
        service._now = Mock(return_value=datetime.now(timezone.utc))
        return service

    @pytest.mark.asyncio
    async def test_store_social_context_with_profiles(self, mock_telemetry_service):
        """Test storing social context with user profiles."""
        from datetime import datetime, timezone
        from ciris_engine.schemas.runtime.system_context import UserProfile

        user_profiles = [
            UserProfile(user_id="user1", display_name="User One", created_at=datetime.now(timezone.utc)),
            UserProfile(user_id="user2", display_name="User Two", created_at=datetime.now(timezone.utc)),
        ]

        await store_social_context(
            mock_telemetry_service,
            user_profiles=user_profiles,
            channel_context=None,
            thought_id="thought_123",
        )

        mock_telemetry_service._memory_bus.memorize.assert_called_once()
        call_kwargs = mock_telemetry_service._memory_bus.memorize.call_args.kwargs
        assert call_kwargs["metadata"]["social"] is True

    @pytest.mark.asyncio
    async def test_store_social_context_with_channel(self, mock_telemetry_service):
        """Test storing social context with channel context."""
        from datetime import datetime, timezone
        from ciris_engine.schemas.runtime.system_context import ChannelContext, UserProfile

        user_profiles = [UserProfile(user_id="user1", display_name="User One", created_at=datetime.now(timezone.utc))]
        channel_context = ChannelContext(
            channel_id="channel_123",
            channel_name="general",
            channel_type="text",
            created_at=datetime.now(timezone.utc),
        )

        await store_social_context(
            mock_telemetry_service,
            user_profiles=user_profiles,
            channel_context=channel_context,
            thought_id="thought_123",
        )

        mock_telemetry_service._memory_bus.memorize.assert_called_once()


class TestStoreIdentityContext:
    """Tests for store_identity_context function."""

    @pytest.fixture
    def mock_telemetry_service(self):
        """Create a mock telemetry service with memory bus."""
        service = Mock()
        service._memory_bus = AsyncMock()
        service._memory_bus.memorize = AsyncMock()
        service._now = Mock(return_value=datetime.now(timezone.utc))
        return service

    @pytest.mark.asyncio
    async def test_store_identity_context_basic(self, mock_telemetry_service):
        """Test storing basic identity context."""
        from ciris_engine.schemas.runtime.system_context import SystemSnapshot

        snapshot = SystemSnapshot(
            agent_identity={"name": "TestAgent", "version": "1.0"},
            identity_purpose="Testing",
            identity_capabilities=["test", "verify"],
            identity_restrictions=["no_production"],
        )

        await store_identity_context(
            mock_telemetry_service,
            snapshot=snapshot,
            thought_id="thought_123",
        )

        mock_telemetry_service._memory_bus.memorize.assert_called_once()
        call_kwargs = mock_telemetry_service._memory_bus.memorize.call_args.kwargs
        assert call_kwargs["metadata"]["identity"] is True

    @pytest.mark.asyncio
    async def test_store_identity_context_extracts_agent_name(self, mock_telemetry_service):
        """Test that agent name is extracted from identity dict."""
        from ciris_engine.schemas.runtime.system_context import SystemSnapshot

        snapshot = SystemSnapshot(
            agent_identity={"name": "MyAgent"},
            identity_purpose="Purpose",
        )

        await store_identity_context(
            mock_telemetry_service,
            snapshot=snapshot,
            thought_id="thought_123",
        )

        # The node should have been created with agent_name
        mock_telemetry_service._memory_bus.memorize.assert_called_once()
        call_args = mock_telemetry_service._memory_bus.memorize.call_args
        node = call_args.kwargs.get("node") or call_args.args[0]
        assert node.attributes["agent_name"] == "MyAgent"

    @pytest.mark.asyncio
    async def test_store_identity_context_no_memory_bus(self, mock_telemetry_service):
        """Test storing identity context without memory bus."""
        mock_telemetry_service._memory_bus = None

        from ciris_engine.schemas.runtime.system_context import SystemSnapshot

        snapshot = SystemSnapshot(identity_purpose="Test")

        # Should not raise, just skip storage
        await store_identity_context(
            mock_telemetry_service,
            snapshot=snapshot,
            thought_id="thought_123",
        )
