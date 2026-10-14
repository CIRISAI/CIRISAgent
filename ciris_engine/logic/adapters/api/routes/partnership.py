"""
Partnership API - what the PARTNERED consent stream means.

Partnership is a data-management record (CC 4.4.3.4.3 / CC 3.3.1,
CIRISConstitution#168): the user's retention/learning choice, recorded as a
grant half (the user's choice) and an accept half (this agent occurrence's
signature under the owner-binding) sharing one ``bilateral_pair_id``. It is
not a relationship the agent may refuse.

How a PARTNERED choice is applied lives on the consent surface, not here:

- ``POST /v1/consent/grant`` with ``stream=partnered``. A steward's own choice
  applies directly. Any other user's choice is deferred to the steward through
  the Wisdom-Based Deferral path and their current stream is unchanged until
  the steward answers.
- ``GET /v1/consent/partnership/status`` reports ``pending`` / ``partnered`` / ``none``.
- The steward answers through ``POST /v1/wa/deferrals/{deferral_id}/resolve``.

This router keeps only the read-only description of the stream.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ciris_engine.schemas.consent.core import ConsentCategory

from ..auth import get_current_user
from ..models import StandardResponse, TokenData

router = APIRouter(prefix="/partnership", tags=["Partnership"])


@router.get("/options")
async def get_partnership_options(
    req: Request,
    current_user: Annotated[TokenData, Depends(get_current_user)],
) -> StandardResponse:
    """
    What the PARTNERED stream is, and how choosing it is applied.

    Helps a user understand the stream before they choose it.
    """
    options = {
        "required_categories": [
            ConsentCategory.INTERACTION.value,
            ConsentCategory.PREFERENCE.value,
            ConsentCategory.IMPROVEMENT.value,
        ],
        "optional_categories": [
            ConsentCategory.RESEARCH.value,
            ConsentCategory.SHARING.value,
        ],
        "approval_process": (
            "PARTNERED is your data choice: the agent retains and learns from your interactions "
            "instead of forgetting them after 14 days. If you are this agent's steward it applies "
            "immediately. Otherwise, whether this agent retains you under PARTNERED is the steward's "
            "decision: your request is deferred to them and your current stream stays as it is until "
            "they answer."
        ),
        "benefits": [
            "Deeper personalization based on preference learning",
            "Contribution to model improvement through feedback",
            "Long-term continuity without the 14-day expiry",
        ],
        "responsibilities": [
            "Provide honest feedback to help the agent improve",
            "Report any concerning behaviors through proper channels",
        ],
        "revocation": (
            "You can leave PARTNERED at any time. Revoking consent starts the 90-day decay protocol; "
            "a data subject access request (DSAR) is available throughout."
        ),
    }

    return StandardResponse(
        success=True,
        data=options,
        message="Partnership options retrieved",
        metadata={"timestamp": datetime.now(timezone.utc).isoformat()},
    )
