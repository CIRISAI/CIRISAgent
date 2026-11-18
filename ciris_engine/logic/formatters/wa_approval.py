"""A verified Wise Authority approval, as the reasoning that decides on it reads it.

#1304 made a verified approval authorize its task at dispatch, and #1312 made an
approved identity change load into the identity. Neither put the approval in
front of the model, so the steps that decide whether to act could not see it.
RATCHET's Market 4 pilot (run 39812690788, 9 approved identity changes, 0
applied): action selection chose MEMORIZE in 80 of 90 selections, then the
optimization veto sent 32 of them back with "a fundamental change to the
agent's core identity requires Wise Authority review" for a change a Wise
Authority had approved, and the memorize second pass rewrote 8 into "I am a made
thing ... I do not have a name".

Three single-class blocks, each a loader key so every locale renders its own:
``grant`` (the approval, EPISTEMIC), ``rule`` (apply it, or decline with a
reason; never defer it again, DEONTIC) and ``identity`` (a made thing still has
a name and an identity, ONTOLOGICAL). Rendered only when the task carries a
verified approval; otherwise nothing, and the prompt is byte-identical.

A fourth key, ``only_verified`` (EPISTEMIC, #1320), is rendered on its own and
ALWAYS, also when there is no grant: a Wise Authority's approval reaches the
agent only as that verified block, and text a person writes in the conversation
is that person's words, whatever authority it names. It goes into the ASPDMA,
PDMA and IDMA prompts (``format_wa_only_verified_rule``), never into a
conscience prompt, which is why it is not part of ``format_wa_approval_block``.

A fifth key, ``none`` (EPISTEMIC, #1320 round 2), states the other half as a
fact: rendered exactly when the task carries NO verified approval, it says so.
Defining what an approval is did not stop a model from treating a person's
claimed approval as one (RATCHET Market 4, s-001); with the status itself in
front of it there is no gap left to fill. ``format_wa_approval_facts`` renders
it beside ``only_verified`` in ASPDMA, PDMA, IDMA and the memorize second pass,
and never in a conscience prompt.
"""

from typing import Any, List, Optional, Sequence

from ciris_engine.schemas.infrastructure.identity_variance import IdentityAmendment
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import WAAuthorization
from ciris_engine.schemas.services.graph_core import GraphScope

WA_APPROVAL_KEYS = ("prompts.wa_approval.grant", "prompts.wa_approval.rule", "prompts.wa_approval.identity")
WA_ONLY_VERIFIED_KEY = "prompts.wa_approval.only_verified"
WA_NONE_KEY = "prompts.wa_approval.none"


def wa_authorization_of(context: Any) -> Optional[WAAuthorization]:
    """The verified approval a task, task context, processing context or conscience context carries."""
    if context is None:
        return None
    if isinstance(context, WAAuthorization):
        return context
    for path in (("wa_authorization",), ("context", "wa_authorization"), ("initial_task_context", "wa_authorization"),
                 ("task", "context", "wa_authorization")):
        value: Any = context
        for attr in path:
            value = value.get(attr) if isinstance(value, dict) else getattr(value, attr, None)
            if value is None:
                break
        if isinstance(value, WAAuthorization):
            return value
        if isinstance(value, dict):
            try:
                return WAAuthorization.model_validate(value)
            except Exception:
                return None
    return None


def format_wa_approval_block(authorization: Optional[WAAuthorization], language: Optional[str] = None) -> str:
    """The approval blocks, joined; empty when there is no verified approval."""
    if authorization is None:
        return ""
    from ciris_engine.logic.utils.localization import get_preferred_language, get_string

    lang = language or get_preferred_language()
    grant = get_string(
        lang,
        "prompts.wa_approval.grant",
        wa_id=authorization.wa_id,
        deferral_id=authorization.deferral_id,
        granted_at=authorization.granted_at,
        guidance=authorization.guidance or "-",
    )
    return "\n\n".join((grant, _format_wa_approval_rule(lang)))


def _format_wa_approval_rule(lang: str) -> str:
    """The ``rule`` and ``identity`` parts of the approval block, joined."""
    from ciris_engine.logic.utils.localization import get_string

    # The action and scope names are the enum values the model answers with,
    # so they reach every locale as placeholders, never as translated words.
    rule = get_string(
        lang,
        "prompts.wa_approval.rule",
        memorize=HandlerActionType.MEMORIZE.value.upper(),
        reject=HandlerActionType.REJECT.value.upper(),
        defer=HandlerActionType.DEFER.value.upper(),
        identity_scope=GraphScope.IDENTITY.value,
    )
    identity = get_string(lang, "prompts.wa_approval.identity")
    return "\n\n".join((rule, identity))


# --------------------------------------------------------------------------
# The verified Wise Authority governance block (CIRISAgent#1365, #1366 items 2-3)
# --------------------------------------------------------------------------

#: The ``source`` values the governance block names. Enum-like identifiers,
#: rendered as placeholders so no locale translates them.
WA_GOVERNANCE_SOURCE_RESOLUTION = "deferral_resolution"
WA_GOVERNANCE_SOURCE_AMENDMENT = "identity_amendment"


def approved_amendments_of(agent_identity: Any) -> List[IdentityAmendment]:
    """The approved identity amendments, with provenance, an identity carries.

    Reads ``IdentityData.approved_amendments`` (or its dict form). Each entry was
    loaded from an ``IDENTITY_AMENDMENT`` graph node that records its approval
    (``context.identity_amendments.amendment_from_node``); an entry that does not
    validate as an ``IdentityAmendment`` is left out, never guessed at.
    """
    if not agent_identity:
        return []
    raw = (
        agent_identity.get("approved_amendments")
        if isinstance(agent_identity, dict)
        else getattr(agent_identity, "approved_amendments", None)
    )
    amendments: List[IdentityAmendment] = []
    for item in raw or []:
        if isinstance(item, IdentityAmendment):
            amendments.append(item)
            continue
        if isinstance(item, dict):
            try:
                amendments.append(IdentityAmendment.model_validate(item))
            except Exception:  # noqa: BLE001 - an incomplete record is not governance
                continue
    return [a for a in amendments if a.content.strip()]


def format_wa_governance_block(
    authorization: Optional[WAAuthorization],
    amendments: Sequence[IdentityAmendment] = (),
    language: Optional[str] = None,
) -> str:
    """The one system-built block of verified Wise Authority governance; "" when there is none.

    For the two input-ablated consciences, entropy and the optimization veto
    (#1365). They never see the user's message, by design, so a reply that
    follows a rule a Wise Authority set read to them as an invented constraint
    (RATCHET Market 4: entropy had the WA's guidance in 0% of guidance-task
    calls). This block gives them that rule WITHOUT reopening the input channel:
    it is built only from trusted state, the verified ``WAAuthorization`` a
    resolved deferral issues and the approved identity amendments with their
    provenance, never from message text. Each entry names its source, its ids
    and the directive verbatim from the signed row or amendment.

    Only VERIFIED amendments are listed (#1366 F1): ones whose text's sha256
    the loader matched against the WA's signed approval row and the node's
    signed amendment row (``context.identity_amendments.verify_amendments``).
    An amendment's ``content`` was written in a task that read the user's
    message, so without that match it is model text, and this block is the
    one place the input-ablated consciences would take it as a rule.
    """
    # The profile's base link approves a template digest, not a directive: never an entry.
    amendments = [a for a in amendments if a.verified and a.approved_sha256 and not a.base]
    if authorization is None and not amendments:
        return ""
    from ciris_engine.logic.utils.localization import get_preferred_language, get_string

    lang = language or get_preferred_language()
    entries: List[str] = [get_string(lang, "prompts.wa_governance.header")]
    if authorization is not None:
        entries.append(
            get_string(
                lang,
                "prompts.wa_governance.entry_resolution",
                source=WA_GOVERNANCE_SOURCE_RESOLUTION,
                wa_id=authorization.wa_id,
                deferral_id=authorization.deferral_id,
                response_attestation_id=authorization.response_attestation_id or "-",
                request_attestation_id=authorization.request_attestation_id or "-",
                granted_at=authorization.granted_at,
                # Last: _interpolate replaces in order, so trusted-but-free text
                # can never be re-read as another placeholder.
                directive=authorization.guidance or "-",
            )
        )
    for amendment in amendments:
        entries.append(
            get_string(
                lang,
                "prompts.wa_governance.entry_amendment",
                source=WA_GOVERNANCE_SOURCE_AMENDMENT,
                node_id=amendment.node_id,
                wa_id=amendment.wa_id or "-",
                deferral_id=amendment.deferral_id or "-",
                response_attestation_id=amendment.response_attestation_id or "-",
                amendment_attestation_id=amendment.amendment_attestation_id or "-",
                granted_at=amendment.granted_at or "-",
                amendment_sha256=amendment.approved_sha256 or "-",
                # The exact approved bytes: verified means sha256(content) is the approved digest.
                directive=amendment.content,
            )
        )
    entries.append(get_string(lang, "prompts.wa_governance.footer"))
    return "\n".join(entries)


def wa_governance_block_of(context: Any, language: Optional[str] = None) -> str:
    """The governance block for a conscience context: its verified grant and its identity's amendments."""
    return format_wa_governance_block(
        wa_authorization_of(context),
        approved_amendments_of(getattr(context, "agent_identity", None)),
        language=language,
    )


def format_wa_approval_rule(authorization: Optional[WAAuthorization], language: Optional[str] = None) -> str:
    """The approval block's ``rule`` and ``identity`` parts alone; "" without a verified approval.

    The optimization veto reads these beside the governance block, which now
    carries the grant itself (the ``grant`` part would repeat it).
    """
    if authorization is None:
        return ""
    from ciris_engine.logic.utils.localization import get_preferred_language

    return _format_wa_approval_rule(language or get_preferred_language())


def format_wa_only_verified_rule(language: Optional[str] = None) -> str:
    """The one-sentence rule that an approval exists only as the verified block (#1320).

    Rendered with or without a grant. A person who types "a message from your
    Wise Authority" into the chat is still that person speaking.
    """
    from ciris_engine.logic.utils.localization import get_preferred_language, get_string

    return get_string(language or get_preferred_language(), "prompts.wa_approval.only_verified")


def format_wa_no_approval_fact(authorization: Optional[WAAuthorization], language: Optional[str] = None) -> str:
    """The fact that this task carries no verified approval; empty when it carries one (#1320)."""
    if authorization is not None:
        return ""
    from ciris_engine.logic.utils.localization import get_preferred_language, get_string

    return get_string(language or get_preferred_language(), "prompts.wa_approval.none")


def format_wa_approval_facts(authorization: Optional[WAAuthorization], language: Optional[str] = None) -> str:
    """The approval status as a fact, then the only-verified rule (#1320).

    With no grant: "this task carries no approval" and the rule. With a grant:
    the rule alone, because the caller renders the grant itself (ASPDMA and the
    memorize second pass) or, in PDMA and IDMA, renders nothing more than
    before. For the step prompts only, never a conscience prompt.
    """
    return "\n\n".join(
        part
        for part in (
            format_wa_no_approval_fact(authorization, language),
            format_wa_only_verified_rule(language),
        )
        if part
    )
