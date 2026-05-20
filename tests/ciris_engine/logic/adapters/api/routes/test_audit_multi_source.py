"""
Comprehensive unit tests for multi-source audit API functionality.

Tests the enhanced audit API that queries graph memory, the persist
audit chain (formerly SQLite `audit_log`, now `cirislens_audit_log`),
and JSONL files.

2.9.0 / CIRISAgent#763: `_query_sqlite_audit` is now a thin wrapper
around `engine.audit_list_entries`. The tests stub the persist engine
via the `set_persist_engine` shim so the wrapper sees canned rows
without going through `audit_record_entry` (which requires hash-chain
signing).
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from ciris_engine.logic.adapters.api.routes.audit import (
    AuditEntryResponse,
    _merge_audit_sources,
    _query_jsonl_audit,
    _query_sqlite_audit,
)
from ciris_engine.schemas.api.audit import AuditContext
from ciris_engine.schemas.services.nodes import AuditEntry


class _FakePersistAuditEngine:
    """Minimal persist-engine stub that only implements `audit_list_entries`.

    Used by tests that need to assert the legacy-shaped output of
    `_query_sqlite_audit` (which now routes through
    `engine.audit_list_entries`). The stub returns persist-shape rows
    (recorded_at, action_type, actor_id, payload, prev_hash, etc.) and
    honours the filter's recorded_after/recorded_before / tenant scoping,
    plus the offset/limit pagination contract.
    """

    def __init__(self, rows: List[dict]) -> None:
        # Sort newest-first like persist does.
        self._rows = sorted(
            rows, key=lambda r: r.get("recorded_at", ""), reverse=True
        )

    def audit_list_entries(
        self, filter_json: str, cursor_json: Any, limit: int
    ) -> str:
        filt = json.loads(filter_json) if isinstance(filter_json, str) else (filter_json or {})
        recorded_after = filt.get("recorded_after")
        recorded_before = filt.get("recorded_before")
        cursor = (
            json.loads(cursor_json)
            if isinstance(cursor_json, str)
            else (cursor_json or {})
        )
        start = int(cursor.get("offset", 0)) if isinstance(cursor, dict) else 0

        items: List[dict] = []
        for row in self._rows:
            ts = row.get("recorded_at", "")
            if recorded_after and ts < recorded_after:
                continue
            if recorded_before and ts > recorded_before:
                continue
            items.append(row)

        page = items[start : start + limit]
        next_cursor = (
            {"offset": start + limit} if start + limit < len(items) else None
        )
        return json.dumps({"items": page, "cursor": next_cursor})


def _make_persist_audit_row(
    *,
    entry_id: str,
    recorded_at: str,
    action_type: str,
    actor_id: str,
    payload: str = "",
    sequence_number: int = 1,
    prev_hash: str = "",
    entry_hash: str = "",
    signature: str = "",
    signing_key_id: str = "key_001",
) -> dict:
    """Construct a persist-shape `cirislens_audit_log` row."""
    return {
        "entry_id": entry_id,
        "recorded_at": recorded_at,
        "action_type": action_type,
        "actor_id": actor_id,
        "payload": payload,
        "sequence_number": sequence_number,
        "prev_hash": prev_hash,
        "entry_hash": entry_hash,
        "signature": signature,
        "signing_key_id": signing_key_id,
        "signature_verified": 1,
    }


@pytest.fixture
def mock_sqlite_db(monkeypatch):
    """Wire a fake persist engine so `_query_sqlite_audit` sees test rows.

    2.9.0: the legacy `audit_log` table is no longer the source of truth.
    `_query_sqlite_audit(db_path)` reads from persist's `audit_list_entries`,
    so we install a fake engine via `set_persist_engine` for the test and
    yield the temp `db_path` string for signature compat with callers.
    """
    from ciris_engine.logic.persistence.models import graph as _graph_mod
    from ciris_engine.logic.persistence.models.graph import set_persist_engine

    rows = [
        _make_persist_audit_row(
            entry_id="evt-001",
            recorded_at="2025-09-01T10:00:00+00:00",
            action_type="HANDLER_ACTION_SPEAK",
            actor_id="user_123",
            payload='{"message": "test message 1"}',
            sequence_number=1,
            prev_hash="hash_000",
            entry_hash="hash_001",
            signature="sig_001",
        ),
        _make_persist_audit_row(
            entry_id="evt-002",
            recorded_at="2025-09-01T11:00:00+00:00",
            action_type="HANDLER_ACTION_TASK_COMPLETE",
            actor_id="user_124",
            payload='{"task": "test task"}',
            sequence_number=2,
            prev_hash="hash_001",
            entry_hash="hash_002",
            signature="sig_002",
        ),
        _make_persist_audit_row(
            entry_id="evt-003",
            recorded_at="2025-08-31T09:00:00+00:00",
            action_type="HANDLER_ACTION_SPEAK",
            actor_id="user_125",
            payload='{"message": "old message"}',
            sequence_number=3,
            prev_hash="hash_002",
            entry_hash="hash_003",
            signature="sig_003",
        ),
    ]

    fake_engine = _FakePersistAuditEngine(rows)
    prior_engine = _graph_mod._engine
    prior_dsn = _graph_mod._engine_dsn
    set_persist_engine(fake_engine, dsn="sqlite:///:memory:")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        yield db_path
    finally:
        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
        try:
            Path(db_path).unlink()
        except OSError:
            pass


@pytest.fixture
def mock_jsonl_file():
    """Create a temporary JSONL file with test audit data."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        # Write test JSONL entries
        test_entries = [
            {
                "id": "jsonl_001",
                "timestamp": "2025-09-01T12:00:00+00:00",
                "action": "USER_LOGIN",
                "actor": "user_200",
                "description": "User login event",
                "signature": "jsonl_sig_001",
                "hash_chain": "jsonl_hash_001",
            },
            {
                "id": "jsonl_002",
                "timestamp": "2025-09-01T13:00:00+00:00",
                "action": "FILE_UPLOAD",
                "actor": "user_201",
                "description": "File upload event",
                "signature": "jsonl_sig_002",
                "hash_chain": "jsonl_hash_002",
            },
            {
                "id": "jsonl_003",
                "timestamp": "2025-08-30T08:00:00+00:00",
                "action": "USER_LOGOUT",
                "actor": "user_202",
                "description": "Old logout event",
                "signature": "jsonl_sig_003",
                "hash_chain": "jsonl_hash_003",
            },
        ]

        for entry in test_entries:
            f.write(json.dumps(entry) + "\n")

        jsonl_path = f.name

    yield jsonl_path
    Path(jsonl_path).unlink()


@pytest.fixture
def mock_graph_entries():
    """Create mock graph audit entries."""
    mock1 = MagicMock()
    mock1.id = "graph_001"
    mock1.action = "THOUGHT_CREATED"
    mock1.actor = "graph_user_300"
    mock1.timestamp = datetime(2025, 9, 1, 14, 0, 0, tzinfo=timezone.utc)
    mock1.signature = "graph_sig_001"
    mock1.hash_chain = "graph_hash_001"

    # Create mock context that behaves properly
    mock1.context = MagicMock()
    mock1.context.description = "Graph thought created"
    mock1.context.model_dump.return_value = {"description": "Graph thought created"}

    mock2 = MagicMock()
    mock2.id = "graph_002"
    mock2.action = "MEMORY_STORED"
    mock2.actor = "graph_user_301"
    mock2.timestamp = datetime(2025, 9, 1, 15, 0, 0, tzinfo=timezone.utc)
    mock2.signature = "graph_sig_002"
    mock2.hash_chain = "graph_hash_002"

    mock2.context = MagicMock()
    mock2.context.description = "Graph memory stored"
    mock2.context.model_dump.return_value = {"description": "Graph memory stored"}

    return [mock1, mock2]


class TestQuerySQLiteAudit:
    """Test SQLite audit querying functionality."""

    @pytest.mark.asyncio
    async def test_query_sqlite_basic(self, mock_sqlite_db):
        """Test basic SQLite audit querying."""
        entries = await _query_sqlite_audit(mock_sqlite_db)

        assert len(entries) == 3
        assert entries[0]["event_id"] == "evt-002"  # Newest first
        assert entries[1]["event_id"] == "evt-001"
        assert entries[2]["event_id"] == "evt-003"

    @pytest.mark.asyncio
    async def test_query_sqlite_with_time_range(self, mock_sqlite_db):
        """Test SQLite querying with time range filters."""
        start_time = datetime(2025, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2025, 9, 1, 23, 59, 59, tzinfo=timezone.utc)

        entries = await _query_sqlite_audit(mock_sqlite_db, start_time=start_time, end_time=end_time)

        assert len(entries) == 2  # Only Sept 1 entries
        assert all("2025-09-01" in entry["event_timestamp"] for entry in entries)

    @pytest.mark.asyncio
    async def test_query_sqlite_with_pagination(self, mock_sqlite_db):
        """Test SQLite querying with pagination."""
        entries = await _query_sqlite_audit(mock_sqlite_db, limit=1, offset=1)

        assert len(entries) == 1
        assert entries[0]["event_id"] == "evt-001"

    @pytest.mark.asyncio
    async def test_query_sqlite_nonexistent_db(self):
        """Test querying when no persist engine is wired returns []."""
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        _graph_mod._engine = None
        _graph_mod._engine_dsn = None
        try:
            entries = await _query_sqlite_audit("/nonexistent/path.db")
            assert entries == []
        finally:
            _graph_mod._engine = prior_engine
            _graph_mod._engine_dsn = prior_dsn


class TestQueryJSONLAudit:
    """Test JSONL audit querying functionality."""

    @pytest.mark.asyncio
    async def test_query_jsonl_basic(self, mock_jsonl_file):
        """Test basic JSONL audit querying."""
        entries = await _query_jsonl_audit(mock_jsonl_file)

        assert len(entries) == 3
        assert entries[0]["id"] == "jsonl_002"  # Newest first
        assert entries[1]["id"] == "jsonl_001"
        assert entries[2]["id"] == "jsonl_003"

    @pytest.mark.asyncio
    async def test_query_jsonl_with_time_range(self, mock_jsonl_file):
        """Test JSONL querying with time range filters."""
        start_time = datetime(2025, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2025, 9, 1, 23, 59, 59, tzinfo=timezone.utc)

        entries = await _query_jsonl_audit(mock_jsonl_file, start_time=start_time, end_time=end_time)

        assert len(entries) == 2  # Only Sept 1 entries
        assert all("2025-09-01" in entry["timestamp"] for entry in entries)

    @pytest.mark.asyncio
    async def test_query_jsonl_with_pagination(self, mock_jsonl_file):
        """Test JSONL querying with pagination."""
        entries = await _query_jsonl_audit(mock_jsonl_file, limit=1, offset=1)

        assert len(entries) == 1
        assert entries[0]["id"] == "jsonl_001"

    @pytest.mark.asyncio
    async def test_query_jsonl_nonexistent_file(self):
        """Test JSONL querying with nonexistent file."""
        entries = await _query_jsonl_audit("/nonexistent/path.jsonl")
        assert entries == []

    @pytest.mark.asyncio
    async def test_query_jsonl_invalid_json_lines(self, mock_jsonl_file):
        """Test JSONL querying handles invalid JSON lines gracefully."""
        # Append invalid JSON to test file
        with open(mock_jsonl_file, "a") as f:
            f.write("invalid json line\n")
            f.write('{"valid": "json"}\n')

        entries = await _query_jsonl_audit(mock_jsonl_file)

        # Should still get the 3 original valid entries plus 1 new valid entry
        assert len(entries) == 4


class TestMergeAuditSources:
    """Test audit source merging functionality."""

    @pytest.mark.asyncio
    async def test_merge_all_sources(self, mock_graph_entries, mock_sqlite_db, mock_jsonl_file):
        """Test merging audit entries - all unique entries from all sources are preserved."""
        # Get data from fixtures
        sqlite_entries = await _query_sqlite_audit(mock_sqlite_db)
        jsonl_entries = await _query_jsonl_audit(mock_jsonl_file)

        # Merge all sources - entries are deduplicated by timestamp+action
        merged = await _merge_audit_sources(mock_graph_entries, sqlite_entries, jsonl_entries)

        # Should have entries from all sources (unique by timestamp+action)
        # 3 sqlite + 2 jsonl + 2 graph = 7-8 (depending on dedup)
        assert len(merged) >= 3  # At least sqlite entries

        # Check we have entries from multiple sources
        all_sources = set()
        for entry in merged:
            all_sources.update(entry.storage_sources)
        # SQLite entries should always be present
        assert "sqlite" in all_sources

    @pytest.mark.asyncio
    async def test_merge_with_duplicates(self, mock_graph_entries):
        """Test merging handles duplicate entries - entries show all sources they appear in."""
        # Create duplicate entries across sources (same timestamp+action = same event)
        sqlite_entries = [
            {
                "event_id": "graph_001",  # Same ID as graph entry
                "event_timestamp": "2025-09-01T14:00:00+00:00",
                "event_type": "THOUGHT_CREATED",
                "originator_id": "graph_user_300",
                "event_payload": '{"duplicate": "from sqlite"}',
                "signature": "sqlite_sig_001",
                "previous_hash": "sqlite_hash_001",
            }
        ]

        jsonl_entries = [
            {
                "id": "graph_001",  # Same ID as graph entry
                "timestamp": "2025-09-01T14:00:00+00:00",
                "action": "THOUGHT_CREATED",
                "actor": "graph_user_300",
                "description": "Duplicate from JSONL",
                "signature": "jsonl_sig_001",
                "hash_chain": "jsonl_hash_001",
            }
        ]

        merged = await _merge_audit_sources(mock_graph_entries[:1], sqlite_entries, jsonl_entries)

        # Should be deduplicated to 1 entry (same timestamp+action)
        assert len(merged) == 1

        # Entry should show all sources it appears in (sorted alphabetically)
        graph_001_entry = next(entry for entry in merged if entry.id == "graph_001")
        assert "sqlite" in graph_001_entry.storage_sources  # SQLite is authoritative
        # May also include graph and/or jsonl if they were merged

    @pytest.mark.asyncio
    async def test_merge_empty_sources(self):
        """Test merging with empty sources."""
        merged = await _merge_audit_sources([], [], [])
        assert merged == []

    @pytest.mark.asyncio
    async def test_merge_single_source(self, mock_graph_entries):
        """Test merging with only one source."""
        merged = await _merge_audit_sources(mock_graph_entries, [], [])

        assert len(merged) == 2
        assert all(entry.storage_sources == ["graph"] for entry in merged)

    @pytest.mark.asyncio
    async def test_merge_sorting_by_timestamp(self):
        """Test merged entries are sorted by timestamp (newest first)."""
        # Create multiple SQLite entries with specific timestamps
        sqlite_entries = [
            {
                "event_id": "oldest",
                "event_timestamp": "2025-08-01T10:00:00+00:00",
                "event_type": "OLD_EVENT",
                "originator_id": "old_user",
            },
            {
                "event_id": "newest",
                "event_timestamp": "2025-09-02T10:00:00+00:00",
                "event_type": "NEW_EVENT",
                "originator_id": "new_user",
            },
            {
                "event_id": "middle",
                "event_timestamp": "2025-08-15T10:00:00+00:00",
                "event_type": "MIDDLE_EVENT",
                "originator_id": "middle_user",
            },
        ]

        merged = await _merge_audit_sources([], sqlite_entries, [])

        # Check entries are sorted newest first
        timestamps = [entry.timestamp for entry in merged]
        assert timestamps == sorted(timestamps, reverse=True)
        assert merged[0].id == "newest"


class TestAuditEntryResponseSchema:
    """Test AuditEntryResponse schema with storage_sources field."""

    def test_storage_sources_default(self):
        """Test storage_sources field has proper default."""
        entry = AuditEntryResponse(
            id="test_001",
            action="TEST_ACTION",
            actor="test_user",
            timestamp=datetime.now(timezone.utc),
            context=AuditContext(),
        )

        assert entry.storage_sources == []

    def test_storage_sources_assignment(self):
        """Test storage_sources field accepts list values."""
        entry = AuditEntryResponse(
            id="test_001",
            action="TEST_ACTION",
            actor="test_user",
            timestamp=datetime.now(timezone.utc),
            context=AuditContext(),
            storage_sources=["graph", "sqlite", "jsonl"],
        )

        assert entry.storage_sources == ["graph", "sqlite", "jsonl"]

    def test_storage_sources_serialization(self):
        """Test storage_sources field serializes correctly."""
        entry = AuditEntryResponse(
            id="test_001",
            action="TEST_ACTION",
            actor="test_user",
            timestamp=datetime.now(timezone.utc),
            context=AuditContext(),
            storage_sources=["graph", "sqlite"],
        )

        serialized = entry.model_dump()
        assert "storage_sources" in serialized
        assert serialized["storage_sources"] == ["graph", "sqlite"]


class TestErrorHandling:
    """Test error handling in audit querying functions."""

    @pytest.mark.asyncio
    async def test_sqlite_db_permission_error(self):
        """Test SQLite querying returns [] when persist engine unavailable.

        2.9.0: `_query_sqlite_audit` no longer touches the legacy file
        directly — it routes through `engine.audit_list_entries`. The
        wrapper returns [] when the persist engine isn't wired, so the
        permission-error scenario is now equivalent to the
        "engine missing" scenario (both fail closed, returning []).
        """
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        _graph_mod._engine = None
        _graph_mod._engine_dsn = None
        try:
            entries = await _query_sqlite_audit("/nonexistent/path.db")
            assert entries == []
        finally:
            _graph_mod._engine = prior_engine
            _graph_mod._engine_dsn = prior_dsn

    @pytest.mark.asyncio
    async def test_jsonl_file_permission_error(self):
        """Test JSONL querying handles permission errors."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write('{"test": "data"}\n')
            jsonl_path = f.name

        # Make file unreadable
        Path(jsonl_path).chmod(0o000)

        try:
            entries = await _query_jsonl_audit(jsonl_path)
            assert entries == []  # Should return empty list on error
        finally:
            # Restore permissions and cleanup
            Path(jsonl_path).chmod(0o644)
            Path(jsonl_path).unlink()

    @pytest.mark.asyncio
    async def test_merge_handles_malformed_entries(self):
        """Test merging handles malformed entries gracefully."""
        # Create malformed entries with minimal required fields
        # SQLite is authoritative, so when present only SQLite entries are used
        malformed_sqlite = [
            {
                "event_id": "malformed_001",
                "event_timestamp": "2025-09-01T10:00:00+00:00",
                "event_type": "UNKNOWN_EVENT",
                "originator_id": "unknown_user",
                # Missing optional fields like event_payload
            }
        ]

        # Should not raise exception
        merged = await _merge_audit_sources([], malformed_sqlite, [])

        # Should still create entries with defaults
        assert len(merged) == 1

        # Check that default values are used for missing fields
        for entry in merged:
            assert entry.action is not None
            assert entry.actor is not None
            assert entry.timestamp is not None

    @pytest.mark.asyncio
    async def test_merge_handles_malformed_jsonl_when_no_sqlite(self):
        """Test JSONL entries with missing fields get defaults when no SQLite."""
        malformed_jsonl = [
            {
                "id": "malformed_jsonl_001",
                "timestamp": "2025-09-01T11:00:00+00:00",
                # Missing action and actor - should use defaults
            }
        ]

        # No SQLite entries, so JSONL will be processed
        merged = await _merge_audit_sources([], [], malformed_jsonl)

        # Should still create entry with defaults
        assert len(merged) == 1
        assert merged[0].action is not None
        assert merged[0].actor is not None


class TestOutcomeExtraction:
    """Test outcome extraction from audit entries."""

    @pytest.mark.asyncio
    async def test_sqlite_entry_with_fail_event_type_has_failure_outcome(self):
        """Test SQLite entry with 'fail' in event_type gets outcome='failure'."""
        sqlite_entries = [
            {
                "event_id": "fail_001",
                "event_timestamp": "2025-09-01T10:00:00+00:00",
                "event_type": "HANDLER_ACTION_FAILED",  # Contains 'fail'
                "originator_id": "test_user",
            }
        ]

        merged = await _merge_audit_sources([], sqlite_entries, [])

        assert len(merged) == 1
        assert merged[0].context.outcome == "failure"

    @pytest.mark.asyncio
    async def test_sqlite_entry_with_error_event_type_has_failure_outcome(self):
        """Test SQLite entry with 'error' in event_type gets outcome='failure'."""
        sqlite_entries = [
            {
                "event_id": "error_001",
                "event_timestamp": "2025-09-01T10:00:00+00:00",
                "event_type": "TOOL_EXECUTION_ERROR",  # Contains 'error'
                "originator_id": "test_user",
            }
        ]

        merged = await _merge_audit_sources([], sqlite_entries, [])

        assert len(merged) == 1
        assert merged[0].context.outcome == "failure"

    @pytest.mark.asyncio
    async def test_sqlite_entry_with_success_event_type_has_success_outcome(self):
        """Test SQLite entry with normal event_type gets outcome='success'."""
        sqlite_entries = [
            {
                "event_id": "success_001",
                "event_timestamp": "2025-09-01T10:00:00+00:00",
                "event_type": "HANDLER_ACTION_SPEAK",  # Normal event
                "originator_id": "test_user",
            }
        ]

        merged = await _merge_audit_sources([], sqlite_entries, [])

        assert len(merged) == 1
        assert merged[0].context.outcome == "success"

    @pytest.mark.asyncio
    async def test_jsonl_entry_with_fail_action_has_failure_outcome(self):
        """Test JSONL entry with 'fail' in action gets outcome='failure'."""
        jsonl_entries = [
            {
                "id": "jsonl_fail_001",
                "timestamp": "2025-09-01T10:00:00+00:00",
                "action": "TASK_FAILED",  # Contains 'fail'
                "actor": "test_user",
            }
        ]

        merged = await _merge_audit_sources([], [], jsonl_entries)

        assert len(merged) == 1
        assert merged[0].context.outcome == "failure"

    @pytest.mark.asyncio
    async def test_jsonl_entry_with_error_action_has_failure_outcome(self):
        """Test JSONL entry with 'error' in action gets outcome='failure'."""
        jsonl_entries = [
            {
                "id": "jsonl_error_001",
                "timestamp": "2025-09-01T10:00:00+00:00",
                "action": "CONNECTION_ERROR",  # Contains 'error'
                "actor": "test_user",
            }
        ]

        merged = await _merge_audit_sources([], [], jsonl_entries)

        assert len(merged) == 1
        assert merged[0].context.outcome == "failure"

    @pytest.mark.asyncio
    async def test_jsonl_entry_with_success_action_has_success_outcome(self):
        """Test JSONL entry with normal action gets outcome='success'."""
        jsonl_entries = [
            {
                "id": "jsonl_success_001",
                "timestamp": "2025-09-01T10:00:00+00:00",
                "action": "MESSAGE_SENT",  # Normal action
                "actor": "test_user",
            }
        ]

        merged = await _merge_audit_sources([], [], jsonl_entries)

        assert len(merged) == 1
        assert merged[0].context.outcome == "success"

    @pytest.mark.asyncio
    async def test_defer_reason_extracted_from_sqlite_payload(self):
        """Test that defer_reason is extracted from event_payload JSON in SQLite entries."""
        # Create SQLite entries with defer_reason in parameters
        sqlite_entries = [
            {
                "event_id": "defer_evt_001",
                "event_timestamp": "2025-09-01T10:00:00+00:00",
                "event_type": "HANDLER_ACTION_DEFER",
                "originator_id": "user_defer",
                "event_payload": json.dumps(
                    {
                        "action_type": "DEFER",
                        "parameters": json.dumps(
                            {
                                "defer_reason": "Waiting for human approval",
                                "defer_until": "2025-09-02T10:00:00+00:00",
                            }
                        ),
                    }
                ),
                "sequence_number": 1,
                "entry_hash": "hash_defer_001",
                "signature": "sig_defer_001",
            }
        ]

        merged = await _merge_audit_sources([], sqlite_entries, [])

        assert len(merged) == 1
        assert merged[0].context.metadata is not None
        assert merged[0].context.metadata.get("defer_reason") == "Waiting for human approval"

    @pytest.mark.asyncio
    async def test_defer_reason_extracted_from_nested_parameters(self):
        """Test that defer_reason is extracted even with deeply nested parameters JSON."""
        # Create SQLite entries with nested JSON structure
        sqlite_entries = [
            {
                "event_id": "defer_nested_001",
                "event_timestamp": "2025-09-01T11:00:00+00:00",
                "event_type": "HANDLER_ACTION_DEFER",
                "originator_id": "user_nested",
                "event_payload": json.dumps(
                    {
                        "handler": "defer_handler",
                        "parameters": json.dumps(
                            {
                                "defer_reason": "Requires WA guidance",
                                "context": {"priority": "high"},
                            }
                        ),
                    }
                ),
                "sequence_number": 2,
                "entry_hash": "hash_nested_001",
                "signature": "sig_nested_001",
            }
        ]

        merged = await _merge_audit_sources([], sqlite_entries, [])

        assert len(merged) == 1
        assert merged[0].context.metadata.get("defer_reason") == "Requires WA guidance"

    @pytest.mark.asyncio
    async def test_sqlite_authoritative_deduplication(self):
        """Test that entries with same timestamp+action are deduplicated, with SQLite as authoritative."""
        # Create mock graph entry with SAME action as SQLite for deduplication
        mock_graph = MagicMock()
        mock_graph.id = "graph_dup_001"
        mock_graph.action = "HANDLER_ACTION_SPEAK"  # Same action as SQLite
        mock_graph.actor = "user_graph"
        mock_graph.timestamp = datetime(2025, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
        mock_graph.signature = "graph_sig_001"
        mock_graph.hash_chain = "graph_hash_001"
        mock_graph.context = MagicMock()
        mock_graph.context.model_dump.return_value = {}

        graph_entries = [mock_graph]

        sqlite_entries = [
            {
                "event_id": "sqlite_auth_001",
                "event_timestamp": "2025-09-01T10:00:00+00:00",
                "event_type": "HANDLER_ACTION_SPEAK",
                "originator_id": "user_sqlite",
                "event_payload": "{}",
                "sequence_number": 1,
                "entry_hash": "hash_sqlite_001",
                "signature": "sig_sqlite_001",
            }
        ]

        jsonl_entries = [
            {
                "id": "jsonl_dup_001",
                "timestamp": "2025-09-01T10:00:00+00:00",
                "action": "HANDLER_ACTION_SPEAK",  # Same action as SQLite
                "actor": "user_jsonl",
            }
        ]

        merged = await _merge_audit_sources(graph_entries, sqlite_entries, jsonl_entries)

        # Should be deduplicated to 1 entry (same timestamp+action)
        assert len(merged) == 1
        # SQLite is authoritative - should have its signature
        assert merged[0].signature == "sig_sqlite_001"
        # SQLite should be in storage_sources
        assert "sqlite" in merged[0].storage_sources

    @pytest.mark.asyncio
    async def test_graph_and_jsonl_used_when_sqlite_empty(self):
        """Test that graph and JSONL sources are used when SQLite has no entries."""
        # Create mock graph entry
        mock_graph = MagicMock()
        mock_graph.id = "graph_only_001"
        mock_graph.action = "SPEAK"
        mock_graph.actor = "user_graph"
        mock_graph.timestamp = datetime(2025, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
        mock_graph.signature = "graph_sig_001"
        mock_graph.hash_chain = "graph_hash_001"
        mock_graph.context = MagicMock()
        mock_graph.context.model_dump.return_value = {}

        graph_entries = [mock_graph]

        jsonl_entries = [
            {
                "id": "jsonl_only_001",
                "timestamp": "2025-09-01T11:00:00+00:00",
                "action": "TOOL_USE",
                "actor": "user_jsonl",
            }
        ]

        # Empty SQLite entries
        sqlite_entries: List[dict] = []

        merged = await _merge_audit_sources(graph_entries, sqlite_entries, jsonl_entries)

        # Should have entries from both graph and JSONL
        assert len(merged) == 2
        entry_ids = [e.id for e in merged]
        assert "graph_only_001" in entry_ids
        assert "jsonl_only_001" in entry_ids

    @pytest.mark.asyncio
    async def test_jsonl_source_added_when_graph_entry_exists(self):
        """Test that JSONL source is added to graph entry when they have same timestamp+action."""
        # Create mock graph entry
        mock_graph = MagicMock()
        mock_graph.id = "graph_dup_002"
        mock_graph.action = "SPEAK"
        mock_graph.actor = "user_graph"
        mock_graph.timestamp = datetime(2025, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
        mock_graph.signature = "graph_sig_002"
        mock_graph.hash_chain = "graph_hash_002"
        mock_graph.context = MagicMock()
        mock_graph.context.model_dump.return_value = {}

        graph_entries = [mock_graph]

        # JSONL entry with SAME timestamp+action (should be deduplicated, adding jsonl to sources)
        jsonl_entries = [
            {
                "id": "jsonl_dup_002",
                "timestamp": "2025-09-01T10:00:00+00:00",  # Same timestamp
                "action": "SPEAK",  # Same action
                "actor": "user_jsonl",
            }
        ]

        # No SQLite entries - graph is first source
        sqlite_entries: List[dict] = []

        merged = await _merge_audit_sources(graph_entries, sqlite_entries, jsonl_entries)

        # Should be deduplicated to 1 entry
        assert len(merged) == 1
        # Should have both graph and jsonl in storage_sources
        assert "graph" in merged[0].storage_sources
        assert "jsonl" in merged[0].storage_sources

    @pytest.mark.asyncio
    async def test_malformed_payload_json_handled_gracefully(self):
        """Test that malformed event_payload JSON doesn't crash metadata extraction."""
        sqlite_entries = [
            {
                "event_id": "malformed_001",
                "event_timestamp": "2025-09-01T10:00:00+00:00",
                "event_type": "HANDLER_ACTION_DEFER",
                "originator_id": "user_malformed",
                "event_payload": "not valid json {{{",  # Invalid JSON
                "sequence_number": 1,
                "entry_hash": "hash_malformed_001",
                "signature": "sig_malformed_001",
            }
        ]

        # Should not raise exception
        merged = await _merge_audit_sources([], sqlite_entries, [])

        assert len(merged) == 1
        # Metadata should be empty dict since JSON parsing failed
        assert (
            merged[0].context.metadata == {}
            or merged[0].context.metadata is None
            or "defer_reason" not in merged[0].context.metadata
        )

    @pytest.mark.asyncio
    async def test_action_parameters_extracted_from_payload(self):
        """Test that relevant parameters are extracted from event_payload."""
        sqlite_entries = [
            {
                "event_id": "params_001",
                "event_timestamp": "2025-09-01T10:00:00+00:00",
                "event_type": "HANDLER_ACTION_SPEAK",
                "originator_id": "user_params",
                "event_payload": json.dumps(
                    {
                        "action_type": "SPEAK",
                        "thought_id": "thought_123",
                        "parameters": json.dumps(
                            {
                                "content": "Hello world",
                                "channel_id": "test_channel",
                            }
                        ),
                    }
                ),
                "sequence_number": 1,
                "entry_hash": "hash_params_001",
                "signature": "sig_params_001",
            }
        ]

        merged = await _merge_audit_sources([], sqlite_entries, [])

        assert len(merged) == 1
        # Check that relevant fields were extracted to metadata
        metadata = merged[0].context.metadata
        assert metadata is not None
        # 'content' is extracted from parameters
        assert metadata.get("content") == "Hello world"
        # 'action_type' and 'thought_id' are extracted from payload
        assert metadata.get("action_type") == "SPEAK"
        assert metadata.get("thought_id") == "thought_123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
