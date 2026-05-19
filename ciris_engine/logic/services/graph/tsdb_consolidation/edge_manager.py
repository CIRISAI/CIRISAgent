"""Edge management for TSDB consolidation — persist-substrate routed for 2.9.0.

Phase 3b cutover (CIRISAgent#763, CIRISPersist#65): every edge write now
routes through `engine.cirisgraph_upsert_edge`. The legacy raw-SQL
inserts retired with the rest of the consolidation pipeline.

The service.py orchestration uses two methods from this class:
- `create_summary_to_nodes_edges(summary, nodes, relationship, weight_text)`
- `cleanup_orphaned_edges()` — persist cascades on node-delete, so this
  is now a no-op shim.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import uuid4

from ciris_engine.schemas.services.graph_core import GraphNode

logger = logging.getLogger(__name__)


def _engine() -> Any:
    """Resolve the wired persist engine."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    return get_persist_engine()


def _scope_str(scope: Any) -> str:
    """Normalize a GraphScope (enum / str) into persist's uppercase scope token."""
    if scope is None:
        return "LOCAL"
    if hasattr(scope, "value"):
        return str(scope.value).upper()
    return str(scope).upper()


class EdgeManager:
    """Thin persist-substrate wrapper preserving the legacy public API."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """`db_path` retained for signature compat; persist owns the connection."""
        self.db_path = db_path

    # ------------------------------------------------------------------
    # Primary write path used by the service
    # ------------------------------------------------------------------

    def create_summary_to_nodes_edges(
        self,
        summary: GraphNode,
        nodes: List[GraphNode],
        relationship: str,
        weight_text: Optional[str] = None,
    ) -> int:
        """Create one edge per node from `summary` to each entry in `nodes`.

        Routes through `engine.cirisgraph_upsert_edge`. Returns the count
        of edges actually written.
        """
        engine = _engine()
        if engine is None or not nodes:
            return 0

        created = 0
        scope = _scope_str(summary.scope)
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for target in nodes:
            edge_payload = {
                "edge_id": str(uuid4()),
                "source_node_id": summary.id,
                "target_node_id": target.id,
                "scope": scope,
                "relationship": relationship,
                "weight": 1.0,
                "attributes": {"context": weight_text or relationship},
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            try:
                engine.cirisgraph_upsert_edge(json.dumps(edge_payload), 0)
                created += 1
            except Exception as e:
                logger.warning(
                    f"cirisgraph_upsert_edge failed for {summary.id} -> {target.id}: {e}"
                )
        return created

    # ------------------------------------------------------------------
    # No-op shim — persist cascades edge deletes on cirisgraph_delete_node
    # ------------------------------------------------------------------

    def cleanup_orphaned_edges(self) -> int:
        """No-op shim — persist cascades on node-delete (CIRISPersist#65).

        The legacy implementation scanned `graph_edges` for dangling source
        or target references and deleted them. Persist's hard-delete on a
        node removes all incident edges atomically, so orphaned edges no
        longer accumulate.
        """
        return 0

    # ------------------------------------------------------------------
    # Helpers kept as thin wrappers for any remaining test caller
    # ------------------------------------------------------------------

    def create_cross_summary_edges(
        self, summaries: List[GraphNode], period_start: datetime
    ) -> int:
        """Create CROSS_SUMMARY edges between every pair of summaries in the list."""
        if len(summaries) < 2:
            return 0
        count = 0
        scope = _scope_str(summaries[0].scope)
        for i, a in enumerate(summaries):
            for b in summaries[i + 1 :]:
                count += self._upsert_edge(a.id, b.id, scope, "CROSS_SUMMARY", period_start)
        return count

    def create_temporal_edges(
        self, current_summary: GraphNode, previous_summary_id: Optional[str]
    ) -> int:
        """Create TEMPORAL_NEXT / TEMPORAL_PREV edges between adjacent summaries."""
        if not previous_summary_id:
            return 0
        scope = _scope_str(current_summary.scope)
        n = self._upsert_edge(previous_summary_id, current_summary.id, scope, "TEMPORAL_NEXT")
        n += self._upsert_edge(current_summary.id, previous_summary_id, scope, "TEMPORAL_PREV")
        return n

    def get_previous_summary_id(
        self, node_type_prefix: str, current_node_id: str
    ) -> Optional[str]:
        """Best-effort previous-summary lookup via persist graph query."""
        engine = _engine()
        if engine is None:
            return None
        try:
            filter_json = json.dumps({
                "scope": "LOCAL",
                "node_type": node_type_prefix,
            })
            cursor = json.dumps({"version": "v1", "last_ts": "9999-12-31T23:59:59Z", "last_id": ""})
            raw = engine.cirisgraph_query_nodes(filter_json, cursor, 50)
            parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            items = parsed.get("items", []) if isinstance(parsed, dict) else []
            for row in items:
                if isinstance(row, dict) and row.get("node_id") != current_node_id:
                    return str(row["node_id"])
        except Exception as e:
            logger.warning(f"get_previous_summary_id failed: {e}")
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _upsert_edge(
        self,
        source_id: str,
        target_id: str,
        scope: str,
        relationship: str,
        period_start: Optional[datetime] = None,
    ) -> int:
        engine = _engine()
        if engine is None:
            return 0
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload = {
            "edge_id": str(uuid4()),
            "source_node_id": source_id,
            "target_node_id": target_id,
            "scope": scope,
            "relationship": relationship,
            "weight": 1.0,
            "attributes": {
                "period_start": period_start.isoformat() if period_start else None,
            },
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        try:
            engine.cirisgraph_upsert_edge(json.dumps(payload), 0)
            return 1
        except Exception as e:
            logger.warning(f"cirisgraph_upsert_edge({source_id} -> {target_id}) failed: {e}")
            return 0
