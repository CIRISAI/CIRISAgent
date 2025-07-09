"""
Audit consolidation for security and compliance tracking.

Consolidates AUDIT_ENTRY nodes into AuditSummaryNode with hash chain verification.
"""

import logging
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus
from ciris_engine.logic.buses.memory_bus import MemoryBus

logger = logging.getLogger(__name__)


class AuditConsolidator:
    """Consolidates audit entries into summaries with cryptographic hashing."""
    
    def __init__(self, memory_bus: Optional[MemoryBus] = None):
        """
        Initialize audit consolidator.
        
        Args:
            memory_bus: Memory bus for storing results
        """
        self._memory_bus = memory_bus
    
    async def consolidate(
        self,
        period_start: datetime,
        period_end: datetime,
        period_label: str,
        audit_nodes: List[GraphNode]
    ) -> Optional[GraphNode]:
        """
        Consolidate audit entries into a summary with hash verification.
        
        Note: This only consolidates the graph representation. The full audit trail
        with cryptographic hash chain remains intact in the audit database.
        
        Args:
            period_start: Start of consolidation period
            period_end: End of consolidation period
            period_label: Human-readable period label
            audit_nodes: List of AUDIT_ENTRY nodes from graph
            
        Returns:
            AuditSummaryNode as GraphNode if successful
        """
        if not audit_nodes:
            logger.info(f"No audit entries found for period {period_start} - creating empty summary")
        
        logger.info(f"Consolidating {len(audit_nodes)} audit entries")
        
        # Collect metrics and event IDs
        event_ids = []
        events_by_type: Dict[str, int] = defaultdict(int)
        events_by_actor: Dict[str, int] = defaultdict(int)
        events_by_service: Dict[str, int] = defaultdict(int)
        failed_auth_attempts = 0
        permission_denials = 0
        emergency_shutdowns = 0
        config_changes = 0
        security_events = []
        high_severity_events = []
        
        # Sort nodes by timestamp for chronological ordering
        sorted_nodes = sorted(audit_nodes, key=lambda n: n.updated_at or datetime.utcnow())
        
        first_event_id = None
        last_event_id = None
        
        for i, node in enumerate(sorted_nodes):
            # Extract event ID from node ID (format: "audit_<event_id>")
            event_id = node.id.replace('audit_', '') if node.id.startswith('audit_') else node.id
            event_ids.append(event_id)
            
            if i == 0:
                first_event_id = event_id
            if i == len(sorted_nodes) - 1:
                last_event_id = event_id
            
            # Extract attributes
            attrs = node.attributes
            if not isinstance(attrs, dict):
                attrs = attrs.model_dump() if hasattr(attrs, 'model_dump') else {}
            
            # Extract key fields
            action = attrs.get('action', 'unknown')
            actor = attrs.get('actor', 'unknown')
            timestamp = attrs.get('timestamp', attrs.get('created_at', ''))
            
            # Parse context data
            context = attrs.get('context', {})
            if isinstance(context, str):
                try:
                    context = json.loads(context)
                except:
                    context = {}
            
            service_name = context.get('service_name', 'unknown')
            additional_data = context.get('additional_data', {})
            
            event_type = additional_data.get('event_type', action)
            severity = additional_data.get('severity', 'info')
            outcome = additional_data.get('outcome', 'success')
            
            # Track metrics
            events_by_type[event_type] += 1
            events_by_actor[actor] += 1
            events_by_service[service_name] += 1
            
            # Identify security events
            is_security_event = False
            
            # Failed authentication attempts
            if ('AUTH_FAILURE' in event_type.upper() or 
                (outcome == 'failure' and 'auth' in event_type.lower())):
                failed_auth_attempts += 1
                is_security_event = True
            
            # Permission denials
            elif ('PERMISSION_DENIED' in event_type.upper() or 
                  ('permission' in event_type.lower() and outcome == 'failure')):
                permission_denials += 1
                is_security_event = True
            
            # Emergency shutdowns
            elif 'EMERGENCY_SHUTDOWN' in event_type.upper():
                emergency_shutdowns += 1
                is_security_event = True
            
            # Config changes
            elif any(cfg in event_type.upper() for cfg in ['CONFIG_CREATE', 'CONFIG_UPDATE', 'CONFIG_DELETE']):
                config_changes += 1
            
            # Track security events
            if is_security_event:
                security_events.append({
                    'event_id': event_id,
                    'timestamp': timestamp,
                    'event_type': event_type,
                    'actor': actor,
                    'outcome': outcome
                })
            
            # Track high severity events
            if severity in ['error', 'critical', 'high']:
                high_severity_events.append({
                    'event_id': event_id,
                    'timestamp': timestamp,
                    'event_type': event_type,
                    'severity': severity,
                    'actor': actor
                })
        
        # Compute audit hash (SHA-256 of concatenated event IDs)
        audit_hash = self._compute_audit_hash(event_ids)
        
        # Calculate security score (0-100, lower is better)
        total_events = len(audit_nodes)
        security_issues = failed_auth_attempts + permission_denials + emergency_shutdowns
        security_score = min(100, (security_issues / total_events * 100) if total_events > 0 else 0)
        
        # Create summary data
        summary_data = {
            'id': f"audit_summary_{period_start.strftime('%Y%m%d_%H')}",
            'period_start': period_start.isoformat(),
            'period_end': period_end.isoformat(),
            'period_label': period_label,
            'audit_hash': audit_hash,
            'hash_algorithm': 'sha256',
            'total_audit_events': len(audit_nodes),
            'events_by_type': dict(events_by_type),
            'events_by_actor': dict(events_by_actor),
            'events_by_service': dict(events_by_service),
            'failed_auth_attempts': failed_auth_attempts,
            'permission_denials': permission_denials,
            'emergency_shutdowns': emergency_shutdowns,
            'config_changes': config_changes,
            'security_score': security_score,
            'security_events': security_events[:10],  # Keep top 10
            'high_severity_events': high_severity_events[:10],  # Keep top 10
            'first_event_id': first_event_id,
            'last_event_id': last_event_id,
            'source_node_count': len(audit_nodes),
            'created_at': period_end.isoformat(),
            'updated_at': period_end.isoformat()
        }
        
        # Create GraphNode
        summary_node = GraphNode(
            id=str(summary_data['id']),
            type=NodeType.AUDIT_SUMMARY,
            scope=GraphScope.LOCAL,
            attributes=summary_data,
            updated_by="tsdb_consolidation",
            updated_at=period_end  # Use period end as timestamp
        )
        
        # Store summary
        if self._memory_bus:
            result = await self._memory_bus.memorize(node=summary_node)
            if result.status != MemoryOpStatus.OK:
                logger.error(f"Failed to store audit summary: {result.error}")
                return None
        else:
            logger.warning("No memory bus available - summary not stored")
        
        return summary_node
    
    def get_edges(
        self,
        summary_node: GraphNode,
        audit_nodes: List[GraphNode]
    ) -> List[Tuple[GraphNode, GraphNode, str, Dict[str, Any]]]:
        """
        Get edges to create for audit summary.
        
        Returns edges from summary to:
        - High severity audit events
        - Security-related events
        - First and last events in period
        """
        edges = []
        
        # Sort nodes by timestamp
        sorted_nodes = sorted(audit_nodes, key=lambda n: n.updated_at or datetime.utcnow())
        
        # Link to first and last events (self-reference with data in attributes)
        if sorted_nodes:
            # First event - store data in edge attributes
            first_node = sorted_nodes[0]
            first_attrs = first_node.attributes if isinstance(first_node.attributes, dict) else {}
            edges.append((
                summary_node,
                summary_node,  # Self-reference
                'FIRST_AUDIT_EVENT',
                {
                    'event_order': 'first',
                    'audit_node_id': first_node.id,
                    'event_type': first_attrs.get('event_type', 'unknown'),
                    'severity': first_attrs.get('severity', 'unknown'),
                    'target_entity': first_attrs.get('target_entity'),
                    'timestamp': first_node.updated_at.isoformat() if first_node.updated_at else None
                }
            ))
            
            # Last event - store data in edge attributes
            if len(sorted_nodes) > 1:
                last_node = sorted_nodes[-1]
                last_attrs = last_node.attributes if isinstance(last_node.attributes, dict) else {}
                edges.append((
                    summary_node,
                    summary_node,  # Self-reference
                    'LAST_AUDIT_EVENT',
                    {
                        'event_order': 'last',
                        'audit_node_id': last_node.id,
                        'event_type': last_attrs.get('event_type', 'unknown'),
                        'severity': last_attrs.get('severity', 'unknown'),
                        'target_entity': last_attrs.get('target_entity'),
                        'timestamp': last_node.updated_at.isoformat() if last_node.updated_at else None
                    }
                ))
        
        # Link to security events
        security_count = 0
        for node in audit_nodes:
            attrs = node.attributes
            if isinstance(attrs, dict):
                event_type = attrs.get('event_type', '').lower()
                severity = attrs.get('severity', '').lower()
                
                # Check if security-related
                is_security = any(keyword in event_type for keyword in ['auth', 'access', 'permission', 'security'])
                is_high_severity = severity in ['high', 'critical', 'error']
                
                if (is_security or is_high_severity) and security_count < 10:
                    edges.append((
                        summary_node,
                        summary_node,  # Self-reference with audit data
                        'SECURITY_AUDIT_EVENT',
                        {
                            'audit_node_id': node.id,
                            'event_type': attrs.get('event_type', 'unknown'),
                            'severity': severity,
                            'target_entity': attrs.get('target_entity'),
                            'is_security': is_security,
                            'timestamp': node.updated_at.isoformat() if node.updated_at else None
                        }
                    ))
                    security_count += 1
        
        return edges
    
    def _compute_audit_hash(self, event_ids: List[str]) -> str:
        """
        Compute SHA-256 hash of event IDs for audit integrity.
        
        Args:
            event_ids: List of event IDs in chronological order
            
        Returns:
            Hex digest of SHA-256 hash
        """
        # Concatenate event IDs with delimiter
        combined = '|'.join(event_ids)
        
        # Compute SHA-256 hash
        hash_obj = hashlib.sha256()
        hash_obj.update(combined.encode('utf-8'))
        
        return hash_obj.hexdigest()