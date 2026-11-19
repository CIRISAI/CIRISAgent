"""Provider spending-limit refusals (HTTP 402/403): classification and retry policy.

CIRISAgent#1366 item 20. OpenRouter answers 402 for FOUR different situations,
and they need four different responses:

==============================  ===========================  =======================================
error.metadata.limit_source     reason                       response
==============================  ===========================  =======================================
openrouter_in_flight_budget     in_flight_budget_exhausted   transient: wait (Retry-After if sent)
                                                             and retry, the ONLY retryable case
openrouter_credits              weight_exceeds_budget        this one request is bigger than the
                                                             whole budget: surface, no retry
openrouter_credits              (anything else)              balance cannot cover it: billing
openrouter_key_limit            (402 or 403)                 the key's own limit: surface with its
                                                             reset; "key limit", not "add credits"
==============================  ===========================  =======================================

OpenRouter's documentation says to branch on ``limit_source`` and never on the
hint text (openrouter.ai/docs/api-reference/limits), so nothing here reads the
message prose. A 402 that carries no ``limit_source`` is not classified here and
keeps today's handling (``insufficient_quota``, no retry).

Every 402 used to read as ``insufficient_quota``: the call failed with no retry,
and one transient in-flight refusal ruined a whole RATCHET Market 4 episode.
The cause of the refusals was ours too: OpenRouter reserves
``input + max_tokens`` x price for every request in flight, and every DMA and
conscience asks for max_tokens=8192 while its measured completions are 60-240
tokens (kept at 8192 by ruling; the retry and pause below absorb the refusals).
"""

from __future__ import annotations

import hashlib
import hmac
import random
import secrets
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field

#: limit_source values OpenRouter documents for a spending refusal.
LIMIT_SOURCE_IN_FLIGHT = "openrouter_in_flight_budget"
LIMIT_SOURCE_CREDITS = "openrouter_credits"
LIMIT_SOURCE_KEY_LIMIT = "openrouter_key_limit"
REASON_WEIGHT_EXCEEDS_BUDGET = "weight_exceeds_budget"

#: In-flight budget backoff: full-jitter exponential backoff with the provider's
#: Retry-After as the floor. Each wait is capped, and all waits for one call are
#: bounded in total (and, tighter, by the caller's deadline -- see the LLM bus).
IN_FLIGHT_BACKOFF_BASE_S = 2.0
IN_FLIGHT_BACKOFF_CAP_S = 60.0
IN_FLIGHT_TOTAL_WAIT_S = 300.0
#: Floor on a wait the provider gave no Retry-After for: costs are still settling
#: the instant after a refusal, so a retry within milliseconds is a certain one.
IN_FLIGHT_MIN_WAIT_S = 2.0
#: Callers released from a shared pause are spread over up to this many seconds
#: so they do not all hit the provider in the same instant.
IN_FLIGHT_RELEASE_SPREAD_S = 2.0

class ProviderLimitFaultCode(str, Enum):
    """The structured fault a spending-limit refusal maps to.

    The values are the slugs the health surface and the failed-task notice key
    on (``last_fault_code``); ``insufficient_quota`` is the pre-existing one.
    """

    IN_FLIGHT_BUDGET = "in_flight_budget"
    REQUEST_TOO_LARGE = "request_too_large"
    INSUFFICIENT_QUOTA = "insufficient_quota"
    KEY_LIMIT = "key_limit"
    BUDGET_LIMIT = "budget_limit"


class ProviderLimitFault(BaseModel):
    """One provider spending-limit refusal, read from its structured body."""

    model_config = ConfigDict(frozen=True)

    code: ProviderLimitFaultCode
    http_status: int = Field(..., description="402 or 403")
    limit_source: str = Field(..., description="error.metadata.limit_source, verbatim")
    reason: Optional[str] = Field(None, description="error.metadata.reason, verbatim")
    retry_after_s: Optional[float] = Field(None, ge=0, description="Retry-After header, in seconds, when sent")
    limit_reset: Optional[str] = Field(
        None, description="When the limit resets (metadata limit_reset / resets_at), when the provider said"
    )

    @property
    def retryable(self) -> bool:
        """Only the in-flight budget is worth waiting for: it settles as requests finish."""
        return self.code is ProviderLimitFaultCode.IN_FLIGHT_BUDGET

    def describe(self) -> str:
        """The operator-facing sentence. Its first clause is what health shows.

        The words matter downstream: the DMA / conscience retry rule
        (``conscience.transport._UNFUNDED_MARKERS``) gives no further attempt to
        a failure that says "http 402" or "credit limit exceeded", which is right
        for every refusal here EXCEPT the in-flight budget -- so that one alone
        names no status code. None of them may say "rate limit", "429",
        "timeout" or "token limit", which other classifiers read.
        """
        src = f"limit_source={self.limit_source}" + (f", reason={self.reason}" if self.reason else "")
        reset = f" Resets: {self.limit_reset}." if self.limit_reset else ""
        if self.code is ProviderLimitFaultCode.IN_FLIGHT_BUDGET:
            return (
                f"OpenRouter in-flight spending budget is full ({src}): transient, it frees as "
                f"running requests settle."
            )
        if self.code is ProviderLimitFaultCode.REQUEST_TOO_LARGE:
            # Still says "HTTP 402": the DMA must not retry it unchanged. The
            # budget is a share of the balance, so credits are a remedy too.
            return (
                f"HTTP {self.http_status}: this request is too large for the in-flight budget ({src}): "
                f"lower max_tokens or the prompt, or add credits."
            )
        if self.code is ProviderLimitFaultCode.KEY_LIMIT:
            return (
                f"OpenRouter key limit reached: the API key's credit limit exceeded "
                f"(HTTP {self.http_status}, {src}).{reset} Raise the key's limit or wait for the reset; "
                f"adding account credit will not help."
            )
        if self.code is ProviderLimitFaultCode.BUDGET_LIMIT:
            return (
                f"OpenRouter budget limit reached (HTTP {self.http_status}, {src}): credit limit exceeded "
                f"for this budget.{reset}"
            )
        return f"HTTP {self.http_status}: OpenRouter credits cannot cover this request ({src}). Add credits."


class ProviderLimitError(RuntimeError):
    """A provider spending-limit refusal, categorized. ``fault`` says which one."""

    def __init__(self, fault: ProviderLimitFault) -> None:
        super().__init__(fault.describe())
        self.fault = fault


def _code_for(limit_source: str, reason: Optional[str]) -> Optional[ProviderLimitFaultCode]:
    if limit_source == LIMIT_SOURCE_IN_FLIGHT:
        return ProviderLimitFaultCode.IN_FLIGHT_BUDGET
    if limit_source == LIMIT_SOURCE_CREDITS:
        if reason == REASON_WEIGHT_EXCEEDS_BUDGET:
            return ProviderLimitFaultCode.REQUEST_TOO_LARGE
        return ProviderLimitFaultCode.INSUFFICIENT_QUOTA
    if limit_source == LIMIT_SOURCE_KEY_LIMIT:
        return ProviderLimitFaultCode.KEY_LIMIT
    if limit_source.startswith("openrouter_") and limit_source.endswith("_budget"):
        # openrouter_guardrail_budget / openrouter_workspace_budget (403): the
        # wait is "usually hours or days", no Retry-After. Not retryable.
        return ProviderLimitFaultCode.BUDGET_LIMIT
    return None


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Retry-After as seconds: delta-seconds or an HTTP-date. None when absent or unreadable."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        from datetime import datetime, timezone

        when = parsedate_to_datetime(text)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, IndexError):
        return None


def _error_object(body: object) -> Optional[Mapping[str, object]]:
    """The inner error object, from either the envelope or the openai SDK's unwrapped body."""
    if isinstance(body, list) and body and isinstance(body[0], Mapping):
        body = body[0]
    if not isinstance(body, Mapping):
        return None
    inner = body.get("error")
    if isinstance(inner, Mapping):
        return inner
    return body


def _str_or_none(value: object) -> Optional[str]:
    return str(value) if value is not None and str(value).strip() else None


def provider_limit_fault(error: BaseException) -> Optional[ProviderLimitFault]:
    """The spending-limit fault anywhere in ``error``'s cause chain, or None.

    Reads only structure: the HTTP status, ``error.metadata.limit_source`` and
    ``reason``, and the Retry-After header. Never the message.
    """
    seen: set[int] = set()
    cur: Optional[BaseException] = error
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ProviderLimitError):
            return cur.fault
        status = getattr(cur, "status_code", None)
        if status in (402, 403):
            err = _error_object(getattr(cur, "body", None))
            metadata = err.get("metadata") if err is not None else None
            if isinstance(metadata, Mapping):
                limit_source = _str_or_none(metadata.get("limit_source"))
                reason = _str_or_none(metadata.get("reason"))
                code = _code_for(limit_source, reason) if limit_source else None
                if code is not None and limit_source is not None:
                    response = getattr(cur, "response", None)
                    headers = getattr(response, "headers", None)
                    retry_after = parse_retry_after(headers.get("retry-after")) if headers is not None else None
                    reset = _str_or_none(metadata.get("limit_reset")) or _str_or_none(metadata.get("resets_at"))
                    return ProviderLimitFault(
                        code=code,
                        http_status=int(status),
                        limit_source=limit_source,
                        reason=reason,
                        retry_after_s=retry_after,
                        limit_reset=reset,
                    )
        # Explicit causes only (`raise ... from e`). An unrelated error raised
        # while a refusal was being handled carries it as implicit __context__,
        # and must surface as itself, not be waited out as an in-flight refusal.
        cur = getattr(cur, "__cause__", None)
    return None


def budget_identity(base_url: Optional[str], api_key: Optional[str]) -> tuple[str, str]:
    """Who owns an in-flight budget: (base URL, per-process HMAC fingerprint of the API key).

    OpenRouter's in-flight budget belongs to the account/key, not to one
    registered service: replicas and differently-named services with the same
    key share it. The key itself is never returned, logged or stored -- only
    16 hex digits of a per-process HMAC, enough to tell keys apart.
    """
    url = (base_url or "").strip().rstrip("/").lower()
    key = (api_key or "").strip()
    return (url, _key_fingerprint(key) if key else "")


#: Per-process HMAC key. The fingerprint only has to tell keys apart inside this
#: process (it keys the LLM bus's in-flight pause), so it never needs to be stable
#: across processes, and nothing outside this process can recompute it.
_FINGERPRINT_KEY = secrets.token_bytes(32)


def _key_fingerprint(key: str) -> str:
    """16 hex digits of HMAC-SHA256 over the API key under a per-process random key."""
    return hmac.new(_FINGERPRINT_KEY, key.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def in_flight_backoff_s(attempt: int, retry_after_s: Optional[float]) -> float:
    """Wait before in-flight retry ``attempt`` (0-based).

    With a Retry-After: max(Retry-After, full jitter over [0, base * 2**attempt]).
    Retry-After is a FLOOR and is never shortened, even past the 60 s cap: the
    caller compares the result with the time it has and surfaces the refusal
    when it does not fit, rather than resending before the provider's time.

    Without one: equal jitter (half the ceiling plus up to half again), never
    under IN_FLIGHT_MIN_WAIT_S, capped at IN_FLIGHT_BACKOFF_CAP_S.

    ``attempt`` is the caller's choice of exponent: the LLM bus passes the
    larger of the call's own attempt and the account's consecutive refusals,
    so sustained pressure backs off for every caller, not only the one retrying.
    """
    ceiling = min(IN_FLIGHT_BACKOFF_CAP_S, IN_FLIGHT_BACKOFF_BASE_S * 2.0 ** min(max(0, attempt), 32))
    if retry_after_s is not None:
        return max(retry_after_s, random.uniform(0.0, ceiling))
    jittered = ceiling / 2.0 + random.uniform(0.0, ceiling / 2.0)
    return min(IN_FLIGHT_BACKOFF_CAP_S, max(IN_FLIGHT_MIN_WAIT_S, jittered))


__all__ = [
    "IN_FLIGHT_BACKOFF_BASE_S",
    "IN_FLIGHT_BACKOFF_CAP_S",
    "IN_FLIGHT_MIN_WAIT_S",
    "IN_FLIGHT_RELEASE_SPREAD_S",
    "IN_FLIGHT_TOTAL_WAIT_S",
    "ProviderLimitError",
    "ProviderLimitFault",
    "ProviderLimitFaultCode",
    "budget_identity",
    "in_flight_backoff_s",
    "parse_retry_after",
    "provider_limit_fault",
]
