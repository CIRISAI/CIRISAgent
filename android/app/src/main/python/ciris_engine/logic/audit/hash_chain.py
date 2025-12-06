"""
Hash chain manager for signed audit trail system.

Provides cryptographic integrity through hash chaining and ensures
tamper-evident audit logs for the CIRIS Agent system.
"""

import hashlib
import json
import logging
import sqlite3
import threading
from typing import List, Optional

from ciris_engine.logic.utils.jsondict_helpers import get_int, get_str
from ciris_engine.schemas.audit.hash_chain import ChainSummary, HashChainVerificationResult
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class AuditHashChain:
    """Manages the cryptographic hash chain for audit entries"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._last_hash: Optional[str] = None
        self._sequence_number: int = 0
        self._initialized = False
        self._lock = threading.Lock()

    def initialize(self, force: bool = False) -> None:
        """Initialize the hash chain by loading the last entry"""
        if self._initialized and not force:
            return

        last_entry = self.get_last_entry()
        if last_entry:
            entry_hash_val = get_str(last_entry, "entry_hash", "")
            self._last_hash = entry_hash_val if entry_hash_val else None
            self._sequence_number = get_int(last_entry, "sequence_number", 0)
        else:
            self._last_hash = None
            self._sequence_number = 0

        self._initialized = True
        logger.info(f"Hash chain initialized at sequence {self._sequence_number}")

    def compute_entry_hash(self, entry: JSONDict) -> str:
        """Compute deterministic hash of entry content.

        Args:
            entry: Audit entry as JSON-compatible dict

        Returns:
            SHA-256 hash of the canonical entry representation
        """
        # Create canonical representation for hashing
        canonical = {
            "event_id": entry["event_id"],
            "event_timestamp": entry["event_timestamp"],
            "event_type": entry["event_type"],
            "originator_id": entry["originator_id"],
            "event_payload": entry.get("event_payload", ""),
            "sequence_number": entry["sequence_number"],
            "previous_hash": entry["previous_hash"],
        }

        # Convert to deterministic JSON
        canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))

        # Compute SHA-256 hash
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def prepare_entry(self, entry: JSONDict) -> JSONDict:
        """Prepare an entry for the hash chain by adding chain fields.

        Args:
            entry: Audit entry to prepare

        Returns:
            Entry with sequence_number, previous_hash, and entry_hash added
        """
        if not self._initialized:
            self.initialize()

        with self._lock:
            # Re-read the last entry inside the lock to ensure we have the latest
            last_entry = self.get_last_entry()
            if last_entry:
                entry_hash_val = get_str(last_entry, "entry_hash", "")
                self._last_hash = entry_hash_val if entry_hash_val else None
                self._sequence_number = get_int(last_entry, "sequence_number", 0)

            self._sequence_number += 1
            entry["sequence_number"] = self._sequence_number
            entry["previous_hash"] = self._last_hash or "genesis"

            entry_hash = self.compute_entry_hash(entry)
            entry["entry_hash"] = entry_hash

            self._last_hash = entry_hash

        return entry

    def get_last_entry(self) -> Optional[JSONDict]:
        """Retrieve the last entry from the chain.

        Returns:
            Last audit entry as JSON-compatible dict, or None if chain is empty
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM audit_log
                ORDER BY sequence_number DESC
                LIMIT 1
            """
            )

            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row)
            return None

        except sqlite3.Error as e:
            logger.error(f"Failed to get last entry: {e}")
            return None

    def verify_chain_integrity(self, start_seq: int = 1, end_seq: Optional[int] = None) -> HashChainVerificationResult:
        """Verify the integrity of the hash chain"""
        conn = None
        result = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Build query
            if end_seq:
                cursor.execute(
                    """
                    SELECT * FROM audit_log
                    WHERE sequence_number >= ? AND sequence_number <= ?
                    ORDER BY sequence_number
                """,
                    (start_seq, end_seq),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM audit_log
                    WHERE sequence_number >= ?
                    ORDER BY sequence_number
                """,
                    (start_seq,),
                )

            entries = [dict(row) for row in cursor.fetchall()]

            if not entries:
                result = HashChainVerificationResult(
                    valid=True, entries_checked=0, errors=[], last_sequence=0, tampering_location=None
                )
            else:
                errors: List[str] = []
                previous_hash: Optional[str] = None

                # If not starting from sequence 1, get the previous entry's hash
                if start_seq > 1:
                    cursor.execute(
                        """
                        SELECT entry_hash FROM audit_log
                        WHERE sequence_number = ?
                    """,
                        (start_seq - 1,),
                    )
                    prev_row = cursor.fetchone()
                    if prev_row:
                        previous_hash = prev_row[0]

                for i, entry in enumerate(entries):
                    expected_seq = start_seq + i
                    if entry["sequence_number"] != expected_seq:
                        errors.append(f"Sequence gap at {entry['sequence_number']}, expected {expected_seq}")

                    if i == 0 and start_seq == 1:
                        expected_prev = "genesis"
                    else:
                        expected_prev = previous_hash or ""

                    if entry["previous_hash"] != expected_prev:
                        errors.append(f"Hash chain break at sequence {entry['sequence_number']}")

                    computed_hash = self.compute_entry_hash(entry)
                    if computed_hash != entry["entry_hash"]:
                        errors.append(f"Entry hash mismatch at sequence {entry['sequence_number']}")

                    previous_hash = entry["entry_hash"]

                result = HashChainVerificationResult(
                    valid=len(errors) == 0,
                    entries_checked=len(entries),
                    errors=errors,
                    last_sequence=entries[-1]["sequence_number"] if entries else 0,
                    tampering_location=None,
                )

        except sqlite3.Error as e:
            logger.error(f"Chain verification failed: {e}")
            result = HashChainVerificationResult(
                valid=False,
                entries_checked=0,
                errors=[f"Database error: {e}"],
                last_sequence=0,
                tampering_location=None,
            )
        finally:
            if conn:
                conn.close()

        return result

    def find_tampering(self) -> Optional[int]:
        """Find the first tampered entry in the chain using linear search"""
        if not self._initialized:
            self.initialize()

        if self._sequence_number == 0:
            return None  # Empty chain

        # Do a full chain verification to find errors
        result = self.verify_chain_integrity(1, self._sequence_number)

        if result.valid:
            return None  # No tampering found

        # Parse errors to find first tampered sequence
        errors = result.errors
        if not errors:
            return 1  # Found tampering but no specific errors

        # Sort to find the first error by sequence number
        tampered_sequences: List[int] = []
        for error in errors:
            # Look for specific error patterns
            import re

            # Pattern for "Entry hash mismatch at sequence X"
            match = re.search(r"at sequence (\d+)", error)
            if match:
                tampered_sequences.append(int(match.group(1)))
                continue
            # Pattern for "Hash chain break at sequence X"
            match = re.search(r"sequence (\d+)", error)
            if match:
                tampered_sequences.append(int(match.group(1)))

        if tampered_sequences:
            return min(tampered_sequences)  # Return the first tampered sequence

        # If we can't parse specific sequence, return 1 as fallback
        return 1

    def get_chain_summary(self) -> ChainSummary:
        """Get a summary of the current chain state"""
        if not self._initialized:
            self.initialize()

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*), MIN(sequence_number), MAX(sequence_number) FROM audit_log")
            count, min_seq, max_seq = cursor.fetchone()

            cursor.execute("SELECT event_timestamp FROM audit_log ORDER BY sequence_number LIMIT 1")
            oldest_row = cursor.fetchone()
            oldest = oldest_row[0] if oldest_row else None

            cursor.execute("SELECT event_timestamp FROM audit_log ORDER BY sequence_number DESC LIMIT 1")
            newest_row = cursor.fetchone()
            newest = newest_row[0] if newest_row else None

            conn.close()

            return ChainSummary(
                total_entries=count or 0,
                sequence_range=[min_seq, max_seq] if min_seq else [0, 0],
                current_sequence=self._sequence_number,
                current_hash=self._last_hash,
                oldest_entry=oldest,
                newest_entry=newest,
                error=None,
            )

        except sqlite3.Error as e:
            logger.error(f"Failed to get chain summary: {e}")
            return ChainSummary(
                total_entries=0,
                sequence_range=[0, 0],
                current_sequence=0,
                current_hash=None,
                oldest_entry=None,
                newest_entry=None,
                error=str(e),
            )
