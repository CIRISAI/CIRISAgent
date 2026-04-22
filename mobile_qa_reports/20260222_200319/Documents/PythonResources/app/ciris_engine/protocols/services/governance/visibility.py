"""Visibility Service Protocol."""

from abc import abstractmethod
from typing import Protocol

from ciris_engine.schemas.services.visibility import ReasoningTrace, TaskDecisionHistory, VisibilitySnapshot

from ...runtime.base import ServiceProtocol


class VisibilityServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for visibility service."""

    @abstractmethod
    async def get_current_state(self) -> VisibilitySnapshot:
        """Get current agent state snapshot."""
        ...

    @abstractmethod
    async def get_reasoning_trace(self, task_id: str) -> ReasoningTrace:
        """Get reasoning trace for a task."""
        ...

    @abstractmethod
    async def get_decision_history(self, task_id: str) -> TaskDecisionHistory:
        """Get decision history for a task."""
        ...

    @abstractmethod
    async def explain_action(self, action_id: str) -> str:
        """Explain why an action was taken."""
        ...
