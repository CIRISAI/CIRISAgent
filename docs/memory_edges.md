# Memory Graph Edges Documentation

## Overview

The CIRIS memory system now fully supports graph edges between nodes. Edges represent relationships between memory nodes and can be queried along with nodes.

## Key Features

### 1. Edge Storage
- Edges are stored in the `graph_edges` table
- Each edge has: source, target, relationship type, weight, and optional attributes
- Edges belong to a specific scope (LOCAL, IDENTITY, ENVIRONMENT, COMMUNITY)

### 2. Including Edges in Queries

When querying nodes, you can include edges by setting `include_edges=true`:

```python
# Python SDK
query = MemoryQuery(
    node_id="some_node_id",
    scope=GraphScope.LOCAL,
    include_edges=True,
    depth=1  # How many levels of connected nodes to fetch
)
nodes = await memory_service.recall(query)

# The edges will be in node.attributes['_edges']
```

```typescript
// TypeScript SDK
const nodes = await client.memory.queryWithEdges('some_query', {
  include_edges: true,
  depth: 1
});

// Access edges via node.attributes._edges
```

### 3. Creating Edges

```python
# Python
edge = GraphEdge(
    source="node1_id",
    target="node2_id",
    relationship="related_to",
    scope=GraphScope.LOCAL,
    weight=0.8
)
await memory_service.create_edge(edge)
```

```typescript
// TypeScript
await client.memory.createEdge({
  source: "node1_id",
  target: "node2_id",
  relationship: "related_to",
  scope: "local",
  weight: 0.8
});
```

### 4. API Endpoints

#### Get node with edges
```bash
GET /v1/memory/{node_id}?include_edges=true&depth=1
```

#### Query nodes with edges
```bash
POST /v1/memory/query
{
  "query": "search term",
  "include_edges": true,
  "depth": 1
}
```

#### Get edges for a node
```bash
GET /v1/memory/{node_id}/edges?scope=local
```

**Note:** Edge creation happens internally through agent processing. There is no direct API endpoint for creating edges as this would bypass the agent's memory management system.

## Edge Data Format

When edges are included in a node response, they appear in the `attributes._edges` array:

```json
{
  "id": "node_id",
  "type": "concept",
  "scope": "local",
  "attributes": {
    "name": "Node Name",
    "_edges": [
      {
        "source": "node_id",
        "target": "other_node_id",
        "relationship": "related_to",
        "weight": 0.8,
        "attributes": {
          "created_at": "2025-01-07T12:00:00Z"
        }
      }
    ]
  }
}
```

## Graph Traversal

- `depth=1`: Returns only the requested node with its direct edges
- `depth=2`: Returns the requested node, its edges, and all directly connected nodes with their edges
- `depth=3`: Returns up to 3 levels of graph traversal

## Use Cases

1. **Knowledge Graph**: Link concepts, ideas, and observations
2. **Social Graph**: Track relationships between users and agents
3. **Dependency Graph**: Model dependencies between configurations or tasks
4. **Temporal Graph**: Connect events and observations over time

## Performance Considerations

- Including edges adds overhead to queries
- Use appropriate depth limits to avoid fetching too much data
- Edges are indexed by source and target for efficient queries
