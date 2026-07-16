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


def _surface_first_run_claim_pin() -> None:
    """Echo the node's one-time first-run CLAIM PIN to the app's console.

    ciris-server ≥0.5.119 (CIRISServer#277) exposes
    ``ciris_server.first_run_claim_pin()`` — an in-process, NON-consuming,
    never-over-HTTP accessor stashed the instant compose mints the PIN. On the
    embedded topology the embedding app IS the node's console, but the rust
    tracing banner is unobservable on Android (0-byte file sink at compose,
    nothing in logcat). Bridge it here: print + log the PIN in the exact
    banner vocabulary the client's capture already latches
    (``parseOwnershipBanner`` — the "CLAIM PIN" marker + the Crockford
    XXXX-XXXX shape — via BOTH the logcat python.stdout stream and the
    <home>/logs/latest.log file-tail). No PIN (already-claimed node, or a
    pre-0.5.119 wheel) ⇒ silent no-op. Security note: this reaches the app's
    own stdout/log file only — the same trust domain as the desktop console
    the PIN is designed for; it is never served over HTTP.
    """
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

        accessor = getattr(ciris_server, "first_run_claim_pin", None)
        if accessor is None:
            return  # pre-0.5.119 wheel — banner-only capture still applies
        pin = accessor()
        if pin:
            line = f"Node fold: OWNERSHIP UNCLAIMED — one-time CLAIM PIN: {pin} (console-only; used by setup self-claim)"
            print(line, flush=True)  # → logcat python.stdout on Android; console on desktop
            logger.info(line)  # → <home>/logs/latest.log for the file-tail capture
    except Exception as exc:  # noqa: BLE001 — never let PIN surfacing break the boot
        logger.debug("Node fold: first_run_claim_pin probe failed (non-fatal): %s", exc)


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

    # In-process runtime RESTART (mobile post-setup): the prior runtime's node
    # may still be serving 4243 on its own tokio thread (module globals can be
    # wiped by the re-import while the daemon thread lives on). The node is a
    # process-singleton — if 4243 already accepts, reuse it: its brain proxy
    # targets 127.0.0.1:<brain_port>, which the restarted brain rebinds.
    import socket as _socket

    try:
        with _socket.create_connection(("127.0.0.1", 4243), timeout=1):
            logger.info("Node fold: 4243 already serving (prior runtime in this process) — reusing the live node")
            # Non-consuming: re-surface the PIN for the restarted runtime's
            # capture (the wizard's self-claim may run after this reload).
            _surface_first_run_claim_pin()
            return
    except OSError:
        pass

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

    # CIRISServer#276 clean-restart: on an in-process runtime RESTART (mobile
    # setup-complete), the prior node's tokio thread can keep :4243 bound for
    # minutes during teardown/rebind (EADDRINUSE) even though the reuse-probe
    # above no longer connects — the old ~4-minute wedge between an owned
    # first-run and the automated filmstrip. shutdown_node() (ciris-server
    # >=0.5.122) signals the prior node to stop and BLOCKS until :4243 is
    # bindable again; it no-ops immediately when nothing is serving, so it is
    # safe on the first-boot path too. Guarded via getattr so a wheel <0.5.122
    # degrades to the prior (EADDRINUSE-prone) behavior rather than crashing.
    _shutdown_node = getattr(ciris_server, "shutdown_node", None)
    if _shutdown_node is not None:
        try:
            _bindable = _shutdown_node(timeout_secs=30)
            logger.info("Node fold: shutdown_node() → :4243 bindable=%s (CIRISServer#276 clean-restart)", _bindable)
        except Exception as exc:  # noqa: BLE001
            # Non-fatal: if the primitive itself errors, fall through to serve()
            # — a genuine EADDRINUSE there still trips node-fails ⇒ agent-fails.
            logger.warning("Node fold: shutdown_node() raised (continuing to serve): %s", exc)

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

    # node-fails ⇒ agent-fails: give the node time to compose + bind 4243;
    # if it died on startup, abort the whole boot. Desktop composes in ~2-3s;
    # on-device under arm64 translation (emulator) the same compose takes
    # 15-40s, so the window is 60s — an early _node_error still aborts fast.
    time.sleep(2.5)
    if _node_error is not None:
        raise RuntimeError(f"node fold failed to start (node-fails ⇒ agent-fails): {_node_error}")
    # Confirm the node's read-API actually bound 4243 (a router-assembly panic
    # shows up here as a closed port).
    import socket

    node_up = False
    try:
        from ciris_engine.logic.utils.path_resolution import is_android, is_ios

        _mobile = is_android() or is_ios()
    except Exception:  # noqa: BLE001
        _mobile = False
    # compose_status() (ciris-server ≥0.5.120, CIRISServer#279): in-process
    # compose-progress snapshot — {"completed", "current": {phase, elapsed_s,
    # stuck, ...} | null, "history": [{phase, ms}]}. Poll it during the bind
    # wait so a wedged compose NAMES its seam in the log (and in the failure),
    # instead of a dark N-minute timeout. The [COMPOSE] lines are what the QA
    # fold-RCA reads to attribute a compose-hang to its phase.
    def _compose_phase() -> Optional[str]:
        try:
            import json as _json

            _status_fn = getattr(ciris_server, "compose_status", None)
            if _status_fn is None:
                return None
            st = _json.loads(_status_fn() or "{}")
            cur = st.get("current") or {}
            if st.get("completed"):
                return "completed"
            if cur:
                stuck = " STUCK" if cur.get("stuck") else ""
                return f"{cur.get('phase')} ({cur.get('elapsed_s')}s{stuck})"
            return None
        except Exception:  # noqa: BLE001
            return None

    _attempts = 190 if _mobile else 115  # mobile ~100s (must sit UNDER the 120s Start Adapters step timeout), desktop ~60s
    _last_phase: Optional[str] = None
    for _i in range(_attempts):
        if _node_error is not None:
            raise RuntimeError(f"node fold failed to start (node-fails ⇒ agent-fails): {_node_error}")
        try:
            with socket.create_connection(("127.0.0.1", 4243), timeout=1):
                node_up = True
                break
        except OSError:
            time.sleep(0.5)
        if _i % 20 == 19:  # every ~10s: log compose-phase transitions
            _phase = _compose_phase()
            if _phase and _phase != _last_phase:
                logger.info("[COMPOSE] phase: %s", _phase)
                _last_phase = _phase
    if _node_error is not None:
        raise RuntimeError(f"node fold failed to start (node-fails ⇒ agent-fails): {_node_error}")
    if not node_up:
        _wedged = _compose_phase()
        raise RuntimeError(
            "node fold: read-API did not bind 127.0.0.1:4243 in the bind window "
            f"(node-fails ⇒ agent-fails); compose phase at expiry: {_wedged or 'unknown (no compose_status — wheel <0.5.120?)'}"
        )
    logger.info("Node fold: node runtime started — substrate read-API LISTENING on 4243 ✅")
    # Surface the one-time first-run CLAIM PIN (minted during compose, stashed
    # in-process by ciris-server ≥0.5.119) so the client's capture latches it.
    _surface_first_run_claim_pin()
    # The node's SIGNED self identity-occurrence publish + trusted-peer boot-prime
    # are owned by the substrate (CIRISServer#227 S1, ciris-server >=0.5.101) — the
    # agent does NOT derive/publish encryption_pubkeys itself.
