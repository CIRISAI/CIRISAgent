"""
Edge management for TSDB consolidation.

Handles proper creation of edges in the graph_edges table instead of storing as nodes.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set, Tuple
from uuid import uuid4

from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope
from ciris_engine.logic.persistence.db.core import get_db_connection

logger = logging.getLogger(__name__)


class EdgeManager:
    """Manages proper edge creation in the graph."""
    
    def __init__(self) -> None:
        """Initialize edge manager."""
        pass
    
    async def create_edges(
        self,
        edges: List[Tuple[GraphNode, GraphNode, str, Dict[str, Any]]]
    ) -> int:
        """
        Create multiple edges in the graph.
        
        Args:
            edges: List of (source_node, target_node, relationship, attributes) tuples
            
        Returns:
            Number of edges created
        """
        if not edges:
            return 0
        
        edges_created = 0
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                for source_node, target_node, relationship, attrs in edges:
                    edge_id = str(uuid4())
                    
                    cursor.execute("""
                        INSERT INTO graph_edges (
                            edge_id, source_node_id, target_node_id, scope,
                            relationship, weight, attributes_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        edge_id,
                        source_node.id,
                        target_node.id,
                        GraphScope.LOCAL.value,
                        relationship,
                        attrs.get('weight', 1.0),
                        json.dumps(attrs),
                        datetime.utcnow().isoformat()
                    ))
                    edges_created += 1
                
                conn.commit()
                logger.info(f"Created {edges_created} edges")
                
        except Exception as e:
            logger.error(f"Failed to create edges: {e}")
            
        return edges_created
    
    async def create_summary_to_nodes_edges(
        self,
        summary_node: GraphNode,
        target_nodes: List[GraphNode],
        relationship: str = "SUMMARIZES",
        context: Optional[str] = None
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
            return 0
        
        edges_created = 0
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Batch insert edges
                edge_data = []
                for target_node in target_nodes:
                    edge_id = f"edge_{uuid4().hex[:8]}"
                    edge_data.append((
                        edge_id,
                        summary_node.id,
                        target_node.id,
                        summary_node.scope.value if summary_node.scope else 'local',
                        relationship,
                        1.0,  # Default weight
                        f'{{"context": "{context or "Summary edge"}"}}',
                        datetime.utcnow().isoformat()
                    ))
                
                # Insert edges
                cursor.executemany("""
                    INSERT INTO graph_edges 
                    (edge_id, source_node_id, target_node_id, scope, 
                     relationship, weight, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, edge_data)
                
                edges_created = cursor.rowcount
                conn.commit()
                
                logger.info(f"Created {edges_created} edges from {summary_node.id} to target nodes")
        
        except Exception as e:
            logger.error(f"Failed to create summary edges: {e}")
        
        return edges_created
    
    async def create_cross_summary_edges(
        self,
        summaries: List[GraphNode],
        period_start: datetime
    ) -> int:
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
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                edge_data = []
                
                # Create edges between each pair of summaries
                for i in range(len(summaries)):
                    for j in range(i + 1, len(summaries)):
                        source = summaries[i]
                        target = summaries[j]
                        
                        # Determine relationship based on node types
                        relationship = self._determine_cross_summary_relationship(
                            source.id, target.id
                        )
                        
                        edge_id = f"edge_{uuid4().hex[:8]}"
                        edge_data.append((
                            edge_id,
                            source.id,
                            target.id,
                            source.scope.value if source.scope else 'local',
                            relationship,
                            1.0,
                            f'{{"context": "Same period correlation for {period_start.isoformat()}"}}',
                            datetime.utcnow().isoformat()
                        ))
                
                if edge_data:
                    cursor.executemany("""
                        INSERT INTO graph_edges 
                        (edge_id, source_node_id, target_node_id, scope, 
                         relationship, weight, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, edge_data)
                    
                    edges_created = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"Created {edges_created} cross-summary edges for period {period_start}")
        
        except Exception as e:
            logger.error(f"Failed to create cross-summary edges: {e}")
        
        return edges_created
    
    async def create_temporal_edges(
        self,
        current_summary: GraphNode,
        previous_summary_id: Optional[str]
    ) -> int:
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
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Step 1: Create TEMPORAL_NEXT from current to itself (marking as latest)
                edge_id_self = f"edge_{uuid4().hex[:8]}"
                cursor.execute("""
                    INSERT INTO graph_edges 
                    (edge_id, source_node_id, target_node_id, scope, 
                     relationship, weight, attributes_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    edge_id_self,
                    current_summary.id,
                    current_summary.id,  # Points to itself
                    current_summary.scope.value if hasattr(current_summary.scope, 'value') else 'local',
                    "TEMPORAL_NEXT",
                    1.0,
                    json.dumps({"is_latest": True, "context": "Current latest summary"}),
                    datetime.utcnow().isoformat()
                ))
                edges_created += 1
                
                if previous_summary_id:
                    # Step 2a: Update previous TEMPORAL_NEXT to point to current
                    # First, delete the self-referencing edge
                    cursor.execute("""
                        DELETE FROM graph_edges
                        WHERE source_node_id = ?
                          AND target_node_id = ?
                          AND relationship = 'TEMPORAL_NEXT'
                    """, (previous_summary_id, previous_summary_id))
                    
                    # Then create new edge pointing to current
                    edge_id_forward = f"edge_{uuid4().hex[:8]}"
                    cursor.execute("""
                        INSERT INTO graph_edges 
                        (edge_id, source_node_id, target_node_id, scope, 
                         relationship, weight, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        edge_id_forward,
                        previous_summary_id,
                        current_summary.id,
                        current_summary.scope.value if hasattr(current_summary.scope, 'value') else 'local',
                        "TEMPORAL_NEXT",
                        1.0,
                        json.dumps({"is_latest": False, "context": "Points to next period"}),
                        datetime.utcnow().isoformat()
                    ))
                    edges_created += 1
                    
                    # Step 2b: Create TEMPORAL_PREV from current to previous
                    edge_id_backward = f"edge_{uuid4().hex[:8]}"
                    cursor.execute("""
                        INSERT INTO graph_edges 
                        (edge_id, source_node_id, target_node_id, scope, 
                         relationship, weight, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        edge_id_backward,
                        current_summary.id,
                        previous_summary_id,
                        current_summary.scope.value if hasattr(current_summary.scope, 'value') else 'local',
                        "TEMPORAL_PREV",
                        1.0,
                        json.dumps({"context": "Points to previous period"}),
                        datetime.utcnow().isoformat()
                    ))
                    edges_created += 1
                
                conn.commit()
                
                logger.debug(f"Created temporal edges for {current_summary.id} (previous: {previous_summary_id or 'None'})")
                return edges_created
        
        except Exception as e:
            logger.error(f"Failed to create temporal edges: {e}")
            return 0
    
    async def create_concept_edges(
        self,
        summary_nodes: List[GraphNode],
        concept_nodes: List[GraphNode],
        period_label: str
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
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                edge_data = []
                
                # Create edges from each summary to each concept
                for summary in summary_nodes:
                    for concept in concept_nodes:
                        edge_id = f"edge_{uuid4().hex[:8]}"
                        edge_data.append((
                            edge_id,
                            summary.id,
                            concept.id,
                            summary.scope.value if summary.scope else 'local',
                            "PERIOD_CONCEPT",
                            0.8,  # Slightly lower weight for indirect relationships
                            f'{{"context": "Concept created during {period_label}"}}',
                            datetime.utcnow().isoformat()
                        ))
                
                if edge_data:
                    cursor.executemany("""
                        INSERT INTO graph_edges 
                        (edge_id, source_node_id, target_node_id, scope, 
                         relationship, weight, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, edge_data)
                    
                    edges_created = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"Created {edges_created} concept edges for period {period_label}")
        
        except Exception as e:
            logger.error(f"Failed to create concept edges: {e}")
        
        return edges_created
    
    async def get_previous_summary_id(
        self,
        node_type_prefix: str,
        previous_period_id: str
    ) -> Optional[str]:
        """
        Get the ID of a summary node from the previous period.
        
        Args:
            node_type_prefix: Prefix like "tsdb_summary", "conversation_summary"
            previous_period_id: Period ID like "20250702_00"
            
        Returns:
            Node ID if found, None otherwise
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Look for summary node with matching ID pattern
                node_id_pattern = f"{node_type_prefix}_{previous_period_id}"
                
                cursor.execute("""
                    SELECT node_id 
                    FROM graph_nodes
                    WHERE node_id = ?
                    LIMIT 1
                """, (node_id_pattern,))
                
                row = cursor.fetchone()
                return row['node_id'] if row else None
        
        except Exception as e:
            logger.error(f"Failed to find previous summary: {e}")
            return None
    
    def _determine_cross_summary_relationship(
        self,
        source_id: str,
        target_id: str
    ) -> str:
        """
        Determine the relationship type between two summary nodes.
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
            
        Returns:
            Relationship type string
        """
        # Extract summary types from IDs
        source_type = source_id.split('_')[0]
        target_type = target_id.split('_')[0]
        
        # Define meaningful relationships
        relationships = {
            ('conversation', 'trace'): "DRIVES_PROCESSING",
            ('trace', 'tsdb'): "GENERATES_METRICS",
            ('tsdb', 'conversation'): "IMPACTS_QUALITY",
            ('audit', 'trace'): "SECURES_EXECUTION",
            ('trace', 'audit'): "CREATES_TRAIL",
            ('conversation', 'task'): "INITIATES_TASKS",
            ('task', 'tsdb'): "CONSUMES_RESOURCES"
        }
        
        # Look up specific relationship or use default
        return relationships.get(
            (source_type, target_type),
            "TEMPORAL_CORRELATION"
        )
    
    async def create_user_participation_edges(
        self,
        conversation_summary: GraphNode,
        participant_data: Dict[str, Dict[str, Any]],
        period_label: str
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
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                edge_data = []
                
                for user_id, metrics in participant_data.items():
                    user_node_id = f"user_{user_id}"
                    
                    # Check if user node exists
                    cursor.execute("""
                        SELECT node_id FROM graph_nodes 
                        WHERE node_type = 'user' AND node_id = ?
                        LIMIT 1
                    """, (user_node_id,))
                    
                    user_exists = cursor.fetchone() is not None
                    
                    # Create user node if it doesn't exist
                    if not user_exists and metrics.get('author_name'):
                        logger.info(f"Creating user node for {user_id} ({metrics['author_name']})")
                        
                        user_attributes = {
                            'user_id': user_id,
                            'display_name': metrics['author_name'],
                            'first_seen': datetime.utcnow().isoformat(),
                            'created_by': 'tsdb_consolidation',
                            'channels': metrics['channels']
                        }
                        
                        cursor.execute("""
                            INSERT INTO graph_nodes 
                            (node_id, scope, node_type, attributes_json, 
                             version, updated_by, updated_at, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            user_node_id,
                            'local',
                            'user',
                            json.dumps(user_attributes),
                            1,
                            'tsdb_consolidation',
                            datetime.utcnow().isoformat(),
                            datetime.utcnow().isoformat()
                        ))
                        user_exists = True
                    
                    if user_exists:
                        # Create edge from summary to user
                        edge_id = f"edge_{uuid4().hex[:8]}"
                        message_count = metrics['message_count']
                        
                        # Weight based on participation level (normalized 0-1)
                        # More messages = higher weight
                        weight = min(1.0, message_count / 100.0)
                        
                        attributes = {
                            "context": f"Participated in conversations during {period_label}",
                            "message_count": message_count,
                            "channels": metrics['channels'],
                            "author_name": metrics.get('author_name')
                        }
                        
                        edge_data.append((
                            edge_id,
                            conversation_summary.id,
                            f"user_{user_id}",
                            conversation_summary.scope.value if conversation_summary.scope else 'local',
                            "INVOLVED_USER",
                            weight,
                            json.dumps(attributes),
                            datetime.utcnow().isoformat()
                        ))
                    else:
                        logger.debug(f"User node not found for user_id: {user_id}")
                
                if edge_data:
                    cursor.executemany("""
                        INSERT INTO graph_edges 
                        (edge_id, source_node_id, target_node_id, scope, 
                         relationship, weight, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, edge_data)
                    
                    edges_created = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"Created {edges_created} user participation edges for {conversation_summary.id}")
        
        except Exception as e:
            logger.error(f"Failed to create user participation edges: {e}")
        
        return edges_created
    
    async def cleanup_orphaned_edges(self) -> int:
        """
        Remove edges where source or target nodes no longer exist.
        
        Returns:
            Number of edges deleted
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Delete edges with missing nodes
                cursor.execute("""
                    DELETE FROM graph_edges
                    WHERE source_node_id NOT IN (SELECT node_id FROM graph_nodes)
                       OR target_node_id NOT IN (SELECT node_id FROM graph_nodes)
                """)
                
                deleted = cursor.rowcount
                conn.commit()
                
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} orphaned edges")
                
                return deleted
        
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned edges: {e}")
            return 0
    
    async def create_edges(
        self,
        edges: List[Tuple[GraphNode, GraphNode, str, Dict[str, Any]]]
    ) -> int:
        """
        Create multiple edges from a list of edge specifications.
        
        Args:
            edges: List of (source_node, target_node, relationship, attributes) tuples
            
        Returns:
            Number of edges created
        """
        if not edges:
            return 0
        
        edges_created = 0
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                edge_data = []
                
                for source_node, target_node, relationship, attrs in edges:
                    # Handle self-references (where we store data in attributes)
                    if source_node.id == target_node.id:
                        # For self-references, we create edges with special attributes
                        edge_id = f"edge_{uuid4().hex[:8]}"
                        
                        # Merge provided attributes with edge metadata
                        edge_attrs = {"self_reference": True}
                        edge_attrs.update(attrs)
                        
                        edge_data.append((
                            edge_id,
                            source_node.id,
                            target_node.id,
                            source_node.scope.value if hasattr(source_node.scope, 'value') else str(source_node.scope),
                            relationship,
                            1.0,  # Default weight
                            json.dumps(edge_attrs),
                            datetime.utcnow().isoformat()
                        ))
                    else:
                        # Normal edge between different nodes
                        edge_id = f"edge_{uuid4().hex[:8]}"
                        edge_data.append((
                            edge_id,
                            source_node.id,
                            target_node.id,
                            source_node.scope.value if hasattr(source_node.scope, 'value') else str(source_node.scope),
                            relationship,
                            1.0,  # Default weight
                            json.dumps(attrs) if attrs else '{}',
                            datetime.utcnow().isoformat()
                        ))
                
                if edge_data:
                    cursor.executemany("""
                        INSERT INTO graph_edges 
                        (edge_id, source_node_id, target_node_id, scope, 
                         relationship, weight, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, edge_data)
                    
                    edges_created = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"Created {edges_created} edges from batch")
        
        except Exception as e:
            logger.error(f"Failed to create edges: {e}")
        
        return edges_created
    
    async def update_next_period_edges(
        self,
        period_start: datetime,
        summaries: List[GraphNode]
    ) -> int:
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
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Calculate next period
                next_period = period_start + timedelta(hours=6)
                next_period_id = next_period.strftime('%Y%m%d_%H')
                
                for summary in summaries:
                    # Extract summary type from ID
                    parts = summary.id.split('_')
                    if len(parts) >= 2:
                        summary_type = f"{parts[0]}_{parts[1]}"
                        next_summary_id = f"{summary_type}_{next_period_id}"
                        
                        # Check if next summary exists
                        cursor.execute("""
                            SELECT node_id FROM graph_nodes
                            WHERE node_id = ?
                            LIMIT 1
                        """, (next_summary_id,))
                        
                        if cursor.fetchone():
                            # Create edge from current to next
                            edge_id = f"edge_{uuid4().hex[:8]}"
                            cursor.execute("""
                                INSERT OR IGNORE INTO graph_edges 
                                (edge_id, source_node_id, target_node_id, scope, 
                                 relationship, weight, attributes_json, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                edge_id,
                                summary.id,
                                next_summary_id,
                                summary.scope.value if hasattr(summary.scope, 'value') else str(summary.scope),
                                "TEMPORAL_NEXT",
                                1.0,
                                json.dumps({"direction": "forward", "context": "Next period in sequence"}),
                                datetime.utcnow().isoformat()
                            ))
                            
                            if cursor.rowcount > 0:
                                edges_created += 1
                                
                                # Also create backward edge from next to current
                                edge_id_back = f"edge_{uuid4().hex[:8]}"
                                cursor.execute("""
                                    INSERT OR IGNORE INTO graph_edges 
                                    (edge_id, source_node_id, target_node_id, scope, 
                                     relationship, weight, attributes_json, created_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    edge_id_back,
                                    next_summary_id,
                                    summary.id,
                                    summary.scope.value if hasattr(summary.scope, 'value') else str(summary.scope),
                                    "TEMPORAL_PREV",
                                    1.0,
                                    json.dumps({"direction": "backward", "context": "Previous period in sequence"}),
                                    datetime.utcnow().isoformat()
                                ))
                                
                                if cursor.rowcount > 0:
                                    edges_created += 1
                
                conn.commit()
                
                if edges_created > 0:
                    logger.info(f"Created {edges_created} edges to next period summaries")
                    
        except Exception as e:
            logger.error(f"Failed to update next period edges: {e}")
            
        return edges_created