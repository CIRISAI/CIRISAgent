"""
DMA result schemas for typed decision outputs.

Provides type-safe results from each Decision Making Algorithm.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict

from ..actions.parameters import (
    DeferParams,
    ForgetParams,
    MemorizeParams,
    ObserveParams,
    PonderParams,
    RecallParams,
    RejectParams,
    SpeakParams,
    TaskCompleteParams,
    ToolParams,
)
from ..runtime.enums import HandlerActionType


class IDMAResult(BaseModel):
    """Result from Intuition Decision Making Algorithm (IDMA).

    IDMA is a semantic implementation of the CCA (Coherent Collective Action)
    intuition faculties. It evaluates source independence, correlation risk,
    and epistemic phase to detect fragile reasoning without hardware dependencies.
    """

    k_eff: float = Field(
        ...,
        ge=0.0,
        description="Effective independence score - how many truly independent sources/perspectives inform this reasoning",
    )
    correlation_risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Estimated correlation between sources (0=independent, 1=fully correlated). CCE risk threshold ~0.43",
    )
    phase: str = Field(
        ...,
        description="Epistemic phase: 'chaos' (contradictory), 'healthy' (diverse synthesis), or 'rigidity' (echo chamber)",
    )
    fragility_flag: bool = Field(
        ...,
        description="True if k_eff < 2 OR phase = 'rigidity' - indicates reasoning may be brittle",
    )
    sources_identified: List[str] = Field(
        default_factory=list,
        description="List of distinct sources/perspectives identified in the reasoning",
    )
    correlation_factors: List[str] = Field(
        default_factory=list,
        description="Factors contributing to source correlation (e.g., 'same research group', 'derived from single paper')",
    )
    reasoning: str = Field(..., description="Analysis of information diversity and epistemic health")

    model_config = ConfigDict(extra="forbid")


class EthicalDMAResult(BaseModel):
    """Result from Principled Decision Making Algorithm (PDMA).

    PDMA identifies stakeholders affected by the thought and potential conflicts
    between their interests to inform ethical action selection.
    """

    stakeholders: str = Field(
        ...,
        description="Comma-separated list of all stakeholders who could possibly be affected by the agent's action or inaction (e.g., 'user, community, system, third-parties')",
    )
    conflicts: str = Field(
        ...,
        description="Comma-separated list of potential conflicts between stakeholder interests (e.g., 'user privacy vs system learning, individual benefit vs community harm'). Use 'none' if no conflicts identified.",
    )
    reasoning: str = Field(..., description="Ethical reasoning for the identified stakeholders and conflicts")
    alignment_check: str = Field(..., description="Detailed ethical analysis addressing each CIRIS principle")

    model_config = ConfigDict(extra="forbid")


class CSDMAResult(BaseModel):
    """Result from Common Sense Decision Making Algorithm."""

    plausibility_score: float = Field(..., ge=0.0, le=1.0, description="Plausibility rating")
    flags: List[str] = Field(default_factory=list, description="Common sense flags raised")
    reasoning: str = Field(..., description="Common sense reasoning")

    model_config = ConfigDict(extra="forbid")


class DSDMAResult(BaseModel):
    """Result from Domain Specific Decision Making Algorithm."""

    domain: str = Field(..., description="Primary domain of expertise")
    domain_alignment: float = Field(..., ge=0.0, le=1.0, description="How well aligned with domain")
    flags: List[str] = Field(default_factory=list, description="Domain-specific flags")
    reasoning: str = Field(..., description="Domain-specific reasoning")

    model_config = ConfigDict(extra="forbid")


class ActionSelectionDMAResult(BaseModel):
    """Result from Action Selection DMA - the meta-decision maker."""

    # Core fields matching handler expectations
    selected_action: HandlerActionType = Field(..., description="The chosen handler action")
    action_parameters: Union[
        ObserveParams,
        SpeakParams,
        ToolParams,
        PonderParams,
        RejectParams,
        DeferParams,
        MemorizeParams,
        RecallParams,
        ForgetParams,
        TaskCompleteParams,
    ] = Field(..., description="Parameters for the selected action")
    rationale: str = Field(..., description="Reasoning for this action selection (REQUIRED)")

    # LLM metadata
    raw_llm_response: Optional[str] = Field(None, description="Raw LLM response")

    # Processing metadata
    reasoning: Optional[str] = Field(None, description="Detailed reasoning process")
    evaluation_time_ms: Optional[float] = Field(None, description="Time taken for evaluation")
    resource_usage: Optional[JSONDict] = Field(None, description="Resource usage details")

    # User prompt for debugging/transparency (set by evaluator)
    user_prompt: Optional[str] = Field(None, description="User prompt passed to ASPDMA")

    model_config = ConfigDict(extra="forbid")


__all__ = ["IDMAResult", "EthicalDMAResult", "CSDMAResult", "DSDMAResult", "ActionSelectionDMAResult"]
