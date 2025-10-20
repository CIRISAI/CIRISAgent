"""Mock implementations of processor protocols for testing.

Note: These mocks will be enhanced after the protocol definitions
from 1.4.2-processor-protocols are merged.
"""

from typing import Any, Optional

from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.context import ProcessorContext
from ciris_engine.schemas.processors.core import DMAResults
from ciris_engine.schemas.runtime.models import Thought


class MockDMAOrchestrator:
    """Mock DMA orchestrator for testing."""

    async def run_dmas(self, thought_item: Any, processing_context: ProcessorContext) -> DMAResults:
        return DMAResults()  # Return empty results

    async def run_action_selection(
        self,
        thought_item: Any,
        actual_thought: Thought,
        processing_context: ProcessorContext,
        dma_results: DMAResults,
        profile_name: str,
    ) -> ActionSelectionDMAResult:
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.OBSERVE,
            action_parameters={},
            rationale="Mock action",
        )


class MockContextBuilder:
    """Mock context builder for testing."""

    async def build_context(
        self, thought_id: str, additional_context: Optional[dict[str, Any]] = None
    ) -> ProcessorContext:
        return ProcessorContext(origin="mock")  # Return empty context with required origin


class MockConscienceRegistry:
    """Mock conscience registry for testing."""

    def get_consciences(self) -> list[Any]:
        return []  # Return empty list


def create_test_thought(thought_id: str, content: str, **kwargs: Any) -> Thought:
    """Create a test Thought instance with minimal required fields.

    Args:
        thought_id: The thought ID
        content: The thought content
        **kwargs: Additional optional fields

    Returns:
        Thought instance for testing
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    return Thought(
        thought_id=thought_id,
        source_task_id=kwargs.get("source_task_id", "test-task"),
        content=content,
        created_at=kwargs.get("created_at", now),
        updated_at=kwargs.get("updated_at", now),
        **{k: v for k, v in kwargs.items() if k not in ["source_task_id", "created_at", "updated_at"]}
    )


def create_test_epistemic_data():
    """Create test epistemic data for conscience results.

    Returns:
        EpistemicData instance for testing
    """
    from ciris_engine.schemas.conscience.core import EpistemicData

    return EpistemicData(
        entropy_level=0.3,
        coherence_level=0.8,
        uncertainty_acknowledged=True,
        reasoning_transparency=0.9,
    )
