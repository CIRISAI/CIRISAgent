"""Tests for shutdown_continuity.py module."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock


class TestShutdownContinuity:
    """Tests for shutdown continuity helpers."""

    def test_determine_shutdown_consent_status_accepted(self) -> None:
        """Test detecting accepted shutdown."""
        from ciris_engine.logic.runtime.shutdown_continuity import determine_shutdown_consent_status

        runtime = MagicMock()
        runtime.agent_processor.shutdown_processor.shutdown_result.action = "shutdown_accepted"

        result = determine_shutdown_consent_status(runtime)
        assert result == "accepted"

    def test_determine_shutdown_consent_status_rejected(self) -> None:
        """Test detecting rejected shutdown."""
        from ciris_engine.logic.runtime.shutdown_continuity import determine_shutdown_consent_status

        runtime = MagicMock()
        runtime.agent_processor.shutdown_processor.shutdown_result.action = "shutdown_rejected"
        runtime.agent_processor.shutdown_processor.shutdown_result.status = "rejected"

        result = determine_shutdown_consent_status(runtime)
        assert result == "rejected"

    def test_determine_shutdown_consent_status_manual(self) -> None:
        """Test detecting manual shutdown when no processor."""
        from ciris_engine.logic.runtime.shutdown_continuity import determine_shutdown_consent_status

        runtime = MagicMock()
        runtime.agent_processor = None

        result = determine_shutdown_consent_status(runtime)
        assert result == "manual"

    def test_build_shutdown_node_attributes(self) -> None:
        """Test building shutdown node attributes."""
        from ciris_engine.logic.runtime.shutdown_continuity import build_shutdown_node_attributes

        runtime = MagicMock()
        mock_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        runtime.time_service.now.return_value = mock_time

        attrs = build_shutdown_node_attributes(runtime, "test reason", "accepted")

        assert attrs["created_by"] == "runtime_shutdown"
        assert attrs["reason"] == "test reason"
        assert attrs["consent_status"] == "accepted"
        assert "shutdown" in attrs["tags"]
        assert "continuity_awareness" in attrs["tags"]

    def test_build_shutdown_node_attributes_no_time_service(self) -> None:
        """Test building attributes when time service is unavailable."""
        from ciris_engine.logic.runtime.shutdown_continuity import build_shutdown_node_attributes

        runtime = MagicMock()
        runtime.time_service = None

        attrs = build_shutdown_node_attributes(runtime, "test reason", "manual")

        assert attrs["created_by"] == "runtime_shutdown"
        assert "created_at" in attrs
        assert "updated_at" in attrs

    @pytest.mark.asyncio
    async def test_update_identity_with_shutdown_reference(self) -> None:
        """Test updating identity with shutdown reference."""
        from ciris_engine.logic.runtime.shutdown_continuity import update_identity_with_shutdown_reference

        runtime = MagicMock()
        runtime.agent_identity.core_profile = MagicMock()
        runtime.agent_identity.identity_metadata.modification_count = 0
        runtime.identity_manager._save_identity_to_graph = AsyncMock()

        await update_identity_with_shutdown_reference(runtime, "shutdown_12345")

        assert runtime.agent_identity.core_profile.last_shutdown_memory == "shutdown_12345"
        assert runtime.agent_identity.identity_metadata.modification_count == 1
        runtime.identity_manager._save_identity_to_graph.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_startup_node(self) -> None:
        """Test creating startup continuity node."""
        from ciris_engine.logic.runtime.shutdown_continuity import create_startup_node

        runtime = MagicMock()
        runtime.memory_service = AsyncMock()
        mock_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        runtime.time_service.now.return_value = mock_time

        await create_startup_node(runtime)

        runtime.memory_service.memorize.assert_called_once()
        # Verify the node has correct attributes
        call_args = runtime.memory_service.memorize.call_args
        node = call_args[0][0]
        assert node.attributes["created_by"] == "runtime_startup"
        assert "startup" in node.attributes["tags"]

    @pytest.mark.asyncio
    async def test_preserve_shutdown_continuity(self) -> None:
        """Test preserving shutdown continuity."""
        from ciris_engine.logic.runtime.shutdown_continuity import preserve_shutdown_continuity

        runtime = MagicMock()
        runtime.memory_service = AsyncMock()
        runtime._shutdown_reason = "Test shutdown"
        runtime.agent_processor = None  # Manual shutdown
        mock_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        runtime.time_service.now.return_value = mock_time

        await preserve_shutdown_continuity(runtime)

        runtime.memory_service.memorize.assert_called_once()
