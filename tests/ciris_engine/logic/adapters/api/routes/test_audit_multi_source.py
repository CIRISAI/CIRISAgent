"""
Comprehensive unit tests for multi-source audit API functionality.

Tests the enhanced audit API that queries graph memory, SQLite database, and JSONL files.
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from ciris_engine.logic.adapters.api.routes.audit import (
    _merge_audit_sources,
    _query_jsonl_audit,
    _query_sqlite_audit,
    AuditEntryResponse,
)
from ciris_engine.schemas.api.audit import AuditContext
from ciris_engine.schemas.services.nodes import AuditEntry


@pytest.fixture
def mock_sqlite_db():
    """Create a temporary SQLite database with test audit data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Create database with audit schema
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE audit_log (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                originator_id TEXT NOT NULL,
                event_payload TEXT,
                sequence_number INTEGER NOT NULL,
                previous_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL,
                signature TEXT NOT NULL,
                signing_key_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert test data
        test_entries = [
            ("evt-001", "2025-09-01T10:00:00+00:00", "HANDLER_ACTION_SPEAK", "user_123", 
             '{"message": "test message 1"}', 1, "hash_000", "hash_001", "sig_001", "key_001"),
            ("evt-002", "2025-09-01T11:00:00+00:00", "HANDLER_ACTION_TASK_COMPLETE", "user_124",
             '{"task": "test task"}', 2, "hash_001", "hash_002", "sig_002", "key_001"),
            ("evt-003", "2025-08-31T09:00:00+00:00", "HANDLER_ACTION_SPEAK", "user_125",
             '{"message": "old message"}', 3, "hash_002", "hash_003", "sig_003", "key_001"),
        ]
        
        for entry in test_entries:
            cursor.execute("""
                INSERT INTO audit_log 
                (event_id, event_timestamp, event_type, originator_id, event_payload, 
                 sequence_number, previous_hash, entry_hash, signature, signing_key_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, entry)
        
        conn.commit()
    
    yield db_path
    Path(db_path).unlink()


@pytest.fixture
def mock_jsonl_file():
    """Create a temporary JSONL file with test audit data."""
    with tempfile.NamedTemporaryFile(mode='w', suffix=".jsonl", delete=False) as f:
        # Write test JSONL entries
        test_entries = [
            {
                "id": "jsonl_001",
                "timestamp": "2025-09-01T12:00:00+00:00",
                "action": "USER_LOGIN",
                "actor": "user_200",
                "description": "User login event",
                "signature": "jsonl_sig_001",
                "hash_chain": "jsonl_hash_001"
            },
            {
                "id": "jsonl_002", 
                "timestamp": "2025-09-01T13:00:00+00:00",
                "action": "FILE_UPLOAD",
                "actor": "user_201",
                "description": "File upload event",
                "signature": "jsonl_sig_002",
                "hash_chain": "jsonl_hash_002"
            },
            {
                "id": "jsonl_003",
                "timestamp": "2025-08-30T08:00:00+00:00", 
                "action": "USER_LOGOUT",
                "actor": "user_202",
                "description": "Old logout event",
                "signature": "jsonl_sig_003",
                "hash_chain": "jsonl_hash_003"
            }
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
        
        entries = await _query_sqlite_audit(
            mock_sqlite_db,
            start_time=start_time,
            end_time=end_time
        )
        
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
        """Test SQLite querying with nonexistent database."""
        entries = await _query_sqlite_audit("/nonexistent/path.db")
        assert entries == []


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
        
        entries = await _query_jsonl_audit(
            mock_jsonl_file,
            start_time=start_time,
            end_time=end_time
        )
        
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
        """Test merging audit entries from all sources."""
        # Get data from fixtures
        sqlite_entries = await _query_sqlite_audit(mock_sqlite_db)
        jsonl_entries = await _query_jsonl_audit(mock_jsonl_file)
        
        # Merge all sources
        merged = await _merge_audit_sources(mock_graph_entries, sqlite_entries, jsonl_entries)
        
        # Should have all entries from all sources (no duplicates in this test)
        assert len(merged) == 7  # 2 graph + 3 sqlite + 3 jsonl - 1 duplicate
        
        # Check storage sources are properly tracked
        storage_sources = [entry.storage_sources for entry in merged]
        assert ["graph"] in storage_sources
        assert ["jsonl"] in storage_sources  
        assert ["sqlite"] in storage_sources

    @pytest.mark.asyncio
    async def test_merge_with_duplicates(self, mock_graph_entries):
        """Test merging handles duplicate entries correctly."""
        # Create duplicate entries across sources
        sqlite_entries = [
            {
                "event_id": "graph_001",  # Same ID as graph entry
                "event_timestamp": "2025-09-01T14:00:00+00:00",
                "event_type": "THOUGHT_CREATED",
                "originator_id": "graph_user_300",
                "event_payload": '{"duplicate": "from sqlite"}',
                "signature": "sqlite_sig_001",
                "previous_hash": "sqlite_hash_001"
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
                "hash_chain": "jsonl_hash_001"
            }
        ]
        
        merged = await _merge_audit_sources(mock_graph_entries[:1], sqlite_entries, jsonl_entries)
        
        # Should have only 2 unique entries (graph_001 and graph_002)
        assert len(merged) == 2
        
        # graph_001 should have all 3 storage sources
        graph_001_entry = next(entry for entry in merged if entry.id == "graph_001")
        assert sorted(graph_001_entry.storage_sources) == ["graph", "jsonl", "sqlite"]

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
    async def test_merge_sorting_by_timestamp(self, mock_graph_entries):
        """Test merged entries are sorted by timestamp (newest first).""" 
        # Create entries with specific timestamps
        sqlite_entries = [
            {
                "event_id": "oldest",
                "event_timestamp": "2025-08-01T10:00:00+00:00",
                "event_type": "OLD_EVENT",
                "originator_id": "old_user"
            }
        ]
        
        jsonl_entries = [
            {
                "id": "newest",
                "timestamp": "2025-09-02T10:00:00+00:00",
                "action": "NEW_EVENT", 
                "actor": "new_user"
            }
        ]
        
        merged = await _merge_audit_sources(mock_graph_entries, sqlite_entries, jsonl_entries)
        
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
            context=AuditContext()
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
            storage_sources=["graph", "sqlite", "jsonl"]
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
            storage_sources=["graph", "sqlite"]
        )
        
        serialized = entry.model_dump()
        assert "storage_sources" in serialized
        assert serialized["storage_sources"] == ["graph", "sqlite"]


class TestErrorHandling:
    """Test error handling in audit querying functions."""

    @pytest.mark.asyncio
    async def test_sqlite_db_permission_error(self):
        """Test SQLite querying handles permission errors."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            db_path = f.name
        
        # Make file unreadable
        Path(db_path).chmod(0o000)
        
        try:
            entries = await _query_sqlite_audit(db_path)
            assert entries == []  # Should return empty list on error
        finally:
            # Restore permissions and cleanup
            Path(db_path).chmod(0o644)
            Path(db_path).unlink()

    @pytest.mark.asyncio
    async def test_jsonl_file_permission_error(self):
        """Test JSONL querying handles permission errors."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
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
        malformed_sqlite = [
            {
                "event_id": "malformed_001",
                "event_timestamp": "2025-09-01T10:00:00+00:00",
                "event_type": "UNKNOWN_EVENT", 
                "originator_id": "unknown_user"
                # Missing optional fields like event_payload
            }
        ]
        
        malformed_jsonl = [
            {
                "id": "malformed_002",
                "timestamp": "2025-09-01T11:00:00+00:00",
                # Missing action and actor - should use defaults
            }
        ]
        
        # Should not raise exception
        merged = await _merge_audit_sources([], malformed_sqlite, malformed_jsonl)
        
        # Should still create entries with defaults
        assert len(merged) == 2
        
        # Check that default values are used for missing fields
        for entry in merged:
            assert entry.action is not None
            assert entry.actor is not None
            assert entry.timestamp is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])