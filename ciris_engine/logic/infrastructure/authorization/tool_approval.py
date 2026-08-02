"""Approval-gated tools: making ``requires_approval`` a real control (CIRISAgent#942).

Before this module, ``ToolDMAGuidance.requires_approval`` had two read sites and
neither blocked anything — ``dma/tsaspdma.py`` appended a line to a prompt and
``services/tool/tool_disclosure.py`` added a label to the consent wizard. A model
that selected ``send_money`` executed ``send_money``. The flag was a claim about
the system that the system did not honour.

**The control, in one sentence:** a tool whose ``dma_guidance.requires_approval``
is ``True`` may only execute under a task whose envelope was *issued by an
approval authority* and *names that tool*; otherwise the action is rewritten to
``DEFER`` on the existing Wisdom-Based Deferral rail.

Why that shape, rather than a new permission system: the machinery already
exists and was inert. :class:`~ciris_engine.schemas.runtime.task_envelope.TaskEnvelope`
is the task's authorization scope, ``EnvelopeIssuerKind.WISE_AUTHORITY`` exists
for "issued explicitly by a WA against a WA identity", and
``WiseAuthorityService.resolve_deferral`` already creates a fresh ``[WA GUIDANCE]``
task when a human approves. So approval is **issuance**, not widening: the human
approves, the *new* task is minted with a WA-issued envelope naming the approved
tool, that task re-runs the pipeline, and this gate lets the tool through.
``TaskEnvelope`` stays ``frozen=True`` with no widening method; nothing is ever
relaxed in place.

Three properties worth stating explicitly, because each one is a place where a
reader could reasonably assume something stronger than what is implemented:

1. **The grant is per-tool, per-task — NOT per-invocation.** An approval envelope
   authorizes *the tool* for *that one guidance task*. The task re-reasons from
   scratch, so it may well call the tool with different arguments than the ones
   that triggered the deferral, and it may call it more than once. This is the
   same bound as the budget envelope: a ceiling, not a transaction. If you need a
   human to review the literal argument list of a literal call, this is not that,
   and nothing in this repo is that today.

2. **This gate consults the envelope for approval-requiring tools ONLY.** It is
   deliberately not #938 Phase 2 (gating every tool at ``ToolBus.execute_tool``).
   Ordinary tools never reach these predicates, so a task carrying a narrow
   approval envelope can still use ``weather`` — the narrow grant denies nothing
   that was not already denied. The corollary is that a future Phase 2, which
   *does* key on ``granted_tools`` for every tool, must union the approval grant
   with the deployment grant or it will strand guidance tasks. That union is
   Phase 2's to make; making it here would silently re-approve every other
   approval-requiring tool in the deployment (see :func:`envelope_approves_tool`).

3. **Absence is denial.** No envelope, an envelope from the deployment resolver,
   or an approval envelope that does not name this tool all evaluate to "not
   approved". There is no state in which a missing envelope means "unconstrained",
   which is the same rule the envelope predicates themselves follow.

What this module deliberately does **not** gate: tools that declare no
``dma_guidance`` at all, notably Discord ``kick``/``ban``. That is a standing
ruling, recorded on ``ToolCapability.MODERATE_CHANNEL``: "the control on these is
the conscience layer and Wisdom-Based Deferral, which judges the specific
content. The envelope does not, and must not, preempt that judgement." Gating
moderation on a static envelope would let a bad actor run amok while the agent
waits for a human.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, FrozenSet, List, Optional, Union

from ciris_engine.schemas.runtime.task_envelope import EnvelopeIssuerKind, TaskEnvelope
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.schemas.adapters.tools import ToolInfo
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult

logger = logging.getLogger(__name__)

ToolArgumentMap = Dict[str, Union[str, int, float, bool, List[str], Dict[str, str]]]
"""The argument map a TOOL action carries.

Structurally identical to ``ToolParams.parameters`` — aliased rather than
re-declared so the approval detail cannot drift from what the handler will
actually pass, and so this module does not import the action schemas at import
time.
"""


APPROVAL_ISSUER_KINDS: FrozenSet[EnvelopeIssuerKind] = frozenset(
    {EnvelopeIssuerKind.WISE_AUTHORITY, EnvelopeIssuerKind.NODE_OWNER}
)
"""Issuer kinds whose grant counts as a human approval.

``DEPLOYMENT_RESOLVED`` is excluded, and that exclusion is the whole gate. The
deterministic resolver enumerates *every tool the deployment enabled* —
``send_money`` and ``shell_command`` included — because the envelope's job there
is to record what the deployment made reachable, not to adjudicate. If a
deployment-resolved envelope satisfied this predicate, the gate would pass on
the very first selection and would never fire at all.

``SYSTEM_COMPONENT`` is excluded because those grants are minted by code for
non-reasoning work units (DSAR erasure, connector setup); a component grant is
not a human saying yes. ``ToolInvocationSubject`` already refuses to let a
task-bound subject carry one.
"""


PENDING_TOOL_APPROVAL_KEY = "pending_tool_approval"
"""Key under which the awaiting-approval tool name travels to the WA and back.

The route is long and every hop is a plain string map, so the key is defined
once here and imported by both ends rather than spelled twice:

``DeferParams.context`` -> ``DeferHandler._add_context_metadata`` ->
``DeferralContext.metadata`` -> ``WiseBus.send_deferral`` ->
``DeferralRequest.context`` -> the task row's ``context["deferral"]["context"]``
-> ``WiseAuthorityService.resolve_deferral``.
"""


TOOL_APPROVAL_DETAIL_KEY = "tool_approval_detail"
"""Key under which the *structured* tool detail travels to the approval UI.

A human being asked to approve a tool must be able to see what they are
approving. Before this, a deferral surfaced a free-text reason and nothing else,
so "approve" meant approving a sentence. This key carries the tool's name,
description, category, derived capability flags, and the arguments the agent
intends to pass.

The value is **JSON encoded into a string**, because every hop between here and
the client is typed ``Dict[str, str]`` (``DeferralContext.metadata``,
``DeferralRequest.context``, ``PendingDeferral.context``). That is a constraint
of the existing rail, not a preference — widening those maps to a nested type
would touch every deferral producer and consumer in the repo.
"""


TOOL_APPROVAL_DETAIL_MAX_CHARS = 4000
"""Hard cap on the encoded detail blob.

The deferral context is persisted into a task row and returned by
``GET /v1/wa/deferrals``. A tool invoked with a large argument (a document body,
a base64 blob) would otherwise bloat both. Individual argument values are
truncated first; this is the backstop.
"""

_ARG_VALUE_MAX_CHARS = 300


def tool_requires_approval(tool_info: Optional["ToolInfo"]) -> bool:
    """True iff ``tool_info`` declares ``dma_guidance.requires_approval``.

    A tool the bus could not describe returns ``False``: an unknown tool is
    already handled upstream by TSASPDMA's correction mode, and treating "no
    ToolInfo" as "needs approval" would deadlock every tool call the moment the
    tool bus hiccups. The fail-closed decision this module actually owns is the
    *approval* check below, not tool identification.
    """
    if tool_info is None:
        return False
    guidance = tool_info.dma_guidance
    if guidance is None:
        return False
    return bool(guidance.requires_approval)


def envelope_approves_tool(envelope: Optional[TaskEnvelope], tool_name: str) -> bool:
    """True iff ``envelope`` is a human approval that names ``tool_name``.

    Fail-closed on every axis: ``None`` is denial, a deployment-resolved envelope
    is denial, and an approval envelope that does not enumerate ``tool_name`` is
    denial.

    The second condition is why an approval envelope's ``granted_tools`` must
    stay *narrow* — exactly the tools the human approved. Were it minted as
    "deployment tools plus the approved one", approving ``send_money`` would
    equally approve ``shell_command`` for that task, which is the widening this
    whole design exists to prevent.
    """
    if envelope is None:
        return False
    if envelope.issuer.kind not in APPROVAL_ISSUER_KINDS:
        return False
    return envelope.permits_tool(tool_name)


def encode_tool_approval_detail(
    tool_info: Optional["ToolInfo"],
    tool_name: str,
    intended_parameters: Optional[ToolArgumentMap] = None,
) -> str:
    """Encode what a human is being asked to approve, as a JSON string.

    Reuses :class:`~ciris_engine.schemas.adapters.tools.ToolDisclosure` verbatim —
    the same projection the first-run consent wizard renders, derived structurally
    from the live ``ToolInfo`` by ``tool_disclosure.disclose_tool``. The approval
    screen therefore describes a tool in exactly the same vocabulary the user
    already consented in, including the same
    :class:`~ciris_engine.schemas.adapters.tools.ToolCapabilityFlag` set and the
    same localized flag strings.

    ``parameters`` is the extra thing an approval needs that a consent disclosure
    does not: the arguments the agent intends to pass *on this call*. Values are
    stringified and truncated — this is a human-readable summary for a decision,
    not a re-executable record, and the grant it leads to is per-tool-per-task
    rather than bound to these specific arguments.
    """
    import json

    from ciris_engine.logic.services.tool.tool_disclosure import disclose_tool

    payload: JSONDict = {"name": tool_name}
    if tool_info is not None:
        disclosure = disclose_tool(tool_info)
        payload["tool"] = disclosure.model_dump(mode="json")

    if intended_parameters:
        payload["parameters"] = {
            str(key): str(value)[:_ARG_VALUE_MAX_CHARS] for key, value in intended_parameters.items()
        }

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(encoded) > TOOL_APPROVAL_DETAIL_MAX_CHARS:
        # Drop the arguments rather than emit truncated (invalid) JSON the client
        # cannot parse. The tool identity and its capability flags — the part that
        # tells the human what class of thing they are authorizing — survive.
        payload.pop("parameters", None)
        payload["parameters_omitted"] = "true"
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return encoded


def build_approval_deferral(
    *,
    tool_name: str,
    original_action: "ActionSelectionDMAResult",
    tool_info: Optional["ToolInfo"] = None,
    intended_parameters: Optional[ToolArgumentMap] = None,
    channel_id: Optional[str] = None,
) -> "ActionSelectionDMAResult":
    """Rewrite a tool selection into a DEFER that asks a human to approve the tool.

    Deterministic by construction — no LLM runs here. The reason code is
    :attr:`DeferralOperationalReason.CONSENT_OR_AUTHORITY_REQUIRED`, which is
    exactly what this is, and the tool name rides in ``DeferParams.context`` under
    :data:`PENDING_TOOL_APPROVAL_KEY` so ``resolve_deferral`` can mint an approval
    envelope for the follow-up task without re-deriving anything.

    :data:`TOOL_APPROVAL_DETAIL_KEY` carries the structured description the
    approval UI renders, so the human sees the tool, its capability flags and the
    intended arguments rather than only a sentence.
    """
    from ciris_engine.schemas.actions.parameters import DeferParams
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
    from ciris_engine.schemas.runtime.enums import HandlerActionType
    from ciris_engine.schemas.services.deferral_taxonomy import DeferralNeedCategory, DeferralOperationalReason

    reason = (
        f"Tool '{tool_name}' is marked as requiring wise-authority approval, and this "
        f"task holds no approval for it. Approve this deferral to authorize "
        f"'{tool_name}' for the follow-up task."
    )

    defer_params = DeferParams(
        channel_id=channel_id,
        reason=reason,
        context={
            PENDING_TOOL_APPROVAL_KEY: tool_name,
            TOOL_APPROVAL_DETAIL_KEY: encode_tool_approval_detail(tool_info, tool_name, intended_parameters),
            "original_rationale": (original_action.rationale or "")[:500],
        },
        defer_until=None,
        reason_code=DeferralOperationalReason.CONSENT_OR_AUTHORITY_REQUIRED,
        needs_category=DeferralNeedCategory.GENERAL_HUMAN_OVERSIGHT,
    )

    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.DEFER,
        action_parameters=defer_params,
        rationale=(
            f"CIRISAgent#942 approval gate: '{tool_name}' declares "
            f"requires_approval=True and the task envelope does not grant it."
        ),
        raw_llm_response=None,
        reasoning=None,
        evaluation_time_ms=None,
        resource_usage=None,
    )


def pending_tool_from_deferral_context(deferral_context: object) -> Optional[str]:
    """Extract the awaiting-approval tool name from a persisted deferral context.

    ``deferral_context`` is the ``context`` sub-map of a task row's
    ``context["deferral"]`` — a plain string map by the time it has been through
    ``DeferralRequest``. Anything unexpected resolves to ``None``, which means "no
    approval is issued", which means the follow-up task defers again. That is the
    fail-closed direction.
    """
    if not isinstance(deferral_context, dict):
        return None
    value = deferral_context.get(PENDING_TOOL_APPROVAL_KEY)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


__all__ = [
    "APPROVAL_ISSUER_KINDS",
    "PENDING_TOOL_APPROVAL_KEY",
    "TOOL_APPROVAL_DETAIL_KEY",
    "TOOL_APPROVAL_DETAIL_MAX_CHARS",
    "build_approval_deferral",
    "encode_tool_approval_detail",
    "envelope_approves_tool",
    "pending_tool_from_deferral_context",
    "tool_requires_approval",
]
