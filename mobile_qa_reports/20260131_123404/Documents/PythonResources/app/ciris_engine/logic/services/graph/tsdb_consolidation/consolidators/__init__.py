"""
Consolidation strategies for different data types.

Each consolidator handles a specific type of data:
- MetricsConsolidator: TSDB metrics from both correlations and graph nodes
- ConversationConsolidator: Service interactions and conversations
- TraceConsolidator: Trace spans and task processing
- AuditConsolidator: Audit entries and security events
- TaskConsolidator: Task outcomes and thought processes
- MemoryConsolidator: General memory nodes (concepts, identity, etc.)
"""

from .audit import AuditConsolidator
from .conversation import ConversationConsolidator
from .memory import MemoryConsolidator
from .metrics import MetricsConsolidator
from .task import TaskConsolidator
from .trace import TraceConsolidator

__all__ = [
    "MetricsConsolidator",
    "ConversationConsolidator",
    "TraceConsolidator",
    "AuditConsolidator",
    "TaskConsolidator",
    "MemoryConsolidator",
]
