"""
Memory consolidator for TSDB consolidation.

This consolidator creates edges from summary nodes to important memory nodes
(concepts, identity, config) that were created or updated in the consolidation period.
It does NOT create a summary node.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from ciris_engine.schemas.services.graph_core import GraphNode, NodeType
from ciris_engine.logic.buses.memory_bus import MemoryBus

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """
    Creates edges from summary nodes to important memory nodes.
    """
    
    # Memory node types to track
    MEMORY_NODE_TYPES = [
        'concept',
        'identity',
        'identity_snapshot',
        'config',
        'behavioral',
        'social'
    ]
    
    def __init__(self, memory_bus: Optional[MemoryBus] = None):
        """
        Initialize memory consolidator.
        
        Args:
            memory_bus: Memory bus (not used, kept for interface compatibility)
        """
        self._memory_bus = memory_bus
    
    def consolidate(
        self,
        period_start: datetime,
        period_end: datetime,
        period_label: str,
        nodes_by_type: Dict[str, List[GraphNode]],
        summary_nodes: List[GraphNode]
    ) -> List[Tuple[GraphNode, GraphNode, str, dict]]:
        """
        Create edges from summary nodes to important memory nodes in the period.
        
        This does NOT create a summary node. Instead, it identifies important
        memory nodes (concepts, identity, config) and returns edges that should
        be created from the summary nodes to these memory nodes.
        
        Args:
            period_start: Start of consolidation period
            period_end: End of consolidation period
            period_label: Human-readable period label
            nodes_by_type: Dict mapping node types to lists of nodes
            summary_nodes: List of summary nodes that need edges
            
        Returns:
            List of (source_node, target_node, edge_type, attributes) tuples
        """
        edges: List[Tuple[GraphNode, GraphNode, str, dict]] = []
        
        # Filter for memory node types
        memory_nodes = {}
        total_memory_nodes = 0
        
        for node_type in self.MEMORY_NODE_TYPES:
            if node_type in nodes_by_type:
                nodes = nodes_by_type[node_type]
                if nodes:
                    memory_nodes[node_type] = nodes
                    total_memory_nodes += len(nodes)
        
        if not memory_nodes:
            logger.info(f"No memory nodes found for period {period_start} to {period_end}")
            return edges
        
        logger.info(f"Creating edges to {total_memory_nodes} memory nodes across {len(memory_nodes)} types")
        
        # Create edges from each summary node to relevant memory nodes
        for summary_node in summary_nodes:
            # Determine which memory nodes are relevant to this summary type
            if summary_node.type == NodeType.TSDB_SUMMARY:
                # TSDB summaries link to configs that affect metrics
                if 'config' in memory_nodes:
                    for config_node in memory_nodes['config']:
                        if self._is_metrics_config(config_node):
                            edges.append((
                                summary_node,
                                config_node,
                                'METRICS_CONFIG',
                                {
                                    'period': period_label,
                                    'config_type': self._get_config_type(config_node)
                                }
                            ))
            
            elif summary_node.type == NodeType.CONVERSATION_SUMMARY:
                # Conversation summaries link to concepts discussed
                if 'concept' in memory_nodes:
                    for concept_node in memory_nodes['concept']:
                        edges.append((
                            summary_node,
                            concept_node,
                            'DISCUSSED_CONCEPT',
                            {
                                'period': period_label,
                                'relevance': self._calculate_relevance(concept_node, summary_node)
                            }
                        ))
                
                # Link to social nodes if present
                if 'social' in memory_nodes:
                    for social_node in memory_nodes['social']:
                        edges.append((
                            summary_node,
                            social_node,
                            'SOCIAL_CONTEXT',
                            {
                                'period': period_label
                            }
                        ))
            
            elif summary_node.type == NodeType.TRACE_SUMMARY:
                # Trace summaries link to behavioral patterns
                if 'behavioral' in memory_nodes:
                    for behavioral_node in memory_nodes['behavioral']:
                        edges.append((
                            summary_node,
                            behavioral_node,
                            'BEHAVIORAL_PATTERN',
                            {
                                'period': period_label
                            }
                        ))
            
            elif summary_node.type == NodeType.AUDIT_SUMMARY:
                # Audit summaries link to identity changes
                if 'identity' in memory_nodes:
                    for identity_node in memory_nodes['identity']:
                        edges.append((
                            summary_node,
                            identity_node,
                            'IDENTITY_AUDIT',
                            {
                                'period': period_label,
                                'change_type': self._get_identity_change_type(identity_node)
                            }
                        ))
                
                # Also link to identity snapshots
                if 'identity_snapshot' in memory_nodes:
                    for snapshot_node in memory_nodes['identity_snapshot']:
                        edges.append((
                            summary_node,
                            snapshot_node,
                            'IDENTITY_SNAPSHOT_REF',
                            {
                                'period': period_label
                            }
                        ))
            
            elif summary_node.type == NodeType.TASK_SUMMARY:
                # Task summaries link to concepts used in task processing
                if 'concept' in memory_nodes:
                    for concept_node in memory_nodes['concept']:
                        if self._is_task_relevant_concept(concept_node):
                            edges.append((
                                summary_node,
                                concept_node,
                                'TASK_CONCEPT',
                                {
                                    'period': period_label
                                }
                            ))
        
        logger.info(f"Created {len(edges)} edges to memory nodes")
        return edges
    
    def _is_metrics_config(self, config_node: GraphNode) -> bool:
        """Check if config node relates to metrics/telemetry."""
        attrs = config_node.attributes
        if isinstance(attrs, dict):
            # Check both config_type and key fields
            config_type = attrs.get('config_type', '').lower()
            config_key = attrs.get('key', '').lower()
            check_value = config_type + ' ' + config_key
            return any(keyword in check_value for keyword in ['metric', 'telemetry', 'monitoring', 'resource', 'log_level'])
        return False
    
    def _is_task_relevant_concept(self, concept_node: GraphNode) -> bool:
        """Check if concept is relevant to task processing."""
        attrs = concept_node.attributes
        if isinstance(attrs, dict):
            concept_type = attrs.get('concept_type', '').lower()
            return any(keyword in concept_type for keyword in ['task', 'handler', 'action', 'processing'])
        return True  # Default to including all concepts
    
    def _calculate_relevance(self, concept_node: GraphNode, summary_node: GraphNode) -> float:
        """Calculate relevance score between concept and summary."""
        # Simple relevance based on whether concept was updated in this period
        return 1.0 if concept_node.updated_at else 0.5
    
    def _get_identity_change_type(self, identity_node: GraphNode) -> str:
        """Determine the type of identity change."""
        attrs = identity_node.attributes
        if isinstance(attrs, dict):
            if attrs.get('purpose_changed'):
                return 'purpose_update'
            elif attrs.get('capabilities_changed'):
                return 'capability_update'
            elif attrs.get('boundaries_changed'):
                return 'boundary_update'
        return 'general_update'
    
    def _get_config_type(self, config_node: GraphNode) -> str:
        """Determine the type of configuration."""
        attrs = config_node.attributes
        if isinstance(attrs, dict):
            # Try config_type first, then key
            config_type = attrs.get('config_type')
            if config_type and isinstance(config_type, str):
                return str(config_type)  # Ensure str type for mypy
            # Extract type from key if available
            key = attrs.get('key', '')
            if isinstance(key, str) and '.' in key:
                return key.split('.')[0]  # e.g., 'database' from 'database.main_db'
            return str(key) if key else 'general'
        return 'general'