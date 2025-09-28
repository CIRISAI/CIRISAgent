"""
Unit tests for data converter helper functions.

These tests specifically target the helper functions extracted to reduce complexity
and increase testability of the data conversion logic.
"""

import pytest
from datetime import datetime

from ciris_engine.logic.services.graph.tsdb_consolidation.data_converter import (
    safe_dict_get,
    ensure_dict,
    safe_str_dict,
    build_request_data_from_raw,
    build_response_data_from_raw,
    build_interaction_context_from_raw,
)


class TestSafeDictGet:
    """Test safe_dict_get helper function."""

    def test_with_dict(self):
        data = {"key1": "value1", "key2": 42}
        assert safe_dict_get(data, "key1") == "value1"
        assert safe_dict_get(data, "key2") == 42
        assert safe_dict_get(data, "missing") is None
        assert safe_dict_get(data, "missing", "default") == "default"

    def test_with_non_dict_types(self):
        assert safe_dict_get("string", "key") is None
        assert safe_dict_get(123, "key") is None
        assert safe_dict_get([1, 2, 3], "key") is None
        assert safe_dict_get(None, "key") is None

    def test_with_default_value(self):
        assert safe_dict_get("string", "key", "fallback") == "fallback"
        assert safe_dict_get(None, "key", "default") == "default"


class TestEnsureDict:
    """Test ensure_dict helper function."""

    def test_with_dict(self):
        data = {"key": "value"}
        result = ensure_dict(data)
        assert result == {"key": "value"}
        assert result is data  # Should return same object

    def test_with_non_dict_types(self):
        assert ensure_dict("string") == {}
        assert ensure_dict(123) == {}
        assert ensure_dict([1, 2, 3]) == {}
        assert ensure_dict(None) == {}

    def test_with_empty_dict(self):
        assert ensure_dict({}) == {}


class TestSafeStrDict:
    """Test safe_str_dict helper function."""

    def test_with_dict(self):
        data = {"key1": "value1", "key2": 42, "key3": True, "key4": None}
        result = safe_str_dict(data)
        expected = {"key1": "value1", "key2": "42", "key3": "True", "key4": "None"}
        assert result == expected

    def test_with_non_dict_types(self):
        assert safe_str_dict("string") == {}
        assert safe_str_dict(123) == {}
        assert safe_str_dict([1, 2, 3]) == {}
        assert safe_str_dict(None) == {}

    def test_with_empty_dict(self):
        assert safe_str_dict({}) == {}

    def test_with_complex_values(self):
        data = {"list": [1, 2, 3], "dict": {"nested": "value"}}
        result = safe_str_dict(data)
        assert result["list"] == "[1, 2, 3]"
        assert "nested" in result["dict"]


class TestBuildRequestDataFromRaw:
    """Test build_request_data_from_raw helper function."""

    def test_with_valid_request_data(self):
        raw_request = {
            "channel_id": "channel123",
            "author_id": "user456",
            "parameters": {
                "author_name": "TestUser",
                "content": "Hello world",
                "extra_param": "value"
            },
            "headers": {"Authorization": "Bearer token"},
            "metadata": {"source": "test"}
        }

        result = build_request_data_from_raw(raw_request)
        assert result is not None
        assert result.channel_id == "channel123"
        assert result.author_id == "user456"
        assert result.author_name == "TestUser"
        assert result.content == "Hello world"
        assert result.parameters["extra_param"] == "value"
        assert result.headers["Authorization"] == "Bearer token"
        assert result.metadata["source"] == "test"

    def test_with_parameters_override(self):
        """Test that parameters values override top-level values."""
        raw_request = {
            "author_id": "top_level_user",
            "parameters": {
                "author_id": "param_user",  # Should override top-level
                "content": "From parameters"
            }
        }

        result = build_request_data_from_raw(raw_request)
        assert result.author_id == "param_user"
        assert result.content == "From parameters"

    def test_with_invalid_parameters(self):
        """Test with non-dict parameters."""
        raw_request = {
            "channel_id": "channel123",
            "parameters": "invalid_string"  # Not a dict
        }

        result = build_request_data_from_raw(raw_request)
        assert result is not None
        assert result.channel_id == "channel123"
        assert result.parameters == {}  # Should be empty dict

    def test_with_non_dict_input(self):
        assert build_request_data_from_raw("string") is None
        assert build_request_data_from_raw(123) is None
        assert build_request_data_from_raw(None) is None
        assert build_request_data_from_raw([]) is None

    def test_with_missing_fields(self):
        """Test with minimal data."""
        raw_request = {"channel_id": "channel123"}

        result = build_request_data_from_raw(raw_request)
        assert result is not None
        assert result.channel_id == "channel123"
        assert result.author_id is None
        assert result.author_name is None
        assert result.content is None
        assert result.parameters == {}
        assert result.headers == {}
        assert result.metadata == {}


class TestBuildResponseDataFromRaw:
    """Test build_response_data_from_raw helper function."""

    def test_with_valid_response_data(self):
        raw_response = {
            "execution_time_ms": 150.5,
            "success": True,
            "error": None,
            "error_type": None,
            "result": "Operation completed",
            "resource_usage": {"memory": 1024, "cpu": 0.5},
            "metadata": {"version": "1.0"}
        }

        result = build_response_data_from_raw(raw_response)
        assert result is not None
        assert result.execution_time_ms == 150.5
        assert result.success is True
        assert result.error is None
        assert result.result == "Operation completed"
        assert result.resource_usage["memory"] == 1024
        assert result.metadata["version"] == "1.0"

    def test_with_non_dict_nested_fields(self):
        """Test with invalid nested dictionary fields."""
        raw_response = {
            "success": True,
            "resource_usage": "invalid_string",  # Not a dict
            "metadata": 123  # Not a dict
        }

        result = build_response_data_from_raw(raw_response)
        assert result is not None
        assert result.success is True
        assert result.resource_usage == {}  # Should be empty dict
        assert result.metadata == {}  # Should be empty dict

    def test_with_non_dict_input(self):
        assert build_response_data_from_raw("string") is None
        assert build_response_data_from_raw(123) is None
        assert build_response_data_from_raw(None) is None
        assert build_response_data_from_raw([]) is None


class TestBuildInteractionContextFromRaw:
    """Test build_interaction_context_from_raw helper function."""

    def test_with_valid_context_data(self):
        context_data = {
            "trace_id": "trace123",
            "span_id": "span456",
            "parent_span_id": "parent789",
            "user_id": "user123",
            "session_id": "session456",
            "environment": "production",
            "additional_data": {"custom": "value", "flag": True}
        }

        result = build_interaction_context_from_raw(context_data)
        assert result is not None
        assert result.trace_id == "trace123"
        assert result.span_id == "span456"
        assert result.parent_span_id == "parent789"
        assert result.user_id == "user123"
        assert result.session_id == "session456"
        assert result.environment == "production"
        assert result.additional_data["custom"] == "value"

    def test_with_invalid_additional_data(self):
        """Test with non-dict additional_data."""
        context_data = {
            "trace_id": "trace123",
            "additional_data": "invalid_string"  # Not a dict
        }

        result = build_interaction_context_from_raw(context_data)
        assert result is not None
        assert result.trace_id == "trace123"
        assert result.additional_data == {}  # Should be empty dict

    def test_with_non_dict_input(self):
        assert build_interaction_context_from_raw("string") is None
        assert build_interaction_context_from_raw(123) is None
        assert build_interaction_context_from_raw(None) is None
        assert build_interaction_context_from_raw([]) is None

    def test_with_minimal_data(self):
        """Test with minimal context data."""
        context_data = {"trace_id": "trace123"}

        result = build_interaction_context_from_raw(context_data)
        assert result is not None
        assert result.trace_id == "trace123"
        assert result.span_id is None
        assert result.additional_data == {}


class TestHelperFunctionIntegration:
    """Integration tests showing how helper functions work together."""

    def test_full_conversion_workflow(self):
        """Test a complete workflow using all helper functions."""
        # Simulate raw data that might come from database
        raw_request = {
            "channel_id": "test-channel",
            "parameters": {
                "author_name": "TestUser",
                "content": "Test message",
                "extra": 42
            },
            "headers": {"type": "json"},
            "metadata": {"version": "1.0"}
        }

        raw_response = {
            "execution_time_ms": 100.0,
            "success": True,
            "result": "processed",
            "resource_usage": {"memory": 512}
        }

        context_data = {
            "trace_id": "trace-123",
            "user_id": "user-456",
            "additional_data": {"session": "active"}
        }

        # Use helper functions
        request_data = build_request_data_from_raw(raw_request)
        response_data = build_response_data_from_raw(raw_response)
        context = build_interaction_context_from_raw(context_data)

        # Verify results
        assert request_data.channel_id == "test-channel"
        assert request_data.author_name == "TestUser"
        assert request_data.parameters["extra"] == "42"  # Converted to string

        assert response_data.execution_time_ms == 100.0
        assert response_data.success is True
        assert response_data.resource_usage["memory"] == 512

        assert context.trace_id == "trace-123"
        assert context.user_id == "user-456"
        assert context.additional_data["session"] == "active"

    def test_error_resilience(self):
        """Test that helper functions handle errors gracefully."""
        # Test with various types of invalid data
        invalid_inputs = [
            "string",
            123,
            [1, 2, 3],
            None,
            {"invalid": "structure"}
        ]

        for invalid_input in invalid_inputs:
            # None of these should raise exceptions
            request_result = build_request_data_from_raw(invalid_input)
            response_result = build_response_data_from_raw(invalid_input)
            context_result = build_interaction_context_from_raw(invalid_input)

            # Most should return None for non-dict inputs
            if not isinstance(invalid_input, dict):
                assert request_result is None
                assert response_result is None
                assert context_result is None