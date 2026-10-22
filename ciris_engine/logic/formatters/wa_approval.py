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
"""

from typing import Any, Optional

from ciris_engine.schemas.runtime.models import WAAuthorization

WA_APPROVAL_KEYS = ("prompts.wa_approval.grant", "prompts.wa_approval.rule", "prompts.wa_approval.identity")


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
    rule = get_string(lang, "prompts.wa_approval.rule")
    identity = get_string(lang, "prompts.wa_approval.identity")
    return "\n\n".join((grant, rule, identity))
