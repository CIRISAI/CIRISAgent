"""What a deferral tells the Wise Authority, and how much of it (CIRISAgent#1366 item 6).

A deferral reason and its context are what a WA reads to decide what was
contested. They used to be cut at 200 characters on the way to
``GET /v1/wa/deferrals``, so a max-depth auto-deferral reached the WA as
"Maximum action depth (5) reached" with nothing to validate. They are now kept
whole up to a large safety cap, and a cut says so.

The redactor is for the last draft an auto-deferral carries: a tool call's
arguments go to a human reviewer, so a value under a secret-looking key never
does.
"""

import json
from typing import List, Mapping, Optional, Sequence, Union

from ciris_engine.schemas.api.config_security import ConfigSecurity

# Large enough for a full drafted reply plus its rationale; small enough that a
# runaway value cannot bloat the WA listing. Same budget as the tool-approval
# detail (tool_approval.TOOL_APPROVAL_DETAIL_MAX_CHARS).
DEFERRAL_TEXT_MAX_CHARS = 4000

TRUNCATION_MARKER = "…[truncated]"

REDACTED = "[REDACTED]"

# ConfigSecurity's patterns need an affix ("api_key", "oauth_token"); a tool
# argument is often the bare word.
_SECRET_KEY_WORDS = ("password", "passwd", "secret", "token", "apikey", "api_key", "credential", "private_key")

# What a tool argument can be (ToolParams.parameters) and what it redacts to.
ArgumentValue = Union[str, int, float, bool, None, Sequence["ArgumentValue"], Mapping[str, "ArgumentValue"]]
RedactedValue = Union[str, int, float, bool, None, List["RedactedValue"], dict[str, "RedactedValue"]]


def clip_deferral_text(text: str, limit: int = DEFERRAL_TEXT_MAX_CHARS) -> str:
    """``text`` whole if it fits in ``limit`` characters, else cut with an explicit marker."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(TRUNCATION_MARKER))] + TRUNCATION_MARKER


def is_secret_key(key: str) -> bool:
    """True when an argument named ``key`` likely holds a secret."""
    lowered = key.lower()
    return ConfigSecurity.is_sensitive(key) or any(word in lowered for word in _SECRET_KEY_WORDS)


def redact_value(value: ArgumentValue, key: Optional[str] = None) -> RedactedValue:
    """``value`` with every entry under a secret-looking key replaced by ``[REDACTED]``, recursively."""
    if key is not None and is_secret_key(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def redacted_json(arguments: Mapping[str, ArgumentValue]) -> str:
    """Tool arguments as JSON, secrets redacted, for a human reviewer."""
    return json.dumps(redact_value(arguments), ensure_ascii=False, sort_keys=True, default=str)


__all__ = [
    "DEFERRAL_TEXT_MAX_CHARS",
    "REDACTED",
    "TRUNCATION_MARKER",
    "clip_deferral_text",
    "is_secret_key",
    "redact_value",
    "redacted_json",
]
