# Persistence Layer Tests

This directory contains comprehensive tests for the CIRIS persistence layer, focusing on achieving 85% test coverage for all database and node-related functionality.

## Test Structure

### Core Database Tests (`test_database.py`)
- Database connection and initialization
- Foreign key constraint enforcement
- Transaction atomicity and ACID properties
- Concurrent access patterns
- Migration system integration
- Error handling and edge cases
- SQLite-specific features (row factory, pragma settings)

### TypedGraphNode Tests (`test_typed_nodes.py`)
- Base TypedGraphNode functionality
- Serialization/deserialization for all 11 active node types:
  - AuditEntry
  - ConfigNode
  - IdentitySnapshot
  - IncidentNode
  - AuditSummaryNode
  - ConversationSummaryNode
  - TraceSummaryNode
  - Discord nodes (Message, User, Channel, Guild)
- Type safety and validation
- Edge cases and error handling

### Migration System Tests (`test_migrations.py`)
- Migration runner functionality
- Migration tracking and ordering
- Rollback capabilities
- Error handling
- Idempotency
- Support for complex migrations (indexes, table alterations)

### Transaction Management Tests (`test_transactions.py`)
- ACID properties (Atomicity, Consistency, Isolation, Durability)
- Nested transactions using savepoints
- Concurrent transaction handling
- Deadlock detection and recovery
- Transaction isolation levels
- Long-running transactions
- WAL mode testing

### Node Registry Tests (`test_node_registry.py`)
- Node type registration and lookup
- Automatic registration via decorator
- Serialization/deserialization through registry
- Error handling for invalid nodes
- Registry state management
- Performance with many node types

## Design Principles

All tests follow CIRIS core philosophy:
- **No Dicts**: All data uses Pydantic models/schemas
- **No Strings**: Use enums and typed constants
- **No Exceptions**: No special cases or bypass patterns
- **Type Safety**: Full type validation throughout

## Running Tests

```bash
# Run all persistence tests
pytest tests/test_persistence/ -v

# Run specific test module
pytest tests/test_persistence/test_database.py -v

# Run with coverage
pytest tests/test_persistence/ --cov=ciris_engine.logic.persistence --cov=ciris_engine.schemas.services
```

## Key Test Scenarios

1. **Database Integrity**: Foreign keys, constraints, indexes
2. **Concurrent Access**: Multiple threads reading/writing
3. **Transaction Safety**: Rollback on errors, isolation
4. **Node Serialization**: Round-trip for all node types
5. **Migration Reliability**: Idempotent, ordered execution
6. **Error Recovery**: Graceful handling of failures

## SQLite Considerations

Tests are designed for SQLite's threading model:
- Single writer, multiple readers
- WAL mode for better concurrency
- Proper pragma settings (foreign_keys=ON)
- Thread-safe connection handling

All tests respect the offline-first, 4GB RAM constraint design goal.
