"""Tests for edge_helpers module."""

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.edge_helpers import (
    create_cross_summary_attributes,
    create_generic_edge_attributes,
    create_summary_edge_attributes,
    create_task_summary_attributes,
    create_trace_summary_attributes,
)
from ciris_engine.schemas.services.graph.edges import (
    CrossSummaryAttributes,
    GenericEdgeAttributes,
    SummaryEdgeAttributes,
    TaskSummaryAttributes,
    TraceSummaryAttributes,
)


class TestCreateSummaryEdgeAttributes:
    """Tests for create_summary_edge_attributes."""

    def test_creates_summary_attributes_with_defaults(self) -> None:
        """Test creating summary attributes with default values."""
        result = create_summary_edge_attributes()

        assert isinstance(result, SummaryEdgeAttributes)
        assert result.context == "Summary edge created during consolidation"
        assert result.created_by == "tsdb_consolidation"
        assert result.period_label is None
        assert result.node_count is None
        assert result.aggregation_type is None

    def test_creates_summary_attributes_with_all_params(self) -> None:
        """Test creating summary attributes with all parameters."""
        result = create_summary_edge_attributes(
            period_label="hourly",
            node_count=10,
            aggregation_type="mean",
            context="Custom context",
        )

        assert isinstance(result, SummaryEdgeAttributes)
        assert result.context == "Custom context"
        assert result.period_label == "hourly"
        assert result.node_count == 10
        assert result.aggregation_type == "mean"


class TestCreateTaskSummaryAttributes:
    """Tests for create_task_summary_attributes."""

    def test_creates_task_summary_with_required_params(self) -> None:
        """Test creating task summary with required parameters."""
        result = create_task_summary_attributes(task_count=5)

        assert isinstance(result, TaskSummaryAttributes)
        assert result.task_count == 5
        assert result.handlers_used == []
        assert result.duration_ms is None
        assert result.context == "Task summary edge"

    def test_creates_task_summary_with_all_params(self) -> None:
        """Test creating task summary with all parameters."""
        result = create_task_summary_attributes(
            task_count=10,
            handlers_used=["handler1", "handler2"],
            duration_ms=1500.5,
            context="Custom task context",
        )

        assert result.task_count == 10
        assert result.handlers_used == ["handler1", "handler2"]
        assert result.duration_ms == 1500.5
        assert result.context == "Custom task context"


class TestCreateTraceSummaryAttributes:
    """Tests for create_trace_summary_attributes."""

    def test_creates_trace_summary_with_required_params(self) -> None:
        """Test creating trace summary with required parameters."""
        result = create_trace_summary_attributes(span_count=20)

        assert isinstance(result, TraceSummaryAttributes)
        assert result.span_count == 20
        assert result.error_count == 0
        assert result.services == []
        assert result.context == "Trace summary edge"

    def test_creates_trace_summary_with_all_params(self) -> None:
        """Test creating trace summary with all parameters."""
        result = create_trace_summary_attributes(
            span_count=50,
            error_count=3,
            services=["service1", "service2"],
            context="Custom trace context",
        )

        assert result.span_count == 50
        assert result.error_count == 3
        assert result.services == ["service1", "service2"]
        assert result.context == "Custom trace context"


class TestCreateCrossSummaryAttributes:
    """Tests for create_cross_summary_attributes."""

    def test_creates_cross_summary_with_required_params(self) -> None:
        """Test creating cross summary with required parameters."""
        result = create_cross_summary_attributes(relationship_type="causal")

        assert isinstance(result, CrossSummaryAttributes)
        assert result.relationship_type == "causal"
        assert result.shared_resources is None
        assert result.correlation_strength is None
        assert result.context == "Cross-summary causal edge"

    def test_creates_cross_summary_with_all_params(self) -> None:
        """Test creating cross summary with all parameters."""
        result = create_cross_summary_attributes(
            relationship_type="temporal",
            shared_resources={"cpu": 0.5, "memory": 0.3},
            correlation_strength=0.85,
            context="Custom cross context",
        )

        assert result.relationship_type == "temporal"
        assert result.shared_resources == {"cpu": 0.5, "memory": 0.3}
        assert result.correlation_strength == 0.85
        assert result.context == "Custom cross context"


class TestCreateGenericEdgeAttributes:
    """Tests for create_generic_edge_attributes."""

    def test_creates_generic_attributes_with_defaults(self) -> None:
        """Test creating generic attributes with default values."""
        result = create_generic_edge_attributes()

        assert isinstance(result, GenericEdgeAttributes)
        assert result.context == "Generic edge"
        assert result.created_by == "tsdb_consolidation"
        assert result.data == {}

    def test_creates_generic_attributes_with_data(self) -> None:
        """Test creating generic attributes with custom data."""
        custom_data = {"key1": "value1", "key2": 123}
        result = create_generic_edge_attributes(
            data=custom_data,
            context="Custom generic context",
        )

        assert result.data == custom_data
        assert result.context == "Custom generic context"
