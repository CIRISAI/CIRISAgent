"""Resolved enabled-tool set for envelope issuance (CIRISAgent#938, Phase 1).

"Every tool this deployment enabled is granted" is the correct default grant —
it follows from what is knowable at task creation. What matters is *how it is
written down*: as the resolved, explicitly enumerated list of tool names the
registry actually offers, not as a wildcard. An enumerated set that happens to
be complete is auditable and diffable; ``allow: ["*"]`` is neither.

Resolution goes through ``ToolBus.get_all_tool_info()`` because that is the
method that **aggregates across every registered tool service**.
``get_available_tools()`` resolves a single provider and would silently produce
an envelope that grants one adapter's tools and no others.

Results are cached with a short TTL so issuance does not sweep the registry on
every task.

Cold-cache behaviour is deliberately fail-closed: if the registry has never
been observed, :func:`cached_enabled_tools` returns ``None`` and the issuer
mints an envelope with an **empty** grant, logging a warning. Under Phase 1
nothing enforces, so this is inert; under Phase 2 it would deny. That is a real
operational risk and it is called out in ``FSD/TASK_ENVELOPE.md``: Phase 2 must
not go live until priming is guaranteed at runtime bootstrap.
"""

from __future__ import annotations

import logging
import time
from typing import Any, FrozenSet, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 60.0
"""How long a resolved enabled-tool set is reused before the registry is swept
again. Adapters register their tool services at startup and rarely afterwards,
so a minute keeps issuance cheap without letting a newly-registered adapter go
unnoticed for long."""


@runtime_checkable
class ToolNameSource(Protocol):
    """Anything that can enumerate every tool this deployment has enabled.

    ``ToolBus`` satisfies this; tests can supply a stub without constructing a
    service registry.
    """

    async def get_all_tool_info(self, handler_name: str = "default") -> List[Any]:  # pragma: no cover - protocol
        ...


_CACHED_TOOLS: Optional[FrozenSet[str]] = None
_CACHED_AT: float = 0.0
_REGISTERED_SOURCE: Optional[ToolNameSource] = None


def register_tool_name_source(source: ToolNameSource) -> None:
    """Register the live tool registry as the resolution source.

    Called by ``ToolBus.__init__`` so any issuance site can resolve without
    being handed a bus explicitly.
    """
    global _REGISTERED_SOURCE
    _REGISTERED_SOURCE = source


def _cache_is_fresh(ttl: float) -> bool:
    return _CACHED_TOOLS is not None and (time.monotonic() - _CACHED_AT) < ttl


async def prime_enabled_tools(
    source: Optional[ToolNameSource] = None,
    *,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
    force: bool = False,
) -> FrozenSet[str]:
    """Resolve and cache the enabled tool names. Returns the resolved set.

    Reuses a cache entry younger than ``ttl_seconds`` unless ``force``. On
    failure the previous cache is kept — a transient registry error must not
    silently shrink every subsequent envelope — and an empty set is returned
    only when nothing has ever been resolved.
    """
    global _CACHED_TOOLS, _CACHED_AT

    if not force and _cache_is_fresh(ttl_seconds):
        assert _CACHED_TOOLS is not None  # narrowed by _cache_is_fresh
        return _CACHED_TOOLS

    src = source or _REGISTERED_SOURCE
    if src is None:
        logger.warning(
            "TaskEnvelope: no tool-name source registered; enabled-tool set cannot be resolved. "
            "Envelopes issued now will carry an empty grant."
        )
        return _CACHED_TOOLS if _CACHED_TOOLS is not None else frozenset()

    try:
        infos = await src.get_all_tool_info()
    except Exception as exc:
        logger.warning("TaskEnvelope: failed to resolve enabled tools from registry: %s", exc)
        return _CACHED_TOOLS if _CACHED_TOOLS is not None else frozenset()

    names = []
    for info in infos or []:
        name = getattr(info, "name", None) or (info if isinstance(info, str) else None)
        if name and str(name).strip():
            names.append(str(name))
    resolved = frozenset(names)

    if not resolved:
        # An empty sweep is far more likely to be "adapters have not registered
        # yet" than "this deployment enabled nothing". Keep whatever we had.
        logger.warning(
            "TaskEnvelope: tool registry reported zero tools; keeping the previously resolved set (%s tools).",
            len(_CACHED_TOOLS) if _CACHED_TOOLS is not None else 0,
        )
        return _CACHED_TOOLS if _CACHED_TOOLS is not None else frozenset()

    if resolved != _CACHED_TOOLS:
        logger.info(
            "TaskEnvelope: resolved enabled-tool set (%d tools): %s",
            len(resolved),
            ", ".join(sorted(resolved)),
        )
    _CACHED_TOOLS = resolved
    _CACHED_AT = time.monotonic()
    return resolved


def cached_enabled_tools() -> Optional[FrozenSet[str]]:
    """The last resolved enabled-tool set, or ``None`` if never resolved."""
    return _CACHED_TOOLS


def reset_enabled_tools_cache() -> None:
    """Clear cache and registered source. For tests and runtime teardown."""
    global _CACHED_TOOLS, _CACHED_AT, _REGISTERED_SOURCE
    _CACHED_TOOLS = None
    _CACHED_AT = 0.0
    _REGISTERED_SOURCE = None


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "ToolNameSource",
    "cached_enabled_tools",
    "prime_enabled_tools",
    "register_tool_name_source",
    "reset_enabled_tools_cache",
]
