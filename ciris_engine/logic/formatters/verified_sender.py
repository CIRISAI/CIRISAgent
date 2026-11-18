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
from typing import Any, Optional

from ciris_engine.schemas.runtime.models import VerifiedSender

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

# A display name is attacker-chosen text placed inside a system-built block.
# Collapse anything that could break the block's layout (newlines, control
# characters, a fake "===" banner) and bound the length.
_UNSAFE = re.compile(r"[\x00-\x1f\x7f  ]+")
_BANNER = re.compile(r"={2,}")
_MAX_LEN = 64


def _inline(value: str) -> str:
    text = _BANNER.sub("=", _UNSAFE.sub(" ", value)).strip()
    return text if len(text) <= _MAX_LEN else text[: _MAX_LEN - 1] + "…"


def verified_sender_of(context: Any) -> Optional[VerifiedSender]:
    """The verified sender a task, task context, processing context or conscience context carries.

    Follows the same paths as ``wa_authorization_of``: the record itself,
    ``.verified_sender`` (a TaskContext), ``.context.verified_sender`` (a
    Task), ``.initial_task_context.verified_sender`` (a processing context) and
    ``.task.context.verified_sender``. Dicts are accepted at every step.
    """
    if context is None:
        return None
    if isinstance(context, VerifiedSender):
        return context
    for path in (
        ("verified_sender",),
        ("context", "verified_sender"),
        ("initial_task_context", "verified_sender"),
        ("task", "context", "verified_sender"),
    ):
        value: Any = context
        for attr in path:
            value = value.get(attr) if isinstance(value, dict) else getattr(value, attr, None)
            if value is None:
                break
        if isinstance(value, VerifiedSender):
            return value
        if isinstance(value, dict):
            try:
                return VerifiedSender.model_validate(value)
            except Exception:
                return None
    return None


def format_verified_sender_block(sender: Optional[VerifiedSender], language: Optional[str] = None) -> str:
    """The VERIFIED SENDER block; empty when there is no verified sender."""
    if sender is None:
        return ""
    from ciris_engine.logic.utils.localization import get_preferred_language, get_string

    lang = language or get_preferred_language()
    lines = [
        get_string(lang, "prompts.verified_sender.header"),
        get_string(lang, "prompts.verified_sender.id", user_id=_inline(sender.user_id or "unknown")),
        (
            get_string(lang, "prompts.verified_sender.role", role=sender.role.value)
            if sender.role is not None
            else get_string(lang, "prompts.verified_sender.role_not_verified")
        ),
        get_string(lang, "prompts.verified_sender.source", source=_inline(sender.source)),
    ]
    if sender.self_chosen_display_name:
        lines.append(
            get_string(
                lang,
                "prompts.verified_sender.display_name",
                display_name=_inline(sender.self_chosen_display_name),
            )
        )
    lines.append(get_string(lang, "prompts.verified_sender.wa_prefix"))
    lines.append(get_string(lang, "prompts.verified_sender.footer"))
    return "\n".join(lines)


def verified_sender_block_of(context: Any, language: Optional[str] = None) -> str:
    """``format_verified_sender_block(verified_sender_of(context))``: the block for a task or context."""
    return format_verified_sender_block(verified_sender_of(context), language)
