#!/usr/bin/env python3
"""Back off on provider rate limits around the vendored pipeline's model calls.

AGENT-OWNED adapter (see ``localization/VENDORED.md``). Not vendored.

The sharded i18n lane (``.github/workflows/i18n-lane.yml``) runs up to 28
locale shards at once against one OpenRouter key. OpenRouter pre-authorizes
``max_tokens x output price`` before every call, so concurrent shards can see
**402** (the pre-authorizations add up past the balance) and **429** (rate
limit) where one sequential run never did. The vendored ``localize.py`` treats
every exception from ``call_model`` as "this rung is dead": the translate lane
escalates to the next rung, the reviewer marks the key UNREVIEWED, and repair
gives up. A transient 429 therefore turned into an escalation, a fail-closed
rejection, or a wasted expensive rung.

This module wraps ``localize.call_model`` -- a module attribute the vendored
functions look up at call time, the same hook pattern ``accord_localize.py``
uses -- so a transient status is retried in place with exponential backoff and
jitter (honouring ``Retry-After``). Anything else is re-raised unchanged, so the
vendored escalation and fail-closed behaviour are exactly as upstream.

Tunable by environment (all optional):

``LOCALIZE_BACKOFF_ATTEMPTS``   total attempts per call for 429 / 5xx (default 6)
``LOCALIZE_BACKOFF_402_ATTEMPTS`` total attempts for 402 (default 3): a 402 on a
                                genuinely empty balance is not transient, and
                                waiting ten minutes per call would turn a dead
                                key into a four-hour timeout instead of a failure
``LOCALIZE_BACKOFF_BASE``       first delay in seconds (default 20)
``LOCALIZE_BACKOFF_CAP``        longest single delay in seconds (default 300)

Entry point for ``TARGET=ui`` (``localization/run_lane.sh``)::

    python3 localization/lane_backoff.py --lane translate ...   # = localize.py, with backoff
"""

from __future__ import annotations

import os
import random
import re
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Optional, TypeVar

HERE = Path(__file__).resolve().parent

#: Statuses worth waiting out. 402 is here because of OpenRouter's
#: pre-authorization (see the module docstring); 529 is Anthropic "overloaded".
RETRY_STATUSES = frozenset({402, 408, 429, 500, 502, 503, 504, 529})

#: OpenRouter can answer HTTP 200 with ``{"error": {"code": 429, ...}}``, which
#: the vendored client raises as ``RuntimeError("openrouter: {...}")``.
_OPENROUTER_CODE = re.compile(r"^openrouter: .*?['\"]code['\"]:\s*(\d{3})")

T = TypeVar("T")


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, "") or default))
    except ValueError:
        return default


def status_of(exc: BaseException) -> Optional[int]:
    """The HTTP status an exception carries, if any.

    ``urllib.error.HTTPError.code`` (the OpenRouter path), ``status_code``
    (the Anthropic SDK's ``APIStatusError``), or the code inside an OpenRouter
    in-body error.
    """
    for attr in ("code", "status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    if isinstance(exc, RuntimeError):
        m = _OPENROUTER_CODE.match(str(exc))
        if m:
            return int(m.group(1))
    return None


def retry_after(exc: BaseException) -> Optional[float]:
    """Seconds from a ``Retry-After`` header, when the exception has one."""
    headers = getattr(exc, "headers", None)
    if headers is None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get("Retry-After") or headers.get("retry-after")
    except Exception:  # noqa: BLE001 - a header object we do not understand is no header
        return None
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None  # an HTTP-date; fall back to our own schedule


def with_backoff(
    fn: Callable[..., T],
    *,
    attempts: Optional[int] = None,
    attempts_402: Optional[int] = None,
    base: Optional[float] = None,
    cap: Optional[float] = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: Optional[random.Random] = None,
    log: Callable[[str], None] = print,
) -> Callable[..., T]:
    """``fn`` retried in place on a transient provider status."""
    n_any = attempts if attempts is not None else _env_int("LOCALIZE_BACKOFF_ATTEMPTS", 6)
    n_402 = attempts_402 if attempts_402 is not None else _env_int("LOCALIZE_BACKOFF_402_ATTEMPTS", 3)
    first = base if base is not None else _env_float("LOCALIZE_BACKOFF_BASE", 20.0)
    longest = cap if cap is not None else _env_float("LOCALIZE_BACKOFF_CAP", 300.0)
    jitter = rng or random.Random()

    def call(*args: Any, **kwargs: Any) -> T:
        attempt = 0
        while True:
            attempt += 1
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - classified below, re-raised unchanged
                status = status_of(exc)
                if status not in RETRY_STATUSES:
                    raise
                limit = min(n_402, n_any) if status == 402 else n_any
                if attempt >= limit:
                    raise
                delay = first * (2 ** (attempt - 1))
                delay = min(longest, delay * (0.75 + 0.5 * jitter.random()))  # jitter de-syncs the shards
                hinted = retry_after(exc)
                if hinted is not None:
                    delay = min(longest, max(delay, hinted))
                model = args[0] if args else kwargs.get("model", "?")
                log(f"[backoff] {model}: HTTP {status}, attempt {attempt}/{limit}; retrying in {delay:.0f}s")
                sleep(delay)

    call.__wrapped__ = fn  # type: ignore[attr-defined]
    call._lane_backoff = True  # type: ignore[attr-defined]
    return call


def install(L: ModuleType) -> None:
    """Wrap the vendored module's ``call_model`` once."""
    current = getattr(L, "call_model")
    if getattr(current, "_lane_backoff", False):
        return
    setattr(L, "call_model", with_backoff(current))


def main() -> int:
    """``localize.py``'s own CLI, with backoff installed (TARGET=ui)."""
    sys.path.insert(0, str(HERE))
    import localize  # noqa: E402  the vendored module, unmodified

    install(localize)
    rc: int = localize.main()
    return rc


if __name__ == "__main__":
    sys.exit(main())
