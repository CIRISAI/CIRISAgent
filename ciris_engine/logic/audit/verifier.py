"""Audit verifier — persist-substrate routed for 2.9.0.

Phase 3a (CIRISAgent#763): the verifier no longer touches sqlite3. All
chain integrity walks go through persist's `audit_verify_chain` which
operates on `cirislens_audit_log` — the canonical store after the A3
write-path cutover.

Legacy methods (`verify_entry`, `verify_range`, `find_tampering_fast`,
`get_verification_report`, `verify_root_anchors`, `_verify_*_signatures`)
that walked the legacy `audit_log` table were removed in 2.9.0; production
had no callers. End-to-end chain verification is the only supported call.
"""

import json
import logging
from typing import List, Optional

from ciris_engine.protocols.services.lifecycle import TimeServiceProtocol
from ciris_engine.schemas.audit.verification import CompleteVerificationResult

logger = logging.getLogger(__name__)


def _audit_tenant_id() -> str:
    """Resolve the tenant_id under which persist records audit entries.

    Mirrors `audit_service._audit_tenant_id` — agents tag rows with
    `agent-default` when `CIRIS_AGENT_TENANT` is unset (production default).
    """
    import os

    return os.environ.get("CIRIS_AGENT_TENANT", "agent-default")


def _resolve_last_sequence(engine: object, tenant_id: str) -> Optional[int]:
    """Return the largest sequence_number in cirislens_audit_log for tenant.

    Calls persist's `audit_list_entries(filter_json, cursor, limit)` with
    a tenant-scoped filter; persist returns DESC by sequence so the first
    row carries the max.
    """
    list_fn = getattr(engine, "audit_list_entries", None)
    if list_fn is None:
        return None
    filter_json = json.dumps({"tenant_id": tenant_id})
    raw = list_fn(filter_json, None, 1)
    parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
    items = parsed.get("items") if isinstance(parsed, dict) else parsed
    if not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    seq = first.get("sequence_number")
    return int(seq) if seq is not None else None


class AuditVerifier:
    """Verify audit-chain integrity via persist's substrate."""

    def __init__(self, db_path: str, time_service: TimeServiceProtocol) -> None:
        # `db_path` retained for signature compat — persist owns the
        # connection pool.
        self.db_path = db_path
        self._time_service = time_service
        self._initialized = False

    def initialize(self) -> None:
        """No-op shim — persist owns the audit table; nothing to set up."""
        self._initialized = True

    def verify_complete_chain(self) -> CompleteVerificationResult:
        """Walk the full chain via persist's `audit_verify_chain`.

        Verified against a real 69-entry production fixture (clean +
        tampered cases). Persist's verifier combines hash + signature
        verification under a single outcome.
        """
        if not self._initialized:
            self.initialize()

        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        logger.info("Starting complete audit chain verification via persist")
        start_time = self._time_service.now()

        try:
            engine = get_persist_engine()
            if engine is None:
                raise RuntimeError("persist engine not wired")

            tenant_id = _audit_tenant_id()
            last_seq = _resolve_last_sequence(engine, tenant_id)

            end_time = self._time_service.now()
            verification_time = int((end_time - start_time).total_seconds() * 1000)

            if last_seq is None or last_seq < 1:
                return CompleteVerificationResult(
                    valid=True,
                    entries_verified=0,
                    hash_chain_valid=True,
                    signatures_valid=True,
                    verification_time_ms=verification_time,
                    summary="Empty audit log",
                )

            raw = engine.audit_verify_chain(tenant_id, 1, last_seq)
            payload = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            outcome = payload.get("outcome", {}) if isinstance(payload, dict) else {}
            walked = int(payload.get("entries_walked", 0)) if isinstance(payload, dict) else 0
            ok = isinstance(outcome, dict) and outcome.get("outcome") == "ok"

            errors: List[str] = []
            if not ok and isinstance(outcome, dict):
                at_seq = outcome.get("at_sequence")
                reason = outcome.get("reason", "unknown")
                detail = outcome.get("detail", "")
                errors.append(
                    f"chain break at sequence {at_seq}: {reason} ({detail})"
                )

            end_time = self._time_service.now()
            verification_time = int((end_time - start_time).total_seconds() * 1000)

            result = CompleteVerificationResult(
                valid=ok,
                entries_verified=walked,
                hash_chain_valid=ok,
                # Persist combines hash + signature verification under one
                # outcome; report the same value rather than synthesizing
                # a false distinction.
                signatures_valid=ok,
                verification_time_ms=verification_time,
                hash_chain_errors=errors,
                signature_errors=[],
            )

            if ok:
                logger.info(
                    f"Audit verification passed: {walked} entries in {verification_time}ms"
                )
            else:
                logger.error(f"Audit verification FAILED: {errors}")

            return result
        except Exception as e:
            end_time = self._time_service.now()
            verification_time = int((end_time - start_time).total_seconds() * 1000)
            logger.exception("persist audit_verify_chain failed")
            return CompleteVerificationResult(
                valid=False,
                entries_verified=0,
                hash_chain_valid=False,
                signatures_valid=False,
                verification_time_ms=verification_time,
                error=f"verify_complete_chain error: {type(e).__name__}: {e}",
            )
