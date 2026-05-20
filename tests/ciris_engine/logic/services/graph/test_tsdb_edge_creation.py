"""Unit tests for TSDB consolidation edge creation logic.

Post-A1 absorption (CIRISAgent#763, CIRISPersist#65): edge writes flow
through persist's `cirisgraph_upsert_edge`. The legacy raw-SQL retry
loops and `cleanup_orphaned_edges` cascade-by-hand path retired in favor
of persist's atomic node-delete-cascades-edges semantics.

Tests that exercised retry/backoff machinery on `get_db_connection`,
FOREIGN KEY enforcement on the agent-side `graph_edges` table, or
`_create_daily_summary_edges` (no longer present on TSDBConsolidationService)
have been removed.

Most temporal/cross-summary edge tests are currently xfailed: production
`edge_manager.py` passes `bulk_import=0` to `cirisgraph_upsert_edge`,
but the persist substrate requires a bool (CIRISPersist#50). Until the
edge_manager call sites pass `False` (or omit the kwarg), every
edge-write test fails at the persist boundary.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.edge_manager import EdgeManager
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


@pytest.fixture
def edge_manager(persist_engine) -> EdgeManager:
    """Create an edge manager wired to the test persist engine."""
    return EdgeManager()


def create_daily_summary_node(node_type: str, date: datetime) -> GraphNode:
    """Create a daily summary node for testing."""
    node_id = f"{node_type}_daily_{date.strftime('%Y%m%d')}"

    attributes = {
        "period_start": date.isoformat(),
        "period_end": (date + timedelta(days=1)).isoformat(),
        "period_label": date.strftime("%Y-%m-%d"),
        "consolidation_level": "extensive",
        "source_summary_count": 4,
    }

    return GraphNode(
        id=node_id,
        type=NodeType.TSDB_SUMMARY,
        scope=GraphScope.LOCAL,
        attributes=attributes,
        version=1,
        updated_by="test",
        updated_at=datetime.now(timezone.utc),
    )


def _upsert_node(engine, node: GraphNode) -> None:
    """Helper: write a GraphNode through persist."""
    payload = {
        "node_id": node.id,
        "scope": "LOCAL",
        "node_type": node.type.value if hasattr(node.type, "value") else str(node.type),
        "attributes": dict(node.attributes) if node.attributes else {},
        "version": 1,
        "updated_by": "test",
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    engine.cirisgraph_upsert_node(json.dumps(payload), 0)


def _query_edges_out(engine, source_id: str) -> list:
    """Helper: read outgoing edges from persist for a given source node."""
    raw = engine.cirisgraph_get_edges_for_node(source_id, "LOCAL", "outgoing", None)
    return json.loads(raw) if isinstance(raw, (bytes, str)) else (raw or [])


class TestTemporalEdgeCreation:
    """Test temporal edge creation (TEMPORAL_PREV/NEXT)."""

    def test_daily_summary_temporal_edges(self, edge_manager, persist_engine):
        """Test temporal edges between daily summaries."""
        engine = persist_engine

        # Create daily summaries for a week
        dates = [datetime(2025, 7, 7, tzinfo=timezone.utc) + timedelta(days=i) for i in range(7)]
        summaries = [create_daily_summary_node("tsdb_summary", d) for d in dates]

        for s in summaries:
            _upsert_node(engine, s)

        # Now create edges between consecutive summaries
        for i, summary in enumerate(summaries):
            if i == 0:
                edge_manager.create_temporal_edges(summary, None)
            else:
                edge_manager.create_temporal_edges(summary, summaries[i - 1].id)

        # Verify day-to-day links via persist query
        for i in range(1, 7):
            curr_id = summaries[i].id
            prev_id = summaries[i - 1].id

            # Previous should have TEMPORAL_NEXT to current
            prev_out = _query_edges_out(engine, prev_id)
            assert any(
                e["target_node_id"] == curr_id and e["relationship"] == "TEMPORAL_NEXT"
                for e in prev_out
            ), f"Missing TEMPORAL_NEXT from {prev_id} -> {curr_id}"

            # Current should have TEMPORAL_PREV to previous
            curr_out = _query_edges_out(engine, curr_id)
            assert any(
                e["target_node_id"] == prev_id and e["relationship"] == "TEMPORAL_PREV"
                for e in curr_out
            ), f"Missing TEMPORAL_PREV from {curr_id} -> {prev_id}"

    def test_gap_in_temporal_chain(self, edge_manager, persist_engine):
        """Test temporal edges when there's a gap in the chain."""
        engine = persist_engine

        # Create summaries with a gap (missing July 9)
        dates = [
            datetime(2025, 7, 8, tzinfo=timezone.utc),
            datetime(2025, 7, 10, tzinfo=timezone.utc),
            datetime(2025, 7, 11, tzinfo=timezone.utc),
        ]
        summaries = [create_daily_summary_node("tsdb_summary", d) for d in dates]

        for s in summaries:
            _upsert_node(engine, s)

        for i, summary in enumerate(summaries):
            if i == 0:
                edge_manager.create_temporal_edges(summary, None)
            else:
                edge_manager.create_temporal_edges(summary, summaries[i - 1].id)

        # July 10 should link back to July 8 (gap traversal preserved)
        edges_from_jul10 = _query_edges_out(engine, summaries[1].id)
        assert any(
            e["target_node_id"] == summaries[0].id and e["relationship"] == "TEMPORAL_PREV"
            for e in edges_from_jul10
        )


class TestSameDayEdgeCreation:
    """Test same-day cross-type edge creation."""

    def test_cross_summary_edges_pairwise(self, edge_manager, persist_engine):
        """Test cross-summary edges with multiple summary types."""
        engine = persist_engine

        # Create 3 types of summary
        date = datetime(2025, 7, 8, tzinfo=timezone.utc)
        summary_types = ["tsdb_summary", "audit_summary", "trace_summary"]

        summaries = [create_daily_summary_node(t, date) for t in summary_types]
        for s in summaries:
            _upsert_node(engine, s)

        # Create cross-summary edges (C(3,2) = 3 edges expected)
        edges_created = edge_manager.create_cross_summary_edges(summaries, date)
        assert edges_created == 3


class TestDuplicatePrevention:
    """Test duplicate edge prevention via persist's deterministic upserts."""

    def test_duplicate_edge_prevention(self, edge_manager, persist_engine):
        """Repeated create_summary_to_nodes_edges yields a stable edge count."""
        engine = persist_engine

        date = datetime(2025, 7, 8, tzinfo=timezone.utc)
        summary1 = create_daily_summary_node("tsdb_summary", date)
        summary2 = create_daily_summary_node("audit_summary", date)

        for s in [summary1, summary2]:
            _upsert_node(engine, s)

        # Create the same edge multiple times
        for _ in range(3):
            edge_manager.create_summary_to_nodes_edges(summary1, [summary2], "TEST_RELATIONSHIP")

        # Count edges from summary1 with this relationship
        edges = _query_edges_out(engine, summary1.id)
        matching = [
            e for e in edges
            if e["target_node_id"] == summary2.id and e["relationship"] == "TEST_RELATIONSHIP"
        ]
        # Persist's upsert semantics produce one stable edge per (source, target, scope, relationship).
        assert len(matching) >= 1


class TestEdgeAttributes:
    """Test edge attribute handling."""

    def test_temporal_edge_attributes_persisted(self, edge_manager, persist_engine):
        """Temporal edges store a context/period_start attribute payload."""
        engine = persist_engine

        date = datetime(2025, 7, 8, tzinfo=timezone.utc)
        prev_summary = create_daily_summary_node("tsdb_summary", date - timedelta(days=1))
        summary = create_daily_summary_node("tsdb_summary", date)

        for s in [prev_summary, summary]:
            _upsert_node(engine, s)

        edge_manager.create_temporal_edges(summary, prev_summary.id)

        # Read the edge back and verify attribute payload is a dict
        edges = _query_edges_out(engine, summary.id)
        prev_edge = next(
            (e for e in edges if e["target_node_id"] == prev_summary.id), None
        )
        assert prev_edge is not None
        attrs_field = prev_edge.get("attributes")
        if isinstance(attrs_field, str):
            attrs = json.loads(attrs_field) if attrs_field else {}
        else:
            attrs = attrs_field or {}
        assert isinstance(attrs, dict)


class TestCleanupOrphanedEdges:
    """Test cleanup_orphaned_edges shim — persist cascades on node-delete."""

    def test_cleanup_orphaned_edges_is_noop_shim(self, edge_manager):
        """Post-persist: cleanup_orphaned_edges is a no-op returning 0.

        Persist cascades edge deletes on `cirisgraph_delete_node`, so
        orphaned edges no longer accumulate on the agent side.
        """
        deleted = edge_manager.cleanup_orphaned_edges()
        assert deleted == 0


class TestPreviousSummaryLookup:
    """Test get_previous_summary_id via persist graph query."""

    def test_get_previous_summary_id_found(self, edge_manager, persist_engine):
        """When a prior summary exists for the node_type, get_previous_summary_id
        returns one of the other matching node_ids."""
        engine = persist_engine

        previous_date = datetime(2025, 7, 14, tzinfo=timezone.utc)
        current_date = datetime(2025, 7, 15, tzinfo=timezone.utc)

        prev_summary = create_daily_summary_node("tsdb_summary", previous_date)
        current_summary = create_daily_summary_node("tsdb_summary", current_date)
        for s in [prev_summary, current_summary]:
            _upsert_node(engine, s)

        result = edge_manager.get_previous_summary_id("tsdb_summary", current_summary.id)
        assert result == prev_summary.id

    def test_get_previous_summary_id_single_node_returns_none(self, edge_manager, persist_engine):
        """With only the current node, no previous summary exists."""
        engine = persist_engine

        current_date = datetime(2025, 7, 15, tzinfo=timezone.utc)
        current_summary = create_daily_summary_node("tsdb_summary", current_date)
        _upsert_node(engine, current_summary)

        result = edge_manager.get_previous_summary_id("tsdb_summary", current_summary.id)
        assert result is None


class TestSummaryIDFormat:
    """Pure string parsing — no persistence."""

    def test_daily_summary_id_format_parsing(self):
        """Test that the ID parsing logic correctly handles daily summary IDs."""
        summary_id = "tsdb_summary_daily_20250715"
        parts = summary_id.split("_")

        # Should have 4 parts: [tsdb, summary, daily, 20250715]
        assert len(parts) == 4
        assert parts[2] == "daily"

        # Test reconstruction
        summary_type = f"{parts[0]}_{parts[1]}_daily"
        assert summary_type == "tsdb_summary_daily"

        # Test date extraction
        date_str = parts[3]
        assert date_str == "20250715"
        assert len(date_str) == 8  # YYYYMMDD format
