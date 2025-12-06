"""
Self-Observation Service

Enables the agent to observe its own behavior patterns and generate insights
for continuous learning. This service coordinates:
- IdentityVarianceMonitor (tracks drift from baseline identity)
- PatternAnalysisLoop (detects patterns and stores insights)
- Configurable pattern detection algorithms (via graph config)

The agent can modify its own observation algorithms through graph configuration,
enabling meta-learning and self-directed analytical evolution.
"""

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry
    from ciris_engine.schemas.runtime.enums import ServiceType

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.infrastructure.sub_services.identity_variance_monitor import IdentityVarianceMonitor
from ciris_engine.logic.infrastructure.sub_services.pattern_analysis_loop import PatternAnalysisLoop
from ciris_engine.logic.services.base_scheduled_service import BaseScheduledService
from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService
from ciris_engine.logic.utils.jsondict_helpers import get_float, get_int, get_str
from ciris_engine.protocols.infrastructure.base import RegistryAwareServiceProtocol, ServiceRegistryProtocol
from ciris_engine.protocols.runtime.base import ServiceProtocol
from ciris_engine.protocols.services import SelfObservationServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.infrastructure.behavioral_patterns import ActionFrequency, TemporalPattern
from ciris_engine.schemas.infrastructure.feedback_loop import AnalysisResult, DetectedPattern, PatternType
from ciris_engine.schemas.runtime.core import AgentIdentityRoot
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.special.self_observation import (
    AnalysisStatus,
    CycleEventData,
    LearningSummary,
    ObservabilityAnalysis,
    ObservationCycleResult,
    ObservationEffectiveness,
    ObservationOpportunity,
    ObservationStatus,
    PatternEffectiveness,
    PatternInsight,
    PatternLibrarySummary,
    ReviewOutcome,
    ServiceImprovementReport,
)

logger = logging.getLogger(__name__)


class ObservationState(str, Enum):
    """Current state of the self-observation system."""

    LEARNING = "learning"  # Gathering data, no changes yet
    PROPOSING = "proposing"  # Actively proposing adaptations
    ADAPTING = "adapting"  # Applying approved changes
    STABILIZING = "stabilizing"  # Waiting for changes to settle
    REVIEWING = "reviewing"  # Under WA review for variance


@dataclass
class ObservationCycle:
    """Represents one complete observation and analysis cycle."""

    cycle_id: str
    started_at: datetime
    state: ObservationState
    patterns_detected: int
    proposals_generated: int
    changes_applied: int
    variance_before: float
    variance_after: Optional[float]
    completed_at: Optional[datetime]


class SelfObservationService(BaseScheduledService, SelfObservationServiceProtocol, RegistryAwareServiceProtocol):
    """
    Service that enables self-observation, pattern detection, and insight generation.

    This service:
    1. Coordinates between variance monitoring, pattern detection, and telemetry
    2. Manages the adaptation lifecycle with safety checks
    3. Ensures changes stay within the 20% identity variance threshold
    4. Provides a unified interface for self-configuration

    The flow:
    Experience → Telemetry → Patterns → Insights → Agent Decisions → Config Changes
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        memory_bus: Optional[MemoryBus] = None,
        variance_threshold: float = 0.20,
        observation_interval_hours: int = 6,
        stabilization_period_hours: int = 24,
    ) -> None:
        # Convert observation interval to seconds for BaseScheduledService
        super().__init__(time_service=time_service, run_interval_seconds=observation_interval_hours * 3600)
        self._time_service: Optional[TimeServiceProtocol] = time_service
        self._memory_bus = memory_bus
        self._variance_threshold = variance_threshold
        self._observation_interval = timedelta(hours=observation_interval_hours)
        self._stabilization_period = timedelta(hours=stabilization_period_hours)

        # Component services
        self._variance_monitor: Optional[IdentityVarianceMonitor] = None
        self._pattern_loop: Optional[PatternAnalysisLoop] = None
        self._telemetry_service: Optional[GraphTelemetryService] = None

        # State tracking
        self._current_state = ObservationState.LEARNING
        self._current_cycle: Optional[ObservationCycle] = None
        self._adaptation_history: List[ObservationCycle] = []
        self._last_adaptation = self._time_service.now() if self._time_service else datetime.now()
        # No more pending proposals - agent decides through thoughts

        # Safety mechanisms
        self._emergency_stop = False
        self._consecutive_failures = 0
        self._max_failures = 3
        self._pattern_history: List[DetectedPattern] = []  # Add missing attribute for tracking pattern history
        self._last_variance_report = 0.0  # Store last variance for status reporting
        self._start_time = (
            self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        )  # Track when service started
        self._adaptation_errors = 0  # Track adaptation errors
        self._last_error: Optional[str] = None  # Store last error message

        # Tracking variables for custom metrics
        self._observations_made = 0
        self._patterns_detected = 0
        self._adaptations_triggered = 0
        self._performance_checks = 0
        self._anomalies_detected = 0
        self._self_corrections = 0
        self._learning_cycles = 0
        self._model_updates = 0

    async def attach_registry(self, registry: "ServiceRegistryProtocol") -> None:
        """
        Attach service registry for bus and service discovery.

        Implements RegistryAwareServiceProtocol to enable proper initialization
        of memory bus and component services.

        Args:
            registry: Service registry providing access to buses and services
        """
        self._service_registry = registry

        # Initialize memory bus
        if not self._memory_bus and registry:
            try:
                from ciris_engine.logic.buses import MemoryBus

                time_service = self._time_service
                if time_service is not None:
                    self._memory_bus = MemoryBus(registry, time_service)
            except Exception as e:
                logger.error(f"Failed to initialize memory bus: {e}")

        # Initialize component services
        await self._initialize_components()

    async def _initialize_components(self) -> None:
        """Initialize the component services."""
        try:
            # Create variance monitor
            time_service = self._time_service
            if time_service is not None:
                self._variance_monitor = IdentityVarianceMonitor(
                    time_service=time_service, memory_bus=self._memory_bus, variance_threshold=self._variance_threshold
                )
            if self._service_registry and self._variance_monitor:
                self._variance_monitor.set_service_registry(self._service_registry)

            # Create feedback loop
            if time_service is not None:
                self._pattern_loop = PatternAnalysisLoop(
                    time_service=time_service,
                    memory_bus=self._memory_bus,
                    analysis_interval_hours=int(self._observation_interval.total_seconds() / 3600),
                )
            if self._service_registry and self._pattern_loop:
                self._pattern_loop.set_service_registry(self._service_registry)

            # Create telemetry service
            self._telemetry_service = GraphTelemetryService(memory_bus=self._memory_bus)
            if self._service_registry:
                await self._telemetry_service.attach_registry(self._service_registry)

            logger.info("Self-configuration components initialized")

        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")

    async def _initialize_identity_baseline(self, identity: AgentIdentityRoot) -> str:
        """
        Initialize the identity baseline for variance monitoring.

        This should be called once during agent initialization.
        """
        if not self._variance_monitor:
            raise RuntimeError("Variance monitor not initialized")

        baseline_id = await self._variance_monitor.initialize_baseline(identity)
        logger.info(f"Identity baseline established: {baseline_id}")

        # Store initialization event
        init_node = GraphNode(
            id=f"self_observation_init_{int(self._time_service.now().timestamp() if self._time_service else datetime.now().timestamp())}",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "event_type": "self_observation_initialized",
                "baseline_id": baseline_id,
                "variance_threshold": self._variance_threshold,
                "timestamp": self._time_service.now().isoformat() if self._time_service else datetime.now().isoformat(),
            },
            updated_by="self_observation",
            updated_at=self._time_service.now() if self._time_service else datetime.now(),
        )

        if self._memory_bus:
            await self._memory_bus.memorize(init_node, handler_name="self_observation")

        return baseline_id

    async def _run_scheduled_task(self) -> None:
        """
        Execute the scheduled observation cycle.

        This is called periodically by BaseScheduledService.
        """
        # Check if we should actually run
        if not await self._should_run_observation_cycle():
            return

        # Run the observation cycle
        await self._run_observation_cycle()

    async def _should_run_observation_cycle(self) -> bool:
        """Check if it's time to run an adaptation cycle."""
        # Don't run if in emergency stop
        if self._emergency_stop:
            return False

        # Don't run if currently in a cycle
        if self._current_cycle and not self._current_cycle.completed_at:
            return False

        # Check state-based conditions
        if self._current_state == ObservationState.REVIEWING:
            # Wait for WA review to complete
            return False

        if self._current_state == ObservationState.STABILIZING:
            # Check if stabilization period has passed
            if not self._time_service:
                return False
            time_since_last = self._time_service.now() - self._last_adaptation
            if time_since_last < self._stabilization_period:
                return False

        # We're already scheduled by BaseScheduledService, so just check state
        return True

    async def _run_observation_cycle(self) -> ObservationCycleResult:
        """
        Run a variance check cycle.

        This method now only checks variance and triggers WA review if needed.
        Actual configuration changes happen through agent decisions.
        """
        try:
            # Check current variance
            if self._variance_monitor:
                variance_report = await self._variance_monitor.check_variance()
                # Store variance for status reporting
                self._last_variance_report = variance_report.total_variance
            else:
                return ObservationCycleResult(
                    cycle_id="no_monitor",
                    state=ObservationState(self._current_state.value),
                    started_at=self._time_service.now() if self._time_service else datetime.now(),
                    completed_at=self._time_service.now() if self._time_service else datetime.now(),
                    patterns_detected=0,
                    proposals_generated=0,
                    proposals_approved=0,
                    proposals_rejected=0,
                    changes_applied=0,
                    rollbacks_performed=0,
                    variance_before=0.0,
                    variance_after=0.0,
                    success=False,
                    requires_review=False,
                    error="Variance monitor not initialized",
                )

            cycle_id = f"variance_check_{int(self._time_service.now().timestamp() if self._time_service else datetime.now().timestamp())}"

            if variance_report.requires_wa_review:
                # Variance too high - enter review state
                self._current_state = ObservationState.REVIEWING
                await self._store_cycle_event(
                    "variance_exceeded",
                    CycleEventData(
                        event_type="variance_exceeded",
                        cycle_id=cycle_id,
                        variance=variance_report.total_variance,
                        metadata={"threshold": self._variance_threshold},
                    ),
                )

            return ObservationCycleResult(
                cycle_id=cycle_id,
                state=ObservationState(self._current_state.value),
                started_at=self._time_service.now() if self._time_service else datetime.now(),
                completed_at=self._time_service.now() if self._time_service else datetime.now(),
                patterns_detected=0,  # Patterns detected by feedback loop
                proposals_generated=0,  # No proposals - agent decides
                proposals_approved=0,
                proposals_rejected=0,
                changes_applied=0,  # Changes via MEMORIZE
                rollbacks_performed=0,
                variance_before=variance_report.total_variance,
                variance_after=variance_report.total_variance,
                success=True,
                requires_review=variance_report.requires_wa_review,
            )

        except Exception as e:
            logger.error(f"Variance check failed: {e}")
            self._consecutive_failures += 1

            if self._consecutive_failures >= self._max_failures:
                self._emergency_stop = True
                logger.error("Emergency stop activated after repeated failures")

            return ObservationCycleResult(
                cycle_id="error",
                state=ObservationState(self._current_state.value),
                started_at=self._time_service.now() if self._time_service else datetime.now(),
                completed_at=self._time_service.now() if self._time_service else datetime.now(),
                patterns_detected=0,
                proposals_generated=0,
                proposals_approved=0,
                proposals_rejected=0,
                changes_applied=0,
                rollbacks_performed=0,
                variance_before=0.0,
                variance_after=0.0,
                success=False,
                requires_review=False,
                error=str(e),
            )

    async def _store_cycle_event(self, event_type: str, data: CycleEventData) -> None:
        """Store an event during the adaptation cycle."""
        cycle_id = self._current_cycle.cycle_id if self._current_cycle else "unknown"
        event_node = GraphNode(
            id=f"cycle_event_{cycle_id}_{event_type}_{int(self._time_service.now().timestamp() if self._time_service else datetime.now().timestamp())}",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={
                "cycle_id": cycle_id,
                "event_type": event_type,
                "data": data.model_dump(),
                "timestamp": self._time_service.now().isoformat() if self._time_service else datetime.now().isoformat(),
            },
            updated_by="self_observation",
            updated_at=self._time_service.now() if self._time_service else datetime.now(),
        )

        if self._memory_bus:
            await self._memory_bus.memorize(event_node, handler_name="self_observation")

    async def _store_cycle_summary(self, cycle: ObservationCycle) -> None:
        """Store a summary of the completed adaptation cycle."""
        summary_node = GraphNode(
            id=f"cycle_summary_{cycle.cycle_id}",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "cycle_id": cycle.cycle_id,
                "duration_seconds": (
                    (cycle.completed_at - cycle.started_at).total_seconds() if cycle.completed_at else 0
                ),
                "patterns_detected": cycle.patterns_detected,
                "proposals_generated": cycle.proposals_generated,
                "changes_applied": cycle.changes_applied,
                "variance_before": cycle.variance_before,
                "variance_after": cycle.variance_after,
                "final_state": cycle.state.value,
                "success": cycle.changes_applied > 0 or cycle.patterns_detected > 0,
                "timestamp": (
                    cycle.completed_at.isoformat()
                    if cycle.completed_at
                    else (self._time_service.now().isoformat() if self._time_service else datetime.now().isoformat())
                ),
            },
            updated_by="self_observation",
            updated_at=self._time_service.now() if self._time_service else datetime.now(),
        )

        if self._memory_bus:
            await self._memory_bus.memorize(
                node=summary_node, handler_name="self_observation", metadata={"cycle_summary": True}
            )

    async def get_adaptation_status(self) -> ObservationStatus:
        """Get current status of the self-observation system."""
        # Get current variance from last check or default to 0
        current_variance = 0.0
        if self._variance_monitor and hasattr(self, "_last_variance_report"):
            current_variance = getattr(self, "_last_variance_report", 0.0)

        status = ObservationStatus(
            is_active=not self._emergency_stop,
            current_state=ObservationState(self._current_state.value),
            cycles_completed=len(self._adaptation_history),
            last_cycle_at=self._last_adaptation,
            current_variance=current_variance,
            patterns_in_buffer=0,  # No more proposal buffer
            pending_proposals=0,  # No more proposals
            average_cycle_duration_seconds=self._calculate_average_cycle_duration(),
            total_changes_applied=sum(c.changes_applied for c in self._adaptation_history),
            rollback_rate=self._calculate_rollback_rate(),
            identity_stable=self._consecutive_failures < 3,
            time_since_last_change=(
                (self._time_service.now() - self._last_adaptation).total_seconds()
                if self._time_service and self._last_adaptation
                else None
            ),
            under_review=self._current_state == ObservationState.REVIEWING,
            review_reason="Variance exceeded threshold" if self._current_state == ObservationState.REVIEWING else None,
        )

        return status

    async def resume_after_review(self, review_outcome: ReviewOutcome) -> None:
        """Resume self-configuration after WA review."""
        if self._current_state != ObservationState.REVIEWING:
            logger.warning("Resume called but not in REVIEWING state")
            return

        # Process review outcome
        if review_outcome.decision == "approve":
            self._current_state = ObservationState.STABILIZING
            logger.info("WA review approved - entering stabilization")
        else:
            self._current_state = ObservationState.LEARNING
            logger.info("WA review rejected - returning to learning")

        # Reset failure counter on successful review
        self._consecutive_failures = 0

        # Store review outcome
        review_node = GraphNode(
            id=f"wa_review_outcome_{int(self._time_service.now().timestamp() if self._time_service else datetime.now().timestamp())}",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "review_type": "identity_variance",
                "outcome": review_outcome.model_dump(),
                "new_state": self._current_state.value,
                "timestamp": self._time_service.now().isoformat() if self._time_service else datetime.now().isoformat(),
            },
            updated_by="self_observation",
            updated_at=self._time_service.now() if self._time_service else datetime.now(),
        )

        if self._memory_bus:
            await self._memory_bus.memorize(review_node, handler_name="self_observation")

    async def emergency_stop(self, reason: str) -> None:
        """Activate emergency stop for self-configuration."""
        self._emergency_stop = True
        logger.error(f"Emergency stop activated: {reason}")

        # Store emergency stop event
        stop_node = GraphNode(
            id=f"emergency_stop_{int(self._time_service.now().timestamp() if self._time_service else datetime.now().timestamp())}",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "event_type": "emergency_stop",
                "reason": reason,
                "previous_state": self._current_state.value,
                "timestamp": self._time_service.now().isoformat() if self._time_service else datetime.now().isoformat(),
            },
            updated_by="self_observation",
            updated_at=self._time_service.now() if self._time_service else datetime.now(),
        )

        if self._memory_bus:
            await self._memory_bus.memorize(stop_node, handler_name="self_observation")

    def _calculate_average_cycle_duration(self) -> float:
        """Calculate average duration of completed observation cycles."""
        if not self._adaptation_history:
            return 0.0

        completed_cycles = [cycle for cycle in self._adaptation_history if cycle.completed_at is not None]

        if not completed_cycles:
            return 0.0

        total_duration = 0.0
        for cycle in completed_cycles:
            if cycle.completed_at and cycle.started_at:
                duration = (cycle.completed_at - cycle.started_at).total_seconds()
                total_duration += duration

        return total_duration / len(completed_cycles)

    def _calculate_rollback_rate(self) -> float:
        """Calculate rollback rate from adaptation history."""
        if not self._adaptation_history:
            return 0.0

        total_changes = sum(cycle.changes_applied for cycle in self._adaptation_history)
        total_rollbacks = sum(getattr(cycle, "rollbacks_performed", 0) for cycle in self._adaptation_history)

        if total_changes == 0:
            return 0.0

        return total_rollbacks / total_changes

    async def _on_start(self) -> None:
        """Start the self-configuration service."""
        # Start component services
        if self._variance_monitor:
            await self._variance_monitor.start()
        if self._pattern_loop:
            await self._pattern_loop.start()
        if self._telemetry_service:
            await self._telemetry_service.start()

        logger.info("SelfObservationService started - enabling autonomous observation and learning")

    async def _on_stop(self) -> None:
        """Stop the service."""
        # Complete current cycle if any
        if self._current_cycle and not self._current_cycle.completed_at:
            self._current_cycle.completed_at = self._time_service.now() if self._time_service else datetime.now()
            await self._store_cycle_summary(self._current_cycle)

        # Stop component services
        if self._variance_monitor:
            await self._variance_monitor.stop()
        if self._pattern_loop:
            await self._pattern_loop.stop()
        if self._telemetry_service:
            await self._telemetry_service.stop()

        logger.info("SelfObservationService stopped")

    async def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        if self._emergency_stop:
            return False

        # Check component health
        components_healthy = all(
            [
                await self._variance_monitor.is_healthy() if self._variance_monitor else False,
                await self._pattern_loop.is_healthy() if self._pattern_loop else False,
                await self._telemetry_service.is_healthy() if self._telemetry_service else False,
            ]
        )

        return components_healthy and self._consecutive_failures < self._max_failures

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="SelfObservationService",
            actions=["adapt_configuration", "monitor_identity", "process_feedback", "emergency_stop"],
            version="1.0.0",
            dependencies=["variance_monitor", "feedback_loop", "telemetry_service"],
            metadata=None,
        )

    def get_status(self) -> ServiceStatus:
        """Get current service status."""
        # Let BaseScheduledService handle the status
        status = super().get_status()

        # Add our custom metrics
        if status.custom_metrics is not None:
            status.custom_metrics.update(
                {
                    "adaptation_count": float(len(self._adaptation_history)),
                    "consecutive_failures": float(self._consecutive_failures),
                    "emergency_stop": float(self._emergency_stop),
                    "changes_since_last_adaptation": float(
                        sum(c.changes_applied for c in self._adaptation_history[-1:]) if self._adaptation_history else 0
                    ),
                    "current_variance": self._last_variance_report,
                }
            )

        return status

    # ========== New Protocol Methods for 1000-Year Operation ==========

    async def initialize_baseline(self, identity: AgentIdentityRoot) -> str:
        """
        Establish identity baseline for variance monitoring.
        This is an alias for _initialize_identity_baseline to match the protocol.
        """
        return await self._initialize_identity_baseline(identity)

    async def analyze_observability_window(self, window: timedelta = timedelta(hours=6)) -> ObservabilityAnalysis:
        """
        Analyze all observability signals for adaptation opportunities.

        This method looks at insights stored by the feedback loop.
        """
        current_time = self._time_service.now() if self._time_service else datetime.now()
        window_start = current_time - window

        analysis = ObservabilityAnalysis(
            window_start=window_start,
            window_end=current_time,
            total_signals=0,
            signals_by_type={},
            observation_opportunities=[],
        )

        if not self._memory_bus:
            return analysis

        # Query for insights in the window
        from ciris_engine.schemas.services.operations import MemoryQuery

        query = MemoryQuery(
            node_id="behavioral_patterns",  # MemoryQuery requires node_id
            scope=GraphScope.LOCAL,
            type=NodeType.CONCEPT,
            include_edges=False,
            depth=1,
        )

        insights = await self._memory_bus.recall(query, handler_name="self_observation")

        # Process insights into opportunities
        for insight in insights:
            if isinstance(insight.attributes, dict) and insight.attributes.get("actionable", False):
                opportunity = ObservationOpportunity(
                    opportunity_id=f"opp_{insight.id}",
                    trigger_signals=[],  # No specific signals, derived from patterns
                    proposed_changes=[],  # Agent decides on changes
                    expected_improvement={"general": 0.1},  # Conservative estimate
                    risk_assessment="low",  # All insights are pre-filtered as safe
                    priority=1,
                )
                analysis.observation_opportunities.append(opportunity)

        analysis.total_signals = len(insights)

        return analysis

    async def trigger_adaptation_cycle(self) -> ObservationCycleResult:
        """
        Manually trigger an adaptation assessment cycle.

        This now just runs a variance check.
        """
        if self._emergency_stop:
            return ObservationCycleResult(
                cycle_id="manual_trigger_blocked",
                state=ObservationState(self._current_state.value),
                started_at=self._time_service.now() if self._time_service else datetime.now(),
                completed_at=self._time_service.now() if self._time_service else datetime.now(),
                patterns_detected=0,
                proposals_generated=0,
                proposals_approved=0,
                proposals_rejected=0,
                changes_applied=0,
                rollbacks_performed=0,
                variance_before=0.0,
                variance_after=0.0,
                success=False,
                requires_review=False,
                error="Emergency stop active",
            )

        # Run variance check
        return await self._run_observation_cycle()

    async def get_pattern_library(self) -> PatternLibrarySummary:
        """
        Get summary of learned adaptation patterns.

        Patterns are now insights stored by the feedback loop.
        """
        summary = PatternLibrarySummary(
            total_patterns=0,
            high_reliability_patterns=0,
            recently_used_patterns=0,
            most_effective_patterns=[],
            pattern_categories={},
        )

        if not self._memory_bus:
            return summary

        # Query for pattern nodes
        from ciris_engine.schemas.services.operations import MemoryQuery

        query = MemoryQuery(
            node_id="pattern_library",  # MemoryQuery requires node_id
            scope=GraphScope.LOCAL,
            type=NodeType.CONCEPT,
            include_edges=False,
            depth=1,
        )

        patterns = await self._memory_bus.recall(query, handler_name="self_observation")

        summary.total_patterns = len(patterns)

        # Group by type
        for pattern in patterns:
            if isinstance(pattern.attributes, dict):
                pattern_type = get_str(pattern.attributes, "pattern_type", "unknown")
                if pattern_type not in summary.pattern_categories:
                    summary.pattern_categories[pattern_type] = 0
                summary.pattern_categories[pattern_type] += 1

        return summary

    async def measure_adaptation_effectiveness(self, adaptation_id: str) -> ObservationEffectiveness:
        """
        Measure if an adaptation actually improved the system.

        Since adaptations are now agent-driven, effectiveness
        is measured by variance stability.
        """
        effectiveness = ObservationEffectiveness(
            observation_id=adaptation_id,
            measurement_period_hours=24,
            overall_effectiveness=0.0,
            recommendation="keep",  # Default recommendation
        )

        # Check if variance is stable
        if self._variance_monitor and hasattr(self, "_last_variance_report"):
            current_variance = self._last_variance_report
            if current_variance < self._variance_threshold:
                effectiveness.recommendation = "keep"
                effectiveness.overall_effectiveness = 1.0 - (current_variance / self._variance_threshold)
            else:
                effectiveness.recommendation = "review"

        return effectiveness

    async def get_improvement_report(self, period: timedelta = timedelta(days=30)) -> ServiceImprovementReport:
        """
        Generate service improvement report for period.
        """
        current_time = self._time_service.now() if self._time_service else datetime.now()
        period_start = current_time - period

        report = ServiceImprovementReport(
            report_period_start=period_start,
            report_period_end=current_time,
            total_observations=0,
            successful_observations=0,
            rolled_back_observations=0,
            average_performance_improvement=0.0,
            error_rate_reduction=0.0,
            resource_efficiency_gain=0.0,
            starting_variance=0.0,
            ending_variance=self._last_variance_report if hasattr(self, "_last_variance_report") else 0.0,
            peak_variance=0.0,
            top_improvements=[],
            recommendations=[],
        )

        # Count variance checks in period
        for cycle in self._adaptation_history:
            if hasattr(cycle, "started_at") and cycle.started_at >= period_start:
                report.total_observations += 1
                if hasattr(cycle, "success") and cycle.success:
                    report.successful_observations += 1

        # Add recommendations based on current state
        if self._emergency_stop:
            report.recommendations.append("Clear emergency stop and investigate cause")
        if self._consecutive_failures > 0:
            report.recommendations.append("Investigate variance check failures")

        return report

    # ========== Pattern Detection Protocol Methods ==========

    async def analyze_patterns(self, force: bool = False) -> AnalysisResult:
        """
        Analyze recent system behavior and detect patterns.

        Delegates to the PatternAnalysisLoop component.
        """
        if self._pattern_loop:
            return await self._pattern_loop.analyze_and_adapt(force=force)

        # Return empty result if no pattern loop
        return AnalysisResult(
            status="no_pattern_loop",
            patterns_detected=0,
            insights_stored=0,
            timestamp=self._time_service.now() if self._time_service else datetime.now(),
            next_analysis_in=None,
            error="Pattern analysis loop not initialized",
        )

    async def get_detected_patterns(
        self, pattern_type: Optional[PatternType] = None, hours: int = 24
    ) -> List[DetectedPattern]:
        """
        Get recently detected patterns.

        Queries the pattern loop for detected patterns.
        """
        if not self._pattern_loop:
            return []

        # Get patterns from the pattern loop
        all_patterns = list(self._pattern_loop._detected_patterns.values())

        # Filter by time window
        cutoff_time = (self._time_service.now() if self._time_service else datetime.now()) - timedelta(hours=hours)
        recent_patterns = [p for p in all_patterns if p.detected_at >= cutoff_time]

        # Filter by type if specified
        if pattern_type:
            recent_patterns = [p for p in recent_patterns if p.pattern_type == pattern_type]

        return recent_patterns

    async def get_action_frequency(self, hours: int = 24) -> Dict[str, ActionFrequency]:
        """
        Get frequency analysis of agent actions.

        Analyzes telemetry data to compute action frequencies.
        """
        action_frequencies: Dict[str, ActionFrequency] = {}

        if not self._memory_bus:
            return action_frequencies

        # Query telemetry nodes from memory
        from ciris_engine.schemas.services.operations import MemoryQuery

        query = MemoryQuery(
            node_id="telemetry_metrics", scope=GraphScope.LOCAL, type=NodeType.TSDB_DATA, include_edges=False, depth=1
        )

        try:
            telemetry_nodes = await self._memory_bus.recall(query, handler_name="self_observation")

            # Count actions in the time window
            cutoff_time = (self._time_service.now() if self._time_service else datetime.now()) - timedelta(hours=hours)
            action_counts: Dict[str, List[datetime]] = defaultdict(list)

            for node in telemetry_nodes:
                if isinstance(node.attributes, dict) and node.attributes.get("action"):
                    action_name = get_str(node.attributes, "action", "")
                    timestamp_str = get_str(node.attributes, "timestamp", "")
                    if timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str)
                        if timestamp >= cutoff_time:
                            action_counts[action_name].append(timestamp)

            # Build frequency objects
            for action, timestamps in action_counts.items():
                timestamps_sorted = sorted(timestamps)
                daily_average = len(timestamps) / (hours / 24.0) if hours > 0 else 0.0

                action_frequencies[action] = ActionFrequency(
                    action=action,
                    count=len(timestamps),
                    evidence=[ts.isoformat() for ts in timestamps_sorted[-3:]],  # Last 3 examples
                    last_seen=(
                        timestamps_sorted[-1]
                        if timestamps_sorted
                        else (self._time_service.now() if self._time_service else datetime.now())
                    ),
                    daily_average=daily_average,
                )

        except Exception as e:
            logger.error(f"Failed to get action frequency: {e}")

        return action_frequencies

    async def get_pattern_insights(self, limit: int = 50) -> List[PatternInsight]:
        """
        Get stored pattern insights from graph memory.
        """
        insights: List[PatternInsight] = []

        if not self._memory_bus:
            return insights

        # Query insight nodes
        from ciris_engine.schemas.services.operations import MemoryQuery

        query = MemoryQuery(
            node_id="pattern_insights", scope=GraphScope.LOCAL, type=NodeType.CONCEPT, include_edges=False, depth=1
        )

        try:
            insight_nodes = await self._memory_bus.recall(query, handler_name="self_observation")

            # Convert to PatternInsight objects
            for node in insight_nodes[:limit]:
                if isinstance(node.attributes, dict):
                    # Map detected_at to last_seen for schema compatibility
                    last_seen_str = get_str(node.attributes, "detected_at", "")
                    if last_seen_str:
                        try:
                            last_seen_dt = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            last_seen_dt = datetime.now()
                    else:
                        last_seen_dt = datetime.now()

                    insights.append(
                        PatternInsight(
                            pattern_id=node.id,
                            pattern_type=get_str(node.attributes, "pattern_type", "unknown"),
                            description=get_str(node.attributes, "description", ""),
                            confidence=get_float(node.attributes, "confidence", 0.0),
                            occurrences=get_int(node.attributes, "occurrences", 1),
                            last_seen=last_seen_dt,
                            metadata=(
                                node.attributes.get("metadata", {})
                                if isinstance(node.attributes.get("metadata"), dict)
                                else {}
                            ),
                        )
                    )

        except Exception as e:
            logger.error(f"Failed to get pattern insights: {e}")

        return insights

    async def get_learning_summary(self) -> LearningSummary:
        """
        Get summary of what the system has learned.
        """
        patterns = await self.get_detected_patterns(hours=168)  # 1 week
        action_freq = await self.get_action_frequency(hours=168)
        insights = await self.get_pattern_insights(limit=10)

        # Group patterns by type
        patterns_by_type: Dict[str, int] = defaultdict(int)
        for pattern in patterns:
            patterns_by_type[pattern.pattern_type.value] += 1

        # Find most/least used actions
        sorted_actions = sorted(action_freq.items(), key=lambda x: x[1].count, reverse=True)
        most_used = [name for name, _ in sorted_actions[:5]]
        least_used = [name for name, _ in sorted_actions[-5:] if _.count > 0]

        action_frequencies = {name: freq.count for name, freq in action_freq.items()}

        recent_insight_descriptions = [insight.description for insight in insights[:5]]

        current_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        # Ensure both datetimes are timezone-aware for subtraction
        if hasattr(self, "_start_time") and self._start_time is not None:
            if self._start_time.tzinfo is None:
                self._start_time = self._start_time.replace(tzinfo=timezone.utc)
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)
            days_running = max(1, (current_time - self._start_time).days)
        else:
            # Fallback if _start_time is not set
            days_running = 1
        learning_rate = len(patterns) / days_running

        return LearningSummary(
            total_patterns=len(patterns),
            patterns_by_type=dict(patterns_by_type),
            action_frequencies=action_frequencies,
            most_used_actions=most_used,
            least_used_actions=least_used,
            insights_count=len(insights),
            recent_insights=recent_insight_descriptions,
            learning_rate=learning_rate,
            recommendation="continue" if len(patterns) > 10 else "gather more data",
        )

    async def get_temporal_patterns(self, hours: int = 168) -> List[TemporalPattern]:
        """
        Get temporal patterns (daily, weekly cycles).
        """
        temporal_patterns = []

        # Get patterns of temporal type
        patterns = await self.get_detected_patterns(pattern_type=PatternType.TEMPORAL, hours=hours)

        # Convert to TemporalPattern objects
        for pattern in patterns:
            temporal_patterns.append(
                TemporalPattern(
                    pattern_id=pattern.pattern_id,
                    pattern_type=pattern.metrics.metadata.get("temporal_type", "unknown"),
                    time_window=pattern.metrics.metadata.get("time_window", ""),
                    activity_description=pattern.description,
                    occurrence_count=pattern.metrics.occurrence_count,
                    first_detected=pattern.detected_at,
                    last_observed=pattern.detected_at,  # Would need to track this separately
                    metrics={
                        "average_value": pattern.metrics.average_value,
                        "peak_value": pattern.metrics.peak_value,
                        "data_points": float(pattern.metrics.data_points),
                    },
                )
            )

        return temporal_patterns

    async def get_pattern_effectiveness(self, pattern_id: str) -> Optional[PatternEffectiveness]:
        """
        Get effectiveness metrics for a specific pattern.
        """

        # This would need to track whether acting on patterns improved outcomes
        # For now, return a simple structure

        # Check if pattern exists
        if self._pattern_loop and pattern_id in self._pattern_loop._detected_patterns:
            pattern = self._pattern_loop._detected_patterns[pattern_id]

            return PatternEffectiveness(
                pattern_id=pattern_id,
                pattern_type=pattern.pattern_type.value,
                times_applied=0,  # Would need to track this
                success_rate=0.0,  # Would need to track outcomes
                average_improvement=0.0,  # Would need metrics
                last_applied=None,
                recommendation="monitor",  # or "apply", "ignore"
            )

        return None

    async def get_analysis_status(self) -> AnalysisStatus:
        """
        Get current analysis status.
        """
        time_since_last = (self._time_service.now() if self._time_service else datetime.now()) - self._last_adaptation
        next_analysis_in = max(0, self._observation_interval.total_seconds() - time_since_last.total_seconds())

        # Get total patterns and insights
        patterns_detected = len(self._pattern_history)
        insights = await self.get_pattern_insights()

        return AnalysisStatus(
            is_running=not self._emergency_stop,
            last_analysis=self._last_adaptation,
            next_analysis_in_seconds=next_analysis_in,
            patterns_detected=patterns_detected,
            insights_generated=len(insights),
            analysis_interval_seconds=self._observation_interval.total_seconds(),
            error_count=self._adaptation_errors,
            last_error=self._last_error,
        )

    def get_service_type(self) -> "ServiceType":
        """Get the service type enum value."""
        from ciris_engine.schemas.runtime.enums import ServiceType

        # Self-observation is closest to visibility in available ServiceType options
        return ServiceType.VISIBILITY

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [
            "observe",
            "analyze_patterns",
            "get_insights",
            "get_variance",
            "pause_adaptation",
            "resume_adaptation",
            "emergency_stop",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        return self._time_service is not None

    async def get_metrics(self) -> Dict[str, float]:
        """Get all self-observation metrics including base, custom, and v1.4.3 specific."""
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "self_observation_observations": float(self._observations_made),
                "self_observation_patterns_detected": float(self._patterns_detected),
                "self_observation_identity_variance": float(self._last_variance_report),
                "self_observation_uptime_seconds": self._calculate_uptime(),
            }
        )

        return metrics

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect self-observation metrics."""
        metrics = super()._collect_custom_metrics()

        # Calculate observation rate
        obs_rate = 0.0
        if hasattr(self, "_start_time") and self._start_time:
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()
            if uptime > 0:
                obs_rate = self._observations_made / uptime

        metrics.update(
            {
                "observations_made": float(self._observations_made),
                "patterns_detected": float(self._patterns_detected),
                "adaptations_triggered": float(self._adaptations_triggered),
                "performance_checks": float(self._performance_checks),
                "anomalies_detected": float(self._anomalies_detected),
                "self_corrections": float(self._self_corrections),
                "learning_cycles": float(self._learning_cycles),
                "model_updates": float(self._model_updates),
                "observation_rate_per_hour": obs_rate * 3600,
                "pattern_variance_monitor_active": 1.0,  # Sub-service
                "identity_variance_monitor_active": 1.0,  # Sub-service
                "analysis_loop_active": 1.0,  # Pattern analysis loop
            }
        )

        return metrics
