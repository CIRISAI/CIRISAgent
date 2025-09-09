"""
Comprehensive test suite for agent.py interact function helper methods.

Tests coverage for the extracted helper methods that reduce cognitive complexity:
- _check_send_messages_permission
- _create_interaction_message
- _handle_consent_for_user
- _check_processor_pause_status
- _get_interaction_timeout
- _get_cognitive_state
- _cleanup_interaction_tracking

These tests ensure robust coverage of all authentication paths, consent management, 
and interaction handling with proper mocking of external dependencies.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from ciris_engine.logic.adapters.api.routes.agent import (
    InteractRequest,
    InteractResponse,
    _check_processor_pause_status,
    _check_send_messages_permission,
    _cleanup_interaction_tracking,
    _create_interaction_message,
    _get_current_cognitive_state,
    _get_interaction_timeout,
    _handle_consent_for_user,
    _message_responses,
    _response_events,
)
from ciris_engine.schemas.api.auth import AuthContext, Permission, UserRole
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.messages import IncomingMessage


class TestCheckSendMessagesPermission:
    """Test _check_send_messages_permission helper method."""

    def test_check_send_messages_permission_with_permission(self):
        """Test successful permission check when user has SEND_MESSAGES."""
        mock_request = Mock(spec=Request)
        mock_auth = Mock(spec=AuthContext)
        mock_auth.has_permission.return_value = True
        
        # Should not raise exception
        _check_send_messages_permission(mock_auth, mock_request)
        mock_auth.has_permission.assert_called_once_with(Permission.SEND_MESSAGES)

    def test_check_send_messages_permission_oauth_user_auto_request(self):
        """Test auto-creation of permission request for OAuth users."""
        mock_request = Mock(spec=Request)
        mock_auth = Mock(spec=AuthContext)
        mock_auth.has_permission.return_value = False
        mock_auth.user_id = "oauth-user-123"
        
        # Mock auth service
        mock_auth_service = Mock()
        mock_user = Mock()
        mock_user.auth_type = "oauth"
        mock_user.permission_requested_at = None
        mock_user.wa_id = "oauth-user-123"
        
        mock_auth_service.get_user.return_value = mock_user
        mock_auth_service._users = {}
        
        mock_request.app.state.auth_service = mock_auth_service
        
        with pytest.raises(HTTPException) as exc_info:
            _check_send_messages_permission(mock_auth, mock_request)
        
        # Should set permission_requested_at and store user
        assert mock_user.permission_requested_at is not None
        assert mock_auth_service._users["oauth-user-123"] == mock_user
        
        # Should return 403 with proper error detail
        assert exc_info.value.status_code == 403
        error_detail = exc_info.value.detail
        assert error_detail["error"] == "insufficient_permissions"
        assert error_detail["permission_requested"] is True
        assert "discord_invite" in error_detail

    def test_check_send_messages_permission_no_auth_service(self):
        """Test handling when no auth service is available."""
        mock_request = Mock(spec=Request)
        mock_auth = Mock(spec=AuthContext)
        mock_auth.has_permission.return_value = False
        mock_auth.user_id = "user-123"
        
        # No auth service
        mock_request.app.state = Mock()
        delattr(mock_request.app.state, 'auth_service')
        
        with pytest.raises(HTTPException) as exc_info:
            _check_send_messages_permission(mock_auth, mock_request)
        
        assert exc_info.value.status_code == 403
        error_detail = exc_info.value.detail
        assert error_detail["can_request_permissions"] is True

    def test_check_send_messages_permission_existing_request(self):
        """Test handling when user already has a permission request."""
        mock_request = Mock(spec=Request)
        mock_auth = Mock(spec=AuthContext)
        mock_auth.has_permission.return_value = False
        mock_auth.user_id = "user-123"
        
        # Mock auth service with existing request
        mock_auth_service = Mock()
        mock_user = Mock()
        mock_user.auth_type = "oauth"
        mock_user.permission_requested_at = datetime.now(timezone.utc)
        
        mock_auth_service.get_user.return_value = mock_user
        mock_request.app.state.auth_service = mock_auth_service
        
        with pytest.raises(HTTPException) as exc_info:
            _check_send_messages_permission(mock_auth, mock_request)
        
        error_detail = exc_info.value.detail
        assert error_detail["permission_requested"] is True
        assert error_detail["can_request_permissions"] is False
        assert error_detail["requested_at"] is not None


class TestCreateInteractionMessage:
    """Test _create_interaction_message helper method."""

    @patch('uuid.uuid4')
    def test_create_interaction_message_success(self, mock_uuid):
        """Test successful message creation."""
        mock_uuid.return_value = Mock()
        mock_uuid.return_value.__str__ = Mock(return_value="test-message-id")
        
        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "user-123"
        
        body = InteractRequest(message="Hello, CIRIS!")
        
        message_id, channel_id, msg = _create_interaction_message(mock_auth, body)
        
        assert message_id == "test-message-id"
        assert channel_id == "api_user-123"
        assert isinstance(msg, IncomingMessage)
        assert msg.message_id == "test-message-id"
        assert msg.author_id == "user-123"
        assert msg.author_name == "user-123"
        assert msg.content == "Hello, CIRIS!"
        assert msg.channel_id == "api_user-123"
        assert msg.timestamp is not None

    def test_create_interaction_message_different_users(self):
        """Test message creation for different user IDs."""
        mock_auth1 = Mock(spec=AuthContext)
        mock_auth1.user_id = "user-abc"
        
        mock_auth2 = Mock(spec=AuthContext)
        mock_auth2.user_id = "user-xyz"
        
        body = InteractRequest(message="Test message")
        
        _, channel_id1, msg1 = _create_interaction_message(mock_auth1, body)
        _, channel_id2, msg2 = _create_interaction_message(mock_auth2, body)
        
        assert channel_id1 == "api_user-abc"
        assert channel_id2 == "api_user-xyz"
        assert msg1.author_id == "user-abc"
        assert msg2.author_id == "user-xyz"


class TestHandleConsentForUser:
    """Test _handle_consent_for_user helper method."""

    @pytest.mark.asyncio
    async def test_handle_consent_existing_user(self):
        """Test consent handling when user already has consent."""
        mock_request = Mock(spec=Request)
        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "user-123"
        
        # Mock consent manager
        mock_consent_manager = AsyncMock()
        mock_consent_status = Mock()
        mock_consent_manager.get_consent.return_value = mock_consent_status
        
        mock_request.app.state.consent_manager = mock_consent_manager
        
        result = await _handle_consent_for_user(mock_auth, "channel-123", mock_request)
        
        assert result == ""
        mock_consent_manager.get_consent.assert_called_once_with("user-123")

    @pytest.mark.asyncio
    async def test_handle_consent_new_user(self):
        """Test consent creation for first-time user."""
        mock_request = Mock(spec=Request)
        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "new-user-123"
        
        # Mock consent manager
        mock_consent_manager = AsyncMock()
        
        # Mock ConsentNotFoundError
        from ciris_engine.logic.services.governance.consent import ConsentNotFoundError
        mock_consent_manager.get_consent.side_effect = ConsentNotFoundError("Not found")
        
        # Mock successful consent creation
        mock_consent_status = Mock()
        mock_consent_manager.grant_consent.return_value = mock_consent_status
        
        mock_request.app.state.consent_manager = mock_consent_manager
        
        result = await _handle_consent_for_user(mock_auth, "channel-123", mock_request)
        
        assert "Privacy Notice" in result
        assert "14 days" in result
        mock_consent_manager.grant_consent.assert_called_once()
        
        # Check consent request details
        consent_req = mock_consent_manager.grant_consent.call_args[0][0]
        assert consent_req.user_id == "new-user-123"
        from ciris_engine.schemas.consent.core import ConsentStream
        assert consent_req.stream == ConsentStream.TEMPORARY

    @pytest.mark.asyncio
    async def test_handle_consent_no_manager(self):
        """Test consent handling when no consent manager is available."""
        mock_request = Mock(spec=Request)
        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "user-123"
        
        # No consent manager
        mock_request.app.state = Mock()
        mock_request.app.state.consent_manager = None
        
        with patch('ciris_engine.logic.services.lifecycle.time.TimeService') as mock_time_service_class:
            with patch('ciris_engine.logic.services.governance.consent.ConsentService') as mock_consent_service_class:
                mock_time_service = Mock()
                mock_time_service_class.return_value = mock_time_service
                
                mock_consent_service = AsyncMock()
                mock_consent_service.get_consent.return_value = Mock()
                mock_consent_service_class.return_value = mock_consent_service
                
                result = await _handle_consent_for_user(mock_auth, "channel-123", mock_request)
                
                assert result == ""
                assert mock_request.app.state.consent_manager == mock_consent_service

    @pytest.mark.asyncio
    async def test_handle_consent_exception_handling(self):
        """Test graceful handling of consent service exceptions."""
        mock_request = Mock(spec=Request)
        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "user-123"
        
        # Mock consent manager that raises exception
        mock_consent_manager = AsyncMock()
        mock_consent_manager.get_consent.side_effect = Exception("Service error")
        
        mock_request.app.state.consent_manager = mock_consent_manager
        
        result = await _handle_consent_for_user(mock_auth, "channel-123", mock_request)
        
        # Should handle exception gracefully and return empty string
        assert result == ""


class TestCheckProcessorPauseStatus:
    """Test _check_processor_pause_status helper method."""

    @pytest.mark.asyncio
    async def test_check_processor_not_paused(self):
        """Test when processor is not paused."""
        mock_request = Mock(spec=Request)
        mock_msg = Mock(spec=IncomingMessage)
        
        # Mock runtime with unpaused processor
        mock_runtime = Mock()
        mock_processor = Mock()
        mock_processor._is_paused = False
        mock_runtime.agent_processor = mock_processor
        
        mock_request.app.state.runtime = mock_runtime
        
        result = await _check_processor_pause_status(mock_request, mock_msg, "msg-123", datetime.now(timezone.utc))
        
        assert result is None

    @pytest.mark.asyncio
    async def test_check_processor_paused(self):
        """Test when processor is paused."""
        mock_request = Mock(spec=Request)
        mock_msg = Mock(spec=IncomingMessage)
        message_id = "msg-123"
        start_time = datetime.now(timezone.utc)
        
        # Mock runtime with paused processor
        mock_runtime = Mock()
        mock_processor = Mock()
        mock_processor._is_paused = True
        mock_processor.get_current_state.return_value = "WORK"
        mock_runtime.agent_processor = mock_processor
        
        # Mock message handler
        mock_on_message = AsyncMock()
        mock_request.app.state.runtime = mock_runtime
        mock_request.app.state.on_message = mock_on_message
        
        # Add to tracking (simulate normal flow)
        _response_events[message_id] = asyncio.Event()
        
        result = await _check_processor_pause_status(mock_request, mock_msg, message_id, start_time)
        
        assert isinstance(result, SuccessResponse)
        assert isinstance(result.data, InteractResponse)
        assert result.data.message_id == message_id
        assert "Processor paused" in result.data.response
        assert result.data.state == "WORK"
        assert result.data.processing_time_ms >= 0
        
        # Should have called message handler
        mock_on_message.assert_called_once_with(mock_msg)
        
        # Should have cleaned up tracking
        assert message_id not in _response_events

    @pytest.mark.asyncio
    async def test_check_processor_paused_no_message_handler(self):
        """Test paused processor without message handler."""
        mock_request = Mock(spec=Request)
        mock_request.app = Mock()
        mock_request.app.state = Mock()
        mock_msg = Mock(spec=IncomingMessage)
        
        # Mock runtime with paused processor
        mock_runtime = Mock()
        mock_processor = Mock()
        mock_processor._is_paused = True
        mock_runtime.agent_processor = mock_processor
        
        mock_request.app.state.runtime = mock_runtime
        # Explicitly create app state without on_message attribute
        mock_request.app.state = Mock(spec_set=['runtime'])
        mock_request.app.state.runtime = mock_runtime
        
        with pytest.raises(HTTPException) as exc_info:
            await _check_processor_pause_status(mock_request, mock_msg, "msg-123", datetime.now(timezone.utc))
        
        assert exc_info.value.status_code == 503
        assert "Message handler not configured" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_check_processor_no_runtime(self):
        """Test when no runtime is available."""
        mock_request = Mock(spec=Request)
        mock_msg = Mock(spec=IncomingMessage)
        
        # No runtime
        mock_request.app.state = Mock()
        mock_request.app.state.runtime = None
        
        result = await _check_processor_pause_status(mock_request, mock_msg, "msg-123", datetime.now(timezone.utc))
        
        assert result is None

    @pytest.mark.asyncio
    async def test_check_processor_exception_handling(self):
        """Test graceful handling of processor check exceptions."""
        mock_request = Mock(spec=Request)
        mock_msg = Mock(spec=IncomingMessage)
        
        # Mock runtime that raises exception
        mock_request.app.state.runtime = Mock()
        mock_request.app.state.runtime.agent_processor = Mock()
        mock_request.app.state.runtime.agent_processor._is_paused = Mock(side_effect=Exception("Runtime error"))
        
        result = await _check_processor_pause_status(mock_request, mock_msg, "msg-123", datetime.now(timezone.utc))
        
        # Should handle exception gracefully and return None
        assert result is None


class TestGetInteractionTimeout:
    """Test _get_interaction_timeout helper method."""

    def test_get_interaction_timeout_default(self):
        """Test default timeout when no config available."""
        mock_request = Mock(spec=Request)
        mock_request.app.state = Mock()
        # Remove api_config attribute to test default behavior
        if hasattr(mock_request.app.state, 'api_config'):
            delattr(mock_request.app.state, 'api_config')
        
        timeout = _get_interaction_timeout(mock_request)
        
        assert timeout == 55.0

    def test_get_interaction_timeout_from_config(self):
        """Test timeout from API config."""
        mock_request = Mock(spec=Request)
        mock_config = Mock()
        mock_config.interaction_timeout = 120.0
        
        mock_request.app.state.api_config = mock_config
        
        timeout = _get_interaction_timeout(mock_request)
        
        assert timeout == 120.0

    def test_get_interaction_timeout_no_state(self):
        """Test timeout when app state is minimal."""
        mock_request = Mock(spec=Request)
        mock_request.app = Mock()
        mock_request.app.state = Mock()
        # Remove api_config attribute to test default behavior
        if hasattr(mock_request.app.state, 'api_config'):
            delattr(mock_request.app.state, 'api_config')
        
        timeout = _get_interaction_timeout(mock_request)
        
        assert timeout == 55.0


class TestGetCurrentCognitiveState:
    """Test _get_current_cognitive_state helper method."""

    def test_get_cognitive_state_default(self):
        """Test default cognitive state when no runtime available."""
        mock_request = Mock(spec=Request)
        mock_request.app.state = Mock()
        mock_request.app.state.runtime = None
        
        state = _get_current_cognitive_state(mock_request)
        
        assert state == "WORK"

    def test_get_cognitive_state_from_runtime(self):
        """Test cognitive state from runtime state manager."""
        # Create a completely non-Mock request object
        class MockRequest:
            def __init__(self):
                self.app = MockApp()
        
        class MockApp:
            def __init__(self):
                self.state = MockAppState()
        
        class MockAppState:
            def __init__(self):
                self.runtime = MockRuntime()
        
        class MockRuntime:
            def __init__(self):
                self.state_manager = MockStateManager()
        
        class MockStateManager:
            def __init__(self):
                self.current_state = "DREAM"
        
        mock_request = MockRequest()
        
        state = _get_current_cognitive_state(mock_request)
        
        assert state == "DREAM"

    def test_get_cognitive_state_no_state_manager(self):
        """Test cognitive state when runtime has no state manager."""
        # Create a simple object without state_manager attribute
        class MockRuntimeNoStateManager:
            pass
        
        class MockAppState:
            def __init__(self):
                self.runtime = MockRuntimeNoStateManager()
        
        class MockApp:
            def __init__(self):
                self.state = MockAppState()
        
        mock_request = Mock()
        mock_request.app = MockApp()
        
        state = _get_current_cognitive_state(mock_request)
        
        assert state == "WORK"


class TestCleanupInteractionTracking:
    """Test _cleanup_interaction_tracking helper method."""

    def test_cleanup_interaction_tracking_success(self):
        """Test successful cleanup of interaction tracking."""
        message_id = "test-msg-123"
        
        # Add items to tracking dictionaries
        _response_events[message_id] = asyncio.Event()
        _message_responses[message_id] = "Test response"
        
        _cleanup_interaction_tracking(message_id)
        
        assert message_id not in _response_events
        assert message_id not in _message_responses

    def test_cleanup_interaction_tracking_nonexistent(self):
        """Test cleanup when message ID doesn't exist in tracking."""
        message_id = "nonexistent-msg"
        
        # Should not raise exception
        _cleanup_interaction_tracking(message_id)
        
        # Verify no items exist
        assert message_id not in _response_events
        assert message_id not in _message_responses

    def test_cleanup_interaction_tracking_partial(self):
        """Test cleanup when only some tracking items exist."""
        message_id = "partial-msg-123"
        
        # Add only to events, not responses
        _response_events[message_id] = asyncio.Event()
        
        _cleanup_interaction_tracking(message_id)
        
        assert message_id not in _response_events
        assert message_id not in _message_responses


class TestInteractionTrackingIntegration:
    """Integration tests for interaction tracking across helper methods."""

    def test_interaction_flow_tracking(self):
        """Test complete interaction tracking flow."""
        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "integration-user"
        
        body = InteractRequest(message="Integration test")
        
        # Create interaction
        message_id, channel_id, msg = _create_interaction_message(mock_auth, body)
        
        # Add tracking (simulate main function)
        event = asyncio.Event()
        _response_events[message_id] = event
        _message_responses[message_id] = "Integration response"
        
        # Verify tracking exists
        assert message_id in _response_events
        assert message_id in _message_responses
        
        # Cleanup
        _cleanup_interaction_tracking(message_id)
        
        # Verify cleanup
        assert message_id not in _response_events
        assert message_id not in _message_responses

    def test_multiple_concurrent_interactions(self):
        """Test handling of multiple concurrent interactions."""
        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "concurrent-user"
        
        body = InteractRequest(message="Concurrent test")
        
        # Create multiple interactions
        interactions = []
        for i in range(3):
            message_id, channel_id, msg = _create_interaction_message(mock_auth, body)
            _response_events[message_id] = asyncio.Event()
            _message_responses[message_id] = f"Response {i}"
            interactions.append(message_id)
        
        # Verify all exist
        for message_id in interactions:
            assert message_id in _response_events
            assert message_id in _message_responses
        
        # Cleanup one at a time
        for i, message_id in enumerate(interactions):
            _cleanup_interaction_tracking(message_id)
            assert message_id not in _response_events
            assert message_id not in _message_responses
            
            # Others should still exist
            for j, other_id in enumerate(interactions):
                if j > i:
                    assert other_id in _response_events
                    assert other_id in _message_responses