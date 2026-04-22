"""
Tests for hash chain REANCHOR marker verification.

Tests that the hash chain verifier correctly handles REANCHOR markers
created during retention cleanup.
"""

import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import Generator

import pytest

from ciris_engine.logic.audit.hash_chain import AuditHashChain, HashChainVerificationResult


class TestHashChainReanchor:
    """Test suite for hash chain REANCHOR marker handling."""

    @pytest.fixture
    def temp_db_path(self) -> Generator[str, None, None]:
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # Create the audit_log table
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                originator_id TEXT NOT NULL,
                target_id TEXT,
                event_summary TEXT,
                event_payload TEXT,
                sequence_number INTEGER NOT NULL,
                previous_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL,
                signature TEXT NOT NULL,
                signing_key_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sequence_number)
            )
        """
        )
        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        import os

        try:
            os.unlink(db_path)
        except Exception:
            pass

    @pytest.fixture
    def hash_chain(self, temp_db_path: str) -> AuditHashChain:
        """Create AuditHashChain instance."""
        chain = AuditHashChain(temp_db_path)
        chain.initialize()
        return chain

    def _insert_entry_raw(self, db_path: str, entry: dict) -> None:
        """Insert entry directly into audit_log table."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_log
            (event_id, event_timestamp, event_type, originator_id,
             event_summary, event_payload, sequence_number, previous_hash,
             entry_hash, signature, signing_key_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["event_id"],
                entry["event_timestamp"],
                entry["event_type"],
                entry["originator_id"],
                entry.get("event_summary", "test"),
                entry.get("event_payload", "{}"),
                entry["sequence_number"],
                entry["previous_hash"],
                entry["entry_hash"],
                entry.get("signature", "test_sig"),
                entry.get("signing_key_id", "test_key"),
            ),
        )
        conn.commit()
        conn.close()

    def _create_entry_with_proper_hash(
        self,
        hash_chain: AuditHashChain,
        event_id: str,
        override_previous_hash: str | None = None,
        override_sequence: int | None = None,
    ) -> dict:
        """Create entry with properly computed hash."""
        now = datetime.now(timezone.utc)
        entry = {
            "event_id": event_id,
            "event_timestamp": now.isoformat(),
            "event_type": "test",
            "originator_id": "system",
            "event_summary": "test entry",
            "event_payload": "{}",
        }

        # Use hash_chain to compute proper hash
        prepared = hash_chain.prepare_entry(entry.copy())

        # Override previous_hash if specified (for REANCHOR testing)
        if override_previous_hash is not None:
            prepared["previous_hash"] = override_previous_hash
            # Recompute hash with new previous_hash
            prepared["entry_hash"] = hash_chain.compute_entry_hash(prepared)

        if override_sequence is not None:
            prepared["sequence_number"] = override_sequence
            # Recompute hash with new sequence
            prepared["entry_hash"] = hash_chain.compute_entry_hash(prepared)

        return prepared

    # ========== Test REANCHOR marker acceptance ==========

    def test_verify_chain_accepts_reanchor_marker(self, hash_chain, temp_db_path):
        """Test that verifier accepts REANCHOR marker as valid anchor."""
        # Create entry with REANCHOR as previous_hash
        entry1 = self._create_entry_with_proper_hash(
            hash_chain,
            "post_cleanup_1",
            override_previous_hash="REANCHOR_2024-01-01T00:00:00+00:00",
            override_sequence=5,
        )
        self._insert_entry_raw(temp_db_path, entry1)

        # Create second entry linking to first
        # Need to reinitialize to pick up the new entry
        hash_chain.initialize()
        entry2 = self._create_entry_with_proper_hash(
            hash_chain,
            "post_cleanup_2",
        )
        self._insert_entry_raw(temp_db_path, entry2)

        # Verify chain starting from reanchored entry
        result = hash_chain.verify_chain_integrity(start_seq=5, end_seq=6)

        assert isinstance(result, HashChainVerificationResult)
        assert result.valid is True
        assert result.entries_checked == 2
        assert len(result.errors) == 0

    def test_verify_chain_rejects_invalid_previous_hash(self, hash_chain, temp_db_path):
        """Test that verifier rejects invalid previous hash (not REANCHOR, not genesis, wrong hash)."""
        # Create first entry normally
        entry1 = self._create_entry_with_proper_hash(hash_chain, "entry_1")
        self._insert_entry_raw(temp_db_path, entry1)

        hash_chain.initialize()

        # Create second entry with wrong previous_hash
        entry2 = self._create_entry_with_proper_hash(
            hash_chain,
            "entry_2",
            override_previous_hash="WRONG_HASH",  # Invalid
        )
        self._insert_entry_raw(temp_db_path, entry2)

        result = hash_chain.verify_chain_integrity(start_seq=1, end_seq=2)

        assert result.valid is False
        assert "Hash chain break" in result.errors[0]

    def test_verify_chain_multiple_reanchors(self, hash_chain, temp_db_path):
        """Test chain with REANCHOR point works correctly."""
        # Simulate chain that has been cleaned up - start at seq 100
        entry1 = self._create_entry_with_proper_hash(
            hash_chain,
            "after_cleanup",
            override_previous_hash="REANCHOR_2024-06-01T00:00:00",
            override_sequence=100,
        )
        self._insert_entry_raw(temp_db_path, entry1)

        hash_chain.initialize()

        entry2 = self._create_entry_with_proper_hash(hash_chain, "subsequent_1")
        self._insert_entry_raw(temp_db_path, entry2)

        result = hash_chain.verify_chain_integrity(start_seq=100, end_seq=101)

        assert result.valid is True
        assert result.entries_checked == 2

    def test_verify_chain_various_reanchor_formats(self, hash_chain, temp_db_path):
        """Test REANCHOR marker with various timestamp formats."""
        test_cases = [
            "REANCHOR_2024-01-01T00:00:00+00:00",
            "REANCHOR_2024-06-15T12:30:45",
            "REANCHOR_2024-01-01",
            "REANCHOR_cleanup_90d",
        ]

        for i, reanchor_marker in enumerate(test_cases):
            # Clear database and reset chain
            conn = sqlite3.connect(temp_db_path)
            conn.execute("DELETE FROM audit_log")
            conn.commit()
            conn.close()

            # Reset hash chain state
            hash_chain._sequence_number = 0
            hash_chain._last_hash = None

            entry = self._create_entry_with_proper_hash(
                hash_chain,
                f"test_{i}",
                override_previous_hash=reanchor_marker,
            )
            self._insert_entry_raw(temp_db_path, entry)

            result = hash_chain.verify_chain_integrity(start_seq=1, end_seq=1)

            assert result.valid is True, f"Failed for marker: {reanchor_marker}"

    def test_chain_continuity_after_reanchor(self, hash_chain, temp_db_path):
        """Test that chain continues correctly after REANCHOR point."""
        # Create first entry with REANCHOR
        entry1 = self._create_entry_with_proper_hash(
            hash_chain,
            "entry_0",
            override_previous_hash="REANCHOR_2024-01-01",
            override_sequence=10,
        )
        self._insert_entry_raw(temp_db_path, entry1)

        # Create subsequent entries
        hash_chain.initialize()
        for i in range(1, 3):
            entry = self._create_entry_with_proper_hash(hash_chain, f"entry_{i}")
            self._insert_entry_raw(temp_db_path, entry)
            hash_chain.initialize()

        result = hash_chain.verify_chain_integrity(start_seq=10, end_seq=12)

        assert result.valid is True
        assert result.entries_checked == 3
        assert len(result.errors) == 0

    def test_chain_break_detected_after_reanchor(self, hash_chain, temp_db_path):
        """Test that chain breaks are still detected after REANCHOR."""
        # Create anchor entry
        entry1 = self._create_entry_with_proper_hash(
            hash_chain,
            "anchor",
            override_previous_hash="REANCHOR_2024-01-01",
            override_sequence=10,
        )
        self._insert_entry_raw(temp_db_path, entry1)

        hash_chain.initialize()

        # Create good link
        entry2 = self._create_entry_with_proper_hash(hash_chain, "good_link")
        self._insert_entry_raw(temp_db_path, entry2)

        hash_chain.initialize()

        # Create broken link
        entry3 = self._create_entry_with_proper_hash(
            hash_chain,
            "broken_link",
            override_previous_hash="WRONG_HASH",
        )
        self._insert_entry_raw(temp_db_path, entry3)

        result = hash_chain.verify_chain_integrity(start_seq=10, end_seq=12)

        assert result.valid is False
        assert "Hash chain break at sequence 12" in result.errors[0]

    def test_verify_empty_range(self, hash_chain, temp_db_path):
        """Test verification of empty range."""
        result = hash_chain.verify_chain_integrity(start_seq=1, end_seq=10)

        # Empty chain should verify as valid (no entries to check)
        assert result.valid is True
        assert result.entries_checked == 0

    def test_verify_single_reanchored_entry(self, hash_chain, temp_db_path):
        """Test verification of single entry with REANCHOR."""
        entry = self._create_entry_with_proper_hash(
            hash_chain,
            "only_entry",
            override_previous_hash="REANCHOR_after_full_cleanup",
            override_sequence=50,
        )
        self._insert_entry_raw(temp_db_path, entry)

        result = hash_chain.verify_chain_integrity(start_seq=50, end_seq=50)

        assert result.valid is True
        assert result.entries_checked == 1

    def test_genesis_valid_for_first_entry(self, hash_chain, temp_db_path):
        """Test that genesis is valid for first entry (sequence 1)."""
        entry = self._create_entry_with_proper_hash(hash_chain, "first_entry")
        # First entry should naturally get genesis as previous_hash
        self._insert_entry_raw(temp_db_path, entry)

        result = hash_chain.verify_chain_integrity(start_seq=1, end_seq=1)

        assert result.valid is True
        assert entry["previous_hash"] == "genesis"

    def test_prepare_entry_continues_from_reanchor(self, hash_chain, temp_db_path):
        """Test that prepare_entry continues chain correctly after REANCHOR."""
        # Insert reanchored entry first
        entry = self._create_entry_with_proper_hash(
            hash_chain,
            "reanchored",
            override_previous_hash="REANCHOR_cleanup",
            override_sequence=10,
        )
        self._insert_entry_raw(temp_db_path, entry)

        # Reinitialize chain to pick up existing state
        hash_chain.initialize()

        # Prepare new entry
        new_entry = {
            "event_id": "new_entry",
            "event_timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "test",
            "originator_id": "system",
        }

        prepared = hash_chain.prepare_entry(new_entry)

        # Should continue from last entry
        assert prepared["sequence_number"] == 11
        assert prepared["previous_hash"] == entry["entry_hash"]
        assert "entry_hash" in prepared
