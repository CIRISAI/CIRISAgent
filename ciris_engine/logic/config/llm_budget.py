"""
The one place that decides local-vs-remote and which time budget applies
(CIRISAgent#1186). Every timeout and attempt count on the LLM path reads from
`active_budget()`; nothing else classifies providers.

Precedence for each knob: explicit env var > profile value. Precedence for
the profile: `CIRIS_LLM_BUDGET_PROFILE` > declared provider id > base URL.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from typing import Callable, Optional
from urllib.parse import urlparse

from ciris_engine.logic.config.env_utils import get_env_var
from ciris_engine.schemas.config.llm_budget import PROFILES, LLMBudgetProfile, ProviderClass

logger = logging.getLogger(__name__)

#: Provider ids the setup wizard and settings screens write for models that
#: run on the user's own hardware. A declaration beats any URL guess.
LOCAL_PROVIDER_IDS = frozenset({"local", "local_inference", "localai", "mobile_local", "ollama", "lmstudio"})

#: Hosted APIs. Checked before any local heuristic, so a cloud URL on an odd
#: port is never mistaken for a box on the desk.
CLOUD_HOST_MARKERS = (
    "ciris.ai",
    "ciris-services",
    "openrouter.ai",
    "together.xyz",
    "openai.com",
    "anthropic.com",
    "googleapis.com",
    "groq.com",
    "deepinfra.com",
    "mistral.ai",
    "fireworks.ai",
)

#: Ports that local inference servers listen on by default (Ollama, LM Studio,
#: llama.cpp / vLLM defaults). Used only when the host itself is ambiguous.
LOCAL_SERVER_PORTS = frozenset({11434, 1234, 8000, 8080})

_CGNAT = ipaddress.ip_network("100.64.0.0/10")  # Tailscale and other overlay networks


def _host_is_local(host: str) -> bool:
    if host in ("localhost", "0.0.0.0") or host.endswith(".local") or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip in _CGNAT


def classify_provider(provider_id: Optional[str] = None, base_url: Optional[str] = None) -> ProviderClass:
    """LOCAL if the model runs on hardware the user controls, else REMOTE.

    An explicit provider id wins; otherwise the base URL's host decides —
    parsed, not substring-matched (``"10."`` must not match ``api.v10.example``).
    No URL and no declaration means a hosted SDK default: REMOTE.
    """
    if provider_id and provider_id.strip().lower() in LOCAL_PROVIDER_IDS:
        return ProviderClass.LOCAL
    if not base_url:
        return ProviderClass.REMOTE
    lowered = base_url.lower()
    if any(marker in lowered for marker in CLOUD_HOST_MARKERS):
        return ProviderClass.REMOTE
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    host = (parsed.hostname or "").lower()
    if _host_is_local(host):
        return ProviderClass.LOCAL
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port in LOCAL_SERVER_PORTS and "." not in host:
        return ProviderClass.LOCAL  # a bare LAN hostname such as http://gpu-box:11434
    return ProviderClass.REMOTE


def _env_float(name: str, fallback: float) -> float:
    raw = get_env_var(name)
    if not raw:
        return fallback
    try:
        value = float(raw)
    except ValueError:
        logger.warning("[LLM_BUDGET] ignoring %s=%r: not a number", name, raw)
        return fallback
    return value if value > 0 else fallback


def _env_int(name: str, fallback: int) -> int:
    raw = get_env_var(name)
    if not raw:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        logger.warning("[LLM_BUDGET] ignoring %s=%r: not an integer", name, raw)
        return fallback
    return value if value >= 1 else fallback


def resolve_budget(provider_id: Optional[str] = None, base_url: Optional[str] = None) -> LLMBudgetProfile:
    """The profile for this provider, with any explicit env overrides applied.

    Overrides that would break nesting are repaired, not rejected: an
    operator raising CIRIS_LLM_TIMEOUT past the conscience per-try gets the
    per-try raised to match, with a warning, instead of an agent that will
    not boot.
    """
    forced = (get_env_var("CIRIS_LLM_BUDGET_PROFILE") or "").strip().lower()
    if forced in (ProviderClass.LOCAL.value, ProviderClass.REMOTE.value):
        provider_class = ProviderClass(forced)
    else:
        provider_class = classify_provider(provider_id, base_url)
    base = PROFILES[provider_class]

    http = _env_float("CIRIS_LLM_TIMEOUT", base.llm_http_timeout_s)
    dma_try = _env_float("CIRIS_DMA_TIMEOUT", base.dma_per_try_s)
    consc_try = _env_float("CIRIS_CONSCIENCE_TIMEOUT", base.conscience_per_try_s)
    interact = _env_float("CIRIS_API_INTERACTION_TIMEOUT", base.interact_deadline_s)
    thought = _env_float("CIRIS_THOUGHT_BUDGET", base.thought_budget_s)

    if http > consc_try or http > dma_try:
        logger.warning(
            "[LLM_BUDGET] LLM HTTP timeout %.0fs exceeds a stage per-try (conscience %.0fs, DMA %.0fs); "
            "raising the per-try to match so the inner timeout can still fire",
            http,
            consc_try,
            dma_try,
        )
        consc_try = max(consc_try, http)
        dma_try = max(dma_try, http)
    if thought > interact:
        thought = interact

    return base.model_copy(
        update={
            "llm_http_timeout_s": http,
            "dma_per_try_s": dma_try,
            "dma_attempts": _env_int("CIRIS_DMA_ATTEMPTS", base.dma_attempts),
            "conscience_per_try_s": consc_try,
            "conscience_attempts": _env_int("CIRIS_CONSCIENCE_ATTEMPTS", base.conscience_attempts),
            "thought_budget_s": thought,
            "interact_deadline_s": interact,
        }
    )


def primary_provider_declaration() -> tuple[Optional[str], Optional[str]]:
    """(provider id, base URL) of the primary provider as configured in env."""
    provider_id = get_env_var("CIRIS_LLM_PROVIDER") or get_env_var("LLM_PROVIDER")
    base_url = get_env_var("OPENAI_API_BASE") or get_env_var("CIRIS_OPENAI_API_BASE")
    return provider_id, base_url


def active_budget() -> LLMBudgetProfile:
    """The budget for the primary provider. Cheap; call it where the value is used."""
    provider_id, base_url = primary_provider_declaration()
    return resolve_budget(provider_id, base_url)


#: The shortest attempt worth starting against a thought deadline. An honest
#: call answers in 2-14s (2026-09-04 RCA; the 87K-token veto ~9s), so a try
#: with less than ~10s left is mostly a request we will cancel -- it spends
#: provider capacity and returns nothing. When the per-try itself is shorter
#: (tests, an operator override) the per-try is the floor instead.
MIN_USEFUL_ATTEMPT_S = 10.0


def attempt_timeout(per_try_s: float, deadline: Optional["Deadline"]) -> Optional[float]:
    """Timeout for the next attempt, or None when the deadline cannot afford one.

    No deadline -> the static per-try, unchanged. Shared by every stage that
    retries under the thought deadline (DMAs, consciences, second-pass DMAs).
    """
    if deadline is None:
        return per_try_s
    if not deadline.affords(min(per_try_s, MIN_USEFUL_ATTEMPT_S)):
        return None
    return deadline.clamp(per_try_s)


class Deadline:
    """An absolute point in time a piece of work must finish by.

    Set once, high in the stack; stages ask for the remainder instead of
    inventing their own budget (Google SRE: deadline propagation).
    """

    __slots__ = ("_at", "_clock")

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._at = clock() + seconds

    def remaining(self) -> float:
        return max(0.0, self._at - self._clock())

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def clamp(self, per_try_s: float) -> float:
        """The per-try to use now: never longer than what is left."""
        return min(per_try_s, self.remaining())

    def affords(self, seconds: float) -> bool:
        """Is there time left for an attempt that needs `seconds` to be useful?"""
        return self.remaining() >= seconds
