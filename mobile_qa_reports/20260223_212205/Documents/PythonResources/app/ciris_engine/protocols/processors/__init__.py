"""
Processor protocols for CIRIS agent.

These protocols define the interfaces for:
- AgentProcessorProtocol: Main coordinator managing all states
- ProcessorProtocol: Base interface for state processors
"""

from .agent import AgentProcessorMetrics, AgentProcessorProtocol, ProcessingSchedule, QueueStatus, StepResult
from .base import ProcessorProtocol

__all__ = [
    "AgentProcessorProtocol",
    "ProcessorProtocol",
    "ProcessingSchedule",
    "AgentProcessorMetrics",
    "QueueStatus",
    "StepResult",
]
