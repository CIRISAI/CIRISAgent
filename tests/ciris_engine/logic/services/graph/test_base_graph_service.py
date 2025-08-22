"""
Comprehensive test suite for BaseGraphService.

Tests all methods and edge cases in ciris_engine/logic/services/graph/base.py
FAIL FAST AND LOUD: Any missing schema should cause immediate test failure.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.services.graph.base import BaseGraphService
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus, MemoryQuery, MemoryOpResult


# Concrete implementation for testing abstract class
class TestGraphService(BaseGraphService):
    """Concrete implementation of BaseGraphService for testing."""
    
    def get_node_type(self) -> str:
        """Return test node type."""
        return "test_node"
    
    def get_status(self) -> "ServiceStatus":
        """Get service status - required by ServiceProtocol."""
        from ciris_engine.schemas.services.core import ServiceStatus
        return ServiceStatus(
            service_name=self.service_name,
            is_running=True,
            healthy=self._check_dependencies(),
            uptime_seconds=0.0,
            error_count=self._error_count
        )
    
    async def is_healthy(self) -> bool:
        """Check if healthy - required by ServiceProtocol."""
        return self._check_dependencies()
    
    def get_service_type(self) -> "ServiceType":
        """Get service type - required by ServiceProtocol."""
        from ciris_engine.schemas.runtime.enums import ServiceType
        return ServiceType.GRAPH
    
    async def start(self) -> None:
        """Start service - async override of base."""
        super().start()  # Call non-async parent
    
    async def stop(self) -> None:
        """Stop service - async override of base."""
        super().stop()  # Call non-async parent


@pytest.fixture
def time_service():
    """Create mock time service."""
    mock_time = MagicMock()
    mock_time.timestamp.return_value = 1234567890.0
    mock_time.now.return_value = datetime.now(timezone.utc)
    return mock_time


@pytest.fixture
def memory_bus():
    """Create mock memory bus."""
    mock_bus = MagicMock()
    mock_bus.memorize = AsyncMock()
    mock_bus.recall = AsyncMock()
    return mock_bus


@pytest.fixture
def graph_service(memory_bus, time_service):
    """Create test graph service instance."""
    service = TestGraphService(memory_bus=memory_bus, time_service=time_service)
    return service


class TestBaseGraphServiceInitialization:
    """Test service initialization."""

    def test_init_with_dependencies(self, memory_bus, time_service):
        """Test initialization with all dependencies."""
        service = TestGraphService(memory_bus=memory_bus, time_service=time_service)
        
        assert service.service_name == "TestGraphService"
        assert service._memory_bus == memory_bus
        assert service._time_service == time_service
        assert service._request_count == 0
        assert service._error_count == 0
        assert service._total_response_time == 0.0
        assert service._start_time is None
        assert service._started is False

    def test_init_without_dependencies(self):
        """Test initialization without dependencies."""
        service = TestGraphService()
        
        assert service.service_name == "TestGraphService"
        assert service._memory_bus is None
        assert service._time_service is None
        assert service._started is False

    def test_set_memory_bus(self, memory_bus):
        """Test setting memory bus after initialization."""
        service = TestGraphService()
        service._set_memory_bus(memory_bus)
        
        assert service._memory_bus == memory_bus

    def test_set_time_service(self, time_service):
        """Test setting time service after initialization."""
        service = TestGraphService()
        service._set_time_service(time_service)
        
        assert service._time_service == time_service


class TestBaseGraphServiceLifecycle:
    """Test service lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_without_telemetry(self, graph_service):
        """Test starting service without telemetry."""
        with patch('ciris_engine.logic.services.graph.base.logger') as mock_logger:
            await graph_service.start()
            
            assert graph_service._start_time is not None
            assert graph_service._started is True
            mock_logger.info.assert_called_once_with("TestGraphService started")

    @pytest.mark.asyncio
    async def test_start_service(self, graph_service):
        """Test starting service sets proper state."""
        with patch('ciris_engine.logic.services.graph.base.logger') as mock_logger:
            await graph_service.start()
            
            assert graph_service._start_time is not None
            assert graph_service._started is True
            mock_logger.info.assert_called_once_with("TestGraphService started")

    @pytest.mark.asyncio
    async def test_stop(self, graph_service):
        """Test stopping service."""
        # Start first
        await graph_service.start()
        assert graph_service._started is True
        
        with patch('ciris_engine.logic.services.graph.base.logger') as mock_logger:
            await graph_service.stop()
            
            assert graph_service._started is False
            mock_logger.info.assert_called_once_with("TestGraphService stopped")


class TestBaseGraphServiceCapabilities:
    """Test service capabilities."""

    def test_get_capabilities(self, graph_service):
        """Test getting service capabilities."""
        caps = graph_service.get_capabilities()
        
        # FAIL FAST: ServiceCapabilities schema MUST exist
        assert isinstance(caps, ServiceCapabilities), "ServiceCapabilities schema is missing!"
        assert caps.service_name == "TestGraphService"
        assert "store_in_graph" in caps.actions
        assert "query_graph" in caps.actions
        assert "test_node" in caps.actions  # From get_node_type()
        assert caps.version == "1.0.0"

    def test_check_dependencies_with_memory_bus(self, graph_service):
        """Test checking dependencies with memory bus available."""
        assert graph_service._check_dependencies() is True

    def test_check_dependencies_without_memory_bus(self, time_service):
        """Test checking dependencies without memory bus."""
        service = TestGraphService(time_service=time_service)
        assert service._check_dependencies() is False

    def test_get_actions(self, graph_service):
        """Test getting supported actions."""
        actions = graph_service._get_actions()
        
        assert "store_in_graph" in actions
        assert "query_graph" in actions
        assert "test_node" in actions


class TestBaseGraphServiceMetrics:
    """Test metrics collection."""

    def test_collect_custom_metrics_with_all_dependencies(self, graph_service):
        """Test collecting custom metrics with all dependencies."""
        graph_service._request_count = 10
        graph_service._error_count = 2
        
        metrics = graph_service._collect_custom_metrics()
        
        assert metrics["memory_bus_available"] == 1.0
        assert metrics["time_service_available"] == 1.0
        assert metrics["graph_operations_total"] == 10.0
        assert metrics["graph_errors_total"] == 2.0

    def test_collect_custom_metrics_without_dependencies(self):
        """Test collecting custom metrics without dependencies."""
        service = TestGraphService()
        
        metrics = service._collect_custom_metrics()
        
        assert metrics["memory_bus_available"] == 0.0
        assert metrics["time_service_available"] == 0.0
        assert metrics["graph_operations_total"] == 0.0
        assert metrics["graph_errors_total"] == 0.0
    
    def test_collect_metrics_full(self, graph_service):
        """Test full metrics collection including base metrics."""
        # Set up state
        graph_service._request_count = 5
        graph_service._error_count = 1
        graph_service._total_response_time = 250.0  # 50ms average
        graph_service._started = True
        graph_service._start_time = datetime.now() - timedelta(seconds=30)
        
        metrics = graph_service._collect_metrics()
        
        # Check base metrics
        assert "uptime_seconds" in metrics
        assert metrics["uptime_seconds"] >= 30.0
        assert metrics["request_count"] == 5.0
        assert metrics["error_count"] == 1.0
        assert metrics["avg_response_time_ms"] == 50.0
        assert metrics["healthy"] == 1.0
        
        # Check custom metrics are included
        assert metrics["memory_bus_available"] == 1.0
        assert metrics["graph_operations_total"] == 5.0
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, graph_service):
        """Test the public get_metrics method."""
        graph_service._request_count = 3
        graph_service._started = True
        
        metrics = await graph_service.get_metrics()
        
        assert isinstance(metrics, dict)
        assert metrics["request_count"] == 3.0
        assert "healthy" in metrics

    def test_track_request(self, graph_service):
        """Test tracking a request."""
        initial_count = graph_service._request_count
        initial_time = graph_service._total_response_time
        
        graph_service._track_request(100.5)
        
        assert graph_service._request_count == initial_count + 1
        assert graph_service._total_response_time == initial_time + 100.5

    def test_track_error(self, graph_service):
        """Test tracking an error."""
        initial_count = graph_service._error_count
        
        graph_service._track_error()
        
        assert graph_service._error_count == initial_count + 1


class TestBaseGraphServiceStoreOperations:
    """Test graph storage operations."""

    @pytest.mark.asyncio
    async def test_store_in_graph_success(self, graph_service, memory_bus):
        """Test successful node storage."""
        # Create test node - FAIL FAST if GraphNode schema missing
        node = GraphNode(
            id="test-123",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={"created_by": "test", "metadata": {"test": "data"}}
        )
        
        # Mock successful storage
        memory_bus.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.OK,
            data=node
        )
        
        result = await graph_service.store_in_graph(node)
        
        assert result == "test-123"
        memory_bus.memorize.assert_called_once_with(node)

    @pytest.mark.asyncio
    async def test_store_in_graph_with_to_graph_node(self, graph_service, memory_bus):
        """Test storing object with to_graph_node method."""
        # Create mock object with to_graph_node method
        mock_obj = MagicMock()
        graph_node = GraphNode(
            id="converted-123",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes=GraphNodeAttributes(created_by="test")
        )
        mock_obj.to_graph_node.return_value = graph_node
        
        memory_bus.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.OK,
            data=graph_node
        )
        
        result = await graph_service.store_in_graph(mock_obj)
        
        assert result == "converted-123"
        mock_obj.to_graph_node.assert_called_once()
        memory_bus.memorize.assert_called_once_with(graph_node)

    @pytest.mark.asyncio
    async def test_store_in_graph_failure(self, graph_service, memory_bus):
        """Test failed node storage."""
        node = GraphNode(
            id="fail-123",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes=GraphNodeAttributes(created_by="test")
        )
        
        # Mock failed storage
        memory_bus.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.ERROR,
            error="Storage failed"
        )
        
        result = await graph_service.store_in_graph(node)
        
        assert result == ""  # Empty string on failure

    @pytest.mark.asyncio
    async def test_store_in_graph_no_memory_bus(self, time_service):
        """Test storing without memory bus - MUST FAIL FAST."""
        service = TestGraphService(time_service=time_service)
        
        node = GraphNode(
            id="test-123",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes=GraphNodeAttributes(created_by="test")
        )
        
        # FAIL FAST AND LOUD - RuntimeError expected
        with pytest.raises(RuntimeError, match="Memory bus not available"):
            await service.store_in_graph(node)


class TestBaseGraphServiceQueryOperations:
    """Test graph query operations."""

    @pytest.mark.asyncio
    async def test_query_graph_success_with_list(self, graph_service, memory_bus):
        """Test successful query returning list."""
        # FAIL FAST if MemoryQuery schema missing
        query = MemoryQuery(
            node_id="test_query",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL
        )
        
        nodes = [
            GraphNode(
                id=f"node-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes=GraphNodeAttributes(created_by="test")
            )
            for i in range(3)
        ]
        
        memory_bus.recall.return_value = MemoryOpResult(
            status=MemoryOpStatus.OK,
            data=nodes
        )
        
        result = await graph_service.query_graph(query)
        
        assert len(result) == 3
        assert result == nodes
        memory_bus.recall.assert_called_once_with(query)

    @pytest.mark.asyncio
    async def test_query_graph_success_with_single_node(self, graph_service, memory_bus):
        """Test successful query returning single node."""
        query = MemoryQuery(node_id="test_query", scope=GraphScope.LOCAL, type=NodeType.CONCEPT)
        
        node = GraphNode(
            id="single-node",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes=GraphNodeAttributes(created_by="test")
        )
        
        memory_bus.recall.return_value = MemoryOpResult(
            status=MemoryOpStatus.OK,
            data=node
        )
        
        result = await graph_service.query_graph(query)
        
        assert len(result) == 1
        assert result[0] == node

    @pytest.mark.asyncio
    async def test_query_graph_direct_list_result(self, graph_service, memory_bus):
        """Test query with direct list result (no MemoryOpResult wrapper)."""
        query = MemoryQuery(node_id="test_query", scope=GraphScope.LOCAL, type=NodeType.CONCEPT)
        
        nodes = [
            GraphNode(
                id=f"direct-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes=GraphNodeAttributes(created_by="test")
            )
            for i in range(2)
        ]
        
        memory_bus.recall.return_value = nodes
        
        result = await graph_service.query_graph(query)
        
        assert result == nodes

    @pytest.mark.asyncio
    async def test_query_graph_failure(self, graph_service, memory_bus):
        """Test failed query."""
        query = MemoryQuery(node_id="test_query", scope=GraphScope.LOCAL, type=NodeType.CONCEPT)
        
        memory_bus.recall.return_value = MemoryOpResult(
            status=MemoryOpStatus.ERROR,
            error="Query failed"
        )
        
        result = await graph_service.query_graph(query)
        
        assert result == []

    @pytest.mark.asyncio
    async def test_query_graph_no_memory_bus(self, time_service):
        """Test querying without memory bus."""
        service = TestGraphService(time_service=time_service)
        
        query = MemoryQuery(node_id="test_query", scope=GraphScope.LOCAL, type=NodeType.CONCEPT)
        
        with patch('ciris_engine.logic.services.graph.base.logger') as mock_logger:
            result = await service.query_graph(query)
            
            assert result == []
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_graph_unexpected_result_type(self, graph_service, memory_bus):
        """Test query with unexpected result type."""
        query = MemoryQuery(node_id="test_query", scope=GraphScope.LOCAL, type=NodeType.CONCEPT)
        
        # Return something unexpected
        memory_bus.recall.return_value = "unexpected string result"
        
        result = await graph_service.query_graph(query)
        
        assert result == []


class TestBaseGraphServiceAbstractMethods:
    """Test abstract method requirements."""

    def test_get_node_type_not_implemented(self):
        """Test that get_node_type must be implemented - FAIL FAST."""
        # Try to create instance without implementing abstract method
        class IncompleteService(BaseGraphService):
            pass
        
        # Should not be able to instantiate
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteService()

    def test_get_node_type_implemented(self, graph_service):
        """Test implemented get_node_type method."""
        assert graph_service.get_node_type() == "test_node"


class TestBaseGraphServiceEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_store_none_node(self, graph_service, memory_bus):
        """Test storing None as node."""
        memory_bus.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.ERROR,
            error="Invalid node"
        )
        
        result = await graph_service.store_in_graph(None)
        
        assert result == ""

    @pytest.mark.asyncio
    async def test_query_with_none_query(self, graph_service, memory_bus):
        """Test querying with None query."""
        memory_bus.recall.return_value = MemoryOpResult(
            status=MemoryOpStatus.ERROR,
            error="Invalid query"
        )
        
        result = await graph_service.query_graph(None)
        
        assert result == []

    def test_metrics_with_no_requests(self, graph_service):
        """Test metrics when no requests have been made."""
        graph_service._start_time = datetime.now()
        graph_service._started = True
        
        metrics = graph_service._collect_metrics()
        
        # Average response time should be 0 when no requests
        assert metrics["avg_response_time_ms"] == 0.0
        assert metrics["request_count"] == 0.0

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, graph_service, memory_bus):
        """Test concurrent store and query operations."""
        # Setup nodes
        nodes = [
            GraphNode(
                id=f"concurrent-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes=GraphNodeAttributes(created_by="test")
            )
            for i in range(5)
        ]
        
        # Mock responses
        memory_bus.memorize.side_effect = [
            MemoryOpResult(status=MemoryOpStatus.OK, data=node)
            for node in nodes
        ]
        memory_bus.recall.return_value = MemoryOpResult(
            status=MemoryOpStatus.OK,
            data=nodes
        )
        
        # Run concurrent operations
        store_tasks = [graph_service.store_in_graph(node) for node in nodes]
        query_task = graph_service.query_graph(MemoryQuery(type=NodeType.CONCEPT))
        
        results = await asyncio.gather(*store_tasks, query_task)
        
        # Check store results
        for i in range(5):
            assert results[i] == f"concurrent-{i}"
        
        # Check query result
        assert len(results[5]) == 5


class TestBaseGraphServiceNewMethods:
    """Test new recall_node and search_nodes methods."""

    @pytest.mark.asyncio
    async def test_recall_node_success(self, graph_service, memory_bus):
        """Test successful node recall by ID."""
        # Create a typed node - TypedGraphNode is abstract, so use a GraphNode directly
        node = GraphNode(
            id="recall-123",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={"created_by": "test", "metadata": {"test": "data"}}
        )
        
        # Setup context manager mock
        mock_connection = AsyncMock()
        mock_connection.recall = AsyncMock(return_value=[node])
        memory_bus.get_connection = MagicMock()
        memory_bus.get_connection.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        memory_bus.get_connection.return_value.__aexit__ = AsyncMock()
        
        result = await graph_service.recall_node("recall-123", GraphScope.LOCAL)
        
        assert result == node
        # Check the MemoryQuery was created correctly
        call_args = mock_connection.recall.call_args[0][0]
        assert call_args.node_id == "recall-123"
        assert call_args.scope == GraphScope.LOCAL

    @pytest.mark.asyncio
    async def test_recall_node_not_found(self, graph_service, memory_bus):
        """Test recall_node returns None when node not found."""
        # Mock empty result
        mock_connection = AsyncMock()
        mock_connection.recall = AsyncMock(return_value=[])
        memory_bus.get_connection = MagicMock()
        memory_bus.get_connection.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        memory_bus.get_connection.return_value.__aexit__ = AsyncMock()
        
        result = await graph_service.recall_node("missing-id")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_recall_node_error_handling(self, graph_service, memory_bus):
        """Test recall_node handles errors gracefully."""
        # Mock connection that raises an error
        mock_connection = AsyncMock()
        mock_connection.recall = AsyncMock(side_effect=Exception("Database error"))
        memory_bus.get_connection = MagicMock()
        memory_bus.get_connection.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        memory_bus.get_connection.return_value.__aexit__ = AsyncMock()
        
        with patch('ciris_engine.logic.services.graph.base.logger') as mock_logger:
            result = await graph_service.recall_node("error-id")
            
            assert result is None
            assert graph_service._error_count == 1
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_nodes_by_type(self, graph_service, memory_bus):
        """Test searching nodes by type."""
        # Create test nodes
        nodes = [
            GraphNode(
                id=f"node-{i}",
                type=NodeType.CONCEPT if i % 2 == 0 else NodeType.MEMORY,
                scope=GraphScope.LOCAL,
                attributes={"created_by": "test", "metadata": {}}
            )
            for i in range(5)
        ]
        
        # Mock recall to return all nodes
        mock_connection = AsyncMock()
        mock_connection.recall = AsyncMock(return_value=nodes)
        memory_bus.get_connection = MagicMock()
        memory_bus.get_connection.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        memory_bus.get_connection.return_value.__aexit__ = AsyncMock()
        
        # Search for CONCEPT nodes only
        result = await graph_service.search_nodes(node_type=NodeType.CONCEPT)
        
        assert len(result) == 3  # nodes 0, 2, 4
        assert all(node.type == NodeType.CONCEPT for node in result)

    @pytest.mark.asyncio
    async def test_search_nodes_by_metadata(self, graph_service, memory_bus):
        """Test searching nodes by metadata filter."""
        # Create test nodes with different metadata
        nodes = [
            GraphNode(
                id=f"meta-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={"created_by": "test", "metadata": {"category": "A" if i < 2 else "B", "value": i}}
            )
            for i in range(4)
        ]
        
        # Mock recall
        mock_connection = AsyncMock()
        mock_connection.recall = AsyncMock(return_value=nodes)
        memory_bus.get_connection = MagicMock()
        memory_bus.get_connection.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        memory_bus.get_connection.return_value.__aexit__ = AsyncMock()
        
        # Search for category="A" nodes
        result = await graph_service.search_nodes(metadata_filter={"category": "A"})
        
        assert len(result) == 2
        # Access metadata through attributes
        assert all(node.attributes.metadata["category"] == "A" for node in result)

    @pytest.mark.asyncio
    async def test_search_nodes_with_limit(self, graph_service, memory_bus):
        """Test search nodes respects limit."""
        # Create many nodes
        nodes = [
            GraphNode(
                id=f"limit-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={"created_by": "test", "metadata": {}}
            )
            for i in range(20)
        ]
        
        # Mock recall
        mock_connection = AsyncMock()
        mock_connection.recall = AsyncMock(return_value=nodes)
        memory_bus.get_connection = MagicMock()
        memory_bus.get_connection.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        memory_bus.get_connection.return_value.__aexit__ = AsyncMock()
        
        # Search with limit
        result = await graph_service.search_nodes(limit=5)
        
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_search_nodes_empty_result(self, graph_service, memory_bus):
        """Test search_nodes handles empty results."""
        # Mock empty recall
        mock_connection = AsyncMock()
        mock_connection.recall = AsyncMock(return_value=[])
        memory_bus.get_connection = MagicMock()
        memory_bus.get_connection.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        memory_bus.get_connection.return_value.__aexit__ = AsyncMock()
        
        result = await graph_service.search_nodes(node_type=NodeType.CONCEPT)
        
        assert result == []

    @pytest.mark.asyncio
    async def test_search_nodes_error_handling(self, graph_service, memory_bus):
        """Test search_nodes handles errors gracefully."""
        # Mock connection that raises an error
        mock_connection = AsyncMock()
        mock_connection.recall = AsyncMock(side_effect=Exception("Search failed"))
        memory_bus.get_connection = MagicMock()
        memory_bus.get_connection.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        memory_bus.get_connection.return_value.__aexit__ = AsyncMock()
        
        with patch('ciris_engine.logic.services.graph.base.logger') as mock_logger:
            result = await graph_service.search_nodes()
            
            assert result == []
            assert graph_service._error_count == 1
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_memory_delegates_to_recall(self, graph_service, memory_bus):
        """Test query_memory delegates to recall_node when node_id is present."""
        # Create test node
        node = GraphNode(
            id="legacy-123",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={"created_by": "test", "metadata": {}}
        )
        
        # Mock recall
        mock_connection = AsyncMock()
        mock_connection.recall = AsyncMock(return_value=[node])
        memory_bus.get_connection = MagicMock()
        memory_bus.get_connection.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        memory_bus.get_connection.return_value.__aexit__ = AsyncMock()
        
        # Use legacy query_memory with node_id
        query = MemoryQuery(
            query_type="recall",
            node_id="legacy-123",
            scope="test"
        )
        
        result = await graph_service.query_memory(query)
        
        assert len(result) == 1
        assert result[0] == node

    @pytest.mark.asyncio
    async def test_query_memory_delegates_to_search(self, graph_service, memory_bus):
        """Test query_memory delegates to search_nodes when no node_id."""
        # Create test nodes
        nodes = [
            GraphNode(
                id=f"search-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={"created_by": "test", "metadata": {}}
            )
            for i in range(3)
        ]
        
        # Mock recall
        mock_connection = AsyncMock()
        mock_connection.recall = AsyncMock(return_value=nodes)
        memory_bus.get_connection = MagicMock()
        memory_bus.get_connection.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        memory_bus.get_connection.return_value.__aexit__ = AsyncMock()
        
        # Use legacy query_memory without node_id (search)
        query = MemoryQuery(
            query_type="search",
            scope="test"
        )
        
        result = await graph_service.query_memory(query)
        
        assert len(result) == 3


class TestSchemaValidation:
    """Test that all required schemas exist - FAIL FAST AND LOUD."""

    def test_all_required_schemas_exist(self):
        """Test that all required Pydantic schemas exist and are valid."""
        # These imports should not fail - if they do, schemas are missing
        from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
        from ciris_engine.schemas.services.graph_core import (
            GraphNode,
            GraphNodeAttributes,
            GraphScope,
            NodeType,
        )
        from ciris_engine.schemas.services.operations import (
            MemoryOpResult,
            MemoryOpStatus,
            MemoryQuery,
        )
        from ciris_engine.schemas.api.telemetry import ServiceMetrics
        
        # FAIL FAST: All schemas must be Pydantic models
        assert hasattr(ServiceCapabilities, 'model_validate'), "ServiceCapabilities is not a Pydantic model!"
        assert hasattr(GraphNode, 'model_validate'), "GraphNode is not a Pydantic model!"
        assert hasattr(MemoryQuery, 'model_validate'), "MemoryQuery is not a Pydantic model!"
        assert hasattr(MemoryOpResult, 'model_validate'), "MemoryOpResult is not a Pydantic model!"
        assert hasattr(ServiceMetrics, 'model_validate'), "ServiceMetrics is not a Pydantic model!"
        
        # Test instantiation - schemas must be valid
        caps = ServiceCapabilities(
            service_name="test",
            actions=["test"],
            version="1.0.0"
        )
        assert caps.service_name == "test"
        
        node = GraphNode(
            id="test",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes=GraphNodeAttributes(created_by="test")
        )
        assert node.id == "test"
        
        query = MemoryQuery(node_id="test_query", scope=GraphScope.LOCAL, type=NodeType.CONCEPT)
        assert query.type == NodeType.CONCEPT
        assert query.node_id == "test_query"