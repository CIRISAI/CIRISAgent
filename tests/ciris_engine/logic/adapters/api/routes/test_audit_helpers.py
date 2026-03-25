"""
Unit tests for audit API helper functions.

Tests the extracted helper functions used to reduce cognitive complexity
in the audit multi-source merging logic.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.adapters.api.routes.audit import (
    AuditEntryResponse,
    _MergedAuditEntry,
    _add_new_graph_entry,
    _add_new_sqlite_entry,
    _entry_has_additional_metadata,
    _extract_handler_metadata,
    _extract_sqlite_entry_info,
    _find_sqlite_entry_for_dedup_key,
    _handle_duplicate_graph_entry,
    _infer_outcome_from_event,
    _merge_graph_metadata_into_entry,
    _normalize_timestamp_str,
    _parse_event_payload_metadata,
    _track_sqlite_dedup_key,
)
from ciris_engine.schemas.api.audit import AuditContext
from ciris_engine.schemas.services.nodes import AuditEntry


class TestNormalizeTimestampStr:
    """Tests for _normalize_timestamp_str function."""

    def test_normalizes_space_to_t(self):
        """Should replace space with T for ISO format."""
        result = _normalize_timestamp_str("2026-03-25 01:21:00.503015+00:00")
        assert result == "2026-03-25T01:21:00.503015+00:00"

    def test_preserves_already_normalized(self):
        """Should preserve already normalized timestamps."""
        result = _normalize_timestamp_str("2026-03-25T01:21:00.503015+00:00")
        assert result == "2026-03-25T01:21:00.503015+00:00"

    def test_handles_empty_string(self):
        """Should handle empty string."""
        result = _normalize_timestamp_str("")
        assert result == ""


class TestEntryHasAdditionalMetadata:
    """Tests for _entry_has_additional_metadata function."""

    def test_returns_true_with_metadata(self):
        """Should return True when entry has additional_data."""
        entry = MagicMock(spec=AuditEntry)
        entry.context = MagicMock()
        entry.context.additional_data = {"key": "value"}
        assert _entry_has_additional_metadata(entry) is True

    def test_returns_false_without_context(self):
        """Should return False when entry has no context."""
        entry = MagicMock()
        del entry.context  # Remove context attribute
        assert _entry_has_additional_metadata(entry) is False

    def test_returns_false_without_additional_data_attr(self):
        """Should return False when context has no additional_data."""
        entry = MagicMock(spec=AuditEntry)
        entry.context = MagicMock()
        del entry.context.additional_data  # Remove additional_data attribute
        assert _entry_has_additional_metadata(entry) is False

    def test_returns_false_with_empty_additional_data(self):
        """Should return False when additional_data is empty."""
        entry = MagicMock(spec=AuditEntry)
        entry.context = MagicMock()
        entry.context.additional_data = {}
        assert _entry_has_additional_metadata(entry) is False

    def test_returns_false_with_none_additional_data(self):
        """Should return False when additional_data is None."""
        entry = MagicMock(spec=AuditEntry)
        entry.context = MagicMock()
        entry.context.additional_data = None
        assert _entry_has_additional_metadata(entry) is False


class TestInferOutcomeFromEvent:
    """Tests for _infer_outcome_from_event function."""

    def test_returns_provided_outcome(self):
        """Should return provided outcome when not None."""
        assert _infer_outcome_from_event("custom_outcome", "some_event") == "custom_outcome"

    def test_infers_failure_from_fail_event(self):
        """Should infer failure when event_type contains 'fail'."""
        assert _infer_outcome_from_event(None, "action_failed") == "failure"
        assert _infer_outcome_from_event(None, "TASK_FAIL") == "failure"

    def test_infers_failure_from_error_event(self):
        """Should infer failure when event_type contains 'error'."""
        assert _infer_outcome_from_event(None, "error_occurred") == "failure"
        assert _infer_outcome_from_event(None, "VALIDATION_ERROR") == "failure"

    def test_infers_success_for_normal_events(self):
        """Should infer success for normal events."""
        assert _infer_outcome_from_event(None, "task_complete") == "success"
        assert _infer_outcome_from_event(None, "SPEAK") == "success"
        assert _infer_outcome_from_event(None, "MEMORIZE") == "success"

    def test_handles_empty_event_type(self):
        """Should handle empty event_type."""
        assert _infer_outcome_from_event(None, "") == "success"


class TestExtractHandlerMetadata:
    """Tests for _extract_handler_metadata function."""

    def test_extracts_defer_params(self):
        """Should extract DEFER handler parameters."""
        params = {"defer_reason": "need_human_input", "defer_until": "2026-03-26"}
        result = _extract_handler_metadata(params)
        assert result["defer_reason"] == "need_human_input"
        assert result["defer_until"] == "2026-03-26"

    def test_extracts_tool_params_with_tool_name(self):
        """Should extract TOOL handler parameters with tool_name key."""
        params = {"tool_name": "web_search", "parameters": {"query": "test"}}
        result = _extract_handler_metadata(params)
        assert result["tool_name"] == "web_search"
        assert "tool_parameters" in result

    def test_extracts_tool_params_with_name_key(self):
        """Should extract TOOL handler parameters with name key fallback."""
        params = {"name": "calculator"}
        result = _extract_handler_metadata(params)
        assert result["tool_name"] == "calculator"

    def test_extracts_tool_parameters_as_json(self):
        """Should serialize dict parameters as JSON."""
        params = {"parameters": {"key": "value", "nested": {"a": 1}}}
        result = _extract_handler_metadata(params)
        parsed = json.loads(result["tool_parameters"])
        assert parsed == {"key": "value", "nested": {"a": 1}}

    def test_extracts_tool_parameters_as_string(self):
        """Should convert non-dict parameters to string."""
        params = {"parameters": "simple_string"}
        result = _extract_handler_metadata(params)
        assert result["tool_parameters"] == "simple_string"

    def test_extracts_ponder_questions(self):
        """Should extract PONDER handler questions."""
        params = {"ponder_questions": ["What is the meaning?", "How to proceed?"]}
        result = _extract_handler_metadata(params)
        assert result["ponder_questions"] == ["What is the meaning?", "How to proceed?"]

    def test_extracts_ponder_questions_fallback(self):
        """Should extract questions key as fallback for ponder_questions."""
        params = {"questions": ["Question 1"]}
        result = _extract_handler_metadata(params)
        assert result["ponder_questions"] == ["Question 1"]

    def test_extracts_speak_content(self):
        """Should extract SPEAK handler content."""
        params = {"content": "Hello, world!"}
        result = _extract_handler_metadata(params)
        assert result["content"] == "Hello, world!"

    def test_extracts_task_complete_reason(self):
        """Should extract TASK_COMPLETE handler reason."""
        params = {"completion_reason": "Task finished successfully"}
        result = _extract_handler_metadata(params)
        assert result["completion_reason"] == "Task finished successfully"

    def test_extracts_reject_reason(self):
        """Should extract REJECT handler reason."""
        params = {"reason": "Request violates policy"}
        result = _extract_handler_metadata(params)
        assert result["reject_reason"] == "Request violates policy"

    def test_handles_empty_params(self):
        """Should return empty dict for empty params."""
        result = _extract_handler_metadata({})
        assert result == {}

    def test_extracts_multiple_handler_types(self):
        """Should extract all present handler types."""
        params = {
            "defer_reason": "waiting",
            "tool_name": "search",
            "content": "message",
        }
        result = _extract_handler_metadata(params)
        assert result["defer_reason"] == "waiting"
        assert result["tool_name"] == "search"
        assert result["content"] == "message"


class TestParseEventPayloadMetadata:
    """Tests for _parse_event_payload_metadata function."""

    def test_returns_empty_for_none(self):
        """Should return empty metadata and None description for None input."""
        metadata, description = _parse_event_payload_metadata(None)
        assert metadata == {}
        assert description is None

    def test_returns_empty_for_empty_string(self):
        """Should return empty metadata and None description for empty string."""
        metadata, description = _parse_event_payload_metadata("")
        assert metadata == {}
        assert description is None

    def test_handles_invalid_json(self):
        """Should return original string as description for invalid JSON."""
        metadata, description = _parse_event_payload_metadata("not valid json")
        assert metadata == {}
        assert description == "not valid json"

    def test_handles_non_dict_json(self):
        """Should handle JSON that parses to non-dict."""
        metadata, description = _parse_event_payload_metadata('"just a string"')
        assert metadata == {}
        assert description == '"just a string"'

    def test_extracts_direct_payload_fields(self):
        """Should extract direct payload fields."""
        payload = {
            "thought_id": "thought-123",
            "task_id": "task-456",
            "handler_name": "SPEAK",
            "action_type": "speak_action",
        }
        metadata, description = _parse_event_payload_metadata(json.dumps(payload))
        assert metadata["thought_id"] == "thought-123"
        assert metadata["task_id"] == "task-456"
        assert metadata["handler_name"] == "SPEAK"
        assert metadata["action_type"] == "speak_action"

    def test_extracts_nested_parameters(self):
        """Should extract nested parameters with handler metadata."""
        payload = {
            "action_type": "tool_call",
            "parameters": json.dumps({"tool_name": "calculator", "content": "2+2"}),
        }
        metadata, description = _parse_event_payload_metadata(json.dumps(payload))
        assert metadata["tool_name"] == "calculator"
        assert metadata["content"] == "2+2"
        assert metadata["action_type"] == "tool_call"
        assert description == "tool_call"

    def test_uses_action_type_as_description(self):
        """Should use action_type as description."""
        payload = {"action_type": "speak_action", "handler_name": "SPEAK"}
        metadata, description = _parse_event_payload_metadata(json.dumps(payload))
        assert description == "speak_action"

    def test_uses_handler_name_as_fallback_description(self):
        """Should use handler_name as fallback description."""
        payload = {"handler_name": "MEMORIZE"}
        metadata, description = _parse_event_payload_metadata(json.dumps(payload))
        assert description == "MEMORIZE"

    def test_handles_invalid_nested_parameters(self):
        """Should handle invalid JSON in nested parameters."""
        payload = {"parameters": "not valid json", "action_type": "test"}
        metadata, description = _parse_event_payload_metadata(json.dumps(payload))
        assert description == "test"
        # Should not crash, just skip parameter extraction


class TestExtractSqliteEntryInfo:
    """Tests for _extract_sqlite_entry_info function."""

    def test_extracts_all_fields(self):
        """Should extract all required fields from SQLite entry."""
        sqlite_entry = {
            "event_timestamp": "2026-03-25T12:00:00+00:00",
            "originator_id": "user-123",
            "event_type": "SPEAK",
            "event_id": "evt-456",
        }
        result = _extract_sqlite_entry_info(sqlite_entry)
        assert result["event_timestamp"] == "2026-03-25T12:00:00+00:00"
        assert result["originator_id"] == "user-123"
        assert result["event_type"] == "SPEAK"
        assert result["entry_id"] == "evt-456"
        assert result["dedup_key"] == "2026-03-25T12:00:00+00:00_SPEAK"

    def test_generates_entry_id_when_missing(self):
        """Should generate entry_id when event_id is missing."""
        sqlite_entry = {
            "event_timestamp": "2026-03-25T12:00:00+00:00",
            "originator_id": "user-123",
            "event_type": "SPEAK",
        }
        result = _extract_sqlite_entry_info(sqlite_entry)
        assert result["entry_id"] == "audit_2026-03-25T12:00:00+00:00_user-123"

    def test_uses_defaults_for_missing_fields(self):
        """Should use default values for missing fields."""
        sqlite_entry = {}
        result = _extract_sqlite_entry_info(sqlite_entry)
        assert result["event_timestamp"] == ""
        assert result["originator_id"] == "unknown"
        assert result["event_type"] == "unknown"


class TestTrackSqliteDedupKey:
    """Tests for _track_sqlite_dedup_key function."""

    def test_adds_to_seen_timestamps(self):
        """Should add dedup_key to seen_timestamps set."""
        entry_info = {"dedup_key": "2026-03-25T12:00:00_SPEAK", "entry_id": "evt-123"}
        seen_timestamps: set[str] = set()
        dedup_to_entry: Dict[str, str] = {}

        _track_sqlite_dedup_key(entry_info, seen_timestamps, dedup_to_entry)

        assert "2026-03-25T12:00:00_SPEAK" in seen_timestamps

    def test_maps_dedup_key_to_entry_id(self):
        """Should map dedup_key to entry_id."""
        entry_info = {"dedup_key": "2026-03-25T12:00:00_SPEAK", "entry_id": "evt-123"}
        seen_timestamps: set[str] = set()
        dedup_to_entry: Dict[str, str] = {}

        _track_sqlite_dedup_key(entry_info, seen_timestamps, dedup_to_entry)

        assert dedup_to_entry["2026-03-25T12:00:00_SPEAK"] == "evt-123"


class TestMergeGraphMetadataIntoEntry:
    """Tests for _merge_graph_metadata_into_entry function."""

    def test_creates_metadata_dict_if_none(self):
        """Should create metadata dict if it's None."""
        entry_response = AuditEntryResponse(
            id="test-id",
            action="SPEAK",
            actor="user",
            timestamp=datetime.now(timezone.utc),
            context=AuditContext(metadata=None),
        )
        merged_entry = _MergedAuditEntry(entry=entry_response, sources=["sqlite"])

        graph_ctx = MagicMock()
        graph_ctx.additional_data = {"key": "value"}

        _merge_graph_metadata_into_entry(merged_entry, graph_ctx)

        assert merged_entry.entry.context.metadata == {"key": "value"}

    def test_merges_without_overwriting(self):
        """Should merge metadata without overwriting existing keys."""
        entry_response = AuditEntryResponse(
            id="test-id",
            action="SPEAK",
            actor="user",
            timestamp=datetime.now(timezone.utc),
            context=AuditContext(metadata={"existing": "data"}),
        )
        merged_entry = _MergedAuditEntry(entry=entry_response, sources=["sqlite"])

        graph_ctx = MagicMock()
        graph_ctx.additional_data = {"existing": "new_value", "new_key": "new_data"}

        _merge_graph_metadata_into_entry(merged_entry, graph_ctx)

        assert merged_entry.entry.context.metadata["existing"] == "data"  # Not overwritten
        assert merged_entry.entry.context.metadata["new_key"] == "new_data"  # Added

    def test_handles_no_additional_data(self):
        """Should handle context without additional_data."""
        entry_response = AuditEntryResponse(
            id="test-id",
            action="SPEAK",
            actor="user",
            timestamp=datetime.now(timezone.utc),
            context=AuditContext(metadata=None),
        )
        merged_entry = _MergedAuditEntry(entry=entry_response, sources=["sqlite"])

        graph_ctx = MagicMock()
        graph_ctx.additional_data = None

        _merge_graph_metadata_into_entry(merged_entry, graph_ctx)

        assert merged_entry.entry.context.metadata == {}


class TestFindSqliteEntryForDedupKey:
    """Tests for _find_sqlite_entry_for_dedup_key function."""

    def test_finds_matching_entry(self):
        """Should find entry with matching dedup key."""
        timestamp = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
        entry_response = AuditEntryResponse(
            id="test-id",
            action="SPEAK",
            actor="user",
            timestamp=timestamp,
            context=AuditContext(),
        )
        merged_entry = _MergedAuditEntry(entry=entry_response, sources=["sqlite"])
        merged = {"test-id": merged_entry}

        result = _find_sqlite_entry_for_dedup_key(merged, "2026-03-25T12:00:00+00:00_SPEAK")

        assert result is merged_entry

    def test_returns_none_for_no_match(self):
        """Should return None when no matching entry exists."""
        timestamp = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
        entry_response = AuditEntryResponse(
            id="test-id",
            action="SPEAK",
            actor="user",
            timestamp=timestamp,
            context=AuditContext(),
        )
        merged_entry = _MergedAuditEntry(entry=entry_response, sources=["sqlite"])
        merged = {"test-id": merged_entry}

        result = _find_sqlite_entry_for_dedup_key(merged, "2026-03-25T13:00:00+00:00_TOOL")

        assert result is None

    def test_returns_none_for_empty_merged(self):
        """Should return None for empty merged dict."""
        result = _find_sqlite_entry_for_dedup_key({}, "any_key")
        assert result is None


class TestHandleDuplicateGraphEntry:
    """Tests for _handle_duplicate_graph_entry function."""

    def test_does_nothing_without_metadata(self):
        """Should do nothing when has_metadata is False."""
        merged: Dict[str, _MergedAuditEntry] = {}
        entry = MagicMock(spec=AuditEntry)
        logger = MagicMock()

        _handle_duplicate_graph_entry(merged, entry, "dedup_key", False, logger)

        logger.warning.assert_not_called()

    def test_merges_metadata_when_match_found(self):
        """Should merge metadata when matching SQLite entry exists."""
        timestamp = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
        entry_response = AuditEntryResponse(
            id="test-id",
            action="SPEAK",
            actor="user",
            timestamp=timestamp,
            context=AuditContext(metadata=None),
        )
        merged_entry = _MergedAuditEntry(entry=entry_response, sources=["sqlite"])
        merged = {"test-id": merged_entry}

        entry = MagicMock(spec=AuditEntry)
        entry.context = MagicMock()
        entry.context.additional_data = {"graph_key": "graph_value"}

        logger = MagicMock()

        _handle_duplicate_graph_entry(merged, entry, "2026-03-25T12:00:00+00:00_SPEAK", True, logger)

        assert "graph" in merged_entry.sources
        assert merged_entry.entry.context.metadata["graph_key"] == "graph_value"

    def test_logs_warning_when_no_match_found(self):
        """Should log warning when no matching SQLite entry found."""
        merged: Dict[str, _MergedAuditEntry] = {}
        entry = MagicMock(spec=AuditEntry)
        entry.context = MagicMock()
        entry.context.additional_data = {"key": "value"}

        logger = MagicMock()

        _handle_duplicate_graph_entry(merged, entry, "nonexistent_key", True, logger)

        logger.warning.assert_called_once()


class TestAddNewGraphEntry:
    """Tests for _add_new_graph_entry function."""

    def test_adds_new_entry_to_merged(self):
        """Should add new entry when entry_id not in merged."""
        merged: Dict[str, _MergedAuditEntry] = {}
        seen_timestamps: set[str] = set()

        entry = MagicMock(spec=AuditEntry)
        entry.action = "SPEAK"
        entry.actor = "user"
        entry.timestamp = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
        entry.signature = None
        entry.hash_chain = None
        entry.context = MagicMock()
        entry.context.model_dump = MagicMock(return_value={})

        logger = MagicMock()

        _add_new_graph_entry(merged, entry, "new-entry-id", "dedup_key", seen_timestamps, logger)

        assert "new-entry-id" in merged
        assert "graph" in merged["new-entry-id"].sources
        assert "dedup_key" in seen_timestamps

    def test_appends_source_for_existing_entry(self):
        """Should append 'graph' source when entry_id already exists."""
        timestamp = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
        entry_response = AuditEntryResponse(
            id="existing-id",
            action="SPEAK",
            actor="user",
            timestamp=timestamp,
            context=AuditContext(),
        )
        existing_entry = _MergedAuditEntry(entry=entry_response, sources=["sqlite"])
        merged = {"existing-id": existing_entry}
        seen_timestamps: set[str] = set()

        entry = MagicMock(spec=AuditEntry)
        logger = MagicMock()

        _add_new_graph_entry(merged, entry, "existing-id", "dedup_key", seen_timestamps, logger)

        assert "sqlite" in merged["existing-id"].sources
        assert "graph" in merged["existing-id"].sources


class TestAddNewSqliteEntry:
    """Tests for _add_new_sqlite_entry function."""

    def test_adds_new_entry_with_payload(self):
        """Should add new SQLite entry with parsed payload."""
        merged: Dict[str, _MergedAuditEntry] = {}
        sqlite_entry = {
            "event_timestamp": "2026-03-25T12:00:00+00:00",
            "originator_id": "user-123",
            "event_type": "TOOL",
            "event_id": "evt-456",
            "event_payload": json.dumps({
                "action_type": "tool_call",
                "parameters": json.dumps({"tool_name": "calculator"}),
            }),
            "signature": "sig-123",
            "previous_hash": "hash-123",
        }
        entry_info = {
            "event_timestamp": "2026-03-25T12:00:00+00:00",
            "originator_id": "user-123",
            "event_type": "TOOL",
            "entry_id": "evt-456",
        }

        _add_new_sqlite_entry(merged, sqlite_entry, entry_info)

        assert "evt-456" in merged
        assert merged["evt-456"].entry.action == "TOOL"
        assert merged["evt-456"].entry.actor == "user-123"
        assert "sqlite" in merged["evt-456"].sources
        assert merged["evt-456"].entry.context.metadata["tool_name"] == "calculator"

    def test_adds_new_entry_without_payload(self):
        """Should add new SQLite entry without payload."""
        merged: Dict[str, _MergedAuditEntry] = {}
        sqlite_entry = {
            "event_timestamp": "2026-03-25T12:00:00+00:00",
            "originator_id": "user-123",
            "event_type": "SPEAK",
        }
        entry_info = {
            "event_timestamp": "2026-03-25T12:00:00+00:00",
            "originator_id": "user-123",
            "event_type": "SPEAK",
            "entry_id": "audit_2026-03-25T12:00:00+00:00_user-123",
        }

        _add_new_sqlite_entry(merged, sqlite_entry, entry_info)

        assert "audit_2026-03-25T12:00:00+00:00_user-123" in merged
        assert merged["audit_2026-03-25T12:00:00+00:00_user-123"].entry.action == "SPEAK"

    def test_infers_outcome_from_event_type(self):
        """Should infer outcome from event type."""
        merged: Dict[str, _MergedAuditEntry] = {}
        sqlite_entry = {
            "event_timestamp": "2026-03-25T12:00:00+00:00",
            "originator_id": "user-123",
            "event_type": "action_failed",
        }
        entry_info = {
            "event_timestamp": "2026-03-25T12:00:00+00:00",
            "originator_id": "user-123",
            "event_type": "action_failed",
            "entry_id": "evt-fail",
        }

        _add_new_sqlite_entry(merged, sqlite_entry, entry_info)

        assert merged["evt-fail"].entry.context.outcome == "failure"
