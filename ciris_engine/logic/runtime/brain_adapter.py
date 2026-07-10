"""BrainAdapter — the agent's cognitive loop folded onto the CIRISServer node.

CIRISAGENT_ADOPTION Phase 4 (the single boot path, 2.9.7): the agent no longer
calls persist/edge/verify directly. It boots the **node**
(``ciris_server.serve_with_python_adapter(BrainAdapter(), home, key_id)``) which
stands up the one persist ``Engine`` + ``Edge`` + the substrate read-API on port
4243 (federation / self / accord / auth / config / health / memory-read). This
adapter is the Python "brain": its cognitive loop (processors/dma/conscience/
handlers + LLM/tool services) runs against the node's shared Engine singleton and
serves the brain routes (chat/cognition, audit, telemetry, tools, WA, memory
writes, LLM status) on its own sibling listener (:8080), which the node
reverse-proxies onto 4243 per :func:`proxy_routes`.

Node-fails ⇒ agent-fails: if ``serve_with_python_adapter`` cannot compose the
node, the process exits — there is no direct-persist fallback boot.

Contract (CIRISServer#80 ``crate::py_adapter``, all members duck-typed):
    adapter_type: str          # "brain"
    enabled: bool              # True
    proxy_routes(self) -> [{"prefix": ..., "upstream": ...}]
    start(self)                # one-shot: boot the cognitive runtime + :8080
    stop(self)                 # teardown
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# The brain's sibling HTTP listener. The node (4243) reverse-proxies the brain
# prefixes here; substrate prefixes are served by the node natively.
BRAIN_UPSTREAM = "http://127.0.0.1:8080"

# Substrate surface — served NATIVELY by the node on 4243 (FSD §4c). The brain
# must NOT proxy these, or it would shadow the node's authoritative routes.
_SUBSTRATE_PREFIXES = (
    "/v1/federation",
    "/v1/self",
    "/v1/accord",
    "/v1/auth",       # login/me/device-grants + attestation (node owns identity)
    "/v1/config",
    "/v1/health",
    "/v1/system/health",
)

# Brain surface — the cognitive/agent routes the node does NOT serve, proxied to
# the sibling :8080. The py_adapter proxy is prefix-catch-all (`/v1/X/{*rest}`),
# so a proxied prefix cannot coexist with ANY node-native route under it — the
# router panics ("Insertion failed due to conflict"). So we proxy ONLY prefixes
# with no node-native subroutes; the substrate surface the node serves natively
# (federation/self/accord/auth/config/health + memory-READ + my-data/capacity +
# system/health) is deliberately excluded. Overlapping brain halves (memory
# WRITES, system LLM-status) reach :8080 directly for now — folding them under
# 4243 needs per-method proxying (follow-up), not a prefix catch-all.
_BRAIN_PREFIXES = (
    "/v1/agent",
    "/v1/interact",
    "/v1/audit",
    "/v1/telemetry",
    "/v1/tools",
    "/v1/wa",
    "/v1/tickets",
    "/v1/transparency",
    "/v1/scheduler",
    "/v1/emergency",
    "/v1/dsar",
    "/v1/partnership",
    "/v1/billing",
    "/v1/connectors",
)


class BrainAdapter:
    """Duck-typed CIRISServer Python adapter wrapping the agent cognitive loop."""

    adapter_type: str = "brain"
    enabled: bool = True

    def __init__(self, upstream: str = BRAIN_UPSTREAM, runtime_boot: Optional[Any] = None) -> None:
        self._upstream = upstream
        # runtime_boot: a zero-arg callable that boots the agent runtime + :8080
        # sibling listener and returns a stoppable handle. Injected so this
        # module stays free of the heavy runtime import at definition time.
        self._runtime_boot = runtime_boot
        self._handle: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None

    # ── CIRISServer py_adapter contract ──────────────────────────────────────
    def proxy_routes(self) -> List[Dict[str, str]]:
        """Brain prefixes reverse-proxied onto the node's 4243 read-API.

        Only brain routes are declared; the node serves the substrate surface
        (:data:`_SUBSTRATE_PREFIXES`) natively, so the wizard's
        ``/v1/federation/announce`` + ``/v1/self/*`` resolve on the node, not
        here.
        """
        return [{"prefix": p, "upstream": self._upstream} for p in _BRAIN_PREFIXES]

    def start(self) -> None:
        """Boot the cognitive runtime + the :8080 sibling listener.

        Runs against the node's ALREADY-composed persist ``Engine`` singleton
        (constructed by ``serve_with_python_adapter`` before this hook fires) —
        the brain attaches to it rather than constructing its own. Booted on a
        daemon thread so this sync hook returns promptly and the node's lifecycle
        proceeds; the node parks until shutdown.
        """
        if self._runtime_boot is None:
            logger.error("BrainAdapter.start: no runtime_boot injected — cognitive loop will NOT run")
            return

        def _boot() -> None:
            try:
                self._handle = self._runtime_boot()
                logger.info("BrainAdapter: cognitive runtime booted on the sibling listener (%s)", self._upstream)
            except Exception:  # noqa: BLE001 — surface, node stays up serving substrate
                logger.exception("BrainAdapter: cognitive runtime boot FAILED")

        self._thread = threading.Thread(target=_boot, name="brain-runtime", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Tear down the cognitive runtime (node lifecycle is stopping)."""
        handle = self._handle
        if handle is None:
            return
        try:
            stop = getattr(handle, "stop", None) or getattr(handle, "shutdown", None)
            if callable(stop):
                stop()
            logger.info("BrainAdapter: cognitive runtime stopped")
        except Exception:  # noqa: BLE001
            logger.exception("BrainAdapter: cognitive runtime stop failed (non-fatal)")
