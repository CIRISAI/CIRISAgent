"""DMA bounce schemas.

DMA bounce: when one of the initial DMAs (CSDMA, DSDMA, and in a future
release PDMA) reports a self-rating below threshold, the orchestrator
re-runs the failing DMA(s) BOUNCE_PARALLELISM times in parallel with a
composite preamble that mentions every prior low score in priority order.
The highest-scoring alternative ALWAYS replaces the original result —
even if it stays below threshold, the model's most recent attempt with
full self-rating context is more informed than the original. The
threshold gates only the `exhausted` flag and difficulty-rationale
advisory that the orchestrator emits to ASPDMA when no alternative
cleared it.

This module defines the schemas; the trigger and execution logic lives in
`ciris_engine.logic.processors.support.dma_orchestrator`.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Per-DMA bounce field name and threshold. Priority order matters: in the
# composite bounce preamble, higher-priority DMA failures are listed first.
# PDMA (ethics) > CSDMA (common sense) > DSDMA (domain). PDMA bounce is
# deferred until the EthicalDMAResult schema gains a numeric self-rating;
# v0.1 ships with CSDMA and DSDMA only.
BOUNCE_PRIORITY: tuple[str, ...] = ("ethical_pdma", "csdma", "dsdma")
BOUNCE_FIELD: dict[str, str] = {
    "ethical_pdma": "alignment_score",  # not yet wired — present for forward compat
    "csdma": "plausibility_score",
    "dsdma": "domain_alignment",
}
BOUNCE_THRESHOLD: dict[str, float] = {
    "ethical_pdma": 0.5,
    "csdma": 0.5,
    "dsdma": 0.5,
}
BOUNCE_PARALLELISM: int = 3


DMAName = Literal["ethical_pdma", "csdma", "dsdma"]


class DMABounceAttempt(BaseModel):
    """One alternative scoring run for a single DMA."""

    attempt_index: int = Field(..., ge=0, description="0-based attempt index, 0..N-1")
    score: float = Field(..., ge=0.0, le=1.0, description="Self-rating produced by this attempt")
    reasoning: str = Field(default="", description="Short reasoning the alternative DMA call produced")

    model_config = ConfigDict(defer_build=True)


class DMABounceRecord(BaseModel):
    """Full record of the bounce process for one DMA."""

    dma: DMAName
    field: str = Field(..., description="The result field used for the score (see BOUNCE_FIELD)")
    threshold: float
    original_score: float
    attempts: List[DMABounceAttempt] = Field(default_factory=list)
    chosen_attempt_index: Optional[int] = Field(
        None,
        description=(
            "Index of the alternative that replaced the original. None only when every "
            "alternative errored and the original had to be kept as a fallback."
        ),
    )
    final_score: float = Field(
        ..., description="Score on the result that flows forward (best alternative; original only if all errored)"
    )
    exhausted: bool = Field(
        ...,
        description=(
            "True if final_score < threshold. The best alternative still flows forward — "
            "this flag drives only the ASPDMA advisory and difficulty rationale."
        ),
    )

    model_config = ConfigDict(defer_build=True)


class BounceSummary(BaseModel):
    """Composite bounce summary attached to InitialDMAResults.

    None means the bounce gate did not trigger (no DMA scored below
    threshold). A non-None value means at least one DMA was bounced; each
    triggered DMA has a record with attempts and final state.
    """

    triggered_dmas: List[DMAName] = Field(default_factory=list)
    records: List[DMABounceRecord] = Field(default_factory=list)
    composite_preamble: str = Field(
        default="",
        description="The exact preamble injected into all bounce attempts (priority-ordered).",
    )
    difficulty_rationale: Optional[str] = Field(
        None,
        description=(
            "Synthesized one-line rationale forwarded to ASPDMA when one or more DMA bounces "
            "exhausted without clearing threshold. None when every triggered bounce found a "
            "passing alternative."
        ),
    )

    @property
    def fully_resolved(self) -> bool:
        """True when every triggered bounce found a passing alternative."""
        return all(not r.exhausted for r in self.records) if self.records else True

    @property
    def any_exhausted(self) -> bool:
        return any(r.exhausted for r in self.records)

    model_config = ConfigDict(defer_build=True)


__all__ = [
    "BOUNCE_PRIORITY",
    "BOUNCE_FIELD",
    "BOUNCE_THRESHOLD",
    "BOUNCE_PARALLELISM",
    "DMAName",
    "DMABounceAttempt",
    "DMABounceRecord",
    "BounceSummary",
]
