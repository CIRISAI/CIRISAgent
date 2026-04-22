"""Typed result models for H3ERE pipeline phases."""

from pydantic import BaseModel, Field

from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import ConscienceApplicationResult


class ActionSelectionPhaseResult(BaseModel):
    """Result of action selection and conscience validation phase.

    Replaces the JSONDict return type from _perform_action_selection_phase.
    """

    action_result: ActionSelectionDMAResult = Field(..., description="The action selected by ASPDMA")
    conscience_result: ConscienceApplicationResult = Field(
        ..., description="Result of conscience checks on the selected action"
    )

    class Config:
        frozen = True  # Immutable result object
