"""Conscience retry feedback for the verb second passes (CIRISAgent#1366 item 1).

On a conscience retry the thought processor stores the veto on the queue item
(``failed_action``, ``failure_reason``, ``retry_guidance``) and ASPDMA renders
``retry_guidance`` -- the CONSCIENCE OVERRIDE GUIDANCE block, already in the
agent's locale. The verb second passes (TSASPDMA, DSASPDMA, MSASPDMA,
RSASPDMA, FSASPDMA) re-decide the action after ASPDMA, so without the same
block they re-propose exactly what the conscience vetoed (measured: TSASPDMA
saw the veto reason in 0 of 162 retry calls).

The block is the SAME text ASPDMA receives, rendered the same way, never
reworded here. A first pass has no feedback and renders nothing.
"""

from typing import Optional, Union

from ciris_engine.schemas.dma.faculty import ConscienceFailureContext
from ciris_engine.schemas.types import JSONDict

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


__all__ = ["ConscienceFeedback", "conscience_feedback_block", "with_conscience_feedback"]
