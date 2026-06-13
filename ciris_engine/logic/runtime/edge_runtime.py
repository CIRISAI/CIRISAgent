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

    try:
        # `import-not-found` covers the wheel-absent case (CI without the
        # ciris-edge wheel installed); `import-untyped` covers the case
        # where it IS installed but ships no py.typed marker (current
        # 1.0.x state); `unused-ignore` keeps both contexts green —
        # whichever of the first two doesn't apply in a given environment.
        import ciris_edge  # type: ignore[import-not-found, import-untyped, unused-ignore]
    except ImportError as e:
        raise RuntimeError(
            "ciris-edge not importable but is REQUIRED for 2.9.4+. Pin ciris-edge>=2.0.2,<3.0.0 in requirements.txt."
        ) from e

    identity_dir.mkdir(parents=True, exist_ok=True)
    identity_path = identity_dir / "edge_identity.rid"

    listen_addr = os.environ.get("CIRIS_EDGE_LISTEN_ADDR", "0.0.0.0:4242")
    bootstrap_peers_raw = os.environ.get("CIRIS_EDGE_BOOTSTRAP_PEERS", "")
    bootstrap_peers = [p.strip() for p in bootstrap_peers_raw.split(",") if p.strip()]

    from ciris_engine.logic.utils.agent_mode_broker import get_agent_mode_broker

    agent_mode_value = get_agent_mode_broker().current_mode().value

    try:
        edge = ciris_edge.ciris_edge.init_edge_runtime(
            engine,
            str(identity_path),
            listen_addr=listen_addr,
            bootstrap_peers=bootstrap_peers,
            agent_mode=agent_mode_value,
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
            engine.register_federation_key("agent", key_id)
            logger.info("Federation signer key registered with persist: %s", key_id)
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
