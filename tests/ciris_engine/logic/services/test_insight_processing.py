"""
Test insight processing flow between PatternAnalysisLoop and DreamProcessor.

This tests that:
1. PatternAnalysisLoop stores insights as CONCEPT nodes with insight_type='behavioral_pattern'
2. DreamProcessor queries and processes these insights during dream cycles
"""

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.infrastructure.sub_services.pattern_analysis_loop import PatternAnalysisLoop
from ciris_engine.logic.processors.states.dream_processor import DreamProcessor
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.infrastructure.feedback_loop import DetectedPattern, PatternMetrics, PatternType
from ciris_engine.schemas.processors.base import ProcessorServices
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


class MockTimeService(TimeServiceProtocol):
    """Mock time service for testing with full protocol compliance."""

    def __init__(self, current_time: Optional[datetime] = None):
        self._current_time = current_time or datetime.now(timezone.utc)
        self._start_time = self._current_time
        self._started = False
        self._healthy = True

    def now(self) -> datetime:
        return self._current_time

    def now_iso(self) -> str:
        return self._current_time.isoformat()

    def get_current_time(self) -> datetime:
        return self._current_time

    def timestamp(self) -> float:
        return self._current_time.timestamp()

    def get_uptime(self) -> float:
        """Get service uptime in seconds."""
        if not self._started:
            return 0.0
        return (self._current_time - self._start_time).total_seconds()

    async def start(self) -> None:
        """Start the mock service."""
        self._started = True
        self._start_time = self._current_time

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
            metadata={
                "current_time": self._current_time.isoformat(),
                "description": "Mock time service for testing insight processing",
            },
        )

    def get_status(self) -> "ServiceStatus":
        """Get current service status."""
        from ciris_engine.schemas.services.core import ServiceStatus

        return ServiceStatus(
            service_name="MockTimeService",
            service_type="time",
            is_healthy=self._started and self._healthy,
            uptime_seconds=self.get_uptime(),
            metrics={"current_time": self._current_time.timestamp(), "started": 1.0 if self._started else 0.0},
            last_error=None,
            last_health_check=self._current_time,
        )

    # Test helper methods
    def advance_time(self, **kwargs):
        """Advance the current time for testing."""
        self._current_time += timedelta(**kwargs)

    def set_time(self, new_time: datetime):
        """Set the current time for testing."""
        self._current_time = new_time


@pytest.mark.asyncio
async def test_feedback_loop_stores_insights_as_concept_nodes() -> None:
    """Test that PatternAnalysisLoop stores insights as CONCEPT nodes."""
    # Setup
    time_service = MockTimeService()
    memory_bus = MagicMock(spec=MemoryBus)
    memory_bus.memorize = AsyncMock(return_value=MemoryOpResult(status=MemoryOpStatus.OK, reason="Success"))

    feedback_loop = PatternAnalysisLoop(time_service=time_service, memory_bus=memory_bus)

    # Create a test pattern
    pattern = DetectedPattern(
        pattern_type=PatternType.FREQUENCY,
        pattern_id="test_pattern",
        description="Test action is used frequently",
        evidence_nodes=["node1", "node2", "node3"],
        detected_at=time_service.now(),
        metrics=PatternMetrics(occurrence_count=10, average_value=0.5, confidence=0.8),  # type: ignore
    )

    # Store pattern insights
    stored_count = await feedback_loop._store_pattern_insights([pattern])

    # Verify
    assert stored_count == 1
    memory_bus.memorize.assert_called_once()

    # Check the stored node
    call_args = memory_bus.memorize.call_args
    stored_node = call_args.kwargs["node"]

    assert stored_node.type == NodeType.CONCEPT
    assert stored_node.scope == GraphScope.LOCAL
    assert stored_node.attributes["insight_type"] == "behavioral_pattern"
    assert stored_node.attributes["pattern_type"] == PatternType.FREQUENCY.value
    assert stored_node.attributes["description"] == pattern.description
    assert stored_node.attributes["actionable"] is True


@pytest.mark.asyncio
async def test_dream_processor_queries_behavioral_insights() -> None:
    """Test that DreamProcessor queries for behavioral pattern insights."""
    # Setup
    time_service = MockTimeService()
    memory_bus = MagicMock(spec=MemoryBus)

    # Create mock insight nodes
    insight_nodes = [
        GraphNode(
            id="insight_1",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={
                "insight_type": "behavioral_pattern",
                "pattern_type": "frequency",
                "description": "Action SPEAK is used 80% of the time",
                "actionable": True,
                "detected_at": (time_service.now() - timedelta(hours=1)).isoformat(),
            },
            updated_by="test",
            updated_at=time_service.now(),
        ),
        GraphNode(
            id="insight_2",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={
                "insight_type": "behavioral_pattern",
                "pattern_type": "temporal",
                "description": "Different tools preferred at different times of day",
                "actionable": True,
                "detected_at": (time_service.now() - timedelta(hours=2)).isoformat(),
            },
            updated_by="test",
            updated_at=time_service.now(),
        ),
    ]

    memory_bus.search = AsyncMock(return_value=insight_nodes)

    # Create DreamProcessor with minimal setup
    config_accessor = MagicMock()
    thought_processor = MagicMock()
    action_dispatcher = MagicMock()
    resource_monitor = MagicMock()
    services = ProcessorServices(time_service=time_service, resource_monitor=resource_monitor)

    dream_processor = DreamProcessor(
        config_accessor=config_accessor,
        thought_processor=thought_processor,
        action_dispatcher=action_dispatcher,
        services=services,
    )
    dream_processor.memory_bus = memory_bus

    # Process behavioral insights
    insights = await dream_processor._process_behavioral_insights()

    # Verify search was called
    memory_bus.search.assert_called_once()
    call_args = memory_bus.search.call_args
    query = call_args.kwargs["query"]

    assert query == "type:concept"

    # Verify insights processed
    assert len(insights) == 4  # 2 pattern descriptions + 2 action opportunities
    assert "Pattern (frequency): Action SPEAK is used 80% of the time" in insights
    assert "Pattern (temporal): Different tools preferred at different times of day" in insights
    assert "Action Opportunity: Action SPEAK is used 80% of the time" in insights
    assert "Action Opportunity: Different tools preferred at different times of day" in insights


@pytest.mark.asyncio
async def test_all_insights_processed_without_filtering() -> None:
    """Test that all behavioral pattern insights are processed without reliability filtering."""
    # Setup
    time_service = MockTimeService()
    memory_bus = MagicMock(spec=MemoryBus)

    # Create insight nodes with varying reliability
    insight_nodes = [
        GraphNode(
            id="high_reliability",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={
                "insight_type": "behavioral_pattern",
                "pattern_type": "frequency",
                "description": "High reliability pattern",
                "actionable": True,
                "detected_at": (time_service.now() - timedelta(hours=1)).isoformat(),
            },
            updated_by="test",
            updated_at=time_service.now(),
        ),
        GraphNode(
            id="low_reliability",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={
                "insight_type": "behavioral_pattern",
                "pattern_type": "frequency",
                "description": "Low reliability pattern",
                "actionable": True,
                "detected_at": (time_service.now() - timedelta(hours=1)).isoformat(),
            },
            updated_by="test",
            updated_at=time_service.now(),
        ),
    ]

    memory_bus.search = AsyncMock(return_value=insight_nodes)

    # Create DreamProcessor
    config_accessor = MagicMock()
    thought_processor = MagicMock()
    action_dispatcher = MagicMock()
    resource_monitor = MagicMock()
    services = ProcessorServices(time_service=time_service, resource_monitor=resource_monitor)

    dream_processor = DreamProcessor(
        config_accessor=config_accessor,
        thought_processor=thought_processor,
        action_dispatcher=action_dispatcher,
        services=services,
    )
    dream_processor.memory_bus = memory_bus

    # Process insights
    insights = await dream_processor._process_behavioral_insights()

    # Verify all insights are processed (no reliability filtering)
    assert len(insights) == 4  # 2 patterns + 2 action opportunities
    assert "High reliability pattern" in str(insights)
    assert "Low reliability pattern" in str(insights)


@pytest.mark.asyncio
async def test_feedback_loop_stores_all_detected_patterns() -> None:
    """Test that feedback loop stores all detected patterns as insights."""
    # Setup
    time_service = MockTimeService()
    memory_bus = MagicMock(spec=MemoryBus)
    memory_bus.memorize = AsyncMock(return_value=MemoryOpResult(status=MemoryOpStatus.OK, reason="Success"))

    feedback_loop = PatternAnalysisLoop(time_service=time_service, memory_bus=memory_bus)

    # Create patterns with varying reliability
    patterns = [
        DetectedPattern(
            pattern_type=PatternType.FREQUENCY,
            pattern_id="high_conf",
            description="High reliability pattern",
            evidence_nodes=["node1"],
            detected_at=time_service.now(),
            metrics=PatternMetrics(occurrence_count=10, average_value=0.8, confidence=0.9),  # type: ignore
        ),
        DetectedPattern(
            pattern_type=PatternType.FREQUENCY,
            pattern_id="low_conf",
            description="Low reliability pattern",
            evidence_nodes=["node2"],
            detected_at=time_service.now(),
            metrics=PatternMetrics(occurrence_count=5, average_value=0.5, confidence=0.6),  # type: ignore
        ),
    ]

    # Store pattern insights
    stored_count = await feedback_loop._store_pattern_insights(patterns)

    # Verify all patterns stored
    assert stored_count == 2
    assert memory_bus.memorize.call_count == 2


@pytest.mark.asyncio
async def test_integration_feedback_loop_to_dream_processor() -> None:
    """Test the full integration from feedback loop to dream processor."""
    # Setup
    time_service = MockTimeService()
    memory_bus = MagicMock(spec=MemoryBus)

    # Track stored nodes
    stored_nodes = []

    async def mock_memorize(node: GraphNode, **kwargs: Any) -> MemoryOpResult:
        stored_nodes.append(node)
        return MemoryOpResult(status=MemoryOpStatus.OK, reason="Success")

    async def mock_search(query: str, **kwargs: Any) -> List[GraphNode]:
        # Return nodes that match the query
        if query == "type:concept":
            return [
                n
                for n in stored_nodes
                if n.type == NodeType.CONCEPT and n.attributes.get("insight_type") == "behavioral_pattern"
            ]
        return []

    memory_bus.memorize = AsyncMock(side_effect=mock_memorize)
    memory_bus.search = AsyncMock(side_effect=mock_search)

    # Create feedback loop and store insights
    feedback_loop = PatternAnalysisLoop(time_service=time_service, memory_bus=memory_bus)

    pattern = DetectedPattern(
        pattern_type=PatternType.PERFORMANCE,
        pattern_id="perf_degradation",
        description="Response times degraded by 25%",
        evidence_nodes=["metric1", "metric2"],
        detected_at=time_service.now(),
        metrics=PatternMetrics(
            average_value=250.0,
            peak_value=500.0,
            trend="increasing",  # type: ignore
            confidence=0.95,  # type: ignore
        ),
    )

    await feedback_loop._store_pattern_insights([pattern])

    # Create dream processor and process insights
    config_accessor = MagicMock()
    thought_processor = MagicMock()
    action_dispatcher = MagicMock()
    resource_monitor = MagicMock()
    services = ProcessorServices(time_service=time_service, resource_monitor=resource_monitor)

    dream_processor = DreamProcessor(
        config_accessor=config_accessor,
        thought_processor=thought_processor,
        action_dispatcher=action_dispatcher,
        services=services,
    )
    dream_processor.memory_bus = memory_bus

    insights = await dream_processor._process_behavioral_insights()

    # Verify end-to-end flow
    assert len(stored_nodes) == 1
    assert stored_nodes[0].type == NodeType.CONCEPT
    assert stored_nodes[0].attributes["insight_type"] == "behavioral_pattern"

    assert len(insights) == 2  # Pattern + action opportunity
    assert "Pattern (performance): Response times degraded by 25%" in insights
    assert "Action Opportunity: Response times degraded by 25%" in insights


@pytest.mark.asyncio
async def test_dream_processor_handles_missing_attributes() -> None:
    """Test that DreamProcessor handles nodes with missing attributes gracefully."""
    # Setup
    time_service = MockTimeService()
    memory_bus = MagicMock(spec=MemoryBus)

    # Create nodes with missing attributes
    insight_nodes = [
        GraphNode(
            id="missing_attrs",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={},  # No attributes
            updated_by="test",
            updated_at=time_service.now(),
        ),
        GraphNode(
            id="partial_attrs",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={
                "insight_type": "behavioral_pattern",
                # Missing other fields
            },
            updated_by="test",
            updated_at=time_service.now(),
        ),
        GraphNode(
            id="complete",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={
                "insight_type": "behavioral_pattern",
                "pattern_type": "frequency",
                "description": "Complete pattern",
                "actionable": True,
                "detected_at": (time_service.now() - timedelta(hours=1)).isoformat(),
            },
            updated_by="test",
            updated_at=time_service.now(),
        ),
    ]

    memory_bus.search = AsyncMock(return_value=insight_nodes)

    # Create DreamProcessor
    config_accessor = MagicMock()
    thought_processor = MagicMock()
    action_dispatcher = MagicMock()
    resource_monitor = MagicMock()
    services = ProcessorServices(time_service=time_service, resource_monitor=resource_monitor)

    dream_processor = DreamProcessor(
        config_accessor=config_accessor,
        thought_processor=thought_processor,
        action_dispatcher=action_dispatcher,
        services=services,
    )
    dream_processor.memory_bus = memory_bus

    # Process insights - should not crash
    insights = await dream_processor._process_behavioral_insights()

    # Verify all patterns processed, including ones with missing attributes
    assert len(insights) == 3  # 2 patterns (one empty) + 1 action opportunity
    assert "Complete pattern" in str(insights)
    assert "Pattern (unknown): " in str(insights)  # Node with missing attributes
