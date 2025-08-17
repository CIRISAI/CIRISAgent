"""Tests for SecretsToolService."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.tools.secrets_tool_service import SecretsToolService
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus


class TestSecretsToolService:
    """Test the secrets tool service."""

    @pytest.fixture
    def mock_secrets_service(self):
        """Create a mock secrets service."""
        mock = Mock(spec=SecretsService)
        mock.filter = Mock()
        mock.filter.detection_config = Mock()
        mock.store = Mock()
        # Add retrieve_secret method that SecretsToolService expects
        mock.retrieve_secret = AsyncMock()
        return mock

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        from datetime import datetime

        mock = Mock()
        mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
        return mock

    @pytest_asyncio.fixture
    async def tool_service(self, mock_secrets_service, mock_time_service):
        """Create the tool service."""
        service = SecretsToolService(secrets_service=mock_secrets_service, time_service=mock_time_service)
        await service.start()
        return service

    @pytest.mark.asyncio
    async def test_get_available_tools(self, tool_service):
        """Test getting list of available tools."""
        tools = await tool_service.get_available_tools()
        assert len(tools) == 3
        assert "recall_secret" in tools
        assert "update_secrets_filter" in tools
        assert "self_help" in tools

    @pytest.mark.asyncio
    async def test_get_metrics(self, tool_service):
        """Test getting telemetry data from secrets tool service."""
        # Set up some metrics (v1.4.3 uses different counters)
        tool_service._request_count = 10
        tool_service._secrets_retrieved = 7  # Successful retrievals
        tool_service._start_time = tool_service._now()

        metrics = await tool_service.get_metrics()

        # Check v1.4.3 metrics
        assert "secrets_tool_invocations" in metrics
        assert "secrets_tool_retrieved" in metrics
        assert "secrets_tool_stored" in metrics
        assert "secrets_tool_uptime_seconds" in metrics

        # Check expected values
        assert metrics["secrets_tool_invocations"] == 10.0
        assert metrics["secrets_tool_retrieved"] == 7.0
        assert metrics["secrets_tool_stored"] == 0.0  # This service only retrieves
        assert metrics["secrets_tool_uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_get_metrics_no_requests(self, tool_service):
        """Test telemetry when no requests have been made."""
        metrics = await tool_service.get_metrics()

        # v1.4.3 metrics - no generic metrics anymore
        assert metrics["secrets_tool_invocations"] == 0.0
        assert metrics["secrets_tool_retrieved"] == 0.0
        assert metrics["secrets_tool_stored"] == 0.0
        assert metrics["secrets_tool_uptime_seconds"] >= 0.0

    @pytest.mark.asyncio
    async def test_get_metrics_error_handling(self, tool_service):
        """Test telemetry handles errors gracefully."""
        # Mock is_healthy to raise an exception
        tool_service.is_healthy = AsyncMock(side_effect=Exception("Test error"))

        metrics = await tool_service.get_metrics()

        # v1.4.3: Should still return metrics even with health check errors
        assert "secrets_tool_invocations" in metrics
        assert "secrets_tool_uptime_seconds" in metrics

    @pytest.mark.asyncio
    async def test_get_all_tool_info(self, tool_service):
        """Test getting info for all tools."""
        tools = await tool_service.get_all_tool_info()
        assert len(tools) == 3

        tool_names = [tool.name for tool in tools]
        assert "recall_secret" in tool_names
        assert "update_secrets_filter" in tool_names
        assert "self_help" in tool_names

        # Check self_help tool specifically
        self_help = next(t for t in tools if t.name == "self_help")
        assert self_help.description == "Access your experience document for guidance"
        assert self_help.category == "knowledge"
        assert len(self_help.parameters.required) == 0  # No required parameters

    @pytest.mark.asyncio
    async def test_recall_secret_success(self, tool_service, mock_secrets_service):
        """Test successful secret recall."""
        # Setup mock - use retrieve_secret (async method)
        mock_secrets_service.retrieve_secret.return_value = "my-secret-value"

        result = await tool_service.execute_tool(
            "recall_secret", {"secret_uuid": "test-uuid", "purpose": "testing", "decrypt": True}
        )

        assert isinstance(result, ToolExecutionResult)
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert result.data["value"] == "my-secret-value"
        assert result.data["decrypted"] is True

    @pytest.mark.asyncio
    async def test_update_secrets_filter_add_pattern(self, tool_service, mock_secrets_service):
        """Test adding a pattern to secrets filter - currently disabled."""
        # Filter operations are intentionally disabled in the implementation
        result = await tool_service.execute_tool(
            "update_secrets_filter", {"operation": "add_pattern", "pattern": "API_KEY=.*", "pattern_type": "regex"}
        )

        # The implementation returns FAILED status for filter operations
        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert result.error == "Filter operations not currently exposed"

    @pytest.mark.asyncio
    async def test_update_secrets_filter_remove_pattern(self, tool_service, mock_secrets_service):
        """Test removing a pattern from secrets filter - currently disabled."""
        result = await tool_service.execute_tool(
            "update_secrets_filter", {"operation": "remove_pattern", "pattern": "API_KEY=.*"}
        )

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert result.error == "Filter operations not currently exposed"

    @pytest.mark.asyncio
    async def test_update_secrets_filter_enable(self, tool_service, mock_secrets_service):
        """Test enabling/disabling secrets filter - currently disabled."""
        result = await tool_service.execute_tool("update_secrets_filter", {"operation": "enable", "enabled": True})

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert result.error == "Filter operations not currently exposed"

    @pytest.mark.asyncio
    async def test_update_secrets_filter_list_patterns(self, tool_service, mock_secrets_service):
        """Test listing patterns - returns empty list but succeeds."""
        result = await tool_service.execute_tool("update_secrets_filter", {"operation": "list_patterns"})

        # list_patterns succeeds but returns empty list
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert result.data["operation"] == "list_patterns"
        assert result.data["patterns"] == []

    @pytest.mark.asyncio
    async def test_recall_secret_not_found(self, tool_service, mock_secrets_service):
        """Test recalling a non-existent secret."""
        # Setup mock to return None (not found)
        mock_secrets_service.retrieve_secret.return_value = None

        result = await tool_service.execute_tool(
            "recall_secret", {"secret_uuid": "non-existent-uuid", "purpose": "testing"}
        )

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_recall_secret_without_decrypt(self, tool_service, mock_secrets_service):
        """Test recalling a secret without decryption (just verify existence)."""
        # Setup mock
        mock_secrets_service.retrieve_secret.return_value = "my-secret-value"

        result = await tool_service.execute_tool(
            "recall_secret", {"secret_uuid": "test-uuid", "purpose": "verification", "decrypt": False}
        )

        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert result.data["exists"] is True
        assert result.data["decrypted"] is False
        assert "value" not in result.data

    @pytest.mark.asyncio
    async def test_self_help_success(self, tool_service):
        """Test successful self_help tool execution."""
        # Mock file content
        mock_content = """# Agent Experience Document

## Discord Operations
- Use discord_delete_message to remove inappropriate content
- Always log moderation actions

## Error Handling
- Retry failed operations up to 3 times
- Log all errors for debugging
"""

        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.read_text", return_value=mock_content
        ):

            result = await tool_service.execute_tool("self_help", {})

            assert result.status == ToolExecutionStatus.COMPLETED
            assert result.success is True
            assert result.data["content"] == mock_content
            assert result.data["source"] == "docs/agent_experience.md"
            assert result.data["length"] == len(mock_content)

    @pytest.mark.asyncio
    async def test_self_help_file_not_found(self, tool_service):
        """Test self_help when experience document doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            result = await tool_service.execute_tool("self_help", {})

            assert result.status == ToolExecutionStatus.FAILED
            assert result.success is False
            assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_self_help_read_error(self, tool_service):
        """Test self_help when file read fails."""
        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.read_text", side_effect=IOError("Permission denied")
        ):

            result = await tool_service.execute_tool("self_help", {})

            assert result.status == ToolExecutionStatus.FAILED
            assert result.success is False
            assert "Permission denied" in result.error

    @pytest.mark.asyncio
    async def test_validate_parameters(self, tool_service):
        """Test parameter validation for all tools."""
        # Test recall_secret validation
        assert (
            await tool_service.validate_parameters("recall_secret", {"secret_uuid": "test", "purpose": "test"}) is True
        )
        assert (
            await tool_service.validate_parameters("recall_secret", {"secret_uuid": "test"}) is False
        )  # Missing purpose

        # Test update_secrets_filter validation
        assert await tool_service.validate_parameters("update_secrets_filter", {"operation": "list_patterns"}) is True
        assert (
            await tool_service.validate_parameters(
                "update_secrets_filter", {"operation": "add_pattern", "pattern": "test"}
            )
            is True
        )
        assert (
            await tool_service.validate_parameters("update_secrets_filter", {"operation": "add_pattern"}) is False
        )  # Missing pattern

        # Test self_help validation (no params required)
        assert await tool_service.validate_parameters("self_help", {}) is True
        assert await tool_service.validate_parameters("self_help", {"any": "param"}) is True

    @pytest.mark.asyncio
    async def test_unknown_tool(self, tool_service):
        """Test executing an unknown tool."""
        result = await tool_service.execute_tool("unknown_tool", {})

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_service_lifecycle(self, mock_secrets_service, mock_time_service):
        """Test service start and stop."""
        service = SecretsToolService(secrets_service=mock_secrets_service, time_service=mock_time_service)

        # Test start
        await service.start()
        assert await service.is_healthy() is True

        # Test stop
        await service.stop()
        # Service should still be healthy after stop (no resources to clean up)
        assert await service.is_healthy() is True
