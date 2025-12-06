"""
Agent state definitions for processor state management.

Defines the operational states an agent can be in.
"""

from enum import Enum


class AgentState(str, Enum):
    """High-level operational states for CIRIS agent."""

    WAKEUP = "wakeup"
    DREAM = "dream"
    PLAY = "play"
    WORK = "work"
    SOLITUDE = "solitude"
    SHUTDOWN = "shutdown"


__all__ = ["AgentState"]
