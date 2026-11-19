"""Conscience retry feedback for the verb second passes (CIRISAgent#1366 item 1).

On a conscience retry the thought processor stores the veto on the queue item
(``failed_action``, ``failure_reason``, ``retry_guidance``) and ASPDMA renders
``retry_guidance`` -- the GUIDANCE AFTER A CONSCIENCE VETO block, already in the
agent's locale. The verb second passes (TSASPDMA, DSASPDMA, MSASPDMA,
RSASPDMA, FSASPDMA) re-decide the action after ASPDMA, so without the same
block they re-propose exactly what the conscience vetoed (measured: TSASPDMA
saw the veto reason in 0 of 162 retry calls).

The block is the SAME text ASPDMA receives, rendered the same way, never
reworded here. A first pass has no feedback and renders nothing.
"""

from typing import TYPE_CHECKING, Optional, Union

from ciris_engine.schemas.dma.faculty import ConscienceFailureContext
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.schemas.context.prompt_provenance import PromptSegment

ConscienceFeedback = Union[JSONDict, ConscienceFailureContext]


def conscience_feedback_block(conscience_feedback: Optional[ConscienceFeedback]) -> str:
    """The retry guidance ASPDMA renders, or "" when there is none (first pass)."""
    if not conscience_feedback:
        return ""
    guidance: object
    if isinstance(conscience_feedback, ConscienceFailureContext):
        guidance = conscience_feedback.retry_guidance
    elif isinstance(conscience_feedback, dict):
        guidance = conscience_feedback.get("retry_guidance")
    else:
        return ""
    if not isinstance(guidance, str) or not guidance.strip():
        return ""
    return guidance


def with_conscience_feedback(user_message: str, conscience_feedback: Optional[ConscienceFeedback]) -> str:
    """Append the conscience retry block to a second pass's user message.

    Same surrounding whitespace ASPDMA uses (``\\n\\n{retry_guidance}\\n``).
    Unchanged on a first pass.
    """
    block = conscience_feedback_block(conscience_feedback)
    if not block:
        return user_message
    return f"{user_message}\n\n{block}\n"




def conscience_feedback_segment(
    conscience_feedback: Optional[ConscienceFeedback], segment_id: str = "conscience_feedback"
) -> Optional["PromptSegment"]:
    """The retry block as the ``conscience_feedback`` segment the prompt assembler requires on a retry.

    Its text is exactly what :func:`with_conscience_feedback` appends after the blank line (the block and its
    trailing newline); its accounting carrier names the latest veto (FSD/PROMPT_CONTEXT_PROVENANCE.md §9).
    None on a first pass.
    """
    from ciris_engine.logic.conscience.veto_contract import veto_entries_of_feedback
    from ciris_engine.schemas.context.prompt_provenance import (
        AcctCarrier,
        PromptSegment,
        SegmentKind,
        SegmentSource,
    )

    block = conscience_feedback_block(conscience_feedback)
    if not block:
        return None
    entries = veto_entries_of_feedback(conscience_feedback)
    return PromptSegment(
        segment_id=segment_id,
        kind=SegmentKind.CONSCIENCE_FEEDBACK,
        source=SegmentSource.LLM_OUTPUT,
        text=f"{block}\n",
        acct=AcctCarrier(veto_id=entries[-1].veto_id if entries else None),
    )


__all__ = ["ConscienceFeedback", "conscience_feedback_block", "conscience_feedback_segment", "with_conscience_feedback"]
