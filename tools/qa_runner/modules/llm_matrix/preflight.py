"""Credential liveness — answered before anything is graded.

Why this runs first
-------------------
A stale key produces the same HTTP 401 on every cell in a provider's column.
Graded naively that reads as "this provider answers 401 to everything", which
looks like a provider quirk and is nothing of the sort. Worse, the column's
*correct* cells (a bad model, a routing restriction) never get to happen,
because auth fails before the request is routed — so the sweep silently loses
the coverage it was run for, and reports confident nonsense instead.

So liveness is established up front and a column that cannot be trusted is
**skipped with a reason**, never failed.

Which call
----------
The preflight IS the baseline cell the matrix already runs: one chat completion
with ``max_tokens=1``. Not the ``/models`` listing, even though listing is
free — listing only proves the credential is *accepted*, and both Anthropic and
Together were observed on 2026-08-21 serving a full model list on an account
whose completions endpoint refused for lack of credit. A key that lists but
cannot complete is not live for our purposes, and the cheapest call that can
tell the difference is the one-token completion. It costs nothing extra because
the sweep was going to make it anyway.

Classification
--------------
``NO_CREDIT`` is kept strictly separate from ``EXPIRED_OR_REVOKED``. Re-issuing
a key with an exhausted balance changes nothing, and a re-provisioning list
that includes it sends someone to do the wrong work. The distinction is not
free to draw — providers disagree about how to signal it:

    Together    HTTP 402, code ``credit_limit``
    Anthropic   HTTP **400**, ``invalid_request_error``, "credit balance is too low"
    Google      HTTP **400** for a bad KEY ("Please pass a valid API key")

so the same 400 means "top up" at one provider and "re-issue" at another, and
only the message body separates them. That is exactly the ambiguity the
matrix's classifier findings are about; here it is resolved explicitly.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from .schemas import KeyLiveness, KeyStatus, LLMProbeOutcome

# Phrases that mean "the account has no money", not "the key is bad". Matched
# against the provider's own message because the status code alone is
# ambiguous — see the module docstring.
_NO_CREDIT_PHRASES = re.compile(
    r"credit balance|credit limit|out of credit|insufficient (funds|credit|balance|quota)"
    r"|billing|payment required|add credits|quota exceeded|exceeded your current quota",
    re.IGNORECASE,
)

# Phrases that mean the credential itself was rejected, whatever the status.
_BAD_KEY_PHRASES = re.compile(
    r"invalid api key|invalid x-api-key|api key is invalid|incorrect api key"
    r"|pass a valid api key|no auth credentials|unauthorized|user not found"
    r"|authentication_error|invalid_api_key|api key not valid",
    re.IGNORECASE,
)

_RATE_LIMIT_PHRASES = re.compile(r"rate limit|too many requests|slow down", re.IGNORECASE)


def classify_liveness(outcome: LLMProbeOutcome) -> Tuple[KeyLiveness, str]:
    """Turn a preflight outcome into a verdict plus the remedy for a human.

    The remedy string is written to be actionable on its own — it ends up in
    the operator-facing "keys needing re-provisioning" section, where the
    reader may have no other context.
    """
    if outcome.succeeded:
        return KeyLiveness.LIVE, "None — the credential completed a request."

    message = outcome.provider_error_message or outcome.exception_str or ""
    status = outcome.http_status

    # Message first, status second. The message is the only thing that
    # separates Anthropic's out-of-credit 400 from Google's bad-key 400.
    if _NO_CREDIT_PHRASES.search(message):
        return (
            KeyLiveness.NO_CREDIT,
            "Top up the account balance. Do NOT re-issue the key — it is valid; the account is out of funds.",
        )
    if _BAD_KEY_PHRASES.search(message):
        return KeyLiveness.EXPIRED_OR_REVOKED, "Re-issue the key at the provider and overwrite the key file."
    if _RATE_LIMIT_PHRASES.search(message):
        return KeyLiveness.RATE_LIMITED, "Transient — wait and re-run. Nothing to re-provision."

    if status == 401:
        return KeyLiveness.EXPIRED_OR_REVOKED, "Re-issue the key at the provider and overwrite the key file."
    if status == 402:
        return (
            KeyLiveness.NO_CREDIT,
            "Top up the account balance. Do NOT re-issue the key — it is valid; the account is out of funds.",
        )
    if status == 429:
        return KeyLiveness.RATE_LIMITED, "Transient — wait and re-run. Nothing to re-provision."
    if status == 403:
        # The openai/anthropic SDKs both send a User-Agent, so the Cloudflare
        # "error code: 1010" bot rejection that bit modules/mobile/llm_preflight.py
        # should not appear here. A 403 that does appear is an entitlement
        # decision about the model, not a statement about the key.
        return (
            KeyLiveness.OTHER,
            "Access denied for this model, not a credential failure. Check the account's model entitlements.",
        )
    if status == 404:
        # The credential got far enough for the provider to route the request
        # and reject the MODEL. The key works; our probe model does not.
        return (
            KeyLiveness.OTHER,
            "Credential accepted — the provider rejected the preflight MODEL, not the key. The model named in "
            "dimensions.py's cheap_model for this provider is probably decommissioned; update it.",
        )
    if status is None:
        return (
            KeyLiveness.OTHER,
            "No HTTP response at all — DNS, TLS, proxy or no network. Re-run before concluding anything.",
        )
    return KeyLiveness.OTHER, f"Unexpected HTTP {status}; the provider's message above is authoritative."


def build_status(
    provider: str,
    key_file: str,
    outcome: Optional[LLMProbeOutcome],
    key_present: bool,
) -> KeyStatus:
    """Assemble the recordable verdict. Never touches the credential value."""
    if not key_present:
        return KeyStatus(
            provider=provider,
            key_file=key_file,
            liveness=KeyLiveness.MISSING,
            http_status=None,
            provider_message=None,
            remedy=f"No key file at {key_file}. Provision one, or pass -p to exclude this provider.",
        )
    if outcome is None:
        return KeyStatus(
            provider=provider,
            key_file=key_file,
            liveness=KeyLiveness.NOT_PROBED,
            http_status=None,
            provider_message=None,
            remedy="Not probed (dry run makes no network calls).",
        )

    liveness, remedy = classify_liveness(outcome)
    return KeyStatus(
        provider=provider,
        key_file=key_file,
        liveness=liveness,
        http_status=outcome.http_status,
        # Already redacted at capture time in probes.py.
        provider_message=outcome.provider_error_message or outcome.exception_str,
        remedy=remedy,
    )


def skip_reason(status: KeyStatus) -> str:
    """The ``skipped_reason`` recorded on cells this credential cannot support."""
    detail = f"HTTP {status.http_status}" if status.http_status is not None else "no HTTP response"
    return (
        f"key at {status.key_file} is not live ({status.liveness.value}, {detail}) — "
        f"cell skipped, not failed. {status.remedy}"
    )


__all__ = ["build_status", "classify_liveness", "skip_reason"]
