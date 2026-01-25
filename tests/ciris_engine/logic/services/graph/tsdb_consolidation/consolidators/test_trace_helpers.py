"""
Tests for trace consolidation helper functions.

Ensures 80%+ coverage for all trace consolidation logic.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.consolidators.trace import (
    TraceConsolidator,
    _calculate_latency_stats,
    _calculate_percentiles,
    _calculate_trace_depth_metrics,
    _finalize_task_summaries,
    _get_tag_bool,
    _get_tag_value,
    _initialize_task_summary,
    _process_dma_span,
    _process_guardrail_span,
    _process_handler_for_thought,
    _process_span_errors,
    _process_span_latency,
    _update_task_status,
    _update_task_trace_id,
)
from ciris_engine.schemas.services.graph.consolidation import SpanTags, TraceSpanData
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


class MockTags:
    """Mock object for SpanTags to test _get_tag_value and _get_tag_bool."""

    def __init__(self, additional_tags: Optional[Dict[str, Any]] = None):
        self.additional_tags = additional_tags or {}


class TestGetTagValue:
    """Tests for _get_tag_value function."""

    def test_returns_default_when_tags_is_none(self):
        """Should return default when tags is None."""
        result = _get_tag_value(None, "key")
        assert result == "unknown"

    def test_returns_default_when_tags_has_no_additional_tags(self):
        """Should return default when tags lacks additional_tags attribute."""
        tags = object()  # Object without additional_tags
        result = _get_tag_value(tags, "key")
        assert result == "unknown"

    def test_returns_value_when_present(self):
        """Should return value when key exists in additional_tags."""
        tags = MockTags({"component_type": "handler"})
        result = _get_tag_value(tags, "component_type")
        assert result == "handler"

    def test_returns_default_when_key_missing(self):
        """Should return default when key is not in additional_tags."""
        tags = MockTags({"other": "value"})
        result = _get_tag_value(tags, "missing_key")
        assert result == "unknown"

    def test_returns_custom_default(self):
        """Should return custom default when provided."""
        tags = MockTags({})
        result = _get_tag_value(tags, "missing_key", "custom_default")
        assert result == "custom_default"

    def test_converts_non_string_values(self):
        """Should convert non-string values to strings."""
        tags = MockTags({"number": 42, "float": 3.14})
        assert _get_tag_value(tags, "number") == "42"
        assert _get_tag_value(tags, "float") == "3.14"

    def test_returns_default_for_none_value(self):
        """Should return default when value is None."""
        tags = MockTags({"null_value": None})
        result = _get_tag_value(tags, "null_value")
        assert result == "unknown"

    def test_handles_empty_string_value(self):
        """Should return default for empty string values."""
        tags = MockTags({"empty": ""})
        result = _get_tag_value(tags, "empty")
        assert result == "unknown"


class TestGetTagBool:
    """Tests for _get_tag_bool function."""

    def test_returns_false_when_tags_is_none(self):
        """Should return False when tags is None."""
        result = _get_tag_bool(None, "key")
        assert result is False

    def test_returns_false_when_tags_has_no_additional_tags(self):
        """Should return False when tags lacks additional_tags."""
        tags = object()
        result = _get_tag_bool(tags, "key")
        assert result is False

    def test_returns_true_when_value_matches_true_value(self):
        """Should return True when value equals true_value."""
        tags = MockTags({"violation": "true"})
        result = _get_tag_bool(tags, "violation")
        assert result is True

    def test_returns_false_when_value_does_not_match(self):
        """Should return False when value does not equal true_value."""
        tags = MockTags({"violation": "false"})
        result = _get_tag_bool(tags, "violation")
        assert result is False

    def test_supports_custom_true_value(self):
        """Should support custom true_value parameter."""
        tags = MockTags({"status": "active"})
        result = _get_tag_bool(tags, "status", true_value="active")
        assert result is True

    def test_returns_false_for_missing_key(self):
        """Should return False when key is missing."""
        tags = MockTags({})
        result = _get_tag_bool(tags, "missing_key")
        assert result is False


class TestInitializeTaskSummary:
    """Tests for _initialize_task_summary function."""

    def test_creates_summary_with_task_id(self):
        """Should create summary with task_id."""
        summary = _initialize_task_summary("task-123", None)
        assert summary["task_id"] == "task-123"

    def test_creates_summary_with_default_status(self):
        """Should set status to 'processing'."""
        summary = _initialize_task_summary("task-123", None)
        assert summary["status"] == "processing"

    def test_creates_empty_thoughts_list(self):
        """Should initialize empty thoughts list."""
        summary = _initialize_task_summary("task-123", None)
        assert summary["thoughts"] == []

    def test_creates_empty_handlers_selected_list(self):
        """Should initialize empty handlers_selected list."""
        summary = _initialize_task_summary("task-123", None)
        assert summary["handlers_selected"] == []

    def test_creates_empty_trace_ids_list(self):
        """Should initialize empty trace_ids list (JSON-compatible)."""
        summary = _initialize_task_summary("task-123", None)
        assert summary["trace_ids"] == []

    def test_sets_timestamps_from_parameter(self):
        """Should set start_time and end_time as ISO format strings."""
        timestamp = datetime(2023, 10, 1, 12, 0, tzinfo=timezone.utc)
        summary = _initialize_task_summary("task-123", timestamp)
        assert summary["start_time"] == timestamp.isoformat()
        assert summary["end_time"] == timestamp.isoformat()

    def test_handles_none_timestamp(self):
        """Should handle None timestamp."""
        summary = _initialize_task_summary("task-123", None)
        assert summary["start_time"] is None
        assert summary["end_time"] is None


class TestUpdateTaskTraceId:
    """Tests for _update_task_trace_id function."""

    def test_adds_trace_id_to_list(self):
        """Should add trace_id to trace_ids list."""
        task_summaries = {
            "task-123": {
                "trace_ids": [],
                "end_time": None,
            }
        }
        timestamp = datetime(2023, 10, 1, 12, 0, tzinfo=timezone.utc)

        _update_task_trace_id(task_summaries, "task-123", "trace-abc", timestamp)

        assert "trace-abc" in task_summaries["task-123"]["trace_ids"]

    def test_updates_end_time(self):
        """Should update end_time as ISO format string."""
        timestamp = datetime(2023, 10, 1, 12, 0, tzinfo=timezone.utc)
        task_summaries = {
            "task-123": {
                "trace_ids": [],
                "end_time": None,
            }
        }

        _update_task_trace_id(task_summaries, "task-123", "trace-abc", timestamp)

        assert task_summaries["task-123"]["end_time"] == timestamp.isoformat()

    def test_does_nothing_when_task_not_found(self):
        """Should do nothing when task_id not in task_summaries."""
        task_summaries = {}
        _update_task_trace_id(task_summaries, "missing-task", "trace-abc", None)
        assert "missing-task" not in task_summaries

    def test_handles_non_dict_summary(self):
        """Should handle case where summary is not a dict."""
        task_summaries = {"task-123": "not-a-dict"}
        # Should not raise
        _update_task_trace_id(task_summaries, "task-123", "trace-abc", None)

    def test_handles_non_set_trace_ids(self):
        """Should handle case where trace_ids is not a set."""
        task_summaries = {
            "task-123": {
                "trace_ids": "not-a-set",
                "end_time": None,
            }
        }
        # Should not raise, just update end_time
        _update_task_trace_id(task_summaries, "task-123", "trace-abc", None)


class TestProcessHandlerForThought:
    """Tests for _process_handler_for_thought function."""

    def test_increments_handler_actions(self):
        """Should increment handler_actions counter."""
        handler_actions: Dict[str, int] = defaultdict(int)
        task_summaries = {
            "task-123": {
                "handlers_selected": [],
                "thoughts": [],
            }
        }

        _process_handler_for_thought(task_summaries, "task-123", "thought-1", "SPEAK", None, handler_actions)

        assert handler_actions["SPEAK"] == 1

    def test_appends_to_handlers_selected(self):
        """Should append action_type to handlers_selected."""
        handler_actions: Dict[str, int] = defaultdict(int)
        task_summaries = {
            "task-123": {
                "handlers_selected": [],
                "thoughts": [],
            }
        }

        _process_handler_for_thought(task_summaries, "task-123", "thought-1", "SPEAK", None, handler_actions)

        assert "SPEAK" in task_summaries["task-123"]["handlers_selected"]

    def test_appends_thought_info_with_timestamp(self):
        """Should append thought info with ISO timestamp."""
        handler_actions: Dict[str, int] = defaultdict(int)
        timestamp = datetime(2023, 10, 1, 12, 0, tzinfo=timezone.utc)
        task_summaries = {
            "task-123": {
                "handlers_selected": [],
                "thoughts": [],
            }
        }

        _process_handler_for_thought(task_summaries, "task-123", "thought-1", "SPEAK", timestamp, handler_actions)

        thought = task_summaries["task-123"]["thoughts"][0]
        assert thought["thought_id"] == "thought-1"
        assert thought["handler"] == "SPEAK"
        assert thought["timestamp"] == timestamp.isoformat()

    def test_handles_none_timestamp(self):
        """Should handle None timestamp in thought info."""
        handler_actions: Dict[str, int] = defaultdict(int)
        task_summaries = {
            "task-123": {
                "handlers_selected": [],
                "thoughts": [],
            }
        }

        _process_handler_for_thought(task_summaries, "task-123", "thought-1", "SPEAK", None, handler_actions)

        thought = task_summaries["task-123"]["thoughts"][0]
        assert thought["timestamp"] is None

    def test_does_nothing_when_task_not_found(self):
        """Should do nothing when task_id not in task_summaries."""
        handler_actions: Dict[str, int] = defaultdict(int)
        task_summaries = {}

        _process_handler_for_thought(task_summaries, "missing-task", "thought-1", "SPEAK", None, handler_actions)

        # handler_actions still incremented
        assert handler_actions["SPEAK"] == 1


class TestUpdateTaskStatus:
    """Tests for _update_task_status function."""

    def test_increments_tasks_by_status(self):
        """Should increment tasks_by_status counter."""
        tasks_by_status: Dict[str, int] = defaultdict(int)
        task_summaries = {"task-123": {"status": "processing"}}

        _update_task_status(task_summaries, "task-123", "completed", tasks_by_status)

        assert tasks_by_status["completed"] == 1

    def test_updates_task_summary_status(self):
        """Should update status in task summary."""
        tasks_by_status: Dict[str, int] = defaultdict(int)
        task_summaries = {"task-123": {"status": "processing"}}

        _update_task_status(task_summaries, "task-123", "completed", tasks_by_status)

        assert task_summaries["task-123"]["status"] == "completed"

    def test_handles_missing_task(self):
        """Should not raise when task is missing."""
        tasks_by_status: Dict[str, int] = defaultdict(int)
        task_summaries = {}

        _update_task_status(task_summaries, "missing", "completed", tasks_by_status)

        # Counter still incremented
        assert tasks_by_status["completed"] == 1


class TestProcessSpanErrors:
    """Tests for _process_span_errors function."""

    def test_returns_0_when_no_error(self):
        """Should return 0 when span has no error."""
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            error=False,
        )
        component_failures: Dict[str, int] = defaultdict(int)
        errors_by_component: Dict[str, int] = defaultdict(int)

        result = _process_span_errors(span, "handler", component_failures, errors_by_component)

        assert result == 0
        assert component_failures["handler"] == 0
        assert errors_by_component["handler"] == 0

    def test_returns_1_and_increments_counters_when_error(self):
        """Should return 1 and increment counters when span has error."""
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            error=True,
        )
        component_failures: Dict[str, int] = defaultdict(int)
        errors_by_component: Dict[str, int] = defaultdict(int)

        result = _process_span_errors(span, "handler", component_failures, errors_by_component)

        assert result == 1
        assert component_failures["handler"] == 1
        assert errors_by_component["handler"] == 1


class TestProcessSpanLatency:
    """Tests for _process_span_latency function."""

    def test_tracks_latency_ms_when_present(self):
        """Should track latency_ms when provided."""
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            latency_ms=100.5,
        )
        component_latencies: Dict[str, List[float]] = defaultdict(list)

        _process_span_latency(span, "handler", component_latencies)

        assert component_latencies["handler"] == [100.5]

    def test_tracks_duration_ms_when_latency_ms_missing(self):
        """Should fall back to duration_ms when latency_ms is None."""
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            latency_ms=None,
            duration_ms=50.0,
        )
        component_latencies: Dict[str, List[float]] = defaultdict(list)

        _process_span_latency(span, "handler", component_latencies)

        assert component_latencies["handler"] == [50.0]

    def test_ignores_zero_duration_ms(self):
        """Should not track when duration_ms is 0."""
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            latency_ms=None,
            duration_ms=0.0,
        )
        component_latencies: Dict[str, List[float]] = defaultdict(list)

        _process_span_latency(span, "handler", component_latencies)

        assert component_latencies["handler"] == []


class TestProcessGuardrailSpan:
    """Tests for _process_guardrail_span function."""

    def test_increments_violation_counter_when_violation_true(self):
        """Should increment guardrail_violations when violation is true."""
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            tags=SpanTags(additional_tags={"guardrail_type": "content_filter", "violation": "true"}),
        )
        guardrail_violations: Dict[str, int] = defaultdict(int)

        _process_guardrail_span(span, guardrail_violations)

        assert guardrail_violations["content_filter"] == 1

    def test_does_not_increment_when_violation_false(self):
        """Should not increment when violation is not 'true'."""
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            tags=SpanTags(additional_tags={"guardrail_type": "content_filter", "violation": "false"}),
        )
        guardrail_violations: Dict[str, int] = defaultdict(int)

        _process_guardrail_span(span, guardrail_violations)

        assert guardrail_violations["content_filter"] == 0

    def test_handles_missing_tags(self):
        """Should handle span without tags."""
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            tags=None,
        )
        guardrail_violations: Dict[str, int] = defaultdict(int)

        _process_guardrail_span(span, guardrail_violations)

        # Should use "unknown" as default guardrail_type and not increment
        assert guardrail_violations["unknown"] == 0


class TestProcessDmaSpan:
    """Tests for _process_dma_span function."""

    def test_increments_dma_decisions(self):
        """Should increment dma_decisions counter."""
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            tags=SpanTags(additional_tags={"dma_type": "prioritize"}),
        )
        dma_decisions: Dict[str, int] = defaultdict(int)

        _process_dma_span(span, dma_decisions)

        assert dma_decisions["prioritize"] == 1

    def test_uses_unknown_for_missing_dma_type(self):
        """Should use 'unknown' when dma_type is missing."""
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            tags=SpanTags(additional_tags={}),
        )
        dma_decisions: Dict[str, int] = defaultdict(int)

        _process_dma_span(span, dma_decisions)

        assert dma_decisions["unknown"] == 1


class TestCalculateLatencyStats:
    """Tests for _calculate_latency_stats function."""

    def test_calculates_stats_for_single_component(self):
        """Should calculate avg, p50, p95, p99 for a component."""
        component_latencies = {"handler": [10.0, 20.0, 30.0, 40.0, 50.0]}

        result = _calculate_latency_stats(component_latencies)

        assert "handler" in result
        assert result["handler"]["avg"] == 30.0
        assert result["handler"]["p50"] == 30.0

    def test_calculates_stats_for_multiple_components(self):
        """Should calculate stats for multiple components."""
        component_latencies = {
            "handler": [10.0, 20.0, 30.0],
            "guardrail": [5.0, 10.0, 15.0],
        }

        result = _calculate_latency_stats(component_latencies)

        assert "handler" in result
        assert "guardrail" in result
        assert result["handler"]["avg"] == 20.0
        assert result["guardrail"]["avg"] == 10.0

    def test_skips_empty_latency_lists(self):
        """Should skip components with empty latency lists."""
        component_latencies = {
            "handler": [10.0, 20.0],
            "empty": [],
        }

        result = _calculate_latency_stats(component_latencies)

        assert "handler" in result
        assert "empty" not in result

    def test_returns_empty_dict_for_empty_input(self):
        """Should return empty dict when no latencies."""
        result = _calculate_latency_stats({})
        assert result == {}

    def test_handles_single_value(self):
        """Should handle single latency value."""
        component_latencies = {"handler": [100.0]}

        result = _calculate_latency_stats(component_latencies)

        assert result["handler"]["avg"] == 100.0
        assert result["handler"]["p50"] == 100.0
        assert result["handler"]["p95"] == 100.0
        assert result["handler"]["p99"] == 100.0


class TestCalculatePercentiles:
    """Tests for _calculate_percentiles function."""

    def test_returns_zeros_for_empty_list(self):
        """Should return (0, 0, 0, 0) for empty list."""
        result = _calculate_percentiles([])
        assert result == (0.0, 0.0, 0.0, 0.0)

    def test_calculates_percentiles_correctly(self):
        """Should calculate avg, p50, p95, p99 correctly."""
        values = list(range(1, 101))  # 1 to 100

        avg, p50, p95, p99 = _calculate_percentiles(values)

        assert avg == pytest.approx(50.5)
        # p50 is sorted_vals[n // 2] = sorted_vals[50] = 51 (0-indexed list of 1-100)
        assert p50 == 51
        # p95 is sorted_vals[int(n * 0.95)] = sorted_vals[95] = 96
        assert p95 == 96
        # p99 is sorted_vals[int(n * 0.99)] = sorted_vals[99] = 100
        assert p99 == 100

    def test_handles_single_value(self):
        """Should handle single value."""
        avg, p50, p95, p99 = _calculate_percentiles([42.0])

        assert avg == 42.0
        assert p50 == 42.0
        assert p95 == 42.0
        assert p99 == 42.0

    def test_handles_two_values(self):
        """Should handle two values."""
        avg, p50, p95, p99 = _calculate_percentiles([10.0, 20.0])

        assert avg == 15.0
        assert p50 == 20.0  # Index 1 (n // 2)


class TestFinalizeTaskSummaries:
    """Tests for _finalize_task_summaries function."""

    def test_calculates_duration_ms(self):
        """Should calculate duration_ms from start_time and end_time."""
        start = datetime(2023, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 1, 12, 0, 1, tzinfo=timezone.utc)  # 1 second later
        task_summaries = {
            "task-1": {
                "start_time": start,
                "end_time": end,
                "trace_ids": set(),
            }
        }

        result = _finalize_task_summaries(task_summaries)

        assert result == [1000.0]  # 1 second = 1000ms
        assert task_summaries["task-1"]["duration_ms"] == 1000.0

    def test_converts_trace_ids_set_to_list(self):
        """Should convert trace_ids from set to list."""
        start = datetime(2023, 10, 1, 12, 0, tzinfo=timezone.utc)
        task_summaries = {
            "task-1": {
                "start_time": start,
                "end_time": start,
                "trace_ids": {"trace-a", "trace-b"},
            }
        }

        _finalize_task_summaries(task_summaries)

        assert isinstance(task_summaries["task-1"]["trace_ids"], list)
        assert set(task_summaries["task-1"]["trace_ids"]) == {"trace-a", "trace-b"}

    def test_handles_non_datetime_timestamps(self):
        """Should handle non-datetime start_time or end_time."""
        task_summaries = {
            "task-1": {
                "start_time": "not-datetime",
                "end_time": None,
                "trace_ids": set(),
            }
        }

        result = _finalize_task_summaries(task_summaries)

        assert result == []  # No duration calculated

    def test_handles_non_set_trace_ids(self):
        """Should handle non-set trace_ids."""
        start = datetime(2023, 10, 1, 12, 0, tzinfo=timezone.utc)
        task_summaries = {
            "task-1": {
                "start_time": start,
                "end_time": start,
                "trace_ids": ["already-list"],
            }
        }

        _finalize_task_summaries(task_summaries)

        # Should remain unchanged
        assert task_summaries["task-1"]["trace_ids"] == ["already-list"]

    def test_returns_multiple_processing_times(self):
        """Should return processing times for all tasks."""
        start = datetime(2023, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
        end1 = datetime(2023, 10, 1, 12, 0, 1, tzinfo=timezone.utc)
        end2 = datetime(2023, 10, 1, 12, 0, 2, tzinfo=timezone.utc)
        task_summaries = {
            "task-1": {"start_time": start, "end_time": end1, "trace_ids": set()},
            "task-2": {"start_time": start, "end_time": end2, "trace_ids": set()},
        }

        result = _finalize_task_summaries(task_summaries)

        assert len(result) == 2
        assert 1000.0 in result
        assert 2000.0 in result


class TestCalculateTraceDepthMetrics:
    """Tests for _calculate_trace_depth_metrics function."""

    def test_calculates_max_and_avg_depth(self):
        """Should calculate max and average trace depth."""
        task_summaries = {
            "task-1": {"thoughts": [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}]},
            "task-2": {"thoughts": [{"id": "t1"}]},
        }

        max_depth, avg_depth = _calculate_trace_depth_metrics(task_summaries)

        assert max_depth == 3
        assert avg_depth == 2.0

    def test_returns_zeros_for_empty_summaries(self):
        """Should return (0, 0) for empty task_summaries."""
        max_depth, avg_depth = _calculate_trace_depth_metrics({})

        assert max_depth == 0
        assert avg_depth == 0.0

    def test_handles_non_dict_summaries(self):
        """Should skip non-dict summaries."""
        task_summaries = {
            "task-1": {"thoughts": [{"id": "t1"}]},
            "task-2": "not-a-dict",
        }

        max_depth, avg_depth = _calculate_trace_depth_metrics(task_summaries)

        assert max_depth == 1
        assert avg_depth == 1.0


class TestTraceConsolidatorProcessTaskId:
    """Tests for TraceConsolidator._process_task_id method."""

    def test_adds_task_to_unique_tasks(self):
        """Should add task_id to unique_tasks set."""
        consolidator = TraceConsolidator()
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
        )
        task_summaries = {}
        unique_tasks: Set[str] = set()

        consolidator._process_task_id(span, "task-123", task_summaries, unique_tasks)

        assert "task-123" in unique_tasks

    def test_initializes_task_summary_when_new(self):
        """Should initialize task summary for new task_id."""
        consolidator = TraceConsolidator()
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
        )
        task_summaries = {}
        unique_tasks: Set[str] = set()

        consolidator._process_task_id(span, "task-123", task_summaries, unique_tasks)

        assert "task-123" in task_summaries
        assert task_summaries["task-123"]["task_id"] == "task-123"

    def test_does_not_overwrite_existing_summary(self):
        """Should not overwrite existing task summary."""
        consolidator = TraceConsolidator()
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
        )
        existing_summary = {"task_id": "task-123", "custom_field": "preserved"}
        task_summaries = {"task-123": existing_summary}
        unique_tasks: Set[str] = set()

        consolidator._process_task_id(span, "task-123", task_summaries, unique_tasks)

        assert task_summaries["task-123"]["custom_field"] == "preserved"


class TestTraceConsolidatorProcessThoughtId:
    """Tests for TraceConsolidator._process_thought_id method."""

    def test_adds_thought_to_unique_thoughts(self):
        """Should add thought_id to unique_thoughts set."""
        consolidator = TraceConsolidator()
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
        )
        task_summaries = {}
        unique_thoughts: Set[str] = set()
        thoughts_by_type: Dict[str, int] = defaultdict(int)
        handler_actions: Dict[str, int] = defaultdict(int)

        consolidator._process_thought_id(
            span, "thought-1", None, "handler", task_summaries, unique_thoughts, thoughts_by_type, handler_actions
        )

        assert "thought-1" in unique_thoughts

    def test_tracks_thought_type(self):
        """Should track thought_type in thoughts_by_type."""
        consolidator = TraceConsolidator()
        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            tags=SpanTags(additional_tags={"thought_type": "reflection"}),
        )
        task_summaries = {}
        unique_thoughts: Set[str] = set()
        thoughts_by_type: Dict[str, int] = defaultdict(int)
        handler_actions: Dict[str, int] = defaultdict(int)

        consolidator._process_thought_id(
            span, "thought-1", None, "handler", task_summaries, unique_thoughts, thoughts_by_type, handler_actions
        )

        assert thoughts_by_type["reflection"] == 1


class TestTraceConsolidatorConsolidate:
    """Tests for TraceConsolidator.consolidate method."""

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_spans(self):
        """Should create summary even with no spans."""
        consolidator = TraceConsolidator()
        period_start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2023, 10, 1, 1, 0, tzinfo=timezone.utc)

        result = await consolidator.consolidate(period_start, period_end, "test", [])

        # Should return a summary node even with empty data
        assert result is not None

    @pytest.mark.asyncio
    async def test_processes_spans_and_creates_summary(self):
        """Should process spans and create summary node."""
        consolidator = TraceConsolidator()
        period_start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2023, 10, 1, 1, 0, tzinfo=timezone.utc)

        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            task_id="task-123",
            component_type="handler",
            duration_ms=100.0,
        )

        result = await consolidator.consolidate(period_start, period_end, "test", [span])

        assert result is not None
        assert result.id == "trace_summary_20231001_00"

    @pytest.mark.asyncio
    async def test_stores_summary_via_memory_bus(self):
        """Should store summary via memory bus when available."""
        mock_bus = AsyncMock()
        mock_bus.memorize.return_value = MemoryOpResult(status=MemoryOpStatus.OK)
        consolidator = TraceConsolidator(memory_bus=mock_bus)
        period_start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2023, 10, 1, 1, 0, tzinfo=timezone.utc)

        result = await consolidator.consolidate(period_start, period_end, "test", [])

        mock_bus.memorize.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_on_storage_failure(self):
        """Should return None when storage fails."""
        mock_bus = AsyncMock()
        mock_bus.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.ERROR,
            error="Storage failed",
        )
        consolidator = TraceConsolidator(memory_bus=mock_bus)
        period_start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        period_end = datetime(2023, 10, 1, 1, 0, tzinfo=timezone.utc)

        result = await consolidator.consolidate(period_start, period_end, "test", [])

        assert result is None


class TestTraceConsolidatorGetEdges:
    """Tests for TraceConsolidator.get_edges method."""

    def test_returns_empty_list_for_no_spans(self):
        """Should return empty list when no spans."""
        consolidator = TraceConsolidator()
        mock_node = MagicMock()

        edges = consolidator.get_edges(mock_node, [])

        assert edges == []

    def test_creates_error_task_edges(self):
        """Should create ERROR_TASK edges for spans with errors."""
        consolidator = TraceConsolidator()
        mock_node = MagicMock()

        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            error=True,
        )

        edges = consolidator.get_edges(mock_node, [span])

        assert len(edges) == 1
        assert edges[0][2] == "ERROR_TASK"

    def test_creates_high_latency_task_edges(self):
        """Should create HIGH_LATENCY_TASK edges for high latency spans."""
        consolidator = TraceConsolidator()
        mock_node = MagicMock()

        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            latency_ms=6000.0,  # > 5000ms threshold
        )

        edges = consolidator.get_edges(mock_node, [span])

        assert len(edges) == 1
        assert edges[0][2] == "HIGH_LATENCY_TASK"

    def test_limits_error_edges_to_10(self):
        """Should limit ERROR_TASK edges to 10."""
        consolidator = TraceConsolidator()
        mock_node = MagicMock()

        # Create 15 error spans
        spans = [
            TraceSpanData(
                trace_id=f"trace-{i}",
                span_id=f"span-{i}",
                operation_name="test",
                service_name="test-service",
                timestamp=datetime.now(timezone.utc),
                error=True,
            )
            for i in range(15)
        ]

        edges = consolidator.get_edges(mock_node, spans)

        error_edges = [e for e in edges if e[2] == "ERROR_TASK"]
        assert len(error_edges) == 10

    def test_uses_duration_ms_as_fallback_for_latency(self):
        """Should use duration_ms when latency_ms is None."""
        consolidator = TraceConsolidator()
        mock_node = MagicMock()

        span = TraceSpanData(
            trace_id="trace-1",
            span_id="span-1",
            operation_name="test",
            service_name="test-service",
            timestamp=datetime.now(timezone.utc),
            latency_ms=None,
            duration_ms=6000.0,  # > 5000ms threshold
        )

        edges = consolidator.get_edges(mock_node, [span])

        assert len(edges) == 1
        assert edges[0][2] == "HIGH_LATENCY_TASK"
