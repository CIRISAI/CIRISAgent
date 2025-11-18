"""
Edge management for TSDB consolidation.

Handles proper creation of edges in the graph_edges table instead of storing as nodes.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union, cast
from uuid import uuid4

from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.logic.persistence.db.dialect import get_adapter, init_dialect
from ciris_engine.logic.persistence.db.operations import (
    batch_insert_edges_if_not_exist,
    insert_edge_if_not_exists,
    insert_node_if_not_exists,
)
from ciris_engine.logic.utils.jsondict_helpers import get_float
from ciris_engine.schemas.services.graph.consolidation import ParticipantData
from ciris_engine.schemas.services.graph.edge_types import EdgeSpecification
from ciris_engine.schemas.services.graph.edges import UserParticipationAttributes
from ciris_engine.schemas.services.graph_core import GraphNode
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class EdgeManager:
    """Manages proper edge creation in the graph."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize edge manager.

        Args:
            db_path: Database path to use (if not provided, uses default)
        """
        self._db_path = db_path

    def create_summary_to_nodes_edges(
        self,
        summary_node: GraphNode,
        target_nodes: List[GraphNode],
        relationship: str = "SUMMARIZES",
        context: Optional[str] = None,
    ) -> int:
        """
        Create edges from a summary node to all nodes it summarizes.

        Args:
            summary_node: The summary node
            target_nodes: List of nodes being summarized
            relationship: Edge relationship type
            context: Optional context for the edge

        Returns:
            Number of edges created
        """
        if not target_nodes:
            logger.warning("No target nodes provided for create_summary_to_nodes_edges")
            return 0

        logger.debug(f"Creating SUMMARIZES edges from {summary_node.id} to {len(target_nodes)} nodes")
        edges_created = 0

        try:
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()
                adapter = get_adapter()
                ph = adapter.placeholder()

                # First, ensure the summary node exists
                cursor.execute(
                    f"""
                    SELECT node_id FROM graph_nodes WHERE node_id = {ph}
                """,
                    (summary_node.id,),
                )

                if not cursor.fetchone():
                    logger.error(f"Summary node {summary_node.id} does not exist in database!")
                    return 0

                # Then ensure all target nodes exist
                target_node_ids = [node.id for node in target_nodes]
                placeholders = ",".join(["?"] * len(target_node_ids))
                cursor.execute(
                    f"""
                    SELECT node_id FROM graph_nodes
                    WHERE node_id IN ({placeholders})
                """,
                    target_node_ids,
                )

                existing_nodes = {row["node_id"] for row in cursor.fetchall()}
                missing_nodes = set(target_node_ids) - existing_nodes

                # Create missing channel nodes
                if missing_nodes:
                    logger.info(f"Creating {len(missing_nodes)} missing nodes before creating edges")
                    for node_id in missing_nodes:
                        if node_id.startswith("channel_"):
                            # Extract channel info
                            parts = node_id.split("_", 2)
                            channel_type = parts[1] if len(parts) > 1 else "unknown"
                            channel_name = parts[2] if len(parts) > 2 else node_id

                            insert_node_if_not_exists(
                                node_id=node_id,
                                scope="local",
                                node_type="channel",
                                attributes={
                                    "channel_id": node_id,
                                    "channel_type": channel_type,
                                    "channel_name": channel_name,
                                    "created_by": "tsdb_consolidation",
                                },
                                version=1,
                                updated_by="tsdb_consolidation",
                                db_path=self._db_path,
                            )

                # Batch insert edges
                edge_data = []
                for target_node in target_nodes:
                    # Create deterministic edge ID based on source, target, and relationship
                    # This ensures the same edge always has the same ID
                    edge_id = f"edge_{summary_node.id}_{target_node.id}_{relationship}".replace(" ", "_")
                    edge_data.append(
                        (
                            edge_id,
                            summary_node.id,
                            target_node.id,
                            summary_node.scope.value if summary_node.scope else "local",
                            relationship,
                            1.0,  # Default weight
                            f'{{"context": "{context or "Summary edge"}"}}',
                            datetime.now(timezone.utc).isoformat(),
                        )
                    )

                # Insert edges using operations layer
                edges_created = batch_insert_edges_if_not_exist(edge_data, db_path=self._db_path)

                logger.info(f"Created {edges_created} edges from {summary_node.id} to target nodes")

                # Debug: Check if edges were actually created
                if edges_created == 0 and len(edge_data) > 0:
                    logger.warning(
                        f"No edges created despite {len(edge_data)} edge data entries. Checking for duplicates..."
                    )
                    # Check if edges already exist
                    cursor.execute(
                        f"""
                        SELECT COUNT(*) as count FROM graph_edges
                        WHERE source_node_id = {ph} AND relationship = {ph}
                    """,
                        (summary_node.id, relationship),
                    )
                    existing = cursor.fetchone()["count"]
                    logger.warning(f"Found {existing} existing {relationship} edges from {summary_node.id}")

        except Exception as e:
            logger.error(f"Failed to create summary edges: {e}")

        return edges_created

    def create_cross_summary_edges(self, summaries: List[GraphNode], period_start: datetime) -> int:
        """
        Create edges between different summary types in the same period.

        Args:
            summaries: List of summary nodes from the same period
            period_start: Start of the consolidation period

        Returns:
            Number of edges created
        """
        if len(summaries) < 2:
            return 0

        edges_created = 0

        try:
            with get_db_connection(db_path=self._db_path):
                edge_data = []

                # Create edges between each pair of summaries
                for i in range(len(summaries)):
                    for j in range(i + 1, len(summaries)):
                        source = summaries[i]
                        target = summaries[j]

                        # Determine relationship based on node types
                        relationship = self._determine_cross_summary_relationship(source.id, target.id)

                        edge_id = f"edge_{uuid4().hex[:8]}"
                        edge_data.append(
                            (
                                edge_id,
                                source.id,
                                target.id,
                                source.scope.value if source.scope else "local",
                                relationship,
                                1.0,
                                f'{{"context": "Same period correlation for {period_start.isoformat()}"}}',
                                datetime.now(timezone.utc).isoformat(),
                            )
                        )

                if edge_data:
                    edges_created = batch_insert_edges_if_not_exist(edge_data, db_path=self._db_path)
                    logger.info(f"Created {edges_created} cross-summary edges for period {period_start}")

        except Exception as e:
            logger.error(f"Failed to create cross-summary edges: {e}")

        return edges_created

    def create_temporal_edges(self, current_summary: GraphNode, previous_summary_id: Optional[str]) -> int:
        """
        Create temporal edges for a new summary:
        1. Create TEMPORAL_NEXT from current to itself (marking it as latest)
        2. If previous exists:
           - Update previous TEMPORAL_NEXT to point to current (not itself)
           - Create TEMPORAL_PREV from current to previous

        Args:
            current_summary: Current period's summary node
            previous_summary_id: ID of previous period's summary of same type

        Returns:
            Number of edges created/updated
        """
        edges_created = 0

        try:
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Step 1: Create TEMPORAL_NEXT from current to itself (marking as latest)
                edge_id_self = f"edge_{uuid4().hex[:8]}"
                insert_edge_if_not_exists(
                    edge_id=edge_id_self,
                    source_node_id=current_summary.id,
                    target_node_id=current_summary.id,  # Points to itself
                    scope=current_summary.scope.value if hasattr(current_summary.scope, "value") else "local",
                    relationship="TEMPORAL_NEXT",
                    weight=1.0,
                    attributes={"is_latest": True, "context": "Current latest summary"},
                    db_path=self._db_path,
                )
                edges_created += 1

                if previous_summary_id:
                    # Step 2a: Update previous TEMPORAL_NEXT to point to current
                    # First, delete the self-referencing edge
                    # Use database-agnostic placeholder
                    from ciris_engine.logic.persistence.db.dialect import get_adapter

                    adapter = get_adapter()
                    ph = adapter.placeholder()

                    cursor.execute(
                        f"""
                        DELETE FROM graph_edges
                        WHERE source_node_id = {ph}
                          AND target_node_id = {ph}
                          AND relationship = 'TEMPORAL_NEXT'
                    """,
                        (previous_summary_id, previous_summary_id),
                    )

                    # Then create new edge pointing to current
                    edge_id_forward = f"edge_{uuid4().hex[:8]}"
                    cursor.execute(
                        f"""
                        INSERT INTO graph_edges
                        (edge_id, source_node_id, target_node_id, scope,
                         relationship, weight, attributes_json, created_at)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                        (
                            edge_id_forward,
                            previous_summary_id,
                            current_summary.id,
                            current_summary.scope.value if hasattr(current_summary.scope, "value") else "local",
                            "TEMPORAL_NEXT",
                            1.0,
                            json.dumps({"is_latest": False, "context": "Points to next period"}),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    edges_created += 1

                    # Step 2b: Create TEMPORAL_PREV from current to previous
                    edge_id_backward = f"edge_{uuid4().hex[:8]}"
                    cursor.execute(
                        f"""
                        INSERT INTO graph_edges
                        (edge_id, source_node_id, target_node_id, scope,
                         relationship, weight, attributes_json, created_at)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                        (
                            edge_id_backward,
                            current_summary.id,
                            previous_summary_id,
                            current_summary.scope.value if hasattr(current_summary.scope, "value") else "local",
                            "TEMPORAL_PREV",
                            1.0,
                            json.dumps({"context": "Points to previous period"}),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    edges_created += 1

                conn.commit()

                logger.debug(
                    f"Created temporal edges for {current_summary.id} (previous: {previous_summary_id or 'None'})"
                )
                return edges_created

        except Exception as e:
            logger.error(f"Failed to create temporal edges: {e}")
            return 0

    def create_concept_edges(
        self, summary_nodes: List[GraphNode], concept_nodes: List[GraphNode], period_label: str
    ) -> int:
        """
        Create edges from summaries to concept nodes in the same period.

        Args:
            summary_nodes: Summary nodes for the period
            concept_nodes: Concept nodes created in the period
            period_label: Human-readable period label

        Returns:
            Number of edges created
        """
        if not summary_nodes or not concept_nodes:
            return 0

        edges_created = 0

        try:
            with get_db_connection(db_path=self._db_path):
                edge_data = []

                # Create edges from each summary to each concept
                for summary in summary_nodes:
                    for concept in concept_nodes:
                        edge_id = f"edge_{uuid4().hex[:8]}"
                        edge_data.append(
                            (
                                edge_id,
                                summary.id,
                                concept.id,
                                summary.scope.value if summary.scope else "local",
                                "PERIOD_CONCEPT",
                                0.8,  # Slightly lower weight for indirect relationships
                                f'{{"context": "Concept created during {period_label}"}}',
                                datetime.now(timezone.utc).isoformat(),
                            )
                        )

                if edge_data:
                    edges_created = batch_insert_edges_if_not_exist(edge_data, db_path=self._db_path)
                    logger.info(f"Created {edges_created} concept edges for period {period_label}")

        except Exception as e:
            logger.error(f"Failed to create concept edges: {e}")

        return edges_created

    def get_previous_summary_id(self, node_type_prefix: str, current_node_id: str) -> Optional[str]:
        """
        Get the ID of the most recent summary node before the current one.

        This handles gaps in the timeline by finding the most recent summary
        regardless of how much time has passed, rather than assuming a fixed interval.

        Args:
            node_type_prefix: Prefix like "tsdb_summary", "conversation_summary", or "tsdb_summary_daily"
            current_node_id: Current summary's full node_id (e.g., "tsdb_summary_20251117_18")

        Returns:
            Node ID of most recent previous summary if found, None otherwise
        """
        try:
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()
                adapter = get_adapter()
                ph = adapter.placeholder()

                # Find the most recent summary with the same prefix that comes before current_node_id
                # Using string comparison works because node IDs are in YYYYMMDD_HH or YYYYMMDD format
                cursor.execute(
                    f"""
                    SELECT node_id
                    FROM graph_nodes
                    WHERE node_id LIKE {ph}
                    AND node_id < {ph}
                    ORDER BY node_id DESC
                    LIMIT 1
                """,
                    (f"{node_type_prefix}_%", current_node_id),
                )

                row = cursor.fetchone()
                if row:
                    prev_id = str(row["node_id"]) if isinstance(row, dict) else str(row[0])
                    logger.debug(f"Found previous summary: {prev_id} (before {current_node_id})")
                    return prev_id
                else:
                    logger.debug(f"No previous summary found before {current_node_id}")
                    return None

        except Exception as e:
            logger.error(f"Failed to find previous summary: {e}")
            return None

    def _determine_cross_summary_relationship(self, source_id: str, target_id: str) -> str:
        """
        Determine the relationship type between two summary nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID

        Returns:
            Relationship type string
        """
        # Extract summary types from IDs
        source_type = source_id.split("_")[0]
        target_type = target_id.split("_")[0]

        # Define meaningful relationships
        relationships = {
            ("conversation", "trace"): "DRIVES_PROCESSING",
            ("trace", "tsdb"): "GENERATES_METRICS",
            ("tsdb", "conversation"): "IMPACTS_QUALITY",
            ("audit", "trace"): "SECURES_EXECUTION",
            ("trace", "audit"): "CREATES_TRAIL",
            ("conversation", "task"): "INITIATES_TASKS",
            ("task", "tsdb"): "CONSUMES_RESOURCES",
        }

        # Look up specific relationship or use default
        return relationships.get((source_type, target_type), "TEMPORAL_CORRELATION")

    def create_user_participation_edges(
        self, conversation_summary: GraphNode, participant_data: Dict[str, ParticipantData], period_label: str
    ) -> int:
        """
        Create edges from conversation summary to user nodes.

        Args:
            conversation_summary: The conversation summary node
            participant_data: Dict mapping user_id to participation metrics
            period_label: Human-readable period label

        Returns:
            Number of edges created
        """
        if not participant_data:
            return 0

        edges_created = 0

        try:
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()
                adapter = get_adapter()
                ph = adapter.placeholder()

                edge_data = []

                for user_id, participant in participant_data.items():
                    user_node_id = f"user_{user_id}"

                    # Check if user node exists
                    cursor.execute(
                        f"""
                        SELECT node_id FROM graph_nodes
                        WHERE node_type = 'user' AND node_id = {ph}
                        LIMIT 1
                    """,
                        (user_node_id,),
                    )

                    user_exists = cursor.fetchone() is not None

                    # Create user node if it doesn't exist
                    if not user_exists and participant.author_name:
                        logger.info(f"Creating user node for {user_id} ({participant.author_name})")

                        user_attributes = {
                            "user_id": user_id,
                            "display_name": participant.author_name,
                            "first_seen": datetime.now(timezone.utc).isoformat(),
                            "created_by": "tsdb_consolidation",
                            "channels": participant.channels,
                        }

                        insert_node_if_not_exists(
                            node_id=user_node_id,
                            scope="local",
                            node_type="user",
                            attributes=user_attributes,
                            version=1,
                            updated_by="tsdb_consolidation",
                            db_path=self._db_path,
                        )
                        user_exists = True

                    if user_exists:
                        # Create edge from summary to user
                        edge_id = f"edge_{uuid4().hex[:8]}"
                        message_count = participant.message_count

                        # Weight based on participation level (normalized 0-1)
                        # More messages = higher weight
                        weight = min(1.0, message_count / 100.0)

                        # Use typed edge attributes
                        edge_attrs = UserParticipationAttributes(
                            context=f"Participated in conversations during {period_label}",
                            message_count=message_count,
                            channels=participant.channels,
                            author_name=participant.author_name,
                        )
                        attributes = edge_attrs.model_dump(exclude_none=True)

                        edge_data.append(
                            (
                                edge_id,
                                conversation_summary.id,
                                f"user_{user_id}",
                                conversation_summary.scope.value if conversation_summary.scope else "local",
                                "INVOLVED_USER",
                                weight,
                                json.dumps(attributes),
                                datetime.now(timezone.utc).isoformat(),
                            )
                        )
                    else:
                        logger.debug(f"User node not found for user_id: {user_id}")

                if edge_data:
                    edges_created = batch_insert_edges_if_not_exist(edge_data, db_path=self._db_path)
                    logger.info(f"Created {edges_created} user participation edges for {conversation_summary.id}")

        except Exception as e:
            logger.error(f"Failed to create user participation edges: {e}")

        return edges_created

    def cleanup_orphaned_edges(self) -> int:
        """
        Remove edges where source or target nodes no longer exist.

        Uses a low-priority DELETE with timeout to avoid blocking other operations.

        Returns:
            Number of edges deleted
        """
        import time

        max_retries = 3
        retry_delay = 0.5  # 500ms

        for attempt in range(max_retries):
            try:
                with get_db_connection(db_path=self._db_path) as conn:
                    # Set a shorter busy timeout for this operation (5 seconds)
                    # PRAGMA is SQLite-specific; PostgreSQL handles timeouts differently
                    adapter = init_dialect(self._db_path or "ciris_engine.db")
                    if adapter.is_sqlite():
                        conn.execute("PRAGMA busy_timeout = 5000")
                    # PostgreSQL: statement_timeout is typically set at connection or session level
                    cursor = conn.cursor()

                    # Delete edges with missing nodes
                    cursor.execute(
                        """
                        DELETE FROM graph_edges
                        WHERE source_node_id NOT IN (SELECT node_id FROM graph_nodes)
                           OR target_node_id NOT IN (SELECT node_id FROM graph_nodes)
                    """
                    )

                    deleted = cursor.rowcount
                    conn.commit()

                    if deleted > 0:
                        logger.info(f"Cleaned up {deleted} orphaned edges")

                    return deleted

            except Exception as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"Database locked during orphaned edge cleanup, retry {attempt + 1}/{max_retries}")
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    logger.error(f"Failed to cleanup orphaned edges: {e}")
                    return 0

        return 0

    def _normalize_edge_specifications(
        self, edges: List[EdgeSpecification]
    ) -> Tuple[List[Tuple[str, str, str, JSONDict, Optional[str]]], set[str]]:
        """Convert EdgeSpecification objects to normalized format.

        Returns:
            Tuple of (normalized_edges, node_ids_to_check)
        """
        normalized_edges = []
        node_ids_to_check = set()

        for edge_spec in edges:
            assert isinstance(edge_spec, EdgeSpecification)
            node_ids_to_check.add(edge_spec.source_node_id)
            node_ids_to_check.add(edge_spec.target_node_id)
            scope_value: Optional[str] = None  # No scope info in EdgeSpecification
            normalized_edges.append(
                (
                    edge_spec.source_node_id,
                    edge_spec.target_node_id,
                    edge_spec.edge_type,
                    edge_spec.attributes.model_dump(exclude_none=True),
                    scope_value,
                )
            )

        return normalized_edges, node_ids_to_check

    def _normalize_edge_tuples(
        self, edges: List[Tuple[GraphNode, GraphNode, str, JSONDict]]
    ) -> Tuple[List[Tuple[str, str, str, JSONDict, Optional[str]]], set[str]]:
        """Convert edge tuples to normalized format.

        Returns:
            Tuple of (normalized_edges, node_ids_to_check)
        """
        normalized_edges = []
        node_ids_to_check = set()

        for source_node, target_node, relationship, attrs in edges:
            node_ids_to_check.add(source_node.id)
            node_ids_to_check.add(target_node.id)
            scope_str: Optional[str] = (
                source_node.scope.value if hasattr(source_node.scope, "value") else str(source_node.scope)
            )
            normalized_edges.append((source_node.id, target_node.id, relationship, attrs or {}, scope_str))

        return normalized_edges, node_ids_to_check

    def _create_missing_channel_node(self, node_id: str, existing_nodes: set[str]) -> None:
        """Create a missing channel node in the database."""
        logger.info(f"Creating missing channel node: {node_id}")

        # Extract channel type from ID (e.g., channel_cli_username_hostname)
        parts = node_id.split("_", 2)
        channel_type = parts[1] if len(parts) > 1 else "unknown"
        channel_name = parts[2] if len(parts) > 2 else node_id

        channel_attributes = {
            "channel_id": node_id,
            "channel_type": channel_type,
            "channel_name": channel_name,
            "created_by": "tsdb_consolidation",
            "first_seen": datetime.now(timezone.utc).isoformat(),
        }

        insert_node_if_not_exists(
            node_id=node_id,
            scope="local",
            node_type="channel",
            attributes=channel_attributes,
            version=1,
            updated_by="tsdb_consolidation",
            db_path=self._db_path,
        )
        existing_nodes.add(node_id)

    def _create_missing_nodes(self, missing_nodes: set[str], existing_nodes: set[str]) -> None:
        """Create missing nodes if they are channels."""
        if not missing_nodes:
            return

        logger.info(f"Found missing nodes referenced in edges: {missing_nodes}")

        for node_id in missing_nodes:
            if node_id.startswith("channel_"):
                self._create_missing_channel_node(node_id, existing_nodes)
            else:
                logger.warning(f"Cannot auto-create node of unknown type: {node_id}")

    def _build_edge_record(
        self, source_id: str, target_id: str, relationship: str, attrs: JSONDict, scope: str
    ) -> Tuple[str, str, str, str, str, float, str, str]:
        """Build a single edge record for database insertion.

        Returns:
            Tuple of (edge_id, source_id, target_id, scope, relationship, weight, attributes_json, created_at)
        """
        edge_id = f"edge_{uuid4().hex[:8]}"

        # Handle self-references with special attributes
        if source_id == target_id:
            edge_attrs = attrs.copy()
            edge_attrs["self_reference"] = True
            attrs_json = json.dumps(edge_attrs)
        else:
            attrs_json = json.dumps(attrs)

        return (
            edge_id,
            source_id,
            target_id,
            scope or "local",
            relationship,
            get_float(attrs, "weight", 1.0),  # Type-safe extraction
            attrs_json,
            datetime.now(timezone.utc).isoformat(),
        )

    def _build_edge_data(
        self, normalized_edges: List[Tuple[str, str, str, JSONDict, Optional[str]]], existing_nodes: set[str]
    ) -> List[Tuple[str, str, str, str, str, float, str, str]]:
        """Build edge data for batch insertion."""
        edge_data = []

        for source_id, target_id, relationship, attrs, scope_opt in normalized_edges:
            scope = scope_opt or "unknown"

            # Skip edges if nodes don't exist
            if source_id not in existing_nodes or target_id not in existing_nodes:
                continue

            edge_record = self._build_edge_record(source_id, target_id, relationship, attrs, scope)
            edge_data.append(edge_record)

        return edge_data

    def create_edges(self, edges: List[EdgeSpecification] | List[Tuple[GraphNode, GraphNode, str, JSONDict]]) -> int:
        """
        Create multiple edges from a list of edge specifications.

        Args:
            edges: List of EdgeSpecification objects or tuples of (source, target, relationship, attributes)

        Returns:
            Number of edges created
        """
        if not edges:
            return 0

        edges_created = 0

        try:
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Normalize edges to common format
                if edges and isinstance(edges[0], EdgeSpecification):
                    normalized_edges, node_ids_to_check = self._normalize_edge_specifications(
                        cast(List[EdgeSpecification], edges)
                    )
                else:
                    normalized_edges, node_ids_to_check = self._normalize_edge_tuples(
                        cast(List[Tuple[GraphNode, GraphNode, str, JSONDict]], edges)
                    )

                # Check which nodes already exist
                placeholders = ",".join(["?"] * len(node_ids_to_check))
                cursor.execute(
                    f"""
                    SELECT node_id FROM graph_nodes
                    WHERE node_id IN ({placeholders})
                """,
                    list(node_ids_to_check),
                )

                existing_nodes = {row["node_id"] for row in cursor.fetchall()}

                # Create missing nodes (channels only)
                missing_nodes = node_ids_to_check - existing_nodes
                self._create_missing_nodes(missing_nodes, existing_nodes)

                # Build edge data for insertion
                edge_data = self._build_edge_data(normalized_edges, existing_nodes)

                if edge_data:
                    edges_created = batch_insert_edges_if_not_exist(edge_data, db_path=self._db_path)
                    logger.info(f"Created {edges_created} edges from batch")

        except Exception as e:
            logger.error(f"Failed to create edges: {e}")

        return edges_created

    def update_next_period_edges(self, period_start: datetime, summaries: List[GraphNode]) -> int:
        """
        Update next period's summaries to point back to these summaries.
        Called when we create summaries for a period that already has a next period.

        Args:
            period_start: Start of current period
            summaries: Summaries just created for current period

        Returns:
            Number of edges created
        """
        if not summaries:
            return 0

        edges_created = 0

        try:
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()
                adapter = get_adapter()
                ph = adapter.placeholder()

                # Calculate next period
                next_period = period_start + timedelta(hours=6)
                next_period_id = next_period.strftime("%Y%m%d_%H")

                for summary in summaries:
                    # Extract summary type from ID
                    parts = summary.id.split("_")
                    if len(parts) >= 2:
                        summary_type = f"{parts[0]}_{parts[1]}"
                        next_summary_id = f"{summary_type}_{next_period_id}"

                        # Check if next summary exists
                        cursor.execute(
                            f"""
                            SELECT node_id FROM graph_nodes
                            WHERE node_id = {ph}
                            LIMIT 1
                        """,
                            (next_summary_id,),
                        )

                        if cursor.fetchone():
                            # Create edge from current to next
                            edge_id = f"edge_{uuid4().hex[:8]}"
                            created = insert_edge_if_not_exists(
                                edge_id=edge_id,
                                source_node_id=summary.id,
                                target_node_id=next_summary_id,
                                scope=summary.scope.value if hasattr(summary.scope, "value") else str(summary.scope),
                                relationship="TEMPORAL_NEXT",
                                weight=1.0,
                                attributes={"direction": "forward", "context": "Next period in sequence"},
                                db_path=self._db_path,
                            )

                            if created:
                                edges_created += 1

                                # Also create backward edge from next to current
                                edge_id_back = f"edge_{uuid4().hex[:8]}"
                                created_back = insert_edge_if_not_exists(
                                    edge_id=edge_id_back,
                                    source_node_id=next_summary_id,
                                    target_node_id=summary.id,
                                    scope=(
                                        summary.scope.value if hasattr(summary.scope, "value") else str(summary.scope)
                                    ),
                                    relationship="TEMPORAL_PREV",
                                    weight=1.0,
                                    attributes={"direction": "backward", "context": "Previous period in sequence"},
                                    db_path=self._db_path,
                                )

                                if created_back:
                                    edges_created += 1

                conn.commit()

                if edges_created > 0:
                    logger.info(f"Created {edges_created} edges to next period summaries")

        except Exception as e:
            logger.error(f"Failed to update next period edges: {e}")

        return edges_created
