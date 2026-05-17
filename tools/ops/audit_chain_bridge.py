#!/usr/bin/env python3
"""Bridge legacy ciris_audit.db chain into persist's cirislens_audit_log.

Pre-A3 commit for CIRIS 2.9.0 audit absorption — see CIRISAgent#763
Lane A (A0b row in the waterfall).

Reads the legacy audit chain's terminal entry from `ciris_audit.db`,
assembles a single "genesis bridge" entry per the persist team's
`docs/AUDIT_CHAIN_BRIDGE.md` §1 spec, signs the canonical bytes via
CIRISVerify's TPM-backed Ed25519 key, and submits via persist's typed
`audit_record_entry`. The bridge entry has `sequence_number = 1` and a
non-zero `prev_hash` derived from the legacy chain's terminal state;
persist's `audit_verify_chain` flags the row with
`ChainBreakReason::GenesisPrevHashNotZero` — that's a feature, not a
bug: it signals "this chain bridges to an upstream chain" rather than
"this is a fresh genesis."

Canonical-bytes computation is delegated entirely to persist's v1.5.4
helpers (`audit_canonicalize_for_hash`, `audit_canonicalize_for_signing`)
— the agent never re-implements persist's canonicalization rule.

Idempotent: gated by a sentinel file (`.audit_bridged`) next to the
engine DB. To re-run in dev, remove the sentinel. Re-running in prod
is destructive (a second bridge entry would fail persist's sequence-
monotonicity check).

ServiceInitializer integration: invoked from `_bootstrap_persist_engine`
after A0a graph migration completes, before the persist engine is wired
into the persistence module.

Usage:
    python -m tools.ops.audit_chain_bridge
    python -m tools.ops.audit_chain_bridge --engine-db PATH --audit-db PATH
    python -m tools.ops.audit_chain_bridge --dry-run
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("audit_chain_bridge")


@dataclass
class BridgeResult:
    bridge_id: str
    legacy_terminal_seq: int
    legacy_terminal_hash: str
    legacy_db_sha256: str
    entry_hash_b64: str
    tenant_id: str
    signing_key_id: str
    skipped_reason: Optional[str] = None


def _sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_legacy_terminal(audit_db: Path) -> tuple[int, str, str]:
    """Return (sequence_number, entry_hash, event_id) of the last row of
    the legacy ciris_audit.db chain. Used to seed the bridge entry's
    prev_hash + payload.
    """
    if not audit_db.exists():
        raise FileNotFoundError(f"legacy audit DB not found: {audit_db}")
    con = sqlite3.connect(str(audit_db))
    try:
        row = con.execute(
            "SELECT sequence_number, entry_hash, event_id FROM audit_log "
            "ORDER BY sequence_number DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"legacy audit_log is empty in {audit_db} — nothing to bridge"
            )
        return int(row[0]), str(row[1]), str(row[2])
    finally:
        con.close()


def _derive_prev_hash_b64(legacy_root_hash: str, legacy_root_id: str) -> str:
    """Bridge prev_hash derivation per AUDIT_CHAIN_BRIDGE.md §1.2.

    `prev_hash = sha256(canonical_json({legacy_chain_root_hash,
    legacy_chain_root_id}))` — deterministic from the legacy chain's
    terminal state so anyone holding the archived legacy DB can
    recompute and verify the handoff.
    """
    marker = json.dumps(
        {
            "legacy_chain_root_hash": legacy_root_hash,
            "legacy_chain_root_id": legacy_root_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return base64.b64encode(hashlib.sha256(marker.encode("utf-8")).digest()).decode()


def _get_signer_material() -> tuple[bytes, str, str]:
    """Return (pubkey_bytes, actor_id_b64, signing_key_id) from CIRISVerify.

    The agent's TPM-backed Ed25519 key is the source of truth for
    audit-chain signatures; we register its pubkey in
    `accord_public_keys` via C3 so audit verifiers can resolve
    `signing_key_id` -> pubkey.
    """
    import os
    from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
        get_verifier,
    )

    verifier = get_verifier()
    if verifier is None or not hasattr(verifier, "get_ed25519_public_key_sync"):
        raise RuntimeError(
            "CIRISVerify verifier unavailable — cannot bridge audit chain "
            "without the agent's signing key"
        )
    pubkey_bytes: bytes = verifier.get_ed25519_public_key_sync()
    if not pubkey_bytes:
        raise RuntimeError(
            "CIRISVerify returned empty pubkey — key may not be initialized"
        )
    actor_id_b64 = base64.b64encode(pubkey_bytes).decode("ascii")
    agent_id = os.environ.get("CIRIS_AGENT_ID")
    if agent_id:
        signing_key_id = f"agent-{agent_id}"
    else:
        fingerprint = hashlib.sha256(pubkey_bytes).hexdigest()[:12]
        signing_key_id = f"agent-{fingerprint}"
    return pubkey_bytes, actor_id_b64, signing_key_id


def _sign_with_verifier(canonical_bytes: bytes) -> bytes:
    """Sign `canonical_bytes` with CIRISVerify's TPM-backed Ed25519 key.

    The signer abstraction is at `ciris_engine.logic.audit.signing_protocol`
    — the same path the audit handler uses for normal entries.
    """
    from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
        get_verifier,
    )

    verifier = get_verifier()
    sig: bytes = verifier.sign_ed25519_sync(canonical_bytes)
    return sig


def _resolve_tenant_id() -> str:
    """Tenant ID per AUDIT_CHAIN_BRIDGE.md §2.1.

    Prefer the env var `CIRIS_AGENT_ID` (stable per-deployment value);
    otherwise derive from the pubkey fingerprint.
    """
    import os
    agent_id = os.environ.get("CIRIS_AGENT_ID")
    return agent_id if agent_id else "agent-default"


def run(
    engine_db: Path,
    audit_db: Path,
    signing_key_id: Optional[str] = None,
    dry_run: bool = False,
    engine: Optional[Any] = None,
) -> BridgeResult:
    """Bridge the legacy audit chain into persist's cirislens_audit_log.

    Args:
        engine_db: Path to ciris_engine.db (where persist writes the bridge).
        audit_db: Path to ciris_audit.db (legacy chain we read terminal from).
        signing_key_id: Override for the agent's signing_key_id. If None,
            derived from CIRISVerify pubkey fingerprint.
        dry_run: If True, build + sign + report the entry but don't submit.
        engine: Optional pre-constructed persist Engine (ServiceInitializer
            bootstrap passes the wired engine here so we don't construct
            a second instance — see migrate_to_persist.run() docstring
            for the one-Engine-per-process rationale).
    """
    if not engine_db.exists():
        raise FileNotFoundError(f"engine DB not found: {engine_db}")
    if not audit_db.exists():
        raise FileNotFoundError(f"legacy audit DB not found: {audit_db}")

    legacy_seq, legacy_hash, legacy_id = _read_legacy_terminal(audit_db)
    legacy_db_sha = _sha256_hex(audit_db)
    pubkey_bytes, actor_id_b64, derived_key_id = _get_signer_material()
    key_id = signing_key_id or derived_key_id
    tenant_id = _resolve_tenant_id()

    prev_hash_b64 = _derive_prev_hash_b64(legacy_hash, legacy_id)
    bridge_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    entry: dict[str, Any] = {
        "entry_id": bridge_id,
        "sequence_number": 1,
        "tenant_id": tenant_id,
        "actor_id": actor_id_b64,
        # `chain_bridge` would be the right action_type but isn't in the
        # CHECK constraint yet (AUDIT_CHAIN_BRIDGE.md §1.3 interim guidance).
        # Use `system_event` + `subject_kind = "audit_chain"` so the bridge
        # is structurally distinguishable; promote when persist's V0XX adds
        # the enum value.
        "action_type": "system_event",
        "subject_kind": "audit_chain",
        "subject_id": "ciris_audit_v1",
        "payload": json.dumps(
            {
                "legacy_chain_root_hash": legacy_hash,
                "legacy_chain_root_id": legacy_id,
                "legacy_chain_scheme": "ciris_audit_v1",
                "legacy_terminal_seq": legacy_seq,
                "legacy_db_sha256": legacy_db_sha,
                "bridge_reason": "ciris_agent_2_9_0_cutover",
                "archived_at": now_iso,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        "prev_hash": prev_hash_b64,
        "recorded_at": now_iso,
        "signing_key_id": key_id,
        "entry_hash": "",
        "signature": "",
    }

    if engine is None:
        from ciris_persist import Engine  # type: ignore[import-untyped]
        engine = Engine(f"sqlite:///{engine_db.resolve()}", key_id)

    # v1.5.4 helpers: persist owns canonicalization; agent signs externally.
    canonical_for_hash = engine.audit_canonicalize_for_hash(json.dumps(entry))
    hash_input = canonical_for_hash if isinstance(canonical_for_hash, bytes) else canonical_for_hash.encode()
    entry["entry_hash"] = base64.b64encode(hashlib.sha256(hash_input).digest()).decode()

    canonical_for_sign = engine.audit_canonicalize_for_signing(json.dumps(entry))
    sign_input = canonical_for_sign if isinstance(canonical_for_sign, bytes) else canonical_for_sign.encode()
    sig_bytes = _sign_with_verifier(sign_input)
    entry["signature"] = base64.b64encode(sig_bytes).decode()

    if dry_run:
        logger.info(
            "DRY RUN: bridge_id=%s tenant=%s key_id=%s legacy_seq=%d entry_hash=%s...",
            bridge_id, tenant_id, key_id, legacy_seq, entry["entry_hash"][:24],
        )
        return BridgeResult(
            bridge_id=bridge_id,
            legacy_terminal_seq=legacy_seq,
            legacy_terminal_hash=legacy_hash,
            legacy_db_sha256=legacy_db_sha,
            entry_hash_b64=entry["entry_hash"],
            tenant_id=tenant_id,
            signing_key_id=key_id,
            skipped_reason="dry_run",
        )

    engine.audit_record_entry(json.dumps(entry))
    logger.info(
        "audit chain bridged: bridge_id=%s tenant=%s legacy_seq=%d legacy_hash=%s",
        bridge_id, tenant_id, legacy_seq, legacy_hash[:16] + "...",
    )

    return BridgeResult(
        bridge_id=bridge_id,
        legacy_terminal_seq=legacy_seq,
        legacy_terminal_hash=legacy_hash,
        legacy_db_sha256=legacy_db_sha,
        entry_hash_b64=entry["entry_hash"],
        tenant_id=tenant_id,
        signing_key_id=key_id,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--engine-db",
        type=Path,
        default=Path("data/ciris_engine.db"),
        help="Path to ciris_engine.db (default: data/ciris_engine.db)",
    )
    parser.add_argument(
        "--audit-db",
        type=Path,
        default=Path("data/ciris_audit.db"),
        help="Path to legacy ciris_audit.db (default: data/ciris_audit.db)",
    )
    parser.add_argument(
        "--signing-key-id",
        default=None,
        help="Override signing_key_id (default: derived from CIRISVerify pubkey)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build + sign + report the entry; do not call audit_record_entry",
    )
    parser.add_argument(
        "--sentinel",
        type=Path,
        default=None,
        help="Path to bridge sentinel file (default: <engine-db parent>/.audit_bridged)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore sentinel file (re-run bridge). Dev only — re-running in "
        "prod will fail persist's sequence-monotonicity check.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    sentinel = args.sentinel or args.engine_db.parent / ".audit_bridged"
    if sentinel.exists() and not args.force:
        logger.info("sentinel %s exists; bridge already ran. Use --force to re-run.", sentinel)
        return 0

    try:
        result = run(
            engine_db=args.engine_db,
            audit_db=args.audit_db,
            signing_key_id=args.signing_key_id,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        logger.exception("audit chain bridge failed: %s", exc)
        return 1

    if not args.dry_run:
        sentinel.write_text(
            json.dumps(
                {
                    "bridge_id": result.bridge_id,
                    "legacy_terminal_seq": result.legacy_terminal_seq,
                    "legacy_terminal_hash": result.legacy_terminal_hash,
                    "legacy_db_sha256": result.legacy_db_sha256,
                    "entry_hash_b64": result.entry_hash_b64,
                    "tenant_id": result.tenant_id,
                    "signing_key_id": result.signing_key_id,
                }
            )
        )
        logger.info("sentinel written: %s", sentinel)

    return 0


if __name__ == "__main__":
    sys.exit(main())
