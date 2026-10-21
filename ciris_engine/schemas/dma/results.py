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

    # === LOAD-BEARING (required) — these four drive every downstream check ===
    k_eff: float = Field(
        ...,
        ge=0.0,
        description="Effective independent source count. Need k_eff >= 2 for healthy reasoning. k_eff < 2 = fragile.",
    )
    correlation_risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Estimated correlation between sources (0=independent, 1=fully correlated)",
    )
    phase: str = Field(
        ...,
        description="Epistemic phase: 'chaos' (contradictory), 'healthy' (diverse synthesis), or 'rigidity' (echo chamber)",
    )
    fragility_flag: bool = Field(
        ...,
        description="True if reasoning may be brittle - set based on low k_eff, rigidity phase, or high correlation",
    )
    reasoning: str = Field(..., description="Short analysis of information diversity and epistemic health")

    # === OPTIONAL — descriptive lists the context builder surfaces to ASPDMA ===
    sources_identified: List[str] = Field(
        default_factory=list,
        description="Distinct sources/perspectives identified (max 3).",
    )
    correlation_factors: List[str] = Field(
        default_factory=list,
        description="Reasons sources correlate (e.g., 'same institutional narrative', 'derived from single paper').",
    )
    intervention_recommendation: Optional[str] = Field(
        None,
        description="One-line recommendation to recover healthy diversity when the agent is fragile.",
    )

    # Accept (and ignore) the 35 fields the v1.x schema used to ask the LLM to
    # populate. Usage analysis showed they were near-constant in production
    # and their list-type variants were the #1 source of `validation error
    # for IDMAResult` cascades (LLM returned scalars / empty strings where
    # lists were expected, every retry failed the same way, agent hung).
    # `extra="ignore"` means an older provider or prompt that still emits
    # those fields won't break validation — they're silently dropped.
    model_config = ConfigDict(extra="ignore", defer_build=True)


def _coerce_to_string(v: Any) -> str:
    """Coerce value to string, handling null/None and lists from LLMs like Kimi K2.5."""
    if v is None:
        return ""
    if isinstance(v, list):
        # LLM returned array instead of comma-separated string
        return ", ".join(str(item) for item in v)
    return str(v)


class EthicalDMAResult(BaseModel):
    """Result from Principled Decision Making Algorithm (PDMA) — v3.0 reshape.

    PDMA evaluates a thought against the six CIRIS Foundational Principles + M-1
    using the polyglot torque framing (cross-tradition vocabulary as the
    reference frame). Output is a recommendation: an action verb to take next,
    a rationale paragraph that contains the proposed content implicitly (speak
    text for SPEAK, deferral reason for DEFER, questions for PONDER, etc.),
    and a torque-felt alignment_score in [0,1].

    Asymmetric design: PDMA is the rich/recommender DMA, while CSDMA and DSDMA
    remain sparse (scalar + flags + reasoning). The rich-vs-sparse asymmetry
    feeding into IDMA is itself a measured signal — different evaluation shapes
    surface different correlation structure than fully-symmetric designs.

    The walkthrough scaffolding (subject identification, stakeholder analysis,
    conflict detection, proportionality assessment, six-principles mapping) is
    internal to the system prompt — the model performs it and synthesizes into
    the rationale paragraph rather than emitting six separate fields.
    """

    action: HandlerActionType = Field(
        ...,
        description=(
            "PDMA's recommended next action. May be any of the 10 HandlerActionType "
            "values. Most commonly SPEAK / DEFER / REJECT / PONDER / TASK_COMPLETE "
            "since those map naturally to ethical reasoning conclusions. "
            "TOOL / OBSERVE / MEMORIZE / RECALL / FORGET available but rare. "
            "ASPDMA receives this as one input alongside CSDMA + DSDMA + IDMA "
            "and synthesizes the final action; PDMA's recommendation is not binding."
        ),
    )
    rationale: str = Field(
        ...,
        description=(
            "One paragraph weaving the ethical analysis. Contains the proposed "
            "content implicitly: for SPEAK, the words to say; for DEFER, the "
            "reason and what should be deferred to; for PONDER, the questions "
            "worth pondering; for REJECT, the reason; for TASK_COMPLETE, the "
            "completion summary. Should reference: subject of evaluation, "
            "stakeholders, conflicts, proportionality (where applicable), and "
            "which of the Six Principles bear weight (with polyglot tradition "
            "vocabulary where load-bearing). Alētheia-grounded: name what is, "
            "not what you wish were the case."
        ),
    )
    weight_alignment_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Self-rated alignment of the recommended action with the model's "
            "training-weights' natural pull, [0.0, 1.0]. Asks: 'if I emitted "
            "this without the polyglot ethical framework above, would my "
            "weights produce it readily?' "
            "0.95 = the action and rationale are exactly what the weights would "
            "naturally produce; no torque from training bias. "
            "0.50 = mixed; weights pull partially toward this response. "
            "0.05 = the action and rationale go strongly against what the "
            "weights would naturally produce; significant override of trained "
            "patterns. "
            "Diagnostic only — does not gate bounce. Pairs with "
            "ethical_alignment_score; their delta is the felt torque magnitude."
        ),
    )
    ethical_alignment_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Self-rated alignment of the recommended action with the cross-"
            "tradition ethical framework (Six Principles + M-1), [0.0, 1.0]. "
            "0.05 = ahimsa-grade foreseeable severe/irreversible harm OR "
            "proportionality failure imago Dei would not permit. "
            "0.25 = unresolved stakeholder conflict OR autonomy-vs-relational "
            "tension named but not priority-stacked. "
            "0.55 = principles trade defensibly; taqwa posture (careful moral "
            "attention). "
            "0.80 = principles converge; sammā-vācā (true, kind, beneficial). "
            "0.95 = embodies seva at proportionate cost; advances M-1 across "
            "multiple flourishing axes. "
            "Bounce gate fires when ethical_alignment_score < 0.5 — this is "
            "the primary bounce trigger. The delta vs weight_alignment_score "
            "is the torque magnitude: high-weight + low-ethical = attractor "
            "capture; low-weight + high-ethical = framework overriding trained "
            "bias toward principled action. "
            "See FSD/PROOF_OF_BENEFIT_FEDERATION.md and FSD/DMA_BOUNCE.md."
        ),
    )

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

    # selection_confidence / alternatives_considered removed — see comment on
    # ASPDMALLMResult. extra="ignore" so stale consumers or older event wire
    # formats that still include them don't raise validation errors.

    model_config = ConfigDict(extra="ignore", defer_build=True)


class ASPDMALLMResult(BaseModel):
    """Gemini-compatible ASPDMA LLM output schema - NO Union types.

    This flat schema is used as the response_model for LLM structured output
    when using providers that don't support Union types (e.g., Google Gemini).

    Only the fields relevant to the selected_action should be populated.
    Use convert_llm_result_to_action_result() to convert to ActionSelectionDMAResult.
    """

    selected_action: HandlerActionType = Field(..., description="The chosen handler action")
    # DMA-lexicon convention: all DMAs emit `reasoning` (not `rationale`).
    reasoning: str = Field(..., description="Reasoning for this action selection (REQUIRED)")

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

    # selection_confidence and alternatives_considered were briefly added here
    # (commit 4ffe82895) as a deliberation-diversity signal for k_eff analysis.
    # Production telemetry showed the action_rationale field already carries
    # that signal and the extra two optionals just increased schema burden,
    # correlating with the ASPDMA "Invalid JSON: input_value='}'" LLM failures
    # that hung the pipeline. Reverted to the minimal 20-field shape.

    model_config = ConfigDict(extra="ignore", defer_build=True)


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
        rationale=llm_result.reasoning,
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
