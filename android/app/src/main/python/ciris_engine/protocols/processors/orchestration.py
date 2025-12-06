"""Protocol definitions for thought processor dependencies."""

from typing import Any, Optional, Protocol

from ciris_engine.schemas.conscience.core import ConscienceCheckResult
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.context import ProcessorContext
from ciris_engine.schemas.processors.core import ConscienceApplicationResult, DMAResults
from ciris_engine.schemas.runtime.models import Thought


class DMAOrchestratorProtocol(Protocol):
    """Protocol for DMA orchestration services."""

    async def run_dmas(self, thought_item: Any, processing_context: ProcessorContext) -> DMAResults:
        """Run all DMAs for a thought."""
        ...

    async def run_action_selection(
        self,
        thought_item: Any,
        actual_thought: Thought,
        processing_context: ProcessorContext,
        dma_results: DMAResults,
        profile_name: str,
    ) -> ActionSelectionDMAResult:
        """Run action selection DMA."""
        ...


class ContextBuilderProtocol(Protocol):
    """Protocol for context building services."""

    async def build_context(
        self, thought_id: str, additional_context: Optional[dict[str, Any]] = None
    ) -> ProcessorContext:
        """Build processing context for a thought."""
        ...


class ConscienceEntry:
    """Entry in conscience registry."""

    name: str
    conscience: "ConscienceProtocol"
    circuit_breaker: Optional[Any]


class ConscienceProtocol(Protocol):
    """Protocol for individual conscience implementations."""

    async def check(self, action_result: ActionSelectionDMAResult, context: Any) -> ConscienceCheckResult:
        """Check an action against conscience rules."""
        ...


class ConscienceRegistryProtocol(Protocol):
    """Protocol for conscience registry."""

    def get_consciences(self) -> list[ConscienceEntry]:
        """Get all registered consciences."""
        ...
