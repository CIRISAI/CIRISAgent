# Memory Bus Telemetry

## Overview
The Memory Bus manages all graph memory operations across the system. Unlike other buses, it currently has minimal telemetry collection at the bus level, with most metrics collected by the underlying MemoryService.

## Telemetry Data Collected

### Bus-Level Metrics (Currently Minimal)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| operation_count | implicit | none | per-call | not exposed |
| service_availability | boolean | in-memory | on-demand | via get_service() |

### Service-Level Metrics (LocalGraphMemoryService)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| graph_node_count | gauge | in-memory | on-demand | `_collect_custom_metrics()` |
| secrets_enabled | boolean | in-memory | static | `_collect_custom_metrics()` |
| storage_backend | enum | in-memory | static | `_collect_custom_metrics()` |
| uptime_seconds | gauge | in-memory | on-demand | base service metrics |
| request_count | counter | in-memory | per-request | base service metrics |
| error_count | counter | in-memory | on-error | base service metrics |
| error_rate | calculated | in-memory | on-demand | base service metrics |
| healthy | boolean | in-memory | on-demand | `is_healthy()` |

### Graph Operation Metrics (Implicit)

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| nodes_created | counter | graph db | per-memorize | SQL query |
| edges_created | counter | graph db | per-link | SQL query |
| nodes_by_type | histogram | graph db | current state | SQL query |
| correlations_count | counter | graph db | current state | SQL query |
| time_series_points | counter | graph db | per-metric | SQL query |

## Data Structures

### Service Metrics (from BaseService)
```python
{
    "uptime_seconds": 36420.5,          # Time since service start
    "request_count": 45678.0,           # Total operations
    "error_count": 23.0,                # Failed operations
    "error_rate": 0.0005,                # Error percentage
    "healthy": 1.0,                      # 1.0 if healthy, 0.0 if not
    "secrets_enabled": 1.0,              # 1.0 if secrets service available
    "graph_node_count": 12345.0,         # Total nodes in graph
    "storage_backend": 1.0               # 1.0 = sqlite, 2.0 = neo4j (future)
}
```

### Graph Statistics (from Database)
```python
{
    "total_nodes": 12345,
    "nodes_by_type": {
        "THOUGHT": 5234,
        "MESSAGE": 3456,
        "CONTEXT": 2345,
        "ACTION": 1234,
        "METRIC": 456,
        "AUDIT": 234
    },
    "total_edges": 23456,
    "total_correlations": 34567,
    "database_size_mb": 123.4
}
```

## API Access Patterns

### Current Access
- **No Direct Bus Metrics**: Memory bus doesn't expose metrics directly
- **Service Metrics Internal**: `_collect_custom_metrics()` not exposed via API
- **Database Queries Required**: Must query SQLite directly for statistics

### Recommended Endpoints

#### Memory Statistics
```
GET /v1/telemetry/memory/stats
```
Returns graph database statistics:
```json
{
    "nodes": {
        "total": 12345,
        "by_type": {
            "THOUGHT": 5234,
            "MESSAGE": 3456
        }
    },
    "edges": {
        "total": 23456
    },
    "storage": {
        "backend": "sqlite",
        "size_mb": 123.4,
        "path": "/app/data/ciris.db"
    },
    "performance": {
        "avg_memorize_ms": 12.3,
        "avg_recall_ms": 8.7
    }
}
```

#### Memory Operations Timeline
```
GET /v1/telemetry/memory/timeline
```
Returns recent memory operations:
```json
{
    "operations": [
        {
            "timestamp": "2025-08-14T13:30:00Z",
            "type": "memorize",
            "node_type": "THOUGHT",
            "node_id": "thought-123",
            "duration_ms": 12.3,
            "status": "success"
        }
    ]
}
```

## Graph Storage

### Node Types Stored
- `THOUGHT` - Agent thoughts
- `MESSAGE` - Communication messages
- `CONTEXT` - Context nodes
- `ACTION` - Action taken
- `METRIC` - Telemetry metrics
- `AUDIT` - Audit events
- `CONFIG` - Configuration items
- `INCIDENT` - System incidents

### Edge Relationships
- `FOLLOWS` - Temporal sequence
- `RESPONDS_TO` - Response relationship
- `TRIGGERED_BY` - Causation
- `RELATED_TO` - General relation
- `MEASURED_BY` - Metric ownership

### Database Schema
```sql
-- Graph nodes table
CREATE TABLE graph_nodes (
    id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    attributes TEXT,  -- JSON
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Graph edges table
CREATE TABLE graph_edges (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    target_id TEXT,
    edge_type TEXT,
    attributes TEXT,  -- JSON
    created_at TIMESTAMP
);

-- Correlations table (legacy)
CREATE TABLE correlations (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    target_id TEXT,
    correlation_type TEXT,
    confidence REAL,
    created_at TIMESTAMP
);
```

## Example Usage

### Get Node Count
```python
# Direct database query
from ciris_engine.logic.persistence import get_db_connection

with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM graph_nodes")
    count = cursor.fetchone()[0]
```

### Get Memory Service Metrics
```python
# Access service metrics
memory_service = service_registry.get_service(ServiceType.MEMORY)
if isinstance(memory_service, LocalGraphMemoryService):
    metrics = memory_service._collect_custom_metrics()
    node_count = metrics.get("graph_node_count", 0)
```

### Check Memory Health
```python
# Health check includes database connectivity
memory_bus = get_service(ServiceType.MEMORY)
is_healthy = await memory_bus.is_healthy()
```

## Testing

### Test Files
- `tests/logic/buses/test_memory_bus.py` - Bus tests
- `tests/logic/services/graph/test_memory_service.py` - Service tests

### Validation Steps
1. Perform memorize operation
2. Check node count increases
3. Verify node appears in database
4. Confirm recall returns node
5. Check metrics update

```python
async def test_memory_metrics():
    memory_bus = get_service(ServiceType.MEMORY)

    # Get initial count
    initial_count = get_node_count()

    # Memorize a node
    node = GraphNode(
        id="test-node",
        type=NodeType.THOUGHT,
        attributes={"content": "test"}
    )
    result = await memory_bus.memorize(node)

    # Verify count increased
    new_count = get_node_count()
    assert new_count == initial_count + 1
```

## Known Limitations

1. **No Bus-Level Metrics**: Memory bus doesn't track operation counts or latencies
2. **No Performance Metrics**: Memorize/recall timing not measured
3. **No Cache Metrics**: Cache hit/miss rates not tracked
4. **Limited Error Tracking**: Only counts errors, no categorization
5. **No Query Metrics**: Recall query patterns not analyzed

## Future Enhancements

1. **Operation Metrics**: Track memorize/recall/forget counts and latencies
2. **Cache Layer**: Add in-memory cache with hit/miss tracking
3. **Query Analytics**: Analyze recall patterns for optimization
4. **Performance Monitoring**: Track operation timing percentiles
5. **Storage Metrics**: Monitor database growth and compaction
6. **Batch Operations**: Support bulk memorize with metrics

## Integration Points

- **TimeService**: Provides timestamps for all operations
- **SecretsService**: Encrypts sensitive attributes before storage
- **AuditService**: May use memory bus for audit storage
- **TelemetryService**: Stores metrics as graph nodes

## Monitoring Recommendations

1. **Database Growth**: Monitor file size and node count growth
2. **Operation Latency**: Track memorize/recall response times
3. **Error Rate**: Alert on elevated error rates
4. **Node Type Distribution**: Monitor balance of node types
5. **Query Performance**: Track slow queries via SQL logging

## Configuration

### Database Settings
```python
{
    "db_path": "/app/data/ciris.db",  # SQLite database location
    "connection_timeout": 30,          # Database connection timeout
    "journal_mode": "WAL",            # Write-ahead logging for performance
}
```

### Future Backend Support
- SQLite (current)
- Neo4j (planned)
- ArangoDB (planned)
- PostgreSQL with graph extension (considered)

## Performance Considerations

1. **SQLite Limitations**: Single-writer model can bottleneck under load
2. **No Connection Pooling**: Each operation opens new connection
3. **JSON Serialization**: Attributes stored as JSON text
4. **No Indexing Strategy**: Missing indexes on frequently queried fields
5. **Unbounded Growth**: No automatic cleanup or archival
