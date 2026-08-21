"""Credential redaction.

Every string that a provider hands back — error messages, raw bodies,
``str(exception)`` — is passed through :class:`Redactor` at capture time,
before it is stored in an ``LLMProbeOutcome``. Redaction at capture, not at
render, is deliberate: it means no code path exists that can put key material
into the report file, the console, or a fixture, even by accident.

Two layers:

1. **Exact.** Every key value actually loaded this run is registered and
   replaced wherever it appears, including its URL-encoded and JSON-escaped
   forms. This is the layer that matters.
2. **Heuristic.** Anything shaped like a provider token (``sk-``, ``sk-ant-``,
   ``sk-or-v1-``, ``gsk_``, ``AIza``, long hex runs) is masked even if it was
   never registered — this catches a key echoed back by a provider in a form
   we did not send, and a key belonging to some other account entirely.

The heuristic layer also drives :func:`contains_credential`, which the matrix
uses to raise a ``CREDENTIAL_ECHOED`` finding when a provider reflects key
material back in an error body.
"""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import quote

MASK = "<redacted>"

# Shapes of the tokens the six matrix providers issue. Ordered longest-prefix
# first so `sk-ant-` and `sk-or-v1-` are not eaten by the bare `sk-` rule.
_TOKEN_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-or-v1-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"gsk_[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{30,}"),
    # Together issues bare 64-char hex tokens with no prefix at all.
    re.compile(r"\b[0-9a-f]{64}\b"),
    # Bearer headers, whatever the token shape.
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)\S+"),
    re.compile(r"(?i)(x-api-key\s*[:=]\s*)\S+"),
]

# Not credentials, but account identifiers that providers volunteer inside
# error bodies — OpenRouter returns {"user_id": "user_…"} on a 400. Those
# bodies reach the user verbatim through the classifier's raw-error branch and
# get written into this report, so they are masked here too. Kept separate from
# _TOKEN_PATTERNS because echoing one back is not a credential leak.
_IDENTIFIER_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"""(?i)(['"]?user_id['"]?\s*[:=]\s*['"])[^'"]+(['"])"""),
    re.compile(r"""(?i)(['"]?organization['"]?\s*[:=]\s*['"])org-[^'"]+(['"])"""),
]

# The shortest key fragment worth masking. Below this an "exact" match is more
# likely to be a coincidental substring of ordinary prose than key material.
_MIN_EXACT_LEN = 12


class Redactor:
    """Masks registered secrets and token-shaped substrings."""

    def __init__(self) -> None:
        self._secrets: List[str] = []

    def register(self, secret: Optional[str]) -> None:
        """Register a secret value for exact masking.

        Also registers the forms a transport layer might have rewritten it
        into: URL-quoted, and JSON-escaped. Short or empty values are ignored
        so a blank key from the ABSENT injection cannot mask the whole report.
        """
        if not secret:
            return
        candidates = {secret, secret.strip(), quote(secret, safe=""), secret.replace("/", "\\/")}
        for candidate in candidates:
            if len(candidate) >= _MIN_EXACT_LEN and candidate not in self._secrets:
                self._secrets.append(candidate)
        # Longest first: masking a prefix before its longer form would leave a
        # tail of the real secret behind.
        self._secrets.sort(key=len, reverse=True)

    def scrub(self, text: Optional[str]) -> Optional[str]:
        """Return ``text`` with all known and token-shaped secrets masked."""
        if text is None:
            return None
        out = text
        for secret in self._secrets:
            out = out.replace(secret, MASK)
        for pattern in _TOKEN_PATTERNS:
            if pattern.groups:
                out = pattern.sub(lambda m: f"{m.group(1)}{MASK}", out)
            else:
                out = pattern.sub(MASK, out)
        for pattern in _IDENTIFIER_PATTERNS:
            out = pattern.sub(lambda m: f"{m.group(1)}{MASK}{m.group(2)}", out)
        return out

    def contains_credential(self, text: Optional[str]) -> bool:
        """True when ``text`` holds a registered secret or a token-shaped run.

        Called on the RAW body before scrubbing, to decide whether a provider
        echoed credential material back at us.
        """
        if not text:
            return False
        if any(secret in text for secret in self._secrets):
            return True
        return any(pattern.search(text) for pattern in _TOKEN_PATTERNS)

    def excerpt(self, text: Optional[str], limit: int = 600) -> Optional[str]:
        """Scrub, then truncate. Never returns the whole of a large body."""
        scrubbed = self.scrub(text)
        if scrubbed is None:
            return None
        scrubbed = scrubbed.strip()
        if len(scrubbed) <= limit:
            return scrubbed
        return scrubbed[:limit] + f"… [{len(scrubbed) - limit} more chars]"


__all__ = ["MASK", "Redactor"]
