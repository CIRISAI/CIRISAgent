# Persistence Module

This module contains the persistence components of the CIRIS engine, providing robust storage for agent memory, correlations, tasks, thoughts, and time-series data.

## Overview

The persistence layer supports both **SQLite** (development/small deployments) and **PostgreSQL** (production/scale) through a lightweight dialect adapter. The database backend is determined by the `CIRIS_DB_URL` environment variable:

- **SQLite**: `sqlite:///path/to/db.db` or just `path/to/db.db` (default)
- **PostgreSQL**: `postgresql://user:password@host:port/dbname`

The persistence layer provides several key subsystems:

### 1. Graph Memory System
The graph memory system stores knowledge as nodes and edges with different scopes:
- **LOCAL**: Agent-specific runtime data and observations
- **IDENTITY**: Core agent identity and behavioral parameters (requires WA approval)
- **ENVIRONMENT**: Shared environmental context
- **COMMUNITY**: Community-level shared knowledge
- **NETWORK**: Network-wide distributed knowledge

### 2. Time-Series Database (TSDB)
The TSDB system stores time-series data using the correlations table with specialized types:
- **METRIC_DATAPOINT**: Numeric metrics with tags for filtering
- **LOG_ENTRY**: Timestamped log messages with severity levels
- **AUDIT_EVENT**: Audit trail entries with full context
- **SERVICE_CORRELATION**: General service interaction tracking

### 3. Adaptive Configuration
Dynamic configuration stored as graph nodes with `NodeType.CONFIG`:
- **Filter configurations**: Adaptive content filtering rules
- **Channel configurations**: Per-channel behavioral settings
- **User tracking**: Interaction patterns and preferences
- **Response templates**: Dynamic response formatting
- **Tool preferences**: Learned tool usage patterns

### 4. Core Data Models

#### Graph Nodes (`graph_nodes` table)
```python
GraphNode:
  - id: Unique identifier
  - type: NodeType (AGENT, USER, CHANNEL, CONCEPT, CONFIG, TSDB_DATA)
  - scope: GraphScope (LOCAL, IDENTITY, ENVIRONMENT, COMMUNITY, NETWORK)
  - attributes: JSON data containing node-specific information
  - version: Schema version for migration support
```

#### Correlations (`correlations` table)
```python
ServiceCorrelation:
  - correlation_id: UUID for tracking
  - service_type: Service that generated the data
  - correlation_type: METRIC_DATAPOINT, LOG_ENTRY, AUDIT_EVENT, etc.
  - timestamp: When the event occurred
  - metric_name/value: For metrics
  - log_level/message: For logs
  - tags: JSON tags for filtering and categorization
  - retention_policy: raw, aggregated, downsampled
```

#### Tasks (`tasks` table)
```python
Task:
  - task_id: UUID
  - description: What needs to be done
  - status: pending, in_progress, completed, cancelled
  - priority: Task priority level
  - created_by: Originating handler
```

#### Thoughts (`thoughts` table)
```python
Thought:
  - thought_id: UUID
  - content: The thought content
  - thought_type: Type classification
  - status: pending, processing, completed, rejected
  - escalation_level: How many times escalated
```

## Key Features

### 1. TSDB Integration
The persistence layer now supports time-series operations:
- Store metrics, logs, and audit events as correlations
- Query by time range, tags, and correlation type
- Automatic retention policy support
- Efficient time-based indexing

### 2. Adaptive Learning
Configuration and behavioral patterns are stored as graph nodes:
- Per-channel adaptive filters learn from interactions
- User preference tracking
- Dynamic response template evolution
- Tool usage optimization

### 3. Secrets Management Integration
- Automatic secret detection in graph node attributes
- Encryption of sensitive data before storage
- Secure retrieval with context-aware decryption

### 4. Multi-Scope Memory
Different memory scopes provide appropriate access control:
- LOCAL scope for transient agent data
- IDENTITY scope for core agent configuration (WA-protected)
- Shared scopes for collaborative knowledge

## Database Dialect Support

The persistence layer uses a **DialectAdapter** to support both SQLite and PostgreSQL with minimal code changes:

### Dialect Adapter Features
- **Automatic Detection**: Database type determined from `CIRIS_DB_URL` connection string
- **SQL Translation**: Converts SQLite-specific syntax to PostgreSQL equivalents:
  - `INSERT OR REPLACE` → `INSERT ... ON CONFLICT ... DO UPDATE`
  - `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`
  - `json_extract()` → JSONB operators (`->`, `->>`)
  - `?` placeholders → `%s` placeholders
- **Backward Compatible**: Defaults to SQLite for existing deployments
- **Zero Runtime Overhead**: Translation happens at query build time

### Using PostgreSQL

To use PostgreSQL instead of SQLite, set the `CIRIS_DB_URL` environment variable:

```bash
export CIRIS_DB_URL='postgresql://user:password@localhost:5432/ciris_db'
python main.py --adapter api
```

The dialect adapter automatically:
1. Detects PostgreSQL from the connection string
2. Initializes the database schema if needed
3. Translates all SQL queries to PostgreSQL syntax
4. Uses psycopg2 connection pooling

### Testing Both Dialects

```bash
# Test with SQLite (default)
python -m tools.qa_runner

# Test with PostgreSQL
export CIRIS_DB_URL='postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db'
python -m tools.qa_runner
```

## Database Migrations

The persistence layer uses a migration system based on numbered SQL files located in `ciris_engine/persistence/migrations/`. On startup, the runtime runs all pending migrations in order and records them in the `schema_migrations` table.

### Current Migrations:
1. `001_initial_schema.sql` - Base tables for graph, tasks, thoughts
2. `002_add_retry_status.sql` - Retry support for thoughts
3. `003_signed_audit_trail.sql` - TSDB columns for correlations

### Adding a New Migration:
1. Create a new file with numeric prefix: `004_your_feature.sql`
2. Write SQL statements (executed in a single transaction)
3. Migrations run automatically on startup or `initialize_database()`

If a migration fails, it's rolled back and the database remains unchanged.

## Usage Examples

### Storing a Metric
```python
from ciris_engine.schemas.graph_schemas_v1 import TSDBGraphNode

# Create a metric node
node = TSDBGraphNode.create_metric_node(
    metric_name="cpu_usage",
    value=75.5,
    tags={"host": "agent-1", "env": "prod"}
)

# Store in memory (creates both graph node and correlation)
await memory_service.memorize_metric("cpu_usage", 75.5, tags)
```

### Querying Time-Series Data
```python
# Get last 24 hours of metrics
metrics = await memory_service.recall_timeseries(
    hours=24,
    correlation_types=[CorrelationType.METRIC_DATAPOINT]
)
```

### Adaptive Configuration
```python
# Store adaptive filter config
filter_node = GraphNode(
    id="filter_config_channel_123",
    type=NodeType.CONFIG,
    scope=GraphScope.LOCAL,
    attributes={
        "config_type": ConfigNodeType.FILTER_CONFIG,
        "sensitivity": 0.8,
        "learned_patterns": [...]
    }
)
```

## Best Practices

1. **Use appropriate scopes**: Store data in the most restrictive scope that works
2. **Tag your metrics**: Use consistent tags for easier querying
3. **Set retention policies**: Use "aggregated" or "downsampled" for long-term data
4. **Batch operations**: Use transactions for multiple related operations
5. **Monitor growth**: Regularly check database size and optimize queries
