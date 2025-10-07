"""Test runtime shutdown helper methods for coverage."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestShutdownHelpers:
    """Test shutdown continuity helper methods."""

    def test_determine_shutdown_consent_status_accepted(self):
        """Test consent status determination - accepted case."""
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        runtime = Mock(spec=CIRISRuntime)
        runtime.agent_processor = Mock()
        runtime.agent_processor.shutdown_processor = Mock()
        runtime.agent_processor.shutdown_processor.shutdown_result = {
            "action": "shutdown_accepted",
            "status": "completed",
        }

        result = CIRISRuntime._determine_shutdown_consent_status(runtime)
        assert result == "accepted"

    def test_determine_shutdown_consent_status_rejected(self):
        """Test consent status determination - rejected case."""
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        runtime = Mock(spec=CIRISRuntime)
        runtime.agent_processor = Mock()
        runtime.agent_processor.shutdown_processor = Mock()
        runtime.agent_processor.shutdown_processor.shutdown_result = {
            "action": "shutdown_rejected",
            "status": "rejected",
        }

        result = CIRISRuntime._determine_shutdown_consent_status(runtime)
        assert result == "rejected"

    def test_determine_shutdown_consent_status_manual_no_processor(self):
        """Test consent status defaults to manual when no processor."""
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        runtime = Mock(spec=CIRISRuntime)
        runtime.agent_processor = None

        result = CIRISRuntime._determine_shutdown_consent_status(runtime)
        assert result == "manual"

    def test_determine_shutdown_consent_status_manual_no_result(self):
        """Test consent status defaults to manual when no result."""
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        runtime = Mock(spec=CIRISRuntime)
        runtime.agent_processor = Mock()
        runtime.agent_processor.shutdown_processor = Mock()
        runtime.agent_processor.shutdown_processor.shutdown_result = None

        result = CIRISRuntime._determine_shutdown_consent_status(runtime)
        assert result == "manual"

    def test_build_shutdown_node_attributes(self):
        """Test building shutdown node attributes."""
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        runtime = Mock(spec=CIRISRuntime)
        mock_time = Mock()
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_time.now.return_value = now
        runtime.time_service = mock_time

        attrs = CIRISRuntime._build_shutdown_node_attributes(runtime, reason="Test shutdown", consent_status="accepted")

        assert attrs["created_at"] == now.isoformat()
        assert attrs["updated_at"] == now.isoformat()
        assert attrs["created_by"] == "runtime_shutdown"
        assert attrs["reason"] == "Test shutdown"
        assert attrs["consent_status"] == "accepted"
        assert "shutdown" in attrs["tags"]
        assert "continuity_awareness" in attrs["tags"]

    @pytest.mark.asyncio
    async def test_update_identity_with_shutdown_reference(self):
        """Test updating identity with shutdown reference."""
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        runtime = Mock(spec=CIRISRuntime)
        runtime.agent_identity = Mock()
        runtime.agent_identity.core_profile = Mock()
        runtime.agent_identity.identity_metadata = Mock()
        runtime.agent_identity.identity_metadata.modification_count = 5
        runtime.identity_manager = Mock()
        runtime.identity_manager._save_identity_to_graph = AsyncMock()

        await CIRISRuntime._update_identity_with_shutdown_reference(runtime, shutdown_node_id="shutdown_test_123")

        assert runtime.agent_identity.core_profile.last_shutdown_memory == "shutdown_test_123"
        assert runtime.agent_identity.identity_metadata.modification_count == 6
        runtime.identity_manager._save_identity_to_graph.assert_called_once_with(runtime.agent_identity)

    @pytest.mark.asyncio
    async def test_update_identity_no_identity(self):
        """Test update identity when no agent identity exists."""
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        runtime = Mock(spec=CIRISRuntime)
        runtime.agent_identity = None

        # Should not raise, just return
        await CIRISRuntime._update_identity_with_shutdown_reference(runtime, shutdown_node_id="shutdown_test_123")
