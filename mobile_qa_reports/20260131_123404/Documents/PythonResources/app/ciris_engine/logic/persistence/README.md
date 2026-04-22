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
  - agent_occurrence_id: Runtime instance identifier (for multi-occurrence)
  - description: What needs to be done
  - status: pending, in_progress, completed, cancelled
  - priority: Task priority level
  - created_by: Originating handler
```

#### Thoughts (`thoughts` table)
```python
Thought:
  - thought_id: UUID
  - agent_occurrence_id: Runtime instance identifier (for multi-occurrence)
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

## Multi-Occurrence Support

**Status**: ✅ PRODUCTION-READY (since v1.4.8)

The persistence layer fully supports multiple runtime instances (occurrences) sharing the same database, enabling horizontal scaling and high availability.

### Core Concepts

#### Occurrence ID
Every task and thought includes an `agent_occurrence_id` column that identifies which runtime instance owns it:
- **`"default"`** - Single-occurrence mode (backward compatible)
- **`"occurrence_1"`, `"occurrence_2"`, etc.** - Multi-occurrence mode
- **`"__shared__"`** - Special namespace for shared coordination tasks

#### Occurrence Isolation
All persistence queries automatically filter by occurrence ID:
```python
# Query tasks for specific occurrence
tasks = get_tasks_by_status("active", occurrence_id="occurrence_1")

# Query thoughts for specific occurrence
thoughts = get_thoughts_by_task_id(task_id, occurrence_id="occurrence_1")
```

### Multi-Occurrence APIs

#### 1. Shared Task Coordination

**Atomic Task Claiming** - Ensures only ONE occurrence processes critical decisions:
```python
from ciris_engine.logic.persistence.models.tasks import try_claim_shared_task

# Atomically claim or retrieve shared task
task, was_created = try_claim_shared_task(
    task_type="WAKEUP_RITUAL",
    occurrence_id="occurrence_1",  # This occurrence's ID
    channel_id="api",
    description="Daily wakeup ritual",
    priority=10,
    time_service=time_service,
    db_path=":memory:"
)

if was_created:
    # This occurrence won the race - process the task
    logger.info("Claimed wakeup task")
else:
    # Another occurrence already claimed it
    logger.info("Wakeup already handled by another occurrence")
```

**How it Works:**
- Uses deterministic task_id: `{task_type}_SHARED_{date}` (e.g., `WAKEUP_RITUAL_SHARED_20251028`)
- Uses PostgreSQL `ON CONFLICT DO NOTHING` or SQLite `INSERT OR IGNORE` for atomicity
- Task is created with `agent_occurrence_id="__shared__"`
- Claiming occurrence transfers ownership via `transfer_task_ownership()`

#### 2. Task Ownership Transfer

**Transfer Task to Claiming Occurrence:**
```python
from ciris_engine.logic.persistence.models.tasks import transfer_task_ownership

# Transfer shared task to claiming occurrence
transfer_task_ownership(
    task_id="WAKEUP_RITUAL_SHARED_20251028",
    from_occurrence_id="__shared__",
    to_occurrence_id="occurrence_1",
    db_path=":memory:"
)
```

**Use Cases:**
- After claiming a shared task via `try_claim_shared_task()`
- Moving task ownership between occurrences
- Graceful occurrence shutdown (transfer pending tasks)

#### 3. Thought Ownership Transfer

**Transfer Thoughts to Claiming Occurrence:**
```python
from ciris_engine.logic.persistence.models.thoughts import transfer_thought_ownership

# Transfer all thoughts from shared namespace to claiming occurrence
transfer_thought_ownership(
    from_occurrence_id="__shared__",
    to_occurrence_id="occurrence_1",
    task_id="WAKEUP_RITUAL_SHARED_20251028",
    db_path=":memory:"
)
```

**Critical for Shared Tasks:**
- Thoughts start in `"__shared__"` namespace
- After claiming, transfer to the occurrence that will process them
- Ensures proper occurrence isolation after transfer

#### 4. Query Helpers

**Check Shared Task Status:**
```python
from ciris_engine.logic.persistence.models.tasks import (
    get_shared_task_status,
    is_shared_task_completed,
    get_latest_shared_task
)

# Get shared task if it exists
task = get_shared_task_status("WAKEUP_RITUAL", within_hours=24)

# Check if completed recently
if is_shared_task_completed("WAKEUP_RITUAL", within_hours=24):
    logger.info("Wakeup already completed today")

# Get latest shared task (any status)
latest = get_latest_shared_task("WAKEUP_RITUAL", within_hours=24)
```

### Coordination Patterns

#### Pattern 1: Shared Wakeup/Shutdown Decision
```python
# In wakeup_processor.py or shutdown_processor.py
task, was_created = try_claim_shared_task(
    task_type=f"{state.value.upper()}_RITUAL",
    occurrence_id=self.agent_occurrence_id,
    channel_id=self.channel_id,
    description=f"{state.value.capitalize()} ritual",
    priority=10,
    time_service=self.time_service
)

if was_created:
    # This occurrence claimed the task - transfer ownership
    transfer_task_ownership(
        task_id=task.task_id,
        from_occurrence_id="__shared__",
        to_occurrence_id=self.agent_occurrence_id
    )

    transfer_thought_ownership(
        from_occurrence_id="__shared__",
        to_occurrence_id=self.agent_occurrence_id,
        task_id=task.task_id
    )

    # Process the task
    return self._process_shared_task(task)
else:
    # Another occurrence is handling it - skip
    logger.info(f"{state.value} already handled by another occurrence")
    return None
```

#### Pattern 2: Occurrence-Specific Processing
```python
# Process only this occurrence's tasks
active_tasks = get_tasks_by_status(
    TaskStatus.ACTIVE,
    occurrence_id=self.agent_occurrence_id
)

for task in active_tasks:
    # Process task
    thoughts = get_thoughts_by_task_id(
        task.task_id,
        occurrence_id=self.agent_occurrence_id
    )
    # ... process thoughts
```

### Database Maintenance

The `DatabaseMaintenanceService` handles multi-occurrence cleanup:

```python
# Clean stale shared wakeup tasks (>5 minutes old)
# Query: WHERE task_id LIKE '%_SHARED_%' AND agent_occurrence_id = '__shared__'
```

**What Gets Cleaned:**
- Stale shared wakeup tasks (>5 min, still in `__shared__` namespace)
- Orphaned tasks across ALL occurrences
- Old completed tasks (respects occurrence boundaries)

**What's Preserved:**
- Fresh shared tasks (<5 min)
- Transferred tasks (owned by specific occurrence)
- Active occurrence-specific tasks

### Testing Multi-Occurrence

```bash
# Run multi-occurrence QA tests
python -m tools.qa_runner multi_occurrence

# Test with PostgreSQL
python -m tools.qa_runner multi_occurrence --database-backends postgres

# Expect: 27/27 tests passing (100%)
```

### Migration Guide

**Upgrading to Multi-Occurrence:**

1. **Add occurrence_id to queries** (backward compatible with "default"):
   ```python
   # Before (implicit "default")
   tasks = get_all_tasks()

   # After (explicit occurrence_id)
   tasks = get_all_tasks(occurrence_id=self.agent_occurrence_id)
   ```

2. **Use shared task claiming for critical decisions:**
   ```python
   # Replace direct task creation with atomic claiming
   task, was_created = try_claim_shared_task(...)
   ```

3. **Transfer ownership after claiming:**
   ```python
   if was_created:
       transfer_task_ownership(...)
       transfer_thought_ownership(...)
   ```

### Performance Considerations

- **PostgreSQL Recommended**: Better concurrency handling for multi-occurrence
- **Indexing**: `agent_occurrence_id` column is indexed for fast queries
- **Transaction Isolation**: Use `READ COMMITTED` or higher for PostgreSQL
- **Connection Pooling**: Each occurrence maintains its own connection pool

### Troubleshooting

**Problem**: Occurrence sees another occurrence's tasks
**Solution**: Ensure all queries include `occurrence_id` parameter

**Problem**: Shared task claimed by multiple occurrences
**Solution**: Check database dialect - must use `ON CONFLICT` for PostgreSQL or `INSERT OR IGNORE` for SQLite

**Problem**: Thoughts stuck in `__shared__` namespace
**Solution**: Call `transfer_thought_ownership()` after claiming shared task

**Problem**: Orphaned tasks after occurrence shutdown
**Solution**: DatabaseMaintenanceService cleanup will handle (or implement graceful shutdown with transfer)

### Related Documentation
- `CIRIS_COMPREHENSIVE_GUIDE.md` - Multi-occurrence architecture overview
- `tools/qa_runner/modules/MULTI_OCCURRENCE_README.md` - QA test documentation
- `FSD/multi_occurrence_implementation_plan_1.4.8.md` - Implementation plan
