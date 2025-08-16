# Memory Service Telemetry

## Overview
The Memory Service is the foundational graph database for CIRIS, implementing local SQLite-based graph storage with optional secrets integration. As a core infrastructure service, it provides telemetry on graph node operations, database performance, secrets handling, and memory usage. Unlike other services that use the memory bus, the Memory Service IS the memory backend that other services use.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| uptime_seconds | gauge | in-memory | per request | `_collect_metrics()` |
| request_count | counter | in-memory | per operation | `_track_request()` |
| error_count | counter | in-memory | per error | `_track_error()` |
| error_rate | gauge | calculated | per request | `error_count/request_count` |
| healthy | gauge | in-memory | real-time | health check status |
| memory_bus_available | gauge | in-memory | on dependency check | 0.0 (memory service) |
| secrets_enabled | gauge | in-memory | on service init | SecretsService availability |
| graph_node_count | gauge | database query | on metrics collection | `SELECT COUNT(*) FROM graph_nodes` |
| storage_backend | gauge | constant | static | 1.0 (SQLite backend) |
| memorize_operations | counter | implicit | per memorize() call | operation tracking |
| recall_operations | counter | implicit | per recall() call | operation tracking |
| forget_operations | counter | implicit | per forget() call | operation tracking |
| search_operations | counter | implicit | per search() call | operation tracking |
| timeseries_queries | counter | implicit | per recall_timeseries() | operation tracking |
| metric_memorizations | counter | implicit | per memorize_metric() | metric storage tracking |
| log_memorizations | counter | implicit | per memorize_log() | log storage tracking |
| edge_creations | counter | implicit | per create_edge() | graph edge operations |
| secrets_processed | counter | implicit | per secret detection | secrets handling |

## Data Structures

### GraphNode (Core Storage Unit)
```python
{
    "id": "metric_llm.tokens.total_1723650000123456",
    "type": "tsdb_data",
    "scope": "local",
    "attributes": {
        "created_at": "2025-08-14T13:30:00Z",
        "updated_at": "2025-08-14T13:30:00Z",
        "created_by": "memory_service",
        "tags": ["metric", "llm.tokens.total"],
        "metric_name": "llm.tokens.total",
        "metric_type": "gauge",
        "value": 1523.0,
        "start_time": "2025-08-14T13:30:00Z",
        "end_time": "2025-08-14T13:30:00Z",
        "duration_seconds": 0.0,
        "sample_count": 1,
        "labels": {"service": "OpenAIClient", "handler": "analyze_thought"},
        "service_name": "memory_service",
        "secret_refs": ["uuid-secret-ref-1", "uuid-secret-ref-2"]  # If secrets detected
    },
    "version": 1,
    "updated_by": "memory_service",
    "updated_at": "2025-08-14T13:30:00Z"
}
```

### MemoryOpResult (Operation Response)
```python
{
    "status": "OK",  # OK, DENIED, ERROR
    "error": null,   # Error message if status != OK
    "data": null     # Optional result data
}
```

### TimeSeriesDataPoint (From recall_timeseries)
```python
{
    "timestamp": "2025-08-14T13:30:00Z",
    "metric_name": "llm.tokens.total",
    "value": 1523.0,
    "correlation_type": "METRIC_DATAPOINT",
    "tags": {
        "service": "OpenAIClient",
        "handler": "analyze_thought"
    },
    "source": "memory_service"
}
```

### ServiceMetrics (Health Check Response)
```python
{
    "uptime_seconds": 3600.5,
    "requests_handled": 1250,
    "error_count": 3,
    "avg_response_time_ms": null,  # Not tracked at service level
    "memory_mb": null,             # Not tracked at service level
    "custom_metrics": {
        "secrets_enabled": 1.0,
        "graph_node_count": 45678.0,
        "storage_backend": 1.0,
        "memory_bus_available": 0.0,
        "error_rate": 0.0024,
        "healthy": 1.0
    }
}
```

### GraphEdge (Relationship Storage)
```python
{
    "source": "node_id_1",
    "target": "node_id_2",
    "relationship": "RELATED_TO",
    "weight": 1.0,
    "scope": "local",
    "attributes": {
        "created_at": "2025-08-14T13:30:00Z",
        "relationship_type": "semantic",
        "confidence": 0.85
    }
}
```

### MemoryQuery (Query Structure)
```python
{
    "node_id": "metric_*",        # Node ID pattern (* for wildcard)
    "scope": "local",             # GraphScope enum
    "type": "tsdb_data",          # NodeType enum
    "include_edges": true,        # Include connected edges
    "depth": 2                    # Connection traversal depth
}
```

## API Access Patterns

### Current Access
- **Internal Operations**: Direct method calls on LocalGraphMemoryService
- **No Direct REST API**: Memory service is internal infrastructure
- **Graph Storage**: All data persisted in SQLite graph_nodes table
- **Secrets Integration**: Automatic detection and encryption via SecretsService

### Recommended Endpoints (Future API Exposure)

#### Get Memory Statistics
```
GET /v1/memory/statistics
```
Returns:
```json
{
    "total_nodes": 45678,
    "nodes_by_type": {
        "tsdb_data": 23456,
        "audit_event": 12345,
        "identity": 5678,
        "thought": 3456,
        "correlation": 723
    },
    "nodes_by_scope": {
        "local": 40000,
        "identity": 3000,
        "global": 2678
    },
    "database_size_mb": 234.5,
    "secret_refs_count": 156
}
```

#### Get Service Health
```
GET /v1/memory/health
```
Returns:
```json
{
    "healthy": true,
    "uptime_seconds": 3600.5,
    "database_accessible": true,
    "secrets_service_available": true,
    "last_operation": "2025-08-14T13:29:58Z",
    "metrics": {
        "request_count": 1250,
        "error_count": 3,
        "error_rate": 0.0024,
        "graph_node_count": 45678
    }
}
```

#### Query Time Series Metrics
```
GET /v1/memory/timeseries?metric_name=llm.tokens.total&hours=24
```
Query parameters:
- `metric_name`: Metric to query
- `hours`: Time window (default 24)
- `start_time`: ISO datetime start
- `end_time`: ISO datetime end
- `limit`: Max results (default 1000)

Returns:
```json
{
    "metric_name": "llm.tokens.total",
    "time_window_hours": 24,
    "data_points": [
        {
            "timestamp": "2025-08-14T13:30:00Z",
            "value": 1523.0,
            "tags": {"service": "OpenAIClient"},
            "source": "memory_service"
        }
    ],
    "summary": {
        "count": 234,
        "sum": 45678.0,
        "average": 195.2,
        "min": 10.0,
        "max": 500.0
    }
}
```

## Graph Storage

### Node Types Managed
- `TSDB_DATA` - Time series metrics and logs
- `AUDIT_EVENT` - Audit trail entries
- `IDENTITY` - Self-knowledge and capabilities
- `THOUGHT` - Reasoning and decision data
- `CORRELATION` - Service correlations
- `CONFIG` - Configuration data
- `INCIDENT` - Incident management data
- `VISIBILITY` - Observability data

### Scope Categories
```python
class GraphScope(Enum):
    LOCAL = "local"       # Instance-specific data
    IDENTITY = "identity" # Self-knowledge data
    GLOBAL = "global"     # Cross-instance data
```

### Edge Relationships
- `RELATED_TO` - Generic semantic relationship
- `CAUSED_BY` - Causal relationship (errors, incidents)
- `FOLLOWS_FROM` - Temporal sequence
- `MEASURED_BY` - Metric source relationship
- `PART_OF` - Hierarchical containment
- `CORRELATES_WITH` - Statistical correlation

### Storage Architecture
- **Backend**: SQLite with graph_nodes and graph_edges tables
- **Indexing**: Node ID, type, scope, created_at for time queries
- **Transactions**: ACID compliance for data integrity
- **Concurrency**: Thread-safe connection pooling
- **Backup**: File-based SQLite database backup

## Example Usage

### Store a Metric
```python
memory_service = LocalGraphMemoryService()

# Store metric directly
result = await memory_service.memorize_metric(
    metric_name="custom.processing.time",
    value=123.45,
    tags={"component": "processor", "stage": "analysis"},
    scope="local"
)

print(f"Metric stored: {result.status}")
```

### Store Graph Node
```python
# Create typed node
node = GraphNode(
    id="custom_node_123",
    type=NodeType.IDENTITY,
    scope=GraphScope.IDENTITY,
    attributes={
        "created_at": datetime.now(timezone.utc),
        "capability": "reasoning",
        "confidence": 0.95,
        "evidence": "successful problem solving"
    },
    updated_by="reasoning_module"
)

result = await memory_service.memorize(node)
```

### Query Graph Data
```python
# Query specific node
query = MemoryQuery(
    node_id="custom_node_123",
    scope=GraphScope.IDENTITY,
    include_edges=True,
    depth=2
)

nodes = await memory_service.recall(query)
for node in nodes:
    print(f"Found: {node.id} - {node.attributes}")
```

### Search with Filters
```python
# Search by content
filter = MemorySearchFilter(
    scope=GraphScope.LOCAL,
    node_type=NodeType.TSDB_DATA,
    limit=50
)

results = await memory_service.search(
    query="llm.tokens",
    filters=filter
)
```

### Query Time Series
```python
# Get metrics from last 6 hours
data_points = await memory_service.recall_timeseries(
    scope="local",
    hours=6,
    start_time=datetime.now(timezone.utc) - timedelta(hours=6)
)

for point in data_points:
    print(f"{point.timestamp}: {point.metric_name} = {point.value}")
```

### Create Graph Edges
```python
# Link related nodes
edge = GraphEdge(
    source="node_1",
    target="node_2",
    relationship="CAUSED_BY",
    weight=0.8,
    scope=GraphScope.LOCAL,
    attributes={
        "confidence": 0.85,
        "created_at": datetime.now(timezone.utc)
    }
)

result = memory_service.create_edge(edge)
```

## Testing

### Test Files
- `tests/logic/services/graph/test_memory_service.py` - Core service tests
- `tests/logic/persistence/test_graph_operations.py` - Persistence layer tests
- `tests/integration/test_memory_flow.py` - End-to-end memory tests
- `tests/secrets/test_memory_secrets.py` - Secrets integration tests

### Validation Steps
1. Initialize service with SQLite database
2. Store graph node via `memorize()`
3. Verify node appears in database
4. Query node via `recall()`
5. Test wildcard queries
6. Test edge creation and traversal
7. Test time series storage and retrieval
8. Verify secrets detection and encryption
9. Test health checks and metrics

```python
async def test_memory_service_flow():
    # Initialize service
    memory_service = LocalGraphMemoryService(
        db_path=":memory:",  # In-memory for testing
        secrets_service=mock_secrets_service,
        time_service=mock_time_service
    )

    # Test metric storage
    result = await memory_service.memorize_metric(
        "test.metric",
        value=100.0,
        tags={"test": "true"}
    )
    assert result.status == MemoryOpStatus.OK

    # Test retrieval
    data_points = await memory_service.recall_timeseries(
        scope="local",
        hours=1
    )
    assert len(data_points) >= 1
    assert data_points[0].metric_name == "test.metric"

    # Test health
    health = await memory_service.is_healthy()
    assert health is True

    # Test metrics collection
    metrics = memory_service._collect_metrics()
    assert "graph_node_count" in metrics
    assert metrics["storage_backend"] == 1.0
```

## Configuration

### Database Settings
```python
{
    "db_path": "/app/data/ciris.db",      # SQLite file path
    "connection_timeout": 30,             # Connection timeout seconds
    "busy_timeout": 5000,                # SQLite busy timeout ms
    "journal_mode": "WAL",                # Write-ahead logging
    "synchronous": "NORMAL",              # Durability vs performance
    "cache_size": 2000,                   # Page cache size
}
```

### Secrets Integration
```python
{
    "secrets_service_enabled": true,      # Enable secrets detection
    "auto_encrypt": true,                 # Auto-encrypt detected secrets
    "auto_decrypt_actions": [             # Actions that auto-decrypt
        "speak", "tool", "recall"
    ],
    "secret_retention_days": 90,          # Secret reference retention
}
```

### Performance Tuning
```python
{
    "max_query_results": 1000,            # Limit for wildcard queries
    "timeseries_limit": 1000,            # Time series query limit
    "edge_traversal_max_depth": 5,       # Maximum edge traversal
    "connection_pool_size": 10,           # SQLite connection pool
    "query_timeout_seconds": 30,          # Query timeout
}
```

## Known Limitations

1. **SQLite Concurrency**: Limited concurrent writes (WAL mode helps)
2. **Memory Usage**: Large graph queries can consume significant RAM
3. **No Built-in Sharding**: Single database file limits scale
4. **Secret Cleanup**: No automatic secret reference counting/cleanup
5. **Query Performance**: Full-text search requires manual string matching
6. **No Transactions**: Individual operations not grouped in transactions
7. **Edge Traversal**: Deep traversals can be expensive
8. **Time Series**: Not optimized for high-frequency metrics storage

## Future Enhancements

1. **Graph Database Backend**: Neo4j/ArangoDB support for better graph operations
2. **Full-Text Search**: SQLite FTS5 integration for content search
3. **Query Optimization**: Prepared statements and query planning
4. **Sharding Support**: Multi-database distribution for scale
5. **Streaming APIs**: Real-time graph change notifications
6. **Advanced Analytics**: Graph algorithms (PageRank, clustering)
7. **Time Series Optimization**: Dedicated TSDB backend integration
8. **Secret Lifecycle**: Automatic reference counting and cleanup
9. **Backup/Restore**: Automated backup and point-in-time recovery
10. **Graph Visualization**: Export formats for graph visualization tools

## Integration Points

- **No MemoryBus Dependency**: Memory service IS the backend
- **TimeService**: Required for consistent timestamps
- **SecretsService**: Optional for secrets detection/encryption
- **All Graph Services**: Use memory service as storage backend
- **TSDBConsolidationService**: Processes stored time series data
- **AuditService**: Stores audit events in memory graph
- **ConfigService**: Stores configuration in memory graph

## Monitoring Recommendations

1. **Database Growth**: Monitor `graph_node_count` trend
2. **Query Performance**: Track operation response times
3. **Error Rates**: Watch `error_count` and `error_rate` metrics
4. **Disk Usage**: Monitor SQLite file size growth
5. **Secret References**: Track `secrets_processed` count
6. **Connection Health**: Monitor database connectivity
7. **Edge Density**: Track graph complexity via edge counts
8. **Time Series Volume**: Monitor metric storage rate

## Performance Considerations

1. **Database Size**: SQLite performance degrades with very large databases
2. **Query Complexity**: Wildcard queries scan entire table
3. **Edge Traversals**: Deep traversals require multiple database queries
4. **Secret Processing**: Encryption/decryption adds overhead
5. **Time Series Queries**: Range queries benefit from proper indexing
6. **Concurrent Access**: Write operations may block on SQLite locks
7. **Memory Usage**: Large result sets loaded entirely into memory
8. **JSON Parsing**: Node attributes stored as JSON strings

## Architecture Notes

The Memory Service implements CIRIS's "everything is a memory" philosophy:
- All telemetry data becomes graph memories
- Operational metrics become operational memories
- System logs become temporal memories
- Service interactions become relational memories
- Configuration becomes persistent memories

This unified approach enables:
- Consistent data access patterns across all services
- Rich relationship modeling between different data types
- Temporal correlation analysis across system components
- Secrets management integrated into all data storage
- Audit trails for all memory operations

The service acts as the foundational data layer, with all other graph services depending on it for persistence while providing their own specialized query and analysis capabilities on top of this common storage foundation.
