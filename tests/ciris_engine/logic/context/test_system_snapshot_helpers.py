"""
Comprehensive unit tests for system_snapshot_helpers.py functions.

Tests all helper functions with 80%+ coverage to ensure safety before refactoring.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock, patch

import pytest
from pydantic import BaseModel

from ciris_engine.logic.context.system_snapshot_helpers import (
    _build_current_task_summary,
    _collect_adapter_channels,
    _collect_available_tools,
    _collect_resource_alerts,
    _collect_service_health,
    _enrich_user_profiles,
    _extract_agent_identity,
    _extract_thought_summary,
    _extract_user_ids_from_context,
    _get_recent_tasks,
    _get_secrets_data,
    _get_shutdown_context,
    _get_telemetry_summary,
    _get_top_tasks,
    _json_serial_for_users,
    _resolve_channel_context,
    _safe_extract_channel_info,
)
from ciris_engine.schemas.adapters.tools import ToolInfo
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.runtime.system_context import ChannelContext, TaskSummary, ThoughtSummary, UserProfile
from ciris_engine.schemas.services.graph.memory import MemorySearchFilter
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery

# =============================================================================
# 1. THOUGHT PROCESSING TESTS
# =============================================================================


class TestThoughtProcessing:
    """Test thought processing helper functions."""

    def test_extract_thought_summary_with_none_thought(self):
        """Test extracting thought summary with None thought."""
        result = _extract_thought_summary(None)
        assert result is None

    def test_extract_thought_summary_with_valid_thought(self, mock_thought):
        """Test extracting thought summary with valid thought object."""
        result = _extract_thought_summary(mock_thought)

        assert isinstance(result, ThoughtSummary)
        assert result.thought_id == "thought_123"
        assert result.content == "Test thought content"
        assert result.status == "PROCESSING"
        assert result.source_task_id == "task_456"
        assert result.thought_type == "OBSERVATION"
        assert result.thought_depth == 1

    def test_extract_thought_summary_with_string_status(self):
        """Test extracting thought summary with string status."""
        thought = Mock()
        thought.thought_id = "test_thought_456"
        thought.content = "Another thought"
        thought.status = "COMPLETED"  # String status
        thought.source_task_id = None
        thought.thought_type = None
        thought.thought_depth = None

        result = _extract_thought_summary(thought)

        assert result.thought_id == "test_thought_456"
        assert result.status == "COMPLETED"
        assert result.source_task_id is None

    def test_extract_thought_summary_with_none_thought_id(self):
        """Test extracting thought summary with None thought_id gets default."""
        thought = Mock()
        thought.thought_id = None
        thought.content = "Test"
        thought.status = "NEW"
        thought.source_task_id = "task1"
        thought.thought_type = "ACTION"
        thought.thought_depth = 1

        result = _extract_thought_summary(thought)

        assert result.thought_id == "unknown"  # Default value


# =============================================================================
# 2. CHANNEL RESOLUTION TESTS
# =============================================================================


class TestChannelResolution:
    """Test channel resolution helper functions."""

    def test_safe_extract_channel_info_with_none_context(self):
        """Test extracting channel info with None context."""
        channel_id, channel_context = _safe_extract_channel_info(None, "test")
        assert channel_id is None
        assert channel_context is None

    def test_safe_extract_channel_info_from_system_snapshot_channel_context(self, mock_context_with_channel):
        """Test extracting from system_snapshot.channel_context."""
        channel_id, channel_context = _safe_extract_channel_info(mock_context_with_channel, "test_source")

        assert channel_id == "context_channel_456"
        assert channel_context == mock_context_with_channel.system_snapshot.channel_context

    def test_safe_extract_channel_info_from_system_snapshot_channel_id(self):
        """Test extracting from system_snapshot.channel_id."""
        context = Mock()
        context.system_snapshot = Mock()
        context.system_snapshot.channel_id = "direct_channel_456"
        # No channel_context attribute
        del context.system_snapshot.channel_context

        channel_id, channel_context = _safe_extract_channel_info(context, "test_source")

        assert channel_id == "direct_channel_456"
        assert channel_context is None

    def test_safe_extract_channel_info_from_dict_context(self):
        """Test extracting from dict context."""
        context = {"channel_id": "dict_channel_789"}

        channel_id, channel_context = _safe_extract_channel_info(context, "dict_source")

        assert channel_id == "dict_channel_789"
        assert channel_context is None

    def test_safe_extract_channel_info_from_direct_attribute(self):
        """Test extracting from direct channel_id attribute."""
        context = Mock()
        context.channel_id = "attr_channel_101"
        # Ensure system_snapshot doesn't exist to force direct attribute access
        del context.system_snapshot

        channel_id, channel_context = _safe_extract_channel_info(context, "attr_source")

        assert channel_id == "attr_channel_101"
        assert channel_context is None

    def test_safe_extract_channel_info_with_exception(self, caplog):
        """Test extracting channel info with exception handling - now fails fast."""
        context = Mock()
        context.system_snapshot = Mock()
        # Make channel_context access raise an exception
        type(context.system_snapshot).channel_context = PropertyMock(side_effect=Exception("Test error"))

        with pytest.raises(Exception, match="Test error"):
            channel_id, channel_context = _safe_extract_channel_info(context, "error_source")

        assert "Error extracting channel info from error_source: Test error" in caplog.text

    @pytest.mark.asyncio
    async def test_resolve_channel_context_from_task(self, mock_task):
        """Test resolving channel context from task."""
        # Override the mock task's context to have the structure we need
        mock_task.context.system_snapshot = Mock()
        mock_task.context.system_snapshot.channel_context = Mock()
        mock_task.context.system_snapshot.channel_context.channel_id = "task_channel_123"

        channel_id, channel_context = await _resolve_channel_context(mock_task, None, None)

        assert channel_id == "task_channel_123"
        assert channel_context is not None

    @pytest.mark.asyncio
    async def test_resolve_channel_context_from_thought(self, mock_thought):
        """Test resolving channel context from thought when task has no channel."""
        task = Mock()
        task.context = None

        # Set up thought context - use direct channel_id, not system_snapshot
        del mock_thought.context.system_snapshot
        mock_thought.context.channel_id = "thought_channel_456"

        channel_id, channel_context = await _resolve_channel_context(task, mock_thought, None)

        assert channel_id == "thought_channel_456"
        assert channel_context is None

    @pytest.mark.asyncio
    async def test_resolve_channel_context_with_memory_lookup(self):
        """Test resolving channel context with memory service lookup."""
        task = Mock()
        task.context = Mock()
        # Ensure system_snapshot doesn't exist to force direct attribute access
        del task.context.system_snapshot
        task.context.channel_id = "memory_channel_789"

        memory_service = Mock()
        memory_node = Mock()
        memory_node.id = "channel/memory_channel_789"
        memory_node.attributes = {"channel_name": "Test Channel"}
        memory_service.recall = AsyncMock(return_value=[memory_node])

        channel_id, channel_context = await _resolve_channel_context(task, None, memory_service)

        assert channel_id == "memory_channel_789"
        memory_service.recall.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_channel_context_with_memory_search_fallback(self):
        """Test resolving channel context with memory search fallback."""
        task = Mock()
        task.context = Mock()
        # Ensure system_snapshot doesn't exist to force direct attribute access
        del task.context.system_snapshot
        task.context.channel_id = "search_channel_101"

        memory_service = Mock()
        # First recall returns empty
        memory_service.recall = AsyncMock(return_value=[])
        # Search returns results
        search_node = Mock()
        search_node.id = "channel/search_channel_101"
        search_node.attributes = {"channel_id": "search_channel_101"}
        memory_service.search = AsyncMock(return_value=[search_node])

        with patch("ciris_engine.schemas.services.graph.memory.MemorySearchFilter") as mock_filter:
            channel_id, channel_context = await _resolve_channel_context(task, None, memory_service)

        assert channel_id == "search_channel_101"
        memory_service.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_channel_context_with_memory_exception(self, caplog):
        """Test resolving channel context with memory service exception."""
        task = Mock()
        task.context = Mock()
        # Ensure system_snapshot doesn't exist to force direct attribute access
        del task.context.system_snapshot
        task.context.channel_id = "error_channel_202"

        memory_service = Mock()
        memory_service.recall = AsyncMock(side_effect=Exception("Memory error"))

        channel_id, channel_context = await _resolve_channel_context(task, None, memory_service)

        assert channel_id == "error_channel_202"
        assert "Failed to retrieve channel context for error_channel_202: Memory error" in caplog.text


# =============================================================================
# 3. IDENTITY MANAGEMENT TESTS
# =============================================================================


class TestIdentityManagement:
    """Test identity management helper functions."""

    @pytest.mark.asyncio
    async def test_extract_agent_identity_with_none_memory_service(self):
        """Test extracting agent identity with None memory service."""
        identity_data, purpose, capabilities, restrictions = await _extract_agent_identity(None)

        assert identity_data == {}
        assert purpose is None
        assert capabilities == []
        assert restrictions == []

    @pytest.mark.asyncio
    async def test_extract_agent_identity_with_valid_identity_node(self):
        """Test extracting agent identity with valid identity node."""
        memory_service = Mock()
        identity_node = Mock()
        identity_node.attributes = {
            "agent_id": "test_agent_123",
            "description": "Test agent description",
            "role_description": "Test agent role",
            "trust_level": 0.8,
            "stewardship": "responsible_ai",
            "permitted_actions": ["read", "write"],
            "restricted_capabilities": ["admin"],
        }
        memory_service.recall = AsyncMock(return_value=[identity_node])

        identity_data, purpose, capabilities, restrictions = await _extract_agent_identity(memory_service)

        assert identity_data["agent_id"] == "test_agent_123"
        assert identity_data["description"] == "Test agent description"
        assert identity_data["role"] == "Test agent role"
        assert identity_data["trust_level"] == 0.8
        assert identity_data["stewardship"] == "responsible_ai"
        assert purpose == "Test agent role"
        assert capabilities == ["read", "write"]
        assert restrictions == ["admin"]

    @pytest.mark.asyncio
    async def test_extract_agent_identity_with_pydantic_attributes(self):
        """Test extracting agent identity with Pydantic model attributes."""
        memory_service = Mock()
        identity_node = Mock()
        attrs_model = Mock()
        attrs_model.model_dump.return_value = {
            "agent_id": "pydantic_agent",
            "role_description": "Pydantic agent",
            "trust_level": 0.9,
        }
        identity_node.attributes = attrs_model
        memory_service.recall = AsyncMock(return_value=[identity_node])

        identity_data, purpose, capabilities, restrictions = await _extract_agent_identity(memory_service)

        assert identity_data["agent_id"] == "pydantic_agent"
        assert purpose == "Pydantic agent"

    @pytest.mark.asyncio
    async def test_extract_agent_identity_with_unexpected_attributes_type(self, caplog):
        """Test extracting agent identity with unexpected attributes type."""
        memory_service = Mock()
        identity_node = Mock()
        identity_node.attributes = "unexpected_string"  # Invalid type
        memory_service.recall = AsyncMock(return_value=[identity_node])

        identity_data, purpose, capabilities, restrictions = await _extract_agent_identity(memory_service)

        assert identity_data == {"agent_id": "", "description": "", "role": "", "trust_level": 0.5}
        assert "Unexpected graph node attributes type" in caplog.text

    @pytest.mark.asyncio
    async def test_extract_agent_identity_with_no_identity_node(self):
        """Test extracting agent identity with no identity node found."""
        memory_service = Mock()
        memory_service.recall = AsyncMock(return_value=[])

        identity_data, purpose, capabilities, restrictions = await _extract_agent_identity(memory_service)

        assert identity_data == {}
        assert purpose is None
        assert capabilities == []
        assert restrictions == []

    @pytest.mark.asyncio
    async def test_extract_agent_identity_with_exception(self, caplog):
        """Test extracting agent identity with exception."""
        memory_service = Mock()
        memory_service.recall = AsyncMock(side_effect=Exception("Identity error"))

        identity_data, purpose, capabilities, restrictions = await _extract_agent_identity(memory_service)

        assert identity_data == {}
        assert "Failed to retrieve agent identity from graph: Identity error" in caplog.text


# =============================================================================
# 4. TASK PROCESSING TESTS
# =============================================================================


class TestTaskProcessing:
    """Test task processing helper functions."""

    @patch("ciris_engine.logic.context.system_snapshot_helpers.persistence.get_recent_completed_tasks")
    def test_get_recent_tasks_with_valid_tasks(self, mock_get_recent):
        """Test getting recent tasks with valid task objects."""
        # Create mock task
        mock_task = Mock(spec=BaseModel)
        mock_task.task_id = "task_123"
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.status = Mock()
        mock_task.status.value = "COMPLETED"
        mock_task.channel_id = "test_channel"
        mock_task.priority = 5
        mock_task.retry_count = 2
        mock_task.parent_task_id = "parent_123"

        mock_get_recent.return_value = [mock_task]

        result = _get_recent_tasks(5)

        assert len(result) == 1
        assert isinstance(result[0], TaskSummary)
        assert result[0].task_id == "task_123"
        assert result[0].status == "COMPLETED"
        assert result[0].channel_id == "test_channel"
        assert result[0].priority == 5
        assert result[0].retry_count == 2
        assert result[0].parent_task_id == "parent_123"

    @patch("ciris_engine.logic.context.system_snapshot_helpers.persistence.get_recent_completed_tasks")
    def test_get_recent_tasks_with_string_status(self, mock_get_recent):
        """Test getting recent tasks with string status."""
        mock_task = Mock(spec=BaseModel)
        mock_task.task_id = "task_456"
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.status = "FAILED"  # String instead of enum

        mock_get_recent.return_value = [mock_task]

        result = _get_recent_tasks(1)

        assert result[0].status == "FAILED"

    @patch("ciris_engine.logic.context.system_snapshot_helpers.persistence.get_recent_completed_tasks")
    def test_get_recent_tasks_with_missing_attributes(self, mock_get_recent):
        """Test getting recent tasks with missing optional attributes."""
        mock_task = Mock(spec=BaseModel)
        mock_task.task_id = "task_789"
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.status = "PENDING"
        # Missing optional attributes

        mock_get_recent.return_value = [mock_task]

        result = _get_recent_tasks(1)

        assert result[0].task_id == "task_789"
        assert result[0].channel_id == "system"  # Default value
        assert result[0].priority == 0  # Default value
        assert result[0].retry_count == 0  # Default value
        assert result[0].parent_task_id is None  # Default value

    @patch("ciris_engine.logic.context.system_snapshot_helpers.persistence.get_top_tasks")
    def test_get_top_tasks_with_valid_tasks(self, mock_get_top):
        """Test getting top tasks with valid task objects."""
        mock_task = Mock(spec=BaseModel)
        mock_task.task_id = "top_task_123"
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.status = Mock()
        mock_task.status.value = "PENDING"

        mock_get_top.return_value = [mock_task]

        result = _get_top_tasks(3)

        assert len(result) == 1
        assert result[0].task_id == "top_task_123"
        assert result[0].status == "PENDING"

    def test_build_current_task_summary_with_none_task(self):
        """Test building current task summary with None task."""
        result = _build_current_task_summary(None)
        assert result is None

    def test_build_current_task_summary_with_valid_task(self):
        """Test building current task summary with valid task."""
        task = Mock(spec=BaseModel)
        task.task_id = "current_task_456"
        task.created_at = datetime.now(timezone.utc)
        task.status = Mock()
        task.status.value = "PROCESSING"
        task.channel_id = "current_channel"
        task.priority = 8
        task.retry_count = 1
        task.parent_task_id = None

        result = _build_current_task_summary(task)

        assert isinstance(result, TaskSummary)
        assert result.task_id == "current_task_456"
        assert result.status == "PROCESSING"
        assert result.channel_id == "current_channel"
        assert result.priority == 8

    def test_build_current_task_summary_with_non_basemodel(self):
        """Test building current task summary with non-BaseModel object."""
        task = "not_a_basemodel"

        result = _build_current_task_summary(task)

        assert result is None


# =============================================================================
# 5. SYSTEM CONTEXT TESTS
# =============================================================================


class TestSystemContext:
    """Test system context helper functions."""

    @pytest.mark.asyncio
    async def test_get_secrets_data_with_none_service(self):
        """Test getting secrets data with None service."""
        result = await _get_secrets_data(None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_secrets_data_with_valid_service(self):
        """Test getting secrets data with valid service."""
        secrets_service = Mock()
        expected_data = {"secrets_count": 5, "filter_version": 2}

        with patch("ciris_engine.logic.context.system_snapshot_helpers.build_secrets_snapshot") as mock_build:
            mock_build.return_value = expected_data
            result = await _get_secrets_data(secrets_service)

        assert result == expected_data
        mock_build.assert_called_once_with(secrets_service)

    def test_get_shutdown_context_with_none_runtime(self):
        """Test getting shutdown context with None runtime."""
        result = _get_shutdown_context(None)
        assert result is None

    def test_get_shutdown_context_with_runtime_no_context(self):
        """Test getting shutdown context with runtime missing context."""
        runtime = Mock()
        runtime.current_shutdown_context = None

        result = _get_shutdown_context(runtime)
        assert result is None

    def test_get_shutdown_context_with_valid_context(self):
        """Test getting shutdown context with valid context."""
        runtime = Mock()
        runtime.current_shutdown_context = "graceful_shutdown"

        result = _get_shutdown_context(runtime)
        assert result == "graceful_shutdown"

    def test_collect_resource_alerts_with_none_monitor(self, caplog):
        """Test collecting resource alerts with None monitor."""
        result = _collect_resource_alerts(None)

        assert "Resource monitor not available" in caplog.text
        assert result == []

    def test_collect_resource_alerts_with_critical_alerts(self):
        """Test collecting resource alerts with critical conditions."""
        resource_monitor = Mock()
        resource_monitor.snapshot = Mock()
        resource_monitor.snapshot.critical = ["Memory usage > 90%", "CPU usage > 95%"]
        resource_monitor.snapshot.healthy = True

        result = _collect_resource_alerts(resource_monitor)

        assert len(result) == 2
        assert "🚨 CRITICAL! RESOURCE LIMIT BREACHED! Memory usage > 90%" in result[0]
        assert "🚨 CRITICAL! RESOURCE LIMIT BREACHED! CPU usage > 95%" in result[1]

    def test_collect_resource_alerts_with_unhealthy_system(self):
        """Test collecting resource alerts with unhealthy system."""
        resource_monitor = Mock()
        resource_monitor.snapshot = Mock()
        resource_monitor.snapshot.critical = []
        resource_monitor.snapshot.healthy = False

        result = _collect_resource_alerts(resource_monitor)

        assert len(result) == 1
        assert "🚨 CRITICAL! SYSTEM UNHEALTHY!" in result[0]

    def test_collect_resource_alerts_with_exception(self, caplog):
        """Test collecting resource alerts with exception."""
        resource_monitor = Mock()
        # Use type() to set up a property that raises an exception
        type(resource_monitor).snapshot = PropertyMock(side_effect=Exception("Monitor error"))

        result = _collect_resource_alerts(resource_monitor)

        assert len(result) == 1
        assert "🚨 CRITICAL! FAILED TO CHECK RESOURCES: Monitor error" in result[0]
        assert "Failed to get resource alerts: Monitor error" in caplog.text


# =============================================================================
# 6. SERVICE HEALTH TESTS
# =============================================================================


class TestServiceHealth:
    """Test service health helper functions."""

    @pytest.mark.asyncio
    async def test_collect_service_health_with_none_registry(self):
        """Test collecting service health with None registry."""
        service_health, circuit_breaker = await _collect_service_health(None)

        assert service_health == {}
        assert circuit_breaker == {}

    @pytest.mark.asyncio
    async def test_collect_service_health_with_handler_services(self):
        """Test collecting service health with handler services."""
        service_registry = Mock()

        # Mock service with health status
        service = Mock()
        health_status = Mock()
        health_status.is_healthy = True
        service.get_health_status = AsyncMock(return_value=health_status)
        service.get_circuit_breaker_status = Mock(return_value="CLOSED")

        registry_info = {"handlers": {"discord": {"communication": [service]}}, "global_services": {}}
        service_registry.get_provider_info.return_value = registry_info

        service_health, circuit_breaker = await _collect_service_health(service_registry)

        assert service_health["discord.communication"] is True
        assert circuit_breaker["discord.communication"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_collect_service_health_with_global_services(self):
        """Test collecting service health with global services."""
        service_registry = Mock()

        # Mock global service
        global_service = Mock()
        health_status = Mock()
        health_status.is_healthy = False
        global_service.get_health_status = AsyncMock(return_value=health_status)
        global_service.get_circuit_breaker_status = Mock(return_value="OPEN")

        registry_info = {"handlers": {}, "global_services": {"memory": [global_service]}}
        service_registry.get_provider_info.return_value = registry_info

        service_health, circuit_breaker = await _collect_service_health(service_registry)

        assert service_health["global.memory"] is False
        assert circuit_breaker["global.memory"] == "OPEN"

    @pytest.mark.asyncio
    async def test_collect_service_health_with_missing_health_method(self):
        """Test collecting service health with service missing health method."""
        service_registry = Mock()

        # Mock service without health methods
        service = Mock(spec=[])  # Empty spec, no methods

        registry_info = {"handlers": {"api": {"tool": [service]}}, "global_services": {}}
        service_registry.get_provider_info.return_value = registry_info

        service_health, circuit_breaker = await _collect_service_health(service_registry)

        # Should not have entries for services without health methods
        assert "api.tool" not in service_health
        assert "api.tool" not in circuit_breaker

    @pytest.mark.asyncio
    async def test_collect_service_health_with_none_circuit_breaker(self):
        """Test collecting service health with None circuit breaker status."""
        service_registry = Mock()

        service = Mock()
        # Service needs async health method
        health_status = Mock()
        health_status.is_healthy = True
        service.get_health_status = AsyncMock(return_value=health_status)
        service.get_circuit_breaker_status = Mock(return_value=None)

        registry_info = {"handlers": {"cli": {"runtime_control": [service]}}, "global_services": {}}
        service_registry.get_provider_info.return_value = registry_info

        service_health, circuit_breaker = await _collect_service_health(service_registry)

        assert circuit_breaker["cli.runtime_control"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_collect_service_health_with_exception(self, caplog):
        """Test collecting service health with exception."""
        service_registry = Mock()
        service_registry.get_provider_info.side_effect = Exception("Registry error")

        service_health, circuit_breaker = await _collect_service_health(service_registry)

        assert service_health == {}
        assert circuit_breaker == {}
        assert "Failed to collect service health status: Registry error" in caplog.text


# =============================================================================
# 7. SYSTEM DATA TESTS
# =============================================================================


class TestSystemData:
    """Test system data helper functions."""

    @pytest.mark.asyncio
    async def test_get_telemetry_summary_with_none_service(self):
        """Test getting telemetry summary with None service."""
        result = await _get_telemetry_summary(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_telemetry_summary_with_valid_service(self, caplog):
        """Test getting telemetry summary with valid service."""
        telemetry_service = Mock()
        expected_summary = {"cpu_usage": 0.5, "memory_usage": 0.7}
        telemetry_service.get_telemetry_summary = AsyncMock(return_value=expected_summary)

        result = await _get_telemetry_summary(telemetry_service)

        assert result == expected_summary
        assert "Successfully retrieved telemetry summary" in caplog.text

    @pytest.mark.asyncio
    async def test_get_telemetry_summary_with_exception(self, caplog):
        """Test getting telemetry summary with exception."""
        telemetry_service = Mock()
        telemetry_service.get_telemetry_summary = AsyncMock(side_effect=Exception("Telemetry error"))

        result = await _get_telemetry_summary(telemetry_service)

        assert result is None
        assert "Failed to get telemetry summary: Telemetry error" in caplog.text

    @pytest.mark.asyncio
    async def test_collect_adapter_channels_with_none_runtime(self):
        """Test collecting adapter channels with None runtime."""
        result = await _collect_adapter_channels(None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_collect_adapter_channels_with_no_adapter_manager(self):
        """Test collecting adapter channels with runtime missing adapter_manager."""
        runtime = Mock()
        runtime.adapter_manager = None

        result = await _collect_adapter_channels(runtime)
        assert result == {}

    @pytest.mark.asyncio
    async def test_collect_adapter_channels_with_valid_adapters(self, caplog):
        """Test collecting adapter channels with valid adapters."""
        runtime = Mock()
        adapter_manager = Mock()

        # Mock adapter with channels
        adapter = Mock()
        channel = Mock(spec=ChannelContext)
        channel.channel_type = "discord"
        adapter.get_channel_list.return_value = [channel]

        adapter_manager._adapters = {"discord_adapter": adapter}
        runtime.adapter_manager = adapter_manager

        result = await _collect_adapter_channels(runtime)

        assert "discord" in result
        assert len(result["discord"]) == 1
        assert "Found 1 channels for discord adapter" in caplog.text

    @pytest.mark.asyncio
    async def test_collect_adapter_channels_with_invalid_channel_type(self):
        """Test collecting adapter channels with invalid channel type."""
        runtime = Mock()
        adapter_manager = Mock()

        # Mock adapter with invalid channel type
        adapter = Mock()
        adapter.get_channel_list.return_value = ["invalid_channel"]  # Not ChannelContext

        adapter_manager._adapters = {"bad_adapter": adapter}
        runtime.adapter_manager = adapter_manager

        with pytest.raises(TypeError, match="returned invalid channel list type"):
            await _collect_adapter_channels(runtime)

    @pytest.mark.asyncio
    async def test_collect_adapter_channels_with_adapter_exception(self):
        """Test collecting adapter channels with adapter exception."""
        runtime = Mock()
        adapter_manager = Mock()
        type(adapter_manager)._adapters = PropertyMock(side_effect=Exception("Adapter error"))
        runtime.adapter_manager = adapter_manager

        with pytest.raises(Exception, match="Adapter error"):
            await _collect_adapter_channels(runtime)

    @pytest.mark.asyncio
    async def test_collect_available_tools_with_none_runtime(self):
        """Test collecting available tools with None runtime."""
        result = await _collect_available_tools(None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_collect_available_tools_with_missing_attributes(self):
        """Test collecting available tools with runtime missing required attributes."""
        runtime = Mock()
        # Missing bus_manager or service_registry

        result = await _collect_available_tools(runtime)
        assert result == {}

    @pytest.mark.asyncio
    async def test_collect_available_tools_with_valid_tools(self, caplog):
        """Test collecting available tools with valid tool services."""
        runtime = Mock()
        runtime.bus_manager = Mock()
        runtime.service_registry = Mock()

        # Mock tool service
        tool_service = Mock()
        tool_service.adapter_id = "discord_tools"
        tool_service.get_available_tools.return_value = ["send_message", "get_user"]

        # Mock tool info
        tool_info = Mock(spec=ToolInfo)
        tool_service.get_tool_info.return_value = tool_info

        runtime.service_registry.get_services_by_type.return_value = [tool_service]

        result = await _collect_available_tools(runtime)

        assert "discord" in result
        assert len(result["discord"]) == 2
        assert "Found 2 tools for discord adapter" in caplog.text

    @pytest.mark.asyncio
    async def test_collect_available_tools_with_async_methods(self):
        """Test collecting available tools with async tool service methods."""
        runtime = Mock()
        runtime.bus_manager = Mock()
        runtime.service_registry = Mock()

        # Mock tool service with async methods
        tool_service = Mock()
        tool_service.adapter_id = "api_tools"
        tool_service.get_available_tools = AsyncMock(return_value=["execute"])

        tool_info = Mock(spec=ToolInfo)
        tool_service.get_tool_info = AsyncMock(return_value=tool_info)

        runtime.service_registry.get_services_by_type.return_value = [tool_service]

        result = await _collect_available_tools(runtime)

        assert "api" in result
        assert len(result["api"]) == 1

    @pytest.mark.asyncio
    async def test_collect_available_tools_with_non_iterable_services(self, caplog):
        """Test collecting available tools with non-iterable tool services."""
        runtime = Mock()
        runtime.bus_manager = Mock()
        runtime.service_registry = Mock()

        # Return non-iterable
        runtime.service_registry.get_services_by_type.return_value = "not_iterable"

        result = await _collect_available_tools(runtime)

        assert result == {}
        assert "get_services_by_type('tool') returned non-iterable: <class 'str'>" in caplog.text

    @pytest.mark.asyncio
    async def test_collect_available_tools_with_invalid_tool_info_type(self):
        """Test collecting available tools with invalid tool info type."""
        runtime = Mock()
        runtime.bus_manager = Mock()
        runtime.service_registry = Mock()

        tool_service = Mock()
        tool_service.adapter_id = "bad_tools"
        tool_service.get_available_tools.return_value = ["bad_tool"]
        tool_service.get_tool_info.return_value = "not_tool_info"  # Invalid type

        runtime.service_registry.get_services_by_type.return_value = [tool_service]

        with pytest.raises(TypeError, match="returned invalid type for bad_tool"):
            await _collect_available_tools(runtime)

    @pytest.mark.asyncio
    async def test_collect_available_tools_with_tool_info_exception(self):
        """Test collecting available tools with tool info exception."""
        runtime = Mock()
        runtime.bus_manager = Mock()
        runtime.service_registry = Mock()

        tool_service = Mock()
        tool_service.adapter_id = "error_tools"
        tool_service.get_available_tools.return_value = ["error_tool"]
        tool_service.get_tool_info.side_effect = Exception("Tool info error")

        runtime.service_registry.get_services_by_type.return_value = [tool_service]

        with pytest.raises(Exception, match="Tool info error"):
            await _collect_available_tools(runtime)


# =============================================================================
# 8. USER MANAGEMENT TESTS
# =============================================================================


class TestUserManagement:
    """Test user management helper functions."""

    def test_extract_user_ids_from_context_with_none_inputs(self):
        """Test extracting user IDs with None inputs."""
        result = _extract_user_ids_from_context(None, None)
        assert result == set()

    def test_extract_user_ids_from_task_context(self, caplog):
        """Test extracting user IDs from task context."""
        task = Mock()
        task.context = Mock()
        task.context.user_id = "user_123"

        result = _extract_user_ids_from_context(task, None)

        assert "user_123" in result
        assert "Found user user_123 from task context" in caplog.text

    def test_extract_user_ids_from_thought_content_discord_mentions(self, caplog):
        """Test extracting user IDs from thought content with Discord mentions."""
        thought = Mock()
        thought.content = "Hello <@123456789> and <@987654321>!"
        # No context to avoid picking up mock context.user_id
        thought.context = None

        with caplog.at_level(logging.DEBUG):
            result = _extract_user_ids_from_context(None, thought)

        assert "123456789" in result
        assert "987654321" in result
        assert len(result) == 2
        assert "Found 2 users from Discord mentions:" in caplog.text

    def test_extract_user_ids_from_thought_content_id_patterns(self, caplog):
        """Test extracting user IDs from thought content with ID patterns."""
        thought = Mock()
        thought.content = "User ID: 555666777 contacted us, also ID:888999000"
        thought.context = None  # No context to avoid picking up mock user_id

        result = _extract_user_ids_from_context(None, thought)

        assert "555666777" in result
        assert "888999000" in result
        assert "Found 2 users from ID patterns" in caplog.text

    def test_extract_user_ids_from_thought_context(self, caplog):
        """Test extracting user IDs from thought context."""
        thought = Mock()
        thought.content = ""  # No content mentions
        thought.context = Mock()
        thought.context.user_id = "thought_user_456"

        result = _extract_user_ids_from_context(None, thought)

        assert "thought_user_456" in result
        assert "Found user thought_user_456 from thought context" in caplog.text

    @patch("ciris_engine.logic.context.system_snapshot_helpers.persistence.get_db_connection")
    def test_extract_user_ids_from_correlation_history(self, mock_get_conn, caplog):
        """Test extracting user IDs from correlation history."""
        task = Mock()
        task.context = Mock()
        task.context.correlation_id = "corr_123"
        task.context.user_id = None  # No task user_id to avoid picking it up

        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [{"user_id": "corr_user_1"}, {"user_id": "corr_user_2"}]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value.__enter__.return_value = mock_conn

        result = _extract_user_ids_from_context(task, None)

        assert "corr_user_1" in result
        assert "corr_user_2" in result
        assert "Found user corr_user_1 from correlation history" in caplog.text
        assert "Found user corr_user_2 from correlation history" in caplog.text

    @patch("ciris_engine.logic.context.system_snapshot_helpers.persistence.get_db_connection")
    def test_extract_user_ids_from_correlation_with_exception(self, mock_get_conn, caplog):
        """Test extracting user IDs from correlation with database exception."""
        task = Mock()
        task.context = Mock()
        task.context.correlation_id = "corr_error"
        task.context.user_id = None  # No task user_id

        mock_get_conn.side_effect = Exception("DB error")

        result = _extract_user_ids_from_context(task, None)

        assert len(result) == 0  # Should be empty set
        assert "Failed to extract users from correlation history: DB error" in caplog.text

    def test_json_serial_for_users_with_datetime(self):
        """Test JSON serializer for users with datetime object."""
        dt = datetime(2025, 1, 1, 12, 0, 0)
        result = _json_serial_for_users(dt)
        assert result == "2025-01-01T12:00:00"

    def test_json_serial_for_users_with_pydantic_model(self):
        """Test JSON serializer for users with Pydantic model."""
        model = Mock()
        model.model_dump.return_value = {"field": "value"}
        # Mock the hasattr check properly
        with patch("builtins.hasattr") as mock_hasattr:
            mock_hasattr.side_effect = lambda obj, attr: attr == "model_dump"
            result = _json_serial_for_users(model)
        assert result == {"field": "value"}

    def test_json_serial_for_users_with_other_object(self):
        """Test JSON serializer for users with other object types."""
        result = _json_serial_for_users(12345)
        assert result == "12345"

    @pytest.mark.asyncio
    async def test_enrich_user_profiles_with_existing_user(self, caplog):
        """Test enriching user profiles skips existing users."""
        memory_service = Mock()
        user_ids = {"existing_user"}
        channel_id = "test_channel"
        existing_profiles = [Mock()]
        existing_profiles[0].user_id = "existing_user"

        result = await _enrich_user_profiles(memory_service, user_ids, channel_id, existing_profiles)

        assert len(result) == 1
        assert "User existing_user already exists, skipping" in caplog.text

    @pytest.mark.asyncio
    async def test_enrich_user_profiles_with_new_user_valid_node(self, caplog):
        """Test enriching user profiles with new user and valid node."""
        memory_service = Mock()

        # Mock user node
        user_node = Mock()
        user_node.attributes = {
            "username": "test_user",
            "display_name": "Test User",
            "language": "en",
            "timezone": "UTC",
            "trust_level": 0.8,
            "last_seen": "2025-01-01T12:00:00Z",
            "first_seen": "2024-01-01T12:00:00Z",
        }
        memory_service.recall = AsyncMock(return_value=[user_node])

        # Mock edges
        with patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node") as mock_get_edges:
            mock_get_edges.return_value = []

        user_ids = {"new_user_123"}
        channel_id = "test_channel"
        existing_profiles = []

        # Mock database for recent messages
        with patch("ciris_engine.logic.context.system_snapshot_helpers.persistence.get_db_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_get_conn.return_value.__enter__.return_value = mock_conn

            result = await _enrich_user_profiles(memory_service, user_ids, channel_id, existing_profiles)

        assert len(result) == 1
        assert isinstance(result[0], UserProfile)
        assert result[0].user_id == "new_user_123"
        assert result[0].display_name == "test_user"
        assert result[0].trust_level == 0.8
        assert "Added user profile for new_user_123" in caplog.text

    @pytest.mark.asyncio
    async def test_enrich_user_profiles_with_pydantic_attributes(self):
        """Test enriching user profiles with Pydantic model attributes."""
        memory_service = Mock()

        # Mock user node with Pydantic attributes
        user_node = Mock()
        attrs_model = Mock()
        attrs_model.model_dump.return_value = {"username": "pydantic_user", "trust_level": 0.9}
        user_node.attributes = attrs_model
        memory_service.recall = AsyncMock(return_value=[user_node])

        with patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node") as mock_get_edges:
            mock_get_edges.return_value = []

        user_ids = {"pydantic_user"}
        existing_profiles = []

        with patch("ciris_engine.logic.context.system_snapshot_helpers.persistence.get_db_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_get_conn.return_value.__enter__.return_value = mock_conn

            result = await _enrich_user_profiles(memory_service, user_ids, None, existing_profiles)

        assert len(result) == 1
        assert result[0].display_name == "pydantic_user"

    @pytest.mark.asyncio
    async def test_enrich_user_profiles_with_corrupted_last_seen(self, caplog):
        """Test enriching user profiles with corrupted last_seen data."""
        memory_service = Mock()

        # Mock user node with corrupted data
        user_node = Mock()
        user_node.attributes = {
            "username": "corrupted_user",
            "last_seen": "[insert timestamp here]",  # Template placeholder
        }
        memory_service.recall = AsyncMock(return_value=[user_node])
        memory_service.memorize = AsyncMock()  # Mock the fix operation

        with patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node") as mock_get_edges:
            mock_get_edges.return_value = []

        user_ids = {"corrupted_user"}
        existing_profiles = []

        with patch("ciris_engine.logic.context.system_snapshot_helpers.persistence.get_db_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_get_conn.return_value.__enter__.return_value = mock_conn

            result = await _enrich_user_profiles(memory_service, user_ids, None, existing_profiles)

        assert len(result) == 1
        assert "FIELD_FAILED_VALIDATION: User corrupted_user has invalid last_seen" in caplog.text

    @pytest.mark.asyncio
    async def test_enrich_user_profiles_with_no_user_node(self, caplog):
        """Test enriching user profiles with no user node found."""
        memory_service = Mock()
        memory_service.recall = AsyncMock(return_value=[])  # No user found

        user_ids = {"missing_user"}
        existing_profiles = []

        result = await _enrich_user_profiles(memory_service, user_ids, None, existing_profiles)

        assert len(result) == 0
        assert "Query returned 0 results for user missing_user" in caplog.text

    @pytest.mark.asyncio
    async def test_enrich_user_profiles_with_user_exception(self, caplog):
        """Test enriching user profiles with user processing exception."""
        memory_service = Mock()
        memory_service.recall = AsyncMock(side_effect=Exception("User error"))

        user_ids = {"error_user"}
        existing_profiles = []

        result = await _enrich_user_profiles(memory_service, user_ids, None, existing_profiles)

        assert len(result) == 0
        assert "Failed to enrich user error_user: User error" in caplog.text
