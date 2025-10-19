"""Unit tests for TSDB SQL builders and parsers."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.sql_builders import (
    build_nodes_in_period_query,
    build_oldest_unconsolidated_query,
    build_service_correlations_query,
    build_tasks_in_period_query,
    build_tsdb_data_query,
    parse_correlation_row,
    parse_datetime_field,
    parse_graph_node_row,
    parse_json_string_field,
    parse_task_row,
)
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType


class TestBuildNodesInPeriodQuery:
    """Tests for build_nodes_in_period_query()."""

    def test_build_query_postgresql(self):
        """Test PostgreSQL query uses direct timestamp comparison."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, params = build_nodes_in_period_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "created_at >= %s" in sql
        assert "created_at < %s" in sql
        assert "datetime(" not in sql  # No datetime() function for PostgreSQL
        assert params == ("2025-01-01T00:00:00", "2025-01-02T00:00:00")

    def test_build_query_sqlite(self):
        """Test SQLite query uses datetime() function."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = False
        adapter.placeholder.return_value = "?"

        sql, params = build_nodes_in_period_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "datetime(created_at) >= datetime(?)" in sql
        assert "datetime(created_at) < datetime(?)" in sql
        assert params == ("2025-01-01T00:00:00", "2025-01-02T00:00:00")

    def test_query_filters_local_scope(self):
        """Test query filters for local scope."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, _ = build_nodes_in_period_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "scope = 'local'" in sql

    def test_query_orders_by_type_and_created_at(self):
        """Test query orders results properly."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, _ = build_nodes_in_period_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "ORDER BY node_type, created_at" in sql


class TestBuildTSDBDataQuery:
    """Tests for build_tsdb_data_query()."""

    def test_build_query_postgresql(self):
        """Test PostgreSQL query for TSDB data."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, params = build_tsdb_data_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "node_type = 'tsdb_data'" in sql
        assert "updated_at >= %s" in sql
        assert "updated_at < %s" in sql
        assert len(params) == 4  # start/end for updated_at and created_at

    def test_build_query_sqlite(self):
        """Test SQLite query for TSDB data."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = False
        adapter.placeholder.return_value = "?"

        sql, params = build_tsdb_data_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "datetime(updated_at) >= datetime(?)" in sql
        assert "datetime(created_at) >= datetime(?)" in sql
        assert len(params) == 4

    def test_query_handles_null_updated_at(self):
        """Test query includes fallback to created_at."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, _ = build_tsdb_data_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "updated_at IS NULL" in sql
        assert "created_at >=" in sql


class TestBuildServiceCorrelationsQuery:
    """Tests for build_service_correlations_query()."""

    def test_build_query_postgresql_no_filter(self):
        """Test PostgreSQL query without correlation type filter."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, params = build_service_correlations_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "timestamp >= %s" in sql
        assert "timestamp < %s" in sql
        assert "ORDER BY timestamp" in sql
        assert len(params) == 2

    def test_build_query_sqlite_no_filter(self):
        """Test SQLite query without correlation type filter."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = False
        adapter.placeholder.return_value = "?"

        sql, params = build_service_correlations_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "datetime(timestamp) >= datetime(?)" in sql
        assert len(params) == 2

    def test_build_query_with_correlation_types(self):
        """Test query with correlation type filter."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        correlation_types = ["service_interaction", "metric_datapoint"]
        sql, params = build_service_correlations_query(
            adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00", correlation_types
        )

        assert "correlation_type IN (%s,%s)" in sql
        assert len(params) == 4  # 2 for timestamps, 2 for correlation types
        assert params[2:] == correlation_types

    def test_build_query_selects_all_fields(self):
        """Test query selects required correlation fields."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, _ = build_service_correlations_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        required_fields = [
            "correlation_id",
            "correlation_type",
            "service_type",
            "action_type",
            "trace_id",
            "span_id",
            "parent_span_id",
            "timestamp",
            "request_data",
            "response_data",
            "tags",
        ]
        for field in required_fields:
            assert field in sql


class TestBuildTasksInPeriodQuery:
    """Tests for build_tasks_in_period_query()."""

    def test_build_query_postgresql(self):
        """Test PostgreSQL query for tasks."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, params = build_tasks_in_period_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "updated_at >= %s" in sql
        assert "updated_at < %s" in sql
        assert "status != 'deferred'" in sql
        assert params == ("2025-01-01T00:00:00", "2025-01-02T00:00:00")

    def test_build_query_sqlite(self):
        """Test SQLite query for tasks."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = False
        adapter.placeholder.return_value = "?"

        sql, params = build_tasks_in_period_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "datetime(updated_at) >= datetime(?)" in sql
        assert "status != 'deferred'" in sql

    def test_query_excludes_deferred_tasks(self):
        """Test query excludes deferred tasks."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, _ = build_tasks_in_period_query(adapter, "2025-01-01T00:00:00", "2025-01-02T00:00:00")

        assert "status != 'deferred'" in sql


class TestBuildOldestUnconsolidatedQuery:
    """Tests for build_oldest_unconsolidated_query()."""

    def test_build_query_postgresql(self):
        """Test PostgreSQL query for oldest unconsolidated."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, params = build_oldest_unconsolidated_query(adapter, "local")

        assert "MIN(updated_at)" in sql
        assert "node_type = 'tsdb_data'" in sql
        assert "scope = %s" in sql
        assert params == ("local",)

    def test_build_query_sqlite(self):
        """Test SQLite query for oldest unconsolidated."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = False
        adapter.placeholder.return_value = "?"

        sql, params = build_oldest_unconsolidated_query(adapter, "local")

        assert "MIN(updated_at)" in sql
        assert "scope = ?" in sql

    def test_query_filters_null_updated_at(self):
        """Test query excludes NULL updated_at."""
        adapter = MagicMock()
        adapter.is_postgresql.return_value = True
        adapter.placeholder.return_value = "%s"

        sql, _ = build_oldest_unconsolidated_query(adapter)

        assert "updated_at IS NOT NULL" in sql


class TestParseDateTimeField:
    """Tests for parse_datetime_field()."""

    def test_parse_none(self):
        """Test parsing None returns None."""
        result = parse_datetime_field(None)
        assert result is None

    def test_parse_datetime_with_tz(self):
        """Test parsing datetime object with timezone."""
        dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_datetime_field(dt)

        assert result == dt
        assert result.tzinfo == timezone.utc

    def test_parse_datetime_without_tz(self):
        """Test parsing naive datetime adds UTC timezone."""
        dt = datetime(2025, 1, 1, 12, 0, 0)
        result = parse_datetime_field(dt)

        assert result.tzinfo == timezone.utc
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1

    def test_parse_iso_string(self):
        """Test parsing ISO format string."""
        result = parse_datetime_field("2025-01-01T12:00:00+00:00")

        assert isinstance(result, datetime)
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1

    def test_parse_iso_string_with_z(self):
        """Test parsing ISO string with Z suffix."""
        result = parse_datetime_field("2025-01-01T12:00:00Z")

        assert isinstance(result, datetime)
        assert result.tzinfo is not None


class TestParseJSONStringField:
    """Tests for parse_json_string_field()."""

    def test_parse_none(self):
        """Test parsing None returns empty dict."""
        result = parse_json_string_field(None)
        assert result == {}

    def test_parse_dict(self):
        """Test parsing already-parsed dict returns as-is."""
        data = {"key": "value", "number": 123}
        result = parse_json_string_field(data)
        assert result == data

    def test_parse_valid_json_string(self):
        """Test parsing valid JSON string."""
        json_str = '{"key": "value", "number": 123}'
        result = parse_json_string_field(json_str)

        assert result == {"key": "value", "number": 123}

    def test_parse_empty_string(self):
        """Test parsing empty string returns empty dict."""
        result = parse_json_string_field("")
        assert result == {}

    def test_parse_whitespace_string(self):
        """Test parsing whitespace-only string returns empty dict."""
        result = parse_json_string_field("   ")
        assert result == {}

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns empty dict."""
        result = parse_json_string_field("{invalid json")
        assert result == {}

    def test_parse_complex_json(self):
        """Test parsing complex nested JSON."""
        json_str = '{"outer": {"inner": {"value": 42}}}'
        result = parse_json_string_field(json_str)

        assert result["outer"]["inner"]["value"] == 42


class TestParseGraphNodeRow:
    """Tests for parse_graph_node_row()."""

    def test_parse_complete_row(self):
        """Test parsing complete graph node row."""
        row = {
            "node_id": "node_123",
            "node_type": "agent",
            "scope": "local",
            "attributes_json": '{"key": "value"}',
            "version": 5,
            "updated_by": "system",
            "updated_at": "2025-01-01T12:00:00+00:00",
        }

        result = parse_graph_node_row(row)

        assert result.id == "node_123"
        assert result.type == NodeType.AGENT
        assert result.scope == GraphScope.LOCAL
        assert result.attributes == {"key": "value"}
        assert result.version == 5
        assert result.updated_by == "system"
        assert isinstance(result.updated_at, datetime)

    def test_parse_row_with_dict_attributes(self):
        """Test parsing row with already-parsed attributes."""
        row = {
            "node_id": "node_123",
            "node_type": "user",
            "scope": "local",
            "attributes_json": {"name": "Test User"},  # Already parsed
            "version": 1,
            "updated_by": "system",
            "updated_at": None,
        }

        result = parse_graph_node_row(row)

        assert result.attributes == {"name": "Test User"}
        assert result.type == NodeType.USER

    def test_parse_row_unknown_node_type(self):
        """Test unknown node type falls back to AGENT."""
        row = {
            "node_id": "node_123",
            "node_type": "unknown_type",
            "scope": "local",
            "attributes_json": "{}",
            "version": 1,
            "updated_by": "system",
            "updated_at": None,
        }

        result = parse_graph_node_row(row)

        assert result.type == NodeType.AGENT  # Fallback

    def test_parse_row_with_node_type_override(self):
        """Test parsing with explicit node type override."""
        row = {
            "node_id": "node_123",
            "scope": "local",
            "attributes_json": "{}",
            "version": 1,
            "updated_by": "system",
            "updated_at": None,
        }

        result = parse_graph_node_row(row, node_type=NodeType.TSDB_DATA)

        assert result.type == NodeType.TSDB_DATA

    def test_parse_row_defaults(self):
        """Test parsing row with missing optional fields uses defaults."""
        row = {
            "node_id": "node_minimal",
        }

        result = parse_graph_node_row(row)

        assert result.id == "node_minimal"
        assert result.scope == GraphScope.LOCAL
        assert result.version == 1
        assert result.updated_by == "system"


class TestParseCorrelationRow:
    """Tests for parse_correlation_row()."""

    def test_parse_complete_correlation(self):
        """Test parsing complete correlation row."""
        row = {
            "correlation_id": "corr_123",
            "correlation_type": "service_interaction",
            "service_type": "llm",
            "action_type": "completion",
            "trace_id": "trace_123",
            "span_id": "span_123",
            "parent_span_id": "parent_span_123",
            "timestamp": "2025-01-01T12:00:00+00:00",
            "request_data": '{"model": "gpt-4"}',
            "response_data": '{"completion": "Hello"}',
            "tags": '{"env": "prod"}',
        }

        result = parse_correlation_row(row)

        assert result["correlation_id"] == "corr_123"
        assert result["correlation_type"] == "service_interaction"
        assert result["service_type"] == "llm"
        assert result["request_data"] == {"model": "gpt-4"}
        assert result["response_data"] == {"completion": "Hello"}
        assert result["tags"] == {"env": "prod"}
        assert isinstance(result["timestamp"], datetime)

    def test_parse_correlation_with_dict_json(self):
        """Test parsing correlation with already-parsed JSON fields."""
        row = {
            "correlation_id": "corr_456",
            "correlation_type": "metric_datapoint",
            "service_type": "telemetry",
            "action_type": "record",
            "timestamp": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            "request_data": {"metric": "cpu"},  # Already parsed
            "response_data": {"value": 0.75},  # Already parsed
            "tags": {"host": "server1"},  # Already parsed
        }

        result = parse_correlation_row(row)

        assert result["request_data"] == {"metric": "cpu"}
        assert result["response_data"] == {"value": 0.75}
        assert result["tags"] == {"host": "server1"}

    def test_parse_correlation_null_fields(self):
        """Test parsing correlation with NULL fields."""
        row = {
            "correlation_id": "corr_789",
            "correlation_type": "trace_span",
            "service_type": None,
            "action_type": None,
            "trace_id": None,
            "span_id": None,
            "parent_span_id": None,
            "timestamp": None,
            "request_data": None,
            "response_data": None,
            "tags": None,
        }

        result = parse_correlation_row(row)

        assert result["request_data"] == {}
        assert result["response_data"] == {}
        assert result["tags"] == {}
        assert result["timestamp"] is None


class TestParseTaskRow:
    """Tests for parse_task_row()."""

    def test_parse_complete_task(self):
        """Test parsing complete task row."""
        row = {
            "task_id": "task_123",
            "channel_id": "channel_1",
            "description": "Test task",
            "status": "completed",
            "priority": 5,
            "created_at": "2025-01-01T10:00:00+00:00",
            "updated_at": "2025-01-01T12:00:00+00:00",
            "parent_task_id": "parent_task",
            "context_json": '{"user": "test"}',
            "outcome_json": '{"result": "success"}',
            "retry_count": 2,
        }

        result = parse_task_row(row)

        assert result["task_id"] == "task_123"
        assert result["channel_id"] == "channel_1"
        assert result["description"] == "Test task"
        assert result["status"] == "completed"
        assert result["priority"] == 5
        assert result["retry_count"] == 2
        # created_at and updated_at should be ISO strings
        assert isinstance(result["created_at"], str)
        assert isinstance(result["updated_at"], str)

    def test_parse_task_datetime_objects(self):
        """Test parsing task with datetime objects (PostgreSQL)."""
        created = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        updated = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        row = {
            "task_id": "task_pg",
            "channel_id": "channel_1",
            "description": "PG task",
            "status": "pending",
            "priority": 3,
            "created_at": created,  # datetime object
            "updated_at": updated,  # datetime object
            "parent_task_id": None,
            "context_json": None,
            "outcome_json": None,
            "retry_count": 0,
        }

        result = parse_task_row(row)

        # Should be converted to ISO strings
        assert result["created_at"] == created.isoformat()
        assert result["updated_at"] == updated.isoformat()

    def test_parse_task_defaults(self):
        """Test parsing task with missing optional fields."""
        row = {
            "task_id": "task_minimal",
            "channel_id": "channel_1",
            "description": "Minimal task",
            "status": "pending",
            "priority": 1,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }

        result = parse_task_row(row)

        assert result["parent_task_id"] is None
        assert result["retry_count"] == 0
