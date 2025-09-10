"""Unit tests for telemetry helper functions.

Tests for functions extracted during complexity refactoring to improve maintainability
and test coverage of individual components.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock
import pytest

from ciris_engine.logic.adapters.api.routes.telemetry import (
    _extract_basic_trace_fields,
    _extract_request_data_fields,
    _extract_response_data_fields,
    _extract_span_attributes,
    _build_trace_data_from_correlation,
)


class TestTraceDataExtractionHelpers:
    """Test suite for trace data extraction helper functions."""

    def test_extract_basic_trace_fields_with_trace_context(self):
        """Test basic trace fields extraction when trace context exists."""
        # Arrange
        trace_context = Mock()
        trace_context.trace_id = "trace-123"
        trace_context.span_id = "span-456"
        trace_context.parent_span_id = "parent-789"
        
        status = Mock()
        status.value = "completed"
        
        timestamp = datetime.now(timezone.utc)
        correlation = Mock()
        correlation.trace_context = trace_context
        correlation.correlation_id = "corr-123"
        correlation.timestamp = timestamp
        correlation.action_type = "test_action"
        correlation.service_type = "test_service"
        correlation.handler_name = "test_handler"
        correlation.status = status

        # Act
        result = _extract_basic_trace_fields(correlation)

        # Assert
        assert result["trace_id"] == "trace-123"
        assert result["span_id"] == "span-456"
        assert result["parent_span_id"] == "parent-789"
        assert result["timestamp"] == timestamp.isoformat()
        assert result["operation"] == "test_action"
        assert result["service"] == "test_service"
        assert result["handler"] == "test_handler"
        assert result["status"] == "completed"

    def test_extract_basic_trace_fields_without_trace_context(self):
        """Test basic trace fields extraction when trace context is None."""
        # Arrange
        correlation = Mock()
        correlation.trace_context = None
        correlation.correlation_id = "corr-456"
        correlation.timestamp = None
        correlation.action_type = None
        correlation.service_type = "fallback_service"
        correlation.handler_name = "fallback_handler"
        correlation.status = "status_string"

        # Act
        result = _extract_basic_trace_fields(correlation)

        # Assert
        assert result["trace_id"] == "corr-456"
        assert len(result["span_id"]) > 0  # Should be a UUID
        assert result["parent_span_id"] is None
        assert "T" in result["timestamp"]  # Should be current time ISO format
        assert result["operation"] == "unknown"
        assert result["service"] == "fallback_service"
        assert result["handler"] == "fallback_handler"
        assert result["status"] == "status_string"

    def test_extract_basic_trace_fields_status_without_value_attr(self):
        """Test status extraction when status object doesn't have value attribute."""
        # Arrange
        correlation = Mock()
        correlation.trace_context = None
        correlation.correlation_id = "corr-789"
        correlation.timestamp = datetime.now(timezone.utc)
        correlation.action_type = "action"
        correlation.service_type = "service"
        correlation.handler_name = "handler"
        correlation.status = "direct_status"  # No .value attribute

        # Act
        result = _extract_basic_trace_fields(correlation)

        # Assert
        assert result["status"] == "direct_status"

    def test_extract_request_data_fields_with_valid_data(self):
        """Test request data extraction when request_data exists with fields."""
        # Arrange
        request_data = Mock()
        request_data.task_id = "task-123"
        request_data.thought_id = "thought-456"
        
        correlation = Mock()
        correlation.request_data = request_data
        
        trace_data = {}

        # Act
        _extract_request_data_fields(correlation, trace_data)

        # Assert
        assert trace_data["task_id"] == "task-123"
        assert trace_data["thought_id"] == "thought-456"

    def test_extract_request_data_fields_missing_attributes(self):
        """Test request data extraction when attributes are missing."""
        # Arrange
        request_data = Mock()
        # task_id and thought_id don't exist on request_data
        del request_data.task_id
        del request_data.thought_id
        
        correlation = Mock()
        correlation.request_data = request_data
        
        trace_data = {}

        # Act
        _extract_request_data_fields(correlation, trace_data)

        # Assert
        assert "task_id" not in trace_data
        assert "thought_id" not in trace_data

    def test_extract_request_data_fields_none_values(self):
        """Test request data extraction when fields exist but are None."""
        # Arrange
        request_data = Mock()
        request_data.task_id = None
        request_data.thought_id = None
        
        correlation = Mock()
        correlation.request_data = request_data
        
        trace_data = {}

        # Act
        _extract_request_data_fields(correlation, trace_data)

        # Assert
        assert "task_id" not in trace_data  # None values should not be added
        assert "thought_id" not in trace_data

    def test_extract_request_data_fields_no_request_data(self):
        """Test request data extraction when request_data is None."""
        # Arrange
        correlation = Mock()
        correlation.request_data = None
        
        trace_data = {}

        # Act
        _extract_request_data_fields(correlation, trace_data)

        # Assert
        assert len(trace_data) == 0

    def test_extract_response_data_fields_with_valid_data(self):
        """Test response data extraction when response_data exists with fields."""
        # Arrange
        response_data = Mock()
        response_data.execution_time_ms = 150.5
        response_data.success = True
        response_data.error_message = "test error"
        
        correlation = Mock()
        correlation.response_data = response_data
        
        trace_data = {}

        # Act
        _extract_response_data_fields(correlation, trace_data)

        # Assert
        assert trace_data["duration_ms"] == 150.5
        assert trace_data["success"] is True
        assert trace_data["error"] == "test error"

    def test_extract_response_data_fields_missing_attributes(self):
        """Test response data extraction when attributes are missing."""
        # Arrange
        response_data = Mock()
        # Remove attributes to test hasattr checks
        del response_data.execution_time_ms
        del response_data.success
        del response_data.error_message
        
        correlation = Mock()
        correlation.response_data = response_data
        
        trace_data = {}

        # Act
        _extract_response_data_fields(correlation, trace_data)

        # Assert
        assert "duration_ms" not in trace_data
        assert "success" not in trace_data
        assert "error" not in trace_data

    def test_extract_response_data_fields_no_response_data(self):
        """Test response data extraction when response_data is None."""
        # Arrange
        correlation = Mock()
        correlation.response_data = None
        
        trace_data = {}

        # Act
        _extract_response_data_fields(correlation, trace_data)

        # Assert
        assert len(trace_data) == 0

    def test_extract_span_attributes_with_valid_context(self):
        """Test span attributes extraction when trace_context exists with attributes."""
        # Arrange
        trace_context = Mock()
        trace_context.span_name = "custom_span"
        trace_context.span_kind = "server"
        
        correlation = Mock()
        correlation.trace_context = trace_context
        correlation.action_type = "fallback_action"
        
        trace_data = {}

        # Act
        _extract_span_attributes(correlation, trace_data)

        # Assert
        assert trace_data["span_name"] == "custom_span"
        assert trace_data["span_kind"] == "server"

    def test_extract_span_attributes_missing_attributes(self):
        """Test span attributes extraction when attributes are missing."""
        # Arrange
        trace_context = Mock()
        del trace_context.span_name
        del trace_context.span_kind
        
        correlation = Mock()
        correlation.trace_context = trace_context
        correlation.action_type = "fallback_action"
        
        trace_data = {}

        # Act
        _extract_span_attributes(correlation, trace_data)

        # Assert
        assert trace_data["span_name"] == "fallback_action"  # Should use action_type as fallback
        assert trace_data["span_kind"] == "internal"  # Should use default

    def test_extract_span_attributes_no_trace_context(self):
        """Test span attributes extraction when trace_context is None."""
        # Arrange
        correlation = Mock()
        correlation.trace_context = None
        
        trace_data = {}

        # Act
        _extract_span_attributes(correlation, trace_data)

        # Assert
        assert len(trace_data) == 0

    def test_build_trace_data_from_correlation_complete_integration(self):
        """Test complete trace data building with all components."""
        # Arrange
        trace_context = Mock()
        trace_context.trace_id = "integration-trace"
        trace_context.span_id = "integration-span"
        trace_context.parent_span_id = None
        trace_context.span_name = "integration_span"
        trace_context.span_kind = "client"
        
        request_data = Mock()
        request_data.task_id = "integration-task"
        request_data.thought_id = "integration-thought"
        
        response_data = Mock()
        response_data.execution_time_ms = 250.0
        response_data.success = False
        response_data.error_message = "integration error"
        
        status = Mock()
        status.value = "failed"
        
        timestamp = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        correlation = Mock()
        correlation.trace_context = trace_context
        correlation.correlation_id = "integration-corr"
        correlation.timestamp = timestamp
        correlation.action_type = "integration_action"
        correlation.service_type = "integration_service"
        correlation.handler_name = "integration_handler"
        correlation.status = status
        correlation.request_data = request_data
        correlation.response_data = response_data

        # Act
        result = _build_trace_data_from_correlation(correlation)

        # Assert - Basic fields
        assert result["trace_id"] == "integration-trace"
        assert result["span_id"] == "integration-span"
        assert result["parent_span_id"] is None
        assert result["timestamp"] == "2023-01-01T12:00:00+00:00"
        assert result["operation"] == "integration_action"
        assert result["service"] == "integration_service"
        assert result["handler"] == "integration_handler"
        assert result["status"] == "failed"
        
        # Assert - Request data
        assert result["task_id"] == "integration-task"
        assert result["thought_id"] == "integration-thought"
        
        # Assert - Response data
        assert result["duration_ms"] == 250.0
        assert result["success"] is False
        assert result["error"] == "integration error"
        
        # Assert - Span attributes
        assert result["span_name"] == "integration_span"
        assert result["span_kind"] == "client"

    def test_build_trace_data_from_correlation_minimal_data(self):
        """Test trace data building with minimal required data."""
        # Arrange
        correlation = Mock()
        correlation.trace_context = None
        correlation.correlation_id = "minimal-corr"
        correlation.timestamp = None
        correlation.action_type = None
        correlation.service_type = "minimal_service"
        correlation.handler_name = "minimal_handler"
        correlation.status = "minimal_status"
        correlation.request_data = None
        correlation.response_data = None

        # Act
        result = _build_trace_data_from_correlation(correlation)

        # Assert - Should handle all None/missing values gracefully
        assert result["trace_id"] == "minimal-corr"
        assert len(result["span_id"]) > 0  # Should be generated UUID
        assert result["parent_span_id"] is None
        assert "T" in result["timestamp"]  # Should be current time
        assert result["operation"] == "unknown"
        assert result["service"] == "minimal_service"
        assert result["handler"] == "minimal_handler"
        assert result["status"] == "minimal_status"
        
        # Should not have request/response/span data
        assert "task_id" not in result
        assert "thought_id" not in result
        assert "duration_ms" not in result
        assert "success" not in result
        assert "error" not in result
        assert "span_name" not in result
        assert "span_kind" not in result