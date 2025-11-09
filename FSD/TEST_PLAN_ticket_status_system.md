# Test Plan: Universal Ticket Status System

**Version**: 1.0
**Date**: 2025-11-07
**Status**: Ready for Implementation

---

## 1. Overview

This test plan provides comprehensive coverage for the Universal Ticket Status System implemented in version 1.6.x. The plan covers:
- Migration 009 (SQLite and PostgreSQL)
- Core Tool Service ticket management enhancements
- WorkProcessor two-phase ticket discovery
- Tickets persistence model updates

**Target Coverage**: 100% of new/modified code

---

## 2. Test Structure

### 2.1 Test File Organization

```
tests/
├── ciris_engine/
│   ├── logic/
│   │   ├── persistence/
│   │   │   ├── models/
│   │   │   │   └── test_tickets.py                    # NEW
│   │   │   └── db/
│   │   │       └── test_migration_009.py              # NEW
│   │   ├── services/
│   │   │   └── tools/
│   │   │       └── core_tool_service/
│   │   │           └── test_ticket_tools.py           # NEW
│   │   └── processors/
│   │       └── states/
│   │           └── test_work_processor_tickets.py     # NEW
│   └── integration/
│       └── test_ticket_lifecycle.py                   # NEW
```

---

## 3. Migration Testing

### 3.1 Test File: `test_migration_009.py`

**Location**: `tests/ciris_engine/logic/persistence/db/test_migration_009.py`

**Lines to Cover**: 114 (SQLite) + 39 (PostgreSQL) = 153 lines

#### Test Cases:

##### TC-M001: SQLite Migration 009 - Fresh Database
- **Purpose**: Verify migration 009 applies cleanly on fresh database
- **Setup**:
  - Create temp database
  - Apply migrations 001-008
- **Execute**: Apply migration 009
- **Assert**:
  - `agent_occurrence_id` column exists
  - Default value is `__shared__`
  - Status CHECK constraint includes all 8 states
  - Index `idx_tickets_occurrence_status` exists
- **Lines Covered**: 1-115 (SQLite migration)

##### TC-M002: SQLite Migration 009 - With Existing Tickets
- **Purpose**: Verify existing tickets migrate correctly
- **Setup**:
  - Create temp database with migrations 001-008
  - Insert 5 test tickets with old status values
- **Execute**: Apply migration 009
- **Assert**:
  - All tickets have `agent_occurrence_id='__shared__'`
  - Existing ticket data preserved (ticket_id, sop, metadata, etc.)
  - Old statuses still valid (pending, in_progress, completed, cancelled, failed)
- **Lines Covered**: 60-80 (data migration)

##### TC-M003: SQLite Migration 009 - New Status Values
- **Purpose**: Verify new status values can be inserted
- **Setup**: Database with migration 009 applied
- **Execute**:
  - Insert ticket with status='assigned'
  - Insert ticket with status='blocked'
  - Insert ticket with status='deferred'
- **Assert**: All inserts succeed
- **Lines Covered**: 26-38 (CHECK constraint)

##### TC-M004: SQLite Migration 009 - Invalid Status Rejected
- **Purpose**: Verify CHECK constraint rejects invalid statuses
- **Setup**: Database with migration 009 applied
- **Execute**: Attempt to insert ticket with status='invalid_status'
- **Assert**: Insert fails with CHECK constraint violation
- **Lines Covered**: 29 (CHECK constraint)

##### TC-M005: SQLite Migration 009 - Index Performance
- **Purpose**: Verify multi-occurrence index created
- **Setup**: Database with migration 009 applied
- **Execute**: Query `EXPLAIN QUERY PLAN SELECT * FROM tickets WHERE agent_occurrence_id='occ1' AND status='pending'`
- **Assert**: Query plan uses `idx_tickets_occurrence_status` index
- **Lines Covered**: 101 (index creation)

##### TC-M006: PostgreSQL Migration 009 - Fresh Database
- **Purpose**: Verify PostgreSQL migration applies cleanly
- **Setup**:
  - Create temp PostgreSQL database
  - Apply migrations 001-008
- **Execute**: Apply migration 009
- **Assert**:
  - `agent_occurrence_id` column exists
  - Status CHECK constraint expanded
  - Index created
- **Lines Covered**: 1-39 (PostgreSQL migration)

##### TC-M007: PostgreSQL Migration 009 - Constraint Modification
- **Purpose**: Verify CHECK constraint properly dropped and recreated
- **Setup**: PostgreSQL database with migration 008
- **Execute**: Apply migration 009
- **Assert**:
  - Old `tickets_status_check` constraint dropped
  - New constraint with 8 states active
- **Lines Covered**: 21-30 (constraint modification)

##### TC-M008: Migration Idempotency
- **Purpose**: Verify migration can't be applied twice
- **Setup**: Database with migration 009 applied
- **Execute**: Attempt to apply migration 009 again
- **Assert**: Migration skipped (already in schema_migrations table)
- **Lines Covered**: Migration tracking logic

##### TC-M009: Transaction Rollback on Error
- **Purpose**: Verify transaction rolls back if migration fails
- **Setup**: Database with migrations 001-008
- **Execute**:
  - Inject syntax error into migration 009
  - Attempt to apply
- **Assert**:
  - Migration fails
  - Database state unchanged (no partial application)
  - Transaction rolled back
- **Lines Covered**: 9-11, 110-114 (transaction boundaries)

**Total Test Cases**: 9
**Estimated Lines Covered**: 153/153 (100%)

---

## 4. Core Tool Service Testing

### 4.1 Test File: `test_ticket_tools.py`

**Location**: `tests/ciris_engine/logic/services/tools/core_tool_service/test_ticket_tools.py`

**Lines to Cover**: ~120 lines (new/modified methods in CoreToolService)

#### Test Cases:

##### TC-CT001: update_ticket Tool - Status Update
- **Purpose**: Verify status can be updated via tool
- **Setup**: Mock database with test ticket
- **Execute**: `execute_tool('update_ticket', {'ticket_id': 'T001', 'status': 'in_progress'})`
- **Assert**:
  - Tool returns success=True
  - Ticket status updated to 'in_progress'
  - `_tickets_updated` metric incremented
- **Lines Covered**: service.py:232-289

##### TC-CT002: update_ticket Tool - All 8 Status Values
- **Purpose**: Verify all 8 status values accepted
- **Setup**: Mock database with test ticket
- **Execute**: Update ticket sequentially through all 8 statuses
- **Assert**: Each status update succeeds
- **Lines Covered**: service.py:254-262

##### TC-CT003: update_ticket Tool - Metadata Deep Merge
- **Purpose**: Verify stages metadata deep merges correctly
- **Setup**:
  - Ticket with existing metadata:
    ```json
    {
      "stages": {
        "identity_resolution": {"status": "completed", "result": "user@example.com"},
        "data_collection": {"status": "in_progress"}
      }
    }
    ```
- **Execute**:
  ```python
  update_ticket('T001', metadata={
    "stages": {
      "data_collection": {"status": "completed", "result": {...}}
    },
    "current_stage": "data_packaging"
  })
  ```
- **Assert**:
  - `identity_resolution` stage preserved
  - `data_collection` stage updated (status + result)
  - `current_stage` added
- **Lines Covered**: service.py:263-285

##### TC-CT004: update_ticket Tool - Shallow Metadata Merge
- **Purpose**: Verify non-stages metadata does shallow merge
- **Setup**: Ticket with metadata: `{"foo": "bar", "baz": 1}`
- **Execute**: `update_ticket('T001', metadata={"foo": "updated", "new": "value"})`
- **Assert**: Metadata is `{"foo": "updated", "baz": 1, "new": "value"}`
- **Lines Covered**: service.py:269

##### TC-CT005: update_ticket Tool - Status + Metadata + Notes
- **Purpose**: Verify combined updates work
- **Execute**: `update_ticket('T001', status='blocked', metadata={...}, notes='Waiting for legal')`
- **Assert**: All three fields updated
- **Lines Covered**: service.py:252-285

##### TC-CT006: update_ticket Tool - Nonexistent Ticket
- **Purpose**: Verify error handling for missing ticket
- **Execute**: `update_ticket('NONEXISTENT', status='completed')`
- **Assert**: Returns success=False with error message
- **Lines Covered**: service.py:246-248

##### TC-CT007: defer_ticket Tool - Sets Status to Deferred
- **Purpose**: Verify defer_ticket automatically sets status='deferred'
- **Setup**: Ticket with status='in_progress'
- **Execute**: `defer_ticket('T001', defer_hours=24, reason='Awaiting data')`
- **Assert**:
  - Ticket status changed to 'deferred'
  - Metadata contains deferred_until timestamp
  - Response includes status_updated='deferred'
- **Lines Covered**: service.py:380-394

##### TC-CT008: defer_ticket Tool - Await Human
- **Purpose**: Verify defer with await_human flag
- **Execute**: `defer_ticket('T001', await_human=True, reason='Legal review needed')`
- **Assert**:
  - Status set to 'deferred'
  - Metadata has awaiting_human_response=True
  - No deferred_until timestamp
- **Lines Covered**: service.py:328-334, 380-394

##### TC-CT009: defer_ticket Tool - Defer Until Timestamp
- **Purpose**: Verify defer with absolute timestamp
- **Execute**: `defer_ticket('T001', defer_until='2025-11-08T10:00:00Z', reason='Scheduled')`
- **Assert**:
  - Status set to 'deferred'
  - Metadata has deferred_until='2025-11-08T10:00:00Z'
- **Lines Covered**: service.py:335-342, 380-394

##### TC-CT010: defer_ticket Tool - Defer Hours
- **Purpose**: Verify defer with relative hours
- **Execute**: `defer_ticket('T001', defer_hours=48, reason='Wait period')`
- **Assert**:
  - Status set to 'deferred'
  - Metadata has deferred_until = now + 48 hours
- **Lines Covered**: service.py:344-353, 380-394

##### TC-CT011: defer_ticket Tool - Missing Parameters
- **Purpose**: Verify error when no defer parameters provided
- **Execute**: `defer_ticket('T001', reason='Test')`
- **Assert**: Returns error "Must provide defer_until, defer_hours, or await_human=true"
- **Lines Covered**: service.py:375-378

##### TC-CT012: get_tool_info - update_ticket
- **Purpose**: Verify tool info includes all 8 status values
- **Execute**: `get_tool_info('update_ticket')`
- **Assert**:
  - Returns ToolInfo
  - Status enum includes all 8 values
- **Lines Covered**: service.py:427-450

##### TC-CT013: Tool Metrics - Tickets Updated
- **Purpose**: Verify _tickets_updated metric tracked
- **Setup**: Execute 3 update_ticket calls
- **Execute**: `get_metrics()`
- **Assert**: `tickets_updated_total` = 3.0
- **Lines Covered**: service.py:287, 591

##### TC-CT014: Tool Metrics - Tickets Deferred
- **Purpose**: Verify _tickets_deferred metric tracked
- **Setup**: Execute 2 defer_ticket calls
- **Execute**: `get_metrics()`
- **Assert**: `tickets_deferred_total` = 2.0
- **Lines Covered**: service.py:392, 593

**Total Test Cases**: 14
**Estimated Lines Covered**: 120/120 (100%)

---

## 5. WorkProcessor Testing

### 5.1 Test File: `test_work_processor_tickets.py`

**Location**: `tests/ciris_engine/logic/processors/states/test_work_processor_tickets.py`

**Lines to Cover**: ~200 lines (_discover_incomplete_tickets method)

#### Test Cases:

##### TC-WP001: Phase 1 - Claim Single PENDING Ticket
- **Purpose**: Verify occurrence can claim PENDING ticket with __shared__
- **Setup**:
  - Create ticket: status='pending', agent_occurrence_id='__shared__'
  - WorkProcessor with occurrence_id='occurrence-1'
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**:
  - Ticket status updated to 'assigned'
  - Ticket agent_occurrence_id updated to 'occurrence-1'
  - Seed task created with source='ticket_claim'
  - Returns tasks_created=1
- **Lines Covered**: work_processor.py:296-373

##### TC-WP002: Phase 1 - Atomic Claiming Race Condition
- **Purpose**: Verify only ONE occurrence claims shared ticket
- **Setup**:
  - Create ticket: status='pending', agent_occurrence_id='__shared__'
  - Two WorkProcessors: occurrence-1 and occurrence-2
- **Execute**: Both call `_discover_incomplete_tickets()` simultaneously
- **Assert**:
  - Only one occurrence successfully claims (try_claim_shared_task() atomic)
  - Only one task created
  - Second occurrence logs "Another occurrence already claimed"
- **Lines Covered**: work_processor.py:316-323

##### TC-WP003: Phase 1 - Skip Non-Shared PENDING Tickets
- **Purpose**: Verify occurrence skips PENDING tickets already assigned
- **Setup**: Create ticket: status='pending', agent_occurrence_id='occurrence-2'
- **Execute**: WorkProcessor occurrence-1 calls `_discover_incomplete_tickets()`
- **Assert**:
  - Ticket NOT claimed
  - No task created
  - Logs "Ticket not shared, skipping claim attempt"
- **Lines Covered**: work_processor.py:305-308

##### TC-WP004: Phase 1 - Skip BLOCKED Tickets
- **Purpose**: Verify PENDING+BLOCKED tickets not claimed
- **Setup**: Create ticket: status='blocked', agent_occurrence_id='__shared__'
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**:
  - Ticket NOT claimed
  - No task created
  - Logs "Ticket has status blocked, skipping"
- **Lines Covered**: work_processor.py:310-314

##### TC-WP005: Phase 1 - Skip DEFERRED Tickets
- **Purpose**: Verify PENDING+DEFERRED tickets not claimed
- **Setup**: Create ticket: status='deferred', agent_occurrence_id='__shared__'
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**: Ticket NOT claimed, no task created
- **Lines Covered**: work_processor.py:310-314

##### TC-WP006: Phase 1 - Claim Failure Handling
- **Purpose**: Verify graceful handling when status update fails
- **Setup**:
  - Mock update_ticket_status to return False
  - PENDING ticket with __shared__
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**:
  - Claim succeeds but status update fails
  - No task created
  - Logs "Failed to update ticket to assigned status"
- **Lines Covered**: work_processor.py:325-335

##### TC-WP007: Phase 1 - Task Creation Failure
- **Purpose**: Verify logging when task creation fails after claim
- **Setup**: Mock add_task to return False
- **Execute**: Claim and attempt task creation
- **Assert**: Logs "Claimed ticket but failed to create task"
- **Lines Covered**: work_processor.py:357-373

##### TC-WP008: Phase 2 - Create Continuation Task for ASSIGNED
- **Purpose**: Verify continuation task created for ASSIGNED ticket
- **Setup**: Create ticket: status='assigned', agent_occurrence_id='occurrence-1'
- **Execute**: WorkProcessor occurrence-1 calls `_discover_incomplete_tickets()`
- **Assert**:
  - Task created with source='ticket_continuation'
  - Task correlation_id = ticket_id
  - Returns tasks_created=1
- **Lines Covered**: work_processor.py:375-455

##### TC-WP009: Phase 2 - Create Continuation Task for IN_PROGRESS
- **Purpose**: Verify continuation task created for IN_PROGRESS ticket
- **Setup**: Create ticket: status='in_progress', agent_occurrence_id='occurrence-1'
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**: Task created with source='ticket_continuation'
- **Lines Covered**: work_processor.py:375-455

##### TC-WP010: Phase 2 - Skip Different Occurrence
- **Purpose**: Verify occurrence only processes its own tickets
- **Setup**: Create ticket: status='assigned', agent_occurrence_id='occurrence-2'
- **Execute**: WorkProcessor occurrence-1 calls `_discover_incomplete_tickets()`
- **Assert**:
  - No task created
  - Logs "Ticket assigned to different occurrence, skipping"
- **Lines Covered**: work_processor.py:385-388

##### TC-WP011: Phase 2 - Skip BLOCKED Tickets
- **Purpose**: Verify BLOCKED tickets don't generate continuation tasks
- **Setup**: Create ticket: status='blocked', agent_occurrence_id='occurrence-1'
- **Execute**: WorkProcessor occurrence-1 calls `_discover_incomplete_tickets()`
- **Assert**: No task created, logs "Ticket is blocked, skipping task creation"
- **Lines Covered**: work_processor.py:390-394

##### TC-WP012: Phase 2 - Skip DEFERRED Tickets
- **Purpose**: Verify DEFERRED tickets don't generate continuation tasks
- **Setup**: Create ticket: status='deferred', agent_occurrence_id='occurrence-1'
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**: No task created
- **Lines Covered**: work_processor.py:390-394

##### TC-WP013: Phase 2 - Skip Tickets with Active Tasks
- **Purpose**: Verify no duplicate tasks created
- **Setup**:
  - Create ticket: status='in_progress', agent_occurrence_id='occurrence-1'
  - Create ACTIVE task with correlation_id=ticket_id
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**:
  - No new task created
  - Logs "Ticket already has active task, skipping"
- **Lines Covered**: work_processor.py:396-402

##### TC-WP014: Phase 2 - Respect Deferred Until Timestamp (Not Expired)
- **Purpose**: Verify tickets with future deferred_until skip task creation
- **Setup**:
  - Ticket: status='in_progress', metadata={'deferred_until': '2025-11-08T00:00:00Z'}
  - Current time: 2025-11-07T12:00:00Z
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**: No task created, logs "Ticket deferred until..."
- **Lines Covered**: work_processor.py:404-414

##### TC-WP015: Phase 2 - Deferred Until Expired (Create Task)
- **Purpose**: Verify expired deferred_until allows task creation
- **Setup**:
  - Ticket: status='in_progress', metadata={'deferred_until': '2025-11-06T00:00:00Z'}
  - Current time: 2025-11-07T12:00:00Z
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**: Task created (deferral expired)
- **Lines Covered**: work_processor.py:404-414

##### TC-WP016: Phase 2 - Skip Awaiting Human Response
- **Purpose**: Verify awaiting_human_response prevents task creation
- **Setup**: Ticket with metadata={'awaiting_human_response': True}
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**: No task created, logs "Ticket awaiting human response"
- **Lines Covered**: work_processor.py:416-418

##### TC-WP017: Phase 2 - Invalid Deferred Until Format
- **Purpose**: Verify graceful handling of invalid timestamp
- **Setup**: Ticket with metadata={'deferred_until': 'invalid-date'}
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**:
  - Task creation continues (invalid format ignored)
  - Logs warning "Invalid deferred_until format"
- **Lines Covered**: work_processor.py:406-414

##### TC-WP018: Two-Phase Combined - Multiple Tickets
- **Purpose**: Verify both phases work together
- **Setup**:
  - Ticket A: status='pending', agent_occurrence_id='__shared__'
  - Ticket B: status='assigned', agent_occurrence_id='occurrence-1'
  - Ticket C: status='in_progress', agent_occurrence_id='occurrence-1'
  - Ticket D: status='blocked', agent_occurrence_id='occurrence-1'
- **Execute**: WorkProcessor occurrence-1 calls `_discover_incomplete_tickets()`
- **Assert**:
  - Ticket A: Claimed + task created (Phase 1)
  - Ticket B: Continuation task created (Phase 2)
  - Ticket C: Continuation task created (Phase 2)
  - Ticket D: No task created (BLOCKED)
  - Returns tasks_created=3
- **Lines Covered**: work_processor.py:263-463 (full method)

##### TC-WP019: Task Context Structure
- **Purpose**: Verify seed/continuation tasks have correct context
- **Execute**: Create task for ticket
- **Assert**: Task context includes:
  - ticket_id
  - ticket_sop
  - ticket_type
  - ticket_status
  - ticket_metadata
  - ticket_priority
  - ticket_email
  - ticket_user_identifier
  - is_ticket_task=True
- **Lines Covered**: work_processor.py:343-355, 427-437

##### TC-WP020: Error Handling - Exception During Discovery
- **Purpose**: Verify exceptions logged and don't crash processor
- **Setup**: Mock list_tickets to raise Exception
- **Execute**: `_discover_incomplete_tickets()`
- **Assert**:
  - Exception logged with full traceback
  - Returns tasks_created=0
  - Processor continues running
- **Lines Covered**: work_processor.py:460-463

**Total Test Cases**: 20
**Estimated Lines Covered**: 200/200 (100%)

---

## 6. Tickets Persistence Model Testing

### 6.1 Test File: `test_tickets.py`

**Location**: `tests/ciris_engine/logic/persistence/models/test_tickets.py`

**Lines to Cover**: ~56 lines (update_ticket_status modifications)

#### Test Cases:

##### TC-TP001: update_ticket_status - Status Only
- **Purpose**: Verify updating status alone
- **Setup**: Create test ticket
- **Execute**: `update_ticket_status('T001', 'in_progress')`
- **Assert**:
  - Status updated
  - last_updated timestamp updated
  - completed_at remains NULL
  - Returns True
- **Lines Covered**: tickets.py:137-192

##### TC-TP002: update_ticket_status - Status + Notes
- **Purpose**: Verify status update with notes
- **Execute**: `update_ticket_status('T001', 'blocked', notes='Waiting for approval')`
- **Assert**:
  - Status and notes updated
  - last_updated timestamp updated
- **Lines Covered**: tickets.py:163-165

##### TC-TP003: update_ticket_status - Status + Agent Occurrence ID
- **Purpose**: Verify updating agent_occurrence_id during status change
- **Execute**: `update_ticket_status('T001', 'assigned', agent_occurrence_id='occurrence-1')`
- **Assert**:
  - Status updated to 'assigned'
  - agent_occurrence_id updated to 'occurrence-1'
- **Lines Covered**: tickets.py:167-169

##### TC-TP004: update_ticket_status - All Parameters
- **Purpose**: Verify updating status + notes + occurrence_id
- **Execute**: `update_ticket_status('T001', 'assigned', notes='Claimed', agent_occurrence_id='occ-1')`
- **Assert**: All three fields updated
- **Lines Covered**: tickets.py:159-171

##### TC-TP005: update_ticket_status - Terminal Status Sets completed_at
- **Purpose**: Verify completed_at set for terminal statuses
- **Execute**:
  - `update_ticket_status('T001', 'completed')`
  - `update_ticket_status('T002', 'failed')`
  - `update_ticket_status('T003', 'cancelled')`
- **Assert**: All three tickets have completed_at timestamp
- **Lines Covered**: tickets.py:157

##### TC-TP006: update_ticket_status - Non-Terminal Leaves completed_at NULL
- **Purpose**: Verify completed_at remains NULL for non-terminal statuses
- **Execute**: `update_ticket_status('T001', 'in_progress')`
- **Assert**: completed_at is NULL
- **Lines Covered**: tickets.py:157

##### TC-TP007: update_ticket_status - Nonexistent Ticket
- **Purpose**: Verify error handling for missing ticket
- **Execute**: `update_ticket_status('NONEXISTENT', 'completed')`
- **Assert**:
  - Returns False
  - Logs "Ticket NONEXISTENT not found for status update"
- **Lines Covered**: tickets.py:187-188

##### TC-TP008: update_ticket_status - Database Error
- **Purpose**: Verify exception handling
- **Setup**: Mock get_db_connection to raise exception
- **Execute**: `update_ticket_status('T001', 'completed')`
- **Assert**:
  - Returns False
  - Exception logged
- **Lines Covered**: tickets.py:190-192

##### TC-TP009: update_ticket_status - All 8 Status Values
- **Purpose**: Verify all status values accepted
- **Execute**: Update ticket through all 8 statuses sequentially
- **Assert**: Each update succeeds
- **Lines Covered**: tickets.py:137-192 (full method)

##### TC-TP010: update_ticket_status - Dynamic SQL Construction
- **Purpose**: Verify SQL builds correctly based on parameters
- **Setup**: Capture SQL via mock
- **Execute**: Various parameter combinations
- **Assert**: SQL includes only relevant SET clauses
- **Lines Covered**: tickets.py:160-177

**Total Test Cases**: 10
**Estimated Lines Covered**: 56/56 (100%)

---

## 7. Integration Testing

### 7.1 Test File: `test_ticket_lifecycle.py`

**Location**: `tests/ciris_engine/integration/test_ticket_lifecycle.py`

**Purpose**: End-to-end testing of ticket lifecycle across all components

#### Test Cases:

##### TC-INT001: Full DSAR Ticket Lifecycle
- **Purpose**: Test complete ticket flow from creation to completion
- **Scenario**:
  1. Create PENDING ticket via API
  2. WorkProcessor claims and assigns ticket
  3. Agent processes via Core Tool Service
  4. Agent updates status through stages
  5. Agent marks ticket completed
- **Assert**:
  - All status transitions valid
  - Tasks created at appropriate times
  - Metadata properly tracked
- **Components Tested**: All

##### TC-INT002: Ticket Deferral and Resume
- **Purpose**: Test defer and resume workflow
- **Scenario**:
  1. Create and assign ticket
  2. Agent defers ticket (status → deferred)
  3. WorkProcessor stops creating tasks
  4. Admin updates status back to in_progress
  5. WorkProcessor resumes creating tasks
- **Assert**: Task generation controlled by status
- **Components Tested**: CoreToolService, WorkProcessor

##### TC-INT003: Multi-Occurrence Coordination
- **Purpose**: Test multiple occurrences don't conflict
- **Scenario**:
  1. Create 10 PENDING tickets with __shared__
  2. Spin up 3 WorkProcessor occurrences
  3. All occurrences discover tickets simultaneously
- **Assert**:
  - Each ticket claimed by exactly ONE occurrence
  - 10 tasks total created (no duplicates)
- **Components Tested**: WorkProcessor, Persistence

##### TC-INT004: Blocked Ticket Prevents Task Generation
- **Purpose**: Test BLOCKED status stops workflow
- **Scenario**:
  1. Agent sets ticket status to 'blocked'
  2. WorkProcessor runs discovery
- **Assert**: No tasks created for blocked ticket
- **Components Tested**: CoreToolService, WorkProcessor

##### TC-INT005: Migration + Runtime Integration
- **Purpose**: Test migration applied correctly at runtime
- **Scenario**:
  1. Start system with fresh database
  2. Migrations auto-run (including 009)
  3. Create ticket with new status values
  4. Process ticket
- **Assert**: System operates normally with new schema
- **Components Tested**: All

**Total Test Cases**: 5
**Estimated Lines Covered**: Integration scenarios

---

## 8. Test Implementation Priority

### Phase 1: Foundation (High Priority)
1. **TC-M001 to TC-M009** - Migration tests
2. **TC-TP001 to TC-TP010** - Persistence model tests

### Phase 2: Core Functionality (High Priority)
3. **TC-CT001 to TC-CT014** - Core Tool Service tests
4. **TC-WP001 to TC-WP020** - WorkProcessor tests

### Phase 3: Integration (Medium Priority)
5. **TC-INT001 to TC-INT005** - Integration tests

---

## 9. Test Coverage Summary

| Component | Test File | Test Cases | Lines to Cover | Estimated Coverage |
|-----------|-----------|------------|----------------|-------------------|
| Migration 009 | test_migration_009.py | 9 | 153 | 100% |
| Core Tool Service | test_ticket_tools.py | 14 | 120 | 100% |
| WorkProcessor | test_work_processor_tickets.py | 20 | 200 | 100% |
| Tickets Model | test_tickets.py | 10 | 56 | 100% |
| Integration | test_ticket_lifecycle.py | 5 | N/A | E2E coverage |
| **TOTAL** | **5 files** | **58 tests** | **~529 lines** | **100%** |

---

## 10. Testing Tools and Utilities

### 10.1 Test Fixtures

**Common Fixtures** (to be shared across test files):

```python
# conftest.py additions

@pytest.fixture
def temp_db_with_tickets():
    """Create temp database with migrations 001-009 applied."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    # Apply migrations
    for i in range(1, 10):
        apply_migration(db_path, f"{i:03d}_*.sql")

    yield db_path
    os.unlink(db_path)

@pytest.fixture
def mock_ticket_data():
    """Standard test ticket data."""
    return {
        'ticket_id': 'TEST-001',
        'sop': 'DSAR_ACCESS',
        'ticket_type': 'dsar',
        'status': 'pending',
        'priority': 5,
        'email': 'user@example.com',
        'user_identifier': 'user123',
        'submitted_at': '2025-11-07T10:00:00Z',
        'metadata': {'stages': {}},
        'agent_occurrence_id': '__shared__'
    }

@pytest.fixture
def work_processor_with_tickets(temp_db_with_tickets, mock_ticket_data):
    """WorkProcessor instance with test tickets."""
    # Create processor
    config = Mock()
    config.db_path = temp_db_with_tickets
    config.agent_occurrence_id = 'occurrence-1'

    processor = WorkProcessor(config, ...)

    # Insert test tickets
    insert_test_ticket(temp_db_with_tickets, mock_ticket_data)

    return processor
```

### 10.2 Helper Functions

```python
def insert_test_ticket(db_path, ticket_data):
    """Insert test ticket into database."""
    from ciris_engine.logic.persistence.models.tickets import create_ticket
    return create_ticket(**ticket_data, db_path=db_path)

def assert_ticket_status(db_path, ticket_id, expected_status):
    """Assert ticket has expected status."""
    from ciris_engine.logic.persistence.models.tickets import get_ticket
    ticket = get_ticket(ticket_id, db_path=db_path)
    assert ticket['status'] == expected_status

def assert_task_count_for_ticket(db_path, ticket_id, expected_count):
    """Assert number of tasks created for ticket."""
    from ciris_engine.logic.persistence.models.tasks import get_all_tasks
    tasks = [t for t in get_all_tasks(db_path=db_path)
             if t.get('correlation_id') == ticket_id]
    assert len(tasks) == expected_count
```

---

## 11. Success Criteria

### 11.1 Coverage Metrics
- **Line Coverage**: ≥95% for all new/modified code
- **Branch Coverage**: ≥90% for conditional logic
- **Integration Coverage**: All critical paths tested E2E

### 11.2 Test Quality
- All tests pass consistently (no flaky tests)
- All tests run in <30 seconds total
- Tests are isolated (no cross-test dependencies)
- Mock usage minimized for integration tests

### 11.3 Documentation
- Each test has clear docstring explaining purpose
- Complex test scenarios have inline comments
- Test data is self-explanatory

---

## 12. Rollout Plan

1. Implement Phase 1 tests (migrations, persistence)
2. Run tests, verify 100% pass
3. Implement Phase 2 tests (service, processor)
4. Run full test suite, verify coverage ≥95%
5. Implement Phase 3 integration tests
6. Final coverage report
7. Update CHANGELOG with test coverage metrics

---

## 14. Notes and Considerations

### 14.1 Known Challenges

1. **Migration Testing**:
   - SQLite view validation error (active_scheduled_tasks)
   - May need to fix pre-existing schema bug first

2. **Multi-Occurrence Testing**:
   - Requires proper mocking of try_claim_shared_task()
   - Need to simulate race conditions

3. **Async Testing**:
   - Core Tool Service methods are async
   - Requires pytest-asyncio

### 14.2 Test Dependencies

- pytest ≥7.0
- pytest-asyncio
- pytest-mock
- Coverage.py

---

**End of Test Plan**
