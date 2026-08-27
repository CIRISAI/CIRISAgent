"""
CIRISEdge runtime bootstrap and process singleton.

Edge is a REQUIRED foundation dependency in CIRISAgent 2.9.4+, alongside
ciris-persist and ciris-verify. Failure to initialize the Edge runtime
blocks agent boot — the federation identity (signer_key_id) is part of
the agent's identity and must exist before any cognitive state can run.

Cohabitation contract (CIRISEdge#16 / COHABITATION.md rule 1):
    init_edge_runtime() consumes the SAME ciris_persist.Engine the rest
    of the agent uses. The keyring is NOT re-bootstrapped — Edge extracts
    the signer + rooting directory + outbound queue from the persist
    engine and reuses them. One keyring identity per host.

Test escape:
    PYTEST_CURRENT_TEST or CIRIS_EDGE_DISABLED=true skips Edge init and
    leaves the singleton unset. Callers that hit get_edge() with no live
    runtime get a clear RuntimeError, NOT a silent None — matches the
    persist pattern at logic/persistence/models/graph.py:_get_engine().
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_edge: Optional[Any] = None


def _edge_disabled() -> bool:
    """Edge init skipped under pytest or explicit CIRIS_EDGE_DISABLED=true."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return os.environ.get("CIRIS_EDGE_DISABLED", "").lower() in ("true", "1", "yes")


def initialize_edge_runtime(identity_dir: Path) -> None:
    """Bootstrap the Edge runtime singleton.

    Called once during agent startup AFTER persist's initialize_database()
    has set the global engine. The identity file lives at
    {identity_dir}/edge_identity.rid; on first boot Reticulum generates a
    fresh Ed25519 identity, on subsequent boots it loads.

    Raises:
        RuntimeError: if persist engine is not yet wired, or if Edge
            construction fails (port bind error, identity load failure).
            This is a hard boot blocker — same treatment as persist.
    """
    global _edge

    if _edge_disabled():
        logger.info("Edge runtime init skipped (PYTEST_CURRENT_TEST or CIRIS_EDGE_DISABLED set)")
        return

    if _edge is not None:
        logger.debug("Edge runtime already initialized; skipping re-init")
        return

    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    if engine is None:
        raise RuntimeError(
            "Cannot initialize Edge runtime: persist engine not yet wired. "
            "Call ciris_engine.logic.persistence.initialize_database() first."
        )

    # One-wheel seam (#896): the edge runtime constructor re-hosts from the
    # consolidated ``ciris_server`` wheel (falling back to the standalone
    # ``ciris_edge`` wheel). Sourcing it from the SAME wheel as the persist
    # Engine gives one PyO3 type registry, so the Engine passed below is the
    # same registered Rust type Edge expects — no ``'Engine' object is not an
    # instance of 'Engine'`` cohabitation refusal (CIRISEdge#22).
    from ciris_engine.logic.persistence._substrate import init_edge_runtime

    if init_edge_runtime is None:
        raise RuntimeError(
            "edge runtime constructor not importable but is REQUIRED for 2.9.4+. "
            "Install ciris-server (one wheel) or pin ciris-edge>=2.0.2,<3.0.0 in requirements.txt."
        )

    identity_dir.mkdir(parents=True, exist_ok=True)
    identity_path = identity_dir / "edge_identity.rid"

    listen_addr = os.environ.get("CIRIS_EDGE_LISTEN_ADDR", "0.0.0.0:4242")
    bootstrap_peers_raw = os.environ.get("CIRIS_EDGE_BOOTSTRAP_PEERS", "")
    bootstrap_peers = [p.strip() for p in bootstrap_peers_raw.split(",") if p.strip()]

    from ciris_engine.logic.utils.agent_mode_broker import get_agent_mode_broker

    agent_mode_value = get_agent_mode_broker().current_mode().value

    # Federation delivery (CIRISAgent#915). The embedded edge must carry an
    # ACTIVE Reticulum transport for CEG traces to reach the canonical mesh;
    # the wheel defaults enable_transport OFF. Turn it on when delivery is
    # enabled (default), matching compose's transport node. On ciris-server
    # >=0.5.92 (CIRISEdge#296 / CIRISPersist#402) init_edge_runtime then
    # AUTO-SEEDS the canonical TCP dial from persist's baked
    # canonical_bootstrap_hints() — zero caller glue, exactly like
    # compose::serve — so the agent edge dials + roots ciris-canonical-1 at
    # boot. Opt out with CIRIS_FEDERATION_DELIVERY=false.
    _delivery_on = os.environ.get("CIRIS_FEDERATION_DELIVERY", "true").strip().lower() not in ("0", "false", "no", "off")

    # Rust-side tracing (CIRISAgent#919/#920, ciris-server >=0.5.114): without
    # this a Python-embedded agent has ZERO rust logs — every delivery/rooting
    # diagnostic is invisible (how the trace-flow saga stayed dark). On 0.5.116+
    # init_tracing(log_dir=, filter=) writes a rust log FILE next to the agent's
    # logs — env-whitelist-proof, so RUST_LOG need not survive the mobile env
    # scrub (CIRISServer#264 sub-item). Idempotent.
    try:
        import ciris_server as _cs  # type: ignore[import-not-found, import-untyped, unused-ignore]

        _init_tracing = getattr(_cs, "init_tracing", None)
        if _init_tracing is not None:
            _trace_dir = os.environ.get("CIRIS_HOME") or os.environ.get("CIRIS_DATA_DIR")
            if not _trace_dir:
                # Belt: env can be scrubbed/late on mobile — resolve the real home.
                try:
                    from ciris_engine.logic.utils.path_resolution import get_ciris_home

                    _trace_dir = str(get_ciris_home())
                except Exception:  # noqa: BLE001
                    _trace_dir = None
            _log_dir = os.path.join(_trace_dir, "logs") if _trace_dir else None
            # TEST MODE gets the full-fat filter: compose hangs / keyring stalls /
            # verify paths have all gone dark behind the default filter before
            # (the 2.9.7 compose-hang debug needed exactly these targets). Also
            # force RUST_BACKTRACE so any surfaced panic carries frames.
            _test_mode = os.environ.get("CIRIS_TEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")
            if _test_mode:
                _filter = os.environ.get("RUST_LOG") or (
                    "debug,ciris_server=debug,ciris_edge=debug,ciris_persist=debug,"
                    "ciris_keyring=debug,ciris_verify=debug,ciris_lens_core=debug"
                )
                os.environ.setdefault("RUST_BACKTRACE", "full")
            else:
                _filter = os.environ.get("RUST_LOG") or "info,ciris_server=debug,ciris_edge=debug,ciris_persist=info"
            try:
                _sink_verdict = _init_tracing(log_dir=_log_dir, filter=_filter)
            except TypeError:  # pre-0.5.116 bare signature
                _sink_verdict = _init_tracing()
            logger.info(
                "Rust tracing initialized: log_dir=%s filter=%s test_mode=%s (rust logs → ciris-server.log*)",
                _log_dir,
                _filter,
                _test_mode,
            )
            # 0.5.120 (CIRISServer#279 ask 1): init_tracing returns the sink
            # verdict {fresh_subscriber, file_layer_attached, first_write_ok,
            # log_path} — first-write-verified at t=0. Log it loudly either way
            # so every pull carries it (the t+60s [RUST-SINK] sentinel stays as
            # the belt for older wheels / late failures).
            if isinstance(_sink_verdict, dict):
                if _sink_verdict.get("first_write_ok"):
                    logger.info("[RUST-SINK] t=0 verdict: %s", _sink_verdict)
                else:
                    logger.warning("[RUST-SINK] t=0 DARK — file layer not writing: %s", _sink_verdict)
    except Exception as _trace_exc:  # noqa: BLE001 — observability must never block boot
        logger.debug("ciris_server.init_tracing unavailable/failed (non-fatal): %s", _trace_exc)

    # WHICH KEY THIS EDGE CARRIES (ciris-server 0.5.189, CC 3.4.7.3).
    #
    # The substrate now splits the fused key: the configured key is the ACTOR
    # (`identity_type = agent`, authorship — traces, attestations, on_behalf_of),
    # and boot mints a separate `<alias>-node` key for CARRIAGE (transport,
    # replication, consent, de-admission). Before 0.5.189 one key did both jobs,
    # which is how a node ran for months on the brain's key with every gate green.
    #
    # As of that cut every CEG row — ownership, consent, attestations — is
    # authored by the correct key. The RETICULUM TRANSPORT identity is the one
    # thing that still follows the engine, because edge takes it from
    # `engine.local_signer_capsule()` and in the embedded fold the edge is already
    # running when compose folds onto it — so it is set HERE, by this call.
    #
    # We cannot fix that from Python yet: `node_key::node_signer` is public in
    # Rust for exactly this caller, but it has no PyO3 export and returns an
    # `Arc<LocalSigner>`, not a Python object. `init_edge_runtime` takes no signer
    # argument. Tracked at CIRISServer#492 — the ask is a flag on this call, not a
    # key export, so the key material stays behind the substrate boundary the way
    # `resolve_user_signer` already does.
    #
    # Until then this edge carries the ACTOR key's transport identity. That is the
    # pre-split behaviour and is safe, but it means the lightnet door
    # (`is_bootstrap()` kinds, attributed via the link's transport identity) is
    # still walked by an agency-bearing key.
    try:
        edge = init_edge_runtime(
            engine,
            str(identity_path),
            listen_addr=listen_addr,
            bootstrap_peers=bootstrap_peers,
            agent_mode=agent_mode_value,
            enable_transport=_delivery_on,
        )
    except TypeError as e:
        # PyO3 cross-crate PyClass identity failure — Edge v0.9.1's bundled
        # persist Rust crate produces a different PyClass than the runtime
        # ciris_persist Python module. Tracked at CIRISEdge#22 (cohabitation
        # comment). Until Edge ships a fix (likely v0.9.2+), boot proceeds
        # with Edge in degraded state — UI surface advertises this via
        # GET /v1/system/federation returning {available: false}.
        if "'Engine' object is not an instance of 'Engine'" in str(e):
            logger.warning(
                "Edge runtime init blocked by Edge/persist PyO3 cohabitation bug "
                "(CIRISEdge#22). Federation address unavailable until Edge ships fix. "
                "Boot continuing in degraded state — GET /v1/system/federation will "
                "return available=false."
            )
            return
        raise RuntimeError(
            f"Edge runtime initialization failed with unexpected TypeError: {e}. "
            f"Set CIRIS_EDGE_DISABLED=true to skip."
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"Edge runtime initialization failed (REQUIRED foundation dep): {e}. "
            f"Set CIRIS_EDGE_DISABLED=true to skip in constrained environments."
        ) from e

    _edge = edge

    try:
        key_id = edge.signer_key_id()
        logger.info(
            "Edge runtime initialized: key_id=%s identity=%s listen=%s peers=%d",
            key_id,
            identity_path,
            listen_addr,
            len(bootstrap_peers),
        )
        # 2.9.6 (#866 LensCore fold): register the federation signer key in
        # persist's federation directory. The agent authors local-tier CEG
        # attestations under this identity — the consent wire artifact
        # (consent:community_trust:v1 grants/revocations) and lens-core's
        # per-seal consent gate both depend on it; attestation_upsert_local
        # rejects unregistered attesting keys with federation_invalid_argument.
        # Re-registration of the same key raises federation_conflict — benign.
        try:
            # v10 self-key registration (CIRISConformance conftest pattern):
            # register_self_federation_key registers the engine's OWN signer
            # under the #247-derived federation key_id `<label>-<fp>` — the same
            # id edge.signer_key_id() stamps (CIRISEdge#203, edge 7.0.6+) and
            # the id v10's receive_and_persist verifies trace signatures against.
            # The old 2-arg register_federation_key took (type, key_id); v10's
            # takes a SignedKeyRecord JSON, so that call silently no-op'd and
            # left the signer unregistered → lens receive_and_persist rejected
            # every trace with `verify_unknown_key`.
            derived_kid = engine.register_self_federation_key("agent", key_id, None, None, None)
            logger.info("Federation self key registered with persist: %s (derived %s)", key_id, derived_kid)
        except Exception as reg_exc:
            if "conflict" in str(reg_exc).lower():
                logger.debug("Federation signer key already registered: %s", key_id)
            else:
                logger.warning(
                    "Federation signer key registration failed (%s) — CEG consent "
                    "emits and the lens-core consent gate will not function until "
                    "the key is registered",
                    reg_exc,
                )
    except Exception:
        logger.info("Edge runtime initialized (signer_key_id not yet queryable)")

    # Bootstrap-peer framework hooks (CIRISEdge#46).
    # These run AFTER Edge init succeeds and are non-blocking — any
    # failure is logged but does not fail boot. The hooks themselves
    # are stubs today because Edge 0.13.1 does not yet expose the
    # bootstrap_peers init param or the recent_events ANNOUNCE stream.
    # When Edge 1.0 lands, wire a real BootstrapPeerSeeder here.
    try:
        _seed_bootstrap_peers_into_edge(seeder=None, edge=edge)
    except Exception as exc:
        logger.warning("Bootstrap-peer seed hook failed (non-fatal): %s", exc)
    try:
        register_organic_announce_subscriber(seeder=None)
    except Exception as exc:
        logger.warning("Organic-announce subscriber registration failed (non-fatal): %s", exc)

    # Federation delivery controller (CIRISServer#205 / CIRISAgent#915).
    # With transport enabled above, ciris-server >=0.5.92 auto-seeds + roots the
    # canonical dial at init (CIRISEdge#296); this ONE call then starts the
    # ReplicationRuntime + reconcile loop + announce logger that actually ships
    # the agent's sealed CEG traces to the rooted canonical peer. Without it the
    # trace chain seals locally but nothing reaches the mesh. Default ON (consent
    # still gates what ships at the seal); opt out with CIRIS_FEDERATION_DELIVERY=false.
    if _delivery_on:
        try:
            import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

            start_fd = getattr(ciris_server, "start_federation_delivery", None)
            if start_fd is None:
                logger.info(
                    "Federation delivery controller unavailable in this ciris_server build "
                    "(need >=0.5.92); CEG traces seal locally but are not shipped to the canonical mesh."
                )
            else:
                _n_targets = start_fd(cadence_seconds=15, announce_logger=True)
                logger.info(
                    "Federation delivery controller started (canonical CEG replication + announce rooting); "
                    "admitted canonical targets=%s",
                    _n_targets,
                )
                _spawn_delivery_rooting_probe(engine, edge)
        except Exception as exc:  # noqa: BLE001 — best-effort, never block boot
            logger.warning(
                "Federation delivery controller start failed (non-fatal): %s: %s",
                type(exc).__name__,
                str(exc)[:200],
            )


#: When to reprime after rooting, in seconds post-root, before falling back to
#: the steady cadence. Front-loaded on purpose — see :func:`should_reprime`.
REPRIME_SCHEDULE = (45, 120, 300)

#: Steady-state reprime cadence (s) once REPRIME_SCHEDULE is spent.
REPRIME_CADENCE = 180

#: How many reprimes must pass with nothing received before we call the peer
#: silent rather than slow. Two, so a single unlucky window does not accuse it.
SILENT_PEER_AFTER_REPRIMES = 2


def should_reprime(waited: int, reprimes_done: int, last_reprime: int) -> bool:
    """Is it time to reprime the canonical?

    Front-loaded, then steady. A flat 180s cadence spends the first three
    minutes of every window doing nothing, so a run that ends at ~3 minutes
    gets exactly ONE attempt — which is what a live QA run did: 141 rounds, 21
    Key envelopes sent, zero inbound, KEX never landed, window torn down
    before a second nudge. Reprime is idempotent (CIRISServer#288), so an early
    attempt costs one dial and buys the peer a chance to heal its own
    dial-cache (CIRISEdge#336) while the window is still young.
    """
    if reprimes_done < len(REPRIME_SCHEDULE):
        return waited >= REPRIME_SCHEDULE[reprimes_done]
    return waited - last_reprime >= REPRIME_CADENCE


def peer_is_silent(received_total: int, reprimes_done: int) -> bool:
    """Is the peer not answering at all, as opposed to answering slowly?

    Two stalls wear the same `kex_present=false` label and only one is worth
    waiting through. Inbound arriving means rounds flow and KEX simply has not
    landed yet — that self-heals. Nothing arriving, after we have asked more
    than once, is what a fail-closed refusal looks like from this side: a
    canonical rejects an unknown `attesting_key_id` and says nothing back
    (CIRISServer#488), so a structural refusal and congestion are
    indistinguishable to the sender, and reprime cannot fix either.
    """
    return received_total == 0 and reprimes_done >= SILENT_PEER_AFTER_REPRIMES


def _spawn_delivery_rooting_probe(engine: Any, edge: Any) -> None:
    """One-shot background observability for the trace-delivery last mile.

    Rooting (Reticulum reachability) and envelope shipping are two layers: a peer
    can be transport-rooted (knows_peer / peer_reachability_ratio>0) yet ship 0
    envelopes if its KEM/KEX pubkeys (x25519 + ML-KEM-768) are not in persist's
    federation directory — resolve_peer_kex_pubkeys() returns None, so the
    replication runtime cannot seal an envelope for it. The connect handshake is
    meant to fetch the peer's encryption_pubkeys block from the peer and store it;
    this probe records, once the canonical roots, whether that block is resolvable
    — turning "reachable but 0 envelopes" from a mystery into a logged fact.
    Best-effort, daemon, non-fatal; only runs when delivery is enabled.
    """
    import threading

    def _log_delivery_status(phase: str) -> None:
        """Surface ciris_server.delivery_status() (>=0.5.125, CIRISServer#294) as a
        loggable [DELIVERY-STATUS] line so the QA runner / on-device log tail can
        read the structured delivery state without test mode — the accessor is
        in-process to the server, so it MUST be logged here, not called from the
        runner's own process. Getattr-guarded: older wheels log 'unavailable'.
        Same in-process-accessor → logged-surface pattern as first_run_claim_pin
        and compose_status. Purely diagnostic; never disturbs the probe."""
        try:
            import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

            ds = getattr(ciris_server, "delivery_status", None)
            if ds is None:
                logger.info("[DELIVERY-STATUS] phase=%s unavailable (ciris_server <0.5.125 — no delivery_status accessor)", phase)
                return
            logger.info("[DELIVERY-STATUS] phase=%s %s", phase, ds())
        except Exception as exc:  # noqa: BLE001
            logger.debug("[DELIVERY-STATUS] phase=%s accessor error (non-fatal): %s", phase, exc)

    def _log_trace_plane(phase: str) -> None:
        """Surface `ciris_server.node_state().trace_plane` as a [TRACE-PLANE] line.

        SAME REASON AS _log_delivery_status ABOVE: the accessor is in-process to
        the server, so a QA runner — which boots this agent as a subprocess —
        can never call it and gets `None` no matter how healthy the node is.
        Logging it here is the only way that value reaches a log tail.

        Why this value and not a derived one: "does this node hold offerable
        carriers" cannot be answered from the wire (carriers ride the
        Attestation plane, so there is no Trace envelope kind to count), nor
        from `trace_events.cohort_scope` (a read-time projection in a different
        table, downstream of the attestation's own scope), nor from a
        substring match on the dimension (`trace:` and `trace_summary:` are
        different namespaces and `covers()` is a prefix test, so a loose
        `%trace:%` over-counts). persist's `storage_summary()` answers it, and
        `node_state()` carries that verbatim.

        Purely diagnostic; never disturbs the probe.
        """
        try:
            import json as _json

            import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

            ns = getattr(ciris_server, "node_state", None)
            if ns is None:
                logger.info("[TRACE-PLANE] phase=%s unavailable (ciris_server has no node_state accessor)", phase)
                return
            raw = ns()
            state = _json.loads(raw) if isinstance(raw, str) else raw
            plane = (state or {}).get("trace_plane")
            if plane is None:
                logger.info("[TRACE-PLANE] phase=%s absent (node_state carries no trace_plane)", phase)
                return
            logger.info("[TRACE-PLANE] phase=%s %s", phase, _json.dumps(plane, default=str))
        except Exception as exc:  # noqa: BLE001
            logger.debug("[TRACE-PLANE] phase=%s accessor error (non-fatal): %s", phase, exc)

    def _user_opted_into_traces() -> bool:
        """Did the OWNER opt in to trace replication? Consent is theirs to give.

        One reader of the opt-in signal, shared with every other consent path.
        """
        from ciris_engine.logic.services.governance.consent.trace_sharing import (
            owner_opted_into_trace_sharing,
        )

        return owner_opted_into_trace_sharing()

    def _try_author_consent(peer_key_id: str) -> bool:
        """Author the owner's trace-sharing consent; True once it lands.

        Refuses until the node is claimed, which is expected for the whole
        pre-claim part of the window — the claim happens later in the wizard, so
        a fixed-point attempt at boot is guaranteed to fail. Hence the retry.

        Goes through the one trace-sharing handle, so this authors the CAPTURE
        gate as well as the ship gate. Authoring only the latter was half the
        split that left `capture=True, replication=False` nodes sealing traces
        that never moved.
        """
        from ciris_engine.logic.services.governance.consent.trace_sharing import (
            grant_trace_sharing,
        )
        from ciris_engine.schemas.consent.trace_sharing import TraceConsentSource

        # require_opt_in=False: the caller already checked _user_opted_into_traces()
        # before reaching here, and both read the same signal.
        result = grant_trace_sharing(TraceConsentSource.DELIVERY_PROBE, require_opt_in=False)
        if result.complete:
            logger.info(
                "[DELIVERY-PROBE] owner consent AUTHORED for %s (capture=%s, ship=%s) — "
                "sealed traces can now promote",
                peer_key_id,
                result.capture_grant_id,
                result.peers_authored,
            )
            return True
        logger.debug(
            "[DELIVERY-PROBE] consent not yet complete for %s (capture=%s ship=%s errors=%s) — retrying",
            peer_key_id,
            result.capture_grant_id or "none",
            result.peers_authored or "none",
            result.errors,
        )
        return False

    def _envelopes_sent_total() -> Optional[int]:
        """Read round_diagnostics.envelopes_sent_total from delivery_status()
        (>=0.5.125). The tighter-pants terminal signal: delivery is CONFIRMED
        only when envelopes actually left, never on TX-side optimism. Returns
        None when the accessor is unavailable (older wheel) or unparsable —
        callers treat None as 'cannot confirm', not as zero."""
        try:
            import json as _json

            import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

            ds = getattr(ciris_server, "delivery_status", None)
            if ds is None:
                return None
            raw = ds()
            data = _json.loads(raw) if isinstance(raw, str) else raw
            sent = (data or {}).get("round_diagnostics", {}).get("envelopes_sent_total")
            return int(sent) if sent is not None else None
        except Exception:  # noqa: BLE001 — diagnostics only
            return None

    def _probe() -> None:
        import time as _t

        try:
            import json as _json

            canon = _json.loads(engine.list_canonical_servers() or "[]")
            if not canon:
                return
            ckey = canon[0].get("key_id")
            if not ckey:
                return
            # Rooting is announce-driven and observed at ~130s on the canonical
            # (the agent cold-start-roots the peer off its RNS announce, not off a
            # reply), so a 120s window expired ~10s BEFORE rooting and reported a
            # false "did not root". Give rooting 240s.
            root_deadline = 240
            waited = 0
            rooted = False
            while waited < root_deadline:
                _t.sleep(10)
                waited += 10
                try:
                    rooted = bool(edge.knows_peer(ckey))
                except Exception:  # noqa: BLE001
                    rooted = False
                if rooted:
                    logger.info("[DELIVERY-PROBE] canonical %s ROOTED after ~%ss", ckey, waited)
                    break
            if not rooted:
                logger.info("[DELIVERY-PROBE] canonical %s did not root within %ss", ckey, root_deadline)
                _log_delivery_status("did-not-root")
                _log_trace_plane("did-not-root")
                return

            # KEX does NOT appear at rooting — it lands only once an inbound
            # IdentityOccurrence anti-entropy round from the peer completes (which
            # needs the peer to REPLY over a rooted return path). The 0.5.131 run
            # proved a one-shot 180s window is too eager: it declared "peer not
            # replying / responder unwired, NOT the agent" 80s BEFORE the dial-cache
            # warm-up self-healed (CIRISEdge#336 residual — both sides may dial a
            # stale cached dest for minutes before flipping to the routable one).
            # So: belt, suspenders, AND tighter pants —
            #   belt      — reprime on KEX stall (idempotent, CIRISServer#288) so the
            #               peer keeps getting fresh prime/KEX chances to heal its
            #               own dial cache the way we healed ours;
            #   suspenders — keep [DELIVERY-STATUS] LIVE through the whole delivery
            #               window instead of freezing at a give-up snapshot;
            #   tighter pants — the terminal verdict is envelopes_sent-based
            #               (ship-confirmed vs ship-unconfirmed), never TX-side
            #               optimism and never premature peer-blame.
            window_deadline = 900  # full delivery window (s) — mobile test-mode keeps the app alive this long
            status_cadence = 60  # live [DELIVERY-STATUS] emit cadence (s)

            # REPRIME EARLY, THEN SETTLE. A flat 180s cadence spends the first
            # three minutes of every window doing nothing, and a run that ends
            # at ~3 minutes therefore gets ONE attempt — which is what a live
            # QA run did: 141 rounds, zero inbound envelopes, KEX never landed,
            # window torn down before a second nudge. Reprime is idempotent
            # (CIRISServer#288), so the first one costs a dial and buys the
            # peer an early chance to heal its own cache; only after that does
            # the slow cadence make sense.
            reprimes_done = 0
            inbound_seen = False
            waited = 0
            kex_seen_at: Optional[int] = None
            last_status = 0
            last_reprime = 0
            _consent_authored = False
            while waited < window_deadline:
                _t.sleep(15)
                waited += 15
                if kex_seen_at is None:
                    try:
                        kex = edge.resolve_peer_kex_pubkeys(ckey)
                    except Exception as kex_exc:  # noqa: BLE001
                        kex = f"<error: {kex_exc}>"
                    if isinstance(kex, dict):
                        kex_seen_at = waited
                        logger.info(
                            "[DELIVERY-PROBE] canonical %s KEX PRESENT after ~%ss post-root — "
                            "IdentityOccurrence round synced; replication can now seal envelopes",
                            ckey,
                            waited,
                        )
                        _log_delivery_status("kex-present")
                        _log_trace_plane("kex-present")
                    elif should_reprime(waited, reprimes_done, last_reprime):
                        # KEX stall — reprime rather than give up. Warm-up dial-cache
                        # lag (CIRISEdge#336) means the peer may be dialing our stale
                        # dest for minutes; every reprime re-roots the canonical
                        # against current handles and gives its next round a fresh
                        # chance to route (mirror of the flip that healed OUR dials).
                        last_reprime = waited
                        reprimes_done += 1

                        # IS ANYTHING COMING BACK AT ALL? Two very different
                        # stalls wear the same "kex_present=false" label, and
                        # only one of them is worth waiting through:
                        #
                        #   inbound > 0 — rounds are flowing, the peer replies,
                        #                 KEX simply has not landed yet. Waiting
                        #                 is the right move; it self-heals.
                        #   inbound = 0 — the peer is not answering us at all.
                        #                 A canonical fail-closes on an unknown
                        #                 attesting_key_id and says nothing back
                        #                 (CIRISServer#488), so from here a
                        #                 structural refusal is indistinguishable
                        #                 from congestion and reprime will not
                        #                 fix it — our key is not registered
                        #                 there. Observed live: 141 rounds, 21
                        #                 Key envelopes sent, ZERO inbound, and
                        #                 the node never reached the canonical.
                        try:
                            _m = edge.metrics_snapshot() or {}
                            _recv = sum((_m.get("envelopes_received_total") or {}).values())
                            inbound_seen = inbound_seen or _recv > 0
                            if peer_is_silent(_recv, reprimes_done):
                                logger.warning(
                                    "[DELIVERY-PROBE] canonical %s: %ss post-root, %d reprimes, and ZERO "
                                    "envelopes received from ANY peer. The peer is not replying — which is "
                                    "what a fail-closed refusal looks like from this side when the canonical "
                                    "holds no key for us (CIRISServer#488). Reprime cannot fix that; the key "
                                    "has to be registered there.",
                                    ckey,
                                    waited,
                                    reprimes_done,
                                )
                            else:
                                logger.info(
                                    "[DELIVERY-PROBE] canonical %s: %ss post-root, %d reprimes, %d envelopes "
                                    "received — the peer IS replying, so KEX has not landed yet rather than "
                                    "being refused. Waiting.",
                                    ckey,
                                    waited,
                                    reprimes_done,
                                    _recv,
                                )
                        except Exception as _m_exc:  # noqa: BLE001 — diagnostics only
                            logger.debug("[DELIVERY-PROBE] metrics_snapshot unavailable: %s", _m_exc)
                        try:
                            import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

                            rp = getattr(ciris_server, "reprime_federation_delivery", None)
                            if rp is not None:
                                n = rp()
                                logger.info(
                                    "[DELIVERY-PROBE] canonical %s KEX still None at %ss post-root — repriming "
                                    "(likely dial-cache warm-up on one side, CIRISEdge#336; %s target(s) re-seeded)",
                                    ckey,
                                    waited,
                                    n,
                                )
                        except Exception as rp_exc:  # noqa: BLE001
                            logger.debug("[DELIVERY-PROBE] reprime attempt failed (non-fatal): %s", rp_exc)
                # The owner's consent grant is a PRECONDITION for any envelope
                # to exist: promote_consented_backlog only lifts a sealed trace
                # out of (cohort_scope=self, tier=local) when a live grant covers
                # its dimension. Since 0.5.146 the substrate correctly refuses to
                # author that grant on the owner's behalf, and 0.5.147's
                # in-process entry point refuses on an UNCLAIMED node — which the
                # node always is at bind time, because the claim happens later in
                # the wizard.
                #
                # So retry it on this loop instead of at a fixed point in boot:
                # the fold cannot know when the claim lands, and a one-shot
                # attempt at the only moment it is guaranteed to fail is worse
                # than none. Idempotent, and stops as soon as it takes.
                # GATED ON THE USER'S OPT-IN. The substrate stopped
                # boot-authoring consent in 0.5.146 precisely because consent is
                # the owner's act, not the fabric's — and this loop would have
                # quietly reintroduced that: it fires whenever the node is
                # CLAIMED, and claiming a node is not consenting to replicate
                # your reasoning traces off it.
                #
                # The wizard's own HTTP call cannot carry the intent (POST
                # /v1/federation/consent 404s in the fold by construction), so
                # the opt-in is read from the accord-metrics adapter, which is
                # where the wizard's "Send traces" choice lands.
                if not _consent_authored and _user_opted_into_traces():
                    _consent_authored = _try_author_consent(ckey)

                # tighter pants: terminal condition is envelopes actually SENT
                sent = _envelopes_sent_total()
                if sent and sent > 0:
                    logger.info(
                        "[DELIVERY-PROBE] canonical %s SHIP CONFIRMED — envelopes_sent_total=%s at ~%ss post-root",
                        ckey,
                        sent,
                        waited,
                    )
                    _log_delivery_status("ship-confirmed")
                    _log_trace_plane("ship-confirmed")
                    return
                if waited - last_status >= status_cadence:
                    last_status = waited
                    _phase = "kex-present-await-ship" if kex_seen_at is not None else "kex-none-repriming"
                    _log_delivery_status(_phase)
                    _log_trace_plane(_phase)
            logger.info(
                "[DELIVERY-PROBE] canonical %s window closed after %ss post-root with SHIP UNCONFIRMED "
                "(kex=%s, envelopes_sent=0). Do not assume a peer fault: the CIRISEdge#336 dial-cache "
                "residual is symmetric — the peer may have been dialing our stale dest all window "
                "(explicit-hash dests cannot announce by design, so its cache heals only via our "
                "prime/replication contact). See CIRISAgent#927 for the reverse-path ledger.",
                ckey,
                window_deadline,
                "present" if kex_seen_at is not None else "none",
            )
            _log_delivery_status("window-closed-unconfirmed")
            _log_trace_plane("window-closed-unconfirmed")
        except Exception as exc:  # noqa: BLE001 — pure diagnostics, never disturb boot
            logger.debug("[DELIVERY-PROBE] probe error (non-fatal): %s", exc)

    def _sink_health() -> None:
        """RUST-SINK HEALTH SENTINEL (own thread; never delays the probe).

        Judge the rust tracing file ~60s into the boot. A 0-byte
        ciris-server.log at that point means every compose/keyring/edge
        diagnostic is going nowhere — the exact condition that kept the 2.9.7
        Android compose-hang dark — so say it LOUDLY in the python log, where
        every future pull-logs will carry the verdict.
        """
        try:
            import glob as _glob
            import time as _t2

            _t2.sleep(60)
            _home = os.environ.get("CIRIS_HOME") or os.environ.get("CIRIS_DATA_DIR")
            if not _home:
                return
            _rust_logs = sorted(_glob.glob(os.path.join(_home, "logs", "ciris-server.log*")))
            _sizes = {os.path.basename(p): os.path.getsize(p) for p in _rust_logs}
            _dated = {n: s for n, s in _sizes.items() if not n.endswith(".boot")}
            if _dated and all(s == 0 for s in _dated.values()):
                logger.warning(
                    "[RUST-SINK] DARK — rust tracing files exist but carry 0 bytes at t+60s (%s). "
                    "Compose/keyring/edge diagnostics are being LOST (init_tracing sink not receiving "
                    "writes on this platform). Debug via the python-side probes only.",
                    _sizes,
                )
            elif _rust_logs:
                logger.info("[RUST-SINK] healthy at t+60s: %s", _sizes)
        except Exception as _sink_exc:  # noqa: BLE001
            logger.debug("[RUST-SINK] health check failed (non-fatal): %s", _sink_exc)

    threading.Thread(target=_probe, name="delivery-rooting-probe", daemon=True).start()
    threading.Thread(target=_sink_health, name="rust-sink-health", daemon=True).start()


def _seed_bootstrap_peers_into_edge(seeder: Optional[Any], edge: Any) -> None:
    """Hook: push canonical peers into Edge's bootstrap-peer set.

    TODO CIRISEdge#46 — pass bootstrap_peers to init_edge_runtime when
    Edge 1.0 lands. Today Edge 0.13.1 accepts ``bootstrap_peers`` only
    as a list of transport-hint strings via the CIRIS_EDGE_BOOTSTRAP_PEERS
    env var (already wired above). Once Edge 1.0 exposes a typed
    bootstrap-peer surface (key_id + pubkey + transport_hint), this
    hook will translate ``seeder.list_peers(canonical_only=True)`` into
    that surface and apply it.
    """
    logger.debug(
        "TODO CIRISEdge#46 — pass bootstrap_peers to init_edge_runtime when 1.0 lands "
        "(stub no-op, seeder=%s, edge=%s)",
        type(seeder).__name__ if seeder is not None else "None",
        type(edge).__name__ if edge is not None else "None",
    )


def register_organic_announce_subscriber(seeder: Optional[Any]) -> None:
    """Hook: subscribe the seeder to Edge ANNOUNCE events.

    TODO CIRISEdge#46 — subscribe to recent_events ANNOUNCE stream when
    Edge 1.0 lands. The wire shape will be (key_id, pubkey, alias?)
    per ANNOUNCE, and this hook will forward each to
    ``seeder.record_organic_peer()``.
    """
    logger.debug(
        "TODO CIRISEdge#46 — subscribe to recent_events ANNOUNCE stream when Edge 1.0 lands (stub no-op, seeder=%s)",
        type(seeder).__name__ if seeder is not None else "None",
    )


def get_edge() -> Any:
    """Return the live Edge instance. Raises if not initialized."""
    if _edge is None:
        if _edge_disabled():
            raise RuntimeError(
                "Edge runtime is disabled (PYTEST_CURRENT_TEST or CIRIS_EDGE_DISABLED set). "
                "Callers must guard with edge_runtime.is_available()."
            )
        raise RuntimeError("Edge runtime not initialized. Call initialize_edge_runtime() during boot.")
    return _edge


def try_get_edge() -> Optional[Any]:
    """Return the Edge instance if initialized, else None (no exception)."""
    return _edge


def is_available() -> bool:
    """True if Edge runtime is live and queryable."""
    return _edge is not None


def get_federation_address() -> Optional[str]:
    """Return the local agent's federation key_id, or None if Edge unavailable."""
    if _edge is None:
        return None
    try:
        # ciris_edge is untyped (no py.typed marker yet) so
        # `_edge.signer_key_id()` is inferred Any. Narrow to Optional[str]
        # before returning to satisfy mypy [no-any-return].
        key_id: Optional[str] = _edge.signer_key_id()
        return key_id
    except Exception as e:
        logger.warning("Edge signer_key_id() failed: %s", e)
        return None


def reset_edge_runtime() -> None:
    """Test-only: clear the singleton. Production code MUST NOT call this."""
    global _edge
    _edge = None
