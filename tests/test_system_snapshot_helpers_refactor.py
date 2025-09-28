"""
Unit tests for system_snapshot_helpers.py refactoring.

Tests cover the complex functions before and after refactoring to ensure
behavioral compatibility and regression prevention.
"""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
from typing import List, Dict, Any, Optional

from ciris_engine.logic.context.system_snapshot_helpers import (
    _collect_available_tools,
    _validate_runtime_capabilities,
    _get_tool_services,
    _call_async_or_sync_method,
    _get_tool_info_safely,
    _extract_adapter_type,
    _validate_tool_infos
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
                parameters=ToolParameterSchema(type="object", properties={})
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
                parameters=ToolParameterSchema(type="object", properties={"param": {"type": "string"}})
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
        sync_service.get_tool_info = Mock(return_value=ToolInfo(
            name="sync_tool",
            description="Sync",
            parameters=ToolParameterSchema(type="object", properties={})
        ))

        # Create async tool service
        async_service = Mock()
        async_service.adapter_id = "async_adapter"
        async_service.get_available_tools = AsyncMock(return_value=["async_tool"])
        async_service.get_tool_info = AsyncMock(return_value=ToolInfo(
            name="async_tool",
            description="Async",
            parameters=ToolParameterSchema(type="object", properties={})
        ))

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
        mock_runtime = Mock(spec=['service_registry'])  # Only has service_registry
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
            name="test_tool",
            description="Test",
            parameters=ToolParameterSchema(type="object", properties={})
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
            ToolInfo(
                name="tool1",
                description="Test 1",
                parameters=ToolParameterSchema(type="object", properties={})
            ),
            ToolInfo(
                name="tool2",
                description="Test 2",
                parameters=ToolParameterSchema(type="object", properties={})
            )
        ]

        # Should not raise exception
        _validate_tool_infos(tool_infos)

    def test_validate_tool_infos_failure(self):
        """Test validating tool infos with wrong type."""
        tool_infos = [
            ToolInfo(
                name="tool1",
                description="Test 1",
                parameters=ToolParameterSchema(type="object", properties={})
            ),
            {"wrong": "type"}  # Wrong type
        ]

        with pytest.raises(TypeError, match="Non-ToolInfo object"):
            _validate_tool_infos(tool_infos)