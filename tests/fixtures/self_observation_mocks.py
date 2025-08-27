"""
Mock objects for self-observation service testing.

Provides comprehensive mocks for testing the self-observation service
and its dependencies.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

from ciris_engine.schemas.infrastructure.behavioral_patterns import ActionFrequency, TemporalPattern
from ciris_engine.schemas.infrastructure.feedback_loop import AnalysisResult, DetectedPattern, PatternType
from ciris_engine.schemas.runtime.core import AgentIdentityRoot
from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery, MemoryOpResult
from ciris_engine.schemas.services.special.self_observation import (
    AnalysisStatus,
    ConfigurationChange,
    CycleEventData,
    LearningSummary,
    ObservabilityAnalysis,
    ObservationCycleResult,
    ObservationEffectiveness,
    ObservationOpportunity,
    ObservationState,
    ObservationStatus,
    PatternEffectiveness,
    PatternInsight,
    PatternLibrarySummary,
    ProcessSnapshotResult,
    ReviewOutcome,
    ServiceImprovementReport,
)


class MockTimeService:
    """Mock time service for consistent time operations."""

    def __init__(self, fixed_time: Optional[datetime] = None):
        self.fixed_time = fixed_time or datetime(2025, 1, 27, 12, 0, 0, tzinfo=timezone.utc)
        self._offset = timedelta()

    def now(self) -> datetime:
        """Return current time."""
        return self.fixed_time + self._offset

    def advance(self, seconds: float):
        """Advance time by given seconds."""
        self._offset += timedelta(seconds=seconds)

    def reset(self):
        """Reset time offset."""
        self._offset = timedelta()


class MockMemoryBus:
    """Mock memory bus for graph operations."""

    def __init__(self):
        self.stored_nodes = []
        self.queries = []
        self.memorize = AsyncMock(return_value=MagicMock(success=True))
        self.query = AsyncMock(return_value=[])
        self.recall = AsyncMock(return_value=[])

    async def store_node(self, node: GraphNode) -> bool:
        """Store a graph node."""
        self.stored_nodes.append(node)
        return True

    async def execute_query(self, query: MemoryQuery) -> MemoryOpResult:
        """Execute a memory query."""
        self.queries.append(query)
        return MemoryOpResult(success=True, node_id=None, message="Query executed")


class MockIdentityVarianceMonitor:
    """Mock identity variance monitor sub-service."""

    def __init__(self):
        from ciris_engine.schemas.infrastructure.identity_variance import VarianceReport
        
        self.baseline_established = False
        self.current_variance = 0.0
        self.variance_history = []
        self._baseline_snapshot_id = "baseline_123"
        self.initialize = AsyncMock(return_value="baseline_123")
        self.measure_variance = AsyncMock(return_value=0.05)
        self.get_variance_report = AsyncMock()
        self.is_stable = AsyncMock(return_value=True)
        
        # Mock check_variance to return a VarianceReport
        self.check_variance = AsyncMock(return_value=VarianceReport(
            timestamp=datetime.now(timezone.utc),
            baseline_snapshot_id="baseline_123",
            current_snapshot_id="current_123",
            total_variance=0.05,
            differences=[],
            requires_wa_review=False,
            recommendations=[]
        ))

    async def establish_baseline(self, identity: AgentIdentityRoot) -> str:
        """Establish identity baseline."""
        self.baseline_established = True
        self._baseline_snapshot_id = "baseline_123"
        return "baseline_123"
    
    async def initialize_baseline(self, identity: AgentIdentityRoot) -> str:
        """Initialize identity baseline."""
        self.baseline_established = True
        self._baseline_snapshot_id = "baseline_123"
        return "baseline_123"

    async def get_current_variance(self) -> float:
        """Get current variance from baseline."""
        return self.current_variance

    async def update_variance(self, new_variance: float):
        """Update variance value."""
        self.current_variance = new_variance
        self.variance_history.append(new_variance)


class MockPatternAnalysisLoop:
    """Mock pattern analysis loop sub-service."""

    def __init__(self):
        self.patterns = []
        self.insights = []
        self.is_running = False
        self.analyze = AsyncMock(return_value=AnalysisResult(
            status="completed",
            patterns_detected=2,
            insights_stored=1,
            timestamp=datetime.now(timezone.utc),
            next_analysis_in=3600.0
        ))
        self.get_patterns = AsyncMock(return_value=[])
        self.get_insights = AsyncMock(return_value=[])
        self.start = AsyncMock()
        self.stop = AsyncMock()

    async def add_pattern(self, pattern: DetectedPattern):
        """Add a detected pattern."""
        self.patterns.append(pattern)

    async def add_insight(self, insight: PatternInsight):
        """Add a pattern insight."""
        self.insights.append(insight)


class MockTelemetryService:
    """Mock telemetry service for metrics."""

    def __init__(self):
        self.metrics = {}
        self.events = []
        self.capture_metrics = AsyncMock()
        self.record_event = AsyncMock()
        self.get_metrics = AsyncMock(return_value={})
        self._service_registry = None
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.is_healthy = AsyncMock(return_value=True)

    def _set_service_registry(self, registry):
        """Set the service registry."""
        self._service_registry = registry

    async def record_metric(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record a metric."""
        self.metrics[name] = value

    async def get_metric(self, name: str) -> Optional[float]:
        """Get a metric value."""
        return self.metrics.get(name)


class MockServiceRegistry:
    """Mock service registry."""

    def __init__(self):
        self.services = {}

    def get_service(self, service_type: str) -> Optional[Any]:
        """Get a service by type."""
        return self.services.get(service_type)

    def register_service(self, service_type: str, service: Any):
        """Register a service."""
        self.services[service_type] = service


def create_agent_identity(
    agent_id: Optional[str] = None,
    core_values: Optional[List[str]] = None,
    capabilities: Optional[List[str]] = None,
    constraints: Optional[List[str]] = None,
) -> AgentIdentityRoot:
    """Create an agent identity for testing."""
    from ciris_engine.schemas.runtime.core import CoreProfile, IdentityMetadata
    
    now = datetime.now(timezone.utc)
    agent_id = agent_id or str(uuid.uuid4())
    
    return AgentIdentityRoot(
        agent_id=agent_id,
        identity_hash=f"hash_{agent_id}",
        core_profile=CoreProfile(
            description="Test AI Assistant",
            role_description="Test agent for unit testing",
            domain_specific_knowledge={"testing": "Unit test knowledge"},
            areas_of_expertise=["testing", "validation"],
        ),
        identity_metadata=IdentityMetadata(
            created_at=now,
            last_modified=now,
            modification_count=0,
            creator_agent_id="system",
            version="1.0.0",
        ),
        permitted_actions=capabilities or ["text_processing", "reasoning", "learning"],
        trust_level=0.8,
    )


def create_observation_cycle_result(
    cycle_id: Optional[str] = None,
    state: ObservationState = ObservationState.LEARNING,
    patterns_detected: int = 0,
    success: bool = True,
    requires_review: bool = False,
) -> ObservationCycleResult:
    """Create an observation cycle result for testing."""
    now = datetime.now(timezone.utc)
    return ObservationCycleResult(
        cycle_id=cycle_id or str(uuid.uuid4()),
        state=state,
        started_at=now,
        completed_at=now + timedelta(seconds=30),
        patterns_detected=patterns_detected,
        pattern_types=["behavioral", "temporal"] if patterns_detected > 0 else [],
        proposals_generated=patterns_detected // 2,
        proposals_approved=patterns_detected // 3,
        proposals_rejected=0,
        changes_applied=patterns_detected // 4,
        rollbacks_performed=0,
        variance_before=0.05,
        variance_after=0.06,
        success=success,
        requires_review=requires_review,
        error=None if success else "Test error",
    )


def create_observation_status(
    is_active: bool = True,
    current_state: ObservationState = ObservationState.LEARNING,
    cycles_completed: int = 10,
    current_variance: float = 0.05,
) -> ObservationStatus:
    """Create an observation status for testing."""
    return ObservationStatus(
        is_active=is_active,
        current_state=current_state,
        cycles_completed=cycles_completed,
        last_cycle_at=datetime.now(timezone.utc),
        current_variance=current_variance,
        patterns_in_buffer=5,
        pending_proposals=2,
        average_cycle_duration_seconds=30.5,
        total_changes_applied=15,
        rollback_rate=0.1,
        identity_stable=True,
        time_since_last_change=3600.0,
        under_review=False,
        review_reason=None,
    )


def create_review_outcome(
    review_id: Optional[str] = None,
    decision: str = "approve",
    approved_changes: Optional[List[str]] = None,
    resume_observation: bool = True,
    new_variance_limit: Optional[float] = None,
) -> ReviewOutcome:
    """Create a review outcome for testing."""
    return ReviewOutcome(
        review_id=review_id or str(uuid.uuid4()),
        reviewer_id="wa_reviewer_001",
        decision=decision,
        approved_changes=approved_changes or ["change_001", "change_002"],
        rejected_changes=[],
        modified_proposals={},
        feedback="Changes look safe and appropriate",
        new_constraints=[],
        resume_observation=resume_observation,
        new_variance_limit=new_variance_limit,
    )


def create_pattern_insight(
    pattern_id: Optional[str] = None,
    pattern_type: str = "behavioral",
    confidence: float = 0.85,
    occurrences: int = 10,
) -> PatternInsight:
    """Create a pattern insight for testing."""
    return PatternInsight(
        pattern_id=pattern_id or str(uuid.uuid4()),
        pattern_type=pattern_type,
        description="Test pattern description",
        confidence=confidence,
        occurrences=occurrences,
        last_seen=datetime.now(timezone.utc),
        metadata={},
    )


def create_detected_pattern(
    pattern_type: PatternType = PatternType.TEMPORAL,
    confidence: float = 0.85,
    occurrences: int = 5,
) -> DetectedPattern:
    """Create a detected pattern for testing."""
    from ciris_engine.schemas.infrastructure.feedback_loop import PatternMetrics
    
    return DetectedPattern(
        pattern_id=str(uuid.uuid4()),
        pattern_type=pattern_type,
        description="Test detected pattern",
        evidence_nodes=["event_001", "event_002"],
        detected_at=datetime.now(timezone.utc),
        metrics=PatternMetrics(
            occurrence_count=occurrences,
            average_value=0.75,
            peak_value=0.95,
            time_range_hours=24.0,
            data_points=100,
            trend="stable",
        ),
    )


def create_system_snapshot() -> SystemSnapshot:
    """Create a system snapshot for testing."""
    from ciris_engine.schemas.runtime.system_context import ChannelContext
    
    return SystemSnapshot(
        channel_id="test_channel",
        channel_context=ChannelContext(
            channel_id="test_channel",
            channel_type="test",
            created_at=datetime.now(timezone.utc),
            channel_name="Test Channel",
            is_active=True,
        ),
        system_counts={
            "total_tasks": 10,
            "total_thoughts": 5,
            "pending_tasks": 3,
            "pending_thoughts": 2,
        },
        agent_identity={"agent_id": "test_agent"},
        agent_version="1.0.0",
        service_health={"SelfObservationService": True},
        circuit_breaker_status={},
        resource_alerts=[],
        detected_secrets=[],
        user_profiles=[],
    )


def create_observability_analysis(
    window_hours: int = 6,
    patterns_count: int = 5,
    anomalies_count: int = 1,
) -> ObservabilityAnalysis:
    """Create an observability analysis for testing."""
    now = datetime.now(timezone.utc)
    return ObservabilityAnalysis(
        window_start=now - timedelta(hours=window_hours),
        window_end=now,
        total_signals=100,
        signals_by_type={"behavioral": 30, "temporal": 40, "performance": 30},
        patterns_detected=["behavioral", "temporal"] if patterns_count > 0 else [],
        anomalies_detected=["high_variance"] if anomalies_count > 0 else [],
        observation_opportunities=[],
    )


class MockSelfObservationService:
    """Full mock of self observation service for integration tests."""

    def __init__(
        self,
        time_service: Optional[MockTimeService] = None,
        memory_bus: Optional[MockMemoryBus] = None,
        telemetry_service: Optional[MockTelemetryService] = None,
    ):
        self.time_service = time_service or MockTimeService()
        self.memory_bus = memory_bus or MockMemoryBus()
        self.telemetry_service = telemetry_service or MockTelemetryService()
        self.identity_monitor = MockIdentityVarianceMonitor()
        self.pattern_analyzer = MockPatternAnalysisLoop()

        # State
        self.is_running = False
        self.current_state = ObservationState.LEARNING
        self.cycles_completed = 0

        # Mock all async methods
        self.initialize_baseline = AsyncMock(return_value="baseline_123")
        self.analyze_observability_window = AsyncMock(return_value=create_observability_analysis())
        self.trigger_adaptation_cycle = AsyncMock(return_value=create_observation_cycle_result())
        self.get_adaptation_status = AsyncMock(return_value=create_observation_status())
        self.get_pattern_library = AsyncMock()
        self.measure_adaptation_effectiveness = AsyncMock()
        self.get_improvement_report = AsyncMock()
        self.analyze_patterns = AsyncMock()
        self.get_detected_patterns = AsyncMock(return_value=[])
        self.get_action_frequency = AsyncMock(return_value={})
        self.get_pattern_insights = AsyncMock(return_value=[])
        self.resume_after_review = AsyncMock()
        self.emergency_stop = AsyncMock()
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.is_healthy = AsyncMock(return_value=True)
        self.get_capabilities = Mock()
        self.get_status = Mock()


__all__ = [
    "MockTimeService",
    "MockMemoryBus",
    "MockIdentityVarianceMonitor",
    "MockPatternAnalysisLoop",
    "MockTelemetryService",
    "MockServiceRegistry",
    "MockSelfObservationService",
    "create_agent_identity",
    "create_observation_cycle_result",
    "create_observation_status",
    "create_review_outcome",
    "create_pattern_insight",
    "create_detected_pattern",
    "create_system_snapshot",
    "create_observability_analysis",
]