"""
Comprehensive unit tests for emergency shutdown functionality.

Tests the critical emergency shutdown API endpoint and ensures it properly
calls emergency_shutdown() instead of request_shutdown() to force termination.
"""

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes.emergency import (
    ROOT_WA_AUTHORITY_KEYS,
    emergency_shutdown,
    is_authorized_key,
    verify_signature,
    verify_timestamp,
)
from ciris_engine.schemas.services.shutdown import EmergencyCommandType, EmergencyShutdownStatus, WASignedCommand


class TestEmergencyShutdownAPI:
    """Test the emergency shutdown API endpoint."""

    @pytest.fixture
    def valid_command(self):
        """Create a valid emergency shutdown command."""
        return WASignedCommand(
            command_id="test-emergency-123",
            command_type=EmergencyCommandType.SHUTDOWN_NOW,
            wa_id="test-wa-root",
            wa_public_key=ROOT_WA_AUTHORITY_KEYS[0],  # Use first authorized key
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            reason="Test emergency shutdown",
            signature="test-signature-base64",
            target_agent_id="test-agent",
        )

    @pytest.fixture
    def mock_request(self):
        """Create mock FastAPI request."""
        request = Mock()
        request.app = Mock()
        request.app.state = Mock()

        # Mock runtime with shutdown service
        runtime = Mock()
        shutdown_service = Mock()
        shutdown_service.emergency_shutdown = AsyncMock()
        runtime.shutdown_service = shutdown_service
        request.app.state.runtime = runtime

        return request

    @pytest.mark.asyncio
    async def test_emergency_shutdown_calls_emergency_method(self, valid_command, mock_request):
        """Test that emergency shutdown calls emergency_shutdown() not request_shutdown()."""
        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=True
        ), patch("ciris_engine.logic.adapters.api.routes.emergency.is_authorized_key", return_value=True):

            response = await emergency_shutdown(valid_command, mock_request)

            # Verify emergency_shutdown was called, not request_shutdown
            shutdown_service = mock_request.app.state.runtime.shutdown_service
            shutdown_service.emergency_shutdown.assert_called_once()

            # Verify the reason includes emergency prefix and WA ID
            call_args = shutdown_service.emergency_shutdown.call_args[0]
            reason = call_args[0]
            assert "EMERGENCY:" in reason
            assert valid_command.reason in reason
            assert valid_command.wa_id in reason

            # Verify response structure
            assert response.data.command_verified is True
            assert response.data.shutdown_initiated is not None

    @pytest.mark.asyncio
    async def test_emergency_shutdown_invalid_command_type(self, mock_request):
        """Test emergency shutdown rejects invalid command types."""
        # Test with FREEZE command type (not SHUTDOWN_NOW)
        command = WASignedCommand(
            command_id="test-123",
            command_type=EmergencyCommandType.FREEZE,  # Not SHUTDOWN_NOW
            wa_id="test-wa",
            wa_public_key=ROOT_WA_AUTHORITY_KEYS[0],
            issued_at=datetime.now(timezone.utc),
            reason="Test",
            signature="test-sig",
        )

        # This should fail because only SHUTDOWN_NOW is supported
        with pytest.raises(HTTPException) as exc_info:
            await emergency_shutdown(command, mock_request)

        assert exc_info.value.status_code == 400
        assert "Invalid command type" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_emergency_shutdown_timestamp_verification_fails(self, valid_command, mock_request):
        """Test emergency shutdown fails with invalid timestamp."""
        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=False):

            with pytest.raises(HTTPException) as exc_info:
                await emergency_shutdown(valid_command, mock_request)

            assert exc_info.value.status_code == 403
            assert "timestamp" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_emergency_shutdown_signature_verification_fails(self, valid_command, mock_request):
        """Test emergency shutdown fails with invalid signature."""
        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=False
        ):

            with pytest.raises(HTTPException) as exc_info:
                await emergency_shutdown(valid_command, mock_request)

            assert exc_info.value.status_code == 403
            assert "signature" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_emergency_shutdown_unauthorized_key(self, valid_command, mock_request):
        """Test emergency shutdown fails with unauthorized key."""
        valid_command.wa_public_key = "unauthorized-key"

        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=True
        ), patch("ciris_engine.logic.adapters.api.routes.emergency.is_authorized_key", return_value=False):

            with pytest.raises(HTTPException) as exc_info:
                await emergency_shutdown(valid_command, mock_request)

            assert exc_info.value.status_code == 403
            assert "unauthorized" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_emergency_shutdown_no_runtime(self, valid_command):
        """Test emergency shutdown fails when runtime not available."""
        mock_request = Mock()
        mock_request.app = Mock()
        mock_request.app.state = Mock()
        mock_request.app.state.runtime = None

        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=True
        ), patch("ciris_engine.logic.adapters.api.routes.emergency.is_authorized_key", return_value=True):

            with pytest.raises(HTTPException) as exc_info:
                await emergency_shutdown(valid_command, mock_request)

            assert exc_info.value.status_code == 500
            assert "runtime not available" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_emergency_shutdown_no_shutdown_service(self, valid_command, mock_request):
        """Test emergency shutdown fails when shutdown service not available."""
        mock_request.app.state.runtime.shutdown_service = None

        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=True
        ), patch("ciris_engine.logic.adapters.api.routes.emergency.is_authorized_key", return_value=True):

            with pytest.raises(HTTPException) as exc_info:
                await emergency_shutdown(valid_command, mock_request)

            assert exc_info.value.status_code == 500
            assert "shutdown service" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_emergency_shutdown_service_exception(self, valid_command, mock_request):
        """Test emergency shutdown handles service exceptions."""
        # Make emergency_shutdown raise an exception
        mock_request.app.state.runtime.shutdown_service.emergency_shutdown.side_effect = Exception("Service error")

        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=True
        ), patch("ciris_engine.logic.adapters.api.routes.emergency.is_authorized_key", return_value=True):

            with pytest.raises(HTTPException) as exc_info:
                await emergency_shutdown(valid_command, mock_request)

            assert exc_info.value.status_code == 500
            assert "Service error" in str(exc_info.value.detail)


class TestSignatureVerification:
    """Test signature verification logic."""

    @patch("ciris_engine.logic.adapters.api.routes.emergency.CRYPTO_AVAILABLE", True)
    def test_verify_signature_crypto_not_available(self):
        """Test signature verification when crypto not available."""
        with patch("ciris_engine.logic.adapters.api.routes.emergency.CRYPTO_AVAILABLE", False):
            command = Mock()
            result = verify_signature(command)
            assert result is False

    @patch("ciris_engine.logic.adapters.api.routes.emergency.CRYPTO_AVAILABLE", True)
    def test_verify_signature_invalid_signature_exception(self):
        """Test signature verification with invalid signature."""
        command = Mock()
        command.wa_public_key = "test-key"
        command.signature = "invalid-signature"
        command.command_id = "test-123"
        command.command_type = Mock()
        command.command_type.value = "SHUTDOWN_NOW"
        command.wa_id = "test-wa"
        command.issued_at = datetime.now(timezone.utc)
        command.reason = "test"
        command.target_agent_id = "test-agent"
        command.expires_at = None
        command.target_tree_path = None

        with patch("base64.urlsafe_b64decode") as mock_decode, patch(
            "ciris_engine.logic.adapters.api.routes.emergency.Ed25519PublicKey"
        ) as mock_key_class:

            # Make decode raise ValueError to simulate invalid base64
            mock_decode.side_effect = ValueError("Invalid base64")

            result = verify_signature(command)
            assert result is False

    @patch("ciris_engine.logic.adapters.api.routes.emergency.CRYPTO_AVAILABLE", True)
    def test_verify_signature_success(self):
        """Test successful signature verification."""
        command = Mock()
        command.wa_public_key = "dGVzdC1rZXk"  # Valid base64
        command.signature = "dGVzdC1zaWc"  # Valid base64
        command.command_id = "test-123"
        command.command_type = Mock()
        command.command_type.value = "SHUTDOWN_NOW"
        command.wa_id = "test-wa"
        command.issued_at = datetime.now(timezone.utc)
        command.reason = "test"
        command.target_agent_id = "test-agent"
        command.expires_at = None
        command.target_tree_path = None

        with patch("base64.urlsafe_b64decode") as mock_decode, patch(
            "ciris_engine.logic.adapters.api.routes.emergency.Ed25519PublicKey"
        ) as mock_key_class, patch("json.dumps") as mock_json:

            # Setup mocks for successful verification
            mock_decode.return_value = b"test-data"
            mock_public_key = Mock()
            mock_key_class.from_public_bytes.return_value = mock_public_key
            mock_public_key.verify = Mock()  # No exception = success
            mock_json.return_value = '{"test": "data"}'

            result = verify_signature(command)
            assert result is True


class TestTimestampVerification:
    """Test timestamp verification logic."""

    def test_verify_timestamp_valid(self):
        """Test timestamp verification with valid recent timestamp."""
        command = Mock()
        command.issued_at = datetime.now(timezone.utc) - timedelta(minutes=2)  # 2 minutes ago
        command.expires_at = None

        result = verify_timestamp(command)
        assert result is True

    def test_verify_timestamp_too_old(self):
        """Test timestamp verification with timestamp too old."""
        command = Mock()
        command.issued_at = datetime.now(timezone.utc) - timedelta(minutes=10)  # 10 minutes ago
        command.expires_at = None

        result = verify_timestamp(command, window_minutes=5)
        assert result is False

    def test_verify_timestamp_future(self):
        """Test timestamp verification with future timestamp."""
        command = Mock()
        command.issued_at = datetime.now(timezone.utc) + timedelta(minutes=5)  # 5 minutes in future
        command.expires_at = None

        result = verify_timestamp(command)
        assert result is False

    def test_verify_timestamp_expired(self):
        """Test timestamp verification with expired command."""
        command = Mock()
        command.issued_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        command.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)  # Expired 1 minute ago

        result = verify_timestamp(command)
        assert result is False

    def test_verify_timestamp_not_yet_expired(self):
        """Test timestamp verification with not yet expired command."""
        command = Mock()
        command.issued_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        command.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)  # Expires in 5 minutes

        result = verify_timestamp(command)
        assert result is True


class TestKeyAuthorization:
    """Test key authorization logic."""

    def test_is_authorized_key_valid(self):
        """Test key authorization with valid root key."""
        valid_key = ROOT_WA_AUTHORITY_KEYS[0]

        result = is_authorized_key(valid_key)
        assert result is True

    def test_is_authorized_key_invalid(self):
        """Test key authorization with invalid key."""
        invalid_key = "unauthorized-key-12345"

        result = is_authorized_key(invalid_key)
        assert result is False

    def test_is_authorized_key_empty(self):
        """Test key authorization with empty key."""
        result = is_authorized_key("")
        assert result is False

    def test_is_authorized_key_none(self):
        """Test key authorization with None key."""
        result = is_authorized_key(None)
        assert result is False


class TestEmergencyShutdownIntegration:
    """Integration tests for emergency shutdown workflow."""

    @pytest.mark.asyncio
    async def test_full_emergency_shutdown_workflow(self):
        """Test complete emergency shutdown workflow end-to-end."""
        # Create valid command
        command = WASignedCommand(
            command_id="integration-test-123",
            command_type=EmergencyCommandType.SHUTDOWN_NOW,
            wa_id="integration-test-wa",
            wa_public_key=ROOT_WA_AUTHORITY_KEYS[0],
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            reason="Integration test emergency shutdown",
            signature="integration-test-signature",
            target_agent_id="integration-test-agent",
        )

        # Create mock request with full service setup
        mock_request = Mock()
        mock_request.app = Mock()
        mock_request.app.state = Mock()

        # Mock service registry path (preferred)
        service_registry = Mock()
        runtime_service = Mock()
        runtime_service.handle_emergency_shutdown = AsyncMock()

        status = EmergencyShutdownStatus(
            command_received=datetime.now(timezone.utc),
            command_verified=True,
            shutdown_initiated=datetime.now(timezone.utc),
            services_stopped=["runtime_control"],
            data_persisted=True,
            final_message_sent=True,
            shutdown_completed=datetime.now(timezone.utc),
            exit_code=0,
        )
        runtime_service.handle_emergency_shutdown.return_value = status

        service_registry.get_service = AsyncMock(return_value=runtime_service)
        mock_request.app.state.service_registry = service_registry

        # Mock all verification functions to pass
        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=True
        ), patch("ciris_engine.logic.adapters.api.routes.emergency.is_authorized_key", return_value=True):

            response = await emergency_shutdown(command, mock_request)

            # Verify runtime service was called
            runtime_service.handle_emergency_shutdown.assert_called_once_with(command)

            # Verify response
            assert response.data.command_verified is True
            assert response.data.shutdown_completed is not None
            assert response.data.exit_code == 0

    @pytest.mark.asyncio
    async def test_emergency_shutdown_fallback_to_direct(self):
        """Test emergency shutdown falls back to direct shutdown service."""
        command = WASignedCommand(
            command_id="fallback-test-123",
            command_type=EmergencyCommandType.SHUTDOWN_NOW,
            wa_id="fallback-test-wa",
            wa_public_key=ROOT_WA_AUTHORITY_KEYS[0],
            issued_at=datetime.now(timezone.utc),
            reason="Fallback test emergency shutdown",
            signature="fallback-test-signature",
        )

        # Create mock request with no service registry (fallback path)
        mock_request = Mock()
        mock_request.app = Mock()
        mock_request.app.state = Mock()
        mock_request.app.state.service_registry = None  # Force fallback

        # Mock runtime with shutdown service
        runtime = Mock()
        shutdown_service = Mock()
        shutdown_service.emergency_shutdown = AsyncMock()
        runtime.shutdown_service = shutdown_service
        mock_request.app.state.runtime = runtime

        with patch("ciris_engine.logic.adapters.api.routes.emergency.verify_timestamp", return_value=True), patch(
            "ciris_engine.logic.adapters.api.routes.emergency.verify_signature", return_value=True
        ), patch("ciris_engine.logic.adapters.api.routes.emergency.is_authorized_key", return_value=True):

            response = await emergency_shutdown(command, mock_request)

            # Verify direct emergency_shutdown was called
            shutdown_service.emergency_shutdown.assert_called_once()

            # Verify the call used the correct emergency reason format
            call_args = shutdown_service.emergency_shutdown.call_args[0]
            reason = call_args[0]
            assert "EMERGENCY:" in reason
            assert command.reason in reason
            assert command.wa_id in reason

            # Verify response
            assert response.data.command_verified is True
