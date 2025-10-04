from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable

from ciris_engine.schemas.conscience.core import ConscienceCheckResult
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult


@runtime_checkable
class ConscienceInterface(Protocol):
    """Protocol for all conscience implementations."""

    async def check(
        self,
        action: ActionSelectionDMAResult,
        context: Dict[str, Any],
    ) -> ConscienceCheckResult:
        """Check if action passes conscience."""
        ...
