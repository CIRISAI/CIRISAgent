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

from typing import Any, Optional

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
    return "\n\n".join((grant, rule, identity))


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
