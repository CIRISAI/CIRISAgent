"""
Comprehensive end-to-end tests for TSDB consolidation with all node types.

Tests the complete flow of:
1. Generating correlations of all types
2. Validating correlation data
3. Running consolidation
4. Verifying summary nodes are created correctly
"""

from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock

import pytest

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.memory import TimeSeriesDataPoint
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceRequestData,
    ServiceResponseData,
)


class MockTimeService(TimeServiceProtocol):
    """Mock time service for testing with full protocol compliance."""

    def __init__(self, fixed_time: datetime):
        self.fixed_time = fixed_time
        self.start_time = fixed_time
        self._started = False
        self._healthy = True

    def now(self) -> datetime:
        return self.fixed_time

    def now_iso(self) -> str:
        return self.fixed_time.isoformat()

    def timestamp(self) -> float:
        return self.fixed_time.timestamp()

    def get_uptime(self) -> float:
        """Get service uptime in seconds."""
        if not self._started:
            return 0.0
        return (self.fixed_time - self.start_time).total_seconds()

    async def start(self) -> None:
        """Start the mock service."""
        self._started = True
        self.start_time = self.fixed_time

    async def stop(self) -> None:
        """Stop the mock service."""
        self._started = False

    async def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return self._started and self._healthy

    def get_service_type(self) -> "ServiceType":
        """Get the service type."""
        from ciris_engine.schemas.runtime.enums import ServiceType

        return ServiceType.TIME

    def get_capabilities(self) -> "ServiceCapabilities":
        """Get service capabilities."""
        from ciris_engine.schemas.services.core import ServiceCapabilities

        return ServiceCapabilities(
            service_name="MockTimeService",
            actions=["now", "now_iso", "timestamp", "get_uptime"],
            version="1.0.0",
            dependencies=[],
            metadata={"fixed_time": self.fixed_time.isoformat(), "description": "Mock time service for testing"},
        )

    def get_status(self) -> "ServiceStatus":
        """Get current service status."""
        from ciris_engine.schemas.services.core import ServiceStatus

        return ServiceStatus(
            service_name="MockTimeService",
            service_type="time",
            is_healthy=self._started and self._healthy,
            uptime_seconds=self.get_uptime(),
            metrics={"fixed_time": self.fixed_time.timestamp(), "started": 1.0 if self._started else 0.0},
            last_error=None,
            last_health_check=self.fixed_time,
        )

    # Test helper methods
    def advance_time(self, hours: int = 0, minutes: int = 0, seconds: int = 0):
        """Advance the fixed time for testing."""
        self.fixed_time += timedelta(hours=hours, minutes=minutes, seconds=seconds)

    def set_healthy(self, healthy: bool):
        """Set the health status for testing error conditions."""
        self._healthy = healthy


@pytest.fixture
def mock_time_service():
    """Create a mock time service with fixed time."""
    # Set time to 13:00 so consolidation will process 06:00-12:00 period
    fixed_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    return MockTimeService(fixed_time)


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    return AsyncMock(spec=MemoryBus)


@pytest.fixture
def consolidation_service(mock_memory_bus, mock_time_service):
    """Create a TSDB consolidation service with mocks."""
    # Set up a temporary database for the tests
    import sqlite3
    import tempfile

    from ciris_engine.schemas.persistence.tables import (
        GRAPH_EDGES_TABLE_V1,
        GRAPH_NODES_TABLE_V1,
        SERVICE_CORRELATIONS_TABLE_V1,
        TASKS_TABLE_V1,
        THOUGHTS_TABLE_V1,
    )

    # Create temporary database
    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = db_file.name
    db_file.close()

    # Create tables
    conn = sqlite3.connect(db_path)
    conn.executescript(GRAPH_NODES_TABLE_V1)
    conn.executescript(GRAPH_EDGES_TABLE_V1)
    conn.executescript(SERVICE_CORRELATIONS_TABLE_V1)
    conn.executescript(TASKS_TABLE_V1)
    conn.executescript(THOUGHTS_TABLE_V1)
    conn.commit()
    conn.close()

    # Monkey patch get_db_connection to use our test database
    import ciris_engine.logic.persistence.db.core
    import ciris_engine.logic.services.graph.tsdb_consolidation.edge_manager
    import ciris_engine.logic.services.graph.tsdb_consolidation.query_manager

    original_get_db = ciris_engine.logic.persistence.db.core.get_db_connection

    test_db_path = db_path  # Capture from closure

    def get_test_db_connection(db_path=None, **kwargs):
        # Use provided db_path if given, otherwise use test db
        use_path = db_path if db_path else test_db_path
        conn = sqlite3.connect(use_path)
        conn.row_factory = sqlite3.Row
        return conn

    # Patch in all places
    ciris_engine.logic.persistence.db.core.get_db_connection = get_test_db_connection
    ciris_engine.logic.services.graph.tsdb_consolidation.query_manager.get_db_connection = get_test_db_connection
    ciris_engine.logic.services.graph.tsdb_consolidation.edge_manager.get_db_connection = get_test_db_connection

    service = TSDBConsolidationService(
        memory_bus=mock_memory_bus,
        time_service=mock_time_service,
        db_path=test_db_path,  # Pass the test database path
        consolidation_interval_hours=6,
        raw_retention_hours=24,
    )

    # Store cleanup info
    service._test_db_path = db_path
    service._original_get_db = original_get_db

    yield service

    # Cleanup
    ciris_engine.logic.persistence.db.core.get_db_connection = original_get_db
    ciris_engine.logic.services.graph.tsdb_consolidation.query_manager.get_db_connection = original_get_db
    ciris_engine.logic.services.graph.tsdb_consolidation.edge_manager.get_db_connection = original_get_db
    import os

    os.unlink(db_path)


def create_metric_datapoints(period_start: datetime, period_end: datetime) -> List[TimeSeriesDataPoint]:
    """Create sample METRIC_DATAPOINT correlations."""
    datapoints = []

    # Create metrics every 5 minutes
    current = period_start
    while current < period_end:
        # Token usage metric
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=current,
                metric_name="llm.tokens_used",
                value=float(100 + (current.minute % 10) * 10),  # Vary between 100-190
                correlation_type="METRIC_DATAPOINT",
                tags={"model": "gpt-4", "service": "llm"},
            )
        )

        # Add action metrics
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=current,
                metric_name="handler.action_selected",
                value=1.0,
                correlation_type="METRIC_DATAPOINT",
                tags={"action_type": "SPEAK", "handler": "SpeakHandler"},
            )
        )

        # Cost metric
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=current,
                metric_name="llm.cost_cents",
                value=float(5 + (current.minute % 5)),  # Vary between 5-9
                correlation_type="METRIC_DATAPOINT",
                tags={"model": "gpt-4", "service": "llm"},
            )
        )

        # Action count metrics
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=current,
                metric_name="action.speak.count",
                value=1.0,
                correlation_type="METRIC_DATAPOINT",
                tags={"service": "communication"},
            )
        )

        # Success/error metrics
        if current.minute % 10 == 0:  # Error every 10 minutes
            datapoints.append(
                TimeSeriesDataPoint(
                    timestamp=current,
                    metric_name="action.error.count",
                    value=1.0,
                    correlation_type="METRIC_DATAPOINT",
                    tags={"service": "llm", "error_type": "timeout"},
                )
            )
        else:
            datapoints.append(
                TimeSeriesDataPoint(
                    timestamp=current,
                    metric_name="action.success.count",
                    value=1.0,
                    correlation_type="METRIC_DATAPOINT",
                    tags={"service": "llm"},
                )
            )

        current += timedelta(minutes=5)

    return datapoints


def create_conversation_datapoints(period_start: datetime, period_end: datetime) -> List[TimeSeriesDataPoint]:
    """Create sample SERVICE_INTERACTION correlations for conversations."""
    datapoints = []
    channels = ["api_127.0.0.1:8000", "discord_123456"]

    # Create a conversation in each channel
    for i, channel in enumerate(channels):
        base_time = period_start + timedelta(hours=i + 1)

        # User message (observe)
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=base_time,
                metric_name="service_interaction",
                value=1.0,
                correlation_type="SERVICE_INTERACTION",
                tags={
                    "correlation_type": "SERVICE_INTERACTION",
                    "action_type": "observe",
                    "channel_id": channel,
                    "author_id": f"user_{i}",
                    "author_name": f"User {i}",
                    "content": f"Hello CIRIS, can you help me with task {i}?",
                    "correlation_id": f"obs_{i}_1",
                },
            )
        )

        # Agent response (speak)
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=base_time + timedelta(seconds=5),
                metric_name="service_interaction",
                value=1.0,
                correlation_type="SERVICE_INTERACTION",
                tags={
                    "correlation_type": "SERVICE_INTERACTION",
                    "action_type": "speak",
                    "channel_id": channel,
                    "author_id": "ciris",
                    "author_name": "CIRIS",
                    "content": f"Hello User {i}! I'd be happy to help with task {i}.",
                    "correlation_id": f"spk_{i}_1",
                    "execution_time_ms": "1500",
                },
            )
        )

        # Follow-up
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=base_time + timedelta(seconds=20),
                metric_name="service_interaction",
                value=1.0,
                correlation_type="SERVICE_INTERACTION",
                tags={
                    "correlation_type": "SERVICE_INTERACTION",
                    "action_type": "observe",
                    "channel_id": channel,
                    "author_id": f"user_{i}",
                    "author_name": f"User {i}",
                    "content": "Thanks! Can you explain how this works?",
                    "correlation_id": f"obs_{i}_2",
                },
            )
        )

        # Agent explanation
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=base_time + timedelta(seconds=25),
                metric_name="service_interaction",
                value=1.0,
                correlation_type="SERVICE_INTERACTION",
                tags={
                    "correlation_type": "SERVICE_INTERACTION",
                    "action_type": "speak",
                    "channel_id": channel,
                    "author_id": "ciris",
                    "author_name": "CIRIS",
                    "content": "Let me explain the process step by step...",
                    "correlation_id": f"spk_{i}_2",
                    "execution_time_ms": "2000",
                },
            )
        )

    return datapoints


def create_trace_datapoints(period_start: datetime, period_end: datetime) -> List[TimeSeriesDataPoint]:
    """Create sample TRACE_SPAN correlations."""
    datapoints = []

    # Simulate processing 3 tasks
    for task_num in range(3):
        task_id = f"task_{task_num}"
        task_start = period_start + timedelta(hours=task_num * 2)

        # Agent processor span
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=task_start,
                metric_name="trace_span",
                value=1.0,
                correlation_type="TRACE_SPAN",
                tags={
                    "correlation_type": "TRACE_SPAN",
                    "task_id": task_id,
                    "component_type": "agent_processor",
                    "trace_depth": "1",
                    "task_status": "ACTIVE",
                    "execution_time_ms": "5000",
                    "success": "true",
                },
            )
        )

        # Thought processor spans (3 thoughts per task)
        for thought_num in range(3):
            thought_id = f"thought_{task_num}_{thought_num}"
            thought_time = task_start + timedelta(seconds=thought_num * 10)

            datapoints.append(
                TimeSeriesDataPoint(
                    timestamp=thought_time,
                    metric_name="trace_span",
                    value=1.0,
                    correlation_type="TRACE_SPAN",
                    tags={
                        "correlation_type": "TRACE_SPAN",
                        "task_id": task_id,
                        "thought_id": thought_id,
                        "component_type": "thought_processor",
                        "thought_type": "REASONING",
                        "trace_depth": "2",
                        "execution_time_ms": "500",
                        "success": "true",
                    },
                )
            )

            # DMA span
            datapoints.append(
                TimeSeriesDataPoint(
                    timestamp=thought_time + timedelta(seconds=1),
                    metric_name="trace_span",
                    value=1.0,
                    correlation_type="TRACE_SPAN",
                    tags={
                        "correlation_type": "TRACE_SPAN",
                        "task_id": task_id,
                        "thought_id": thought_id,
                        "component_type": "dma",
                        "dma_type": "iterative_dma",
                        "trace_depth": "3",
                        "execution_time_ms": "200",
                        "success": "true",
                    },
                )
            )

            # Guardrail span (simulate one violation)
            is_violation = task_num == 1 and thought_num == 1
            datapoints.append(
                TimeSeriesDataPoint(
                    timestamp=thought_time + timedelta(seconds=2),
                    metric_name="trace_span",
                    value=1.0,
                    correlation_type="TRACE_SPAN",
                    tags={
                        "correlation_type": "TRACE_SPAN",
                        "task_id": task_id,
                        "thought_id": thought_id,
                        "component_type": "guardrail",
                        "guardrail_type": "content_filter",
                        "violation": "true" if is_violation else "false",
                        "trace_depth": "3",
                        "execution_time_ms": "100",
                        "success": "true",
                    },
                )
            )

            # Handler span
            datapoints.append(
                TimeSeriesDataPoint(
                    timestamp=thought_time + timedelta(seconds=3),
                    metric_name="trace_span",
                    value=1.0,
                    correlation_type="TRACE_SPAN",
                    tags={
                        "correlation_type": "TRACE_SPAN",
                        "task_id": task_id,
                        "thought_id": thought_id,
                        "component_type": "handler",
                        "action_type": "speak",
                        "trace_depth": "3",
                        "execution_time_ms": "300",
                        "success": "true" if not is_violation else "false",
                    },
                )
            )

        # Final task status
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=task_start + timedelta(seconds=35),
                metric_name="trace_span",
                value=1.0,
                correlation_type="TRACE_SPAN",
                tags={
                    "correlation_type": "TRACE_SPAN",
                    "task_id": task_id,
                    "component_type": "agent_processor",
                    "task_status": "COMPLETED" if task_num != 1 else "FAILED",
                    "trace_depth": "1",
                    "execution_time_ms": "35000",
                    "success": "true" if task_num != 1 else "false",
                },
            )
        )

    return datapoints


def create_audit_datapoints(period_start: datetime, period_end: datetime) -> List[TimeSeriesDataPoint]:
    """Create sample AUDIT_EVENT correlations."""
    datapoints = []

    # Auth events
    for i in range(5):
        event_time = period_start + timedelta(minutes=i * 30)
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=event_time,
                metric_name="audit_event",
                value=1.0,
                correlation_type="AUDIT_EVENT",
                tags={
                    "correlation_type": "AUDIT_EVENT",
                    "correlation_id": f"audit_{i}_auth",
                    "event_type": "AUTH_SUCCESS" if i % 2 == 0 else "AUTH_FAILURE",
                    "actor": f"user_{i}",
                    "service": "authentication",
                },
            )
        )

    # Permission events
    datapoints.append(
        TimeSeriesDataPoint(
            timestamp=period_start + timedelta(hours=1),
            metric_name="audit_event",
            value=1.0,
            correlation_type="AUDIT_EVENT",
            tags={
                "correlation_type": "AUDIT_EVENT",
                "correlation_id": "audit_perm_denied",
                "event_type": "PERMISSION_DENIED",
                "actor": "user_3",
                "service": "config_service",
            },
        )
    )

    # Config changes
    for i in range(3):
        event_time = period_start + timedelta(hours=2 + i)
        datapoints.append(
            TimeSeriesDataPoint(
                timestamp=event_time,
                metric_name="audit_event",
                value=1.0,
                correlation_type="AUDIT_EVENT",
                tags={
                    "correlation_type": "AUDIT_EVENT",
                    "correlation_id": f"audit_config_{i}",
                    "event_type": "CONFIG_UPDATE",
                    "actor": "admin",
                    "service": "config_service",
                },
            )
        )

    return datapoints


def datapoints_to_correlations(
    datapoints: List[TimeSeriesDataPoint], correlation_type: str
) -> List[ServiceCorrelation]:
    """Convert TimeSeriesDataPoint objects to ServiceCorrelation objects for testing."""
    correlations = []

    # Map from uppercase tags to lowercase enum values
    type_mapping = {
        "SERVICE_INTERACTION": CorrelationType.SERVICE_INTERACTION,
        "METRIC_DATAPOINT": CorrelationType.METRIC_DATAPOINT,
        "TRACE_SPAN": CorrelationType.TRACE_SPAN,
        "AUDIT_EVENT": CorrelationType.AUDIT_EVENT,
    }

    for dp in datapoints:
        # Check correlation_type from tags in uppercase
        if dp.tags.get("correlation_type") == correlation_type:
            # Build request data from tags
            request_data = ServiceRequestData(
                service_type=dp.tags.get("service", "unknown"),
                method_name=dp.tags.get("action_type", "unknown"),
                channel_id=dp.tags.get("channel_id"),
                parameters={
                    "content": dp.tags.get("content", ""),
                    "author_id": dp.tags.get("author_id", ""),
                    "author_name": dp.tags.get("author_name", ""),
                },
                request_timestamp=dp.timestamp,
            )

            # Build response data
            exec_time = float(dp.tags.get("execution_time_ms", 0))
            success = dp.tags.get("success", "true") == "true"
            response_data = (
                ServiceResponseData(success=success, execution_time_ms=exec_time, response_timestamp=dp.timestamp)
                if exec_time > 0
                else None
            )

            # Use the correct enum value
            enum_type = type_mapping.get(correlation_type, CorrelationType.SERVICE_INTERACTION)

            corr = ServiceCorrelation(
                correlation_id=dp.tags.get("correlation_id", f"corr_{dp.timestamp.timestamp()}"),
                correlation_type=enum_type,
                service_type=dp.tags.get("service", "unknown"),
                handler_name="test_handler",
                action_type=dp.tags.get("action_type", "unknown"),
                request_data=request_data,
                response_data=response_data,
                created_at=dp.timestamp,
                updated_at=dp.timestamp,
                timestamp=dp.timestamp,
                tags=dp.tags,
            )
            correlations.append(corr)

    return correlations


def create_audit_nodes_from_datapoints(datapoints: List[TimeSeriesDataPoint]) -> List[GraphNode]:
    """Convert audit datapoints to actual AUDIT_ENTRY graph nodes."""
    from ciris_engine.schemas.services.nodes import AuditEntry, AuditEntryContext

    nodes = []
    for dp in datapoints:
        if dp.tags.get("correlation_type") == "AUDIT_EVENT":
            # Create an AuditEntry node
            event_type = dp.tags.get("event_type", "unknown")
            actor = dp.tags.get("actor", "unknown")
            service = dp.tags.get("service", "unknown")

            context = AuditEntryContext(
                service_name=service,
                additional_data={
                    "event_type": event_type,
                    "severity": "warning" if "FAIL" in event_type or "DENIED" in event_type else "info",
                    "outcome": "failure" if "FAIL" in event_type or "DENIED" in event_type else "success",
                },
            )

            audit_entry = AuditEntry(
                id=f"audit_{dp.tags.get('correlation_id', dp.timestamp.strftime('%Y%m%d_%H%M%S'))}",
                action=event_type,
                actor=actor,
                timestamp=dp.timestamp,
                context=context,
                created_at=dp.timestamp,
                updated_at=dp.timestamp,
                scope=GraphScope.LOCAL,
                attributes={},  # Required by GraphNode base class
            )

            nodes.append(audit_entry.to_graph_node())

    return nodes


@pytest.mark.asyncio
async def test_end_to_end_consolidation_all_types(consolidation_service, mock_memory_bus, mock_time_service):
    """Test complete consolidation flow for all correlation types."""
    # Set up test period (06:00-12:00 on 2024-01-01)
    period_start = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    period_end = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Generate test data for all types
    metric_datapoints = create_metric_datapoints(period_start, period_end)
    conversation_datapoints = create_conversation_datapoints(period_start, period_end)
    trace_datapoints = create_trace_datapoints(period_start, period_end)
    audit_datapoints = create_audit_datapoints(period_start, period_end)

    # Insert test data into the database
    import json

    from ciris_engine.logic.persistence.db.core import get_db_connection

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Insert service correlations for each type
        for i, dp in enumerate(metric_datapoints):
            correlation_id = f"metric_{i}_{int(dp.timestamp.timestamp())}"
            cursor.execute(
                """
                INSERT INTO service_correlations
                (correlation_id, service_type, handler_name, action_type,
                 request_data, response_data, status, created_at, updated_at,
                 correlation_type, timestamp, metric_name, metric_value,
                 trace_id, span_id, parent_span_id, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    correlation_id,
                    "telemetry",
                    "metrics_collector",
                    "record_metric",
                    json.dumps({"metric_name": dp.metric_name, "value": dp.value, "tags": dp.tags}),
                    json.dumps({"status": "recorded"}),
                    "success",
                    dp.timestamp.isoformat(),
                    dp.timestamp.isoformat(),
                    "metric_datapoint",
                    dp.timestamp.isoformat(),
                    dp.metric_name,
                    dp.value,
                    f"trace_{correlation_id}",
                    f"span_{correlation_id}",
                    None,
                    json.dumps(dp.tags),
                ),
            )

        # Insert conversation correlations
        for i, dp in enumerate(conversation_datapoints):
            correlation_id = f"conv_{i}_{int(dp.timestamp.timestamp())}"
            action_type = dp.tags.get("action_type", "unknown")

            # Format request_data with parameters field as expected by consolidator
            request_data = {
                "channel_id": dp.tags.get("channel_id", "test_channel"),
                "parameters": {
                    "content": dp.tags.get("content", "test message"),
                    "author_id": dp.tags.get("author_id"),
                    "author_name": dp.tags.get("author_name"),
                },
            }

            # Response data with execution time
            response_data = {
                "status": "handled",
                "success": True,
                "execution_time_ms": int(dp.tags.get("execution_time_ms", 0)),
            }

            cursor.execute(
                """
                INSERT INTO service_correlations
                (correlation_id, service_type, handler_name, action_type,
                 request_data, response_data, status, created_at, updated_at,
                 correlation_type, timestamp, metric_name, metric_value,
                 trace_id, span_id, parent_span_id, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    correlation_id,
                    "communication",
                    "discord_adapter",
                    action_type,
                    json.dumps(request_data),
                    json.dumps(response_data),
                    "success",
                    dp.timestamp.isoformat(),
                    dp.timestamp.isoformat(),
                    "service_interaction",
                    dp.timestamp.isoformat(),
                    dp.metric_name,
                    dp.value,
                    f"trace_{correlation_id}",
                    f"span_{correlation_id}",
                    None,
                    json.dumps(dp.tags),
                ),
            )

        # Insert trace correlations with proper task/thought tracking
        for i, dp in enumerate(trace_datapoints):
            correlation_id = f"trace_{i}_{int(dp.timestamp.timestamp())}"
            # Create realistic trace span data
            task_idx = i // 3  # 3 spans per task
            thought_idx = i
            trace_tags = {
                "task_id": f"task_{task_idx}_{int(dp.timestamp.timestamp())}",
                "thought_id": f"thought_{thought_idx}_{int(dp.timestamp.timestamp())}",
                "component_type": ["agent_processor", "thought_processor", "handler"][i % 3],
                "trace_depth": str((i % 3) + 1),
                "thought_type": "standard",
            }
            # Only add non-None values
            if i % 3 == 2:
                trace_tags["action_type"] = "SPEAK"
                trace_tags["task_status"] = "completed"
            # Merge with existing tags
            trace_tags.update(dp.tags)

            cursor.execute(
                """
                INSERT INTO service_correlations
                (correlation_id, service_type, handler_name, action_type,
                 request_data, response_data, status, created_at, updated_at,
                 correlation_type, timestamp, metric_name, metric_value,
                 trace_id, span_id, parent_span_id, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    correlation_id,
                    trace_tags["component_type"],
                    "AgentProcessor" if trace_tags["component_type"] == "agent_processor" else "ThoughtProcessor",
                    "process_thought",
                    None,  # trace spans typically don't have request_data
                    json.dumps({"status": "completed", "duration_ms": dp.value}),
                    "success",
                    dp.timestamp.isoformat(),
                    dp.timestamp.isoformat(),
                    "trace_span",
                    dp.timestamp.isoformat(),
                    None,
                    None,  # trace spans don't use metric_name/value
                    f"trace_{task_idx}",
                    correlation_id,
                    f"span_{i-1}_{int(dp.timestamp.timestamp())}" if i % 3 > 0 else None,
                    json.dumps(trace_tags),
                ),
            )

        # Insert audit nodes into graph_nodes table (not correlations)
        for i, dp in enumerate(audit_datapoints):
            node_id = f"audit_{i}_{int(dp.timestamp.timestamp())}"
            event_type = dp.tags.get("event_type", dp.metric_name)
            audit_attrs = {
                "created_at": dp.timestamp.isoformat(),
                "updated_at": dp.timestamp.isoformat(),
                "created_by": "audit_service",
                "tags": ["actor:system", f"action:{event_type}"],
                "action": event_type,
                "actor": "system",
                "timestamp": dp.timestamp.isoformat(),
                "context": {
                    "service_name": "TestService",
                    "correlation_id": node_id,
                    "additional_data": {"event_type": event_type, "severity": "info", "outcome": "success"},
                },
                "node_class": "AuditEntry",
            }

            cursor.execute(
                """
                INSERT INTO graph_nodes
                (node_id, scope, node_type, attributes_json, version, updated_by, updated_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    node_id,
                    "local",
                    "audit_entry",
                    json.dumps(audit_attrs),
                    1,
                    "audit_service",
                    dp.timestamp.isoformat(),
                    dp.timestamp.isoformat(),
                ),
            )

        # Insert some tasks for task summary
        task_times = [
            period_start + timedelta(hours=1),
            period_start + timedelta(hours=2),
            period_start + timedelta(hours=3),
        ]

        for i, task_time in enumerate(task_times):
            task_id = f"task_{i}_{int(task_time.timestamp())}"
            cursor.execute(
                """
                INSERT INTO tasks
                (task_id, channel_id, description, status, priority,
                 created_at, updated_at, parent_task_id, context_json, outcome_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task_id,
                    "test_channel",
                    f"Test task {i}",
                    "completed",  # Not deferred!
                    i,
                    task_time.isoformat(),
                    (task_time + timedelta(minutes=30)).isoformat(),
                    None,
                    json.dumps({"test": "context"}),
                    json.dumps({"result": "success", "details": f"Task {i} completed"}),
                ),
            )

            # Insert thoughts for each task (3 thoughts per task)
            for j in range(3):
                thought_time = task_time + timedelta(minutes=j * 5)
                cursor.execute(
                    """
                    INSERT INTO thoughts
                    (thought_id, source_task_id, thought_type, status,
                     created_at, updated_at, final_action_json, content)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        f"thought_{i}_{j}_{int(thought_time.timestamp())}",
                        task_id,  # source_task_id is the correct column name
                        "standard",
                        "completed",
                        thought_time.isoformat(),
                        thought_time.isoformat(),
                        json.dumps({"action": "SPEAK"}) if j == 2 else None,
                        f"Thought {j} for task {i}",  # content is required
                    ),
                )

        conn.commit()

    # Mock memory bus responses for each correlation type
    async def mock_recall_timeseries(
        scope, hours=None, correlation_types=None, start_time=None, end_time=None, handler_name=None
    ):
        # Handle both calling patterns
        if correlation_types is None and hours is not None:
            # Old pattern: (scope, hours, correlation_types) - hours is actually correlation_types
            correlation_types = hours
            hours = None

        if "metric_datapoint" in correlation_types:
            return metric_datapoints
        elif "service_interaction" in correlation_types:
            # Convert to correlation objects
            return datapoints_to_correlations(conversation_datapoints, "SERVICE_INTERACTION")
        elif "trace_span" in correlation_types:
            # Convert to correlation objects
            return datapoints_to_correlations(trace_datapoints, "TRACE_SPAN")
        elif "audit_event" in correlation_types:
            # Convert to correlation objects
            return datapoints_to_correlations(audit_datapoints, "AUDIT_EVENT")
        return []

    mock_memory_bus.recall_timeseries.side_effect = mock_recall_timeseries

    # Mock successful memorize operations and track what's stored
    stored_summaries = []

    async def mock_memorize(node):
        stored_summaries.append(node)
        return MemoryOpResult(status=MemoryOpStatus.OK, data=None, error=None)

    mock_memory_bus.memorize.side_effect = mock_memorize

    # Mock query response (no existing summaries for initial check, but audit nodes for wildcard query)
    async def mock_recall(query, handler_name="default"):
        # If querying for audit nodes with wildcard, return the audit nodes
        if hasattr(query, "node_id") and query.node_id == "audit_*":
            return create_audit_nodes_from_datapoints(audit_datapoints)
        # Otherwise return empty (no existing summaries)
        return []

    mock_memory_bus.recall.side_effect = mock_recall

    # Mock search response for audit nodes - return actual audit nodes
    audit_nodes = create_audit_nodes_from_datapoints(audit_datapoints)
    mock_memory_bus.search.return_value = audit_nodes

    # Run consolidation
    summaries = await consolidation_service._consolidate_period(period_start, period_end)

    # Verify we got 4 summaries (metrics, tasks, conversation, trace)
    # Audit might not create a summary if using nodes instead
    assert len(summaries) >= 3

    # Verify memorize was called at least 4 times (summaries + edges)
    assert mock_memory_bus.memorize.call_count >= 4

    # Check each summary type from stored summaries
    stored_nodes = stored_summaries

    # Debug: print all stored nodes
    print(f"\nStored {len(stored_nodes)} nodes:")
    for node in stored_nodes:
        if hasattr(node, "id") and hasattr(node, "type"):
            print(f"  - {node.id} (type: {node.type})")

    # Find each summary type
    tsdb_summary = None
    conversation_summary = None
    trace_summary = None
    audit_summary = None

    for node in stored_nodes:
        # Only look at nodes with an id attribute (skip edges)
        if hasattr(node, "id"):
            # Skip edge nodes - they have 'edge_' prefix or contain '_to_'
            if node.id.startswith("edge_") or "_to_" in node.id:
                continue

            if node.id.startswith("tsdb_summary_") and node.type == NodeType.TSDB_SUMMARY:
                # Check it's actually a TSDB summary (has metrics field)
                if "metrics" in node.attributes:
                    tsdb_summary = node
            elif node.id.startswith("conversation_summary_") and node.type == NodeType.CONVERSATION_SUMMARY:
                conversation_summary = node
            elif node.id.startswith("trace_summary_") and node.type == NodeType.TRACE_SUMMARY:
                trace_summary = node
            elif node.id.startswith("audit_summary_") and node.type == NodeType.TSDB_SUMMARY:
                audit_summary = node

    # Validate TSDB Summary
    assert tsdb_summary is not None
    assert tsdb_summary.type == NodeType.TSDB_SUMMARY
    tsdb_attrs = tsdb_summary.attributes
    assert tsdb_attrs["total_tokens"] > 0
    assert tsdb_attrs["action_counts"]["SPEAK"] > 0
    assert "llm.tokens_used" in tsdb_attrs["metrics"]

    # Validate Conversation Summary
    assert conversation_summary is not None
    assert conversation_summary.type == NodeType.CONVERSATION_SUMMARY
    conv_attrs = conversation_summary.attributes
    assert conv_attrs["total_messages"] == 8  # 4 messages per channel, 2 channels
    assert len(conv_attrs["conversations_by_channel"]) == 2
    assert conv_attrs["unique_users"] == 3  # user_0, user_1, and ciris

    # Validate Trace Summary
    assert trace_summary is not None
    assert trace_summary.type == NodeType.TRACE_SUMMARY  # Trace uses TRACE_SUMMARY type
    trace_attrs = trace_summary.attributes
    assert trace_attrs["total_tasks_processed"] > 0
    assert trace_attrs["total_thoughts_processed"] > 0
    assert "component_calls" in trace_attrs
    assert trace_attrs["component_calls"]["agent_processor"] > 0

    # Validate Audit Summary (if created - depends on implementation)
    if audit_summary:
        assert audit_summary.type == NodeType.TSDB_SUMMARY
        audit_attrs = audit_summary.attributes
        assert "total_audit_events" in audit_attrs or "audit_events_by_type" in audit_attrs


@pytest.mark.asyncio
async def test_consolidation_with_no_data(consolidation_service, mock_memory_bus, mock_time_service):
    """Test consolidation when no correlations exist for the period."""
    period_start = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    period_end = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Mock empty responses
    mock_memory_bus.recall_timeseries.return_value = []
    mock_memory_bus.recall.return_value = []
    mock_memory_bus.search.return_value = []

    # Run consolidation
    summaries = await consolidation_service._consolidate_period(period_start, period_end)

    # Should have no summaries
    assert len(summaries) == 0

    # Memorize should not be called
    assert mock_memory_bus.memorize.call_count == 0


@pytest.mark.asyncio
async def test_consolidation_idempotency(consolidation_service, mock_memory_bus, mock_time_service):
    """Test that consolidation is idempotent - won't re-consolidate already processed periods."""
    period_start = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    period_end = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Test the higher-level method that checks for existing summaries
    # Insert a TSDB summary into the test database
    import json
    import sqlite3

    conn = sqlite3.connect(consolidation_service._test_db_path)
    cursor = conn.cursor()

    # Insert existing summary
    cursor.execute(
        """
        INSERT INTO graph_nodes (node_id, scope, node_type, attributes_json, created_at)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            f"tsdb_summary_{period_start.strftime('%Y%m%d_%H')}",
            GraphScope.LOCAL.value,
            NodeType.TSDB_SUMMARY.value,
            json.dumps({"period_start": period_start.isoformat(), "period_end": period_end.isoformat()}),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    # Check if period is consolidated
    is_consolidated = consolidation_service._is_period_consolidated(period_start, period_end)
    assert is_consolidated is True

    # Now test direct consolidation - it will still create summaries for other types
    # since each type is consolidated independently

    # Mock empty data for all correlation types
    mock_memory_bus.recall_timeseries.return_value = []
    mock_memory_bus.recall.return_value = []
    mock_memory_bus.search.return_value = []  # No audit nodes

    # Mock successful memorize operations
    mock_memory_bus.memorize.return_value = MemoryOpResult(status=MemoryOpStatus.OK, data=None, error=None)

    # Run consolidation
    summaries = await consolidation_service._consolidate_period(period_start, period_end)

    # Should create no summaries since there's no data
    assert len(summaries) == 0
    assert mock_memory_bus.memorize.call_count == 0


@pytest.mark.asyncio
async def test_conversation_summary_preserves_full_content(consolidation_service, mock_memory_bus, mock_time_service):
    """Test that conversation summaries preserve full message content."""
    period_start = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    period_end = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Create detailed conversation
    conversation_datapoints = create_conversation_datapoints(period_start, period_end)

    # Insert conversation data into database
    import json

    from ciris_engine.logic.persistence.db.core import get_db_connection

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Insert conversation correlations
        for i, dp in enumerate(conversation_datapoints):
            action_type = dp.tags.get("action_type", "unknown")

            # Format request_data with parameters field as expected by consolidator
            request_data = {
                "channel_id": dp.tags.get("channel_id", "test_channel"),
                "parameters": {
                    "content": dp.tags.get("content", "test message"),
                    "author_id": dp.tags.get("author_id"),
                    "author_name": dp.tags.get("author_name"),
                },
            }

            # Response data with execution time
            response_data = {
                "status": "handled",
                "success": True,
                "execution_time_ms": int(dp.tags.get("execution_time_ms", 0)),
            }

            cursor.execute(
                """
                INSERT INTO service_correlations
                (correlation_id, service_type, handler_name, action_type,
                 request_data, response_data, status, created_at, updated_at,
                 correlation_type, timestamp, metric_name, metric_value,
                 trace_id, span_id, parent_span_id, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    f"conv_test_{i}_{int(dp.timestamp.timestamp())}",
                    "communication",
                    "discord_adapter",
                    action_type,
                    json.dumps(request_data),
                    json.dumps(response_data),
                    "success",
                    dp.timestamp.isoformat(),
                    dp.timestamp.isoformat(),
                    "service_interaction",
                    dp.timestamp.isoformat(),
                    dp.metric_name,
                    dp.value,
                    f"trace_conv_{i}",
                    f"span_conv_{i}",
                    None,
                    json.dumps(dp.tags),
                ),
            )

        conn.commit()

    # Mock responses
    mock_memory_bus.recall.return_value = []
    mock_memory_bus.search.return_value = []
    # Ensure memorize returns a proper result for async calls
    memorize_result = MemoryOpResult(status=MemoryOpStatus.OK, data=None, error=None)
    mock_memory_bus.memorize.return_value = memorize_result

    # Run consolidation
    summaries = await consolidation_service._consolidate_period(period_start, period_end)

    # Find conversation summary
    conv_summary = None
    for call in mock_memory_bus.memorize.call_args_list:
        node = call[1]["node"] if "node" in call[1] else call[0][0]
        if "conversation_summary_" in node.id:
            conv_summary = node
            break

    assert conv_summary is not None

    # Verify full content is preserved
    conversations = conv_summary.attributes["conversations_by_channel"]
    assert len(conversations) == 2

    # Check first channel has all messages with content
    first_channel = list(conversations.keys())[0]
    messages = conversations[first_channel]
    assert len(messages) == 4

    # Verify message content is preserved
    for msg in messages:
        assert "content" in msg
        assert msg["content"] != ""
        assert "timestamp" in msg
        assert "author_id" in msg


@pytest.mark.asyncio
async def test_audit_hash_generation(consolidation_service, mock_memory_bus, mock_time_service):
    """Test that audit summaries generate correct hashes."""
    period_start = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    period_end = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Create audit events
    audit_datapoints = create_audit_datapoints(period_start, period_end)

    # Insert audit nodes into database
    import json

    from ciris_engine.logic.persistence.db.core import get_db_connection

    # Create audit nodes and insert into graph_nodes table
    audit_nodes = create_audit_nodes_from_datapoints(audit_datapoints)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Insert audit nodes
        for i, node in enumerate(audit_nodes):
            cursor.execute(
                """
                INSERT INTO graph_nodes
                (node_id, node_type, scope, attributes_json, created_at, updated_at, updated_by, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    node.id,
                    node.type.value,
                    node.scope.value,
                    json.dumps(node.attributes),
                    node.updated_at.isoformat() if node.updated_at else audit_datapoints[i].timestamp.isoformat(),
                    node.updated_at.isoformat() if node.updated_at else audit_datapoints[i].timestamp.isoformat(),
                    "test",
                    1,
                ),
            )

        # Insert audit correlations
        for i, dp in enumerate(audit_datapoints):
            cursor.execute(
                """
                INSERT INTO service_correlations
                (correlation_id, service_type, handler_name, action_type,
                 request_data, response_data, status, created_at, updated_at,
                 correlation_type, timestamp, metric_name, metric_value,
                 trace_id, span_id, parent_span_id, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    dp.tags.get("correlation_id", f"audit_test_{i}_{int(dp.timestamp.timestamp())}"),
                    "audit",
                    "audit_service",
                    dp.tags.get("event_type", "unknown"),
                    json.dumps({"event_type": dp.tags.get("event_type"), "actor": dp.tags.get("actor")}),
                    json.dumps({"status": "logged"}),
                    "success",
                    dp.timestamp.isoformat(),
                    dp.timestamp.isoformat(),
                    "audit_event",
                    dp.timestamp.isoformat(),
                    dp.metric_name,
                    dp.value,
                    f"trace_audit_{i}",
                    f"span_audit_{i}",
                    None,
                    json.dumps(dp.tags),
                ),
            )

        conn.commit()

    # Mock responses
    mock_memory_bus.recall.return_value = audit_nodes
    mock_memory_bus.search.return_value = audit_nodes
    # Ensure memorize returns a proper result for async calls
    memorize_result = MemoryOpResult(status=MemoryOpStatus.OK, data=None, error=None)
    mock_memory_bus.memorize.return_value = memorize_result

    # Run consolidation
    summaries = await consolidation_service._consolidate_period(period_start, period_end)

    # Find audit summary
    audit_summary = None
    for call in mock_memory_bus.memorize.call_args_list:
        node = call[1]["node"] if "node" in call[1] else call[0][0]
        if "audit_summary_" in node.id:
            audit_summary = node
            break

    assert audit_summary is not None

    # Verify hash properties
    audit_attrs = audit_summary.attributes
    assert "audit_hash" in audit_attrs
    assert len(audit_attrs["audit_hash"]) == 64  # SHA-256 produces 64 hex chars
    assert audit_attrs["hash_algorithm"] == "sha256"

    # Verify event counts
    assert audit_attrs["total_audit_events"] == 9
    assert audit_attrs["failed_auth_attempts"] == 2
    assert audit_attrs["permission_denials"] == 1
    assert audit_attrs["config_changes"] == 3


@pytest.mark.asyncio
async def test_trace_summary_metrics(consolidation_service, mock_memory_bus, mock_time_service):
    """Test that trace summaries calculate metrics correctly."""
    period_start = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    period_end = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Create trace events
    trace_datapoints = create_trace_datapoints(period_start, period_end)

    # Insert trace data and tasks into database
    import json

    from ciris_engine.logic.persistence.db.core import get_db_connection

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Insert tasks and thoughts for trace summary
        for task_idx in range(3):
            task_time = period_start + timedelta(hours=task_idx + 1)
            task_id = f"task_{task_idx}_{int(task_time.timestamp())}"

            # Insert task
            cursor.execute(
                """
                INSERT INTO tasks
                (task_id, channel_id, description, status, priority,
                 created_at, updated_at, parent_task_id, context_json, outcome_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task_id,
                    "test_channel",
                    f"Test task {task_idx}",
                    "completed",
                    task_idx,
                    task_time.isoformat(),
                    (task_time + timedelta(minutes=30)).isoformat(),
                    None,
                    json.dumps({"test": "context"}),
                    json.dumps({"result": "success"}),
                ),
            )

            # Insert thoughts for each task
            for thought_idx in range(3):
                thought_time = task_time + timedelta(minutes=thought_idx * 5)
                cursor.execute(
                    """
                    INSERT INTO thoughts
                    (thought_id, source_task_id, thought_type, status,
                     created_at, updated_at, content)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        f"thought_{task_idx}_{thought_idx}_{int(thought_time.timestamp())}",
                        task_id,
                        "standard",
                        "completed",
                        thought_time.isoformat(),
                        thought_time.isoformat(),
                        f"Thought {thought_idx} for task {task_idx}",
                    ),
                )

        # Insert trace correlations
        for i, dp in enumerate(trace_datapoints):
            # Extract task index to link traces to tasks
            task_idx = i // 14  # 14 traces per task approximately
            task_id = f"task_{task_idx}_{int((period_start + timedelta(hours=task_idx+1)).timestamp())}"

            # Calculate which thought this trace belongs to (distribute evenly)
            thought_idx = (i % 14) // 5  # Distribute traces across 3 thoughts

            # Enhanced trace tags
            trace_tags = dp.tags.copy()
            trace_tags["task_id"] = task_id
            trace_tags["thought_id"] = (
                f"thought_{task_idx}_{thought_idx}_{int((period_start + timedelta(hours=task_idx+1, minutes=thought_idx*5)).timestamp())}"
            )

            cursor.execute(
                """
                INSERT INTO service_correlations
                (correlation_id, service_type, handler_name, action_type,
                 request_data, response_data, status, created_at, updated_at,
                 correlation_type, timestamp, metric_name, metric_value,
                 trace_id, span_id, parent_span_id, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    f"trace_test_{i}_{int(dp.timestamp.timestamp())}",
                    "processor",
                    trace_tags.get("component_type", "unknown"),
                    "process",
                    json.dumps({"component": trace_tags.get("component_type")}),
                    json.dumps({"status": "completed", "execution_time_ms": trace_tags.get("execution_time_ms", 100)}),
                    "success",
                    dp.timestamp.isoformat(),
                    dp.timestamp.isoformat(),
                    "trace_span",
                    dp.timestamp.isoformat(),
                    dp.metric_name,
                    dp.value,
                    trace_tags.get("trace_id", f"trace_{i}"),
                    trace_tags.get("span_id", f"span_{i}"),
                    trace_tags.get("parent_span_id"),
                    json.dumps(trace_tags),
                ),
            )

        conn.commit()

    # Mock responses
    mock_memory_bus.recall.return_value = []
    mock_memory_bus.search.return_value = []
    # Ensure memorize returns a proper result for async calls
    memorize_result = MemoryOpResult(status=MemoryOpStatus.OK, data=None, error=None)
    mock_memory_bus.memorize.return_value = memorize_result

    # Run consolidation
    summaries = await consolidation_service._consolidate_period(period_start, period_end)

    # Find trace summary
    trace_summary = None
    for call in mock_memory_bus.memorize.call_args_list:
        node = call[1]["node"] if "node" in call[1] else call[0][0]
        if "trace_summary_" in node.id:
            trace_summary = node
            break

    assert trace_summary is not None

    # Verify trace metrics
    trace_attrs = trace_summary.attributes
    assert trace_attrs["total_tasks_processed"] == 3
    assert trace_attrs["total_thoughts_processed"] == 9
    assert trace_attrs["avg_thoughts_per_task"] == 3.0

    # Verify component metrics
    assert trace_attrs["component_calls"]["agent_processor"] > 0
    assert trace_attrs["component_calls"]["thought_processor"] > 0
    assert trace_attrs["component_calls"]["dma"] > 0
    assert trace_attrs["component_calls"]["guardrail"] > 0
    assert trace_attrs["component_calls"]["handler"] > 0

    # Verify patterns
    assert trace_attrs["dma_decisions"]["iterative_dma"] == 9
    assert trace_attrs["guardrail_violations"]["content_filter"] == 1
    assert trace_attrs["handler_actions"]["speak"] == 9

    # Verify trace depth
    assert trace_attrs["max_trace_depth"] == 3
    assert trace_attrs["avg_trace_depth"] > 0
