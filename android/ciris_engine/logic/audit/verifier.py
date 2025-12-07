"""
Audit verifier for tamper detection in signed audit trail system.

Provides comprehensive verification of audit log integrity including
hash chains, digital signatures, and root anchoring.
"""

import logging
import sqlite3
from typing import List, Optional

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


class AuditVerifier:
    """Verifies audit log integrity and detects tampering"""

    def __init__(self, db_path: str, key_path: str, time_service: TimeServiceProtocol) -> None:
        self.db_path = db_path
        self.hash_chain = AuditHashChain(db_path)
        self.signature_manager = AuditSignatureManager(key_path, db_path, time_service)
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
        """Perform complete verification of the entire audit chain"""
        if not self._initialized:
            self.initialize()

        logger.info("Starting complete audit chain verification")
        start_time = self._time_service.now()

        # Get chain summary
        summary = self.hash_chain.get_chain_summary()
        if summary.error:
            return CompleteVerificationResult(
                valid=False,
                entries_verified=0,
                hash_chain_valid=False,
                signatures_valid=False,
                verification_time_ms=0,
                error=summary.error,
            )

        total_entries = summary.total_entries
        if total_entries == 0:
            return CompleteVerificationResult(
                valid=True,
                entries_verified=0,
                hash_chain_valid=True,
                signatures_valid=True,
                verification_time_ms=0,
                summary="Empty audit log",
            )

        # Verify hash chain integrity
        chain_result = self.hash_chain.verify_chain_integrity()

        # Verify signatures
        signature_result = self._verify_all_signatures()

        # Calculate verification time
        end_time = self._time_service.now()
        verification_time = int((end_time - start_time).total_seconds() * 1000)

        # Combine results
        overall_valid = chain_result.valid and signature_result.valid

        result = CompleteVerificationResult(
            valid=overall_valid,
            entries_verified=total_entries,
            hash_chain_valid=chain_result.valid,
            signatures_valid=signature_result.valid,
            verification_time_ms=verification_time,
            hash_chain_errors=chain_result.errors,
            signature_errors=signature_result.errors,
            chain_summary=summary.model_dump() if summary else None,
        )

        if overall_valid:
            logger.info(f"Audit verification passed: {total_entries} entries in {verification_time}ms")
        else:
            logger.error(
                f"Audit verification FAILED: {len(chain_result.errors)} hash + {len(signature_result.errors)} signature errors"
            )

        return result

    def verify_entry(self, entry_id: int) -> EntryVerificationResult:
        """Verify a specific audit entry by ID"""
        if not self._initialized:
            self.initialize()

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
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
        if sequence_number > 1 and entry.get("previous_hash") == "genesis":
            previous_hash_valid = False
            errors.append("Invalid previous hash: 'genesis' only valid for first entry")

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
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
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
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
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
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
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
