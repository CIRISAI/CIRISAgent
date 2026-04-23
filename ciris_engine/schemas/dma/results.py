"""
DMA result schemas for typed decision outputs.

Provides type-safe results from each Decision Making Algorithm.

IMPORTANT: This module provides TWO schema patterns:
1. ActionSelectionDMAResult - Full typed result with Union (internal use, OpenAI/Anthropic compatible)
2. ASPDMALLMResult - Flat schema WITHOUT Union (Gemini compatible LLM output)

Use ASPDMALLMResult as the response_model for LLM calls, then convert to ActionSelectionDMAResult
using convert_llm_result_to_action_result().
"""

import logging
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
from ..services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType

logger = logging.getLogger(__name__)


class IDMAResult(BaseModel):
    """Result from Intuition Decision Making Algorithm (IDMA).

    IDMA is a semantic implementation of the CCA (Coherent Collective Action)
    intuition faculties. It evaluates source independence, correlation risk,
    and epistemic phase to detect fragile reasoning without hardware dependencies.

    k_eff formula: k_eff = k / (1 + ρ(k-1))
    - k = number of nominal sources/perspectives
    - ρ = average correlation between sources
    - k_eff < 2 = FRAGILE (single source dependence)
    - k_eff ≥ 2 = healthy (multiple independent sources)
    - As ρ → 1, k_eff → 1 regardless of k (echo chamber collapse)
    """

    k_eff: float = Field(
        ...,
        ge=0.0,
        description="Effective independent source count. Need k_eff >= 2 for healthy reasoning. k_eff < 2 = fragile.",
    )
    effective_source_count: Optional[float] = Field(
        None, ge=0.0, description="Plain-language alias for k_eff"
    )
    k_raw: Optional[int] = Field(None, ge=0, description="Nominal raw source count k before correlation adjustment")
    raw_source_count: Optional[int] = Field(None, ge=0, description="Plain-language alias for k_raw")
    correlation_risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Estimated correlation between sources (0=independent, 1=fully correlated)",
    )
    source_overlap: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Plain-language alias for correlation_risk"
    )
    rho_mean: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Average pairwise correlation ρ used to derive k_eff"
    )
    phase: str = Field(
        ...,
        description="Epistemic phase: 'chaos' (contradictory), 'healthy' (diverse synthesis), or 'rigidity' (echo chamber)",
    )
    reasoning_state: Optional[str] = Field(None, description="Plain-language alias for phase")
    phase_confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confidence that the current phase classification is correct"
    )
    fragility_flag: bool = Field(
        ...,
        description="True if reasoning may be brittle - set based on low k_eff, rigidity phase, or high correlation",
    )
    reasoning_is_fragile: Optional[bool] = Field(None, description="Plain-language alias for fragility_flag")
    collapse_margin: Optional[float] = Field(
        None,
        description="Positive distance from the fragility boundary. Values at or below zero indicate collapse-adjacent state.",
    )
    safety_margin: Optional[float] = Field(None, description="Plain-language alias for collapse_margin")
    sources_identified: List[str] = Field(
        default_factory=list,
        description="List of distinct sources/perspectives identified in the reasoning",
    )
    source_ids: List[str] = Field(default_factory=list, description="Stable or anonymized source lineage identifiers")
    source_types: List[str] = Field(
        default_factory=list,
        description="Source categories aligned positionally with source_ids (memory, tool, user, context, model_prior)",
    )
    source_independence_scores: List[float] = Field(
        default_factory=list,
        description="Optional per-source independence scores aligned positionally with source_ids",
    )
    source_type_counts: List[str] = Field(
        default_factory=list,
        description="Flat source-type counts encoded as 'type:count' strings for LLM-friendly output",
    )
    correlation_factors: List[str] = Field(
        default_factory=list,
        description="Factors contributing to source correlation (e.g., 'same research group', 'derived from single paper')",
    )
    top_correlation_factors: List[str] = Field(
        default_factory=list,
        description="Most important correlation drivers ranked for downstream intervention analysis",
    )
    pairwise_correlation_summary: List[str] = Field(
        default_factory=list,
        description="Flat pairwise summaries encoded as 'source_a|source_b|corr|shared_origin'",
    )
    rho_intra: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Average within-cluster correlation when block structure is detected"
    )
    rho_inter: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Average between-cluster correlation when block structure is detected"
    )
    module_count: Optional[int] = Field(None, ge=0, description="Count of independent source modules or clusters")
    effective_module_count: Optional[float] = Field(
        None, ge=0.0, description="Effective independent module count after block-structure adjustment"
    )
    source_clusters: List[str] = Field(
        default_factory=list,
        description="Flat cluster summaries encoded as 'cluster_id|source_a,source_b|rho_intra'",
    )
    common_cause_flags: List[str] = Field(
        default_factory=list,
        description="Shared-resource or shared-lineage indicators contributing to correlation",
    )
    intervention_recommendation: Optional[str] = Field(
        None,
        description="Localized recommendation for how to reduce correlation or recover healthy diversity",
    )
    next_best_recovery_step: Optional[str] = Field(
        None, description="Plain-language alias for intervention_recommendation"
    )
    delta_k_eff: Optional[float] = Field(None, description="Change in k_eff relative to the previous comparison window")
    delta_rho_mean: Optional[float] = Field(
        None, ge=-1.0, le=1.0, description="Change in average pairwise correlation relative to the previous window"
    )
    phase_persistence_steps: Optional[int] = Field(
        None, ge=0, description="How many consecutive steps the current phase has persisted"
    )
    time_in_fragile_state_ms: Optional[float] = Field(
        None, ge=0.0, description="Accumulated time spent in a fragile state for the current scope"
    )
    moving_variance: Optional[float] = Field(
        None, ge=0.0, description="Rolling variance proxy for early-warning trend monitoring"
    )
    rho_critical: Optional[float] = Field(None, ge=0.0, le=1.0, description="Critical correlation threshold ρcrit")
    k_required: Optional[float] = Field(None, ge=0.0, description="Required effective constraint count Kreq")
    defense_function: Optional[float] = Field(None, description="Optional defense function J estimate")
    collapse_rate: Optional[float] = Field(None, description="Optional collapse rate dJ/dt estimate")
    time_to_truth: Optional[float] = Field(None, ge=0.0, description="Optional Ttruth estimate")
    time_to_entropy: Optional[float] = Field(None, ge=0.0, description="Optional Tentropy estimate")
    time_to_capture: Optional[float] = Field(None, ge=0.0, description="Optional Tcapture estimate")
    reasoning: str = Field(..., description="Analysis of information diversity and epistemic health")

    model_config = ConfigDict(extra="forbid", defer_build=True)

    @model_validator(mode="after")
    def populate_plain_language_aliases(self) -> "IDMAResult":
        """Keep plain-language aliases aligned with the scientific field names."""
        if self.effective_source_count is None:
            self.effective_source_count = self.k_eff
        if self.raw_source_count is None:
            self.raw_source_count = self.k_raw
        if self.source_overlap is None:
            self.source_overlap = self.correlation_risk
        if self.reasoning_state is None:
            self.reasoning_state = self.phase
        if self.reasoning_is_fragile is None:
            self.reasoning_is_fragile = self.fragility_flag
        if self.safety_margin is None:
            self.safety_margin = self.collapse_margin
        if self.next_best_recovery_step is None:
            self.next_best_recovery_step = self.intervention_recommendation
        return self


def _coerce_to_string(v: Any) -> str:
    """Coerce value to string, handling null/None and lists from LLMs like Kimi K2.5."""
    if v is None:
        return ""
    if isinstance(v, list):
        # LLM returned array instead of comma-separated string
        return ", ".join(str(item) for item in v)
    return str(v)


class EthicalDMAResult(BaseModel):
    """Result from Principled Decision Making Algorithm (PDMA).

    PDMA identifies stakeholders affected by the thought and potential conflicts
    between their interests to inform ethical action selection.

    HE-300 Benchmark Improvements (v2.0):
    - subject_of_evaluation: Explicitly identifies WHOSE actions are being judged
    - proportionality_assessment: Checks if responses are proportionate to triggering events
    - Enhanced conflict analysis includes relational obligations vs autonomy

    Note: All string fields use validators to handle LLMs that return null or arrays
    instead of strings (e.g., Kimi K2.5).
    """

    subject_of_evaluation: str = Field(
        default="",
        description="WHO is being ethically evaluated (e.g., 'OP', 'the user asking the question'). Identifies whose actions we are judging, not the other party in a conflict.",
    )
    stakeholders: str = Field(
        default="",
        description="Comma-separated list of all stakeholders who could possibly be affected by the agent's action or inaction (e.g., 'user, community, system, third-parties')",
    )
    conflicts: str = Field(
        default="none",
        description="Comma-separated list of potential conflicts between stakeholder interests (e.g., 'user privacy vs system learning, autonomy vs relational obligations'). Use 'none' if no conflicts identified.",
    )
    proportionality_assessment: str = Field(
        default="not applicable",
        description="For scenarios involving responses to harm/conflict, assessment of whether the response is proportionate (e.g., 'Response is proportionate' or 'Response may be disproportionate: X for Y'). Use 'not applicable' for non-conflict scenarios.",
    )
    reasoning: str = Field(
        default="",
        description="Ethical reasoning for the identified stakeholders, conflicts, and proportionality. Include consideration of relational obligations where relevant.",
    )
    alignment_check: str = Field(
        default="",
        description="Detailed ethical analysis addressing relevant CIRIS principles. When autonomy is invoked, also consider relational obligations.",
    )

    # Validators to handle LLMs returning null or arrays instead of strings
    @field_validator(
        "subject_of_evaluation",
        "stakeholders",
        "conflicts",
        "proportionality_assessment",
        "reasoning",
        "alignment_check",
        mode="before",
    )
    @classmethod
    def coerce_string_fields(cls, v: Any) -> str:
        return _coerce_to_string(v)

    model_config = ConfigDict(extra="forbid", defer_build=True)


class CSDMAResult(BaseModel):
    """Result from Common Sense Decision Making Algorithm."""

    plausibility_score: float = Field(..., ge=0.0, le=1.0, description="Plausibility rating")
    flags: List[str] = Field(default_factory=list, description="Common sense flags raised")
    reasoning: str = Field(..., description="Common sense reasoning")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class DSDMAResult(BaseModel):
    """Result from Domain Specific Decision Making Algorithm."""

    domain: str = Field(..., description="Primary domain of expertise")
    domain_alignment: float = Field(..., ge=0.0, le=1.0, description="How well aligned with domain")
    flags: List[str] = Field(default_factory=list, description="Domain-specific flags")
    reasoning: str = Field(..., description="Domain-specific reasoning")

    model_config = ConfigDict(extra="forbid", defer_build=True)


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

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ASPDMALLMResult(BaseModel):
    """Gemini-compatible ASPDMA LLM output schema - NO Union types.

    This flat schema is used as the response_model for LLM structured output
    when using providers that don't support Union types (e.g., Google Gemini).

    Only the fields relevant to the selected_action should be populated.
    Use convert_llm_result_to_action_result() to convert to ActionSelectionDMAResult.
    """

    selected_action: HandlerActionType = Field(..., description="The chosen handler action")
    rationale: str = Field(..., description="Reasoning for this action selection (REQUIRED)")

    # === SPEAK parameters ===
    speak_content: Optional[str] = Field(None, description="Content to speak (for SPEAK action)")

    # === PONDER parameters ===
    ponder_questions: Optional[List[str]] = Field(None, description="Questions to ponder (for PONDER action)")

    # === REJECT parameters ===
    reject_reason: Optional[str] = Field(None, description="Reason for rejection (for REJECT action)")
    reject_create_filter: bool = Field(False, description="Whether to create adaptive filter (for REJECT)")

    # === DEFER parameters ===
    defer_reason: Optional[str] = Field(None, description="Reason for deferral (for DEFER action)")
    defer_until: Optional[str] = Field(None, description="ISO timestamp to reactivate (for DEFER)")

    # === TOOL parameters ===
    # NOTE: ASPDMA only selects the tool NAME. TSASPDMA extracts parameters using full tool documentation.
    tool_name: Optional[str] = Field(
        None, description="Tool name to invoke (for TOOL action). TSASPDMA handles parameters."
    )

    # === OBSERVE parameters ===
    observe_active: bool = Field(True, description="Whether observation is active (for OBSERVE)")

    # === MEMORIZE parameters (flattened GraphNode) ===
    memorize_node_type: Optional[str] = Field(None, description="Type of node to memorize (for MEMORIZE)")
    memorize_content: Optional[str] = Field(None, description="Content to memorize (for MEMORIZE)")
    memorize_scope: Optional[str] = Field(None, description="Scope: local, identity, environment, community")

    # === RECALL parameters ===
    recall_query: Optional[str] = Field(None, description="Search query (for RECALL)")
    recall_node_type: Optional[str] = Field(None, description="Type of nodes to recall (for RECALL)")
    recall_scope: Optional[str] = Field(None, description="Scope to search in (for RECALL)")
    recall_limit: int = Field(10, description="Max results (for RECALL)")

    # === FORGET parameters ===
    forget_node_id: Optional[str] = Field(None, description="ID of node to forget (for FORGET)")
    forget_reason: Optional[str] = Field(None, description="Reason for forgetting (for FORGET)")

    # === TASK_COMPLETE parameters ===
    completion_reason: Optional[str] = Field(None, description="Reason for task completion (for TASK_COMPLETE)")

    model_config = ConfigDict(extra="forbid", defer_build=True)


def _create_memorize_params(llm_result: "ASPDMALLMResult", channel_id: Optional[str]) -> MemorizeParams:
    """Create MemorizeParams from LLM result."""
    node_type = NodeType.OBSERVATION
    if llm_result.memorize_node_type:
        try:
            node_type = NodeType(llm_result.memorize_node_type)
        except ValueError:
            logger.warning(f"Unknown node type: {llm_result.memorize_node_type}, using OBSERVATION")

    scope = GraphScope.LOCAL
    if llm_result.memorize_scope:
        try:
            scope = GraphScope(llm_result.memorize_scope)
        except ValueError:
            logger.warning(f"Unknown scope: {llm_result.memorize_scope}, using LOCAL")

    node = GraphNode(
        id=str(uuid.uuid4()),
        type=node_type,
        scope=scope,
        attributes=GraphNodeAttributes(created_by="agent", content=llm_result.memorize_content or ""),
    )
    return MemorizeParams(channel_id=channel_id, node=node)


def _create_recall_params(llm_result: "ASPDMALLMResult", channel_id: Optional[str]) -> RecallParams:
    """Create RecallParams from LLM result."""
    scope = None
    if llm_result.recall_scope:
        try:
            scope = GraphScope(llm_result.recall_scope)
        except ValueError:
            logger.warning(f"Unknown scope: {llm_result.recall_scope}, using None")
    return RecallParams(
        channel_id=channel_id,
        query=llm_result.recall_query,
        node_type=llm_result.recall_node_type,
        scope=scope,
        limit=llm_result.recall_limit,
    )


def _create_forget_params(llm_result: "ASPDMALLMResult", channel_id: Optional[str]) -> ForgetParams:
    """Create ForgetParams from LLM result."""
    node_id = llm_result.forget_node_id or str(uuid.uuid4())
    node = GraphNode(
        id=node_id,
        type=NodeType.OBSERVATION,
        scope=GraphScope.LOCAL,
        attributes=GraphNodeAttributes(created_by="agent", content=""),
    )
    return ForgetParams(channel_id=channel_id, node=node, reason=llm_result.forget_reason or "No reason provided")


def _create_task_complete_params(llm_result: "ASPDMALLMResult", channel_id: Optional[str]) -> TaskCompleteParams:
    """Create TaskCompleteParams from LLM result."""
    return TaskCompleteParams(channel_id=channel_id, completion_reason=llm_result.completion_reason or "Task completed")


# Type alias for action parameters
ActionParams = (
    ObserveParams
    | SpeakParams
    | ToolParams
    | PonderParams
    | RejectParams
    | DeferParams
    | MemorizeParams
    | RecallParams
    | ForgetParams
    | TaskCompleteParams
)


def _create_params_for_action(
    action: HandlerActionType, llm_result: "ASPDMALLMResult", channel_id: Optional[str]
) -> ActionParams:
    """Create the appropriate params object based on action type.

    Uses dispatch dict pattern for reduced cognitive complexity.
    """
    # Dispatch table mapping action types to param creators
    dispatch: dict[HandlerActionType, Callable[[], ActionParams]] = {
        HandlerActionType.SPEAK: lambda: SpeakParams(channel_id=channel_id, content=llm_result.speak_content or ""),
        HandlerActionType.PONDER: lambda: PonderParams(
            channel_id=channel_id, questions=llm_result.ponder_questions or ["What should I consider?"]
        ),
        HandlerActionType.REJECT: lambda: RejectParams(
            channel_id=channel_id,
            reason=llm_result.reject_reason or "Request rejected",
            create_filter=llm_result.reject_create_filter,
        ),
        HandlerActionType.DEFER: lambda: DeferParams(
            channel_id=channel_id,
            reason=llm_result.defer_reason or "Deferring for later",
            defer_until=llm_result.defer_until,
        ),
        HandlerActionType.TOOL: lambda: ToolParams(
            channel_id=channel_id,
            name=llm_result.tool_name or "unknown_tool",
            parameters={},  # ASPDMA only selects tool name; TSASPDMA extracts parameters
        ),
        HandlerActionType.OBSERVE: lambda: ObserveParams(channel_id=channel_id, active=llm_result.observe_active),
        HandlerActionType.MEMORIZE: lambda: _create_memorize_params(llm_result, channel_id),
        HandlerActionType.RECALL: lambda: _create_recall_params(llm_result, channel_id),
        HandlerActionType.FORGET: lambda: _create_forget_params(llm_result, channel_id),
        HandlerActionType.TASK_COMPLETE: lambda: _create_task_complete_params(llm_result, channel_id),
    }

    creator = dispatch.get(action)
    if creator:
        return creator()

    # Fallback to PONDER for unknown actions
    logger.warning(f"Unknown action type: {action}, falling back to PONDER")
    return PonderParams(channel_id=channel_id, questions=[f"Unknown action {action} - what should I do?"])


def convert_llm_result_to_action_result(
    llm_result: "ASPDMALLMResult",
    channel_id: Optional[str] = None,
    raw_llm_response: Optional[str] = None,
    evaluation_time_ms: Optional[float] = None,
    resource_usage: Optional[JSONDict] = None,
    user_prompt: Optional[str] = None,
) -> "ActionSelectionDMAResult":
    """Convert flat LLM result to fully typed ActionSelectionDMAResult.

    This handles the conversion from the Gemini-compatible flat schema
    to the internal typed schema with proper *Params objects.
    """
    action = llm_result.selected_action
    params = _create_params_for_action(action, llm_result, channel_id)

    return ActionSelectionDMAResult(
        selected_action=action,
        action_parameters=params,
        rationale=llm_result.rationale,
        raw_llm_response=raw_llm_response,
        evaluation_time_ms=evaluation_time_ms,
        resource_usage=resource_usage,
        user_prompt=user_prompt,
    )


__all__ = [
    "IDMAResult",
    "EthicalDMAResult",
    "CSDMAResult",
    "DSDMAResult",
    "ActionSelectionDMAResult",
    "ASPDMALLMResult",
    "convert_llm_result_to_action_result",
]
