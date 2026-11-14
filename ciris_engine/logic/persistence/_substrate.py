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

One wheel only (2.22.0). The fallback to the standalone ``ciris_persist`` /
``ciris_edge`` wheels is gone: it could load persist and edge as two separate
native modules, the double load behind the lost-wakeup hang (CIRISEdge#988),
and ciris-server 0.5.247 confirmed ``Engine`` and ``init_edge_runtime`` import
from the one wheel as one ``.so``. A missing ``ciris_server`` is an install
error and fails at import, loudly, instead of degrading.
"""

from __future__ import annotations

from ciris_server import Engine, NotFound, init_tracing, reset_engine  # type: ignore[import-not-found, import-untyped, unused-ignore]
from ciris_server.edge import init_edge_runtime  # type: ignore[import-not-found, import-untyped, unused-ignore]

#: Kept for callers and tests that assert which substrate loaded; one value now.
SUBSTRATE_SOURCE = "ciris_server"

__all__ = [
    "Engine",
    "NotFound",
    "reset_engine",
    "init_edge_runtime",
    "init_tracing",
    "SUBSTRATE_SOURCE",
]
