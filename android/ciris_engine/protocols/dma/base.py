"""
Decision Making Algorithm (DMA) protocols for the CIRIS Trinity Architecture.

These protocols define contracts for all decision making algorithms.
DMAs evaluate actions based on different criteria to guide agent behavior.
"""

from abc import abstractmethod
from typing import Any, List

from ciris_engine.protocols.runtime.base import BaseDMAProtocol

# ============================================================================
# CORE DMA PROTOCOLS
# ============================================================================


class PDMAProtocol(BaseDMAProtocol):
    """Principled Decision Making Algorithm - evaluates ethical implications."""

    # The evaluate method from BaseDMAProtocol is sufficient
    # Implementation returns EthicalDMAResult which contains:
    # - alignment_check: Detailed ethical analysis
    # - decision: The ethically optimal action
    # - rationale: Justification for the decision


class CSDMAProtocol(BaseDMAProtocol):
    """Common Sense Decision Making Algorithm - evaluates practical implications."""

    # The evaluate method from BaseDMAProtocol is sufficient
    # Implementation returns CSDMAResult which contains:
    # - plausibility_score: How plausible/practical the action is (0-1)
    # - flags: Any issues or concerns identified
    # - reasoning: Common sense reasoning about the action
    # - raw_llm_response: The full reasoning chain


class DSDMAProtocol(BaseDMAProtocol):
    """Domain Specific Decision Making Algorithm - evaluates based on agent's job/identity."""

    # The evaluate method from BaseDMAProtocol is sufficient
    # Implementation returns DSDMAResult which contains:
    # - score: Domain alignment score (0-1)
    # - recommended_action: Domain-specific recommendation
    # - flags: Any domain-specific concerns
    # - reasoning: Domain expertise reasoning


class ActionSelectionDMAProtocol(BaseDMAProtocol):
    """
    Recursive ethical evaluation of action selection itself.

    This DMA performs meta-evaluation: it evaluates the ethics of HOW we choose,
    not just WHAT we choose. It takes input from all other DMAs and ensures
    the selection process itself is principled.
    """

    # The evaluate method from BaseDMAProtocol is sufficient
    # Implementation returns ActionSelectionDMAResult which contains:
    # - selected_action: The action selected by the meta-evaluation
    # - ethical_analysis: Analysis of the selection ethics
    # - reasoning: Explanation of the recursive reasoning
    # - reliability: Reliability score for the selection


# ============================================================================
# SPECIALIZED DMA PROTOCOLS (Future Extensions)
# ============================================================================


class EmergencyDMAProtocol(BaseDMAProtocol):
    """Emergency Decision Making Algorithm - for critical situations."""

    @abstractmethod
    async def evaluate_emergency(self, _: Any) -> Any:
        """Evaluate emergency situation."""
        ...

    @abstractmethod
    def get_emergency_level(self) -> int:
        """Get emergency level (1-5)."""
        ...

    @abstractmethod
    async def get_emergency_protocols(self) -> List[str]:
        """Get emergency protocols to follow."""
        ...


class CollaborativeDMAProtocol(BaseDMAProtocol):
    """Collaborative Decision Making Algorithm - for multi-agent scenarios."""

    @abstractmethod
    async def evaluate_collaborative(self, action: Any, _: List[str]) -> Any:
        """Evaluate action in collaborative context."""
        ...

    @abstractmethod
    def get_consensus_score(self) -> float:
        """Get consensus score among agents."""
        ...

    @abstractmethod
    async def negotiate_action(self, _: List[Any]) -> Any:
        """Negotiate action among multiple proposals."""
        ...
