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


def _this_process_owns_port(port: int) -> Optional[bool]:
    """Does THIS process hold the listening socket on `port`?

    A module global cannot answer this. The in-process restart the reuse branch
    exists for re-imports the module — the comment below says so explicitly,
    "module globals can be wiped by the re-import while the daemon thread lives
    on" — so any Python-side flag reads False exactly when the answer is yes.
    That is the failure mode that would refuse a legitimate mobile restart.

    Socket ownership is a KERNEL fact and survives the re-import: match the
    listener's inode from /proc/self/net/tcp against this process's own fds.

    Returns True/False on Linux, and None where /proc is unavailable — None means
    "cannot tell", and the caller must not read it as either answer.
    """
    import glob

    inodes = set()
    found_any = False
    for path in ("/proc/self/net/tcp", "/proc/self/net/tcp6"):
        try:
            with open(path, encoding="utf-8") as fh:
                rows = fh.read().splitlines()[1:]
            found_any = True
        except OSError:
            continue
        for line in rows:
            fields = line.split()
            # st == 0A is TCP_LISTEN; local_address is hex "ADDR:PORT".
            if len(fields) > 9 and fields[3] == "0A":
                try:
                    if int(fields[1].split(":")[1], 16) == port:
                        inodes.add(fields[9])
                except (IndexError, ValueError):
                    continue
    if not found_any:
        return None
    if not inodes:
        return False
    for fd in glob.glob("/proc/self/fd/*"):
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if target.startswith("socket:[") and target[8:-1] in inodes:
            return True
    return False


_node_thread: Optional[threading.Thread] = None
_node_error: Optional[str] = None


def _resolve_home() -> str:
    """The node's home (config + data root) — the agent's CIRIS_HOME.

    This exact string is handed to ``serve_with_python_adapter``, and the node
    derives BOTH ``<home>/identity`` and ``<home>/data`` from it. The persist
    Engine must resolve its federation identity from the same home, so this
    defers to ``get_ciris_home()`` — the one resolver that already knows about
    managed/Android/iOS layouts. It previously returned ``os.getcwd()``, which
    agreed with ``get_data_dir()`` only in development mode; anywhere else the
    node and the Engine would have resolved two different identity dirs.
    """
    from ciris_engine.logic.utils.path_resolution import get_ciris_home

    return str(get_ciris_home())


def _resolve_key_id() -> Optional[str]:
    """Federation keystore alias for the node — the SAME alias the Engine uses.

    This must match ``Engine(..., keystore_alias=...)`` exactly: the sealed
    keystore keys off (identity_dir, alias), so two spellings are two keys, and
    CIRISServer 0.5.160+ refuses to boot on the mismatch (CIRISServer#380).

    This used to return ``get_edge().signer_key_id()`` — the *derived* id
    ``<alias>-<fingerprint>`` — to "align the node to the edge's signer". That
    alignment was attempted at the wrong layer and was self-feeding: the derived
    id became the next boot's alias, minting a fresh sealed key each time. The
    edge derives its id from the Engine's signer anyway, so unifying on the base
    alias aligns all three by construction.
    """
    from ciris_engine.logic.utils.path_resolution import get_federation_alias

    return get_federation_alias()


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
            line = (
                f"Node fold: OWNERSHIP UNCLAIMED — one-time CLAIM PIN: {pin} (console-only; used by setup self-claim)"
            )
            print(line, flush=True)  # → logcat python.stdout on Android; console on desktop
            logger.info(line)  # → <home>/logs/latest.log for the file-tail capture
    except Exception as exc:  # noqa: BLE001 — never let PIN surfacing break the boot
        logger.debug("Node fold: first_run_claim_pin probe failed (non-fatal): %s", exc)


def _reprime_federation_delivery(path: str) -> None:
    """Re-drive the canonical delivery prime (CIRISServer#288 / CIRISAgent#926).

    The setup-complete restart is an in-process reload: the edge runtime is a
    reused process-singleton, so ``start_federation_delivery`` (is_started()-
    guarded) never re-fires and canonical is never re-rooted as a KEX'd
    delivery target — the exact ``peer_count_canonical: 0`` /
    rooted-once-never-dialed shape that stranded the first sealed mobile
    trace. ``reprime_federation_delivery`` (ciris-server >=0.5.124) is
    idempotent and re-drives ONLY the canonical prime against the current
    embedded handles, so it is safe on every re-serve (both the reuse branch
    and a fresh post-bind). getattr-guarded: wheels <0.5.124 degrade to the
    prior (never-re-primed) behavior rather than crashing.
    """
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

        reprime = getattr(ciris_server, "reprime_federation_delivery", None)
        if reprime is None:
            logger.info(
                "Node fold: reprime_federation_delivery unavailable (wheel <0.5.124) — canonical prime not re-driven (%s)",
                path,
            )
            return
        count = reprime()
        logger.info(
            "Node fold: reprime_federation_delivery(%s) → %s canonical delivery target(s) re-seeded", path, count
        )
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: delivery re-prime failure must never take down the fold —
        # the seal path still works; only the ship waits for the next prime.
        logger.warning("Node fold: reprime_federation_delivery(%s) failed (non-fatal): %s", path, exc)


def _author_federation_consent(path: str) -> None:
    """Author the owner's replication consent in-process (ciris-server >=0.5.147).

    THE USER CONSENTS; THE SUBSTRATE ONLY TRUSTS. Since 0.5.146 the substrate no
    longer boot-authors a ``consent:replication`` grant on the owner's behalf —
    correctly, because consent is the owner's act. But the only route that could
    express it, ``POST /v1/federation/consent``, is mounted in
    ``serve_with_adapter``; the embedded agent boots via
    ``federation_delivery::start_and_hold``, which mounts no HTTP router at all.
    So on-device the wizard's call 404'd and NO grant existed.

    Without a grant covering ``trace:``, ``promote_consented_backlog`` never
    lifts a sealed trace out of (cohort_scope=self, tier=local). The node roots
    the canonical, converges to its consent peer, seals signed traces, reports
    healthy — and offers nothing. Observed for a full day: canonical
    ``trace_events`` zero, from every agent.

    0.5.147 adds the in-process entry point. The prefixes are READ from
    ``default_attestation_prefixes()``, never restated here: a restated list is
    exactly how ``["capacity:"]`` shipped while the authority said
    ``["capacity:", "trace:"]``, and a copy that drifts silently strands every
    trace it fails to name.
    """
    # THE OWNER CONSENTS, NOT THE FOLD. Booting a node is not consenting to
    # replicate your reasoning traces off it, and a grant the machinery created
    # is indistinguishable downstream from one the owner asked for. The
    # substrate stopped boot-authoring in 0.5.146 for exactly this reason;
    # authoring here without the opt-in would reintroduce it one layer up.
    #
    # So this path REPLAYS an opt-in the owner already gave — it never
    # originates one. `require_opt_in=True` (the default) makes the helper check
    # the signal and fail CLOSED when it cannot be read.
    from ciris_engine.logic.services.governance.consent.trace_sharing import grant_trace_sharing
    from ciris_engine.schemas.consent.trace_sharing import TraceConsentSource

    result = grant_trace_sharing(TraceConsentSource.NODE_FOLD)
    logger.info(
        "Node fold: trace-sharing consent (%s): opted_in=%s capture=%s ship=%s",
        path,
        result.opted_in,
        result.capture_grant_id or "none",
        result.peers_authored or "none",
    )


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
    #
    # HARDENED (2026-07-20, QA all_1 RCA): "accepts on :4243" is NOT proof the
    # node is OURS. Under CI --parallel-backends, the postgres leg's probe found
    # the SQLITE leg's node (a different process, different signing key)
    # answering :4243 and silently "reused" it — every subsequent accord-metrics
    # capture then failed `receive_and_persist: ValueError: verify_unknown_key`
    # (×244, incidents gate, exit 1). So: before reusing, ask the live node who
    # it is (/v1/self/identity, /v1/health) and require OUR key_id in the
    # answer. Confirmed-foreign ⇒ hard error (node-fails ⇒ agent-fails — never
    # ship traces to someone else's node). Cannot-determine (endpoint shape
    # drift on older wheels) ⇒ loud warning + reuse, preserving the legit
    # mobile-restart path this branch exists for.
    import socket as _socket

    try:
        with _socket.create_connection(("127.0.0.1", 4243), timeout=1):
            live_node = True
    except OSError:
        live_node = False

    if live_node:
        expected_key = key_id or _resolve_key_id()
        identity_text = ""
        http_alive = False  # did ANY HTTP response come back? (zombie vs live)
        try:
            import urllib.error as _urlerr
            import urllib.request as _urlreq

            # Track HTTP-LEVEL LIVENESS separately from identity. A bound socket with
            # nothing serving behind it — our own zombie from a half-dead restart —
            # looks identical to a live node whose identity endpoints drifted on an
            # older wheel, because urlopen raises for both. It is not identical: an
            # HTTPError PROVES a server answered. Connection refused/reset/timeout
            # proves one did not.
            #
            # CI, postgres leg: socket ownership said OURS, identity was unreadable, we
            # reused — and :4243 then served NOTHING for the whole run (0 node-side
            # successes, 39 proxy 502s on a 60s cadence). Ownership was the wrong
            # sufficient condition; the node must also be ALIVE.
            for probe_path in ("/v1/self/identity", "/v1/health"):
                try:
                    with _urlreq.urlopen(f"http://127.0.0.1:4243{probe_path}", timeout=2) as resp:
                        identity_text += resp.read(65536).decode("utf-8", errors="replace")
                        http_alive = True
                except _urlerr.HTTPError:
                    # 404/500/etc — the endpoint is absent or unhappy, but SOMETHING
                    # answered. That is the older-wheel case this branch protects.
                    http_alive = True
                except Exception:  # noqa: BLE001 — refused/timeout: no server there
                    continue
        except Exception:  # noqa: BLE001
            pass

        if expected_key and identity_text and expected_key not in identity_text:
            raise RuntimeError(
                f"node fold: :4243 is already serving but it is NOT our node "
                f"(expected key_id={expected_key} absent from /v1/self/identity + /v1/health). "
                f"Another CIRIS process on this host owns :4243 — reusing it would ship our "
                f"traces to a foreign node (verify_unknown_key, QA all_1 RCA). "
                f"Run one node-folded stack per host, or stop the other process first."
            )
        if not identity_text:
            # THREE distinct states, which the original code collapsed into one:
            #
            #   http_alive AND ours      -> live node, endpoints drifted (old wheel).
            #                               Reuse. This is the case the branch exists for.
            #   NOT http_alive           -> a bound socket with nothing serving behind it.
            #                               A ZOMBIE. Reusing it is how the postgres leg
            #                               spent an entire run 502-ing: 0 node-side
            #                               successes, 39 proxy failures on a 60s cadence,
            #                               while sqlite — which bound its own — passed.
            #   http_alive AND NOT ours  -> foreign live node; the confirmed-foreign raise
            #                               above already covers the readable case, this
            #                               covers the unreadable one.
            #
            # Ownership alone was the wrong sufficient condition — my first fix. It
            # answers 'is it ours', and a zombie of ours is still unusable.
            owns = _this_process_owns_port(4243)
            if not http_alive:
                raise RuntimeError(
                    "node fold: :4243 is bound but does not speak HTTP "
                    f"(owned_by_us={owns}). Reusing a dead listener leaves every "
                    "/v1/auth call answering 502 for the life of the process — observed "
                    "in CI as 0 node-side successes with 39 proxy failures.\n"
                    "TWO CAUSES, both seen: (a) a dead node left the socket bound, or "
                    "(b) a NON-HTTP service holds the port — the QA runner's per-backend "
                    "edge offset used to put the Reticulum listener on 4243, which is not "
                    "a zombie at all, just a different service on a reserved port. Check "
                    "CIRIS_EDGE_LISTEN_ADDR before hunting a dead node."
                )
            if owns is False:
                raise RuntimeError(
                    "node fold: :4243 is serving, its identity could not be read, and the "
                    "listening socket is NOT held by this process — so it is not ours. "
                    "Reusing it would ship traces to a foreign node (verify_unknown_key, "
                    "QA all_1 RCA). Run one node-folded stack per host."
                )
            logger.warning(
                "Node fold: 4243 serving and ALIVE but identity endpoints unreadable "
                "(socket-ownership=%s) — older-wheel endpoint drift; reusing.",
                owns,
            )
        else:
            logger.info(
                "Node fold: 4243 already serving and identity CONFIRMED ours (key_id=%s) — reusing the live node",
                expected_key,
            )
        # Non-consuming: re-surface the PIN for the restarted runtime's
        # capture (the wizard's self-claim may run after this reload).
        _surface_first_run_claim_pin()
        _reprime_federation_delivery("reuse")
        _author_federation_consent("reuse")
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

    # CIRISServer#380 "TWO FEDERATION IDENTITIES" RCA instrument: the node resolves
    # its ONE federation identity from `<home>/identity` + alias, and the sealed
    # keystore keys off (identity_dir, alias). When it refuses for a two-identity
    # mismatch the substrate error does NOT name the on-disk artifacts, so a stray
    # sealed blob, a bare `ed25519.seed`, a `.superseded-*` archive, or a second
    # alias's key is invisible. Enumerate the dir here so the refusal is diagnosable
    # from the agent log alone. Cheap, once per boot, never throws.
    try:
        from ciris_engine.logic.utils.path_resolution import get_identity_dir

        _idir = get_identity_dir()
        _entries = (
            sorted(f"{p.name} ({p.stat().st_size}B)" for p in _idir.iterdir() if p.is_file())
            if _idir.is_dir()
            else ["<identity dir does not exist>"]
        )
        logger.info(
            "Node fold: identity resolution — home=%s alias=%s identity_dir=%s\n  contents: %s",
            resolved_home,
            resolved_key,
            str(_idir),
            "\n            ".join(_entries) if _entries else "<empty>",
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic must never break boot
        logger.warning("Node fold: identity-dir enumeration failed (non-fatal): %s", exc)

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

    _attempts = (
        190 if _mobile else 115
    )  # mobile ~100s (must sit UNDER the 120s Start Adapters step timeout), desktop ~60s
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

    # Hand the node the deployment's OAuth providers now that it is serving.
    #
    # 2.9.14 moved /v1/auth/* onto the node but did not carry across the provider
    # credentials the deleted Python router read from oauth.json, so hosted Google
    # sign-in fell back to the node's loopback callback and Google rejected it.
    # Best-effort and idempotent: a desktop install has no oauth.json and needs none.
    try:
        from ciris_engine.logic.runtime.oauth_provider_sync import sync_oauth_providers_to_node

        sync_oauth_providers_to_node()
    except Exception:  # pragma: no cover - never block the boot on OAuth config
        logger.exception("Node fold: OAuth provider sync failed (agent continues)")
    _reprime_federation_delivery("post-bind")
    _author_federation_consent("post-bind")
    # Surface the one-time first-run CLAIM PIN (minted during compose, stashed
    # in-process by ciris-server ≥0.5.119) so the client's capture latches it.
    _surface_first_run_claim_pin()
    # The node's SIGNED self identity-occurrence publish + trusted-peer boot-prime
    # are owned by the substrate (CIRISServer#227 S1, ciris-server >=0.5.101) — the
    # agent does NOT derive/publish encryption_pubkeys itself.
