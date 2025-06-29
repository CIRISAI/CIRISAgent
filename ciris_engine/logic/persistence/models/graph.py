import json
import logging
from typing import Any, List, Optional
from datetime import datetime

from ciris_engine.logic.persistence import get_db_connection
from ciris_engine.schemas.services.graph_core import GraphNode, GraphEdge, GraphScope
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects and Pydantic models."""

    def default(self, obj: Any):
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Handle Pydantic models
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()
        # Handle objects with dict() method
        if hasattr(obj, 'dict'):
            return obj.dict()
        return super().default(obj)

def add_graph_node(node: GraphNode, time_service: TimeServiceProtocol, db_path: Optional[str] = None) -> str:
    """Insert or replace a graph node."""
    sql = """
        INSERT OR REPLACE INTO graph_nodes
        (node_id, scope, node_type, attributes_json, version, updated_by, updated_at)
        VALUES (:node_id, :scope, :node_type, :attributes_json, :version, :updated_by, :updated_at)
    """
    params = {
        "node_id": node.id,
        "scope": node.scope.value,
        "node_type": node.type.value,
        "attributes_json": json.dumps(node.attributes, cls=DateTimeEncoder),
        "version": node.version,
        "updated_by": node.updated_by,
        "updated_at": node.updated_at or time_service.now().isoformat(),
    }
    try:
        with get_db_connection(db_path=db_path) as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.debug("Added graph node %s in scope %s", node.id, node.scope.value)
        return node.id
    except Exception as e:
        logger.exception("Failed to add graph node %s: %s", node.id, e)
        raise

def get_graph_node(node_id: str, scope: GraphScope, db_path: Optional[str] = None) -> Optional[GraphNode]:
    sql = "SELECT * FROM graph_nodes WHERE node_id = ? AND scope = ?"
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (node_id, scope.value))
            row = cursor.fetchone()
            if row:
                attrs = json.loads(row["attributes_json"]) if row["attributes_json"] else {}
                return GraphNode(
                    id=row["node_id"],
                    type=row["node_type"],
                    scope=scope,
                    attributes=attrs,
                    version=row["version"],
                    updated_by=row["updated_by"],
                    updated_at=row["updated_at"],
                )
            return None
    except Exception as e:
        logger.exception("Failed to fetch graph node %s: %s", node_id, e)
        return None

def delete_graph_node(node_id: str, scope: GraphScope, db_path: Optional[str] = None) -> int:
    sql = "DELETE FROM graph_nodes WHERE node_id = ? AND scope = ?"
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.execute(sql, (node_id, scope.value))
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        logger.exception("Failed to delete graph node %s: %s", node_id, e)
        return 0

def add_graph_edge(edge: GraphEdge, db_path: Optional[str] = None) -> str:
    sql = """
        INSERT OR REPLACE INTO graph_edges
        (edge_id, source_node_id, target_node_id, scope, relationship, weight, attributes_json)
        VALUES (:edge_id, :source_node_id, :target_node_id, :scope, :relationship, :weight, :attributes_json)
    """
    edge_id = f"{edge.source}->{edge.target}->{edge.relationship}"  # deterministic
    params = {
        "edge_id": edge_id,
        "source_node_id": edge.source,
        "target_node_id": edge.target,
        "scope": edge.scope.value,
        "relationship": edge.relationship,
        "weight": edge.weight,
        "attributes_json": json.dumps(edge.attributes, cls=DateTimeEncoder),
    }
    try:
        with get_db_connection(db_path=db_path) as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.debug("Added graph edge %s", edge_id)
        return edge_id
    except Exception as e:
        logger.exception("Failed to add graph edge %s: %s", edge_id, e)
        raise

def delete_graph_edge(edge_id: str, db_path: Optional[str] = None) -> int:
    sql = "DELETE FROM graph_edges WHERE edge_id = ?"
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.execute(sql, (edge_id,))
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        logger.exception("Failed to delete graph edge %s: %s", edge_id, e)
        return 0

def get_edges_for_node(node_id: str, scope: GraphScope, db_path: Optional[str] = None) -> List[GraphEdge]:
    sql = "SELECT * FROM graph_edges WHERE scope = ? AND (source_node_id = ? OR target_node_id = ?)"
    edges: List[GraphEdge] = []
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (scope.value, node_id, node_id))
            rows = cursor.fetchall()
            for row in rows:
                attrs = json.loads(row["attributes_json"]) if row["attributes_json"] else {}
                edges.append(
                    GraphEdge(
                        source=row["source_node_id"],
                        target=row["target_node_id"],
                        relationship=row["relationship"],
                        scope=scope,
                        weight=row["weight"],
                        attributes=attrs,
                    )
                )
    except Exception as e:
        logger.exception("Failed to fetch edges for node %s: %s", node_id, e)
    return edges
