"""Unit tests for TSDB profound consolidation (in-place compression)."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService
from ciris_engine.logic.services.graph.tsdb_consolidation.compressor import SummaryCompressor
from ciris_engine.schemas.services.graph.tsdb_models import SummaryAttributes


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    mock = Mock()
    mock.memorize = AsyncMock()
    mock.recall = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_time_service():
    """Create a mock time service that returns first of month."""
    mock = Mock()
    # Set to August 1, 2025 at 01:00 UTC (so July data gets compressed)
    mock.now = Mock(return_value=datetime(2025, 8, 1, 1, 0, 0, tzinfo=timezone.utc))
    return mock


@pytest.fixture
def tsdb_service(mock_memory_bus, mock_time_service):
    """Create TSDB service with custom target MB/day."""
    service = TSDBConsolidationService(memory_bus=mock_memory_bus, time_service=mock_time_service, db_path=":memory:")
    # Set a very low target to force compression
    service._profound_target_mb_per_day = 0.000001  # 1 byte/day
    return service


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
            version INTEGER DEFAULT 1,
            updated_by TEXT,
            updated_at TEXT,
            created_at TEXT
        )
    """
    )

    return conn


def create_daily_summary(date: datetime, node_type: str = "tsdb_summary", large: bool = True) -> SummaryAttributes:
    """Create a daily summary with extensive data for testing compression."""
    base_attrs = {
        "consolidation_level": "extensive",
        "period_start": date,
        "period_end": date + timedelta(days=1),
    }

    if node_type == "tsdb_summary" and large:
        # Add lots of data to make it large
        base_attrs.update(
            {
                "total_interactions": 5000,
                "unique_services": 50,
                "total_tasks": 1000,
                "total_thoughts": 2000,
                "dominant_patterns": [f"pattern_{i}" for i in range(20)],
                "significant_events": [f"event_{i}" for i in range(30)],
                "messages_by_channel": {
                    f"channel_{i}": {"count": 100 + i, "description": f"Channel {i} description"} for i in range(10)
                },
                "participants": {
                    f"user_{i}": {
                        "message_count": 50 + i,
                        "author_name": f"User Name {i} With Very Long Username",
                        "extra_field": f"data_{i}",
                    }
                    for i in range(5)
                },
            }
        )
    else:
        base_attrs.update(
            {
                "total_interactions": 100,
                "unique_services": 5,
                "total_tasks": 20,
                "total_thoughts": 30,
            }
        )

    return SummaryAttributes(**base_attrs)


class TestSummaryCompressor:
    """Test the compression logic."""

    def test_compress_metrics(self):
        """Test metric compression keeps only significant values."""
        compressor = SummaryCompressor(target_mb_per_day=1.0)

        attrs = SummaryAttributes(
            period_start=datetime(2025, 7, 1, tzinfo=timezone.utc),
            period_end=datetime(2025, 7, 2, tzinfo=timezone.utc),
            consolidation_level="extensive",
            total_interactions=1000,
            unique_services=50,
            total_tasks=200,
            total_thoughts=500,
        )

        result = compressor.compress_summary(attrs)
        compressed = result.compressed_attributes

        # Should have compressed metrics
        assert compressed.compressed_metrics is not None
        assert "ti" in compressed.compressed_metrics  # total_interactions -> ti
        assert "us" in compressed.compressed_metrics  # unique_services -> us
        assert "tt" in compressed.compressed_metrics  # total_tasks -> tt
        assert "tth" in compressed.compressed_metrics  # total_thoughts -> tth

        # Original fields should be zeroed out
        assert compressed.total_interactions == 0
        assert compressed.unique_services == 0
        assert compressed.total_tasks == 0
        assert compressed.total_thoughts == 0

    def test_compress_descriptions(self):
        """Test description compression removes verbosity."""
        compressor = SummaryCompressor(target_mb_per_day=1.0)

        attrs = SummaryAttributes(
            period_start=datetime(2025, 7, 1, tzinfo=timezone.utc),
            period_end=datetime(2025, 7, 2, tzinfo=timezone.utc),
            consolidation_level="extensive",
            messages_by_channel={
                "channel_123": {"count": 100, "description": "Long channel description"},
                "channel_456": {"count": 50, "other_data": "stuff"},
            },
            participants={
                "user_1": {
                    "message_count": 25,
                    "author_name": "Very Long Username That Should Be Truncated",
                    "extra_field": "data",
                }
            },
            dominant_patterns=["pattern1", "pattern2", "pattern3", "pattern4", "pattern5", "pattern6"],
            significant_events=["event" + str(i) for i in range(15)],
        )

        result = compressor.compress_summary(attrs)
        compressed = result.compressed_attributes

        # Channels should only have counts
        assert compressed.messages_by_channel["channel_123"] == 100
        assert compressed.messages_by_channel["channel_456"] == 50

        # Participants compressed
        user = compressed.participants["user_1"]
        assert user["msg_count"] == 25
        assert len(user["name"]) <= 20
        assert "extra_field" not in user

        # Patterns and events should be limited
        assert len(compressed.dominant_patterns) <= 5
        assert len(compressed.significant_events) <= 10

    def test_remove_redundancy(self):
        """Test redundancy removal."""
        compressor = SummaryCompressor(target_mb_per_day=1.0)

        attrs = SummaryAttributes(
            period_start=datetime(2025, 7, 1, tzinfo=timezone.utc),
            period_end=datetime(2025, 7, 2, tzinfo=timezone.utc),
            consolidation_level="extensive",
            total_interactions=1000,
            unique_services=50,
            total_tasks=200,
            total_thoughts=500,
            dominant_patterns=["pattern1", "pattern2"],
            significant_events=["event1", "event2"],
        )

        result = compressor.compress_summary(attrs)
        compressed = result.compressed_attributes

        # Should have compressed metrics
        assert compressed.compressed_metrics is not None

        # Original metric fields should be zeroed after compression
        assert compressed.total_interactions == 0
        assert compressed.unique_services == 0
        assert compressed.total_tasks == 0
        assert compressed.total_thoughts == 0

    def test_estimate_daily_size(self):
        """Test daily size estimation."""
        compressor = SummaryCompressor(target_mb_per_day=1.0)

        # Create some summaries with varying sizes
        summaries = [
            SummaryAttributes(
                period_start=datetime(2025, 7, 1, tzinfo=timezone.utc),
                period_end=datetime(2025, 7, 2, tzinfo=timezone.utc),
                consolidation_level="extensive",
                dominant_patterns=["A" * 256] * 4,  # ~1KB
            ),
            SummaryAttributes(
                period_start=datetime(2025, 7, 2, tzinfo=timezone.utc),
                period_end=datetime(2025, 7, 3, tzinfo=timezone.utc),
                consolidation_level="extensive",
                dominant_patterns=["B" * 512] * 4,  # ~2KB
            ),
            SummaryAttributes(
                period_start=datetime(2025, 7, 3, tzinfo=timezone.utc),
                period_end=datetime(2025, 7, 4, tzinfo=timezone.utc),
                consolidation_level="extensive",
                dominant_patterns=["C" * 256] * 4,  # ~1KB
            ),
        ]

        # Total approximately 4KB over 30 days
        daily_mb = compressor.estimate_daily_size(summaries, 30)

        # Should be a small positive value
        assert daily_mb > 0
        assert daily_mb < 1.0  # Less than 1MB/day


class TestProfoundConsolidation:
    """Test profound consolidation process."""

    @pytest.mark.asyncio
    async def test_compress_daily_summaries_in_place(self, tsdb_service, mock_db_connection):
        """Test that profound consolidation compresses summaries in-place."""
        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", return_value=mock_db_connection):
            cursor = mock_db_connection.cursor()

            # Create daily summaries for July 2025
            for day in range(1, 32):  # Full month
                date = datetime(2025, 7, day, tzinfo=timezone.utc)
                node_id = f"tsdb_summary_daily_{date.strftime('%Y%m%d')}"
                attrs = create_daily_summary(date, large=True)

                cursor.execute(
                    """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, version, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (node_id, "tsdb_summary", "local", json.dumps(attrs.model_dump(mode="json")), 1, date.isoformat()),
                )

            mock_db_connection.commit()

            # Check size before compression
            cursor.execute("SELECT attributes_json FROM graph_nodes")
            before_size = sum(len(row[0]) for row in cursor.fetchall())

            # Run profound consolidation
            tsdb_service._run_profound_consolidation()

            # Check that nodes were updated, not created
            cursor.execute("SELECT COUNT(*) as count FROM graph_nodes")
            assert cursor.fetchone()["count"] == 31  # Same number of nodes

            # Check that nodes were compressed
            cursor.execute(
                """
                SELECT node_id, attributes_json, version
                FROM graph_nodes
                WHERE node_type = 'tsdb_summary'
                ORDER BY node_id
            """
            )

            compressed_count = 0
            after_size = 0

            for node_id, attrs_json, version in cursor.fetchall():
                attrs = json.loads(attrs_json)
                after_size += len(attrs_json)

                # Check compression metadata
                if attrs.get("profound_compressed"):
                    compressed_count += 1
                    assert "compression_date" in attrs
                    assert "compression_ratio" in attrs
                    assert attrs["compression_ratio"] > 0
                    assert version == 2  # Version incremented

                    # Check that verbose data was removed
                    assert "detailed_description" not in attrs
                    assert "full_context" not in attrs
                    assert "debug_info" not in attrs

            assert compressed_count == 31  # All summaries compressed
            assert after_size < before_size  # Total size reduced

            reduction_ratio = 1.0 - (after_size / before_size)
            assert reduction_ratio > 0.3  # At least 30% reduction

    @pytest.mark.asyncio
    async def test_skip_compression_if_under_target(self, tsdb_service, mock_db_connection):
        """Test that compression is skipped if already under target."""
        # Set high target so compression isn't needed
        tsdb_service._profound_target_mb_per_day = 100.0

        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", return_value=mock_db_connection):
            cursor = mock_db_connection.cursor()

            # Create small daily summaries
            for day in range(1, 8):  # Just one week
                date = datetime(2025, 7, day, tzinfo=timezone.utc)
                node_id = f"tsdb_summary_daily_{date.strftime('%Y%m%d')}"
                attrs = create_daily_summary(date, large=False)  # Small summaries

                cursor.execute(
                    """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (node_id, "tsdb_summary", "local", json.dumps(attrs.model_dump(mode="json")), date.isoformat()),
                )

            mock_db_connection.commit()

            # Run profound consolidation
            tsdb_service._run_profound_consolidation()

            # Check that nodes were NOT compressed
            cursor.execute(
                """
                SELECT attributes_json
                FROM graph_nodes
                WHERE json_extract(attributes_json, '$.profound_compressed') = true
            """
            )

            assert cursor.fetchone() is None  # No compression happened

    @pytest.mark.asyncio
    async def test_cleanup_old_basic_summaries(self, tsdb_service, mock_db_connection):
        """Test that old basic summaries are cleaned up during profound consolidation."""
        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", return_value=mock_db_connection):
            cursor = mock_db_connection.cursor()

            # Create daily summaries for July
            for day in range(1, 32):
                date = datetime(2025, 7, day, tzinfo=timezone.utc)
                node_id = f"tsdb_summary_daily_{date.strftime('%Y%m%d')}"
                attrs = create_daily_summary(date)

                cursor.execute(
                    """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (node_id, "tsdb_summary", "local", json.dumps(attrs.model_dump(mode="json")), date.isoformat()),
                )

            # Also create some old basic summaries (from June)
            for day in range(1, 10):
                date = datetime(2025, 6, day, tzinfo=timezone.utc)
                for hour in [0, 6, 12, 18]:
                    period_start = date.replace(hour=hour)
                    node_id = f"tsdb_summary_{period_start.strftime('%Y%m%d_%H')}"
                    attrs = SummaryAttributes(
                        consolidation_level="basic",
                        period_start=period_start,
                        period_end=period_start + timedelta(hours=6),
                    )

                    cursor.execute(
                        """
                        INSERT INTO graph_nodes
                        (node_id, node_type, scope, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (
                            node_id,
                            "tsdb_summary",
                            "local",
                            json.dumps(attrs.model_dump(mode="json")),
                            period_start.isoformat(),
                        ),
                    )

            mock_db_connection.commit()

            # Count basic summaries before
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM graph_nodes
                WHERE json_extract(attributes_json, '$.consolidation_level') = 'basic'
            """
            )
            basic_before = cursor.fetchone()["count"]
            assert basic_before == 36  # 9 days * 4 summaries per day

            # Run profound consolidation
            tsdb_service._run_profound_consolidation()

            # Count basic summaries after
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM graph_nodes
                WHERE json_extract(attributes_json, '$.consolidation_level') = 'basic'
            """
            )
            basic_after = cursor.fetchone()["count"]
            assert basic_after == 0  # All cleaned up (older than 30 days)

    @pytest.mark.asyncio
    async def test_month_boundary_handling(self, tsdb_service, mock_db_connection):
        """Test consolidation handles month boundaries correctly."""
        # Set time to September 1st to consolidate August
        tsdb_service._time_service.now = Mock(return_value=datetime(2025, 9, 1, 1, 0, 0, tzinfo=timezone.utc))

        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", return_value=mock_db_connection):
            cursor = mock_db_connection.cursor()

            # Create summaries for August (31 days)
            for day in range(1, 32):
                date = datetime(2025, 8, day, tzinfo=timezone.utc)
                node_id = f"tsdb_summary_daily_{date.strftime('%Y%m%d')}"
                attrs = create_daily_summary(date)

                cursor.execute(
                    """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (node_id, "tsdb_summary", "local", json.dumps(attrs.model_dump(mode="json")), date.isoformat()),
                )

            mock_db_connection.commit()

            # Run consolidation
            tsdb_service._run_profound_consolidation()

            # Verify only August summaries were compressed
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM graph_nodes
                WHERE json_extract(attributes_json, '$.profound_compressed') = true
                  AND json_extract(attributes_json, '$.period_start') LIKE '2025-08-%'
            """
            )

            assert cursor.fetchone()["count"] == 31
