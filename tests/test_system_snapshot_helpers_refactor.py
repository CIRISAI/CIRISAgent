"""
Unit tests for system_snapshot_helpers.py refactoring.

Tests cover the complex functions before and after refactoring to ensure
behavioral compatibility and regression prevention.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from ciris_engine.logic.context.system_snapshot_helpers import (
    _call_async_or_sync_method,
    _collect_available_tools,
    _collect_service_health,
    _convert_graph_node_to_channel_context,
    _create_user_memory_query,
    _extract_adapter_type,
    _extract_channel_from_search_results,
    _extract_user_from_task_context,
    _extract_user_from_thought_context,
    _extract_user_ids_from_context,
    _extract_users_from_correlation_history,
    _extract_users_from_thought_content,
    _get_initial_channel_info,
    _get_tool_info_safely,
    _get_tool_services,
    _perform_channel_search,
    _perform_direct_channel_lookup,
    _process_services_group,
    _process_single_service,
    _resolve_channel_context,
    _safe_get_circuit_breaker_status,
    _safe_get_health_status,
    _should_skip_user_enrichment,
    _validate_runtime_capabilities,
    _validate_tool_infos,
)
from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema


class TestCollectAvailableToolsBeforeRefactor:
    """Test the original _collect_available_tools function behavior."""

    @pytest.mark.asyncio
    async def test_collect_tools_with_sync_methods(self):
        """Test tool collection when service methods are synchronous."""
        # Create mock tool service with sync methods
        mock_tool_service = Mock()
        mock_tool_service.adapter_id = "discord_adapter"
        mock_tool_service.get_available_tools = Mock(return_value=["speak", "observe"])

        def mock_get_tool_info(tool_name):
            return ToolInfo(
                name=tool_name,
                description=f"Mock {tool_name} tool",
                parameters=ToolParameterSchema(type="object", properties={}),
            )

        mock_tool_service.get_tool_info = Mock(side_effect=mock_get_tool_info)

        # Create mock service registry
        mock_service_registry = Mock()
        mock_service_registry.get_services_by_type = Mock(return_value=[mock_tool_service])

        # Create mock runtime
        mock_runtime = Mock()
        mock_runtime.bus_manager = Mock()
        mock_runtime.service_registry = mock_service_registry

        # Test the function
        result = await _collect_available_tools(mock_runtime)

        # Verify results
        assert "discord" in result
        assert len(result["discord"]) == 2
        assert all(isinstance(tool, ToolInfo) for tool in result["discord"])
        assert result["discord"][0].name == "speak"
        assert result["discord"][1].name == "observe"

    @pytest.mark.asyncio
    async def test_collect_tools_with_async_methods(self):
        """Test tool collection when service methods are asynchronous."""
        # Create mock tool service with async methods
        mock_tool_service = Mock()
        mock_tool_service.adapter_id = "api_service"
        mock_tool_service.get_available_tools = AsyncMock(return_value=["query", "update"])

        async def mock_get_tool_info(tool_name):
            return ToolInfo(
                name=tool_name,
                description=f"Async {tool_name} tool",
                parameters=ToolParameterSchema(type="object", properties={"param": {"type": "string"}}),
            )

        mock_tool_service.get_tool_info = AsyncMock(side_effect=mock_get_tool_info)

        # Create mock service registry
        mock_service_registry = Mock()
        mock_service_registry.get_services_by_type = Mock(return_value=[mock_tool_service])

        # Create mock runtime
        mock_runtime = Mock()
        mock_runtime.bus_manager = Mock()
        mock_runtime.service_registry = mock_service_registry

        # Test the function
        result = await _collect_available_tools(mock_runtime)

        # Verify results
        assert "api" in result
        assert len(result["api"]) == 2
        assert all(isinstance(tool, ToolInfo) for tool in result["api"])

    @pytest.mark.asyncio
    async def test_collect_tools_no_runtime(self):
        """Test tool collection when runtime is None."""
        result = await _collect_available_tools(None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_collect_tools_no_bus_manager(self):
        """Test tool collection when runtime has no bus_manager."""
        mock_runtime = Mock()
        del mock_runtime.bus_manager  # Remove bus_manager attribute

        result = await _collect_available_tools(mock_runtime)
        assert result == {}

    @pytest.mark.asyncio
    async def test_collect_tools_invalid_tool_info_type(self):
        """Test tool collection when get_tool_info returns wrong type."""
        # Create mock tool service that returns wrong type
        mock_tool_service = Mock()
        mock_tool_service.adapter_id = "bad_adapter"
        mock_tool_service.get_available_tools = Mock(return_value=["bad_tool"])
        mock_tool_service.get_tool_info = Mock(return_value={"not": "a_tool_info"})  # Wrong type!

        # Create mock service registry
        mock_service_registry = Mock()
        mock_service_registry.get_services_by_type = Mock(return_value=[mock_tool_service])

        # Create mock runtime
        mock_runtime = Mock()
        mock_runtime.bus_manager = Mock()
        mock_runtime.service_registry = mock_service_registry

        # Should raise TypeError due to type validation
        with pytest.raises(TypeError, match="returned invalid type"):
            await _collect_available_tools(mock_runtime)

    @pytest.mark.asyncio
    async def test_collect_tools_non_iterable_services(self):
        """Test tool collection when get_services_by_type returns non-iterable."""
        # Create mock service registry that returns non-iterable
        mock_service_registry = Mock()
        mock_service_registry.get_services_by_type = Mock(return_value=MagicMock())  # Not iterable!

        # Create mock runtime
        mock_runtime = Mock()
        mock_runtime.bus_manager = Mock()
        mock_runtime.service_registry = mock_service_registry

        # Should handle gracefully
        result = await _collect_available_tools(mock_runtime)
        assert result == {}

    @pytest.mark.asyncio
    async def test_collect_tools_mixed_sync_async(self):
        """Test tool collection with mixed sync/async tool services."""
        # Create sync tool service
        sync_service = Mock()
        sync_service.adapter_id = "sync_adapter"
        sync_service.get_available_tools = Mock(return_value=["sync_tool"])
        sync_service.get_tool_info = Mock(
            return_value=ToolInfo(
                name="sync_tool", description="Sync", parameters=ToolParameterSchema(type="object", properties={})
            )
        )

        # Create async tool service
        async_service = Mock()
        async_service.adapter_id = "async_adapter"
        async_service.get_available_tools = AsyncMock(return_value=["async_tool"])
        async_service.get_tool_info = AsyncMock(
            return_value=ToolInfo(
                name="async_tool", description="Async", parameters=ToolParameterSchema(type="object", properties={})
            )
        )

        # Create mock service registry
        mock_service_registry = Mock()
        mock_service_registry.get_services_by_type = Mock(return_value=[sync_service, async_service])

        # Create mock runtime
        mock_runtime = Mock()
        mock_runtime.bus_manager = Mock()
        mock_runtime.service_registry = mock_service_registry

        # Test the function
        result = await _collect_available_tools(mock_runtime)

        # Verify both adapters are present
        assert "sync" in result
        assert "async" in result
        assert len(result["sync"]) == 1
        assert len(result["async"]) == 1


class TestHelperFunctions:
    """Test the extracted helper functions."""

    def test_validate_runtime_capabilities_valid(self):
        """Test runtime capabilities validation with valid runtime."""
        mock_runtime = Mock()
        mock_runtime.bus_manager = Mock()
        mock_runtime.service_registry = Mock()

        assert _validate_runtime_capabilities(mock_runtime) is True

    def test_validate_runtime_capabilities_none(self):
        """Test runtime capabilities validation with None runtime."""
        assert _validate_runtime_capabilities(None) is False

    def test_validate_runtime_capabilities_missing_attrs(self):
        """Test runtime capabilities validation with missing attributes."""
        mock_runtime = Mock(spec=["service_registry"])  # Only has service_registry
        mock_runtime.service_registry = Mock()

        assert _validate_runtime_capabilities(mock_runtime) is False

    def test_get_tool_services_valid(self):
        """Test getting tool services with valid registry."""
        mock_registry = Mock()
        mock_services = [Mock(), Mock()]
        mock_registry.get_services_by_type.return_value = mock_services

        result = _get_tool_services(mock_registry)
        assert result == mock_services
        mock_registry.get_services_by_type.assert_called_once_with("tool")

    def test_get_tool_services_non_iterable(self):
        """Test getting tool services with non-iterable response."""
        mock_registry = Mock()

        # Create a non-iterable object
        class NonIterable:
            pass

        mock_registry.get_services_by_type.return_value = NonIterable()

        result = _get_tool_services(mock_registry)
        assert result == []

    def test_get_tool_services_string(self):
        """Test getting tool services with string response."""
        mock_registry = Mock()
        mock_registry.get_services_by_type.return_value = "not_a_list"

        result = _get_tool_services(mock_registry)
        assert result == []

    @pytest.mark.asyncio
    async def test_call_async_or_sync_method_async(self):
        """Test calling async method."""
        mock_obj = Mock()

        async def async_method(arg):
            return f"async_result_{arg}"

        mock_obj.test_method = async_method

        result = await _call_async_or_sync_method(mock_obj, "test_method", "value")
        assert result == "async_result_value"

    @pytest.mark.asyncio
    async def test_call_async_or_sync_method_sync(self):
        """Test calling sync method."""
        mock_obj = Mock()
        mock_obj.test_method = Mock(return_value="sync_result")

        result = await _call_async_or_sync_method(mock_obj, "test_method", "value")
        assert result == "sync_result"
        mock_obj.test_method.assert_called_once_with("value")

    @pytest.mark.asyncio
    async def test_call_async_or_sync_method_missing(self):
        """Test calling non-existent method."""
        mock_obj = Mock(spec=[])  # Spec with empty list - no methods

        result = await _call_async_or_sync_method(mock_obj, "missing_method")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_tool_info_safely_success(self):
        """Test getting tool info successfully."""
        mock_service = Mock()
        mock_tool_info = ToolInfo(
            name="test_tool", description="Test", parameters=ToolParameterSchema(type="object", properties={})
        )
        mock_service.get_tool_info = Mock(return_value=mock_tool_info)

        result = await _get_tool_info_safely(mock_service, "test_tool", "adapter_id")
        assert result == mock_tool_info

    @pytest.mark.asyncio
    async def test_get_tool_info_safely_wrong_type(self):
        """Test getting tool info with wrong type."""
        mock_service = Mock()
        mock_service.get_tool_info = Mock(return_value={"wrong": "type"})

        with pytest.raises(TypeError, match="returned invalid type"):
            await _get_tool_info_safely(mock_service, "test_tool", "adapter_id")

    @pytest.mark.asyncio
    async def test_get_tool_info_safely_no_method(self):
        """Test getting tool info when method doesn't exist."""
        mock_service = Mock(spec=[])  # Spec with empty list - no methods

        result = await _get_tool_info_safely(mock_service, "test_tool", "adapter_id")
        assert result is None

    def test_extract_adapter_type_with_underscore(self):
        """Test extracting adapter type with underscore."""
        assert _extract_adapter_type("discord_adapter") == "discord"
        assert _extract_adapter_type("api_service_v2") == "api"

    def test_extract_adapter_type_without_underscore(self):
        """Test extracting adapter type without underscore."""
        assert _extract_adapter_type("cli") == "cli"
        assert _extract_adapter_type("mock") == "mock"

    def test_validate_tool_infos_success(self):
        """Test validating tool infos successfully."""
        tool_infos = [
            ToolInfo(name="tool1", description="Test 1", parameters=ToolParameterSchema(type="object", properties={})),
            ToolInfo(name="tool2", description="Test 2", parameters=ToolParameterSchema(type="object", properties={})),
        ]

        # Should not raise exception
        _validate_tool_infos(tool_infos)

    def test_validate_tool_infos_failure(self):
        """Test validating tool infos with wrong type."""
        tool_infos = [
            ToolInfo(name="tool1", description="Test 1", parameters=ToolParameterSchema(type="object", properties={})),
            {"wrong": "type"},  # Wrong type
        ]

        with pytest.raises(TypeError, match="Non-ToolInfo object"):
            _validate_tool_infos(tool_infos)


class TestServiceHealthHelperFunctions:
    """Test the service health helper functions."""

    @pytest.mark.asyncio
    async def test_safe_get_health_status_success(self):
        """Test getting health status successfully using legacy get_health_status method."""
        mock_service = Mock(spec=["get_health_status"])  # Only has get_health_status, not is_healthy
        mock_health_status = Mock()
        mock_health_status.is_healthy = True
        mock_service.get_health_status = AsyncMock(return_value=mock_health_status)

        has_method, is_healthy = await _safe_get_health_status(mock_service)
        assert has_method is True
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_safe_get_health_status_no_method(self):
        """Test getting health status when method doesn't exist."""
        mock_service = Mock(spec=[])  # No methods

        has_method, is_healthy = await _safe_get_health_status(mock_service)
        assert has_method is False
        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_safe_get_health_status_exception(self):
        """Test getting health status when method raises exception."""
        mock_service = Mock()
        mock_service.get_health_status = AsyncMock(side_effect=Exception("Health check failed"))

        has_method, is_healthy = await _safe_get_health_status(mock_service)
        assert has_method is True  # Has method but failed
        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_safe_get_health_status_no_is_healthy_attr(self):
        """Test getting health status when health status object lacks is_healthy."""
        mock_service = Mock()
        mock_health_status = Mock()
        # Remove is_healthy attribute
        del mock_health_status.is_healthy
        mock_service.get_health_status = AsyncMock(return_value=mock_health_status)

        has_method, is_healthy = await _safe_get_health_status(mock_service)
        assert has_method is True
        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_safe_get_health_status_with_is_healthy_method(self):
        """Test getting health status using ServiceProtocol is_healthy method."""
        mock_service = Mock()
        mock_service.is_healthy = AsyncMock(return_value=True)

        has_method, is_healthy = await _safe_get_health_status(mock_service)
        assert has_method is True
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_safe_get_circuit_breaker_status_success(self):
        """Test getting circuit breaker status successfully."""
        mock_service = Mock()
        mock_service.get_circuit_breaker_status = AsyncMock(return_value="CLOSED")

        has_method, status = await _safe_get_circuit_breaker_status(mock_service)
        assert has_method is True
        assert status == "CLOSED"

    @pytest.mark.asyncio
    async def test_safe_get_circuit_breaker_status_no_method(self):
        """Test getting circuit breaker status when method doesn't exist."""
        mock_service = Mock(spec=[])  # No methods

        has_method, status = await _safe_get_circuit_breaker_status(mock_service)
        assert has_method is False
        assert status == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_safe_get_circuit_breaker_status_none_result(self):
        """Test getting circuit breaker status when method returns None."""
        mock_service = Mock()
        mock_service.get_circuit_breaker_status = AsyncMock(return_value=None)

        has_method, status = await _safe_get_circuit_breaker_status(mock_service)
        assert has_method is True
        assert status == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_safe_get_circuit_breaker_status_exception(self):
        """Test getting circuit breaker status when method raises exception."""
        mock_service = Mock()
        mock_service.get_circuit_breaker_status = AsyncMock(side_effect=Exception("CB check failed"))

        has_method, status = await _safe_get_circuit_breaker_status(mock_service)
        assert has_method is True  # Has method but failed
        assert status == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_process_single_service(self):
        """Test processing a single service."""
        mock_service = Mock()
        # Use ServiceProtocol is_healthy method
        mock_service.is_healthy = AsyncMock(return_value=True)
        mock_service.get_circuit_breaker_status = AsyncMock(return_value="OPEN")

        service_health = {}
        circuit_breaker_status = {}

        await _process_single_service(mock_service, "test.service", service_health, circuit_breaker_status)

        assert service_health["test.service"] is True
        assert circuit_breaker_status["test.service"] == "OPEN"

    @pytest.mark.asyncio
    async def test_process_services_group(self):
        """Test processing a group of services."""
        # Create mock services with ServiceProtocol is_healthy methods
        mock_service1 = Mock()
        mock_service1.is_healthy = AsyncMock(return_value=True)
        mock_service1.get_circuit_breaker_status = AsyncMock(return_value="CLOSED")

        mock_service2 = Mock()
        mock_service2.is_healthy = AsyncMock(return_value=False)
        mock_service2.get_circuit_breaker_status = AsyncMock(return_value="OPEN")

        services_group = {"llm": [mock_service1], "memory": [mock_service2]}

        service_health = {}
        circuit_breaker_status = {}

        await _process_services_group(services_group, "handler", service_health, circuit_breaker_status)

        assert service_health["handler.llm"] is True
        assert circuit_breaker_status["handler.llm"] == "CLOSED"
        assert service_health["handler.memory"] is False
        assert circuit_breaker_status["handler.memory"] == "OPEN"

    @pytest.mark.asyncio
    async def test_collect_service_health_success(self):
        """Test collecting service health successfully."""
        # Create mock service registry
        mock_registry = Mock()

        # Create mock services with ServiceProtocol is_healthy methods
        mock_service1 = Mock()
        mock_service1.is_healthy = AsyncMock(return_value=True)
        mock_service1.get_circuit_breaker_status = AsyncMock(return_value="CLOSED")

        mock_service2 = Mock()
        mock_service2.is_healthy = AsyncMock(return_value=False)
        mock_service2.get_circuit_breaker_status = AsyncMock(return_value="OPEN")

        # Mock registry info
        registry_info = {
            "handlers": {"handler1": {"llm": [mock_service1]}},
            "global_services": {"memory": [mock_service2]},
        }
        mock_registry.get_provider_info = Mock(return_value=registry_info)

        service_health, circuit_breaker_status = await _collect_service_health(mock_registry)

        assert service_health["handler1.llm"] is True
        assert circuit_breaker_status["handler1.llm"] == "CLOSED"
        assert service_health["global.memory"] is False
        assert circuit_breaker_status["global.memory"] == "OPEN"

    @pytest.mark.asyncio
    async def test_collect_service_health_no_registry(self):
        """Test collecting service health with no registry."""
        service_health, circuit_breaker_status = await _collect_service_health(None)

        assert service_health == {}
        assert circuit_breaker_status == {}

    @pytest.mark.asyncio
    async def test_collect_service_health_exception(self):
        """Test collecting service health when registry raises exception."""
        mock_registry = Mock()
        mock_registry.get_provider_info = Mock(side_effect=Exception("Registry error"))

        service_health, circuit_breaker_status = await _collect_service_health(mock_registry)

        assert service_health == {}
        assert circuit_breaker_status == {}


class TestChannelContextHelperFunctions:
    """Test the channel context helper functions."""

    def test_get_initial_channel_info_from_task(self):
        """Test getting channel info from task context."""
        # Mock task with channel context - use proper structure
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.system_snapshot = Mock()
        mock_task.context.system_snapshot.channel_context = Mock()
        mock_task.context.system_snapshot.channel_context.channel_id = "test_channel_123"

        channel_id, channel_context = _get_initial_channel_info(mock_task, None)

        assert channel_id == "test_channel_123"

    def test_get_initial_channel_info_from_thought(self):
        """Test getting channel info from thought context when task has no context."""
        # Mock thought with channel context - use proper structure
        mock_thought = Mock()
        mock_thought.context = Mock()
        mock_thought.context.system_snapshot = Mock()
        mock_thought.context.system_snapshot.channel_context = Mock()
        mock_thought.context.system_snapshot.channel_context.channel_id = "thought_channel_456"

        # Task with no context
        mock_task = Mock()
        mock_task.context = None

        channel_id, channel_context = _get_initial_channel_info(mock_task, mock_thought)

        assert channel_id == "thought_channel_456"

    def test_get_initial_channel_info_no_sources(self):
        """Test getting channel info when no sources have context."""
        channel_id, channel_context = _get_initial_channel_info(None, None)

        assert channel_id is None
        assert channel_context is None

    def test_get_initial_channel_info_task_takes_precedence(self):
        """Test that task context takes precedence over thought context."""
        # Mock task with channel context - use proper structure
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.system_snapshot = Mock()
        mock_task.context.system_snapshot.channel_context = Mock()
        mock_task.context.system_snapshot.channel_context.channel_id = "task_channel_123"

        # Mock thought with different channel context - use proper structure
        mock_thought = Mock()
        mock_thought.context = Mock()
        mock_thought.context.system_snapshot = Mock()
        mock_thought.context.system_snapshot.channel_context = Mock()
        mock_thought.context.system_snapshot.channel_context.channel_id = "thought_channel_456"

        channel_id, channel_context = _get_initial_channel_info(mock_task, mock_thought)

        assert channel_id == "task_channel_123"  # Task takes precedence

    @pytest.mark.asyncio
    async def test_perform_direct_channel_lookup_success(self):
        """Test successful direct channel lookup."""
        mock_memory_service = Mock()
        mock_nodes = [Mock(id="channel/test_123")]
        mock_memory_service.recall = AsyncMock(return_value=mock_nodes)

        result = await _perform_direct_channel_lookup(mock_memory_service, "test_123")

        assert result == mock_nodes
        mock_memory_service.recall.assert_called_once()

    @pytest.mark.asyncio
    async def test_perform_direct_channel_lookup_empty(self):
        """Test direct channel lookup with no results."""
        mock_memory_service = Mock()
        mock_memory_service.recall = AsyncMock(return_value=[])

        result = await _perform_direct_channel_lookup(mock_memory_service, "test_123")

        assert result == []

    @pytest.mark.asyncio
    async def test_perform_channel_search_success(self):
        """Test successful channel search."""
        mock_memory_service = Mock()
        mock_results = [Mock(id="channel/test_123")]
        mock_memory_service.search = AsyncMock(return_value=mock_results)

        result = await _perform_channel_search(mock_memory_service, "test_123")

        assert result == mock_results
        mock_memory_service.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_perform_channel_search_empty(self):
        """Test channel search with no results."""
        mock_memory_service = Mock()
        mock_memory_service.search = AsyncMock(return_value=[])

        result = await _perform_channel_search(mock_memory_service, "test_123")

        assert result == []

    def test_extract_channel_from_search_results_by_id(self):
        """Test extracting channel from search results by node ID."""
        mock_node1 = Mock()
        mock_node1.id = "channel/test_123"
        mock_node1.attributes = {"channel_id": "test_123"}

        mock_node2 = Mock()
        mock_node2.id = "other/node"
        mock_node2.attributes = {"channel_id": "other"}

        search_results = [mock_node1, mock_node2]

        result = _extract_channel_from_search_results(search_results, "test_123")

        assert result == mock_node1

    def test_extract_channel_from_search_results_by_attribute(self):
        """Test extracting channel from search results by channel_id attribute."""
        mock_node1 = Mock()
        mock_node1.id = "some/other/id"
        mock_node1.attributes = {"channel_id": "test_123", "name": "Test Channel"}

        search_results = [mock_node1]

        result = _extract_channel_from_search_results(search_results, "test_123")

        assert result == mock_node1

    def test_extract_channel_from_search_results_model_dump(self):
        """Test extracting channel when attributes is a model with model_dump()."""
        mock_node = Mock()
        mock_node.id = "some/other/id"

        # Mock attributes that has model_dump method
        mock_attributes = Mock()
        mock_attributes.model_dump.return_value = {"channel_id": "test_123"}
        mock_node.attributes = mock_attributes

        search_results = [mock_node]

        result = _extract_channel_from_search_results(search_results, "test_123")

        assert result == mock_node
        mock_attributes.model_dump.assert_called_once()

    def test_extract_channel_from_search_results_not_found(self):
        """Test extracting channel when no matching results."""
        mock_node = Mock()
        mock_node.id = "other/node"
        mock_node.attributes = {"channel_id": "other_channel"}

        search_results = [mock_node]

        result = _extract_channel_from_search_results(search_results, "test_123")

        assert result is None

    def test_extract_channel_from_search_results_no_attributes(self):
        """Test extracting channel when node has no attributes."""
        mock_node = Mock()
        mock_node.id = "other/node"
        mock_node.attributes = None

        search_results = [mock_node]

        result = _extract_channel_from_search_results(search_results, "test_123")

        assert result is None

    def test_convert_graph_node_to_channel_context_success(self):
        """Test successful conversion of GraphNode to ChannelContext."""
        mock_node = Mock()
        mock_node.id = "channel/test_123"
        mock_node.attributes = {
            "channel_id": "test_123",
            "channel_type": "discord",
            "channel_name": "Test Channel",
            "is_private": False,
            "participants": ["user1", "user2"],
        }

        result = _convert_graph_node_to_channel_context(mock_node)

        assert result is not None
        assert result.channel_id == "test_123"
        assert result.channel_type == "discord"
        assert result.channel_name == "Test Channel"
        assert result.is_private is False
        assert result.participants == ["user1", "user2"]

    def test_convert_graph_node_to_channel_context_minimal(self):
        """Test conversion with minimal attributes."""
        mock_node = Mock()
        mock_node.id = "channel/test_456"
        mock_node.attributes = {"channel_id": "test_456"}

        result = _convert_graph_node_to_channel_context(mock_node)

        assert result is not None
        assert result.channel_id == "test_456"
        assert result.channel_type == "unknown"  # Default value

    def test_convert_graph_node_to_channel_context_no_attributes(self):
        """Test conversion when node has no attributes."""
        mock_node = Mock()
        mock_node.id = "channel/test_789"
        mock_node.attributes = None

        result = _convert_graph_node_to_channel_context(mock_node)

        assert result is None

    def test_convert_graph_node_to_channel_context_with_memorized_attributes(self):
        """Test conversion includes arbitrary memorized attributes."""
        mock_node = Mock()
        mock_node.id = "channel/test_123"
        mock_node.attributes = {
            "channel_id": "test_123",
            "channel_type": "discord",
            "channel_name": "Test Channel",
            # Agent memorized arbitrary attributes
            "favorite_topic": "python programming",
            "mood": "friendly",
            "last_joke": "Why do programmers prefer dark mode?",
            "member_count": 42,
            "channel_purpose": "discussing AI development",
        }

        result = _convert_graph_node_to_channel_context(mock_node)

        assert result is not None
        assert result.channel_id == "test_123"
        assert result.channel_type == "discord"
        assert result.channel_name == "Test Channel"

        # Check memorized attributes are preserved as strings
        assert "favorite_topic" in result.memorized_attributes
        assert result.memorized_attributes["favorite_topic"] == "python programming"
        assert result.memorized_attributes["mood"] == "friendly"
        assert result.memorized_attributes["last_joke"] == "Why do programmers prefer dark mode?"
        assert result.memorized_attributes["member_count"] == "42"  # Converted to string
        assert result.memorized_attributes["channel_purpose"] == "discussing AI development"

    @pytest.mark.asyncio
    async def test_resolve_channel_context_success(self):
        """Test successful channel context resolution."""
        # Mock task with channel context - use proper structure
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.system_snapshot = Mock()
        mock_task.context.system_snapshot.channel_context = Mock()
        mock_task.context.system_snapshot.channel_context.channel_id = "test_channel_123"

        # Mock memory service
        mock_memory_service = Mock()
        mock_channel_node = Mock(id="channel/test_channel_123")
        mock_channel_node.attributes = {"channel_id": "test_channel_123", "channel_type": "discord"}
        mock_nodes = [mock_channel_node]
        mock_memory_service.recall = AsyncMock(return_value=mock_nodes)

        channel_id, channel_context = await _resolve_channel_context(mock_task, None, mock_memory_service)

        assert channel_id == "test_channel_123"
        assert channel_context is not None  # Should now be a ChannelContext object
        assert hasattr(channel_context, "channel_id")
        assert channel_context.channel_id == "test_channel_123"

    @pytest.mark.asyncio
    async def test_resolve_channel_context_with_search_fallback(self):
        """Test channel context resolution with search fallback."""
        # Mock task with channel context - use proper structure
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.system_snapshot = Mock()
        mock_task.context.system_snapshot.channel_context = Mock()
        mock_task.context.system_snapshot.channel_context.channel_id = "test_channel_123"

        # Mock memory service - direct lookup fails, search succeeds
        mock_memory_service = Mock()
        mock_memory_service.recall = AsyncMock(return_value=[])  # Direct lookup fails
        mock_found_node = Mock(id="channel/test_channel_123", attributes={"channel_id": "test_channel_123"})
        mock_search_results = [mock_found_node]
        mock_memory_service.search = AsyncMock(return_value=mock_search_results)

        channel_id, channel_context = await _resolve_channel_context(mock_task, None, mock_memory_service)

        assert channel_id == "test_channel_123"
        assert channel_context is not None  # Should now be a ChannelContext object from search
        assert hasattr(channel_context, "channel_id")
        assert channel_context.channel_id == "test_channel_123"

    @pytest.mark.asyncio
    async def test_resolve_channel_context_no_memory_service(self):
        """Test channel context resolution without memory service."""
        # Mock task with channel context - use proper structure
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.system_snapshot = Mock()
        mock_task.context.system_snapshot.channel_context = Mock()
        mock_task.context.system_snapshot.channel_context.channel_id = "test_channel_123"

        channel_id, channel_context = await _resolve_channel_context(mock_task, None, None)

        assert channel_id == "test_channel_123"

    @pytest.mark.asyncio
    async def test_resolve_channel_context_memory_exception(self):
        """Test channel context resolution when memory service raises exception."""
        # Mock task with channel context - use proper structure
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.system_snapshot = Mock()
        mock_task.context.system_snapshot.channel_context = Mock()
        mock_task.context.system_snapshot.channel_context.channel_id = "test_channel_123"

        # Mock memory service that raises exception
        mock_memory_service = Mock()
        mock_memory_service.recall = AsyncMock(side_effect=Exception("Memory error"))

        channel_id, channel_context = await _resolve_channel_context(mock_task, None, mock_memory_service)

        assert channel_id == "test_channel_123"

    @pytest.mark.asyncio
    async def test_resolve_channel_context_search_not_found(self):
        """Test channel context resolution when search doesn't find anything."""
        # Mock task with channel context - use proper structure
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.system_snapshot = Mock()
        mock_task.context.system_snapshot.channel_context = Mock()
        mock_task.context.system_snapshot.channel_context.channel_id = "test_channel_123"
        original_context = mock_task.context.system_snapshot.channel_context

        # Mock memory service - both direct lookup and search fail
        mock_memory_service = Mock()
        mock_memory_service.recall = AsyncMock(return_value=[])  # Direct lookup fails
        mock_memory_service.search = AsyncMock(return_value=[])  # Search also fails

        channel_id, channel_context = await _resolve_channel_context(mock_task, None, mock_memory_service)

        assert channel_id == "test_channel_123"
        assert channel_context == original_context  # Should remain the original context


class TestUserExtractionHelperFunctions:
    """Test user extraction helper functions."""

    def test_extract_user_from_task_context_with_user_id(self):
        """Test extracting user from task context with user_id."""
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.user_id = "user_123"

        user_ids = set()
        _extract_user_from_task_context(mock_task, user_ids)
        assert user_ids == {"user_123"}

    def test_extract_user_from_task_context_no_context(self):
        """Test extracting user from task with no context."""
        mock_task = Mock()
        mock_task.context = None

        user_ids = set()
        _extract_user_from_task_context(mock_task, user_ids)
        assert user_ids == set()

    def test_extract_user_from_task_context_no_user_id(self):
        """Test extracting user from task context without user_id."""
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.user_id = None

        user_ids = set()
        _extract_user_from_task_context(mock_task, user_ids)
        assert user_ids == set()

    def test_extract_user_from_thought_context_with_user_id(self):
        """Test extracting user from thought context with user_id."""
        mock_thought = Mock()
        mock_thought.context = Mock()
        mock_thought.context.user_id = "user_456"

        user_ids = set()
        _extract_user_from_thought_context(mock_thought, user_ids)
        assert user_ids == {"user_456"}

    def test_extract_user_from_thought_context_no_context(self):
        """Test extracting user from thought with no context."""
        mock_thought = Mock()
        mock_thought.context = None

        user_ids = set()
        _extract_user_from_thought_context(mock_thought, user_ids)
        assert user_ids == set()

    def test_extract_user_from_thought_context_no_user_id(self):
        """Test extracting user from thought context without user_id."""
        mock_thought = Mock()
        mock_thought.context = Mock()
        mock_thought.context.user_id = None

        user_ids = set()
        _extract_user_from_thought_context(mock_thought, user_ids)
        assert user_ids == set()

    def test_extract_users_from_correlation_history_success(self):
        """Test extracting users from correlation history."""
        # Mock task with correlation ID
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.correlation_id = "corr_123"

        user_ids = set()

        # Mock the database connection and cursor
        import unittest.mock

        with unittest.mock.patch("ciris_engine.logic.context.system_snapshot_helpers.persistence") as mock_persistence:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = [
                {"user_id": "user_123"},
                {"user_id": "user_456"},
                {"user_id": "user_123"},  # Duplicate
            ]
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = Mock(return_value=mock_conn)
            mock_conn.__exit__ = Mock(return_value=None)
            mock_persistence.get_db_connection.return_value = mock_conn

            _extract_users_from_correlation_history(mock_task, user_ids)

        # Should have extracted unique user IDs
        assert user_ids == {"user_123", "user_456"}

    def test_extract_users_from_correlation_history_no_correlation_id(self):
        """Test extracting users from correlation history without correlation_id."""
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.correlation_id = None

        user_ids = set()
        _extract_users_from_correlation_history(mock_task, user_ids)
        assert user_ids == set()

    def test_extract_users_from_correlation_history_exception(self):
        """Test extracting users from correlation history when exception occurs."""
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.correlation_id = "corr_123"

        user_ids = set()

        # Mock database connection to raise exception
        import unittest.mock

        with unittest.mock.patch("ciris_engine.logic.context.system_snapshot_helpers.persistence") as mock_persistence:
            mock_persistence.get_db_connection.side_effect = Exception("Database error")

            _extract_users_from_correlation_history(mock_task, user_ids)

        # Should handle exception gracefully
        assert user_ids == set()

    def test_extract_users_from_thought_content_with_discord_mentions(self):
        """Test extracting users from thought content with Discord mentions."""
        mock_thought = Mock()
        mock_thought.content = "Hello <@123456789> and <@987654321>, please review this."

        user_ids = set()
        _extract_users_from_thought_content(mock_thought, user_ids)
        assert user_ids == {"123456789", "987654321"}

    def test_extract_users_from_thought_content_with_id_patterns(self):
        """Test extracting users from thought content with ID: patterns."""
        mock_thought = Mock()
        mock_thought.content = "User ID: 123456 and another ID:  789012 found."

        user_ids = set()
        _extract_users_from_thought_content(mock_thought, user_ids)
        assert user_ids == {"123456", "789012"}

    def test_extract_users_from_thought_content_mixed_patterns(self):
        """Test extracting users from thought content with mixed patterns."""
        mock_thought = Mock()
        mock_thought.content = "Hello <@123456789> and user ID: 555666 are mentioned."

        user_ids = set()
        _extract_users_from_thought_content(mock_thought, user_ids)
        assert user_ids == {"123456789", "555666"}

    def test_extract_users_from_thought_content_no_mentions(self):
        """Test extracting users from thought content without mentions."""
        mock_thought = Mock()
        mock_thought.content = "This is a regular message without mentions."

        user_ids = set()
        _extract_users_from_thought_content(mock_thought, user_ids)
        assert user_ids == set()

    def test_extract_users_from_thought_content_no_content(self):
        """Test extracting users from thought with no content."""
        mock_thought = Mock()
        mock_thought.content = None

        user_ids = set()
        _extract_users_from_thought_content(mock_thought, user_ids)
        assert user_ids == set()

    def test_extract_users_from_thought_content_empty_content(self):
        """Test extracting users from thought with empty content."""
        mock_thought = Mock()
        mock_thought.content = ""

        user_ids = set()
        _extract_users_from_thought_content(mock_thought, user_ids)
        assert user_ids == set()

    def test_extract_user_ids_from_context_combined(self):
        """Test extracting user IDs from combined context sources."""
        # Mock task with user and correlation ID
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.user_id = "user_from_task"
        mock_task.context.correlation_id = "corr_123"

        # Mock thought with user and mentions
        mock_thought = Mock()
        mock_thought.context = Mock()
        mock_thought.context.user_id = "user_from_thought"
        mock_thought.content = "Hello <@999888777>, check this out. ID: 111222333"

        # Mock database for correlation history
        import unittest.mock

        with unittest.mock.patch("ciris_engine.logic.context.system_snapshot_helpers.persistence") as mock_persistence:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = [{"user_id": "user_from_correlation"}]
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = Mock(return_value=mock_conn)
            mock_conn.__exit__ = Mock(return_value=None)
            mock_persistence.get_db_connection.return_value = mock_conn

            result = _extract_user_ids_from_context(mock_task, mock_thought)

        # Should return all unique user IDs from all sources
        expected_users = {"user_from_task", "user_from_thought", "999888777", "111222333", "user_from_correlation"}
        assert result == expected_users

    def test_extract_user_ids_from_context_no_sources(self):
        """Test extracting user IDs when no sources provide users."""
        # Mock task and thought with no user info
        mock_task = Mock()
        mock_task.context = None

        mock_thought = Mock()
        mock_thought.context = None
        mock_thought.content = "No mentions here."

        result = _extract_user_ids_from_context(mock_task, mock_thought)
        assert result == set()

    def test_extract_user_ids_from_context_duplicate_removal(self):
        """Test that duplicate user IDs are removed."""
        # Mock task with user ID
        mock_task = Mock()
        mock_task.context = Mock()
        mock_task.context.user_id = "duplicate_user"
        mock_task.context.correlation_id = "corr_123"

        # Mock thought with same user and mention
        mock_thought = Mock()
        mock_thought.context = Mock()
        mock_thought.context.user_id = "duplicate_user"
        mock_thought.content = "Hello <@duplicate_user>, self-mention."

        # Mock database for correlation history with same user
        import unittest.mock

        with unittest.mock.patch("ciris_engine.logic.context.system_snapshot_helpers.persistence") as mock_persistence:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = [{"user_id": "duplicate_user"}]
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = Mock(return_value=mock_conn)
            mock_conn.__exit__ = Mock(return_value=None)
            mock_persistence.get_db_connection.return_value = mock_conn

            result = _extract_user_ids_from_context(mock_task, mock_thought)

        # Should only appear once despite being in all sources
        assert result == {"duplicate_user"}


class TestUserProfileEnrichmentHelperFunctions:
    """Test user profile enrichment helper functions."""

    def test_should_skip_user_enrichment_existing_user(self):
        """Test skipping user that already exists."""
        existing_user_ids = {"user_123", "user_456"}

        result = _should_skip_user_enrichment("user_123", existing_user_ids)
        assert result is True

    def test_should_skip_user_enrichment_new_user(self):
        """Test not skipping user that doesn't exist."""
        existing_user_ids = {"user_123", "user_456"}

        result = _should_skip_user_enrichment("user_789", existing_user_ids)
        assert result is False

    def test_create_user_memory_query(self):
        """Test creating memory query for user enrichment."""
        from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
        from ciris_engine.schemas.services.operations import MemoryQuery

        result = _create_user_memory_query("user_123")

        assert isinstance(result, MemoryQuery)
        assert result.node_id == "user/user_123"
        assert result.scope == GraphScope.LOCAL
        assert result.type == NodeType.USER
        assert result.include_edges is True
        assert result.depth == 2
