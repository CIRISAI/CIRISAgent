"""
Unit tests for error metric tracking in handlers.
"""

import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies, BaseActionHandler
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType


class TestErrorMetricTracking(unittest.TestCase):
    """Test error metric tracking functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock dependencies
        self.mock_bus_manager = MagicMock()
        self.mock_memory_bus = AsyncMock()
        self.mock_bus_manager.memory_bus = self.mock_memory_bus

        self.mock_time_service = MagicMock()
        self.mock_time_service.now.return_value = datetime(2025, 1, 16, 12, 0, 0)

        self.dependencies = ActionHandlerDependencies(
            bus_manager=self.mock_bus_manager,
            time_service=self.mock_time_service,
        )

        # Create a test handler class
        class TestHandler(BaseActionHandler):
            async def execute(self, *args, **kwargs):
                pass

        self.handler = TestHandler(self.dependencies)

    @pytest.mark.asyncio
    async def test_handle_error_tracks_metric(self):
        """Test that _handle_error tracks error.occurred metric."""
        # Create test context
        dispatch_context = DispatchContext(
            agent_id="test_agent",
            user_id="test_user",
            channel_id="test_channel",
        )

        # Create test error
        test_error = ValueError("Test error message")

        # Mock audit log to prevent actual logging
        with patch.object(self.handler, "_audit_log", new_callable=AsyncMock):
            # Call _handle_error
            await self.handler._handle_error(
                action_type=HandlerActionType.SPEAK,
                dispatch_context=dispatch_context,
                thought_id="test_thought_123",
                error=test_error,
            )

        # Verify memorize_metric was called
        self.mock_memory_bus.memorize_metric.assert_called_once()

        # Verify the metric details
        call_args = self.mock_memory_bus.memorize_metric.call_args
        self.assertEqual(call_args.kwargs["metric_name"], "error.occurred")
        self.assertEqual(call_args.kwargs["value"], 1.0)

        # Verify tags
        tags = call_args.kwargs["tags"]
        self.assertEqual(tags["handler"], "TestHandler")
        self.assertEqual(tags["action_type"], "SPEAK")
        self.assertEqual(tags["error_type"], "ValueError")
        self.assertEqual(tags["thought_id"], "test_thought_123")

        # Verify timestamp
        self.assertEqual(call_args.kwargs["timestamp"], datetime(2025, 1, 16, 12, 0, 0))

    @pytest.mark.asyncio
    async def test_handle_error_continues_on_metric_failure(self):
        """Test that _handle_error continues even if metric tracking fails."""
        # Make memorize_metric raise an exception
        self.mock_memory_bus.memorize_metric.side_effect = Exception("Metric tracking failed")

        dispatch_context = DispatchContext(
            agent_id="test_agent",
            user_id="test_user",
            channel_id="test_channel",
        )

        test_error = RuntimeError("Test runtime error")

        # Mock audit log
        with patch.object(self.handler, "_audit_log", new_callable=AsyncMock) as mock_audit:
            # Should not raise despite metric failure
            await self.handler._handle_error(
                action_type=HandlerActionType.TOOL,
                dispatch_context=dispatch_context,
                thought_id="test_thought_456",
                error=test_error,
            )

            # Audit log should still be called
            mock_audit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_error_without_memory_bus(self):
        """Test that _handle_error works without memory bus."""
        # Remove memory bus
        self.handler.bus_manager = MagicMock()
        del self.handler.bus_manager.memory_bus

        dispatch_context = DispatchContext(
            agent_id="test_agent",
            user_id="test_user",
            channel_id="test_channel",
        )

        test_error = TypeError("Test type error")

        # Mock audit log
        with patch.object(self.handler, "_audit_log", new_callable=AsyncMock) as mock_audit:
            # Should work without memory bus
            await self.handler._handle_error(
                action_type=HandlerActionType.MEMORIZE,
                dispatch_context=dispatch_context,
                thought_id="test_thought_789",
                error=test_error,
            )

            # Audit log should still be called
            mock_audit.assert_called_once()

            # Memory bus method should not have been called
            self.mock_memory_bus.memorize_metric.assert_not_called()


if __name__ == "__main__":
    unittest.main()
