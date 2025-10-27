"""Unit tests for TSDB extensive consolidation (daily summaries)."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService
from ciris_engine.schemas.services.graph_core import NodeType
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
    """Create a mock time service that returns a fixed Monday."""
    mock = Mock()
    # Set to Monday, July 15, 2025 at 01:00 UTC (after midnight so consolidation runs)
    mock.now = Mock(return_value=datetime(2025, 7, 15, 1, 0, 0, tzinfo=timezone.utc))
    return mock


@pytest.fixture
def tsdb_service(mock_memory_bus, mock_time_service):
    """Create TSDB service for testing."""
    return TSDBConsolidationService(memory_bus=mock_memory_bus, time_service=mock_time_service, db_path=":memory:")


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
        CREATE TABLE graph_edges (
            edge_id TEXT PRIMARY KEY,
            source_node_id TEXT,
            target_node_id TEXT,
            scope TEXT,
            relationship TEXT,
            weight REAL,
            attributes_json TEXT,
            created_at TEXT
        )
    """
    )

    return conn


def create_basic_summary(day: datetime, hour: int, node_type: str = "tsdb_summary") -> dict:
    """Create a basic summary for testing."""
    period_start = day.replace(hour=hour, minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(hours=6)

    base_attrs = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_label": f"{day.strftime('%Y-%m-%d')}-{['night', 'morning', 'afternoon', 'evening'][hour//6]}",
        "consolidation_level": "basic",
        "source_node_count": 100,
    }

    if node_type == "tsdb_summary":
        base_attrs.update(
            {
                "metrics": {
                    "llm.tokens.input": {"count": 10, "sum": 1000, "min": 50, "max": 200, "avg": 100},
                    "llm.tokens.output": {"count": 10, "sum": 500, "min": 25, "max": 100, "avg": 50},
                    "llm.cost.cents": {"count": 10, "sum": 50.0, "min": 2.0, "max": 10.0, "avg": 5.0},
                },
                "total_tokens": 1500,
                "total_cost_cents": 50.0,
                "total_carbon_grams": 10.5,
                "total_energy_kwh": 0.15,
                "action_counts": {"SPEAK": 5, "RECALL": 3, "MEMORIZE": 2},
                "error_count": 1,
                "success_rate": 0.9,
            }
        )

    return base_attrs


class TestExtensiveConsolidation:
    """Test cases for extensive consolidation."""

    @pytest.mark.asyncio
    async def test_daily_summary_creation(self, tsdb_service, mock_db_connection):
        """Test that 4 basic summaries consolidate into 1 daily summary."""
        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", return_value=mock_db_connection):
            # Insert basic summaries for July 14, 2025 (Monday - part of current week)
            day = datetime(2025, 7, 14, tzinfo=timezone.utc)
            cursor = mock_db_connection.cursor()

            # Create 4 basic summaries for the day (00:00, 06:00, 12:00, 18:00)
            for hour in [0, 6, 12, 18]:
                node_id = f"tsdb_summary_{day.strftime('%Y%m%d')}_{hour:02d}"
                attrs = create_basic_summary(day, hour)

                cursor.execute(
                    """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (node_id, "tsdb_summary", "local", json.dumps(attrs), attrs["period_start"]),
                )

            mock_db_connection.commit()

            # Run extensive consolidation
            await tsdb_service._run_extensive_consolidation()

            # Verify daily summary was created
            assert tsdb_service._memory_bus.memorize.called

            # Check the created node
            call_args = tsdb_service._memory_bus.memorize.call_args
            daily_summary = call_args[0][0]  # First positional argument

            assert daily_summary.id == "tsdb_summary_daily_20250714"
            assert daily_summary.type == NodeType.TSDB_SUMMARY
            assert daily_summary.attributes["consolidation_level"] == "extensive"
            assert daily_summary.attributes["period_label"] == "2025-07-14"
            assert daily_summary.attributes["source_summary_count"] == 4

            # Verify metric aggregation
            assert daily_summary.attributes["total_tokens"] == 6000  # 1500 * 4
            assert daily_summary.attributes["total_cost_cents"] == 200.0  # 50 * 4
            assert daily_summary.attributes["action_counts"]["SPEAK"] == 20  # 5 * 4

    @pytest.mark.asyncio
    async def test_partial_day_consolidation(self, tsdb_service, mock_db_connection):
        """Test consolidation with only 2 summaries for a day."""
        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", return_value=mock_db_connection):
            day = datetime(2025, 7, 15, tzinfo=timezone.utc)  # Tuesday - current week
            cursor = mock_db_connection.cursor()

            # Create only 2 summaries (morning and afternoon)
            for hour in [6, 12]:
                node_id = f"tsdb_summary_{day.strftime('%Y%m%d')}_{hour:02d}"
                attrs = create_basic_summary(day, hour)

                cursor.execute(
                    """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (node_id, "tsdb_summary", "local", json.dumps(attrs), attrs["period_start"]),
                )

            mock_db_connection.commit()

            await tsdb_service._run_extensive_consolidation()

            # Should still create daily summary with partial data
            assert tsdb_service._memory_bus.memorize.called
            daily_summary = tsdb_service._memory_bus.memorize.call_args[0][0]

            assert daily_summary.attributes["source_summary_count"] == 2
            assert daily_summary.attributes["total_tokens"] == 3000  # 1500 * 2

    @pytest.mark.asyncio
    async def test_multiple_types_consolidation(self, tsdb_service, mock_db_connection):
        """Test that different summary types get their own daily summaries."""
        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", return_value=mock_db_connection):
            day = datetime(2025, 7, 16, tzinfo=timezone.utc)  # Wednesday - current week
            cursor = mock_db_connection.cursor()

            # Create summaries for different types
            for node_type in ["tsdb_summary", "audit_summary", "trace_summary"]:
                for hour in [0, 6, 12, 18]:
                    node_id = f"{node_type}_{day.strftime('%Y%m%d')}_{hour:02d}"
                    attrs = create_basic_summary(day, hour, node_type)

                    cursor.execute(
                        """
                        INSERT INTO graph_nodes
                        (node_id, node_type, scope, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (node_id, node_type, "local", json.dumps(attrs), attrs["period_start"]),
                    )

            mock_db_connection.commit()

            await tsdb_service._run_extensive_consolidation()

            # Should create 3 daily summaries (one per type)
            assert tsdb_service._memory_bus.memorize.call_count == 3

            # Verify each type got its own summary
            created_ids = [
                call[0][0].id for call in tsdb_service._memory_bus.memorize.call_args_list  # First positional arg
            ]

            assert "tsdb_summary_daily_20250716" in created_ids
            assert "audit_summary_daily_20250716" in created_ids
            assert "trace_summary_daily_20250716" in created_ids

    @pytest.mark.asyncio
    async def test_week_boundary_handling(self, tsdb_service, mock_db_connection):
        """Test consolidation across week boundaries."""
        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", return_value=mock_db_connection):
            cursor = mock_db_connection.cursor()

            # Create summaries for current week (July 14-20)
            for day_offset in range(7):
                day = datetime(2025, 7, 14, tzinfo=timezone.utc) + timedelta(days=day_offset)

                for hour in [0, 6, 12, 18]:
                    node_id = f"tsdb_summary_{day.strftime('%Y%m%d')}_{hour:02d}"
                    attrs = create_basic_summary(day, hour)

                    cursor.execute(
                        """
                        INSERT INTO graph_nodes
                        (node_id, node_type, scope, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (node_id, "tsdb_summary", "local", json.dumps(attrs), attrs["period_start"]),
                    )

            mock_db_connection.commit()

            await tsdb_service._run_extensive_consolidation()

            # Should create 7 daily summaries
            assert tsdb_service._memory_bus.memorize.call_count == 7

            # Verify date range
            created_dates = sorted(
                [call[0][0].attributes["period_label"] for call in tsdb_service._memory_bus.memorize.call_args_list]
            )

            expected_dates = [
                "2025-07-14",
                "2025-07-15",
                "2025-07-16",
                "2025-07-17",
                "2025-07-18",
                "2025-07-19",
                "2025-07-20",
            ]
            assert created_dates == expected_dates

    @pytest.mark.asyncio
    async def test_duplicate_prevention(self, tsdb_service, mock_db_connection):
        """Test that running consolidation twice doesn't create duplicates."""
        with patch("ciris_engine.logic.persistence.db.core.get_db_connection", return_value=mock_db_connection):
            day = datetime(2025, 7, 14, tzinfo=timezone.utc)  # Monday - current week
            cursor = mock_db_connection.cursor()

            # Create basic summaries
            for hour in [0, 6, 12, 18]:
                node_id = f"tsdb_summary_{day.strftime('%Y%m%d')}_{hour:02d}"
                attrs = create_basic_summary(day, hour)
                cursor.execute(
                    """
                    INSERT INTO graph_nodes
                    (node_id, node_type, scope, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (node_id, "tsdb_summary", "local", json.dumps(attrs), attrs["period_start"]),
                )

            # Also insert the daily summary (simulating previous run)
            daily_attrs = {
                "consolidation_level": "extensive",
                "period_start": day.isoformat(),
                "period_end": (day + timedelta(days=1)).isoformat(),
                "period_label": "2025-07-14",
            }
            cursor.execute(
                """
                INSERT INTO graph_nodes
                (node_id, node_type, scope, attributes_json, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    "tsdb_summary_daily_20250714",
                    "tsdb_summary",
                    "local",
                    json.dumps(daily_attrs),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

            mock_db_connection.commit()

            # Run consolidation again
            await tsdb_service._run_extensive_consolidation()

            # Should not create any new summaries (already consolidated)
            assert tsdb_service._memory_bus.memorize.call_count == 0
