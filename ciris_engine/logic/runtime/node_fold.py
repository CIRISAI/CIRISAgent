"""Phase-4 node fold — stand up the CIRISServer node on the agent's engine/edge.

CIRISAGENT_ADOPTION Phase 4 (the single 2.9.7 boot path): after the agent's
embedded persist Engine + Edge are up and the brain's API listener (:8080) is
serving, we boot the node via ``ciris_server.serve_with_python_adapter``. On
ciris-server >=0.5.96 (CIRISServer#221) that call REUSES the agent's in-process
Engine (``current_rust_engine()``) + Edge (``current_edge()``) — no second
SQLite pool, no second :4242 transport bind — and mounts the node's substrate
read-API on **4243** (federation / self / accord / auth / config / health /
memory-read), including the wizard's ``/v1/federation/announce`` opt-in. The
:class:`BrainAdapter`'s ``proxy_routes`` reverse-proxy the brain prefixes back to
:8080.

Node-fails ⇒ agent-fails: ``serve_with_python_adapter`` blocks on its own tokio
runtime; we run it on a thread and surface an early failure so boot aborts rather
than limping without the node (per the single-boot-path contract).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_node_thread: Optional[threading.Thread] = None
_node_error: Optional[str] = None


def _resolve_home() -> str:
    """The node's home (config + data root) — the agent's CIRIS_HOME."""
    return os.environ.get("CIRIS_HOME") or os.environ.get("CIRIS_DATA_DIR") or os.getcwd()


def _resolve_key_id() -> Optional[str]:
    """Federation key_id for the node config — the embedded edge's signer.

    The node reuses ``current_edge()`` so this only tags config; align it to the
    edge's signer so the node's identity matches the agent's. None ⇒ the wheel's
    DEFAULT_KEY_ID.
    """
    try:
        from ciris_engine.logic.runtime.edge_runtime import get_edge

        return str(get_edge().signer_key_id())
    except Exception:  # noqa: BLE001 — edge may be degraded; fall back to default
        return None


def start_node_fold(brain_port: int, *, home: Optional[str] = None, key_id: Optional[str] = None) -> None:
    """Boot the node (4243) on the agent's engine/edge, brain proxied to :8080.

    Raises RuntimeError if the node fails to start (node-fails ⇒ agent-fails).
    Idempotent: a second call is a no-op.
    """
    global _node_thread, _node_error

    if os.environ.get("CIRIS_NODE_FOLD", "true").strip().lower() in ("0", "false", "no", "off"):
        logger.info("Node fold disabled (CIRIS_NODE_FOLD=false) — federation/self/accord routes NOT served on 4243")
        return
    if _node_thread is not None and _node_thread.is_alive():
        return

    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"node fold: ciris_server not importable: {exc}") from exc

    serve = getattr(ciris_server, "serve_with_python_adapter", None)
    if serve is None:
        raise RuntimeError(
            "node fold: ciris_server.serve_with_python_adapter unavailable (need >=0.5.96); "
            "the federation/self/accord node read-API (4243) cannot be served — the wizard's "
            "/v1/federation/announce would 404 and the agent could not announce."
        )

    from ciris_engine.logic.runtime.brain_adapter import BrainAdapter

    resolved_home = home or _resolve_home()
    resolved_key = key_id or _resolve_key_id()
    adapter = BrainAdapter(upstream=f"http://127.0.0.1:{brain_port}")

    def _run() -> None:
        global _node_error
        try:
            logger.info(
                "Node fold: booting CIRISServer node (reusing embedded engine+edge) → substrate read-API on 4243 "
                "(home=%s key_id=%s); brain proxied to :%d",
                resolved_home,
                resolved_key,
                brain_port,
            )
            # Blocks on the node's tokio runtime until shutdown.
            serve(adapter, resolved_home, resolved_key)
        except Exception as exc:  # noqa: BLE001
            _node_error = f"{type(exc).__name__}: {exc}"
            logger.error("Node fold: serve_with_python_adapter exited/failed: %s", _node_error)

    _node_thread = threading.Thread(target=_run, name="ciris-node-fold", daemon=True)
    _node_thread.start()

    # node-fails ⇒ agent-fails: give the node a moment to compose + bind 4243;
    # if it died on startup, abort the whole boot.
    time.sleep(2.5)
    if _node_error is not None:
        raise RuntimeError(f"node fold failed to start (node-fails ⇒ agent-fails): {_node_error}")
    # Confirm the node's read-API actually bound 4243 (a router-assembly panic
    # shows up here as a closed port).
    import socket

    node_up = False
    for _ in range(6):
        try:
            with socket.create_connection(("127.0.0.1", 4243), timeout=1):
                node_up = True
                break
        except OSError:
            time.sleep(0.5)
    if _node_error is not None:
        raise RuntimeError(f"node fold failed to start (node-fails ⇒ agent-fails): {_node_error}")
    if not node_up:
        raise RuntimeError("node fold: read-API did not bind 127.0.0.1:4243 (node-fails ⇒ agent-fails)")
    logger.info("Node fold: node runtime started — substrate read-API LISTENING on 4243 ✅")
