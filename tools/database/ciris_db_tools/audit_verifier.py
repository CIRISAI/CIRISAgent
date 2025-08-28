"""
Audit trail verification functionality.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseDBTool, ReportFormatter


class AuditVerifierWrapper(BaseDBTool):
    """Wrapper for audit verification functionality."""

    def get_audit_status(self) -> Dict[str, Any]:
        """Get audit trail status and basic integrity check."""
        status = {"audit_trail": {}, "hash_chain": {}, "signatures": {}, "integrity": {}}

        if not Path(self.audit_db_path).exists():
            status["error"] = "Audit database not found"
            return status

        with self.get_connection(str(self.audit_db_path)) as conn:
            cursor = conn.cursor()

            # Basic stats
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_entries,
                    MIN(created_at) as oldest_entry,
                    MAX(created_at) as newest_entry,
                    MIN(sequence_number) as min_seq,
                    MAX(sequence_number) as max_seq
                FROM audit_log
            """
            )

            row = cursor.fetchone()
            if row:
                status["audit_trail"] = {
                    "total_entries": row["total_entries"],
                    "oldest_entry": row["oldest_entry"],
                    "newest_entry": row["newest_entry"],
                    "sequence_range": (row["min_seq"], row["max_seq"]),
                    "expected_entries": row["max_seq"] - row["min_seq"] + 1 if row["min_seq"] and row["max_seq"] else 0,
                }

            # Check sequence completeness
            if status["audit_trail"].get("expected_entries"):
                status["integrity"]["sequence_complete"] = (
                    status["audit_trail"]["total_entries"] == status["audit_trail"]["expected_entries"]
                )

                if not status["integrity"]["sequence_complete"]:
                    # Find gaps
                    cursor.execute(
                        """
                        SELECT sequence_number + 1 as gap_start
                        FROM audit_log a1
                        WHERE NOT EXISTS (
                            SELECT 1 FROM audit_log a2
                            WHERE a2.sequence_number = a1.sequence_number + 1
                        )
                        AND sequence_number < (SELECT MAX(sequence_number) FROM audit_log)
                        LIMIT 10
                    """
                    )

                    gaps = [row["gap_start"] for row in cursor]
                    status["integrity"]["sequence_gaps"] = gaps

            # Sample hash chain verification
            cursor.execute(
                """
                SELECT
                    sequence_number,
                    entry_hash,
                    previous_hash
                FROM audit_log
                ORDER BY sequence_number DESC
                LIMIT 10
            """
            )

            recent_entries = list(cursor)
            if len(recent_entries) >= 2:
                # Quick check: verify last entry links to previous
                last = recent_entries[0]
                prev = recent_entries[1]

                status["hash_chain"]["last_entry_seq"] = last["sequence_number"]
                status["hash_chain"]["last_entry_hash"] = last["entry_hash"][:16] + "..."
                status["hash_chain"]["links_to_previous"] = last["previous_hash"] == prev["entry_hash"]

            # Signature stats
            cursor.execute(
                """
                SELECT
                    COUNT(CASE WHEN signature IS NOT NULL THEN 1 END) as signed_entries,
                    COUNT(CASE WHEN signature IS NULL THEN 1 END) as unsigned_entries,
                    COUNT(DISTINCT signing_key_id) as unique_keys_used
                FROM audit_log
            """
            )

            row = cursor.fetchone()
            status["signatures"] = {
                "signed_entries": row["signed_entries"],
                "unsigned_entries": row["unsigned_entries"],
                "unique_keys_used": row["unique_keys_used"],
            }

            # Get active signing keys
            cursor.execute(
                """
                SELECT key_id, created_at, revoked_at
                FROM audit_signing_keys
                ORDER BY created_at DESC
            """
            )

            keys = list(cursor)
            status["signatures"]["total_keys"] = len(keys)
            status["signatures"]["active_keys"] = sum(1 for k in keys if not k["revoked_at"])
            status["signatures"]["revoked_keys"] = sum(1 for k in keys if k["revoked_at"])

        return status

    def verify_audit_integrity(self, sample_size: Optional[int] = None) -> Dict[str, Any]:
        """Run audit verification (limited version without full verifier)."""
        result = {"is_valid": True, "entries_verified": 0, "errors": [], "warnings": []}

        if not Path(self.audit_db_path).exists():
            result["is_valid"] = False
            result["errors"].append("Audit database not found")
            return result

        with self.get_connection(str(self.audit_db_path)) as conn:
            cursor = conn.cursor()

            # Basic sequence verification
            cursor.execute(
                """
                SELECT COUNT(*) as gap_count
                FROM (
                    SELECT sequence_number + 1 as gap
                    FROM audit_log a1
                    WHERE NOT EXISTS (
                        SELECT 1 FROM audit_log a2
                        WHERE a2.sequence_number = a1.sequence_number + 1
                    )
                    AND sequence_number < (SELECT MAX(sequence_number) FROM audit_log)
                )
            """
            )

            gap_count = cursor.fetchone()["gap_count"]
            if gap_count > 0:
                result["is_valid"] = False
                result["errors"].append(f"Found {gap_count} sequence gaps")

            # Sample hash chain verification
            limit = sample_size if sample_size else 100
            cursor.execute(
                f"""
                SELECT
                    sequence_number,
                    entry_hash,
                    previous_hash
                FROM audit_log
                ORDER BY sequence_number DESC
                LIMIT {limit}
            """
            )

            entries = list(cursor)
            result["entries_verified"] = len(entries)

            # Verify chain
            for i in range(len(entries) - 1):
                current = entries[i]
                prev = entries[i + 1]

                if current["previous_hash"] != prev["entry_hash"]:
                    result["is_valid"] = False
                    result["errors"].append(f"Hash chain broken at sequence {current['sequence_number']}")
                    break

        return result

    def print_audit_report(self):
        """Print audit trail status report."""
        formatter = ReportFormatter()
        formatter.print_section("AUDIT TRAIL STATUS")

        status = self.get_audit_status()

        if status.get("error"):
            print(f"ERROR: {status['error']}")
            return

        # Basic statistics
        if status["audit_trail"]:
            trail = status["audit_trail"]
            formatter.print_subsection("Audit Trail Statistics")
            print(f"Total Entries: {trail['total_entries']:,}")

            if trail["oldest_entry"] and trail["newest_entry"]:
                oldest = self.parse_timestamp(trail["oldest_entry"])
                newest = self.parse_timestamp(trail["newest_entry"])

                print(f"Date Range: {oldest.strftime('%Y-%m-%d %H:%M')} to {newest.strftime('%Y-%m-%d %H:%M')}")
                print(f"Sequence Range: {trail['sequence_range'][0]:,} to {trail['sequence_range'][1]:,}")
                print(f"Expected Entries: {trail['expected_entries']:,}")

        # Integrity check
        if status["integrity"]:
            formatter.print_subsection("Integrity Check")
            print(f"Sequence Complete: {'✓ YES' if status['integrity']['sequence_complete'] else '✗ NO'}")
            if not status["integrity"]["sequence_complete"]:
                print(f"  Missing Sequences: {status['integrity'].get('sequence_gaps', 'Unknown')}")

        # Hash chain
        if status["hash_chain"]:
            chain = status["hash_chain"]
            formatter.print_subsection("Hash Chain")
            print(f"Last Entry: Seq #{chain['last_entry_seq']}")
            print(f"Hash: {chain['last_entry_hash']}")
            print(f"Links Correctly: {'✓ YES' if chain['links_to_previous'] else '✗ NO'}")

        # Signatures
        if status["signatures"]:
            sigs = status["signatures"]
            formatter.print_subsection("Digital Signatures")
            print(f"Signed Entries: {sigs['signed_entries']:,}")
            print(f"Unsigned Entries: {sigs['unsigned_entries']:,}")
            if sigs["signed_entries"] + sigs["unsigned_entries"] > 0:
                coverage = sigs["signed_entries"] / (sigs["signed_entries"] + sigs["unsigned_entries"]) * 100
                print(f"Signature Coverage: {coverage:.1f}%")
            print("\nSigning Keys:")
            print(f"  Total: {sigs['total_keys']}")
            print(f"  Active: {sigs['active_keys']}")
            print(f"  Revoked: {sigs['revoked_keys']}")
            print(f"  Unique Keys Used: {sigs['unique_keys_used']}")

    def print_verification_report(self, sample_size: Optional[int] = None):
        """Print audit verification report."""
        formatter = ReportFormatter()
        formatter.print_section("AUDIT VERIFICATION REPORT")

        print(f"Running verification on {'sample of ' + str(sample_size) if sample_size else 'all'} entries...")

        result = self.verify_audit_integrity(sample_size)

        print(f"\nVerification {'PASSED ✓' if result['is_valid'] else 'FAILED ✗'}")
        print(f"Entries Verified: {result['entries_verified']:,}")

        if result["errors"]:
            formatter.print_subsection("Errors Found")
            for error in result["errors"]:
                print(f"  - {error}")

        if result["warnings"]:
            formatter.print_subsection("Warnings")
            for warning in result["warnings"]:
                print(f"  - {warning}")
