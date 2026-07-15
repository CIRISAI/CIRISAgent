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
        import ciris_server as _cs

        _init_tracing = getattr(_cs, "init_tracing", None)
        if _init_tracing is not None:
            _trace_dir = os.environ.get("CIRIS_HOME") or os.environ.get("CIRIS_DATA_DIR")
            _log_dir = os.path.join(_trace_dir, "logs") if _trace_dir else None
            _filter = os.environ.get("RUST_LOG") or "info,ciris_server=debug,ciris_edge=debug,ciris_persist=info"
            try:
                _init_tracing(log_dir=_log_dir, filter=_filter)
            except TypeError:  # pre-0.5.116 bare signature
                _init_tracing()
    except Exception as _trace_exc:  # noqa: BLE001 — observability must never block boot
        logger.debug("ciris_server.init_tracing unavailable/failed (non-fatal): %s", _trace_exc)

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
                return

            # KEX does NOT appear at rooting — it lands only once an inbound
            # IdentityOccurrence anti-entropy round from the peer completes (which
            # needs the peer to REPLY over a rooted return path). So poll KEX for a
            # window AFTER rooting rather than sampling once. If it never flips to
            # PRESENT, the peer is not answering our replication rounds — the
            # "rooted but 0 envelopes" blocker is on the peer's reply path, not here.
            kex_deadline = 180
            kex_waited = 0
            while kex_waited < kex_deadline:
                try:
                    kex = edge.resolve_peer_kex_pubkeys(ckey)
                except Exception as kex_exc:  # noqa: BLE001
                    kex = f"<error: {kex_exc}>"
                if isinstance(kex, dict):
                    logger.info(
                        "[DELIVERY-PROBE] canonical %s KEX PRESENT after ~%ss post-root — "
                        "IdentityOccurrence round synced; replication can now seal envelopes",
                        ckey,
                        kex_waited,
                    )
                    return
                _t.sleep(15)
                kex_waited += 15
            logger.info(
                "[DELIVERY-PROBE] canonical %s ROOTED but KEX still None after %ss post-root — "
                "the peer is not replying to our anti-entropy rounds (IdentityOccurrence never syncs → "
                "resolve_peer_kex_pubkeys None → replication cannot seal). Blocker is the peer's "
                "replication reply path (peer roots us only as advisory, or its responder is unwired), "
                "NOT the agent.",
                ckey,
                kex_deadline,
            )
        except Exception as exc:  # noqa: BLE001 — pure diagnostics, never disturb boot
            logger.debug("[DELIVERY-PROBE] probe error (non-fatal): %s", exc)

    threading.Thread(target=_probe, name="delivery-rooting-probe", daemon=True).start()


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
