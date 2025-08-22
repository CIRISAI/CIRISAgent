"""
Comprehensive test suite for BaseGraphService.

Tests all methods and edge cases in ciris_engine/logic/services/graph/base.py
FAIL FAST AND LOUD: Any missing schema should cause immediate test failure.
"""

import asyncio
from datetime import datetime, timezone
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
        assert service._telemetry_service is None
        assert service._request_count == 0
        assert service._error_count == 0
        assert service._total_response_time == 0.0
        assert service._start_time is None

    def test_init_without_dependencies(self):
        """Test initialization without dependencies."""
        service = TestGraphService()
        
        assert service.service_name == "TestGraphService"
        assert service._memory_bus is None
        assert service._time_service is None
        assert service._telemetry_service is None

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
            mock_logger.info.assert_called_once_with("TestGraphService started")

    @pytest.mark.asyncio
    async def test_start_with_telemetry(self, graph_service):
        """Test starting service with telemetry."""
        mock_telemetry = MagicMock()
        graph_service._telemetry_service = mock_telemetry
        
        with patch('ciris_engine.logic.services.graph.base.logger') as mock_logger:
            await graph_service.start()
            
            assert graph_service._start_time is not None
            mock_logger.info.assert_called_once_with("TestGraphService started")
            mock_telemetry.update_service_metrics.assert_called_once()
            
            # Check the metrics passed to telemetry
            call_args = mock_telemetry.update_service_metrics.call_args[0][0]
            assert call_args.service_name == "TestGraphService"
            assert call_args.healthy is True
            assert call_args.uptime_seconds == 0.0

    @pytest.mark.asyncio
    async def test_stop(self, graph_service):
        """Test stopping service."""
        with patch('ciris_engine.logic.services.graph.base.logger') as mock_logger:
            await graph_service.stop()
            
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
        """Test collecting metrics with all dependencies."""
        graph_service._request_count = 10
        graph_service._error_count = 2
        
        metrics = graph_service._collect_custom_metrics()
        
        assert metrics["memory_bus_available"] == 1.0
        assert metrics["time_service_available"] == 1.0
        assert metrics["graph_operations_total"] == 10.0
        assert metrics["graph_errors_total"] == 2.0

    def test_collect_custom_metrics_without_dependencies(self):
        """Test collecting metrics without dependencies."""
        service = TestGraphService()
        
        metrics = service._collect_custom_metrics()
        
        assert metrics["memory_bus_available"] == 0.0
        assert metrics["time_service_available"] == 0.0
        assert metrics["graph_operations_total"] == 0.0
        assert metrics["graph_errors_total"] == 0.0

    def test_track_request_without_telemetry(self, graph_service):
        """Test tracking a request without telemetry."""
        initial_count = graph_service._request_count
        initial_time = graph_service._total_response_time
        
        graph_service._track_request(100.5)
        
        assert graph_service._request_count == initial_count + 1
        assert graph_service._total_response_time == initial_time + 100.5

    def test_track_request_with_telemetry(self, graph_service):
        """Test tracking a request with telemetry."""
        mock_telemetry = MagicMock()
        graph_service._telemetry_service = mock_telemetry
        graph_service._update_telemetry = MagicMock()
        
        graph_service._track_request(50.0)
        
        assert graph_service._request_count == 1
        assert graph_service._total_response_time == 50.0
        graph_service._update_telemetry.assert_called_once()

    def test_track_error_without_telemetry(self, graph_service):
        """Test tracking an error without telemetry."""
        initial_count = graph_service._error_count
        
        graph_service._track_error()
        
        assert graph_service._error_count == initial_count + 1

    def test_track_error_with_telemetry(self, graph_service):
        """Test tracking an error with telemetry."""
        mock_telemetry = MagicMock()
        graph_service._telemetry_service = mock_telemetry
        graph_service._update_telemetry = MagicMock()
        
        graph_service._track_error()
        
        assert graph_service._error_count == 1
        graph_service._update_telemetry.assert_called_once()

    @patch('ciris_engine.logic.services.graph.base.psutil')
    def test_update_telemetry(self, mock_psutil, graph_service):
        """Test updating telemetry metrics."""
        # Setup mocks
        mock_process = MagicMock()
        mock_psutil.Process.return_value = mock_process
        mock_process.memory_info.return_value = MagicMock(rss=100 * 1024 * 1024)  # 100 MB
        mock_process.cpu_percent.return_value = 25.5
        
        mock_telemetry = MagicMock()
        graph_service._telemetry_service = mock_telemetry
        graph_service._start_time = datetime.now()
        graph_service._request_count = 5
        graph_service._error_count = 1
        graph_service._total_response_time = 500.0
        
        graph_service._update_telemetry()
        
        mock_telemetry.update_service_metrics.assert_called_once()
        
        # Check metrics passed
        metrics = mock_telemetry.update_service_metrics.call_args[0][0]
        assert metrics.service_name == "TestGraphService"
        assert metrics.healthy is True
        assert metrics.memory_usage_mb == 100.0
        assert metrics.cpu_usage_percent == 25.5
        assert metrics.request_count == 5
        assert metrics.error_count == 1
        assert metrics.avg_response_time_ms == 100.0  # 500/5

    def test_update_telemetry_no_service(self, graph_service):
        """Test update telemetry with no telemetry service."""
        graph_service._telemetry_service = None
        
        # Should not raise any errors
        graph_service._update_telemetry()


class TestBaseGraphServiceStoreOperations:
    """Test graph storage operations."""

    @pytest.mark.asyncio
    async def test_store_in_graph_success(self, graph_service, memory_bus):
        """Test successful node storage."""
        # Create test node - FAIL FAST if GraphNode schema missing
        node = GraphNode(
            id="test-123",
            type=NodeType.CONCEPT,
            scope=GraphScope.GLOBAL,
            attributes=GraphNodeAttributes(
                timestamp=datetime.now(timezone.utc),
                metadata={"test": "data"}
            )
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
            scope=GraphScope.GLOBAL,
            attributes=GraphNodeAttributes(timestamp=datetime.now(timezone.utc))
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
            scope=GraphScope.GLOBAL,
            attributes=GraphNodeAttributes(timestamp=datetime.now(timezone.utc))
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
            scope=GraphScope.GLOBAL,
            attributes=GraphNodeAttributes(timestamp=datetime.now(timezone.utc))
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
            type=NodeType.CONCEPT,
            scope=GraphScope.GLOBAL
        )
        
        nodes = [
            GraphNode(
                id=f"node-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.GLOBAL,
                attributes=GraphNodeAttributes(timestamp=datetime.now(timezone.utc))
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
        query = MemoryQuery(type=NodeType.CONCEPT)
        
        node = GraphNode(
            id="single-node",
            type=NodeType.CONCEPT,
            scope=GraphScope.GLOBAL,
            attributes=GraphNodeAttributes(timestamp=datetime.now(timezone.utc))
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
        query = MemoryQuery(type=NodeType.CONCEPT)
        
        nodes = [
            GraphNode(
                id=f"direct-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.GLOBAL,
                attributes=GraphNodeAttributes(timestamp=datetime.now(timezone.utc))
            )
            for i in range(2)
        ]
        
        memory_bus.recall.return_value = nodes
        
        result = await graph_service.query_graph(query)
        
        assert result == nodes

    @pytest.mark.asyncio
    async def test_query_graph_failure(self, graph_service, memory_bus):
        """Test failed query."""
        query = MemoryQuery(type=NodeType.CONCEPT)
        
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
        
        query = MemoryQuery(type=NodeType.CONCEPT)
        
        with patch('ciris_engine.logic.services.graph.base.logger') as mock_logger:
            result = await service.query_graph(query)
            
            assert result == []
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_graph_unexpected_result_type(self, graph_service, memory_bus):
        """Test query with unexpected result type."""
        query = MemoryQuery(type=NodeType.CONCEPT)
        
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

    def test_average_response_time_no_requests(self, graph_service):
        """Test average response time calculation with no requests."""
        graph_service._start_time = datetime.now()
        
        with patch('ciris_engine.logic.services.graph.base.psutil'):
            mock_telemetry = MagicMock()
            graph_service._telemetry_service = mock_telemetry
            
            graph_service._update_telemetry()
            
            # Check that avg_response_time_ms is 0 when no requests
            metrics = mock_telemetry.update_service_metrics.call_args[0][0]
            assert metrics.avg_response_time_ms == 0.0

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, graph_service, memory_bus):
        """Test concurrent store and query operations."""
        # Setup nodes
        nodes = [
            GraphNode(
                id=f"concurrent-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.GLOBAL,
                attributes=GraphNodeAttributes(timestamp=datetime.now(timezone.utc))
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
            scope=GraphScope.GLOBAL,
            attributes=GraphNodeAttributes(timestamp=datetime.now(timezone.utc))
        )
        assert node.id == "test"
        
        query = MemoryQuery(type=NodeType.CONCEPT)
        assert query.type == NodeType.CONCEPT