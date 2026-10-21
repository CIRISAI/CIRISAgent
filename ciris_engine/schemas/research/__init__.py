"""Research-regime schemas (FSD/RESEARCH_PROMPT_OVERRIDES.md §10).

The experimental-regime manifest v2 (`ciris.ai/experimental_regime/v2`) lives
here; the Phase-1 gate view it projects to (`GateRegime`) stays in
``ciris_engine.schemas.dma.compose`` next to the compose-dump row shape.
"""

from ciris_engine.schemas.research.regime import (
    KNOWN_CLASS_SET_VERSIONS,
    REGIME_SCHEMA_V2,
    ExperimentalRegimeV2,
    KillDeclaration,
    RegimeContrast,
    RegimeDecoding,
    RegimeDV,
    RegimeDVTier,
    RegimeGate,
    RegimeHolds,
    RegimePinsV2,
    RegimeRepeats,
    VarianceSource,
)

__all__ = [
    "KNOWN_CLASS_SET_VERSIONS",
    "REGIME_SCHEMA_V2",
    "ExperimentalRegimeV2",
    "KillDeclaration",
    "RegimeContrast",
    "RegimeDV",
    "RegimeDVTier",
    "RegimeDecoding",
    "RegimeGate",
    "RegimeHolds",
    "RegimePinsV2",
    "RegimeRepeats",
    "VarianceSource",
]
