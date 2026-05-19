"""
Audit verifier for tamper detection in signed audit trail system.

Provides comprehensive verification of audit log integrity including
hash chains, digital signatures, and root anchoring.
"""

import logging
import sqlite3
from typing import List, Optional

from ciris_engine.logic.persistence.db.core import get_safe_sqlite_connection
from ciris_engine.logic.utils.jsondict_helpers import get_int, get_str
from ciris_engine.protocols.services.lifecycle import TimeServiceProtocol
from ciris_engine.schemas.audit.verification import (
    ChainSummary,
    CompleteVerificationResult,
    EntryVerificationResult,
    RangeVerificationResult,
    RootAnchorVerificationResult,
    SignatureVerificationResult,
    SigningKeyInfo,
    VerificationReport,
)
from ciris_engine.schemas.types import JSONDict

from .hash_chain import AuditHashChain
from .signature_manager import AuditSignatureManager

logger = logging.getLogger(__name__)


def _audit_tenant_id() -> str:
    """Resolve the tenant_id under which persist records audit entries.

    Mirrors `audit_service._write_to_persist_chain` — agents tag rows with
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
    import json

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
    """Verifies audit log integrity and detects tampering"""

    def __init__(self, db_path: str, time_service: TimeServiceProtocol) -> None:
        self.db_path = db_path
        self.hash_chain = AuditHashChain(db_path)
        self.signature_manager = AuditSignatureManager(db_path, time_service)
        self._time_service = time_service
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the verifier components"""
        if self._initialized:
            return

        self.hash_chain.initialize()
        self.signature_manager.initialize()
        self._initialized = True
        logger.info("Audit verifier initialized")

    def verify_complete_chain(self) -> CompleteVerificationResult:
        """Perform complete verification of the entire audit chain.

        Post-A3 cutover (CIRISAgent#763 / 2.9.0 Phase 3a): delegates to
        persist's `audit_verify_chain` substrate, which walks the
        `cirislens_audit_log` table — the canonical store after the A3
        write-path cutover. Verified against a real 69-entry production
        fixture; tampered-entry detection returns the exact sequence break.

        The legacy hash_chain / signature_manager paths are kept for
        boot-time initialize() compatibility but never consulted here.
        """
        if not self._initialized:
            self.initialize()

        import json

        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        logger.info("Starting complete audit chain verification via persist")
        start_time = self._time_service.now()

        try:
            engine = get_persist_engine()
            if engine is None:
                raise RuntimeError("persist engine not wired")

            tenant_id = _audit_tenant_id()

            # Discover the last sequence number for this tenant. Persist
            # doesn't (yet) expose a `audit_tail_sequence` helper, so we
            # paginate `audit_list_entries` DESC and read the first row.
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
                # Persist's audit_verify_chain combines hash + signature
                # verification under one outcome; we report the same value
                # for both rather than synthesizing a false-distinction.
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

    def verify_entry(self, entry_id: int) -> EntryVerificationResult:
        """Verify a specific audit entry by ID"""
        if not self._initialized:
            self.initialize()

        try:
            conn = get_safe_sqlite_connection(self.db_path, row_factory=sqlite3.Row)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM audit_log WHERE entry_id = ?", (entry_id,))

            row = cursor.fetchone()
            conn.close()

            if not row:
                return EntryVerificationResult(
                    valid=False,
                    entry_id=entry_id,
                    hash_valid=False,
                    previous_hash_valid=False,
                    errors=[f"Entry {entry_id} not found"],
                )

            entry = dict(row)
            return self._verify_single_entry(entry)

        except sqlite3.Error as e:
            logger.error(f"Database error verifying entry {entry_id}: {e}")
            return EntryVerificationResult(
                valid=False,
                entry_id=entry_id,
                hash_valid=False,
                previous_hash_valid=False,
                errors=[f"Database error: {e}"],
            )

    def verify_range(self, start_seq: int, end_seq: int) -> RangeVerificationResult:
        """Verify a range of entries by sequence number"""
        if not self._initialized:
            self.initialize()

        logger.debug(f"Verifying sequence range {start_seq} to {end_seq}")

        # Verify hash chain for range
        chain_result = self.hash_chain.verify_chain_integrity(start_seq, end_seq)

        # Verify signatures for range
        signature_result = self._verify_signatures_in_range(start_seq, end_seq)

        # Extract values from result objects
        chain_valid = chain_result.valid
        entries_checked = chain_result.entries_checked
        chain_errors = chain_result.errors if hasattr(chain_result, "errors") else []

        return RangeVerificationResult(
            valid=chain_valid and signature_result.valid,
            start_id=start_seq,
            end_id=end_seq,
            entries_verified=entries_checked,
            hash_chain_valid=chain_valid,
            signatures_valid=signature_result.valid,
            errors=chain_errors + (signature_result.errors if hasattr(signature_result, "errors") else []),
            verification_time_ms=0,
        )

    def find_tampering_fast(self) -> Optional[int]:
        """Quickly find the first tampered entry using binary search"""
        if not self._initialized:
            self.initialize()

        logger.info("Performing fast tampering detection")
        return self.hash_chain.find_tampering()

    def _verify_single_entry(self, entry: JSONDict) -> EntryVerificationResult:
        """Verify a single entry's hash and signature

        Args:
            entry: Audit entry as JSON-compatible dict

        Returns:
            Verification result with hash and signature validation status
        """
        errors: List[str] = []

        # Verify entry hash
        computed_hash = self.hash_chain.compute_entry_hash(entry)
        hash_valid = computed_hash == entry["entry_hash"]
        if not hash_valid:
            errors.append(f"Entry hash mismatch: computed {computed_hash}, stored {entry['entry_hash']}")

        # Verify signature - extract values with type narrowing
        entry_hash = get_str(entry, "entry_hash", "")
        signature = get_str(entry, "signature", "")
        signing_key_id_val = get_str(entry, "signing_key_id", "")
        signing_key_id = signing_key_id_val if signing_key_id_val else None

        signature_valid = self.signature_manager.verify_signature(entry_hash, signature, signing_key_id)
        if not signature_valid:
            errors.append(f"Invalid signature for entry {entry['entry_id']}")

        # Check previous hash link
        previous_hash_valid = True  # Assume valid unless we find otherwise
        sequence_number = get_int(entry, "sequence_number", 0)
        prev_hash = entry.get("previous_hash", "")
        # "genesis" is only valid for sequence 1
        # REANCHOR_* markers are valid anchor points (from retention cleanup)
        if sequence_number > 1 and prev_hash == "genesis":
            previous_hash_valid = False
            errors.append("Invalid previous hash: 'genesis' only valid for first entry")
        # Note: REANCHOR_* is valid as an anchor point after retention cleanup

        return EntryVerificationResult(
            valid=len(errors) == 0,
            entry_id=entry["entry_id"],
            hash_valid=hash_valid,
            signature_valid=signature_valid,
            previous_hash_valid=previous_hash_valid,
            errors=errors,
        )

    def _verify_all_signatures(self) -> SignatureVerificationResult:
        """Verify signatures for all entries in the audit log"""
        try:
            conn = get_safe_sqlite_connection(self.db_path, row_factory=sqlite3.Row)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT entry_id, entry_hash, signature, signing_key_id
                FROM audit_log
                ORDER BY sequence_number
            """
            )

            entries = cursor.fetchall()
            conn.close()

            errors: List[str] = []
            verified_count = 0

            for entry in entries:
                if self.signature_manager.verify_signature(
                    entry["entry_hash"], entry["signature"], entry["signing_key_id"]
                ):
                    verified_count += 1
                else:
                    errors.append(f"Invalid signature for entry {entry['entry_id']}")

            return SignatureVerificationResult(
                valid=len(errors) == 0,
                entries_signed=len(entries),
                entries_verified=verified_count,
                errors=errors,
                untrusted_keys=[],
            )

        except sqlite3.Error as e:
            logger.error(f"Database error verifying signatures: {e}")
            return SignatureVerificationResult(
                valid=False, entries_signed=0, entries_verified=0, errors=[f"Database error: {e}"], untrusted_keys=[]
            )

    def _verify_signatures_in_range(self, start_seq: int, end_seq: int) -> SignatureVerificationResult:
        """Verify signatures for entries in a specific sequence range"""
        try:
            conn = get_safe_sqlite_connection(self.db_path, row_factory=sqlite3.Row)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT entry_id, entry_hash, signature, signing_key_id
                FROM audit_log
                WHERE sequence_number >= ? AND sequence_number <= ?
                ORDER BY sequence_number
            """,
                (start_seq, end_seq),
            )

            entries = cursor.fetchall()
            conn.close()

            errors: List[str] = []
            verified_count = 0

            for entry in entries:
                if self.signature_manager.verify_signature(
                    entry["entry_hash"], entry["signature"], entry["signing_key_id"]
                ):
                    verified_count += 1
                else:
                    errors.append(f"Invalid signature for entry {entry['entry_id']} (seq {start_seq}-{end_seq})")

            return SignatureVerificationResult(
                valid=len(errors) == 0,
                entries_signed=len(entries),
                entries_verified=verified_count,
                errors=errors,
                untrusted_keys=[],
            )

        except sqlite3.Error as e:
            logger.error(f"Database error verifying range signatures: {e}")
            return SignatureVerificationResult(
                valid=False, entries_signed=0, entries_verified=0, errors=[f"Database error: {e}"], untrusted_keys=[]
            )

    def get_verification_report(self) -> VerificationReport:
        """Generate a comprehensive verification report"""
        if not self._initialized:
            self.initialize()

        logger.info("Generating comprehensive audit verification report")

        chain_summary = self.hash_chain.get_chain_summary()

        verification_result = self.verify_complete_chain()

        key_info_dict = self.signature_manager.get_key_info()
        key_info = SigningKeyInfo(**key_info_dict)

        first_tampered = self.find_tampering_fast()

        report = VerificationReport(
            timestamp=self._time_service.now(),
            verification_result=verification_result,
            chain_summary=chain_summary,
            signing_key_info=key_info,
            tampering_detected=first_tampered is not None,
            first_tampered_sequence=first_tampered,
            recommendations=[],
        )

        if not verification_result.valid:
            report.recommendations.append("CRITICAL: Audit log integrity compromised - investigate immediately")

        if first_tampered:
            report.recommendations.append(f"Tampering detected at sequence {first_tampered} - verify backup logs")

        if verification_result.verification_time_ms > 10000:
            report.recommendations.append("Verification taking too long - consider archiving old entries")

        if chain_summary.total_entries > 100000:
            report.recommendations.append("Large audit log - consider periodic archiving")

        if key_info.active is False:
            report.recommendations.append("WARNING: Signing key is revoked or inactive")

        return report

    def verify_root_anchors(self) -> RootAnchorVerificationResult:
        """Verify the integrity of root hash anchors"""
        try:
            conn = get_safe_sqlite_connection(self.db_path, row_factory=sqlite3.Row)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT root_id, sequence_start, sequence_end, root_hash, timestamp
                FROM audit_roots
                ORDER BY sequence_start
            """
            )

            roots = cursor.fetchall()
            conn.close()

            if not roots:
                return RootAnchorVerificationResult(
                    valid=True, verified_count=0, total_count=0, message="No root anchors found"
                )

            errors: List[str] = []
            verified_count = 0

            for root in roots:
                range_result = self.verify_range(root["sequence_start"], root["sequence_end"])

                if range_result.valid:
                    verified_count += 1
                else:
                    errors.append(
                        f"Root {root['root_id']} invalid: range {root['sequence_start']}-{root['sequence_end']} compromised"
                    )

            return RootAnchorVerificationResult(
                valid=len(errors) == 0, verified_count=verified_count, total_count=len(roots), errors=errors
            )

        except sqlite3.Error as e:
            logger.error(f"Database error verifying root anchors: {e}")
            return RootAnchorVerificationResult(
                valid=False, verified_count=0, total_count=0, errors=[f"Database error: {e}"]
            )
