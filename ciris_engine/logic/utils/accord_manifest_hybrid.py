"""The accord manifest's hybrid signature, checked once the persist engine is up.

Eric's decision (2026-11-08, via the CC): A1, his accord-holder key, signs the
accord manifest in the bound hybrid form of CC 5.3.2.4.3.1. Ed25519 covers the
manifest bytes; ML-DSA-65 covers the manifest bytes followed by the Ed25519
signature. The 2025 WA root that signs ``accord_manifest.sig`` retires once
that signature ships.

The check can't run at import: nothing there verifies ML-DSA-65. It runs as
soon as the engine is wired (``initialize_database``), which is before any
decision, and that ordering is what the CC asks for. A1's key comes from the
federation directory, where persist's genesis bundle seeds it as a hybrid key
record, so a record without its ML-DSA-65 half fails.

Until the hybrid signature ships, the import-time Ed25519 check
(``constants._verify_accord_manifest_signature``) is the one that applies; a
release that reads both forms is the candidate before the switch (CC 2.6.1.8).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional, Tuple

from ciris_engine.logic.utils.constants import ACCORD_SEED_DIR

logger = logging.getLogger(__name__)

#: Keys allowed to sign the accord manifest: the pinned trust set (CC 4.4.3.8).
ACCORD_MANIFEST_SIGNERS = ("A1",)


def hybrid_signature_path(seed_dir: Optional[Path] = None) -> Path:
    return (seed_dir or ACCORD_SEED_DIR) / "accord_manifest.hybrid.json"


def _signer_keys(engine: Any, signer: str) -> Tuple[str, str]:
    raw = engine.lookup_public_key(signer)
    record = json.loads(raw) if raw else None
    if not isinstance(record, dict):
        raise RuntimeError(f"[ACCORD] {signer} is not in the federation directory")
    ed, pqc = record.get("pubkey_ed25519_base64"), record.get("pubkey_ml_dsa_65_base64")
    if not (isinstance(ed, str) and ed and isinstance(pqc, str) and pqc):
        raise RuntimeError(f"[ACCORD] {signer}'s key record has no ML-DSA-65 half; hybrid resolution fails closed")
    return ed, pqc


def verify_accord_manifest_hybrid(engine: Any, seed_dir: Optional[Path] = None) -> bool:
    """Verify the manifest's hybrid signature strictly. Returns False only when none ships yet.

    Raises RuntimeError on a signature that's present and fails, a signer outside
    the pinned set, or a signer with no hybrid key record: startup stops.
    """
    from ciris_engine.logic.utils import substrate_signing

    sig_path = hybrid_signature_path(seed_dir)
    if not sig_path.exists():
        logger.info("[ACCORD] No hybrid manifest signature yet; the WA-root signature applies until A1 signs")
        return False
    manifest = sig_path.parent / "accord_manifest.json"
    try:
        doc = json.loads(sig_path.read_text(encoding="utf-8"))
        signer = str(doc["signer_key_id"])
        ed_sig, pqc_sig = str(doc["ed25519_sig"]), str(doc["ml_dsa_65_sig"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"[ACCORD] Unreadable hybrid manifest signature: {type(exc).__name__}") from exc
    if signer not in ACCORD_MANIFEST_SIGNERS:
        raise RuntimeError(f"[ACCORD] {signer!r} is not a pinned accord manifest signer")
    ed_pub, pqc_pub = _signer_keys(engine, signer)
    try:
        substrate_signing.verify_hybrid_required(engine, manifest.read_bytes(), ed_sig, pqc_sig, ed_pub, pqc_pub)
    except Exception as exc:
        raise RuntimeError(
            f"[ACCORD] HYBRID MANIFEST SIGNATURE FAILED ({signer}): {type(exc).__name__}: {exc}. "
            "Refusing to run on unverified accord text."
        ) from exc
    logger.info("[ACCORD] Manifest hybrid signature verified (%s, Ed25519 + ML-DSA-65)", signer)
    return True
