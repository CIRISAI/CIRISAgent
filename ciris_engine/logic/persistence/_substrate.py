"""Single substrate seam — the agent's one import boundary to the fabric node.

#896 / CIRISServer ``FSD/CIRISAGENT_ADOPTION.md``: the agent is becoming
``ciris-server wheel + brain``. Every substrate import (the persist ``Engine``
and the edge runtime constructor) flows through this module so the wheel
boundary flips in exactly ONE place — the consolidated ``ciris_server`` abi3
wheel (persist + edge + lens re-hosted) vs the standalone ``ciris_persist`` /
``ciris_edge`` wheels.

Using the one wheel matters beyond convenience: it gives the whole process a
single PyO3 type registry, so the persist ``Engine`` handed to
``init_edge_runtime`` is the *same* registered Rust type both halves see. With
two separate wheels they were distinct PyClasses and Edge refused with
``'Engine' object is not an instance of 'Engine'`` (CIRISEdge#22 cohabitation).

Prefer ``ciris_server``; fall back to the standalone wheels for partial dev
environments that do not have the one wheel installed.
"""

from __future__ import annotations

try:
    from ciris_server import Engine, NotFound, reset_engine  # type: ignore[import-not-found, import-untyped, unused-ignore]
    from ciris_server.edge import init_edge_runtime  # type: ignore[import-not-found, import-untyped, unused-ignore]

    SUBSTRATE_SOURCE = "ciris_server"
except ImportError:  # pragma: no cover - dev env without the consolidated wheel
    from ciris_persist import Engine, NotFound, reset_engine  # type: ignore[import-not-found, import-untyped, unused-ignore]

    try:
        from ciris_edge.ciris_edge import init_edge_runtime  # type: ignore[import-not-found, import-untyped, unused-ignore]
    except ImportError:  # edge wheel absent — edge_runtime raises its own RuntimeError
        init_edge_runtime = None  # type: ignore[assignment, unused-ignore]

    SUBSTRATE_SOURCE = "ciris_persist"

# #937 — the Rust `tracing` subscriber installer. Without it every substrate
# log event is discarded at the source, which is why persist's "migration
# phase begin (advisory lock acquired)" never appeared during the 15-minute
# boot hang. Optional: older wheels and the standalone ciris_persist build
# may not expose it, and `utils/substrate_logging.py` degrades to a warning.
try:
    from ciris_server import init_tracing  # type: ignore[import-not-found, import-untyped, unused-ignore]
except ImportError:  # pragma: no cover - substrate without the entry point
    try:
        from ciris_persist import init_tracing  # type: ignore[import-not-found, import-untyped, unused-ignore]
    except ImportError:
        init_tracing = None  # type: ignore[assignment, unused-ignore]

__all__ = [
    "Engine",
    "NotFound",
    "reset_engine",
    "init_edge_runtime",
    "init_tracing",
    "SUBSTRATE_SOURCE",
]
