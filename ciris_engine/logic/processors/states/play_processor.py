"""
Play processor for creative and experimental processing.
"""

import logging
from typing import Any, Dict, List

from ciris_engine.schemas.processors.results import PlayResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.types import JSONDict

from .work_processor import WorkProcessor

# ServiceProtocol import removed - processors aren't services

logger = logging.getLogger(__name__)


class PlayProcessor(WorkProcessor):
    """
    Handles the PLAY state for creative and experimental processing.

    Currently inherits from WorkProcessor but can be customized for:
    - Creative task prioritization
    - Experimental prompt variations
    - Less constrained processing
    - Learning through exploration
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize play processor."""
        super().__init__(*args, **kwargs)
        self.play_metrics = {"creative_tasks_processed": 0, "experiments_run": 0, "novel_approaches_tried": 0}

    def get_supported_states(self) -> List[AgentState]:
        """Play processor only handles PLAY state."""
        return [AgentState.PLAY]

    async def process(self, round_number: int) -> PlayResult:  # type: ignore[override]
        """
        Execute one round of play processing.
        Currently delegates to work processing but logs differently.
        """
        logger.info(f"Play round {round_number}: creative mode active")

        # Get WorkResult from parent
        work_result = await super().process(round_number)

        # Track creative metrics
        self.play_metrics["creative_tasks_processed"] += work_result.thoughts_processed

        logger.info(
            f"--- Finished Play Round {round_number} "
            f"(Processed: {work_result.thoughts_processed} creative thoughts) ---"
        )

        # Convert to PlayResult
        return PlayResult(
            thoughts_processed=work_result.thoughts_processed,
            errors=work_result.errors,
            duration_seconds=work_result.duration_seconds,
        )

    def get_play_stats(self) -> JSONDict:
        """Get play-specific statistics."""
        base_stats: JSONDict = {
            "last_activity": self.last_activity_time.isoformat(),
            "idle_duration_seconds": self.get_idle_duration(),
            "idle_rounds": self.idle_rounds,
            "active_tasks": self.task_manager.get_active_task_count(),
            "pending_tasks": self.task_manager.get_pending_task_count(),
            "pending_thoughts": self.thought_manager.get_pending_thought_count(),
            "processing_thoughts": self.thought_manager.get_processing_thought_count(),
            "total_rounds": self.metrics.rounds_completed,
            "total_processed": self.metrics.items_processed,
            "total_errors": self.metrics.errors,
        }
        base_stats.update(
            {
                "play_metrics": self.play_metrics.copy(),
                "mode": "play",
                "creativity_level": self._calculate_creativity_level(),
            }
        )
        return base_stats

    def _calculate_creativity_level(self) -> float:
        """
        Calculate a creativity level based on play metrics.
        Returns a value between 0.0 and 1.0.
        """
        if self.play_metrics["creative_tasks_processed"] == 0:
            return 0.0

        # Simple formula - can be made more sophisticated
        experiments_ratio = self.play_metrics["experiments_run"] / max(self.play_metrics["creative_tasks_processed"], 1)

        novel_ratio = self.play_metrics["novel_approaches_tried"] / max(
            self.play_metrics["creative_tasks_processed"], 1
        )

        return min((experiments_ratio + novel_ratio) / 2, 1.0)

    def _prioritize_creative_tasks(self, tasks: List[Any]) -> List[Any]:
        """
        Prioritize tasks that are marked as creative or experimental.

        Future implementation could:
        - Look for tasks with creative tags
        - Boost priority of experimental tasks
        - Prefer tasks that allow exploration
        """
        # For now, return tasks as-is
        return tasks

    def should_experiment(self, thought_content: str) -> bool:
        """
        Determine if we should try an experimental approach.

        Args:
            thought_content: The content of the thought being processed

        Returns:
            True if experimental approach should be tried
        """
        # Future implementation could analyze thought content
        # and decide when to try novel approaches

        # Simple heuristic for now - experiment 20% of the time
        import secrets

        return secrets.randbelow(100) < 20

    def get_status(self) -> JSONDict:
        """Get current play processor status and metrics."""
        base_status = super().get_status()
        play_stats = self.get_play_stats()
        base_status.update(
            {"processor_type": "play", "play_stats": play_stats, "creativity_level": self._calculate_creativity_level()}
        )
        return base_status
