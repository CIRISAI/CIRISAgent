from __future__ import annotations

from typing import Protocol, runtime_checkable

from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import ConscienceCheckResult
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.types import JSONDict


@runtime_checkable
class ConscienceInterface(Protocol):
    """Protocol for all conscience implementations.

    All conscience check implementations must accept ConscienceCheckContext
    instead of JSONDict for type safety.
    """

    async def check(
        self,
        action: ActionSelectionDMAResult,
        context: ConscienceCheckContext,
    ) -> ConscienceCheckResult:
        """Check if action passes conscience evaluation.

        Args:
            action: The action selection result to evaluate
            context: Typed context including thought, task, and system state

        Returns:
            ConscienceCheckResult with evaluation details
        """
        ...
