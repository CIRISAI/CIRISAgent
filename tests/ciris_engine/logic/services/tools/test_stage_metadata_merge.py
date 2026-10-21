"""
Tests for _merge_stage_metadata fix (#776).

The guard condition was short-circuiting on the first update when
current_metadata had no existing "stages" key.
"""

import time
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tool_service():
    """Create a minimal CoreToolService for testing the merge method."""
    from ciris_engine.logic.services.tools.core_tool_service.service import CoreToolService

    svc = CoreToolService.__new__(CoreToolService)
    return svc


class TestMergeStageMetadata:
    """Tests for _merge_stage_metadata."""

    def test_first_update_applies_stages(self, tool_service):
        """When current_metadata has no stages, the update's stages should be applied."""
        current = {}
        updates = {
            "stages": {
                "identity_resolution": {"status": "completed", "completed_at": "2026-01-01"},
                "data_collection": {"status": "pending"},
            }
        }
        result = tool_service._merge_stage_metadata(current, updates, time.time())
        assert "stages" in result
        assert result["stages"]["identity_resolution"]["status"] == "completed"
        assert result["stages"]["data_collection"]["status"] == "pending"

    def test_deep_merge_preserves_existing_stages(self, tool_service):
        """When both have stages, existing stage data should be preserved and updated."""
        current = {
            "stages": {
                "identity_resolution": {"status": "completed", "completed_at": "2026-01-01"},
                "data_collection": {"status": "pending"},
            }
        }
        updates = {
            "stages": {
                "data_collection": {"status": "completed", "completed_at": "2026-01-02"},
            }
        }
        result = tool_service._merge_stage_metadata(current, updates, time.time())
        assert result["stages"]["identity_resolution"]["status"] == "completed"
        assert result["stages"]["data_collection"]["status"] == "completed"
        assert result["stages"]["data_collection"]["completed_at"] == "2026-01-02"

    def test_no_stages_in_update_returns_shallow_merge(self, tool_service):
        """When update has no stages key, should do a shallow merge only."""
        current = {"existing_key": "value", "stages": {"s1": {"status": "done"}}}
        updates = {"new_key": "new_value"}
        result = tool_service._merge_stage_metadata(current, updates, time.time())
        assert result["existing_key"] == "value"
        assert result["new_key"] == "new_value"
        assert result["stages"]["s1"]["status"] == "done"

    def test_empty_current_with_stages_update(self, tool_service):
        """Empty current + stages in update should produce stages (regression test for #776)."""
        current = {}
        updates = {"stages": {"step1": {"status": "in_progress"}}}
        result = tool_service._merge_stage_metadata(current, updates, time.time())
        assert result["stages"]["step1"]["status"] == "in_progress"

    def test_both_empty(self, tool_service):
        """Empty current + empty update should return empty dict."""
        result = tool_service._merge_stage_metadata({}, {}, time.time())
        assert result == {}

    def test_non_dict_stages_in_update_raises(self, tool_service):
        """Non-dict stages value raises — stages must be a dict."""
        current = {}
        updates = {"stages": "invalid"}
        with pytest.raises(AttributeError):
            tool_service._merge_stage_metadata(current, updates, time.time())
