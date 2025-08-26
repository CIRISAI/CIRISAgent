"""
Tests for system_snapshot.py corruption fix.

Specifically tests the fix for LLM-corrupted user node attributes like last_seen
with template placeholders like '2024-09-16T[insert current time]Z'.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.context.system_snapshot import build_system_snapshot
from ciris_engine.schemas.runtime.models import Task, TaskContext, ThoughtContext
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.services.graph_core import (
    GraphNode,
    GraphNodeAttributes,
    GraphScope,
    NodeType,
)
from tests.fixtures.mocks import (
    MockTelemetryService,
    MockResourceMonitor,
    MockMemoryService,
    MockRuntime,
    MockSecretsService,
    MockServiceRegistry,
    MockPersistence,
    create_mock_thought,
    create_mock_task
)


class MockThought:
    """Mock thought object for testing."""
    def __init__(self):
        self.id = "test_thought_id"
        self.status = ThoughtStatus.PROCESSING
        self.thought_type = ThoughtType.STANDARD
        self.content = "Test thought"
        self.context = ThoughtContext(
            task_id="test_task",
            correlation_id="test_correlation",
            round_number=1,
            depth=0
        )
        self.confidence = 0.8
        self.channel_id = "test_channel"


class TestUserNodeCorruptionFix:
    """Test the fix for corrupted user node attributes."""

    @pytest.fixture
    def mock_task(self):
        """Create a mock task."""
        return Task(
            task_id="test_task",
            channel_id="test_channel",
            description="Test task",
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(
                correlation_id="test_correlation",
                user_id="537080239679864862"
            )
        )

    @pytest.fixture
    def mock_thought(self):
        """Create a mock thought."""
        return MockThought()

    @pytest.fixture
    def mock_resource_monitor(self):
        """Create a mock resource monitor."""
        return MockResourceMonitor()

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service."""
        return MockMemoryService()

    @pytest.fixture
    def mock_graphql_provider(self):
        """Create a mock GraphQL provider."""
        mock = AsyncMock()
        mock.query = AsyncMock(return_value=[])
        mock.enrich_context = AsyncMock(return_value={})
        return mock

    @pytest.fixture
    def mock_telemetry_service(self):
        """Create a mock telemetry service."""
        return MockTelemetryService()

    @pytest.fixture
    def mock_secrets_service(self):
        """Create a mock secrets service."""
        return MockSecretsService()

    @pytest.fixture
    def mock_runtime(self):
        """Create a mock runtime."""
        return MockRuntime()

    @pytest.fixture
    def mock_service_registry(self):
        """Create a mock service registry."""
        return MockServiceRegistry()

    @pytest.mark.asyncio
    async def test_fix_template_placeholder_in_last_seen(
        self, 
        mock_task,
        mock_thought,
        mock_resource_monitor,
        mock_memory_service,
        mock_graphql_provider,
        mock_telemetry_service,
        mock_secrets_service,
        mock_runtime,
        mock_service_registry
    ):
        """Test that template placeholders in last_seen are detected and fixed."""
        user_id = "537080239679864862"
        mock_task.context.user_id = user_id
        
        # Mock user node with corrupted last_seen
        corrupted_attrs = {
            "username": "test_user",
            "last_seen": "2024-09-16T[insert current time]Z",
            "email": "test@example.com"
        }
        
        mock_user_node = MagicMock()
        mock_user_node.attributes = corrupted_attrs
        mock_user_node.id = f"user/{user_id}"
        mock_user_node.type = NodeType.USER
        mock_user_node.scope = GraphScope.LOCAL
        
        # Mock memory service query to return corrupted node
        mock_memory_service.query_nodes = AsyncMock(return_value=[mock_user_node])
        
        # Override recall to return our corrupted node
        original_recall = mock_memory_service.recall
        async def mock_recall_with_corruption(query):
            node_id = query.node_id if hasattr(query, "node_id") else str(query)
            if f"user/{user_id}" in node_id:
                return [mock_user_node]
            # Fall back to original behavior for non-user nodes
            return await original_recall(query)
        mock_memory_service.recall = AsyncMock(side_effect=mock_recall_with_corruption)
        
        # Also mock recall to return the corrupted node when queried
        async def mock_recall(query):
            node_id = query.node_id if hasattr(query, "node_id") else str(query)
            if f"user/{user_id}" in node_id:
                return [mock_user_node]
            return []
        mock_memory_service.recall = AsyncMock(side_effect=mock_recall)
        
        # Build system snapshot
        with patch('ciris_engine.logic.context.system_snapshot.logger') as mock_logger, \
             patch('ciris_engine.logic.context.system_snapshot.build_secrets_snapshot', return_value={}), \
             patch('ciris_engine.logic.context.system_snapshot.persistence') as mock_persistence:
            # Set up persistence mocks
            mock_persistence.get_recent_completed_tasks.return_value = []
            mock_persistence.get_top_tasks.return_value = []
            
            # Create proper queue status mock
            queue_status_mock = MagicMock()
            queue_status_mock.total_tasks = 0
            queue_status_mock.queue_size = 0
            queue_status_mock.active_tasks = 0
            queue_status_mock.deferred_tasks = 0
            queue_status_mock.paused = False
            mock_persistence.get_queue_status.return_value = queue_status_mock
            
            mock_persistence.get_db_connection.return_value.__enter__.return_value.cursor.return_value.fetchone.return_value = None
            snapshot = await build_system_snapshot(
                task=mock_task,
                thought=mock_thought,
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory_service,
                graphql_provider=mock_graphql_provider,
                telemetry_service=mock_telemetry_service,
                secrets_service=mock_secrets_service,
                runtime=mock_runtime,
                service_registry=mock_service_registry
            )
            
            # Check that error was logged
            assert any(
                "INVALID DATA" in str(call) and "template placeholder" in str(call)
                for call in mock_logger.error.call_args_list
            ), f"Expected error log not found. Actual calls: {mock_logger.error.call_args_list}"
            
            # Check that memorize was called to fix the node
            assert mock_memory_service.memorize.called, "memorize() should have been called to fix the corrupted node"
            
            # Check the fixed node
            call_args = mock_memory_service.memorize.call_args
            fixed_node = call_args[0][0]  # First positional argument
            
            assert isinstance(fixed_node, GraphNode)
            assert fixed_node.id == f"user/{user_id}"
            assert fixed_node.type == NodeType.USER
            assert fixed_node.scope == GraphScope.LOCAL
            
            # Check that last_seen was fixed (should be a valid ISO timestamp)
            fixed_attrs = fixed_node.attributes
            assert "last_seen" in fixed_attrs
            
            # The value should be parseable as datetime
            last_seen_value = fixed_attrs.get("last_seen")
            assert last_seen_value is not None, "last_seen should have been set"
            # Should not raise an exception
            datetime.fromisoformat(last_seen_value.replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_fix_unparseable_last_seen(
        self,
        mock_task,
        mock_thought,
        mock_resource_monitor,
        mock_memory_service,
        mock_graphql_provider,
        mock_telemetry_service,
        mock_secrets_service,
        mock_runtime,
        mock_service_registry
    ):
        """Test that unparseable last_seen values are detected and fixed."""
        user_id = "123456789"
        mock_task.context.user_id = user_id
        
        # Mock user node with unparseable last_seen
        corrupted_attrs = {
            "username": "test_user2",
            "last_seen": "not-a-date",
            "email": "test2@example.com"
        }
        
        mock_user_node = MagicMock()
        mock_user_node.attributes = corrupted_attrs
        mock_user_node.id = f"user/{user_id}"
        mock_user_node.type = NodeType.USER
        mock_user_node.scope = GraphScope.LOCAL
        
        # Mock memory service query to return corrupted node
        mock_memory_service.query_nodes = AsyncMock(return_value=[mock_user_node])
        
        # Override recall to return our corrupted node
        original_recall = mock_memory_service.recall
        async def mock_recall_with_corruption(query):
            node_id = query.node_id if hasattr(query, "node_id") else str(query)
            if f"user/{user_id}" in node_id:
                return [mock_user_node]
            # Fall back to original behavior for non-user nodes
            return await original_recall(query)
        mock_memory_service.recall = AsyncMock(side_effect=mock_recall_with_corruption)
        
        # Build system snapshot
        with patch('ciris_engine.logic.context.system_snapshot.logger') as mock_logger, \
             patch('ciris_engine.logic.context.system_snapshot.build_secrets_snapshot', return_value={}), \
             patch('ciris_engine.logic.context.system_snapshot.persistence') as mock_persistence:
            snapshot = await build_system_snapshot(
                task=mock_task,
                thought=mock_thought,
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory_service,
                graphql_provider=mock_graphql_provider,
                telemetry_service=mock_telemetry_service,
                secrets_service=mock_secrets_service,
                runtime=mock_runtime,
                service_registry=mock_service_registry
            )
            
            # Check that error was logged
            assert any(
                "INVALID DATA" in str(call) and "unparseable last_seen" in str(call)
                for call in mock_logger.error.call_args_list
            ), f"Expected error log not found. Actual calls: {mock_logger.error.call_args_list}"
            
            # Check that memorize was called to fix the node
            assert mock_memory_service.memorize.called
            
            # Check the fixed node
            call_args = mock_memory_service.memorize.call_args
            fixed_node = call_args[0][0]  # First positional argument
            
            assert isinstance(fixed_node, GraphNode)
            assert fixed_node.id == f"user/{user_id}"

    @pytest.mark.asyncio
    async def test_fix_invalid_type_last_seen(
        self,
        mock_task,
        mock_thought,
        mock_resource_monitor,
        mock_memory_service,
        mock_graphql_provider,
        mock_telemetry_service,
        mock_secrets_service,
        mock_runtime,
        mock_service_registry
    ):
        """Test that non-string/non-datetime last_seen values are detected and fixed."""
        user_id = "987654321"
        mock_task.context.user_id = user_id
        
        # Mock user node with invalid type last_seen
        corrupted_attrs = {
            "username": "test_user3",
            "last_seen": 12345,  # Invalid type - should be string or datetime
            "email": "test3@example.com"
        }
        
        mock_user_node = MagicMock()
        mock_user_node.attributes = corrupted_attrs
        mock_user_node.id = f"user/{user_id}"
        mock_user_node.type = NodeType.USER
        mock_user_node.scope = GraphScope.LOCAL
        
        # Mock memory service query to return corrupted node
        mock_memory_service.query_nodes = AsyncMock(return_value=[mock_user_node])
        
        # Override recall to return our corrupted node
        original_recall = mock_memory_service.recall
        async def mock_recall_with_corruption(query):
            node_id = query.node_id if hasattr(query, "node_id") else str(query)
            if f"user/{user_id}" in node_id:
                return [mock_user_node]
            # Fall back to original behavior for non-user nodes
            return await original_recall(query)
        mock_memory_service.recall = AsyncMock(side_effect=mock_recall_with_corruption)
        
        # Build system snapshot
        with patch('ciris_engine.logic.context.system_snapshot.logger') as mock_logger, \
             patch('ciris_engine.logic.context.system_snapshot.build_secrets_snapshot', return_value={}), \
             patch('ciris_engine.logic.context.system_snapshot.persistence') as mock_persistence:
            snapshot = await build_system_snapshot(
                task=mock_task,
                thought=mock_thought,
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory_service,
                graphql_provider=mock_graphql_provider,
                telemetry_service=mock_telemetry_service,
                secrets_service=mock_secrets_service,
                runtime=mock_runtime,
                service_registry=mock_service_registry
            )
            
            # Check that error was logged
            assert any(
                "INVALID DATA" in str(call) and "non-string/non-datetime" in str(call)
                for call in mock_logger.error.call_args_list
            ), f"Expected error log not found. Actual calls: {mock_logger.error.call_args_list}"
            
            # Check that memorize was called to fix the node
            assert mock_memory_service.memorize.called

    @pytest.mark.asyncio
    async def test_fix_continues_on_update_failure(
        self,
        mock_task,
        mock_thought,
        mock_resource_monitor,
        mock_memory_service,
        mock_graphql_provider,
        mock_telemetry_service,
        mock_secrets_service,
        mock_runtime,
        mock_service_registry
    ):
        """Test that processing continues even if the fix fails."""
        user_id = "555555555"
        mock_task.context.user_id = user_id
        
        # Mock user node with corrupted last_seen
        corrupted_attrs = {
            "username": "test_user4",
            "last_seen": "2024-09-16T[insert current time]Z",
            "email": "test4@example.com"
        }
        
        mock_user_node = MagicMock()
        mock_user_node.attributes = corrupted_attrs
        mock_user_node.id = f"user/{user_id}"
        mock_user_node.type = NodeType.USER
        mock_user_node.scope = GraphScope.LOCAL
        
        # Mock memory service query to return corrupted node
        mock_memory_service.query_nodes = AsyncMock(return_value=[mock_user_node])
        
        # Override recall to return our corrupted node
        original_recall = mock_memory_service.recall
        async def mock_recall_with_corruption(query):
            node_id = query.node_id if hasattr(query, "node_id") else str(query)
            if f"user/{user_id}" in node_id:
                return [mock_user_node]
            # Fall back to original behavior for non-user nodes
            return await original_recall(query)
        mock_memory_service.recall = AsyncMock(side_effect=mock_recall_with_corruption)
        
        # Make memorize fail
        mock_memory_service.memorize = AsyncMock(side_effect=Exception("Update failed"))
        
        # Build system snapshot
        with patch('ciris_engine.logic.context.system_snapshot.logger') as mock_logger, \
             patch('ciris_engine.logic.context.system_snapshot.build_secrets_snapshot', return_value={}), \
             patch('ciris_engine.logic.context.system_snapshot.persistence') as mock_persistence:
            # Should not raise an exception
            snapshot = await build_system_snapshot(
                task=mock_task,
                thought=mock_thought,
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory_service,
                graphql_provider=mock_graphql_provider,
                telemetry_service=mock_telemetry_service,
                secrets_service=mock_secrets_service,
                runtime=mock_runtime,
                service_registry=mock_service_registry
            )
            
            # Check that the failure was logged but processing continued
            assert any(
                "Failed to fix corrupted node" in str(call)
                for call in mock_logger.error.call_args_list
            ), f"Expected failure log not found. Actual calls: {mock_logger.error.call_args_list}"
            
            # Should still build a snapshot
            assert snapshot is not None
            assert hasattr(snapshot, 'user_profiles')

    @pytest.mark.asyncio
    async def test_valid_last_seen_not_modified(
        self,
        mock_task,
        mock_thought,
        mock_resource_monitor,
        mock_memory_service,
        mock_graphql_provider,
        mock_telemetry_service,
        mock_secrets_service,
        mock_runtime,
        mock_service_registry
    ):
        """Test that valid last_seen values are not modified."""
        user_id = "666666666"
        mock_task.context.user_id = user_id
        valid_timestamp = datetime.now(timezone.utc).isoformat()
        
        # Mock user node with valid last_seen
        valid_attrs = {
            "username": "test_user5",
            "last_seen": valid_timestamp,
            "email": "test5@example.com"
        }
        
        mock_user_node = MagicMock()
        mock_user_node.attributes = valid_attrs
        mock_user_node.id = f"user/{user_id}"
        mock_user_node.type = NodeType.USER
        mock_user_node.scope = GraphScope.LOCAL
        
        # Mock memory service query to return valid node
        mock_memory_service.query_nodes = AsyncMock(return_value=[mock_user_node])
        
        # Override recall to return our valid node
        original_recall = mock_memory_service.recall
        async def mock_recall_with_valid(query):
            node_id = query.node_id if hasattr(query, "node_id") else str(query)
            if f"user/{user_id}" in node_id:
                return [mock_user_node]
            # Fall back to original behavior for non-user nodes
            return await original_recall(query)
        mock_memory_service.recall = AsyncMock(side_effect=mock_recall_with_valid)
        
        # Build system snapshot
        with patch('ciris_engine.logic.context.system_snapshot.logger') as mock_logger, \
             patch('ciris_engine.logic.context.system_snapshot.build_secrets_snapshot', return_value={}), \
             patch('ciris_engine.logic.context.system_snapshot.persistence') as mock_persistence:
            snapshot = await build_system_snapshot(
                task=mock_task,
                thought=mock_thought,
                resource_monitor=mock_resource_monitor,
                memory_service=mock_memory_service,
                graphql_provider=mock_graphql_provider,
                telemetry_service=mock_telemetry_service,
                secrets_service=mock_secrets_service,
                runtime=mock_runtime,
                service_registry=mock_service_registry
            )
            
            # Check that no error was logged
            assert not any(
                "INVALID DATA" in str(call)
                for call in mock_logger.error.call_args_list
            ), f"Unexpected error log found. Actual calls: {mock_logger.error.call_args_list}"
            
            # Check that memorize was NOT called (no fix needed)
            assert not mock_memory_service.memorize.called, "memorize() should not be called for valid data"
            
            # Snapshot should exist
            assert snapshot is not None