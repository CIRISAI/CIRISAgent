"""
Discord-specific mock objects for testing.

Provides mocks for Discord components and tool handling.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from ciris_engine.schemas.adapters.tool_execution import ToolExecutionArgs, ToolHandlerContext
from ciris_engine.schemas.adapters.tools import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolInfo,
    ToolParameterSchema,
)
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
)


class MockDiscordClient:
    """Mock Discord client."""

    def __init__(self):
        self.user = MagicMock()
        self.user.id = 123456789
        self.user.name = "TestBot"
        self.guilds = []
        self.get_channel = MagicMock(return_value=None)
        self.get_guild = MagicMock(return_value=None)
        self.fetch_user = AsyncMock(return_value=None)


class MockToolRegistry:
    """Mock tool registry for testing tool handler."""

    def __init__(self):
        self.tools = {}
        self.handlers = {}
        self.schemas = {}
        self.descriptions = {}

    def add_tool(
        self,
        name: str,
        handler: Any,
        schema: Optional[Dict[str, Any]] = None,
        description: Optional[Any] = None,
    ):
        """Add a tool to the registry."""
        self.tools[name] = True
        self.handlers[name] = handler
        if schema:
            self.schemas[name] = schema
        if description:
            self.descriptions[name] = description

    def get_handler(self, tool_name: str) -> Optional[Any]:
        """Get handler for a tool."""
        return self.handlers.get(tool_name)

    def get_schema(self, tool_name: str) -> Optional[Any]:
        """Get schema for a tool."""
        return self.schemas.get(tool_name)

    def get_tools(self) -> Dict[str, Any]:
        """Get all registered tools."""
        return self.tools

    def get_tool_description(self, tool_name: str) -> Optional[Any]:
        """Get description for a tool."""
        return self.descriptions.get(tool_name)


class MockTimeService:
    """Mock time service for consistent time operations."""

    def __init__(self, fixed_time: Optional[datetime] = None):
        self.fixed_time = fixed_time or datetime.now(timezone.utc)

    def now(self) -> datetime:
        """Return current time."""
        return self.fixed_time


class MockPersistenceForDiscord:
    """Mock persistence layer for Discord tool testing."""

    def __init__(self):
        self.correlations = {}
        self.add_correlation_calls = []
        self.update_correlation_calls = []

    def add_correlation(self, correlation: ServiceCorrelation, time_service: Any) -> str:
        """Mock add_correlation."""
        self.correlations[correlation.correlation_id] = correlation
        self.add_correlation_calls.append(correlation)
        return correlation.correlation_id

    def update_correlation(self, request: CorrelationUpdateRequest, correlation_or_time_service: Any) -> bool:
        """Mock update_correlation."""
        self.update_correlation_calls.append(request)
        if request.correlation_id in self.correlations:
            corr = self.correlations[request.correlation_id]
            if request.status:
                corr.status = request.status
            if request.response_data:
                corr.response_data = request.response_data
            return True
        return False


def create_tool_execution_args(
    correlation_id: Optional[str] = None,
    thought_id: Optional[str] = None,
    task_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    timeout_seconds: float = 30.0,
    tool_specific_params: Optional[Dict[str, Any]] = None,
) -> ToolExecutionArgs:
    """Create a ToolExecutionArgs instance for testing."""
    return ToolExecutionArgs(
        correlation_id=correlation_id or str(uuid.uuid4()),
        thought_id=thought_id or "thought_001",
        task_id=task_id or "task_001",
        channel_id=channel_id or "channel_001",
        timeout_seconds=timeout_seconds,
        tool_specific_params=tool_specific_params or {},
    )


def create_tool_info(
    name: str = "test_tool",
    description: str = "A test tool",
    category: str = "testing",
    parameters: Optional[Dict[str, Any]] = None,
) -> ToolInfo:
    """Create a ToolInfo instance for testing."""
    if parameters is None:
        parameters = {
            "type": "object",
            "properties": {"param1": {"type": "string", "description": "Test parameter"}},
            "required": ["param1"],
        }

    return ToolInfo(
        name=name,
        description=description,
        category=category,
        parameters=ToolParameterSchema(**parameters),
        cost=0.0,
        when_to_use="Use for testing",
    )


def create_tool_execution_result(
    tool_name: str = "test_tool",
    status: ToolExecutionStatus = ToolExecutionStatus.COMPLETED,
    success: bool = True,
    data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> ToolExecutionResult:
    """Create a ToolExecutionResult for testing."""
    return ToolExecutionResult(
        tool_name=tool_name,
        status=status,
        success=success,
        data=data or {"result": "test_result"},
        error=error,
        correlation_id=correlation_id or str(uuid.uuid4()),
    )


class MockToolDescription:
    """Mock tool description for registry."""

    def __init__(
        self,
        name: str = "test_tool",
        description: str = "Test tool",
        category: str = "testing",
        parameters: Optional[List[Any]] = None,
        when_to_use: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.category = category
        self.parameters = parameters or []
        self.when_to_use = when_to_use


class MockToolParameter:
    """Mock tool parameter for descriptions."""

    def __init__(
        self,
        name: str,
        param_type: str = "string",
        description: str = "",
        required: bool = True,
        default: Any = None,
        enum: Optional[List[Any]] = None,
    ):
        self.name = name
        self.type = MagicMock(value=param_type)  # Mock enum with value attribute
        self.description = description
        self.required = required
        self.default = default
        self.enum = enum


def create_successful_tool_handler(result_data: Optional[Dict[str, Any]] = None):
    """Create an async tool handler that returns success."""

    async def handler(args: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": True, "data": result_data or {"result": "success"}}

    return handler


def create_failing_tool_handler(error_message: str = "Tool execution failed"):
    """Create an async tool handler that returns failure."""

    async def handler(args: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": error_message}

    return handler


def create_exception_tool_handler(exception: Optional[Exception] = None):
    """Create an async tool handler that raises an exception."""

    async def handler(args: Dict[str, Any]):
        raise exception or RuntimeError("Tool execution error")

    return handler


__all__ = [
    "MockDiscordClient",
    "MockToolRegistry",
    "MockTimeService",
    "MockPersistenceForDiscord",
    "MockToolDescription",
    "MockToolParameter",
    "create_tool_execution_args",
    "create_tool_info",
    "create_tool_execution_result",
    "create_successful_tool_handler",
    "create_failing_tool_handler",
    "create_exception_tool_handler",
]