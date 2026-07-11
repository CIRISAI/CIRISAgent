"""Publish the node's self-occurrence with derived content-encryption pubkeys.

The last trace-flow domino (CIRISServer 0.5.99): agent = node = one keypair, so
the node's Ed25519 seed is the single root. On every boot (idempotent), the node:

  1. derives its content-enc keypair (x25519 + ML-KEM-768) from the node Ed25519
     seed via the verify FFI ``ciris_verify_self_enc_derive`` — deterministic, so
     the same seed re-derives identically after any wipe/restore (zero rekey);
  2. publishes its self-occurrence (``identity_key_id == occurrence_key_id ==
     node key_id``) into persist's federation directory via
     ``engine.put_identity_occurrence_json`` with the derived ``encryption_pubkeys``.

Both ends must publish: the sender so replies can reach it, the canonical (Node A)
so the sender can resolve its KEX and seal traces to it. ``resolve_peer_kex_pubkeys``
reads exactly this occurrence block — until both sides publish, it returns None
and the delivery controller has "canonical rooted but 0 envelopes / KEX=None".

Must run AFTER the node key is registered (there's an FK), so it's called at
end-of-boot / after the ownership claim + node fold. Idempotent on
(identity_key_id, occurrence_key_id) — safe to call every boot.

Gotchas (per the spec):
  - The enc keypair MUST derive from the node key_id's Ed25519 seed; a different
    seed silently breaks decrypt (published pubkeys won't match the respond
    secrets). On a folded node the server adopts+seals ``identity/ed25519.seed``
    → ``ed25519.seed.migrated``; source the same 32 bytes the node was minted with.
  - device_class MUST be one of {phone, laptop, agent} for admission (we use "agent").
  - Republish is free; a wipe/restore re-derives identically → sealability restored.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEVICE_CLASS = "agent"  # admission gate: {phone, laptop, agent}


def _node_ed25519_seed() -> Optional[bytes]:
    """The 32-byte Ed25519 seed backing the node's key_id.

    On a folded node this is the seed the edge signer is minted from
    (``identity/ed25519.seed`` → ``.migrated`` after the substrate adopts it).
    Sourced from the edge's keyring so it is byte-identical to what the node
    key_id was minted with — deriving from any other seed silently breaks the
    KEX (published pubkeys won't match the respond secrets).
    """
    try:
        from ciris_engine.logic.runtime.edge_runtime import get_edge

        edge = get_edge()
    except Exception as exc:  # noqa: BLE001
        logger.debug("self-occurrence: edge unavailable for seed: %s", exc)
        return None
    # 0.5.99 exposes the node signer seed export; probe the stable accessors.
    for accessor in ("signer_ed25519_seed", "transport_identity_ed25519_seed", "node_ed25519_seed"):
        fn = getattr(edge, accessor, None)
        if callable(fn):
            try:
                seed = fn()
                if isinstance(seed, (bytes, bytearray)) and len(seed) == 32:
                    return bytes(seed)
                if isinstance(seed, (list, tuple)) and len(seed) == 32:
                    return bytes(seed)
            except Exception as exc:  # noqa: BLE001
                logger.debug("self-occurrence: %s failed: %s", accessor, exc)
    return None


def _derive_enc_pubkeys(seed: bytes) -> Optional[dict]:
    """Derive {x25519_pub_base64, ml_kem_768_pub_base64} from the node seed.

    Calls the verify FFI ``ciris_verify_self_enc_derive({"ed25519_seed":[...]})``.
    The Python binding for this ships with 0.5.99 — return None (no-op) until it
    is exposed, so pre-0.5.99 boots don't error.
    """
    import ciris_verify as cv  # type: ignore[import-not-found, import-untyped, unused-ignore]

    derive = getattr(cv, "ciris_verify_self_enc_derive", None) or getattr(cv, "self_enc_derive", None)
    if derive is None:
        logger.info(
            "self-occurrence: verify self-enc derive not exposed in this wheel (need ciris-server >=0.5.99); "
            "occurrence NOT published — resolve_peer_kex_pubkeys stays None until the wheel ships the derive."
        )
        return None
    try:
        out = derive({"ed25519_seed": list(seed)})
        out = json.loads(out) if isinstance(out, (str, bytes)) else out
        # Keep ONLY the public halves — never persist/publish the secret halves.
        return {
            "x25519_pub_base64": out["x25519_pub_base64"],
            "ml_kem_768_pub_base64": out["ml_kem_768_pub_base64"],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("self-occurrence: enc-key derive failed: %s", exc)
        return None


def publish_self_occurrence(engine: Any, node_key_id: str, asserted_at: str) -> bool:
    """Publish (idempotent) the node's self-occurrence with derived enc pubkeys.

    Returns True on a confirmed publish (self-check finds encryption_pubkeys),
    False if skipped (primitives not yet in the wheel) or on best-effort failure.
    Never raises — a failed publish must not break boot (delivery degrades to
    'rooted but 0 envelopes', not a crash).
    """
    try:
        seed = _node_ed25519_seed()
        if seed is None:
            logger.info("self-occurrence: node Ed25519 seed unavailable — skipping publish")
            return False
        enc = _derive_enc_pubkeys(seed)
        if enc is None:
            return False  # already logged (pre-0.5.99 or derive failure)

        payload = {
            "identity_key_id": node_key_id,
            "occurrence_key_id": node_key_id,  # agent = node = one keypair
            "device_class": _DEVICE_CLASS,
            "hardware_attestation": None,
            "asserted_at": asserted_at,
            "valid_until": None,
            "encryption_pubkeys": enc,  # 0.5.99 occurrence field the sealer reads
        }
        engine.put_identity_occurrence_json(json.dumps(payload))

        # Self-check (spec step 2): the occurrence is stored with enc pubkeys.
        raw = engine.lookup_identity_for_occurrence_json(node_key_id)
        occ = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        has_enc = bool((occ or {}).get("encryption_pubkeys")) if isinstance(occ, dict) else False
        if has_enc:
            logger.info(
                "self-occurrence: PUBLISHED node %s self-occurrence with encryption_pubkeys "
                "(peers can now resolve our KEX + seal to us)",
                node_key_id,
            )
            return True
        logger.warning("self-occurrence: published but self-check did not find encryption_pubkeys for %s", node_key_id)
        return False
    except Exception as exc:  # noqa: BLE001 — pure best-effort, never break boot
        logger.warning("self-occurrence: publish failed (non-fatal): %s: %s", type(exc).__name__, str(exc)[:200])
        return False
