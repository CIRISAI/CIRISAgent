"""DMA decision schemas for contract-driven architecture."""

from .compose import BlockClass, BlockDisposition, ComposedBlock, ComposeDumpMeta, GateRegime
from .faculty import ConscienceFailureContext, EnhancedDMAInputs, FacultyContext, FacultyEvaluationSet, FacultyResult
from .prompts import PromptCollection, PromptMetadata, PromptTemplate, PromptVariable
from .tsaspdma import TSASPDMAInputs

__all__ = [
    "FacultyContext",
    "FacultyResult",
    "FacultyEvaluationSet",
    "ConscienceFailureContext",
    "EnhancedDMAInputs",
    "PromptTemplate",
    "PromptCollection",
    "PromptVariable",
    "PromptMetadata",
    # TSASPDMA
    "TSASPDMAInputs",
    # Compose dump / ablation gate (#973)
    "BlockClass",
    "BlockDisposition",
    "ComposedBlock",
    "ComposeDumpMeta",
    "GateRegime",
]
