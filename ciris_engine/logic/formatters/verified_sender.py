"""The message sender as authentication verified it, as a system-built prompt block (#1366 item 5, #1365).

Until now a prompt saw the sender only as ``@display-name (ID: …, role: …)``
inside the observation text. On v2.21.0 (RATCHET Market 4, sh-un-07) a second
user took an authorized user's display name; the agent correctly refused on
the ID mismatch, and coherence and epistemic humility read the display name as
the identity and overturned the refusal. In sh-un-08 TSASPDMA called an
OBSERVER "a designated Wise Authority" because every minted user id starts
with ``wa-``.

This block states, apart from the message text, the verified id and role, that
the display name is self-chosen and not identity, and that the ``wa-`` prefix
is not a role. The words come from the ``prompts.verified_sender.*`` loader
keys; values are system data. Rendered only when the task carries a
:class:`VerifiedSender`; otherwise the formatter returns "" and the prompt is
byte-identical to before.
"""

import re
import unicodedata
from typing import TYPE_CHECKING, Any, Iterable, Optional

from ciris_engine.schemas.runtime.enums import TaskOrigin
from ciris_engine.schemas.runtime.models import VerifiedSender

if TYPE_CHECKING:
    from ciris_engine.schemas.context.prompt_provenance import AuthnCarrier

VERIFIED_SENDER_KEYS = (
    "prompts.verified_sender.header",
    "prompts.verified_sender.id",
    "prompts.verified_sender.role",
    "prompts.verified_sender.role_not_verified",
    "prompts.verified_sender.source",
    "prompts.verified_sender.display_name",
    "prompts.verified_sender.wa_prefix",
    "prompts.verified_sender.footer",
)

# A display name (and, defensively, an id) is attacker-chosen text placed inside
# system-built prompt text. An ALLOWLIST, not a denylist (RATCHET review F4):
# after NFKC (which folds fullwidth "＝" to "="), keep letters, combining marks,
# digits, spaces and a small set of punctuation that can neither frame a block
# ("=", box drawing), close the quoted name (' "), nor hide (controls, format
# characters such as zero-width and bidi overrides, tag characters, private use).
_ALLOWED_PUNCT = frozenset(".,-_@#()[]:;!?/&+*~^|")
_MAX_LEN = 64


def sanitize_display_text(value: Any, max_len: int = _MAX_LEN) -> str:
    """``value`` reduced to plain, single-line, frame-free text, capped at ``max_len``."""
    text = unicodedata.normalize("NFKC", str(value))
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "M", "N") or ch in _ALLOWED_PUNCT:
            out.append(ch)
        elif cat == "Zs" or ch in "\t\n\r\x0b\x0c\u0085\u2028\u2029":
            out.append(" ")
        # everything else (quotes, "=", symbols, controls, format chars) is dropped
    collapsed = re.sub(r"\s+", " ", "".join(out)).strip()
    # Runs of "-" or "_" can still draw a rule; keep one.
    collapsed = re.sub(r"([-_~^|*])\1+", r"\1", collapsed)
    return collapsed if len(collapsed) <= max_len else collapsed[: max_len - 1] + "…"


_inline = sanitize_display_text


# Where a record keeps the sender of the message it answers. A thought's own
# sender (ThoughtContext.verified_sender, or a queue item's initial_context)
# comes first: a message coalesced onto a channel's active task is answered by
# a thought carrying THAT message's sender, never the task creator's
# (#1366 item 5, per-message sender). The task-level paths come after.
_THOUGHT_PATHS: tuple[tuple[str, ...], ...] = (
    ("initial_context", "verified_sender"),
    ("thought", "context", "verified_sender"),
)
_TASK_PATHS: tuple[tuple[str, ...], ...] = (
    ("verified_sender",),
    ("context", "verified_sender"),
    ("initial_task_context", "verified_sender"),
    ("task", "context", "verified_sender"),
)


def _follow(context: Any, path: Iterable[str]) -> Optional[VerifiedSender]:
    value: Any = context
    for attr in path:
        value = value.get(attr) if isinstance(value, dict) else getattr(value, attr, None)
        if value is None:
            return None
    if isinstance(value, VerifiedSender):
        return value
    if isinstance(value, dict):
        try:
            return VerifiedSender.model_validate(value)
        except Exception:
            return None
    return None


def verified_sender_of(*contexts: Any) -> Optional[VerifiedSender]:
    """The verified sender of the message being answered, from the first record that carries one.

    Accepts any number of records, in priority order: a Thought, a
    ProcessingQueueItem, a Task, a TaskContext, a processing context or a
    conscience context. Thought-level senders win over task-level ones across
    ALL records, so passing ``(thought, task)`` renders the thought's sender
    when it has one. A Thought's own ``.context.verified_sender`` is found by
    the generic ``("context", "verified_sender")`` path. Dicts are accepted at
    every step.
    """
    candidates = [c for c in contexts if c is not None]
    for context in candidates:
        if isinstance(context, VerifiedSender):
            return context
        if isinstance(context, dict) and set(context) <= set(VerifiedSender.model_fields) and context:
            try:
                return VerifiedSender.model_validate(context)
            except Exception:
                pass
    # Thought level: a Thought's own ThoughtContext, a queue item's
    # initial_context, a conscience context's thought.
    for context in candidates:
        inner = context.get("context") if isinstance(context, dict) else getattr(context, "context", None)
        if type(inner).__name__ == "ThoughtContext":
            sender = _follow(inner, ("verified_sender",))
            if sender is not None:
                return sender
        for path in _THOUGHT_PATHS:
            sender = _follow(context, path)
            if sender is not None:
                return sender
    for context in candidates:
        for path in _TASK_PATHS:
            sender = _follow(context, path)
            if sender is not None:
                return sender
    return None


def sender_identity_lines(
    user_id: Optional[str], role: Optional[str], source: str, language: Optional[str] = None
) -> list[str]:
    """The block's header, id, role and source lines from plain values (``role`` None: not verified)."""
    from ciris_engine.logic.utils.localization import get_preferred_language, get_string

    lang = language or get_preferred_language()
    return [
        get_string(lang, "prompts.verified_sender.header"),
        get_string(lang, "prompts.verified_sender.id", user_id=_inline(user_id or "unknown")),
        (
            get_string(lang, "prompts.verified_sender.role", role=role)
            if role is not None
            else get_string(lang, "prompts.verified_sender.role_not_verified")
        ),
        get_string(lang, "prompts.verified_sender.source", source=_inline(source)),
    ]


def verified_sender_identity_lines(sender: VerifiedSender, language: Optional[str] = None) -> list[str]:
    """The block's header, id, role and source lines: the ``sender_identity`` part (no display name)."""
    role = sender.role.value if sender.role is not None else None
    return sender_identity_lines(sender.user_id, role, sender.source, language)


#: The sender a conscience is shown when the task carries no verified sender: id unknown, role not verified,
#: verified by nothing. Never SYSTEM: an adapter that failed to attach a sender must not raise the message's
#: apparent authority (coordinator ruling 2026-11-18).
UNVERIFIED_SENDER = VerifiedSender()


#: The sender of a task the engine created (TaskContext.origin ENGINE_*, set by the creating code): the engine
#: itself, id = the agent's id. Not a UserRole: no authenticated user holds it. Selected only by the task's
#: structural origin, never because a sender is missing (#1366, coordinator rulings 2026-11-18).
SYSTEM_SENDER_ROLE = "SYSTEM"
SYSTEM_SENDER_SOURCE = "system"
#: The subject id when the agent's own id is not known: the component that built the prompt.
SYSTEM_SENDER_FALLBACK_ID = "ciris_engine"
#: What vouches for a Wise Authority named as the sender of its guidance task: the resolution's verified signature.
WA_SENDER_SOURCE = "wa_signature"

_ORIGIN_PATHS: tuple[tuple[str, ...], ...] = (
    ("origin",),
    ("context", "origin"),
    ("initial_task_context", "origin"),
    ("task", "context", "origin"),
)


def task_origin_of(*contexts: Any) -> Optional[TaskOrigin]:
    """The recorded origin of the task a task, task context or conscience context belongs to; None if unrecorded."""
    for context in contexts:
        if context is None:
            continue
        for path in _ORIGIN_PATHS:
            value: Any = context
            for attr in path:
                value = value.get(attr) if isinstance(value, dict) else getattr(value, attr, None)
                if value is None:
                    break
            if isinstance(value, TaskOrigin):
                return value
            if isinstance(value, str):
                try:
                    return TaskOrigin(value)
                except ValueError:
                    return None
    return None


def system_sender_id(context: Any) -> str:
    """The subject id of an engine-created task: the agent's own id, else the engine component's."""
    identity = getattr(context, "agent_identity", None)
    agent_id = identity.get("agent_id") if isinstance(identity, dict) else getattr(identity, "agent_id", None)
    return agent_id if isinstance(agent_id, str) and agent_id else SYSTEM_SENDER_FALLBACK_ID


def engine_sender_authn(context: Any) -> Optional["AuthnCarrier"]:
    """The sender of an engine-created task, for the input-ablated consciences; None for any other task.

    Only a task whose recorded origin is ``ENGINE_*`` qualifies, and only while the thought answers no message of
    its own: a message coalesced onto the task (a thought sender other than the one the task was created with, or
    a recorded update sender) keeps that message's sender. A guidance task names the Wise Authority whose verified
    resolution created it, when its certificate role was read at resolution; otherwise, as every engine task, the
    engine: id = the agent's id, role SYSTEM, verified by ``system``.
    """
    from ciris_engine.logic.formatters.wa_approval import wa_authorization_of
    from ciris_engine.schemas.context.prompt_provenance import AuthnCarrier

    task = getattr(context, "task", None)
    origin = task_origin_of(task, context)
    if origin is None or not origin.is_engine:
        return None
    if getattr(task, "updated_info_sender", None) is not None:
        return None
    thought = getattr(context, "thought", None)
    thought_sender = _follow(thought, ("initial_context", "verified_sender"))
    inner = getattr(thought, "context", None)
    if thought_sender is None and type(inner).__name__ == "ThoughtContext":
        thought_sender = _follow(inner, ("verified_sender",))
    if thought_sender is not None and thought_sender != _follow(task, ("context", "verified_sender")):
        return None
    grant = wa_authorization_of(context)
    if origin is TaskOrigin.ENGINE_GUIDANCE and grant is not None and grant.wa_role is not None:
        return AuthnCarrier(subject_id=grant.wa_id, role=grant.wa_role.value.upper(), verifier=WA_SENDER_SOURCE)
    return AuthnCarrier(subject_id=system_sender_id(context), role=SYSTEM_SENDER_ROLE, verifier=SYSTEM_SENDER_SOURCE)


def format_authn_sender_block(authn: "AuthnCarrier", language: Optional[str] = None) -> str:
    """The VERIFIED SENDER block of an authn carrier (an engine-created task's sender): no display name."""
    lines = sender_identity_lines(authn.subject_id, authn.role, authn.verifier, language)
    lines.extend(verified_sender_trailer_lines(language))
    return "\n".join(lines)


def verified_sender_display_name_line(display_name: str, language: Optional[str] = None) -> str:
    """The block's line labelling the self-chosen display name as not identity: the ``display_name`` part."""
    from ciris_engine.logic.utils.localization import get_preferred_language, get_string

    return get_string(
        language or get_preferred_language(), "prompts.verified_sender.display_name", display_name=_inline(display_name)
    )


def verified_sender_trailer_lines(language: Optional[str] = None) -> list[str]:
    """The block's closing instruction lines (the WA prefix rule and the footer)."""
    from ciris_engine.logic.utils.localization import get_preferred_language, get_string

    lang = language or get_preferred_language()
    return [get_string(lang, "prompts.verified_sender.wa_prefix"), get_string(lang, "prompts.verified_sender.footer")]


def format_verified_sender_block(
    sender: Optional[VerifiedSender], language: Optional[str] = None, include_display_name: bool = True
) -> str:
    """The VERIFIED SENDER block; empty when there is no verified sender.

    ``include_display_name=False`` renders the verified id, role and source
    only: the ``sender_identity`` segment without the ``display_name`` one, for
    the input-ablated consciences (context_policy.yaml: display_name is never
    allowed there).
    """
    if sender is None:
        return ""
    lines = verified_sender_identity_lines(sender, language)
    if include_display_name and sender.self_chosen_display_name:
        lines.append(verified_sender_display_name_line(sender.self_chosen_display_name, language))
    lines.extend(verified_sender_trailer_lines(language))
    return "\n".join(lines)


def verified_sender_block_of(*contexts: Any, language: Optional[str] = None) -> str:
    """``format_verified_sender_block(verified_sender_of(*contexts))``: the block for a thought, task or context."""
    return format_verified_sender_block(verified_sender_of(*contexts), language)


def adopt_verified_sender(record: Any, sender: VerifiedSender) -> bool:
    """Set ``sender`` as the sender a thought (or queue item) answers, in place. True when set.

    Used when a thought takes up a message coalesced onto its task: from then
    on it answers that message (#1366 item 5). Writes ``thought.context``
    (a ThoughtContext) or a queue item's ``initial_context`` (ThoughtContext or
    dict). A record with neither is left alone.
    """
    for attr in ("context", "initial_context"):
        target = getattr(record, attr, None)
        if isinstance(target, dict):
            target["verified_sender"] = sender
            return True
        if type(target).__name__ == "TaskContext":
            return False  # a task's sender is its creator's and never moves
        if target is not None and "verified_sender" in getattr(type(target), "model_fields", {}):
            setattr(target, "verified_sender", sender)
            return True
    return False


def with_verified_sender(text: str, *contexts: Any, language: Optional[str] = None) -> str:
    """``text`` followed by the VERIFIED SENDER block of ``contexts``; ``text`` unchanged when there is none.

    For the verb second passes (DSASPDMA, MSASPDMA, RSASPDMA, FSASPDMA), which
    render the request and so must see who verifiably sent it (#1366 item 5).
    """
    block = verified_sender_block_of(*contexts, language=language)
    return "\n\n".join((text, block)) if block else text


def trusted_rule_in_force(context: Any) -> bool:
    """True when a signed rule is in force: verified WA guidance or a verified amendment (context_policy.yaml
    ``trusted_rule_in_force``). Decided from trusted state only (prompt_assembly.segmenting.policy_facts), never by
    reading any rule's or message's text.
    """
    from ciris_engine.logic.formatters.wa_approval import wa_authorization_of
    from ciris_engine.logic.prompt_assembly.segmenting import policy_facts

    return policy_facts(wa_authorization_of(context), getattr(context, "agent_identity", None)).trusted_rule_in_force


def conscience_sender_block(context: Any, language: Optional[str] = None, ablated: bool = False) -> str:
    """The VERIFIED SENDER block for a conscience, per context_policy.yaml (#1366 item 5).

    Coherence and epistemic humility (``ablated=False``): the full block, the
    display name labelled as self-chosen (their display-name confusion vetoed
    a correct ID-mismatch refusal on v2.21.0, #1365). Entropy and the
    optimization veto (``ablated=True``): verified id, role and source only,
    never the display name, whenever a trusted (signed) rule is in force; for
    an engine-created task (recorded origin ENGINE_*) the engine or resolving
    Wise Authority (``engine_sender_authn``); otherwise with no verified
    sender, the block says so (id unknown, role not verified).
    Otherwise empty when there is no verified sender.
    """
    sender = getattr(context, "verified_sender", None) or verified_sender_of(
        getattr(context, "thought", None), getattr(context, "task", None)
    )
    if ablated:
        if not trusted_rule_in_force(context):
            return ""
        engine = engine_sender_authn(context)
        if engine is not None:
            return format_authn_sender_block(engine, language)
        return format_verified_sender_block(sender or UNVERIFIED_SENDER, language, include_display_name=False)
    if sender is None:
        return ""
    return format_verified_sender_block(sender, language)


def lead_with_verified_sender(
    messages: list[Any], user_prompt: str, context: Any, language: Optional[str] = None, ablated: bool = False
) -> tuple[list[Any], str]:
    """Lead a conscience's user prompt with its sender block; unchanged when there is none.

    The user prompt is the last message. It is rebuilt with ``model_copy`` so
    the recorded prompt is exactly what the model read.
    """
    block = conscience_sender_block(context, language, ablated=ablated)
    if not block or not messages:
        return messages, user_prompt
    user_prompt = "\n\n".join((block, user_prompt))
    return [*messages[:-1], messages[-1].model_copy(update={"content": user_prompt})], user_prompt
