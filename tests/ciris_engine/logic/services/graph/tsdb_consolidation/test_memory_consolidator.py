"""
Comprehensive unit tests for MemoryConsolidator.

This test suite improves coverage for the memory consolidator from 25.7% toward 50%+
by testing edge cases, error paths, and untested functions.
"""

from datetime import datetime, timezone
from typing import Dict, List

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.consolidators.memory import MemoryConsolidator
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


# Helper functions to create test nodes
def create_graph_node(
    node_id: str,
    node_type: NodeType,
    attributes: Dict | None = None,
    updated_at: datetime | None = None,
) -> GraphNode:
    """Create a graph node for testing."""
    return GraphNode(
        id=node_id,
        type=node_type,
        scope=GraphScope.LOCAL,
        attributes=attributes or {},
        version=1,
        updated_at=updated_at,
    )


def create_summary_node(node_id: str, node_type: NodeType) -> GraphNode:
    """Create a summary node for testing."""
    return create_graph_node(node_id, node_type)


class TestMemoryConsolidatorInit:
    """Test MemoryConsolidator initialization."""

    def test_init_with_memory_bus(self):
        """Test initialization with memory bus."""
        from unittest.mock import Mock

        mock_bus = Mock()
        consolidator = MemoryConsolidator(memory_bus=mock_bus)
        assert consolidator._memory_bus is mock_bus

    def test_init_without_memory_bus(self):
        """Test initialization without memory bus."""
        consolidator = MemoryConsolidator()
        assert consolidator._memory_bus is None

    def test_memory_node_types_constant(self):
        """Test that MEMORY_NODE_TYPES constant is properly defined."""
        consolidator = MemoryConsolidator()
        expected_types = ["concept", "identity", "identity_snapshot", "config", "behavioral", "social"]
        assert consolidator.MEMORY_NODE_TYPES == expected_types


class TestMemoryConsolidatorConsolidateBasics:
    """Test basic consolidate functionality."""

    def test_consolidate_no_memory_nodes(self):
        """Test consolidation when no memory nodes exist."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type={},
            summary_nodes=[],
        )

        assert edges == []

    def test_consolidate_no_relevant_memory_nodes(self):
        """Test consolidation with nodes but no relevant memory types."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        # Create nodes of non-memory types
        nodes_by_type = {
            "user": [create_graph_node("user1", NodeType.USER)],
            "channel": [create_graph_node("channel1", NodeType.CHANNEL)],
        }

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=[],
        )

        assert edges == []

    def test_consolidate_empty_memory_node_lists(self):
        """Test consolidation when memory node types exist but are empty."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        # Create empty lists for memory types
        nodes_by_type = {"concept": [], "identity": [], "config": []}

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=[],
        )

        assert edges == []

    def test_consolidate_no_summary_nodes(self):
        """Test consolidation with memory nodes but no summary nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        nodes_by_type = {"concept": [create_graph_node("concept1", NodeType.CONCEPT)]}

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=[],
        )

        assert edges == []


class TestMemoryConsolidatorTSDBSummary:
    """Test TSDB summary consolidation."""

    def test_tsdb_summary_with_metrics_config(self):
        """Test TSDB summary creates edges to metrics-related config nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        # Create config nodes with metrics-related attributes
        config_nodes = [
            create_graph_node("config1", NodeType.CONFIG, {"config_type": "metric", "key": "cpu_threshold"}),
            create_graph_node("config2", NodeType.CONFIG, {"config_type": "telemetry", "key": "log_level"}),
            create_graph_node("config3", NodeType.CONFIG, {"config_type": "monitoring", "key": "alert_threshold"}),
        ]

        nodes_by_type = {"config": config_nodes}
        summary_nodes = [create_summary_node("summary1", NodeType.TSDB_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 3
        for edge in edges:
            source, target, edge_type, attrs = edge
            assert source.id == "summary1"
            assert edge_type == "METRICS_CONFIG"
            assert attrs["period"] == "2025-01-01"
            assert "config_type" in attrs

    def test_tsdb_summary_with_non_metrics_config(self):
        """Test TSDB summary ignores non-metrics config nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        config_nodes = [create_graph_node("config1", NodeType.CONFIG, {"config_type": "user_setting"})]

        nodes_by_type = {"config": config_nodes}
        summary_nodes = [create_summary_node("summary1", NodeType.TSDB_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 0

    def test_tsdb_summary_with_resource_config(self):
        """Test TSDB summary includes resource-related config."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        config_nodes = [create_graph_node("config1", NodeType.CONFIG, {"key": "resource_limit"})]

        nodes_by_type = {"config": config_nodes}
        summary_nodes = [create_summary_node("summary1", NodeType.TSDB_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 1


class TestMemoryConsolidatorConversationSummary:
    """Test conversation summary consolidation."""

    def test_conversation_summary_with_concepts(self):
        """Test conversation summary creates edges to concept nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)
        updated_time = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

        concept_nodes = [
            create_graph_node("concept1", NodeType.CONCEPT, updated_at=updated_time),
            create_graph_node("concept2", NodeType.CONCEPT),
        ]

        nodes_by_type = {"concept": concept_nodes}
        summary_nodes = [create_summary_node("summary1", NodeType.CONVERSATION_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 2
        for edge in edges:
            source, target, edge_type, attrs = edge
            assert source.id == "summary1"
            assert edge_type == "DISCUSSED_CONCEPT"
            assert attrs["period"] == "2025-01-01"
            assert "relevance" in attrs

    def test_conversation_summary_with_social_nodes(self):
        """Test conversation summary creates edges to social nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        social_nodes = [create_graph_node("social1", NodeType.SOCIAL, {"interaction_type": "conversation"})]

        nodes_by_type = {"social": social_nodes}
        summary_nodes = [create_summary_node("summary1", NodeType.CONVERSATION_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 1
        source, target, edge_type, attrs = edges[0]
        assert edge_type == "SOCIAL_CONTEXT"
        assert attrs["period"] == "2025-01-01"

    def test_conversation_summary_with_concepts_and_social(self):
        """Test conversation summary creates edges to both concepts and social nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        nodes_by_type = {
            "concept": [create_graph_node("concept1", NodeType.CONCEPT)],
            "social": [create_graph_node("social1", NodeType.SOCIAL)],
        }
        summary_nodes = [create_summary_node("summary1", NodeType.CONVERSATION_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 2
        edge_types = [edge[2] for edge in edges]
        assert "DISCUSSED_CONCEPT" in edge_types
        assert "SOCIAL_CONTEXT" in edge_types


class TestMemoryConsolidatorTraceSummary:
    """Test trace summary consolidation."""

    def test_trace_summary_with_behavioral_nodes(self):
        """Test trace summary creates edges to behavioral pattern nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        behavioral_nodes = [
            create_graph_node("behavioral1", NodeType.BEHAVIORAL, {"pattern_type": "recurring"}),
            create_graph_node("behavioral2", NodeType.BEHAVIORAL, {"pattern_type": "anomaly"}),
        ]

        nodes_by_type = {"behavioral": behavioral_nodes}
        summary_nodes = [create_summary_node("summary1", NodeType.TRACE_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 2
        for edge in edges:
            source, target, edge_type, attrs = edge
            assert edge_type == "BEHAVIORAL_PATTERN"
            assert attrs["period"] == "2025-01-01"

    def test_trace_summary_without_behavioral_nodes(self):
        """Test trace summary with no behavioral nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        nodes_by_type = {"concept": [create_graph_node("concept1", NodeType.CONCEPT)]}
        summary_nodes = [create_summary_node("summary1", NodeType.TRACE_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 0


class TestMemoryConsolidatorAuditSummary:
    """Test audit summary consolidation."""

    def test_audit_summary_with_identity_nodes(self):
        """Test audit summary creates edges to identity nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        identity_nodes = [
            create_graph_node("identity1", NodeType.IDENTITY, {"purpose_changed": True}),
            create_graph_node("identity2", NodeType.IDENTITY, {"capabilities_changed": True}),
            create_graph_node("identity3", NodeType.IDENTITY, {"boundaries_changed": True}),
        ]

        nodes_by_type = {"identity": identity_nodes}
        summary_nodes = [create_summary_node("summary1", NodeType.AUDIT_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 3
        change_types = [edge[3]["change_type"] for edge in edges]
        assert "purpose_update" in change_types
        assert "capability_update" in change_types
        assert "boundary_update" in change_types

    def test_audit_summary_with_identity_snapshots(self):
        """Test audit summary creates edges to identity snapshot nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        snapshot_nodes = [
            create_graph_node("snapshot1", NodeType.IDENTITY_SNAPSHOT, {"timestamp": "2025-01-01T10:00:00"}),
        ]

        nodes_by_type = {"identity_snapshot": snapshot_nodes}
        summary_nodes = [create_summary_node("summary1", NodeType.AUDIT_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 1
        source, target, edge_type, attrs = edges[0]
        assert edge_type == "IDENTITY_SNAPSHOT_REF"

    def test_audit_summary_with_identity_and_snapshots(self):
        """Test audit summary creates edges to both identity and snapshot nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        nodes_by_type = {
            "identity": [create_graph_node("identity1", NodeType.IDENTITY, {})],
            "identity_snapshot": [create_graph_node("snapshot1", NodeType.IDENTITY_SNAPSHOT, {})],
        }
        summary_nodes = [create_summary_node("summary1", NodeType.AUDIT_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 2
        edge_types = [edge[2] for edge in edges]
        assert "IDENTITY_AUDIT" in edge_types
        assert "IDENTITY_SNAPSHOT_REF" in edge_types


class TestMemoryConsolidatorTaskSummary:
    """Test task summary consolidation."""

    def test_task_summary_with_task_concepts(self):
        """Test task summary creates edges to task-relevant concept nodes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        concept_nodes = [
            create_graph_node("concept1", NodeType.CONCEPT, {"concept_type": "task_handler"}),
            create_graph_node("concept2", NodeType.CONCEPT, {"concept_type": "action_processing"}),
        ]

        nodes_by_type = {"concept": concept_nodes}
        summary_nodes = [create_summary_node("summary1", NodeType.TASK_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        assert len(edges) == 2
        for edge in edges:
            source, target, edge_type, attrs = edge
            assert edge_type == "TASK_CONCEPT"

    def test_task_summary_with_non_task_concepts(self):
        """Test task summary doesn't create edges for non-task concepts."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        # Concept without task-related keywords
        concept_nodes = [create_graph_node("concept1", NodeType.CONCEPT, {"concept_type": "general"})]

        nodes_by_type = {"concept": concept_nodes}
        summary_nodes = [create_summary_node("summary1", NodeType.TASK_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        # Should not create edge for non-task concepts
        assert len(edges) == 0


class TestMemoryConsolidatorHelperMethods:
    """Test helper methods in MemoryConsolidator."""

    def test_is_metrics_config_with_metric_keyword(self):
        """Test _is_metrics_config identifies metric configs."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"config_type": "metric"})
        assert consolidator._is_metrics_config(config_node) is True

    def test_is_metrics_config_with_telemetry_keyword(self):
        """Test _is_metrics_config identifies telemetry configs."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"config_type": "telemetry"})
        assert consolidator._is_metrics_config(config_node) is True

    def test_is_metrics_config_with_monitoring_keyword(self):
        """Test _is_metrics_config identifies monitoring configs."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"key": "monitoring_interval"})
        assert consolidator._is_metrics_config(config_node) is True

    def test_is_metrics_config_with_resource_keyword(self):
        """Test _is_metrics_config identifies resource configs."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"key": "resource_limit"})
        assert consolidator._is_metrics_config(config_node) is True

    def test_is_metrics_config_with_log_level_keyword(self):
        """Test _is_metrics_config identifies log_level configs."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"key": "log_level"})
        assert consolidator._is_metrics_config(config_node) is True

    def test_is_metrics_config_empty_attributes(self):
        """Test _is_metrics_config with empty attributes."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {})
        assert consolidator._is_metrics_config(config_node) is False

    def test_is_metrics_config_non_matching(self):
        """Test _is_metrics_config with non-matching config."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"config_type": "user_preference"})
        assert consolidator._is_metrics_config(config_node) is False

    def test_is_task_relevant_concept_with_task_keyword(self):
        """Test _is_task_relevant_concept identifies task concepts."""
        consolidator = MemoryConsolidator()
        concept_node = create_graph_node("concept1", NodeType.CONCEPT, {"concept_type": "task_management"})
        assert consolidator._is_task_relevant_concept(concept_node) is True

    def test_is_task_relevant_concept_with_handler_keyword(self):
        """Test _is_task_relevant_concept identifies handler concepts."""
        consolidator = MemoryConsolidator()
        concept_node = create_graph_node("concept1", NodeType.CONCEPT, {"concept_type": "message_handler"})
        assert consolidator._is_task_relevant_concept(concept_node) is True

    def test_is_task_relevant_concept_with_action_keyword(self):
        """Test _is_task_relevant_concept identifies action concepts."""
        consolidator = MemoryConsolidator()
        concept_node = create_graph_node("concept1", NodeType.CONCEPT, {"concept_type": "action_handler"})
        assert consolidator._is_task_relevant_concept(concept_node) is True

    def test_is_task_relevant_concept_with_processing_keyword(self):
        """Test _is_task_relevant_concept identifies processing concepts."""
        consolidator = MemoryConsolidator()
        concept_node = create_graph_node("concept1", NodeType.CONCEPT, {"concept_type": "data_processing"})
        assert consolidator._is_task_relevant_concept(concept_node) is True

    def test_is_task_relevant_concept_empty_attributes(self):
        """Test _is_task_relevant_concept with empty concept_type."""
        consolidator = MemoryConsolidator()
        concept_node = create_graph_node("concept1", NodeType.CONCEPT, {})
        # Empty concept_type results in False (no keywords in empty string)
        assert consolidator._is_task_relevant_concept(concept_node) is False

    def test_is_task_relevant_concept_non_matching(self):
        """Test _is_task_relevant_concept returns False for non-matching concepts."""
        consolidator = MemoryConsolidator()
        concept_node = create_graph_node("concept1", NodeType.CONCEPT, {"concept_type": "general"})
        # Returns False when no keywords match (empty string after keywords check)
        result = consolidator._is_task_relevant_concept(concept_node)
        # The function checks for keywords in concept_type, returns False if none match
        assert result is False

    def test_calculate_relevance_with_updated_at(self):
        """Test _calculate_relevance returns 1.0 for updated nodes."""
        consolidator = MemoryConsolidator()
        updated_time = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        concept_node = create_graph_node("concept1", NodeType.CONCEPT, updated_at=updated_time)
        summary_node = create_summary_node("summary1", NodeType.CONVERSATION_SUMMARY)

        relevance = consolidator._calculate_relevance(concept_node, summary_node)
        assert relevance == 1.0

    def test_calculate_relevance_without_updated_at(self):
        """Test _calculate_relevance returns 0.5 for non-updated nodes."""
        consolidator = MemoryConsolidator()
        concept_node = create_graph_node("concept1", NodeType.CONCEPT)
        summary_node = create_summary_node("summary1", NodeType.CONVERSATION_SUMMARY)

        relevance = consolidator._calculate_relevance(concept_node, summary_node)
        assert relevance == 0.5

    def test_get_identity_change_type_purpose_changed(self):
        """Test _get_identity_change_type identifies purpose changes."""
        consolidator = MemoryConsolidator()
        identity_node = create_graph_node("identity1", NodeType.IDENTITY, {"purpose_changed": True})
        change_type = consolidator._get_identity_change_type(identity_node)
        assert change_type == "purpose_update"

    def test_get_identity_change_type_capabilities_changed(self):
        """Test _get_identity_change_type identifies capability changes."""
        consolidator = MemoryConsolidator()
        identity_node = create_graph_node("identity1", NodeType.IDENTITY, {"capabilities_changed": True})
        change_type = consolidator._get_identity_change_type(identity_node)
        assert change_type == "capability_update"

    def test_get_identity_change_type_boundaries_changed(self):
        """Test _get_identity_change_type identifies boundary changes."""
        consolidator = MemoryConsolidator()
        identity_node = create_graph_node("identity1", NodeType.IDENTITY, {"boundaries_changed": True})
        change_type = consolidator._get_identity_change_type(identity_node)
        assert change_type == "boundary_update"

    def test_get_identity_change_type_multiple_changes(self):
        """Test _get_identity_change_type with multiple changes (purpose takes precedence)."""
        consolidator = MemoryConsolidator()
        identity_node = create_graph_node(
            "identity1",
            NodeType.IDENTITY,
            {"purpose_changed": True, "capabilities_changed": True, "boundaries_changed": True},
        )
        change_type = consolidator._get_identity_change_type(identity_node)
        # First check wins (purpose_changed)
        assert change_type == "purpose_update"

    def test_get_identity_change_type_empty_attributes(self):
        """Test _get_identity_change_type with empty attributes."""
        consolidator = MemoryConsolidator()
        identity_node = create_graph_node("identity1", NodeType.IDENTITY, {})
        change_type = consolidator._get_identity_change_type(identity_node)
        assert change_type == "general_update"

    def test_get_identity_change_type_no_changes(self):
        """Test _get_identity_change_type with no specific changes."""
        consolidator = MemoryConsolidator()
        identity_node = create_graph_node("identity1", NodeType.IDENTITY, {})
        change_type = consolidator._get_identity_change_type(identity_node)
        assert change_type == "general_update"

    def test_get_config_type_from_config_type_field(self):
        """Test _get_config_type extracts from config_type field."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"config_type": "database"})
        config_type = consolidator._get_config_type(config_node)
        assert config_type == "database"

    def test_get_config_type_from_key_with_dot(self):
        """Test _get_config_type extracts from key field with dot."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"key": "database.main_db"})
        config_type = consolidator._get_config_type(config_node)
        assert config_type == "database"

    def test_get_config_type_from_key_without_dot(self):
        """Test _get_config_type uses key directly when no dot."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"key": "timeout"})
        config_type = consolidator._get_config_type(config_node)
        assert config_type == "timeout"

    def test_get_config_type_config_type_takes_precedence(self):
        """Test _get_config_type prefers config_type over key."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"config_type": "database", "key": "cache.ttl"})
        config_type = consolidator._get_config_type(config_node)
        assert config_type == "database"

    def test_get_config_type_no_type_or_key(self):
        """Test _get_config_type with no config_type or key fields."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {"some_other_field": "value"})
        config_type = consolidator._get_config_type(config_node)
        assert config_type == "general"

    def test_get_config_type_empty_dict(self):
        """Test _get_config_type with empty dict."""
        consolidator = MemoryConsolidator()
        config_node = create_graph_node("config1", NodeType.CONFIG, {})
        config_type = consolidator._get_config_type(config_node)
        assert config_type == "general"


class TestMemoryConsolidatorMultipleSummaryNodes:
    """Test consolidation with multiple summary nodes."""

    def test_multiple_summary_nodes_same_type(self):
        """Test consolidation with multiple summary nodes of the same type."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        concept_nodes = [create_graph_node("concept1", NodeType.CONCEPT)]
        nodes_by_type = {"concept": concept_nodes}
        summary_nodes = [
            create_summary_node("summary1", NodeType.CONVERSATION_SUMMARY),
            create_summary_node("summary2", NodeType.CONVERSATION_SUMMARY),
        ]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        # Each summary should create an edge to the concept
        assert len(edges) == 2
        source_ids = [edge[0].id for edge in edges]
        assert "summary1" in source_ids
        assert "summary2" in source_ids

    def test_multiple_summary_nodes_different_types(self):
        """Test consolidation with summary nodes of different types."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        nodes_by_type = {
            "concept": [create_graph_node("concept1", NodeType.CONCEPT, {"concept_type": "task_handler"})],
            "behavioral": [create_graph_node("behavioral1", NodeType.BEHAVIORAL)],
        }
        summary_nodes = [
            create_summary_node("summary1", NodeType.TASK_SUMMARY),
            create_summary_node("summary2", NodeType.TRACE_SUMMARY),
        ]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        # Task summary -> concept, Trace summary -> behavioral
        assert len(edges) == 2
        edge_types = {edge[2] for edge in edges}
        assert "TASK_CONCEPT" in edge_types
        assert "BEHAVIORAL_PATTERN" in edge_types


class TestMemoryConsolidatorDefensiveCoding:
    """Test defensive coding for non-dict attributes."""

    def test_is_metrics_config_with_non_dict_attributes(self):
        """Test _is_metrics_config handles non-dict attributes gracefully."""
        from unittest.mock import Mock

        consolidator = MemoryConsolidator()
        # Create a mock node with non-dict attributes
        mock_node = Mock(spec=GraphNode)
        mock_node.attributes = "not_a_dict"  # Non-dict attribute

        result = consolidator._is_metrics_config(mock_node)
        assert result is False

    def test_is_task_relevant_concept_with_non_dict_attributes(self):
        """Test _is_task_relevant_concept defaults to True for non-dict attributes."""
        from unittest.mock import Mock

        consolidator = MemoryConsolidator()
        mock_node = Mock(spec=GraphNode)
        mock_node.attributes = 12345  # Non-dict attribute

        result = consolidator._is_task_relevant_concept(mock_node)
        assert result is True

    def test_get_config_type_with_non_dict_attributes(self):
        """Test _get_config_type returns general for non-dict attributes."""
        from unittest.mock import Mock

        consolidator = MemoryConsolidator()
        mock_node = Mock(spec=GraphNode)
        mock_node.attributes = ["not", "a", "dict"]  # Non-dict attribute

        result = consolidator._get_config_type(mock_node)
        assert result == "general"


class TestMemoryConsolidatorEdgeCases:
    """Test edge cases and error handling."""

    def test_consolidate_with_all_memory_node_types(self):
        """Test consolidation with all memory node types present."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        nodes_by_type = {
            "concept": [create_graph_node("concept1", NodeType.CONCEPT)],
            "identity": [create_graph_node("identity1", NodeType.IDENTITY)],
            "identity_snapshot": [create_graph_node("snapshot1", NodeType.IDENTITY_SNAPSHOT)],
            "config": [create_graph_node("config1", NodeType.CONFIG, {"config_type": "metric"})],
            "behavioral": [create_graph_node("behavioral1", NodeType.BEHAVIORAL)],
            "social": [create_graph_node("social1", NodeType.SOCIAL)],
        }
        summary_nodes = [
            create_summary_node("summary1", NodeType.TSDB_SUMMARY),
            create_summary_node("summary2", NodeType.CONVERSATION_SUMMARY),
            create_summary_node("summary3", NodeType.TRACE_SUMMARY),
            create_summary_node("summary4", NodeType.AUDIT_SUMMARY),
        ]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        # Should create multiple edges across different summary types
        assert len(edges) > 0
        edge_types = {edge[2] for edge in edges}
        # Verify we have edges from different summary types
        assert len(edge_types) > 1

    def test_consolidate_with_empty_attributes(self):
        """Test consolidation handles nodes with empty attributes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        nodes_by_type = {"identity": [create_graph_node("identity1", NodeType.IDENTITY, {})]}
        summary_nodes = [create_summary_node("summary1", NodeType.AUDIT_SUMMARY)]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label="2025-01-01",
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        # Should still create edge with general_update
        assert len(edges) == 1
        assert edges[0][3]["change_type"] == "general_update"

    def test_consolidate_period_label_in_all_edges(self):
        """Test that period label appears in all edge attributes."""
        consolidator = MemoryConsolidator()
        period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)
        period_label = "custom-period-2025-01-01"

        nodes_by_type = {
            "concept": [create_graph_node("concept1", NodeType.CONCEPT)],
            "config": [create_graph_node("config1", NodeType.CONFIG, {"config_type": "metric"})],
        }
        summary_nodes = [
            create_summary_node("summary1", NodeType.CONVERSATION_SUMMARY),
            create_summary_node("summary2", NodeType.TSDB_SUMMARY),
        ]

        edges = consolidator.consolidate(
            period_start=period_start,
            period_end=period_end,
            period_label=period_label,
            nodes_by_type=nodes_by_type,
            summary_nodes=summary_nodes,
        )

        # All edges should have the custom period label
        for edge in edges:
            attrs = edge[3]
            assert attrs["period"] == period_label
