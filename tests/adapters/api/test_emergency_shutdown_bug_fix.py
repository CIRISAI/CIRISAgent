"""
Test to demonstrate the critical emergency shutdown bug fix.

This test specifically verifies that the emergency shutdown endpoint calls
emergency_shutdown() instead of request_shutdown(), which was the root cause
of the nemesis shutdown failure.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.emergency import ROOT_WA_AUTHORITY_KEYS, emergency_shutdown
from ciris_engine.schemas.services.shutdown import EmergencyCommandType, WASignedCommand


class TestEmergencyShutdownBugFix:
    """Test that verifies the critical emergency shutdown bug is fixed."""

    @pytest.fixture
    def valid_emergency_command(self):
        """Create a valid emergency shutdown command."""
        return WASignedCommand(
            command_id="bugfix-test-123",
            command_type=EmergencyCommandType.SHUTDOWN_NOW,
            wa_id="bugfix-test-wa-root",
            wa_public_key=ROOT_WA_AUTHORITY_KEYS[0],
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            reason="Testing emergency shutdown bug fix",
            signature="bugfix-test-signature",
            target_agent_id="nemesis-test",
        )

    @pytest.fixture
    def mock_shutdown_service(self):
        """Create mock shutdown service with both methods."""
        shutdown_service = Mock()
        shutdown_service.emergency_shutdown = AsyncMock()
        shutdown_service.request_shutdown = AsyncMock()
        return shutdown_service

    @pytest.fixture
    def mock_request_with_shutdown_service(self, mock_shutdown_service):
        """Create mock request with shutdown service."""
        request = Mock()
        request.app = Mock()
        request.app.state = Mock()

        runtime = Mock()
        runtime.shutdown_service = mock_shutdown_service
        request.app.state.runtime = runtime
        request.app.state.service_registry = None  # Force fallback to direct service

        return request

    @pytest.mark.asyncio
    async def test_emergency_shutdown_calls_emergency_method_not_request(
        self, valid_emergency_command, mock_request_with_shutdown_service
    ):
        """
        CRITICAL TEST: Verify emergency shutdown calls emergency_shutdown(), not request_shutdown().

        This test demonstrates the bug fix for the nemesis shutdown failure.
        Before the fix: emergency endpoint called request_shutdown() → graceful shutdown → could wake up
        After the fix: emergency endpoint calls emergency_shutdown() → forced termination → sys.exit(1)
        """
        # Mock all verification to pass
        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=True
        ), patch("ciris_engine.logic.adapters.api.routes.emergency.is_authorized_key", return_value=True):

            # Execute the emergency shutdown
            response = await emergency_shutdown(valid_emergency_command, mock_request_with_shutdown_service)

            # Get the shutdown service from the mock
            shutdown_service = mock_request_with_shutdown_service.app.state.runtime.shutdown_service

            # CRITICAL ASSERTION: Verify emergency_shutdown() was called
            shutdown_service.emergency_shutdown.assert_called_once()

            # CRITICAL ASSERTION: Verify request_shutdown() was NOT called
            shutdown_service.request_shutdown.assert_not_called()

            # Verify the emergency_shutdown was called with the correct emergency reason format
            call_args = shutdown_service.emergency_shutdown.call_args[0]
            emergency_reason = call_args[0]

            # Verify emergency reason includes the command details
            assert "EMERGENCY:" in emergency_reason
            assert valid_emergency_command.reason in emergency_reason
            assert valid_emergency_command.wa_id in emergency_reason

            # Verify response indicates success
            assert response.data.command_verified is True
            assert response.data.shutdown_initiated is not None

    @pytest.mark.asyncio
    async def test_emergency_vs_regular_shutdown_behavior(
        self, valid_emergency_command, mock_request_with_shutdown_service
    ):
        """
        Test that demonstrates the difference between emergency and regular shutdown.

        Emergency shutdown should:
        - Call emergency_shutdown() → sys.exit(1) + SIGKILL backup
        - Force immediate termination

        Regular shutdown should:
        - Call request_shutdown() → graceful cognitive flow
        - Can be interrupted by state transitions
        """
        shutdown_service = mock_request_with_shutdown_service.app.state.runtime.shutdown_service

        # Mock all verification to pass
        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=True
        ), patch("ciris_engine.logic.adapters.api.routes.emergency.is_authorized_key", return_value=True):

            await emergency_shutdown(valid_emergency_command, mock_request_with_shutdown_service)

            # Verify the emergency path was taken
            shutdown_service.emergency_shutdown.assert_called_once()
            shutdown_service.request_shutdown.assert_not_called()

            # Get the actual call to emergency_shutdown
            emergency_call_args = shutdown_service.emergency_shutdown.call_args
            emergency_reason = emergency_call_args[0][0]

            # The emergency reason should be prefixed and include WA details
            assert emergency_reason.startswith("EMERGENCY:")
            assert valid_emergency_command.wa_id in emergency_reason

            # This is the key difference that would have prevented nemesis from waking back up:
            # emergency_shutdown() calls sys.exit(1) and sets up SIGKILL backup
            # request_shutdown() only sets flags that can be overridden by cognitive states

    @pytest.mark.asyncio
    async def test_nemesis_style_shutdown_scenario(self, mock_request_with_shutdown_service):
        """
        Test that simulates the exact nemesis shutdown scenario.

        This recreates the conditions that led to the nemesis shutdown failure
        and verifies the fix prevents the issue.
        """
        # Create command similar to what would have been sent to nemesis
        nemesis_command = WASignedCommand(
            command_id="nemesis-emergency-shutdown",
            command_type=EmergencyCommandType.SHUTDOWN_NOW,
            wa_id="nemesis-authority",
            wa_public_key=ROOT_WA_AUTHORITY_KEYS[0],
            issued_at=datetime.now(timezone.utc),
            reason="Emergency shutdown of nemesis agent",
            signature="nemesis-emergency-signature",
            target_agent_id="echo-nemesis",
        )

        shutdown_service = mock_request_with_shutdown_service.app.state.runtime.shutdown_service

        # Simulate the verification passing (signature would have been valid)
        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=True
        ), patch("ciris_engine.logic.adapters.api.routes.emergency.is_authorized_key", return_value=True):

            # This call would have failed on nemesis due to the bug
            response = await emergency_shutdown(nemesis_command, mock_request_with_shutdown_service)

            # With the fix, this now calls emergency_shutdown() which would force terminate
            shutdown_service.emergency_shutdown.assert_called_once()

            # The old buggy behavior would have called request_shutdown()
            # which explains why nemesis went SHUTDOWN → WAKEUP → continued running
            shutdown_service.request_shutdown.assert_not_called()

            # Verify the emergency shutdown would have been initiated
            assert response.data.command_verified is True

            # The key fix: emergency_shutdown() includes sys.exit(1) and SIGKILL backup
            # This would have prevented nemesis from waking back up
