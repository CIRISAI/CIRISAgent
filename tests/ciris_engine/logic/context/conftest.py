"""
Test fixtures for system snapshot testing.

Provides structured mock objects that match the original function patterns.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import BaseModel

from ciris_engine.schemas.adapters.tools import ToolInfo
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.runtime.system_context import ChannelContext, TaskSummary, ThoughtSummary, UserProfile
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


@pytest.fixture
def mock_task():
    """Create a proper Task mock with context."""
    task = Mock(spec=Task)
    task.task_id = "test_task_123"
    task.created_at = datetime.now(timezone.utc)
    task.status = Mock()
    task.status.value = "PROCESSING"

    # Create proper context structure
    task.context = Mock()
    task.context.user_id = "test_user_456"
    task.context.correlation_id = "corr_789"
    task.context.channel_id = "test_channel_101"

    return task


@pytest.fixture
def mock_thought():
    """Create a proper thought mock."""
    thought = Mock()
    thought.thought_id = "thought_123"
    thought.content = "Test thought content"
    thought.status = Mock()
    thought.status.value = "PROCESSING"
    thought.source_task_id = "task_456"
    thought.thought_type = "OBSERVATION"
    thought.thought_depth = 1

    # Create context
    thought.context = Mock()
    thought.context.user_id = "thought_user_789"

    return thought


@pytest.fixture
def mock_memory_service():
    """Create a proper memory service mock."""
    memory_service = Mock()
    memory_service.recall = AsyncMock(return_value=[])
    memory_service.search = AsyncMock(return_value=[])
    memory_service.memorize = AsyncMock()
    return memory_service


@pytest.fixture
def mock_resource_monitor():
    """Create a proper resource monitor mock."""
    monitor = Mock()
    monitor.snapshot = Mock()
    monitor.snapshot.critical = []
    monitor.snapshot.healthy = True
    return monitor


@pytest.fixture
def mock_service_registry():
    """Create a proper service registry mock."""
    registry = Mock()
    registry.get_provider_info.return_value = {"handlers": {}, "global_services": {}}
    registry.get_services_by_type.return_value = []
    return registry


@pytest.fixture
def mock_runtime():
    """Create a proper runtime mock."""
    runtime = Mock()
    runtime.current_shutdown_context = None

    # Mock adapter manager
    runtime.adapter_manager = Mock()
    runtime.adapter_manager._adapters = {}

    # Mock service registry and bus manager
    runtime.service_registry = Mock()
    runtime.service_registry.get_services_by_type.return_value = []
    runtime.bus_manager = Mock()

    return runtime


@pytest.fixture
def mock_secrets_service():
    """Create a proper secrets service mock."""
    return Mock()


@pytest.fixture
def mock_telemetry_service():
    """Create a proper telemetry service mock."""
    service = Mock()
    service.get_telemetry_summary = AsyncMock(return_value=None)
    return service


@pytest.fixture
def sample_user_node():
    """Create a sample user node for testing."""
    node = Mock()
    node.id = "user/test_user_123"
    node.type = NodeType.USER
    node.attributes = {
        "username": "test_user",
        "display_name": "Test User",
        "language": "en",
        "timezone": "UTC",
        "trust_level": 0.8,
        "last_seen": "2025-01-01T12:00:00Z",
        "first_seen": "2024-01-01T12:00:00Z",
    }
    return node


@pytest.fixture
def sample_identity_node():
    """Create a sample identity node for testing."""
    node = Mock()
    node.id = "agent/identity"
    node.attributes = {
        "agent_id": "test_agent_123",
        "description": "Test agent",
        "role_description": "Test role",
        "trust_level": 0.9,
        "permitted_actions": ["read", "write"],
        "restricted_capabilities": ["admin"],
    }
    return node


@pytest.fixture
def sample_channel_context():
    """Create a sample ChannelContext for testing."""
    return ChannelContext(
        channel_id="test_channel_123",
        channel_type="discord",
        created_at=datetime.now(timezone.utc),
        channel_name="Test Channel",
        is_private=False,
        participants=["user1", "user2"],
        is_active=True,
        message_count=100,
    )


@pytest.fixture
def sample_tool_info():
    """Create a sample ToolInfo for testing."""
    return ToolInfo(name="test_tool", description="A test tool", parameters={}, returns={"type": "string"})


@pytest.fixture
def mock_db_connection():
    """Create a mock database connection."""
    conn = Mock()
    cursor = Mock()
    cursor.fetchall.return_value = []
    conn.cursor.return_value = cursor
    return conn


@pytest.fixture
def mock_task_with_basemodel():
    """Create a BaseModel task mock for persistence functions."""
    task = Mock(spec=BaseModel)
    task.task_id = "task_123"
    task.created_at = datetime.now(timezone.utc)
    task.status = Mock()
    task.status.value = "COMPLETED"
    task.channel_id = "test_channel"
    task.priority = 5
    task.retry_count = 2
    task.parent_task_id = "parent_123"
    return task


@pytest.fixture
def mock_health_service():
    """Create a mock service with health methods."""
    service = Mock()
    health_status = Mock()
    health_status.is_healthy = True
    service.get_health_status = AsyncMock(return_value=health_status)
    service.get_circuit_breaker_status = Mock(return_value="CLOSED")
    return service


@pytest.fixture
def mock_tool_service():
    """Create a mock tool service."""
    service = Mock()
    service.adapter_id = "test_adapter"
    service.get_available_tools = Mock(return_value=["tool1", "tool2"])

    # Mock tool info
    tool_info = Mock(spec=ToolInfo)
    service.get_tool_info = Mock(return_value=tool_info)

    return service


@pytest.fixture
def mock_adapter_with_channels(sample_channel_context):
    """Create a mock adapter with channel list."""
    adapter = Mock()
    adapter.get_channel_list.return_value = [sample_channel_context]
    return adapter


@pytest.fixture(autouse=True)
def configure_test_logging():
    """Configure logging for tests to capture debug messages."""
    # Set logging level to DEBUG for our modules
    logger = logging.getLogger("ciris_engine.logic.context.system_snapshot_helpers")
    logger.setLevel(logging.DEBUG)

    yield

    # Reset logging level after test
    logger.setLevel(logging.INFO)


@pytest.fixture
def mock_context_with_channel():
    """Create a mock context with proper channel structure."""
    context = Mock()
    context.system_snapshot = Mock()
    context.system_snapshot.channel_id = "snapshot_channel_123"
    context.system_snapshot.channel_context = Mock()
    context.system_snapshot.channel_context.channel_id = "context_channel_456"
    return context


@pytest.fixture
def mock_pydantic_attributes():
    """Create a mock Pydantic attributes object."""
    attrs = Mock()
    attrs.model_dump.return_value = {"test_field": "test_value", "numeric_field": 42}
    return attrs


# Fixtures for user enrichment testing
@pytest.fixture
def user_enrichment_setup(mock_memory_service, sample_user_node, mock_db_connection):
    """Set up complete user enrichment test scenario."""
    # Memory service returns user node
    mock_memory_service.recall.return_value = [sample_user_node]

    # Database returns empty results (no recent messages)
    mock_db_connection.cursor.return_value.fetchall.return_value = []

    return {"memory_service": mock_memory_service, "user_node": sample_user_node, "db_connection": mock_db_connection}


# =============================================================================
# CONTEXT ENRICHMENT FIXTURES
# =============================================================================


@pytest.fixture
def mock_enrichment_tool_info():
    """Create a ToolInfo marked for context enrichment."""
    from ciris_engine.schemas.adapters.tools import ToolParameterSchema

    return ToolInfo(
        name="test_list_items",
        description="List all available items for context enrichment",
        parameters=ToolParameterSchema(
            type="object",
            properties={
                "filter": {
                    "type": "string",
                    "description": "Optional filter",
                },
            },
            required=[],
        ),
        context_enrichment=True,
        context_enrichment_params={},
    )


@pytest.fixture
def mock_non_enrichment_tool_info():
    """Create a ToolInfo NOT marked for context enrichment."""
    from ciris_engine.schemas.adapters.tools import ToolParameterSchema

    return ToolInfo(
        name="test_action",
        description="Perform an action",
        parameters=ToolParameterSchema(
            type="object",
            properties={
                "target": {
                    "type": "string",
                    "description": "Action target",
                },
            },
            required=["target"],
        ),
        context_enrichment=False,
    )


@pytest.fixture
def mock_tool_execution_result():
    """Create a mock ToolExecutionResult."""
    from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus

    return ToolExecutionResult(
        tool_name="test_list_items",
        status=ToolExecutionStatus.COMPLETED,
        success=True,
        data={
            "count": 3,
            "items": [
                {"id": "item1", "name": "Item 1"},
                {"id": "item2", "name": "Item 2"},
                {"id": "item3", "name": "Item 3"},
            ],
        },
        error=None,
        correlation_id="test-corr-123",
    )


@pytest.fixture
def mock_enrichment_tool_service(mock_enrichment_tool_info, mock_tool_execution_result):
    """Create a mock tool service with enrichment tools."""
    service = Mock()
    service.adapter_id = "test_adapter"
    service.get_available_tools = AsyncMock(return_value=["test_list_items", "test_action"])
    service.get_tool_info = AsyncMock(return_value=mock_enrichment_tool_info)
    service.execute_tool = AsyncMock(return_value=mock_tool_execution_result)
    return service


@pytest.fixture
def mock_runtime_with_enrichment(mock_enrichment_tool_service):
    """Create a runtime mock with tool service that has enrichment tools."""
    runtime = Mock()
    runtime.current_shutdown_context = None

    # Mock adapter manager
    runtime.adapter_manager = Mock()
    runtime.adapter_manager._adapters = {}

    # Mock service registry with tool services
    runtime.service_registry = Mock()
    runtime.service_registry.get_services_by_type.return_value = [mock_enrichment_tool_service]
    runtime.bus_manager = Mock()

    return runtime
