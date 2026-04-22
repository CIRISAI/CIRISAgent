"""
Protocol for Self-Observation Service - Pattern detection and learning.

This service observes system behavior, detects patterns, and stores insights
for the agent's autonomous adaptation within its identity bounds.
"""

from abc import abstractmethod
from datetime import timedelta
from typing import TYPE_CHECKING, List, Optional, Protocol

from ...runtime.base import ServiceProtocol

# Import forward references for schemas
if TYPE_CHECKING:
    from ciris_engine.schemas.infrastructure.behavioral_patterns import ActionFrequency, TemporalPattern
    from ciris_engine.schemas.infrastructure.feedback_loop import AnalysisResult, DetectedPattern, PatternType
    from ciris_engine.schemas.runtime.core import AgentIdentityRoot
    from ciris_engine.schemas.services.special.self_observation import (
        AnalysisStatus,
        LearningSummary,
        ObservabilityAnalysis,
        ObservationCycleResult,
        ObservationEffectiveness,
        ObservationStatus,
        PatternEffectiveness,
        PatternInsight,
        PatternLibrarySummary,
        ReviewOutcome,
        ServiceImprovementReport,
    )


class SelfObservationServiceProtocol(ServiceProtocol, Protocol):
    """
    Protocol for self-observation service.

    Implements continuous observation and pattern detection to enable
    autonomous adaptation through stored insights.
    """

    # ========== Pattern Detection ==========

    @abstractmethod
    async def analyze_patterns(self, force: bool = False) -> "AnalysisResult":
        """
        Analyze recent system behavior and detect patterns.

        This is the main entry point that:
        1. Detects patterns from metrics and telemetry
        2. Stores pattern insights for agent introspection
        3. Updates learning state

        Args:
            force: Force analysis even if not due

        Returns:
            AnalysisResult with patterns detected and insights stored
        """
        ...

    @abstractmethod
    async def get_detected_patterns(
        self, pattern_type: Optional["PatternType"] = None, hours: int = 24
    ) -> List["DetectedPattern"]:
        """
        Get recently detected patterns.

        Args:
            pattern_type: Filter by pattern type (temporal, frequency, etc.)
            hours: Look back period

        Returns:
            List of detected patterns
        """
        ...

    @abstractmethod
    async def get_action_frequency(self, hours: int = 24) -> dict[str, "ActionFrequency"]:
        """
        Get frequency analysis of agent actions.

        Args:
            hours: Analysis window

        Returns:
            Map of action -> frequency data
        """
        ...

    # ========== Pattern Insights ==========

    @abstractmethod
    async def get_pattern_insights(self, limit: int = 50) -> List["PatternInsight"]:
        """
        Get stored pattern insights.

        These are the insights stored in graph memory for the agent
        to use during its reasoning process.

        Args:
            limit: Maximum insights to return

        Returns:
            List of PatternInsight objects from graph memory
        """
        ...

    @abstractmethod
    async def get_learning_summary(self) -> "LearningSummary":
        """
        Get summary of what the system has learned.

        Returns:
            LearningSummary object with patterns, frequencies, and adaptations
        """
        ...

    # ========== Temporal Analysis ==========

    @abstractmethod
    async def get_temporal_patterns(self, hours: int = 168) -> List["TemporalPattern"]:  # 1 week
        """
        Get temporal patterns (daily, weekly cycles).

        Args:
            hours: Analysis window

        Returns:
            List of temporal patterns detected
        """
        ...

    # ========== Effectiveness Tracking ==========

    @abstractmethod
    async def get_pattern_effectiveness(self, pattern_id: str) -> Optional["PatternEffectiveness"]:
        """
        Get effectiveness metrics for a specific pattern.

        Tracks whether acting on this pattern improved outcomes.

        Args:
            pattern_id: ID of pattern to check

        Returns:
            PatternEffectiveness object if available
        """
        ...

    # ========== Service Status ==========

    @abstractmethod
    async def get_analysis_status(self) -> "AnalysisStatus":
        """
        Get current analysis status.

        Returns:
            AnalysisStatus object including last analysis time, patterns detected, etc.
        """
        ...

    # ========== Adaptation and Identity Management ==========

    @abstractmethod
    async def initialize_baseline(self, identity: "AgentIdentityRoot") -> str:
        """
        Establish identity baseline for variance monitoring.

        Args:
            identity: The agent's identity root

        Returns:
            Baseline ID
        """
        ...

    @abstractmethod
    async def get_adaptation_status(self) -> "ObservationStatus":
        """
        Get current status of the self-observation system.

        Returns:
            ObservationStatus with current state and metrics
        """
        ...

    @abstractmethod
    async def analyze_observability_window(self, window: timedelta = timedelta(hours=6)) -> "ObservabilityAnalysis":
        """
        Analyze all observability signals for adaptation opportunities.

        Args:
            window: Time window to analyze

        Returns:
            ObservabilityAnalysis with signals and opportunities
        """
        ...

    @abstractmethod
    async def trigger_adaptation_cycle(self) -> "ObservationCycleResult":
        """
        Manually trigger an adaptation assessment cycle.

        Returns:
            ObservationCycleResult with cycle outcomes
        """
        ...

    @abstractmethod
    async def get_pattern_library(self) -> "PatternLibrarySummary":
        """
        Get summary of learned adaptation patterns.

        Returns:
            PatternLibrarySummary with pattern statistics
        """
        ...

    @abstractmethod
    async def measure_adaptation_effectiveness(self, adaptation_id: str) -> "ObservationEffectiveness":
        """
        Measure if an adaptation actually improved the system.

        Args:
            adaptation_id: ID of the adaptation to measure

        Returns:
            ObservationEffectiveness metrics
        """
        ...

    @abstractmethod
    async def get_improvement_report(self, period: timedelta = timedelta(days=30)) -> "ServiceImprovementReport":
        """
        Generate service improvement report for period.

        Args:
            period: Time period to analyze

        Returns:
            ServiceImprovementReport with metrics and recommendations
        """
        ...

    @abstractmethod
    async def resume_after_review(self, review_outcome: "ReviewOutcome") -> None:
        """
        Resume self-configuration after WA review.

        Args:
            review_outcome: The outcome of the WA review
        """
        ...

    @abstractmethod
    async def emergency_stop(self, reason: str) -> None:
        """
        Activate emergency stop for self-configuration.

        Args:
            reason: Reason for emergency stop
        """
        ...
