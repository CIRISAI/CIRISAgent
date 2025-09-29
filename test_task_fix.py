#!/usr/bin/env python3
"""
Quick test to fix the async task mocking issues.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Replace the failing test methods
FIXED_TESTS = '''
    @pytest.mark.asyncio
    async def test_stop_service_task_with_task_attribute(self):
        """Test stopping service with _task attribute."""
        service = Mock()
        service.__class__.__name__ = "TestService"

        # Create a real asyncio task that we can control
        async def dummy_coroutine():
            await asyncio.sleep(0.1)  # Short delay

        task = asyncio.create_task(dummy_coroutine())
        service._task = task

        await _stop_service_task(service)

        # Verify task was cancelled
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_service_task_with_scheduler(self):
        """Test stopping service with scheduler."""
        service = Mock()
        service.__class__.__name__ = "TestService"
        service.stop_scheduler = AsyncMock()
        # Ensure no _task attribute exists
        if hasattr(service, '_task'):
            delattr(service, '_task')

        await _stop_service_task(service)
        service.stop_scheduler.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_service_task_cancelled_error(self):
        """Test handling of CancelledError."""
        service = Mock()
        service.__class__.__name__ = "TestService"

        # Create task that will be cancelled
        async def dummy_coroutine():
            await asyncio.sleep(1)  # Long sleep to allow cancellation

        task = asyncio.create_task(dummy_coroutine())
        service._task = task

        # Cancel immediately to trigger CancelledError path
        task.cancel()

        # Mock current_task to return non-cancelled task
        with patch('asyncio.current_task') as mock_current_task:
            current_task_mock = Mock()
            current_task_mock.cancelled.return_value = False
            mock_current_task.return_value = current_task_mock

            # Should not raise CancelledError
            await _stop_service_task(service)
'''

print("Fixed test methods:")
print(FIXED_TESTS)
