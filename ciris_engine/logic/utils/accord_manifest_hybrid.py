"""The accord manifest's hybrid signature, checked once the persist engine is up.

Eric's decision (2026-11-08, via the CC; widened 2026-11-09): an accord holder
(A1, B1 or C1, the HUMANITY_ACCORD family) signs the accord manifest in the bound hybrid form of CC 5.3.2.4.3.1, over sha256 of a short JCS
statement of the manifest's size and sha256 (``accord_manifest_signed_bytes``).
Ed25519 covers those 32 bytes; ML-DSA-65 covers them followed by the Ed25519
signature.

The check can't run at import: nothing there verifies ML-DSA-65. It runs as
soon as the engine is wired (``initialize_database``), which is before any
decision, and that ordering is what the CC asks for. The holder's key comes from the
federation directory, where persist's genesis bundle seeds it as a hybrid key
record, so a record without its ML-DSA-65 half fails.

There is no fallback: the 2025 WA root that signed ``accord_manifest.sig``
is retired, and a missing signature stops startup (CC 3.1.2).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ciris_engine.logic.utils.constants import ACCORD_SEED_DIR

logger = logging.getLogger(__name__)

#: Keys allowed to sign the accord manifest: any HUMANITY_ACCORD holder (Eric,
#: 2026-11-09: "It can be anyone in the humanity accord family"). The ids are
#: pinned here AND the directory record must say identity_type "accord_holder"
#: (persist's baked genesis roster), so a stray record named B1 can't pass.
ACCORD_MANIFEST_SIGNERS = ("A1", "B1", "C1")
ACCORD_HOLDER_IDENTITY_TYPE = "accord_holder"

#: What a holder signs is a short typed statement of the manifest's digest, not the
#: file. A holder's Ed25519 half lives on a YubiKey, whose PKCS#11 EdDSA is single-part
#: and refuses multi-KB inputs (CKR_DATA_LEN_RANGE, CIRISVerify#113). The form is
#: the CC's own (3.1.2, SkillImportManifest canonical bytes v2): a JCS object with
#: a pinned "domain", lowercase-hex digests (2.6.3), the blob's size (5.3.2.5) and
#: "signer_identity"; the signed bytes are sha256(JCS(object)).
ACCORD_MANIFEST_DOMAIN = "ciris.accord_manifest.v1"


def accord_manifest_statement(manifest_bytes: bytes, signer: str) -> Dict[str, Any]:
    return {
        "domain": ACCORD_MANIFEST_DOMAIN,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_size": len(manifest_bytes),
        "signer_identity": signer,
    }


def accord_manifest_signed_bytes(manifest_bytes: bytes, signer: str) -> bytes:
    """The 32 bytes the holder signs: sha256 of the statement's JCS.

    signer_identity is inside them, so the signature can't be re-attributed to
    another holder.
    """
    from ciris_adapters.ciris_verify.ffi_bindings import jcs_canonicalize

    return hashlib.sha256(jcs_canonicalize(accord_manifest_statement(manifest_bytes, signer))).digest()


def hybrid_signature_path(seed_dir: Optional[Path] = None) -> Path:
    return (seed_dir or ACCORD_SEED_DIR) / "accord_manifest.hybrid.json"


def _signer_keys(engine: Any, signer: str) -> Tuple[str, str]:
    raw = engine.lookup_public_key(signer)
    record = json.loads(raw) if raw else None
    if not isinstance(record, dict):
        raise RuntimeError(f"[ACCORD] {signer} is not in the federation directory")
    if record.get("identity_type") != ACCORD_HOLDER_IDENTITY_TYPE:
        raise RuntimeError(f"[ACCORD] {signer}'s directory record is not an accord holder ({record.get('identity_type')!r})")
    ed, pqc = record.get("pubkey_ed25519_base64"), record.get("pubkey_ml_dsa_65_base64")
    if not (isinstance(ed, str) and ed and isinstance(pqc, str) and pqc):
        raise RuntimeError(f"[ACCORD] {signer}'s key record has no ML-DSA-65 half; hybrid resolution fails closed")
    return ed, pqc


def verify_accord_manifest_hybrid(engine: Any, seed_dir: Optional[Path] = None) -> bool:
    """Verify the manifest's hybrid signature strictly; returns True or raises.

    Raises RuntimeError on a missing signature, one that fails, a signer outside
    the pinned set, or a signer with no hybrid key record: startup stops.
    """
    from ciris_engine.logic.utils import substrate_signing

    sig_path = hybrid_signature_path(seed_dir)
    if not sig_path.exists():
        # No fallback: the 2025 WA root is retired (CC 3.1.2 — a missing signature stops the agent).
        raise RuntimeError(f"[ACCORD] No A1 hybrid manifest signature at {sig_path}; refusing to run on unverified accord text")
    manifest = sig_path.parent / "accord_manifest.json"
    try:
        doc = json.loads(sig_path.read_text(encoding="utf-8"))
        signer = str(doc["signer_key_id"])
        ed_sig, pqc_sig = str(doc["ed25519_sig"]), str(doc["ml_dsa_65_sig"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"[ACCORD] Unreadable hybrid manifest signature: {type(exc).__name__}") from exc
    if signer not in ACCORD_MANIFEST_SIGNERS:
        raise RuntimeError(f"[ACCORD] {signer!r} is not a pinned accord manifest signer")
    if doc.get("domain") != ACCORD_MANIFEST_DOMAIN:
        raise RuntimeError(f"[ACCORD] Hybrid manifest signature names domain {doc.get('domain')!r}, not {ACCORD_MANIFEST_DOMAIN!r}")
    manifest_bytes = manifest.read_bytes()
    # Size first, then digest (CC 5.3.2.5); the statement is always rebuilt from
    # the shipped bytes, never taken from the signature file.
    if doc.get("manifest_size") != len(manifest_bytes):
        raise RuntimeError(f"[ACCORD] HYBRID MANIFEST SIGNATURE FAILED ({signer}): manifest is {len(manifest_bytes)} bytes, signed for {doc.get('manifest_size')}")
    if doc.get("manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest():
        raise RuntimeError(f"[ACCORD] HYBRID MANIFEST SIGNATURE FAILED ({signer}): manifest sha256 differs from the signed statement")
    ed_pub, pqc_pub = _signer_keys(engine, signer)
    try:
        signed = accord_manifest_signed_bytes(manifest_bytes, signer)
        substrate_signing.verify_hybrid_required(engine, signed, ed_sig, pqc_sig, ed_pub, pqc_pub)
    except Exception as exc:
        raise RuntimeError(
            f"[ACCORD] HYBRID MANIFEST SIGNATURE FAILED ({signer}): {type(exc).__name__}: {exc}. "
            "Refusing to run on unverified accord text."
        ) from exc
    logger.info("[ACCORD] Manifest hybrid signature verified (%s, Ed25519 + ML-DSA-65)", signer)
    return True
