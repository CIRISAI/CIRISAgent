"""
Coverage-focused tests for Discord audit functionality.

Targets audit edge cases and error handling for improved coverage:
- discord_audit.py edge cases (lines 134, 151, 174, 197, 222)
- Audit event processing and error scenarios
- Security event logging variations
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.discord.discord_audit import DiscordAuditLogger


class TestDiscordAuditCoverage:
    """Coverage-focused tests for Discord audit functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_audit_service = Mock()
        self.mock_audit_service.log_event = AsyncMock()

        self.audit = DiscordAuditLogger(audit_service=self.mock_audit_service)

    @pytest.mark.asyncio
    async def test_log_connection_event_success(self):
        """Test connection event logging - DEPRECATED (too verbose)."""
        await self.audit.log_connection_event("connected", guild_count=5, user_count=100)

        # Method is now deprecated - should not call audit service
        self.mock_audit_service.log_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_connection_event_no_audit_service(self):
        """Test connection event logging when audit service not available."""
        audit_no_service = DiscordAuditLogger(audit_service=None)

        # Should not raise exception - falls back to logging
        await audit_no_service.log_connection_event("connected", guild_count=5, user_count=100)

    @pytest.mark.asyncio
    async def test_log_connection_event_with_error(self):
        """Test connection event logging with error - DEPRECATED (too verbose)."""
        await self.audit.log_connection_event("disconnected", guild_count=0, user_count=0, error="Connection lost")

        # Method is now deprecated - should not call audit service
        self.mock_audit_service.log_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_message_sent_success(self):
        """Test message send logging - DEPRECATED (already audited via speak handler action)."""
        await self.audit.log_message_sent("channel123", "user456", "Hello world!", "corr-123")

        # Method is now deprecated - should not call audit service
        self.mock_audit_service.log_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_message_sent_truncation(self):
        """Test message send logging - DEPRECATED (already audited via speak handler action)."""
        long_message = "x" * 150  # Longer than 100 char limit
        await self.audit.log_message_sent("channel123", "user456", long_message)

        # Method is now deprecated - should not call audit service
        self.mock_audit_service.log_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_message_received_success(self):
        """Test message receive logging - DEPRECATED (too verbose)."""
        await self.audit.log_message_received("channel123", "user456", "TestUser", "msg789")

        # Method is now deprecated - should not call audit service
        self.mock_audit_service.log_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_guidance_request_success(self):
        """Test guidance request logging - DEPRECATED (already audited via defer handler action)."""
        context = {"task_id": "task123", "thought_id": "thought456"}
        await self.audit.log_guidance_request("channel123", "user456", context, "guidance received")

        # Method is now deprecated - should not call audit service
        self.mock_audit_service.log_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_guidance_request_no_guidance(self):
        """Test guidance request logging - DEPRECATED (already audited via defer handler action)."""
        context = {"task_id": "task123"}
        await self.audit.log_guidance_request("channel123", "user456", context, None)

        # Method is now deprecated - should not call audit service
        self.mock_audit_service.log_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_approval_request_success(self):
        """Test approval request logging - DEPRECATED (already audited via handler actions)."""
        await self.audit.log_approval_request("channel123", "user456", "delete_file", "approved", "admin789")

        # Method is now deprecated - should not call audit service
        self.mock_audit_service.log_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_permission_change_success(self):
        """Test permission change logging - DEPRECATED (already audited via grant/revoke handler actions)."""
        await self.audit.log_permission_change("admin123", "user456", "AUTHORITY", "grant", "guild789")

        # Method is now deprecated - should not call audit service
        self.mock_audit_service.log_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_tool_execution_success(self):
        """Test successful tool execution logging - targets line 222."""
        params = {"param1": "value1", "param2": 123}
        await self.audit.log_tool_execution("user123", "file_tool", params, True, 250.5)

        self.mock_audit_service.log_event.assert_called_once()
        call_args = self.mock_audit_service.log_event.call_args[1]
        assert call_args["event_type"] == "discord.execute_tool"
        assert call_args["event_data"].user_id == "user123"

    @pytest.mark.asyncio
    async def test_log_tool_execution_failure(self):
        """Test failed tool execution logging."""
        params = {"param1": "value1"}
        await self.audit.log_tool_execution("user123", "file_tool", params, False, 100.0, "Permission denied")

        self.mock_audit_service.log_event.assert_called_once()
        call_args = self.mock_audit_service.log_event.call_args[1]
        assert call_args["event_type"] == "discord.execute_tool.failed"
        assert call_args["event_data"].result == "failure"

    @pytest.mark.asyncio
    async def test_audit_service_exception_handling(self):
        """Test behavior when audit service raises exception."""
        self.mock_audit_service.log_event.side_effect = Exception("Audit service error")

        # Should not raise exception - errors should be handled gracefully
        await self.audit.log_connection_event("connected", guild_count=5, user_count=100)

    @pytest.mark.asyncio
    async def test_log_operation_with_fallback_logging(self):
        """Test log_operation fallback to standard logging."""
        audit_no_service = DiscordAuditLogger(audit_service=None)

        # Should use fallback logging without raising exception
        await audit_no_service.log_operation("test_op", "test_actor", {"test": "context"}, True)
        await audit_no_service.log_operation("test_op", "test_actor", {"test": "context"}, False, "test error")

    @pytest.mark.asyncio
    async def test_complex_operation_context(self):
        """Test audit logging with complex operation context."""
        complex_context = {
            "channel_id": "channel123",
            "guild_id": "guild456",
            "correlation_id": "corr-789",
            "nested_data": {"key1": "value1", "key2": 123},
            "list_data": [1, 2, 3, 4, 5],
        }

        await self.audit.log_operation("complex_test", "user123", complex_context, True)

        self.mock_audit_service.log_event.assert_called_once()
        call_args = self.mock_audit_service.log_event.call_args[1]
        # EventPayload is a Pydantic model - use attribute access
        event_data = call_args["event_data"]
        assert event_data.channel_id == "channel123"

    @pytest.mark.asyncio
    async def test_empty_parameters_handling(self):
        """Test tool execution with empty parameters."""
        await self.audit.log_tool_execution("user123", "simple_tool", {}, True, 50.0)

        self.mock_audit_service.log_event.assert_called_once()
        call_args = self.mock_audit_service.log_event.call_args[1]
        assert call_args["event_type"] == "discord.execute_tool"
        assert call_args["event_data"].user_id == "user123"

    @pytest.mark.asyncio
    async def test_none_parameters_handling(self):
        """Test tool execution with None parameters."""
        await self.audit.log_tool_execution("user123", "simple_tool", None, True, 50.0)

        self.mock_audit_service.log_event.assert_called_once()
        call_args = self.mock_audit_service.log_event.call_args[1]
        assert call_args["event_type"] == "discord.execute_tool"
        assert call_args["event_data"].user_id == "user123"

    def test_set_audit_service_method(self):
        """Test setting audit service after initialization."""
        audit = DiscordAuditLogger()
        new_service = Mock()

        audit.set_audit_service(new_service)

        assert audit._audit_service == new_service

    def test_initialization_with_time_service(self):
        """Test initialization with custom time service."""
        mock_time_service = Mock()
        audit = DiscordAuditLogger(time_service=mock_time_service)

        assert audit._time_service == mock_time_service

    def test_initialization_creates_default_time_service(self):
        """Test initialization creates default time service when None provided."""
        audit = DiscordAuditLogger()

        assert audit._time_service is not None
