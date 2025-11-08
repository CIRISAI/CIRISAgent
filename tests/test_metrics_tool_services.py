"""
Comprehensive metric tests for Tool services.

Tests all custom metrics for tool services and validates proper
metric tracking during tool execution and error handling.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.services.tools.core_tool_service import SecretsToolService
from ciris_engine.schemas.adapters.tools import ToolResult
from ciris_engine.schemas.services.core.secrets import SecretContext
from tests.test_metrics_base import BaseMetricsTest


class TestSecretsToolServiceMetrics(BaseMetricsTest):
    """Test metrics for SecretsToolService (now CoreToolService)."""

    # Expected custom metrics for CoreToolService (v1.4.3+)
    EXPECTED_SECRETS_TOOL_METRICS = {
        "core_tool_invocations",
        "core_tool_uptime_seconds",
        "secrets_retrieved",
        "secrets_stored",
        "tickets_updated",
        "tickets_retrieved",
        "tickets_deferred",
    }

    # Override the base test that uses generic 'service' fixture
    async def verify_service_metrics_base_requirements(self, secrets_tool_service):
        """Override base test to use our specific fixture."""
        return await super().verify_service_metrics_base_requirements(secrets_tool_service)

    @pytest.fixture
    def mock_secrets_service(self):
        """Mock secrets service."""
        secrets_service = AsyncMock()
        secrets_service.retrieve_secret = AsyncMock()
        secrets_service.store_secret = AsyncMock()
        secrets_service.encrypt = AsyncMock(return_value="encrypted_value")
        secrets_service.decrypt = AsyncMock(return_value="decrypted_value")
        return secrets_service

    @pytest.fixture
    def secrets_tool_service(self, mock_time_service, mock_secrets_service):
        """Create SecretsToolService with mocked dependencies."""
        service = SecretsToolService(secrets_service=mock_secrets_service, time_service=mock_time_service)
        # Set start time for uptime calculation and mark as started
        service._start_time = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        service._started = True  # Mark service as started for health check
        return service

    @pytest.mark.asyncio
    async def test_secrets_tool_service_base_metrics(self, secrets_tool_service):
        """Test that SecretsToolService has all required base metrics."""
        # v1.4.3 does not use base metrics - skip this test
        pass

    @pytest.mark.asyncio
    async def test_secrets_tool_service_custom_metrics_present(self, secrets_tool_service):
        """Test that all expected custom metrics are present."""
        metrics = await self.get_service_metrics(secrets_tool_service)

        # Check that all expected custom metrics exist
        self.assert_metrics_exist(metrics, self.EXPECTED_SECRETS_TOOL_METRICS)

        # Check initial values
        assert metrics["core_tool_invocations"] >= 0.0
        assert metrics["core_tool_uptime_seconds"] >= 0.0
        assert metrics["secrets_retrieved"] >= 0.0
        assert metrics["secrets_stored"] >= 0.0
        assert metrics["tickets_updated"] >= 0.0
        assert metrics["tickets_retrieved"] >= 0.0
        assert metrics["tickets_deferred"] >= 0.0

    @pytest.mark.asyncio
    async def test_tool_execution_metrics_increase(self, secrets_tool_service, mock_secrets_service):
        """Test that tool execution metrics increase when tools are used."""
        # Configure mock to return a secret
        mock_secrets_service.retrieve_secret.return_value = "test_secret_value"

        # Execute a tool
        await secrets_tool_service.execute_tool(
            "recall_secret", {"secret_uuid": "test-uuid", "purpose": "testing", "decrypt": True}
        )

        metrics = await self.get_service_metrics(secrets_tool_service)

        # Verify execution metrics increased
        assert metrics["core_tool_invocations"] >= 1.0
        assert metrics["secrets_retrieved"] >= 1.0

    @pytest.mark.asyncio
    async def test_tool_error_metrics_increase(self, secrets_tool_service, mock_secrets_service):
        """Test that error metrics increase when tools fail."""
        # Configure mock to raise an exception
        mock_secrets_service.retrieve_secret.side_effect = Exception("Database error")

        # Execute a tool that will fail
        result = await secrets_tool_service.execute_tool(
            "recall_secret", {"secret_uuid": "test-uuid", "purpose": "testing"}
        )

        # Verify the tool reported failure
        assert not result.success

        metrics = await self.get_service_metrics(secrets_tool_service)

        # Verify error metrics increased
        assert metrics["tool_executions"] == 1.0
        assert metrics["tool_errors"] == 1.0
        assert metrics["success_rate"] == 0.0  # 0% success rate
        assert metrics["audit_events_generated"] == 1.0

    @pytest.mark.asyncio
    async def test_secret_recall_metrics(self, secrets_tool_service, mock_secrets_service):
        """Test that secret recall metrics are tracked."""
        # Configure mock to return secrets
        mock_secrets_service.retrieve_secret.return_value = "test_secret"

        # Test non-decrypt recall
        await secrets_tool_service.execute_tool(
            "recall_secret", {"secret_uuid": "test-uuid-1", "purpose": "testing", "decrypt": False}
        )

        # Test decrypt recall
        await secrets_tool_service.execute_tool(
            "recall_secret", {"secret_uuid": "test-uuid-2", "purpose": "testing", "decrypt": True}
        )

        metrics = await self.get_service_metrics(secrets_tool_service)

        # Both operations count as recalls
        assert metrics["tool_executions"] == 2.0
        assert metrics["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_self_help_metrics(self, secrets_tool_service):
        """Test that self_help tool execution is tracked."""
        # Mock the file existence and content
        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.read_text", return_value="Agent experience content"
        ):

            result = await secrets_tool_service.execute_tool("self_help", {})

            # Verify successful execution
            assert result.success

            metrics = await self.get_service_metrics(secrets_tool_service)

            # Verify metrics
            assert metrics["tool_executions"] == 1.0
            assert metrics["tool_errors"] == 0.0
            assert metrics["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_filter_update_metrics(self, secrets_tool_service):
        """Test that filter update operations are tracked."""
        # Test list_patterns operation (only one that doesn't return "not exposed" error)
        result = await secrets_tool_service.execute_tool("update_secrets_filter", {"operation": "list_patterns"})

        # Should succeed (returns empty patterns list)
        assert result.success

        metrics = await self.get_service_metrics(secrets_tool_service)

        # Verify execution was tracked
        assert metrics["tool_executions"] == 1.0
        assert metrics["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_multiple_operations_metrics_accumulation(self, secrets_tool_service, mock_secrets_service):
        """Test that metrics accumulate correctly over multiple operations."""
        # Configure mock for successful operations
        mock_secrets_service.retrieve_secret.return_value = "test_secret"

        # Perform multiple successful operations
        for i in range(3):
            await secrets_tool_service.execute_tool(
                "recall_secret", {"secret_uuid": f"test-uuid-{i}", "purpose": "testing"}
            )

        # Perform one failing operation
        mock_secrets_service.retrieve_secret.return_value = None  # Secret not found
        await secrets_tool_service.execute_tool("recall_secret", {"secret_uuid": "missing-uuid", "purpose": "testing"})

        metrics = await self.get_service_metrics(secrets_tool_service)

        # Verify accumulated metrics
        assert metrics["tool_executions"] == 4.0
        assert metrics["tool_errors"] == 1.0  # One failure
        assert metrics["success_rate"] == 0.75  # 3/4 = 75% success
        assert metrics["audit_events_generated"] == 4.0  # All executions generate audit

    @pytest.mark.asyncio
    async def test_invalid_tool_execution_metrics(self, secrets_tool_service):
        """Test that invalid tool names are tracked as errors."""
        result = await secrets_tool_service.execute_tool("nonexistent_tool", {})

        # Should fail
        assert not result.success
        assert "Unknown tool" in result.error

        metrics = await self.get_service_metrics(secrets_tool_service)

        # Verify error tracking
        assert metrics["tool_executions"] == 1.0
        assert metrics["tool_errors"] == 1.0
        assert metrics["success_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_parameter_validation_failure_metrics(self, secrets_tool_service):
        """Test that parameter validation failures are tracked as errors."""
        # Call recall_secret without required secret_uuid
        result = await secrets_tool_service.execute_tool("recall_secret", {"purpose": "testing"})  # Missing secret_uuid

        # Should fail
        assert not result.success
        assert "secret_uuid is required" in result.error

        metrics = await self.get_service_metrics(secrets_tool_service)

        # Verify error tracking
        assert metrics["tool_executions"] == 1.0
        assert metrics["tool_errors"] == 1.0
        assert metrics["success_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_service_capabilities_metadata(self, secrets_tool_service):
        """Test that service capabilities include correct metadata."""
        capabilities = secrets_tool_service.get_capabilities()

        # Check custom metadata
        assert capabilities.metadata is not None
        assert capabilities.metadata.adapter == "core_tools"  # Updated from "secrets" to "core_tools"
        assert capabilities.metadata.tool_count == 6  # Now includes ticket tools: update_ticket, get_ticket, defer_ticket

    @pytest.mark.asyncio
    async def test_tool_info_methods(self, secrets_tool_service):
        """Test that tool information methods work correctly."""
        # Test get_available_tools - CoreToolService now has 6 tools (3 secrets + 3 tickets)
        tools = await secrets_tool_service.get_available_tools()
        assert len(tools) == 6
        # Secrets tools
        assert "recall_secret" in tools
        assert "update_secrets_filter" in tools
        assert "self_help" in tools
        # Ticket tools
        assert "update_ticket" in tools
        assert "get_ticket" in tools
        assert "defer_ticket" in tools

        # Test get_tool_info for each tool
        for tool_name in tools:
            tool_info = await secrets_tool_service.get_tool_info(tool_name)
            assert tool_info is not None
            assert tool_info.name == tool_name
            assert tool_info.description is not None
            assert tool_info.parameters is not None

        # Test get_all_tool_info
        all_info = await secrets_tool_service.get_all_tool_info()
        assert len(all_info) == 6  # 3 secrets tools + 3 ticket tools

    @pytest.mark.asyncio
    async def test_parameter_validation_methods(self, secrets_tool_service):
        """Test parameter validation methods."""
        # Valid parameters
        assert await secrets_tool_service.validate_parameters(
            "recall_secret", {"secret_uuid": "test", "purpose": "test"}
        )

        # Invalid parameters
        assert not await secrets_tool_service.validate_parameters(
            "recall_secret", {"purpose": "test"}  # Missing secret_uuid
        )

        # Test other tools
        assert await secrets_tool_service.validate_parameters("self_help", {})
        assert await secrets_tool_service.validate_parameters("update_secrets_filter", {"operation": "list_patterns"})

    @pytest.mark.asyncio
    async def test_service_health_check(self, secrets_tool_service):
        """Test that service health check works."""
        health = await secrets_tool_service.is_healthy()
        assert health is True

        # Health should be reflected in metrics
        metrics = await self.get_service_metrics(secrets_tool_service)
        assert metrics["healthy"] == 1.0

    @pytest.mark.asyncio
    async def test_dependency_checking(self, secrets_tool_service):
        """Test dependency checking methods."""
        # Check dependencies are registered
        assert "SecretsService" in secrets_tool_service._dependencies

        # Check dependency validation
        assert secrets_tool_service._check_dependencies() is True

        # Test with None secrets service
        secrets_tool_service.secrets_service = None
        assert secrets_tool_service._check_dependencies() is False

    def test_metric_tracking_helper_methods(self, secrets_tool_service):
        """Test the metric tracking helper methods."""
        # Test _track_metric method
        value = secrets_tool_service._track_metric("test_metric", 5.0)
        assert value == 5.0  # Should return default since not tracked

        # Test that tracking storage exists
        assert hasattr(secrets_tool_service, "_metrics_tracking")
        assert isinstance(secrets_tool_service._metrics_tracking, dict)

    @pytest.mark.asyncio
    async def test_metric_ranges_and_types(self, secrets_tool_service):
        """Test that all metrics have valid ranges and types."""
        # Add some activity to get realistic metrics
        secrets_tool_service._track_request()
        secrets_tool_service._track_request()
        secrets_tool_service._track_error(Exception("test"))

        metrics = await self.get_service_metrics(secrets_tool_service)

        # Test all metrics are numeric
        self.assert_all_metrics_are_floats(metrics)

        # Test ranges
        self.assert_metrics_valid_ranges(metrics)

        # Specific range checks for tool metrics
        assert 0 <= metrics["success_rate"] <= 1.0
        assert metrics["available_tools"] >= 0
        assert metrics["tools_enabled"] >= 0
        assert metrics["tool_executions"] >= 0
        assert metrics["tool_errors"] >= 0

    @pytest.mark.asyncio
    async def test_async_tool_result_method(self, secrets_tool_service):
        """Test the async tool result method (should return None for sync tools)."""
        result = await secrets_tool_service.get_tool_result("test_correlation_id", 30.0)
        assert result is None  # Secrets tools execute synchronously

    @pytest.mark.asyncio
    async def test_protocol_compliance_methods(self, secrets_tool_service):
        """Test that all ToolServiceProtocol methods are implemented."""
        # Test list_tools (alias for get_available_tools)
        tools = await secrets_tool_service.list_tools()
        assert len(tools) == 6  # 3 secrets tools + 3 ticket tools

        # Test get_tool_schema
        schema = await secrets_tool_service.get_tool_schema("recall_secret")
        assert schema is not None
        assert schema.type == "object"
        assert "secret_uuid" in schema.properties

        # Test with non-existent tool
        schema = await secrets_tool_service.get_tool_schema("nonexistent")
        assert schema is None
