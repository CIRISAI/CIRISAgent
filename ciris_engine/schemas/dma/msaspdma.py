"""
Memorize-Specific Action Selection PDMA (MSASPDMA) schemas.

MSASPDMA provides a "second look" after ASPDMA selects a MEMORIZE action,
giving the agent the graph's addressing conventions and the nodes that already
exist before it writes.

It returns the same ActionSelectionDMAResult as ASPDMA, allowing it to:
- Confirm MEMORIZE (with a corrected node id / type / scope / attributes)
- Switch to SPEAK for user clarification
- Switch to PONDER to reconsider

WHY THIS VERB NEEDED ONE (the observed failure)

The user said "Remember this: my favorite color is chartreuse." The agent replied
"Noted: your favorite color is chartreuse", then emitted a MEMORIZE onto a node
with a freshly-minted UUID id and ``type=user``:

    node_id = "c6482c1b-4654-49fe-a97a-e5e037e9d0b5"

Nothing reads that node back. User enrichment queries ``user/{user_id}`` and only
that (``_create_user_memory_query``, context/system_snapshot_helpers.py:1535), so
the fact would have been stored and permanently invisible. The write also carried
``created_at``, a system-managed attribute, so the handler refused it — the agent
PONDERed, retried with another fresh UUID, and looped, burning ~73k tokens on
"remember my favorite color".

Neither mistake is a reasoning failure. ASPDMA picks the verb without the graph
conventions needed to fill its parameters, exactly as it picks TOOL without the
tool's documentation. MSASPDMA supplies them, the way TSASPDMA supplies ToolInfo.

NO HEALING. This is a second opinion, not a correction pass: the evaluator is
given the conventions and the candidate nodes and re-decides. Silently rewriting
a malformed node id would hide a model that does not know the conventions, and
leave it inventing UUIDs everywhere MSASPDMA does not run.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


class CandidateNode(BaseModel):
    """An existing node the agent may write to, drawn from the system snapshot.

    Offered so the agent PICKS a real node instead of inventing an id. The
    snapshot already carries the user and channel profiles for the thought being
    processed, so this costs no extra query.
    """

    node_id: str = Field(..., description="Canonical node id, e.g. 'user/alice'")
    node_type: str = Field(..., description="NodeType value, e.g. 'user'")
    scope: str = Field(..., description="GraphScope value, e.g. 'local'")
    description: str = Field(..., description="What this node represents, in one line")
    existing_attributes: List[str] = Field(
        default_factory=list,
        description="Attribute names already present, so the agent can see what it would overwrite",
    )

    model_config = ConfigDict(extra="forbid", defer_build=True)


class MSASPDMAInputs(BaseModel):
    """Inputs for MSASPDMA evaluation.

    Invoked AFTER ASPDMA selects MEMORIZE. Carries the graph conventions the
    agent needs to address the write correctly.
    """

    # What ASPDMA proposed
    proposed_node_id: str = Field(..., description="Node id ASPDMA chose")
    proposed_node_type: str = Field(..., description="Node type ASPDMA chose")
    proposed_node_scope: str = Field(..., description="Graph scope ASPDMA chose")
    proposed_attributes: Dict[str, str] = Field(
        default_factory=dict, description="Attributes ASPDMA wants to store, stringified"
    )
    aspdma_reasoning: str = Field(..., description="ASPDMA's rationale for memorizing")

    # The conventions — the "documentation" half, mirroring TSASPDMA's ToolInfo
    candidate_nodes: List[CandidateNode] = Field(
        default_factory=list, description="Existing nodes from the system snapshot"
    )
    system_owned_attributes: Dict[str, str] = Field(
        default_factory=dict,
        description="Attribute name -> why the agent may not author it",
    )

    # Original thought context
    original_thought: Any = Field(..., description="The ProcessingQueueItem being processed")
    context: Optional[Any] = Field(None, description="Additional processing context if available")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# NOTE: MSASPDMA OUTPUT is ActionSelectionDMAResult (same as ASPDMA and TSASPDMA).
#
# The thought processor replaces the ASPDMA result with the MSASPDMA result; no
# special handling is needed because the action types are the same. MSASPDMA can:
#   - Confirm MEMORIZE with a corrected node
#   - Switch to SPEAK ("which of your profiles should I attach this to?")
#   - Switch to PONDER (reconsider — maybe this is not a fact worth storing)


__all__ = ["CandidateNode", "MSASPDMAInputs"]
