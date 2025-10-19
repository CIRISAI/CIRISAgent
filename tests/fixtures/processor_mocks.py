"""Mock implementations of processor protocols for testing.

Note: These mocks will be enhanced after the protocol definitions
from 1.4.2-processor-protocols are merged.
"""
from typing import Any, Optional
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import DMAResults
from ciris_engine.schemas.processors.context import ProcessorContext
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
