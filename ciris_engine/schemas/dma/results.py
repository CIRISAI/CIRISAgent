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

    # === TOOL parameters - ONLY the name! TSASPDMA handles actual parameters ===
    tool_name: Optional[str] = Field(
        None, description="Tool name to invoke (for TOOL action). TSASPDMA will determine parameters."
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

    model_config = ConfigDict(extra="forbid")


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
    return TaskCompleteParams(
        channel_id=channel_id, completion_reason=llm_result.completion_reason or "Task completed"
    )


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
    """Create the appropriate params object based on action type."""
    if action == HandlerActionType.SPEAK:
        return SpeakParams(channel_id=channel_id, content=llm_result.speak_content or "")
    if action == HandlerActionType.PONDER:
        return PonderParams(channel_id=channel_id, questions=llm_result.ponder_questions or ["What should I consider?"])
    if action == HandlerActionType.REJECT:
        return RejectParams(
            channel_id=channel_id,
            reason=llm_result.reject_reason or "Request rejected",
            create_filter=llm_result.reject_create_filter,
        )
    if action == HandlerActionType.DEFER:
        return DeferParams(
            channel_id=channel_id,
            reason=llm_result.defer_reason or "Deferring for later",
            defer_until=llm_result.defer_until,
        )
    if action == HandlerActionType.TOOL:
        return ToolParams(channel_id=channel_id, name=llm_result.tool_name or "unknown_tool", parameters={})
    if action == HandlerActionType.OBSERVE:
        return ObserveParams(channel_id=channel_id, active=llm_result.observe_active)
    if action == HandlerActionType.MEMORIZE:
        return _create_memorize_params(llm_result, channel_id)
    if action == HandlerActionType.RECALL:
        return _create_recall_params(llm_result, channel_id)
    if action == HandlerActionType.FORGET:
        return _create_forget_params(llm_result, channel_id)
    if action == HandlerActionType.TASK_COMPLETE:
        return _create_task_complete_params(llm_result, channel_id)
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
