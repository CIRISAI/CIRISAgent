"""
Conscience Check Context Schema.

Provides typed context for conscience check operations, replacing Dict[str, Any].
"""

from typing import Any, Optional

from ciris_engine.schemas.runtime.models import VerifiedSender, WAAuthorization
from pydantic import BaseModel, ConfigDict, Field


class ConscienceCheckContext(BaseModel):
    """Context for conscience check operations.

    This schema replaces Dict[str, Any] context parameters in conscience checks,
    providing type safety while maintaining flexibility for additional context data.
    """

    # Core context - thought being evaluated
    thought: Any = Field(..., description="Thought being evaluated (Thought object)")

    # Optional context fields
    task: Optional[Any] = Field(None, description="Associated task if available (Task object)")
    round_number: Optional[int] = Field(None, description="Current processing round number")
    system_snapshot: Optional[Any] = Field(None, description="System state snapshot (SystemSnapshot object)")

    # Upstream DMA outputs that every conscience should be able to read when
    # forming its judgment. These are populated from the DMA chain BEFORE
    # conscience execution — they are inputs to the conscience layer, not
    # outputs of it.
    #
    # idma_result gives the conscience the fragility / source-diversity /
    # k_eff picture IDMA built for this thought (phase, collapse_margin,
    # correlation_risk, etc.). A conscience can cross-reference its own
    # judgment against IDMA's epistemic state — e.g. a high-coherence answer
    # on a thought IDMA flagged as fragile (collapse_margin ≤ 0) warrants
    # extra scrutiny even when no single shard would have fired on its own.
    idma_result: Optional[Any] = Field(
        None, description="IDMAResult from the reasoning stack (fragility / k_eff / phase)"
    )

    # The thought's deadline (ciris_engine.logic.config.llm_budget.Deadline,
    # CIRISAgent#1186): set once when the thought starts processing, so each
    # conscience LLM attempt is clamped to what is left of it rather than
    # getting a fresh budget. A runtime clock object, not data: excluded from
    # serialisation. Typed Any because schemas must not import the logic
    # layer; consumers read it through conscience.core.deadline_of(), which
    # accepts only a real Deadline. None -> static per-try x attempts.
    deadline: Optional[Any] = Field(
        None, exclude=True, description="Thought Deadline (llm_budget.Deadline) the conscience stage spends from"
    )

    # The verified Wise Authority approval the thought's task carries, if any
    # (WiseAuthorityService.resolve_deferral). A conscience judging an approved
    # change has to know the review already happened (formatters/wa_approval.py).
    wa_authorization: Optional[WAAuthorization] = Field(
        None, description="Verified WA approval carried by the thought's task"
    )

    # The agent's identity (IdentityData or its dict form), read from the same
    # system snapshot the DMAs read, approved amendments included. Every
    # conscience renders it with the DMAs' one identity block
    # (formatters.identity.format_core_identity_block), so a conscience judges
    # the agent as it is now, not as it was before an approved amendment.
    agent_identity: Optional[Any] = Field(None, description="Agent identity from the system snapshot")

    # Set by the SYSTEM when it re-reviews an evidence objection (#1366 item 9):
    # trusted governance exists that the objecting conscience was not shown, so
    # it is attached (the verified WA governance block) and that conscience
    # judges once more. Never set from drafter or message text.
    attached_evidence: bool = Field(
        False, description="The verified WA governance block is attached for an evidence re-review"
    )

    # The verified sender of the message the thought answers (#1366 item 5):
    # the thought's own sender when it took up a coalesced message, else the
    # task creator's. Consciences render it apart from the self-chosen display
    # name; the input-ablated pair get id and role only, and only when an
    # ID-scoped trusted rule is in force (formal/h3ere_ctxflow/context_policy.yaml).
    verified_sender: Optional[VerifiedSender] = Field(
        None, description="Verified sender of the message being answered (never the display name as identity)"
    )

    # Additional context can be added via extra fields
    model_config = ConfigDict(
        extra="allow",  # Allow additional context fields
        arbitrary_types_allowed=True,  # Allow runtime objects
    )


__all__ = ["ConscienceCheckContext"]
