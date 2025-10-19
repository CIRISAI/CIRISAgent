"""Unit tests for TSDB consolidation cleanup logic."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    mock = Mock()
    mock.memorize = AsyncMock(return_value=MemoryOpResult(status=MemoryOpStatus.OK))
    mock.recall = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    mock = Mock()
    # Set to a time where we have old data to clean up
    mock.now = Mock(return_value=datetime(2025, 7, 15, 12, 0, 0, tzinfo=timezone.utc))
    return mock


@pytest.fixture
def tsdb_service(mock_memory_bus, mock_time_service):
    """Create TSDB service for testing."""
    return TSDBConsolidationService(
        memory_bus=mock_memory_bus,
        time_service=mock_time_service,
        consolidation_interval_hours=6,
        raw_retention_hours=24,
    )


@pytest.fixture
def mock_db_connection():
    """Create an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create necessary tables
    conn.execute(
        """
        CREATE TABLE graph_nodes (
            node_id TEXT PRIMARY KEY,
            node_type TEXT,
            scope TEXT,
            attributes_json TEXT,
            version INTEGER,
            updated_by TEXT,
            updated_at TEXT,
            created_at TEXT
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE service_correlations (
            correlation_id TEXT PRIMARY KEY,
            trace_id TEXT,
            span_id TEXT,
            parent_span_id TEXT,
            service_name TEXT,
            operation_name TEXT,
            correlation_type TEXT,
            created_at TEXT,
            duration_ms REAL,
            attributes_json TEXT
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE audit_log (
            sequence_number INTEGER PRIMARY KEY,
            entry_id TEXT UNIQUE,
            action TEXT,
            actor TEXT,
            target TEXT,
            details TEXT,
            created_at TEXT,
            entry_hash TEXT,
            previous_hash TEXT,
            signature TEXT
        )
    """
    )

    return conn


def create_tsdb_data_node(created_at: datetime, node_id: str = None) -> tuple:
    """Create a TSDB data node for testing."""
    if not node_id:
        node_id = f"tsdb_data_{created_at.timestamp()}"

    attrs = {"metric_name": "llm.tokens.input", "value": 100, "timestamp": created_at.isoformat()}

    return (node_id, "tsdb_data", "local", json.dumps(attrs), created_at.isoformat())


def create_summary_node(period_start: datetime, node_type: str = "tsdb_summary", source_count: int = 100) -> tuple:
    """Create a summary node for testing."""
    period_end = period_start + timedelta(hours=6)
    node_id = f"{node_type}_{period_start.strftime('%Y%m%d_%H')}"

    attrs = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "consolidation_level": "basic",
        "source_node_count": source_count,
    }

    if node_type == "audit_summary":
        attrs["source_node_count"] = source_count  # audit_entry nodes
    elif node_type == "trace_summary":
        attrs["source_correlation_count"] = source_count  # service correlations

    return (node_id, node_type, "local", json.dumps(attrs), period_start.isoformat())


class TestRawDataCleanup:
    """Test cleanup of raw data after consolidation."""

    @pytest.mark.asyncio
    async def test_cleanup_tsdb_data_nodes(self, tsdb_service, mock_db_connection):
        """Test that TSDB data nodes are cleaned up after consolidation."""

        # Patch get_db_connection to return our mock connection
        def get_test_connection(db_path=None, **kwargs):
            return mock_db_connection

        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", side_effect=get_test_connection):
            cursor = mock_db_connection.cursor()

            # Create old TSDB data nodes (30+ hours ago to ensure period_end is older than 24 hours)
            old_time = datetime(2025, 7, 14, 0, 0, 0, tzinfo=timezone.utc)  # 36 hours ago

            # Insert 100 TSDB data nodes
            for i in range(100):
                node_data = create_tsdb_data_node(old_time + timedelta(minutes=i))
                cursor.execute(
                    """
                        INSERT INTO graph_nodes
                        (node_id, node_type, scope, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                    node_data,
                )

            # Create a summary that claims to have consolidated these nodes
            summary_data = create_summary_node(old_time, "tsdb_summary", 100)
            cursor.execute(
                """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                summary_data,
            )

            mock_db_connection.commit()

            # Run cleanup
            deleted = tsdb_service._cleanup_old_data()

            # The cleanup should have deleted exactly 100 nodes
            assert deleted == 100

    @pytest.mark.asyncio
    async def test_cleanup_validates_counts(self, tsdb_service, mock_db_connection):
        """Test that cleanup validates claimed vs actual counts."""

        def get_test_connection(db_path=None, **kwargs):
            return mock_db_connection

        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", side_effect=get_test_connection):
            cursor = mock_db_connection.cursor()

            old_time = datetime(2025, 7, 14, 0, 0, 0, tzinfo=timezone.utc)  # 36 hours ago

            # Insert only 50 nodes but summary claims 100
            for i in range(50):
                node_data = create_tsdb_data_node(old_time + timedelta(minutes=i))
                cursor.execute(
                    """
                        INSERT INTO graph_nodes
                        (node_id, node_type, scope, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                    node_data,
                )

            # Summary claims 100 nodes
            summary_data = create_summary_node(old_time, "tsdb_summary", 100)
            cursor.execute(
                """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                summary_data,
            )

            mock_db_connection.commit()

            # Run cleanup
            deleted = tsdb_service._cleanup_old_data()

            # Should not delete anything due to count mismatch
            assert deleted == 0


class TestAuditNodeCleanup:
    """Test cleanup of audit graph nodes (not audit_log table)."""

    @pytest.mark.asyncio
    async def test_cleanup_audit_graph_nodes_only(self, tsdb_service, mock_db_connection):
        """Test that only graph audit nodes are cleaned, not audit_log table."""

        def get_test_connection(db_path=None, **kwargs):
            return mock_db_connection

        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", side_effect=get_test_connection):
            cursor = mock_db_connection.cursor()

            old_time = datetime(2025, 7, 14, 0, 0, 0, tzinfo=timezone.utc)  # 36 hours ago

            # Insert audit entries in both tables
            for i in range(50):
                timestamp = old_time + timedelta(minutes=i)

                # Graph node
                cursor.execute(
                    """
                        INSERT INTO graph_nodes
                        (node_id, node_type, scope, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        f"audit_entry_{i}",
                        "audit_entry",
                        "local",
                        json.dumps({"action": "test", "sequence": i}),
                        timestamp.isoformat(),
                    ),
                )

                # Audit log entry (permanent)
                cursor.execute(
                    """
                        INSERT INTO audit_log
                        (sequence_number, entry_id, action, actor, target, details,
                         created_at, entry_hash, previous_hash, signature)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        i,
                        f"audit_{i}",
                        "test_action",
                        "test_actor",
                        "test_target",
                        "test details",
                        timestamp.isoformat(),
                        f"hash_{i}",
                        f"hash_{i-1}" if i > 0 else "genesis",
                        f"sig_{i}",
                    ),
                )

            # Create summary
            summary_data = create_summary_node(old_time, "audit_summary", 50)
            cursor.execute(
                """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                summary_data,
            )

            mock_db_connection.commit()

            # Run cleanup
            deleted = tsdb_service._cleanup_old_data()

            assert deleted == 50  # Only graph nodes deleted


class TestCorrelationCleanup:
    """Test cleanup of service correlations."""

    @pytest.mark.asyncio
    async def test_cleanup_service_correlations(self, tsdb_service, mock_db_connection):
        """Test that service correlations are cleaned up."""

        def get_test_connection(db_path=None, **kwargs):
            return mock_db_connection

        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", side_effect=get_test_connection):
            cursor = mock_db_connection.cursor()

            old_time = datetime(2025, 7, 14, 0, 0, 0, tzinfo=timezone.utc)  # 36 hours ago

            # Insert service correlations
            for i in range(75):
                timestamp = old_time + timedelta(minutes=i)
                cursor.execute(
                    """
                        INSERT INTO service_correlations
                        (correlation_id, trace_id, span_id, service_name,
                         operation_name, correlation_type, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"corr_{i}",
                        f"trace_{i//10}",
                        f"span_{i}",
                        "test_service",
                        "test_operation",
                        "trace_span",
                        timestamp.isoformat(),
                    ),
                )

            # Create trace summary
            summary_data = create_summary_node(old_time, "trace_summary", 75)
            cursor.execute(
                """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                summary_data,
            )

            mock_db_connection.commit()

            # Run cleanup
            deleted = tsdb_service._cleanup_old_data()

            assert deleted == 75


class TestCleanupEdgeCases:
    """Test edge cases in cleanup logic."""

    @pytest.mark.asyncio
    async def test_no_cleanup_within_retention(self, tsdb_service, mock_db_connection):
        """Test that data within retention period is not cleaned up."""

        def get_test_connection(db_path=None, **kwargs):
            return mock_db_connection

        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", side_effect=get_test_connection):
            cursor = mock_db_connection.cursor()

            # Create recent data (only 12 hours ago)
            recent_time = datetime(2025, 7, 15, 0, 0, 0, tzinfo=timezone.utc)

            for i in range(50):
                node_data = create_tsdb_data_node(recent_time + timedelta(minutes=i))
                cursor.execute(
                    """
                        INSERT INTO graph_nodes
                        (node_id, node_type, scope, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                    node_data,
                )

            summary_data = create_summary_node(recent_time, "tsdb_summary", 50)
            cursor.execute(
                """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                summary_data,
            )

            mock_db_connection.commit()

            # Run cleanup
            deleted = tsdb_service._cleanup_old_data()

            # Nothing should be deleted (within 24 hour retention)
            assert deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_handles_missing_attributes(self, tsdb_service, mock_db_connection):
        """Test cleanup handles summaries with missing attributes gracefully."""

        def get_test_connection(db_path=None, **kwargs):
            return mock_db_connection

        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", side_effect=get_test_connection):
            cursor = mock_db_connection.cursor()

            old_time = datetime(2025, 7, 14, 0, 0, 0, tzinfo=timezone.utc)  # 36 hours ago

            # Create summary with missing period attributes
            cursor.execute(
                """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "bad_summary",
                    "tsdb_summary",
                    "local",
                    json.dumps({"consolidation_level": "basic"}),  # Missing period_start/end
                    old_time.isoformat(),
                ),
            )

            # Create some nodes that won't be cleaned due to bad summary
            for i in range(10):
                node_data = create_tsdb_data_node(old_time + timedelta(minutes=i))
                cursor.execute(
                    """
                        INSERT INTO graph_nodes
                        (node_id, node_type, scope, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                    node_data,
                )

            mock_db_connection.commit()

            # Run cleanup - should handle gracefully
            deleted = tsdb_service._cleanup_old_data()

            assert deleted == 0  # Nothing deleted due to bad summary

    @pytest.mark.asyncio
    async def test_cleanup_with_zero_count_summary(self, tsdb_service, mock_db_connection):
        """Test that summaries with zero count don't cause deletion."""

        def get_test_connection(db_path=None, **kwargs):
            return mock_db_connection

        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", side_effect=get_test_connection):
            cursor = mock_db_connection.cursor()

            old_time = datetime(2025, 7, 14, 0, 0, 0, tzinfo=timezone.utc)  # 36 hours ago

            # Create summary with 0 source count
            summary_data = create_summary_node(old_time, "tsdb_summary", 0)
            cursor.execute(
                """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                summary_data,
            )

            # Create some nodes that shouldn't be deleted
            for i in range(10):
                node_data = create_tsdb_data_node(old_time + timedelta(minutes=i))
                cursor.execute(
                    """
                        INSERT INTO graph_nodes
                        (node_id, node_type, scope, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                    node_data,
                )

            mock_db_connection.commit()

            # Run cleanup
            deleted = tsdb_service._cleanup_old_data()

            # Nothing deleted (count mismatch: 0 != 10)
            assert deleted == 0
