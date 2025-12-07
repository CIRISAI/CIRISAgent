import json
import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional

from ciris_engine.logic.persistence.db import get_db_connection
from ciris_engine.logic.persistence.db.dialect import get_adapter
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphEdgeAttributes, GraphNode, GraphScope, NodeType

logger = logging.getLogger(__name__)


def parse_json_field(value: Any) -> Any:
    """Parse JSON field from database.

    PostgreSQL JSONB returns dict, SQLite returns string.
    This function handles both cases.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value) if value else {}
    return {}


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects and Pydantic models."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Handle Pydantic models
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        # Handle objects with dict() method
        if hasattr(obj, "dict"):
            return obj.dict()
        return super().default(obj)


def add_graph_node(node: GraphNode, time_service: TimeServiceProtocol, db_path: Optional[str] = None) -> str:
    """Insert or update a graph node, merging attributes if it exists."""
    logger.debug(
        f"add_graph_node: node_id={node.id!r}, scope={node.scope.value!r}, type={node.type.value!r}, db_path={db_path!r}"
    )
    try:
        with get_db_connection(db_path=db_path) as conn:
            # First check if node exists and get its current attributes
            cursor = conn.cursor()
            logger.debug("DEBUG add_graph_node: Executing SELECT to check if node exists")
            cursor.execute(
                "SELECT attributes_json FROM graph_nodes WHERE node_id = ? AND scope = ?", (node.id, node.scope.value)
            )
            existing_row = cursor.fetchone()
            logger.debug(f"DEBUG add_graph_node: existing_row = {existing_row}")

            if existing_row:
                # Node exists - merge attributes
                existing_attrs = parse_json_field(existing_row["attributes_json"])

                # Convert node.attributes to dict if it's a Pydantic model
                if hasattr(node.attributes, "model_dump"):
                    new_attrs = node.attributes.model_dump()
                elif hasattr(node.attributes, "dict"):
                    new_attrs = node.attributes.dict()
                else:  # isinstance(node.attributes, dict)
                    new_attrs = node.attributes

                # Merge attributes - new values override old ones
                merged_attrs = {**existing_attrs, **new_attrs}

                # Update the node
                sql = """
                    UPDATE graph_nodes
                    SET attributes_json = :attributes_json,
                        version = version + 1,
                        updated_by = :updated_by,
                        updated_at = :updated_at
                    WHERE node_id = :node_id AND scope = :scope
                """
                params = {
                    "node_id": node.id,
                    "scope": node.scope.value,
                    "attributes_json": json.dumps(merged_attrs, cls=DateTimeEncoder),
                    "updated_by": node.updated_by,
                    "updated_at": node.updated_at or time_service.now().isoformat(),
                }
                logger.debug("Updating graph node %s with merged attributes", node.id)
            else:
                # Node doesn't exist - insert new
                sql = """
                    INSERT INTO graph_nodes
                    (node_id, scope, node_type, attributes_json, version, updated_by, updated_at)
                    VALUES (:node_id, :scope, :node_type, :attributes_json, :version, :updated_by, :updated_at)
                """
                params = {
                    "node_id": node.id,
                    "scope": node.scope.value,
                    "node_type": node.type.value,
                    "attributes_json": json.dumps(node.attributes, cls=DateTimeEncoder),
                    "version": str(node.version),  # Convert to string for SQL params
                    "updated_by": node.updated_by,
                    "updated_at": node.updated_at or time_service.now().isoformat(),
                }
                logger.debug("Inserting new graph node %s", node.id)

            logger.debug(f"add_graph_node: Executing {'UPDATE' if existing_row else 'INSERT'} with params: {params}")
            cursor.execute(sql, params)
            logger.debug(f"add_graph_node: cursor.rowcount = {cursor.rowcount}")
            conn.commit()
            logger.debug("add_graph_node: Committed successfully")

            # If we just created a new USER node, ensure TEMPORARY consent exists
            if not existing_row and node.type == NodeType.USER:
                logger.info(f"New USER node created: {node.id}. Creating TEMPORARY consent.")
                try:
                    # Import here to avoid circular dependencies
                    from ciris_engine.schemas.consent.core import ConsentStream

                    # Store consent directly in database
                    # NOTE: Cannot use ConsentService.grant_consent() here because:
                    # 1. add_graph_node() is synchronous but grant_consent() is async
                    # 2. This runs during node persistence, before services are fully initialized
                    consent_node = GraphNode(
                        id=f"consent_{node.id}",
                        type=NodeType.CONSENT,
                        scope=GraphScope.LOCAL,
                        attributes={
                            "user_id": node.id,
                            "stream": ConsentStream.TEMPORARY.value,
                            "granted_at": time_service.now().isoformat(),
                            "expires_at": (
                                time_service.now() + timedelta(days=14)
                            ).isoformat(),  # 14-day temporary consent
                            "reason": "Default TEMPORARY consent on user creation",
                            "categories": [],
                            "impact_score": 0.0,
                            "attribution_count": 0,
                        },
                        updated_by="system_user_creation",
                        updated_at=time_service.now(),
                    )

                    # Recursively add the consent node (but it won't trigger again since it's not a USER type)
                    add_graph_node(consent_node, time_service=time_service, db_path=db_path)
                    logger.info(f"Created TEMPORARY consent for new user {node.id}")

                except Exception as e:
                    logger.warning(f"Could not create consent for user {node.id}: {e}")
                    # Don't fail the node creation if consent fails

        logger.debug("Successfully saved graph node %s in scope %s", node.id, node.scope.value)
        return node.id
    except Exception as e:
        logger.exception("Failed to add/update graph node %s: %s", node.id, e)
        raise


def get_graph_node(node_id: str, scope: GraphScope, db_path: Optional[str] = None) -> Optional[GraphNode]:
    sql = "SELECT * FROM graph_nodes WHERE node_id = ? AND scope = ?"
    logger.debug(f"get_graph_node: node_id={node_id!r}, scope={scope.value!r}, db_path={db_path!r}")
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            logger.debug("DEBUG get_graph_node: Executing SELECT")
            cursor.execute(sql, (node_id, scope.value))
            row = cursor.fetchone()
            logger.debug(f"get_graph_node: row = {row}")
            if row:
                attrs = parse_json_field(row["attributes_json"])
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
    adapter = get_adapter()
    columns = ["edge_id", "source_node_id", "target_node_id", "scope", "relationship", "weight", "attributes_json"]
    sql = adapter.upsert(table="graph_edges", columns=columns, conflict_columns=["edge_id"])

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
            # Note: PostgreSQLCursorWrapper automatically translates ? to %s
            cursor.execute(sql, (scope.value, node_id, node_id))
            rows = cursor.fetchall()
            for row in rows:
                attrs = parse_json_field(row["attributes_json"])
                # Extract only valid GraphEdgeAttributes fields
                valid_attrs = {}
                if "created_at" in attrs:
                    valid_attrs["created_at"] = attrs["created_at"]
                if "context" in attrs:
                    valid_attrs["context"] = attrs["context"]

                edges.append(
                    GraphEdge(
                        source=row["source_node_id"],
                        target=row["target_node_id"],
                        relationship=row["relationship"],
                        scope=scope,
                        weight=row["weight"],
                        attributes=GraphEdgeAttributes(**valid_attrs) if valid_attrs else GraphEdgeAttributes(),
                    )
                )
    except Exception as e:
        logger.exception("Failed to fetch edges for node %s: %s", node_id, e)
    return edges


def get_all_graph_nodes(
    scope: Optional[GraphScope] = None,
    node_type: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[GraphNode]:
    """
    Get all graph nodes with optional filters.

    Args:
        scope: Filter by scope (optional)
        node_type: Filter by node type (optional)
        limit: Maximum number of nodes to return
        offset: Number of nodes to skip (for pagination)
        db_path: Optional database path

    Returns:
        List of GraphNode objects
    """
    sql = "SELECT * FROM graph_nodes WHERE 1=1"
    params: List[Any] = []

    if scope is not None:
        sql += " AND scope = ?"
        params.append(scope.value if hasattr(scope, "value") else scope)

    if node_type is not None:
        sql += " AND node_type = ?"
        params.append(node_type)

    sql += " ORDER BY updated_at DESC"

    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    if offset is not None:
        sql += " OFFSET ?"
        params.append(offset)

    nodes = []
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            for row in rows:
                attrs = parse_json_field(row["attributes_json"])
                nodes.append(
                    GraphNode(
                        id=row["node_id"],
                        type=row["node_type"],
                        scope=row["scope"],
                        attributes=attrs,
                        version=row["version"],
                        updated_by=row["updated_by"],
                        updated_at=row["updated_at"],
                    )
                )

        logger.debug("Retrieved %d graph nodes with filters scope=%s, type=%s", len(nodes), scope, node_type)
        return nodes

    except Exception as e:
        logger.exception("Failed to fetch all graph nodes: %s", e)
        return []


def get_nodes_by_type(
    node_type: str,
    scope: Optional[GraphScope] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[GraphNode]:
    """
    Get all nodes of a specific type.

    Args:
        node_type: The type of nodes to retrieve
        scope: Filter by scope (optional)
        limit: Maximum number of nodes to return
        offset: Number of nodes to skip (for pagination)
        db_path: Optional database path

    Returns:
        List of GraphNode objects of the specified type
    """
    return get_all_graph_nodes(scope=scope, node_type=node_type, limit=limit, offset=offset, db_path=db_path)
