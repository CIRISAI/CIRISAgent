# Graph Memory Service

The memory service is the heart of CIRIS's "Identity as Graph" architecture. It provides a unified interface for storing, retrieving, and managing all agent memories, with the fundamental principle that **identity IS the graph**.

## Overview

The memory service implements three core operations - MEMORIZE, RECALL, and FORGET - with sophisticated scope-based permissions and integrated audit trails. All agent knowledge, from simple facts to complex relationships, is stored as nodes and edges in a graph structure.

## Key Concepts

### Everything is a Memory

In CIRIS, there's no distinction between:
- Configuration settings
- Learned knowledge
- User preferences
- Behavioral patterns
- Identity attributes
- Temporal data (TSDB)

All are memories in the graph, differentiated only by their node types and relationships.

### Scope-Based Access Control

| Scope | Description | WA Approval Required | Use Cases |
|-------|-------------|---------------------|-----------|
| LOCAL | Agent-private memories | No | Personal learning, task context |
| ENVIRONMENT | Deployment-specific | Yes | Credentials, API endpoints |
| IDENTITY | Core identity changes | Yes | Capabilities, purpose, traits |

### Node Types

The system supports multiple typed nodes (see schemas/services/nodes.py):
- **IdentityNode**: Core agent identity (agent/identity)
- **ConfigNode**: Configuration values
- **AuditEntry**: Immutable audit records
- **TSDBSummary**: Time-series data summaries
- **IncidentNode**: Problems and resolutions
- **IdentitySnapshot**: Identity variance tracking

## Core Operations

### MEMORIZE

Adds new knowledge to the graph:

```python
# Store a user preference
# Store a node in the graph
node = GraphNode(
    id="user_preference_language",
    type=NodeType.CONFIG,
    scope=GraphScope.LOCAL,
    attributes={
        "content": "User prefers formal communication style",
        "confidence": 0.9,
        "observed_count": 5
    }
)
await memory_service.memorize(node)

# Store critical configuration (IDENTITY scope requires WA approval)
node = GraphNode(
    id="medical_protocol_override",
    type=NodeType.CONFIG,
    scope=GraphScope.IDENTITY,  # Triggers WA approval
    attributes={
        "content": "Allow emergency medication suggestions"
    }
)
await memory_service.memorize(node)
```

### RECALL

Retrieves memories with semantic search and graph traversal:

```python
# Simple node recall by ID
result = await memory_service.recall(
    MemoryQuery(
        node_id="user_preference_language",
        scope=GraphScope.LOCAL
    )
)

# Wildcard recall - get all nodes of a type
result = await memory_service.recall(
    MemoryQuery(
        node_id="*",  # Wildcard
        scope=GraphScope.LOCAL,
        type=NodeType.CONFIG
    )
)

# Recall with edge traversal
result = await memory_service.recall(
    MemoryQuery(
        node_id="medical_protocol",
        scope=GraphScope.LOCAL,
        include_edges=True,
        depth=2  # Follow edges 2 hops
    )
)
```

### FORGET

Removes or archives memories (with audit trail):

```python
# Forget a node
node = GraphNode(
    id="outdated_medical_protocol",
    type=NodeType.CONFIG,
    scope=GraphScope.LOCAL
)
result = await memory_service.forget(node)
# Note: Reason is tracked in audit trail, not in forget operation
```

## Implementation Details

### LocalGraphMemoryService

The default implementation backed by SQLite:

```python
class LocalGraphMemoryService(BaseGraphService, MemoryService):
    def __init__(self, db_path: Optional[str] = None,
                 secrets_service: Optional[SecretsService] = None,
                 time_service: Optional[TimeServiceProtocol] = None):
        # Initialize with optional dependencies
        super().__init__(memory_bus=None, time_service=time_service)

    async def memorize(self, node: GraphNode) -> MemoryOpResult:
        # Process secrets before storing
        processed_node = await self._process_secrets_for_memorize(node)

        # Store in persistence layer
        persistence.add_graph_node(processed_node, db_path=self.db_path)

        # Note: WA approval happens at handler level, not here
        return MemoryOpResult(status=MemoryOpStatus.OK)
```

### Graph Storage Schema

```sql
-- Nodes table
CREATE TABLE graph_nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    scope TEXT NOT NULL,
    attributes TEXT NOT NULL,  -- JSON with node data
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    updated_by TEXT
);

-- Edges table
CREATE TABLE graph_edges (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    properties TEXT,  -- JSON with edge metadata
    created_at TIMESTAMP,
    PRIMARY KEY (source_id, target_id, relationship)
);
```

## Advanced Features

### Identity Variance Monitoring

The system tracks changes to agent identity and triggers review when variance exceeds 20%:

```python
# Variance calculation weights
VARIANCE_WEIGHTS = {
    "agent_id": 5.0,  # Name changes are major
    "domain_knowledge": 4.0,
    "description": 3.0,
    "capabilities": 2.0,
    "preferences": 1.0
}

# Automatic monitoring on identity changes
if params.scope == GraphScope.IDENTITY:
    variance = calculate_identity_variance(
        current_identity,
        new_identity,
        VARIANCE_WEIGHTS
    )

    if variance > 0.20:
        await defer_to_wise_authority(
            reason=f"Identity variance {variance:.2%} exceeds threshold",
            changes=identity_diff
        )
```

### Time Series Integration

TSDB data is stored as graph correlations:

```python
# Agent introspection of metrics
my_metrics = await memory_service.recall(
    SearchParams(
        query="my performance metrics",
        node_type=NodeType.TSDB_SUMMARY,
        include_associations=True
    )
)

# Returns correlated data
{
    "tokens_used_today": 125000,
    "decisions_made": 342,
    "deferrals": 12,
    "avg_response_time_ms": 1250,
    "carbon_footprint_g": 2.5
}
```

### Graph Traversal Patterns

```python
# Get edges for a node
edges = memory_service.get_node_edges(
    node_id="diabetes_management",
    scope=GraphScope.LOCAL
)

# Create relationships between nodes
edge = GraphEdge(
    source="diabetes_management",
    target="patient_care_protocol",
    relationship="RELATES_TO",
    scope=GraphScope.LOCAL
)
memory_service.create_edge(edge)
```

## Best Practices

### 1. Use Semantic Concepts

```python
# Good - semantic node ID
node = GraphNode(
    id="user_prefers_metric_units",
    type=NodeType.CONFIG,
    ...
)

# Bad - implementation detail
node = GraphNode(
    id="pref_metric_flag_true",
    type=NodeType.CONFIG,
    ...
)
```

### 2. Create Rich Associations

```python
# Good - create edges to connect nodes
edge1 = GraphEdge(source=node_id, target="user_profile", relationship="PREFERENCE_OF")
edge2 = GraphEdge(source=node_id, target="measurement_system", relationship="USES")
memory_service.create_edge(edge1)
memory_service.create_edge(edge2)

# Bad - isolated node with no relationships
# (no edges created)
```

### 3. Include Metadata

```python
# Good - rich metadata
metadata={
    "confidence": 0.85,
    "source": "observed_behavior",
    "observed_count": 10,
    "last_confirmed": "2025-06-25T10:00:00Z"
}

# Bad - no context
metadata={}
```

### 4. Respect Scopes

```python
# Good - appropriate scope
# User preference = LOCAL
await memorize(
    concept="preferred_language",
    scope=GraphScope.LOCAL
)

# Configuration = ENVIRONMENT (needs approval)
await memorize(
    concept="api_endpoint_override",
    scope=GraphScope.ENVIRONMENT
)
```

## Integration with Other Services

### Audit Service
- Every memory operation creates audit entries
- Deletions are logged with reasons
- WA approvals are recorded

### Telemetry Service
- Memory operations are tracked for performance
- Graph size and complexity metrics
- Query performance analysis

### Config Service
- Configuration stored as ConfigNode memories
- Version tracking for config changes
- Rollback capabilities

## Performance Considerations

### Indexing Strategy
- Primary index on node ID
- Secondary indexes on type and scope
- Full-text search on content fields
- Relationship indexes for traversal

### Query Optimization
- Use specific node types when possible
- Limit traversal depth for large graphs
- Cache frequently accessed paths
- Batch related operations

### Storage Efficiency
- Nodes: ~1-5KB each typically
- Edges: ~200 bytes each
- Automatic compression for large content
- Periodic cleanup of orphaned nodes

## Future Enhancements

### Current Architecture
- SQLite-based graph storage for offline operation
- Scope-based access control with WA integration
- Automatic secret detection and encryption
- Time-series data consolidation
- Identity variance monitoring

## Troubleshooting

### Common Issues

**Permission Denied**
- Check if scope requires WA approval
- Verify WA authentication token
- Review audit logs for denial reason

**Node Not Found**
- Verify concept name spelling
- Check scope permissions
- Confirm node wasn't deleted

**Traversal Timeout**
- Reduce max_depth parameter
- Add relationship type filters
- Use more specific start concepts

### Debugging

```python
# Enable debug logging
import logging
logging.getLogger('memory_service').setLevel(logging.DEBUG)

# Inspect graph structure
graph_stats = await memory_service.get_statistics()
print(f"Total nodes: {graph_stats['node_count']}")
print(f"Total edges: {graph_stats['edge_count']}")
print(f"Node types: {graph_stats['node_types']}")

# Use search method for text queries
results = await memory_service.search(
    query="test",
    filters=MemorySearchFilter(
        node_type="CONFIG",
        scope="local",
        limit=10
    )
)
```

## Summary

The graph memory service implements the revolutionary principle that identity IS the graph. By unifying all agent data into a single graph structure with proper access controls, CIRIS creates agents with true persistence, self-awareness, and the ability to learn and evolve while maintaining ethical boundaries.

This isn't just a database - it's the agent's mind, memories, and identity in one coherent system.

---

*Copyright © 2025 Eric Moore and CIRIS L3C - Apache 2.0 License*
