"""
Comprehensive tests for GraphAuditService 90-day retention cleanup.

Tests the cleanup_old_entries() method including:
- SQLite audit_log table cleanup
- Hash chain re-anchoring with REANCHOR markers
- Graph node cleanup via memory bus
- Cache cleanup
"""

import asyncio
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.services.graph.audit_service import GraphAuditService
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


def _ok_result() -> MemoryOpResult:
    """Create successful MemoryOpResult."""
    return MemoryOpResult(status=MemoryOpStatus.OK)


class TestAuditRetentionCleanup:
    """Test suite for 90-day audit retention cleanup."""

    @pytest.fixture
    def mock_time_service(self):
        """Create mock time service."""
        current_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock = Mock()
        mock.now.return_value = current_time
        mock.now_iso.return_value = current_time.isoformat()
        return mock

    @pytest.fixture
    def mock_memory_bus(self):
        """Create mock memory bus."""
        bus = Mock()
        bus.memorize = AsyncMock()
        bus.recall = AsyncMock(return_value=[])
        bus.search = AsyncMock(return_value=[])
        bus.forget = AsyncMock(return_value=_ok_result())
        return bus

    @pytest_asyncio.fixture
    async def audit_service_with_db(
        self, mock_time_service, mock_memory_bus
    ) -> AsyncGenerator[GraphAuditService, None]:
        """Create GraphAuditService with real SQLite database."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519

        # Generate real Ed25519 keypair for testing
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        pub_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        mock_verifier = MagicMock()
        mock_verifier.has_key_sync.return_value = True
        mock_verifier.get_ed25519_public_key_sync.return_value = pub_bytes
        mock_verifier.sign_ed25519_sync.side_effect = lambda data: private_key.sign(data)

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = f"{temp_dir}/test_audit.db"
            with patch(
                "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
                return_value=mock_verifier,
            ):
                service = GraphAuditService(
                    memory_bus=mock_memory_bus,
                    time_service=mock_time_service,
                    retention_days=90,
                    db_path=db_path,
                    enable_hash_chain=True,
                )
                await service.start()
                yield service

                # Cleanup
                try:
                    if service._export_task:
                        service._export_task.cancel()
                        try:
                            await service._export_task
                        except asyncio.CancelledError:
                            pass
                    service._started = False
                except Exception:
                    pass

    def _insert_test_entries(self, db_path: str, entries: list[dict], time_service) -> None:
        """Insert test entries directly into audit_log table."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for entry in entries:
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
                    entry["timestamp"],
                    entry["event_type"],
                    entry["originator_id"],
                    entry["summary"],
                    "{}",
                    entry["sequence_number"],
                    entry["previous_hash"],
                    entry["entry_hash"],
                    "test_signature",
                    "test_key",
                ),
            )

        conn.commit()
        conn.close()

    def _get_all_entries(self, db_path: str) -> list[dict]:
        """Get all entries from audit_log table."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_log ORDER BY sequence_number")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ========== Test cleanup_old_entries ==========

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_deletes_old(self, audit_service_with_db, mock_time_service):
        """Test cleanup deletes entries older than retention period."""
        now = mock_time_service.now()
        db_path = str(audit_service_with_db.db_path)

        # Insert entries: 2 old (100+ days), 2 recent (30 days)
        entries = [
            {
                "event_id": "old_1",
                "timestamp": (now - timedelta(days=100)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": "Old entry 1",
                "sequence_number": 1,
                "previous_hash": "genesis",
                "entry_hash": "hash_1",
            },
            {
                "event_id": "old_2",
                "timestamp": (now - timedelta(days=95)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": "Old entry 2",
                "sequence_number": 2,
                "previous_hash": "hash_1",
                "entry_hash": "hash_2",
            },
            {
                "event_id": "recent_1",
                "timestamp": (now - timedelta(days=30)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": "Recent entry 1",
                "sequence_number": 3,
                "previous_hash": "hash_2",
                "entry_hash": "hash_3",
            },
            {
                "event_id": "recent_2",
                "timestamp": (now - timedelta(days=10)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": "Recent entry 2",
                "sequence_number": 4,
                "previous_hash": "hash_3",
                "entry_hash": "hash_4",
            },
        ]
        self._insert_test_entries(db_path, entries, mock_time_service)

        # Run cleanup with 90-day retention
        deleted = await audit_service_with_db.cleanup_old_entries(retention_days=90)

        assert deleted == 2  # Two old entries deleted

        # Verify remaining entries
        remaining = self._get_all_entries(db_path)
        assert len(remaining) == 2
        assert remaining[0]["event_id"] == "recent_1"
        assert remaining[1]["event_id"] == "recent_2"

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_reanchors_chain(self, audit_service_with_db, mock_time_service):
        """Test cleanup re-anchors hash chain with REANCHOR marker."""
        now = mock_time_service.now()
        db_path = str(audit_service_with_db.db_path)

        entries = [
            {
                "event_id": "old_1",
                "timestamp": (now - timedelta(days=100)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": "Old entry",
                "sequence_number": 1,
                "previous_hash": "genesis",
                "entry_hash": "hash_1",
            },
            {
                "event_id": "new_anchor",
                "timestamp": (now - timedelta(days=30)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": "New anchor",
                "sequence_number": 2,
                "previous_hash": "hash_1",
                "entry_hash": "hash_2",
            },
        ]
        self._insert_test_entries(db_path, entries, mock_time_service)

        await audit_service_with_db.cleanup_old_entries(retention_days=90)

        remaining = self._get_all_entries(db_path)
        assert len(remaining) == 1

        # Check re-anchor marker
        new_anchor = remaining[0]
        assert new_anchor["event_id"] == "new_anchor"
        assert new_anchor["previous_hash"].startswith("REANCHOR_")

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_preserves_recent(self, audit_service_with_db, mock_time_service):
        """Test cleanup preserves all entries within retention period."""
        now = mock_time_service.now()
        db_path = str(audit_service_with_db.db_path)

        # All entries within 90 days
        entries = [
            {
                "event_id": f"entry_{i}",
                "timestamp": (now - timedelta(days=i * 10)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": f"Entry {i}",
                "sequence_number": i + 1,
                "previous_hash": f"hash_{i}" if i > 0 else "genesis",
                "entry_hash": f"hash_{i + 1}",
            }
            for i in range(5)  # 0, 10, 20, 30, 40 days old - all within 90
        ]
        self._insert_test_entries(db_path, entries, mock_time_service)

        deleted = await audit_service_with_db.cleanup_old_entries(retention_days=90)

        assert deleted == 0
        remaining = self._get_all_entries(db_path)
        assert len(remaining) == 5

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_empty_db(self, audit_service_with_db):
        """Test cleanup with empty database returns 0."""
        deleted = await audit_service_with_db.cleanup_old_entries(retention_days=90)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_all_deleted(self, audit_service_with_db, mock_time_service):
        """Test cleanup when all entries are deleted."""
        now = mock_time_service.now()
        db_path = str(audit_service_with_db.db_path)

        # All entries very old
        entries = [
            {
                "event_id": f"old_{i}",
                "timestamp": (now - timedelta(days=100 + i)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": f"Old {i}",
                "sequence_number": i + 1,
                "previous_hash": f"hash_{i}" if i > 0 else "genesis",
                "entry_hash": f"hash_{i + 1}",
            }
            for i in range(3)
        ]
        self._insert_test_entries(db_path, entries, mock_time_service)

        deleted = await audit_service_with_db.cleanup_old_entries(retention_days=90)

        assert deleted == 3
        remaining = self._get_all_entries(db_path)
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_custom_retention(self, audit_service_with_db, mock_time_service):
        """Test cleanup with custom retention days."""
        now = mock_time_service.now()
        db_path = str(audit_service_with_db.db_path)

        entries = [
            {
                "event_id": "entry_20d",
                "timestamp": (now - timedelta(days=20)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": "20 days old",
                "sequence_number": 1,
                "previous_hash": "genesis",
                "entry_hash": "hash_1",
            },
            {
                "event_id": "entry_10d",
                "timestamp": (now - timedelta(days=10)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": "10 days old",
                "sequence_number": 2,
                "previous_hash": "hash_1",
                "entry_hash": "hash_2",
            },
        ]
        self._insert_test_entries(db_path, entries, mock_time_service)

        # 14-day retention should delete 20-day-old entry
        deleted = await audit_service_with_db.cleanup_old_entries(retention_days=14)

        assert deleted == 1
        remaining = self._get_all_entries(db_path)
        assert len(remaining) == 1
        assert remaining[0]["event_id"] == "entry_10d"

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_invalid_retention(self, audit_service_with_db):
        """Test cleanup with invalid retention days returns 0."""
        deleted = await audit_service_with_db.cleanup_old_entries(retention_days=0)
        assert deleted == 0

        deleted = await audit_service_with_db.cleanup_old_entries(retention_days=-1)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_entries_clears_cache(self, audit_service_with_db, mock_time_service):
        """Test cleanup also clears expired entries from cache."""
        now = mock_time_service.now()

        # Add entries to recent cache
        from ciris_engine.schemas.runtime.audit import AuditRequest

        old_entry = AuditRequest(
            entry_id="old_cached",
            timestamp=now - timedelta(days=100),
            entity_id="test",
            event_type="test",
            actor="system",
            details={},
        )
        recent_entry = AuditRequest(
            entry_id="recent_cached",
            timestamp=now - timedelta(days=10),
            entity_id="test",
            event_type="test",
            actor="system",
            details={},
        )

        audit_service_with_db._recent_entries = [old_entry, recent_entry]

        await audit_service_with_db.cleanup_old_entries(retention_days=90)

        # Only recent entry should remain in cache
        assert len(audit_service_with_db._recent_entries) == 1
        assert audit_service_with_db._recent_entries[0].entry_id == "recent_cached"

    # ========== Test graph node cleanup ==========

    @pytest.mark.asyncio
    async def test_cleanup_audit_graph_nodes(self, audit_service_with_db, mock_memory_bus, mock_time_service):
        """Test cleanup of audit graph nodes."""
        now = mock_time_service.now()
        cutoff = now - timedelta(days=90)

        # Create old and new audit nodes
        old_node = GraphNode(
            id="audit_old",
            type=NodeType.AUDIT_ENTRY,
            scope=GraphScope.LOCAL,
            attributes={},
            updated_by="test",
            updated_at=now - timedelta(days=100),
        )
        new_node = GraphNode(
            id="audit_new",
            type=NodeType.AUDIT_ENTRY,
            scope=GraphScope.LOCAL,
            attributes={},
            updated_by="test",
            updated_at=now - timedelta(days=30),
        )

        mock_memory_bus.search.return_value = [old_node, new_node]
        mock_memory_bus.forget.return_value = _ok_result()

        deleted = await audit_service_with_db._cleanup_audit_graph_nodes(cutoff)

        assert deleted == 1  # Only old node deleted
        mock_memory_bus.forget.assert_called_once()
        call_kwargs = mock_memory_bus.forget.call_args[1]
        assert call_kwargs["node"] == old_node

    @pytest.mark.asyncio
    async def test_cleanup_audit_graph_nodes_no_memory_bus(self, mock_time_service):
        """Test graph cleanup returns 0 without memory bus."""
        from cryptography.hazmat.primitives.asymmetric import ed25519

        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        from cryptography.hazmat.primitives import serialization

        pub_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        mock_verifier = MagicMock()
        mock_verifier.has_key_sync.return_value = True
        mock_verifier.get_ed25519_public_key_sync.return_value = pub_bytes
        mock_verifier.sign_ed25519_sync.side_effect = lambda data: private_key.sign(data)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
                return_value=mock_verifier,
            ):
                service = GraphAuditService(
                    memory_bus=None,  # No memory bus
                    time_service=mock_time_service,
                    retention_days=90,
                    db_path=f"{temp_dir}/test.db",
                )

                now = mock_time_service.now()
                cutoff = now - timedelta(days=90)
                deleted = await service._cleanup_audit_graph_nodes(cutoff)

                assert deleted == 0

    # ========== Test 90-day boundary ==========

    @pytest.mark.asyncio
    async def test_cleanup_90_day_boundary(self, audit_service_with_db, mock_time_service):
        """Test cleanup at exact 90-day boundary."""
        now = mock_time_service.now()
        db_path = str(audit_service_with_db.db_path)

        # Note: cutoff is calculated as (now - 90 days)
        # Entries AT the cutoff (exactly 90d old) are kept
        # Entries BEFORE the cutoff (older than 90d) are deleted
        entries = [
            {
                "event_id": "exactly_90d",
                "timestamp": (now - timedelta(days=90)).isoformat(),  # At cutoff - KEPT
                "event_type": "test",
                "originator_id": "system",
                "summary": "Exactly 90 days",
                "sequence_number": 1,
                "previous_hash": "genesis",
                "entry_hash": "hash_1",
            },
            {
                "event_id": "exactly_91d",
                "timestamp": (now - timedelta(days=91)).isoformat(),  # Before cutoff - DELETED
                "event_type": "test",
                "originator_id": "system",
                "summary": "91 days old",
                "sequence_number": 2,
                "previous_hash": "hash_1",
                "entry_hash": "hash_2",
            },
            {
                "event_id": "exactly_89d",
                "timestamp": (now - timedelta(days=89)).isoformat(),  # After cutoff - KEPT
                "event_type": "test",
                "originator_id": "system",
                "summary": "89 days old",
                "sequence_number": 3,
                "previous_hash": "hash_2",
                "entry_hash": "hash_3",
            },
        ]
        self._insert_test_entries(db_path, entries, mock_time_service)

        deleted = await audit_service_with_db.cleanup_old_entries(retention_days=90)

        # Only 91d (older than 90d cutoff) should be deleted
        # 90d is at the boundary and kept, 89d is newer and kept
        assert deleted == 1
        remaining = self._get_all_entries(db_path)
        assert len(remaining) == 2
        # Order may vary, check both are present
        event_ids = [r["event_id"] for r in remaining]
        assert "exactly_90d" in event_ids
        assert "exactly_89d" in event_ids

    @pytest.mark.asyncio
    async def test_cleanup_uses_default_retention(self, audit_service_with_db, mock_time_service):
        """Test cleanup uses default retention_days from service config."""
        now = mock_time_service.now()
        db_path = str(audit_service_with_db.db_path)

        entries = [
            {
                "event_id": "old_entry",
                "timestamp": (now - timedelta(days=100)).isoformat(),
                "event_type": "test",
                "originator_id": "system",
                "summary": "Old",
                "sequence_number": 1,
                "previous_hash": "genesis",
                "entry_hash": "hash_1",
            },
        ]
        self._insert_test_entries(db_path, entries, mock_time_service)

        # Don't pass retention_days - should use service default (90)
        deleted = await audit_service_with_db.cleanup_old_entries()

        assert deleted == 1
