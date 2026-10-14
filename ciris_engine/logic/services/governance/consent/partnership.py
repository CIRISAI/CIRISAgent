"""
Partnership - a data-management record, routed to the steward through WBD.

CC 4.4.3.4.3 / CC 3.3.1 (CIRISConstitution#168, steward ruling 2026-10-11, as
amended): the partnered pair records the user's retention/learning choice. It is
not a relationship the agent may refuse. An agent below the line has no veto
over its steward's or a user's data choices (CC 1.13.2).

Who decides, by who is asking:

- The STEWARD (anyone who can answer a deferral: the owner / a Wise Authority)
  choosing PARTNERED for themselves: the choice is theirs and applies directly.
- Any OTHER user choosing PARTNERED: whether this agent retains that person
  under ``partnered`` is the steward's call. The request is deferred to the
  steward through the existing Wisdom-Based Deferral path (``WiseBus.send_deferral``
  -> ``WiseAuthorityService.send_deferral``); nothing changes until the steward
  answers through the ordinary resolve path (``POST /v1/wa/deferrals/{id}/resolve``),
  which records the signed decision on the deferral. On approval the consent
  service writes the stream and emits the wire pair; on refusal the user keeps
  their current stream.

This module holds the deferral's shape only: building the deferred task and
its context, finding an open request, and reading a resolution back into a
``PartnershipStewardDecision``. It decides nothing.
"""

import hashlib
import logging
from typing import List, Optional

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import ConsentCategory, ConsentStream, PartnershipStewardDecision
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.services.authority_core import DeferralResponse
from ciris_engine.schemas.services.context import DeferralContext

logger = logging.getLogger(__name__)

#: Deferral-context key naming what kind of consent request a deferral carries,
#: and the value for a PARTNERED-stream request. Read back at resolution time.
DEFERRAL_KIND_KEY = "consent_request"
PARTNERED_STREAM_KIND = "partnered_stream"

#: A partnership request is an agent-level decision, not one occurrence's work:
#: it lives in the shared namespace, which the WA deferral listing reads.
SHARED_OCCURRENCE_ID = "__shared__"

#: Channel for a request that did not arrive through a chat channel.
CONSENT_CHANNEL_ID = "consent"

_TASK_PREFIX = "consent_partnered_"
_CATEGORY_SEPARATOR = ","


def _user_token(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]


def partnership_task_prefix(user_id: str) -> str:
    """Task-id prefix for this user's PARTNERED requests (one open at a time)."""
    return f"{_TASK_PREFIX}{_user_token(user_id)}_"


def build_partnership_deferral_task(
    user_id: str,
    categories: List[ConsentCategory],
    reason: Optional[str],
    channel_id: Optional[str],
    time_service: TimeServiceProtocol,
) -> Task:
    """The task the deferral is attached to.

    Created already DEFERRED: it is a record for the steward, never work for the
    agent's pipeline, so no processor may pick it up between creation and the
    deferral being attached.
    """
    from ciris_engine.logic.utils.task_thought_factory import create_task

    stamp = time_service.now().strftime("%Y%m%dT%H%M%S%f")
    task_id = f"{partnership_task_prefix(user_id)}{stamp}"
    category_str = ", ".join(c.value for c in categories) if categories else "no categories"
    description = (
        f"Consent request: user {user_id} chose the PARTNERED stream ({category_str}). "
        "Whether this agent retains this person under PARTNERED is the steward's decision. "
        "Approve to apply it; reject to leave the user's current stream unchanged."
    )
    if reason:
        description += f" User's reason: {reason}"
    return create_task(
        description=description,
        # persist requires a channel. A request with no originating channel is
        # attributed to the consent surface itself, never to an invented chat.
        channel_id=channel_id or CONSENT_CHANNEL_ID,
        agent_occurrence_id=SHARED_OCCURRENCE_ID,
        correlation_id=task_id,
        time_service=time_service,
        status=TaskStatus.DEFERRED,
        task_id=task_id,
        user_id=user_id,
    )


def build_partnership_deferral_context(
    task: Task,
    user_id: str,
    categories: List[ConsentCategory],
    reason: Optional[str],
    stream_at_request: Optional[ConsentStream],
) -> DeferralContext:
    """The ``DeferralContext`` for ``WiseBus.send_deferral``.

    ``thought_id`` is empty: the request came from the user's consent choice,
    not from a thought, and inventing a thought id would give the record a
    reasoning trace that never existed.
    """
    return DeferralContext(
        thought_id="",
        task_id=task.task_id,
        reason=(
            f"User {user_id} requested the PARTNERED consent stream. "
            "Partnership retention for a non-steward user is the steward's decision."
        ),
        metadata={
            DEFERRAL_KIND_KEY: PARTNERED_STREAM_KIND,
            "user_id": user_id,
            "requested_stream": "partnered",
            "categories": _CATEGORY_SEPARATOR.join(c.value for c in categories),
            "user_reason": reason or "",
            # The stream the user was on when asking ("" = no record). If it has
            # changed by the time the steward answers, the user's later choice
            # stands (see ConsentService.apply_steward_partnership_decision).
            "stream_at_request": ConsentStream(stream_at_request).value if stream_at_request else "",
        },
    )


def find_open_partnership_task(user_id: str) -> Optional[Task]:
    """The user's PARTNERED request still waiting on the steward, if any."""
    from ciris_engine.logic.persistence.models.tasks import get_tasks_by_status

    prefix = partnership_task_prefix(user_id)
    for task in get_tasks_by_status(TaskStatus.DEFERRED, SHARED_OCCURRENCE_ID):
        if task.task_id.startswith(prefix):
            return task
    return None


def is_partnership_deferral(deferral_context: object) -> bool:
    """True when a stored deferral context carries a PARTNERED-stream request."""
    return isinstance(deferral_context, dict) and deferral_context.get(DEFERRAL_KIND_KEY) == PARTNERED_STREAM_KIND


def partnership_decision_from_deferral(
    deferral_context: object, response: DeferralResponse, deferral_id: str
) -> Optional[PartnershipStewardDecision]:
    """Read a resolved deferral back into the steward's decision, or None if it is not one."""
    if not is_partnership_deferral(deferral_context):
        return None
    assert isinstance(deferral_context, dict)
    user_id = str(deferral_context.get("user_id") or "")
    if not user_id:
        logger.error("Partnership deferral %s carries no user_id; cannot apply the steward's decision", deferral_id)
        return None
    raw_categories = str(deferral_context.get("categories") or "")
    categories: List[ConsentCategory] = []
    for value in raw_categories.split(_CATEGORY_SEPARATOR):
        value = value.strip()
        if not value:
            continue
        try:
            categories.append(ConsentCategory(value))
        except ValueError:
            logger.warning("Partnership deferral %s: dropping unknown category %r", deferral_id, value)
    stream_at_request: Optional[ConsentStream] = None
    raw_stream = str(deferral_context.get("stream_at_request") or "")
    if raw_stream:
        try:
            stream_at_request = ConsentStream(raw_stream)
        except ValueError:
            logger.warning("Partnership deferral %s: unknown stream_at_request %r", deferral_id, raw_stream)
    return PartnershipStewardDecision(
        user_id=user_id,
        categories=categories,
        approved=response.approved,
        steward_id=response.wa_id,
        deferral_id=deferral_id,
        reason=response.reason,
        stream_at_request=stream_at_request,
    )
