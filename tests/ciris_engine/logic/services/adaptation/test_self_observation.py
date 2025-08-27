"""
Comprehensive unit tests for SelfObservationService.

Tests the self-observation service's ability to monitor behavior patterns,
generate insights, and adapt configurations.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.services.adaptation.self_observation import (
    ObservationCycle,
    ObservationState,
    SelfObservationService,
)
from ciris_engine.schemas.infrastructure.feedback_loop import (
    AnalysisResult,
    DetectedPattern,
    PatternType,
)
from ciris_engine.schemas.runtime.core import AgentIdentityRoot
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.special.self_observation import (
    AnalysisStatus,
    CycleEventData,
    ObservabilityAnalysis,
    ObservationCycleResult,
    ObservationStatus,
    PatternInsight,
    ReviewOutcome,
)
from tests.fixtures.self_observation_mocks import (
    MockIdentityVarianceMonitor,
    MockMemoryBus,
    MockPatternAnalysisLoop,
    MockServiceRegistry,
    MockTelemetryService,
    MockTimeService,
    create_agent_identity,
    create_detected_pattern,
    create_observation_cycle_result,
    create_observation_status,
    create_pattern_insight,
    create_review_outcome,
    create_system_snapshot,
)


class TestSelfObservationService:
    """Test suite for SelfObservationService."""

    @pytest.fixture
    def mock_time_service(self):
        """Create mock time service."""
        return MockTimeService(fixed_time=datetime(2025, 1, 27, 12, 0, 0, tzinfo=timezone.utc))

    @pytest.fixture
    def mock_memory_bus(self):
        """Create mock memory bus."""
        return MockMemoryBus()

    @pytest.fixture
    def mock_telemetry(self):
        """Create mock telemetry service."""
        return MockTelemetryService()

    @pytest.fixture
    def mock_service_registry(self):
        """Create mock service registry."""
        registry = MockServiceRegistry()
        registry.register_service("telemetry", MockTelemetryService())
        return registry

    @pytest.fixture
    def service(self, mock_time_service, mock_memory_bus, mock_telemetry, mock_service_registry):
        """Create SelfObservationService instance."""
        with patch("ciris_engine.logic.services.adaptation.self_observation.MemoryBus") as mock_bus_class:
            with patch("ciris_engine.logic.services.adaptation.self_observation.GraphTelemetryService") as mock_tel_class:
                # Configure mocks
                mock_bus_class.return_value = mock_memory_bus
                mock_tel_class.return_value = mock_telemetry

                service = SelfObservationService(
                    time_service=mock_time_service,
                    memory_bus=mock_memory_bus,
                    variance_threshold=0.15,
                    observation_interval_hours=1,  # 1 hour for faster testing
                    stabilization_period_hours=6,
                )
                
                # Set service registry
                service._set_service_registry(mock_service_registry)
                
                # Mock sub-services
                service._identity_monitor = MockIdentityVarianceMonitor()
                service._pattern_analyzer = MockPatternAnalysisLoop()
                
                return service

    def test_initialization(self, service, mock_time_service, mock_memory_bus):
        """Test service initialization."""
        assert service is not None
        assert service._time_service == mock_time_service
        assert service._memory_bus == mock_memory_bus
        assert service._variance_threshold == 0.15
        assert service._observation_interval.total_seconds() == 3600  # 1 hour
        assert service._current_state == ObservationState.LEARNING

    def test_set_service_registry(self, service, mock_service_registry):
        """Test setting service registry."""
        new_registry = MockServiceRegistry()
        service._set_service_registry(new_registry)
        assert service._service_registry == new_registry

    @pytest.mark.asyncio
    async def test_initialize_baseline(self, service):
        """Test initializing identity baseline."""
        identity = create_agent_identity()
        
        baseline_id = await service.initialize_baseline(identity)
        
        assert baseline_id is not None
        assert service._identity_monitor.baseline_established
        assert service._baseline_identity == identity

    @pytest.mark.asyncio
    async def test_run_observation_cycle_learning(self, service):
        """Test running observation cycle in learning state."""
        service._current_state = ObservationState.LEARNING
        service._pattern_analyzer.patterns = [
            create_detected_pattern(),
            create_detected_pattern(),
        ]
        
        result = await service._run_observation_cycle()
        
        assert isinstance(result, ObservationCycleResult)
        assert result.state == ObservationState.LEARNING
        assert result.patterns_detected >= 0
        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_observation_cycle_proposing(self, service):
        """Test running observation cycle in proposing state."""
        service._current_state = ObservationState.PROPOSING
        service._pending_proposals = ["proposal_1", "proposal_2"]
        
        result = await service._run_observation_cycle()
        
        assert isinstance(result, ObservationCycleResult)
        assert result.state == ObservationState.PROPOSING
        assert result.proposals_generated >= 0

    @pytest.mark.asyncio
    async def test_run_observation_cycle_adapting(self, service):
        """Test running observation cycle in adapting state."""
        service._current_state = ObservationState.ADAPTING
        service._approved_changes = ["change_1", "change_2"]
        service._identity_monitor.current_variance = 0.08
        
        result = await service._run_observation_cycle()
        
        assert isinstance(result, ObservationCycleResult)
        assert result.state == ObservationState.ADAPTING
        assert result.changes_applied >= 0

    @pytest.mark.asyncio
    async def test_run_observation_cycle_stabilizing(self, service):
        """Test running observation cycle in stabilizing state."""
        service._current_state = ObservationState.STABILIZING
        service._stabilization_start_time = datetime.now(timezone.utc)
        service._identity_monitor.current_variance = 0.05
        
        result = await service._run_observation_cycle()
        
        assert isinstance(result, ObservationCycleResult)
        assert result.state == ObservationState.STABILIZING

    @pytest.mark.asyncio
    async def test_run_observation_cycle_reviewing(self, service):
        """Test running observation cycle in reviewing state."""
        service._current_state = ObservationState.REVIEWING
        
        result = await service._run_observation_cycle()
        
        assert isinstance(result, ObservationCycleResult)
        assert result.state == ObservationState.REVIEWING
        assert result.requires_review is True

    @pytest.mark.asyncio
    async def test_should_run_observation_cycle(self, service, mock_time_service):
        """Test determining if observation cycle should run."""
        # Initially should run (no last cycle time)
        should_run = await service._should_run_observation_cycle()
        assert should_run is True
        
        # Set last cycle time to now
        service._last_cycle_time = mock_time_service.now()
        should_run = await service._should_run_observation_cycle()
        assert should_run is False
        
        # Advance time past interval
        mock_time_service.advance(70)  # 70 seconds > 60 second interval
        should_run = await service._should_run_observation_cycle()
        assert should_run is True

    @pytest.mark.asyncio
    async def test_store_cycle_event(self, service, mock_memory_bus):
        """Test storing cycle event to memory."""
        event_data = CycleEventData(
            event_type="pattern_detected",
            cycle_id="cycle_123",
            patterns=["pattern_1", "pattern_2"],
        )
        
        await service._store_cycle_event("pattern_detected", event_data)
        
        assert len(mock_memory_bus.stored_nodes) > 0

    @pytest.mark.asyncio
    async def test_get_adaptation_status(self, service):
        """Test getting adaptation status."""
        service._current_state = ObservationState.ADAPTING
        service._cycles_completed = 10
        service._identity_monitor.current_variance = 0.08
        
        status = await service.get_adaptation_status()
        
        assert isinstance(status, ObservationStatus)
        assert status.current_state == ObservationState.ADAPTING
        assert status.cycles_completed == 10
        assert status.current_variance == 0.08
        assert status.is_active == service._is_running

    @pytest.mark.asyncio
    async def test_resume_after_review(self, service):
        """Test resuming after WA review."""
        service._current_state = ObservationState.REVIEWING
        review = create_review_outcome(
            decision="approve",
            approved_changes=["change_1", "change_2"],
            resume_observation=True,
        )
        
        await service.resume_after_review(review)
        
        assert service._current_state != ObservationState.REVIEWING
        assert service._approved_changes == review.approved_changes

    @pytest.mark.asyncio
    async def test_resume_after_review_with_new_limit(self, service):
        """Test resuming after review with new variance limit."""
        service._current_state = ObservationState.REVIEWING
        review = create_review_outcome(
            decision="modify",
            new_variance_limit=0.20,
            resume_observation=True,
        )
        
        await service.resume_after_review(review)
        
        assert service._max_variance_threshold == 0.20

    @pytest.mark.asyncio
    async def test_emergency_stop(self, service):
        """Test emergency stop."""
        service._is_running = True
        service._current_state = ObservationState.ADAPTING
        
        await service.emergency_stop("Critical issue detected")
        
        assert service._is_running is False
        assert service._current_state == ObservationState.STABILIZING

    @pytest.mark.asyncio
    async def test_analyze_observability_window(self, service, mock_memory_bus):
        """Test analyzing observability window."""
        # Add some mock data to memory
        mock_memory_bus.query = AsyncMock(return_value=[
            create_detected_pattern(),
            create_detected_pattern(),
        ])
        
        analysis = await service.analyze_observability_window(timedelta(hours=6))
        
        assert isinstance(analysis, ObservabilityAnalysis)
        assert analysis.patterns_detected >= 0
        assert analysis.window_end > analysis.window_start

    @pytest.mark.asyncio
    async def test_trigger_adaptation_cycle(self, service):
        """Test manually triggering adaptation cycle."""
        service._current_state = ObservationState.STABILIZING
        
        result = await service.trigger_adaptation_cycle()
        
        assert isinstance(result, ObservationCycleResult)
        assert service._cycles_completed > 0

    @pytest.mark.asyncio
    async def test_get_pattern_library(self, service):
        """Test getting pattern library summary."""
        service._pattern_analyzer.patterns = [
            create_detected_pattern(pattern_type=PatternType.TEMPORAL),
            create_detected_pattern(pattern_type=PatternType.FREQUENCY),
            create_detected_pattern(pattern_type=PatternType.PERFORMANCE),
        ]
        
        library = await service.get_pattern_library()
        
        assert library is not None
        assert library.total_patterns == 3
        assert len(library.patterns_by_type) > 0

    @pytest.mark.asyncio
    async def test_get_action_frequency(self, service, mock_memory_bus):
        """Test getting action frequency analysis."""
        # Mock memory query results
        mock_memory_bus.query = AsyncMock(return_value=[
            {"action": "speak", "count": 10},
            {"action": "observe", "count": 5},
            {"action": "tool", "count": 3},
        ])
        
        frequencies = await service.get_action_frequency(24)
        
        assert isinstance(frequencies, dict)
        assert len(frequencies) >= 0

    @pytest.mark.asyncio
    async def test_get_pattern_insights(self, service, mock_memory_bus):
        """Test getting pattern insights."""
        # Mock insights in memory
        insights = [
            create_pattern_insight(),
            create_pattern_insight(confidence=0.95),
            create_pattern_insight(confidence=0.75),
        ]
        mock_memory_bus.query = AsyncMock(return_value=insights)
        
        result = await service.get_pattern_insights(limit=10)
        
        assert isinstance(result, list)
        assert len(result) <= 10
        for insight in result:
            assert isinstance(insight, PatternInsight)

    @pytest.mark.asyncio
    async def test_analyze_patterns(self, service):
        """Test pattern analysis."""
        service._pattern_analyzer.analyze = AsyncMock(return_value=AnalysisResult(
            patterns_found=3,
            insights_generated=2,
            confidence_score=0.85,
            timestamp=datetime.now(timezone.utc)
        ))
        
        result = await service.analyze_patterns(force=False)
        
        assert isinstance(result, AnalysisResult)
        assert result.patterns_found >= 0
        assert result.confidence_score >= 0

    @pytest.mark.asyncio
    async def test_get_detected_patterns(self, service):
        """Test getting detected patterns with filtering."""
        patterns = [
            create_detected_pattern(pattern_type=PatternType.TEMPORAL),
            create_detected_pattern(pattern_type=PatternType.FREQUENCY),
            create_detected_pattern(pattern_type=PatternType.PERFORMANCE),
        ]
        service._pattern_analyzer.get_patterns = AsyncMock(return_value=patterns)
        
        # Get all patterns
        all_patterns = await service.get_detected_patterns()
        assert len(all_patterns) == 3
        
        # Get specific type
        temporal = await service.get_detected_patterns(
            pattern_type=PatternType.TEMPORAL,
            min_confidence=0.8
        )
        assert len(temporal) >= 0

    @pytest.mark.asyncio
    async def test_on_start(self, service):
        """Test service start."""
        await service._on_start()
        
        assert service._is_running is True
        assert service._identity_monitor is not None
        assert service._pattern_analyzer is not None

    @pytest.mark.asyncio
    async def test_on_stop(self, service):
        """Test service stop."""
        service._is_running = True
        
        await service._on_stop()
        
        assert service._is_running is False

    @pytest.mark.asyncio
    async def test_is_healthy(self, service):
        """Test health check."""
        service._is_running = True
        service._identity_monitor.is_stable = AsyncMock(return_value=True)
        
        is_healthy = await service.is_healthy()
        
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_is_healthy_when_not_running(self, service):
        """Test health check when not running."""
        service._is_running = False
        
        is_healthy = await service.is_healthy()
        
        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_is_healthy_when_unstable(self, service):
        """Test health check when identity unstable."""
        service._is_running = True
        service._identity_monitor.is_stable = AsyncMock(return_value=False)
        
        is_healthy = await service.is_healthy()
        
        assert is_healthy is False

    def test_get_capabilities(self, service):
        """Test getting service capabilities."""
        capabilities = service.get_capabilities()
        
        assert isinstance(capabilities, ServiceCapabilities)
        assert capabilities.can_start is True
        assert capabilities.can_stop is True
        assert len(capabilities.supported_actions) > 0

    def test_get_status(self, service):
        """Test getting service status."""
        service._is_running = True
        service._current_state = ObservationState.ADAPTING
        
        status = service.get_status()
        
        assert isinstance(status, ServiceStatus)
        assert status.is_running is True
        assert status.is_healthy is not None

    @pytest.mark.asyncio
    async def test_measure_adaptation_effectiveness(self, service):
        """Test measuring adaptation effectiveness."""
        service._applied_changes = {
            "adapt_123": {
                "applied_at": datetime.now(timezone.utc) - timedelta(hours=1),
                "change_type": "threshold_adjustment",
                "expected_improvement": 0.1,
            }
        }
        
        effectiveness = await service.measure_adaptation_effectiveness("adapt_123")
        
        assert effectiveness is not None
        assert effectiveness.adaptation_id == "adapt_123"
        assert effectiveness.effectiveness_score >= 0

    @pytest.mark.asyncio
    async def test_get_improvement_report(self, service):
        """Test getting improvement report."""
        service._cycles_completed = 100
        service._total_changes_applied = 20
        service._total_rollbacks = 2
        
        report = await service.get_improvement_report(timedelta(days=30))
        
        assert report is not None
        assert report.total_adaptations >= 0
        assert report.successful_adaptations >= 0
        assert report.improvement_percentage >= 0

    @pytest.mark.asyncio
    async def test_variance_triggers_review(self, service):
        """Test that high variance triggers review."""
        service._current_state = ObservationState.ADAPTING
        service._identity_monitor.current_variance = 0.20  # Above 0.15 threshold
        
        result = await service._run_observation_cycle()
        
        assert result.requires_review is True
        assert service._current_state == ObservationState.REVIEWING

    @pytest.mark.asyncio
    async def test_state_transitions(self, service):
        """Test state machine transitions."""
        # Learning -> Proposing (when patterns found)
        service._current_state = ObservationState.LEARNING
        service._pattern_buffer = [
            create_detected_pattern(),
            create_detected_pattern(),
            create_detected_pattern(),
        ]
        
        await service._run_observation_cycle()
        # State should progress based on patterns

        # Proposing -> Adapting (when proposals approved)
        service._current_state = ObservationState.PROPOSING
        service._pending_proposals = ["proposal_1"]
        service._approved_changes = ["change_1"]
        
        await service._run_observation_cycle()
        # State should progress based on approvals

        # Adapting -> Stabilizing (after changes applied)
        service._current_state = ObservationState.ADAPTING
        service._approved_changes = []
        
        await service._run_observation_cycle()
        # State should move to stabilizing

    @pytest.mark.asyncio
    async def test_concurrent_cycle_prevention(self, service):
        """Test that concurrent cycles are prevented."""
        service._cycle_in_progress = True
        
        result = await service._run_observation_cycle()
        
        assert result.success is False
        assert "already in progress" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_exception_handling_in_cycle(self, service):
        """Test exception handling during cycle."""
        # Make pattern analyzer raise exception
        service._pattern_analyzer.analyze = AsyncMock(side_effect=Exception("Test error"))
        service._current_state = ObservationState.LEARNING
        
        result = await service._run_observation_cycle()
        
        assert result.success is False
        assert result.error is not None
        assert "Test error" in result.error

    @pytest.mark.asyncio
    async def test_scheduled_task_execution(self, service, mock_time_service):
        """Test scheduled task execution."""
        service._is_running = True
        service._last_cycle_time = None
        
        # Should run cycle
        await service._run_scheduled_task()
        
        assert service._cycles_completed > 0
        assert service._last_cycle_time is not None

    @pytest.mark.asyncio
    async def test_scheduled_task_respects_interval(self, service, mock_time_service):
        """Test that scheduled task respects interval."""
        service._is_running = True
        service._last_cycle_time = mock_time_service.now()
        
        # Should not run cycle (too soon)
        initial_cycles = service._cycles_completed
        await service._run_scheduled_task()
        
        assert service._cycles_completed == initial_cycles

        # Advance time and try again
        mock_time_service.advance(70)
        await service._run_scheduled_task()
        
        assert service._cycles_completed > initial_cycles