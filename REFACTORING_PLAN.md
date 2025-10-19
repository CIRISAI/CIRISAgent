# PostgreSQL Dialect Refactoring Plan

## Summary

**Goal**: Replace all raw SQL `INSERT OR IGNORE` statements with dialect-aware operations layer calls.

**Test Coverage**:
- ✅ 24 query builder tests passing
- ✅ 10 operations layer tests passing
- Total: 34 comprehensive unit tests

**Locations to Refactor**: 9 instances in `edge_manager.py`

---

## Files Requiring Refactoring

### 1. `ciris_engine/logic/services/graph/tsdb_consolidation/edge_manager.py` (9 instances)

**Line 213**: `create_cross_summary_edges()` - Batch insert edges
**Line 256**: `create_temporal_edges()` - Insert TEMPORAL_NEXT edge
**Line 387**: `create_concept_edges()` - Batch insert concept edges
**Line 528**: `create_user_participation_edges()` - Insert user nodes
**Line 582**: `create_user_participation_edges()` - Batch insert participation edges
**Line 700**: `_create_missing_channel_node()` - Insert channel nodes
**Line 829**: `create_edges()` - Batch insert edges
**Line 894**: `update_next_period_edges()` - Insert TEMPORAL_NEXT edge
**Line 918**: `update_next_period_edges()` - Insert TEMPORAL_PREV edge

---

## Parallel Refactoring Strategy

### Option A: Git Worktrees (RECOMMENDED)

Use git worktrees to create isolated working directories for parallel refactoring:

```bash
# Create main worktree directory
mkdir -p /tmp/ciris_refactor

# Create worktrees for parallel work
git worktree add /tmp/ciris_refactor/task1 -b refactor/edge-manager-part1
git worktree add /tmp/ciris_refactor/task2 -b refactor/edge-manager-part2
git worktree add /tmp/ciris_refactor/task3 -b refactor/edge-manager-part3

# List all worktrees
git worktree list
```

**Benefits**:
- True parallel execution (separate directories)
- No merge conflicts during work
- Can test each branch independently
- Easy to merge incrementally

### Option B: Sequential Refactoring (FALLBACK)

If worktrees cause issues, refactor sequentially in a single branch.

---

## Task Breakdown for Parallel Execution

### Task 1: Node Creation Methods (3 instances)
**Branch**: `refactor/edge-manager-nodes`
**Worktree**: `/tmp/ciris_refactor/nodes`

**Files**:
- `edge_manager.py:528` - `create_user_participation_edges()` - user nodes
- `edge_manager.py:700` - `_create_missing_channel_node()` - channel nodes
- First instance at line ~105 (already partially refactored)

**Pattern**:
```python
# OLD:
cursor.execute("""
    INSERT OR IGNORE INTO graph_nodes
    (node_id, scope, node_type, attributes_json, version, updated_by, updated_at, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (node_id, scope, node_type, json.dumps(attrs), version, updated_by, now, now))

# NEW:
insert_node_if_not_exists(
    node_id=node_id,
    scope=scope,
    node_type=node_type,
    attributes=attrs,
    version=version,
    updated_by=updated_by,
    db_path=self._db_path
)
```

**Estimated Time**: 15 minutes
**Test Command**: `pytest tests/services/graph/tsdb_consolidation/ -k "edge_manager" -v`

---

### Task 2: Batch Edge Methods (3 instances)
**Branch**: `refactor/edge-manager-batch`
**Worktree**: `/tmp/ciris_refactor/batch`

**Files**:
- `edge_manager.py:213` - `create_cross_summary_edges()`
- `edge_manager.py:387` - `create_concept_edges()`
- `edge_manager.py:582` - `create_user_participation_edges()`

**Pattern**:
```python
# OLD:
cursor.executemany("""
    INSERT OR IGNORE INTO graph_edges
    (edge_id, source_node_id, target_node_id, scope, relationship, weight, attributes_json, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", edge_data)
edges_created = cursor.rowcount
conn.commit()

# NEW:
edges_created = batch_insert_edges_if_not_exist(edge_data, db_path=self._db_path)
```

**Estimated Time**: 20 minutes
**Test Command**: `pytest tests/services/graph/tsdb_consolidation/ -k "cross_summary or concept or participation" -v`

---

### Task 3: Temporal & Update Methods (4 instances)
**Branch**: `refactor/edge-manager-temporal`
**Worktree**: `/tmp/ciris_refactor/temporal`

**Files**:
- `edge_manager.py:256` - `create_temporal_edges()` - TEMPORAL_NEXT self-ref
- `edge_manager.py:829` - `create_edges()` - general batch insert
- `edge_manager.py:894` - `update_next_period_edges()` - forward edge
- `edge_manager.py:918` - `update_next_period_edges()` - backward edge

**Pattern for single inserts**:
```python
# OLD:
cursor.execute("""
    INSERT OR IGNORE INTO graph_edges
    (edge_id, source_node_id, target_node_id, scope, relationship, weight, attributes_json, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (edge_id, source_id, target_id, scope, rel, weight, attrs_json, now))

# NEW:
insert_edge_if_not_exists(
    edge_id=edge_id,
    source_node_id=source_id,
    target_node_id=target_id,
    scope=scope,
    relationship=rel,
    weight=weight,
    attributes=attrs,  # Pass dict, not JSON string
    db_path=self._db_path
)
```

**Pattern for batch inserts**:
```python
# OLD:
cursor.executemany("""INSERT OR IGNORE...""", edge_data)

# NEW:
batch_insert_edges_if_not_exist(edge_data, db_path=self._db_path)
```

**Estimated Time**: 25 minutes
**Test Command**: `pytest tests/services/graph/tsdb_consolidation/ -k "temporal or create_edges" -v`

---

## Execution Plan

### Phase 1: Setup (5 minutes)

```bash
# Ensure we're on main branch
git checkout main
git pull origin main

# Create worktree directory
mkdir -p /tmp/ciris_refactor

# Create all three worktrees
git worktree add /tmp/ciris_refactor/nodes -b refactor/edge-manager-nodes
git worktree add /tmp/ciris_refactor/batch -b refactor/edge-manager-batch
git worktree add /tmp/ciris_refactor/temporal -b refactor/edge-manager-temporal

# Verify worktrees created
git worktree list
```

### Phase 2: Parallel Refactoring (20-25 minutes)

**In 3 separate terminal sessions/Claude agents**:

```bash
# Terminal 1 - Node Creation
cd /tmp/ciris_refactor/nodes
# Refactor node creation instances
# Run tests: pytest tests/services/graph/tsdb_consolidation/ -k "edge_manager" -v

# Terminal 2 - Batch Edges
cd /tmp/ciris_refactor/batch
# Refactor batch edge instances
# Run tests: pytest tests/services/graph/tsdb_consolidation/ -k "cross_summary or concept or participation" -v

# Terminal 3 - Temporal Edges
cd /tmp/ciris_refactor/temporal
# Refactor temporal edge instances
# Run tests: pytest tests/services/graph/tsdb_consolidation/ -k "temporal or create_edges" -v
```

### Phase 3: Integration (10 minutes)

```bash
# Return to main repo
cd /home/emoore/CIRISAgent

# Merge branches sequentially to avoid conflicts
git checkout main
git merge refactor/edge-manager-nodes
git merge refactor/edge-manager-batch
git merge refactor/edge-manager-temporal

# Run full test suite
pytest tests/persistence/ -v
pytest tests/services/graph/tsdb_consolidation/ -v

# Run PostgreSQL integration test
export CIRIS_DB_URL='postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db'
python main.py --adapter cli --mock-llm --timeout 10
```

### Phase 4: Cleanup (2 minutes)

```bash
# Remove worktrees
git worktree remove /tmp/ciris_refactor/nodes
git worktree remove /tmp/ciris_refactor/batch
git worktree remove /tmp/ciris_refactor/temporal

# Delete merged branches
git branch -d refactor/edge-manager-nodes
git branch -d refactor/edge-manager-batch
git branch -d refactor/edge-manager-temporal

# Remove worktree directory
rm -rf /tmp/ciris_refactor
```

---

## Testing Strategy

### Unit Tests (Already Created)
- ✅ `tests/persistence/test_query_builder.py` (24 tests)
- ✅ `tests/persistence/test_operations.py` (10 tests)

### Integration Tests
```bash
# SQLite (existing tests)
pytest tests/services/graph/tsdb_consolidation/ -v

# PostgreSQL (manual verification)
export CIRIS_DB_URL='postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db'
python main.py --adapter cli --mock-llm --timeout 10

# Check incidents log
tail -f logs/incidents_latest.log | grep -i "INSERT OR"
```

### Success Criteria
- ✅ All unit tests pass (34 tests)
- ✅ All integration tests pass
- ✅ No `INSERT OR IGNORE` errors in PostgreSQL logs
- ✅ Zero raw SQL `INSERT OR IGNORE` statements in `edge_manager.py`
- ✅ Code runs successfully with both SQLite and PostgreSQL

---

## Risk Mitigation

### Potential Issues

1. **Transaction Management**: Operations layer creates its own connections
   - **Mitigation**: Ensure `db_path` parameter is passed correctly
   - **Test**: Verify nodes/edges appear in database after calls

2. **JSON Serialization**: Operations layer expects dict, not JSON string
   - **Mitigation**: Pass `attributes={...}` not `json.dumps({...})`
   - **Test**: Verify attributes round-trip correctly

3. **Return Values**: `batch_insert_edges_if_not_exist` returns count, not rowcount
   - **Mitigation**: Use returned count directly
   - **Test**: Verify edge counts match expectations

4. **Connection Management**: Mixing cursor usage with operations layer
   - **Mitigation**: Minimize direct cursor usage, prefer operations layer
   - **Test**: No connection leaks or deadlocks

### Rollback Plan

If issues arise:
```bash
# Abort merge
git merge --abort

# Return to previous state
git reset --hard origin/main

# Remove problematic branches
git branch -D refactor/edge-manager-*

# Clean up worktrees
git worktree prune
```

---

## Post-Refactoring Tasks

1. **Code Review**: Review all changes for correctness
2. **Performance Testing**: Ensure no performance regression
3. **Documentation**: Update docstrings if needed
4. **Commit Message**: Write comprehensive commit message
5. **PR Creation**: Create PR with detailed description
6. **CI/CD Verification**: Ensure all CI checks pass

---

## Timeline

| Phase | Task | Duration | Total |
|-------|------|----------|-------|
| 1 | Setup worktrees | 5 min | 5 min |
| 2 | Parallel refactoring | 25 min | 30 min |
| 3 | Integration & testing | 10 min | 40 min |
| 4 | Cleanup | 2 min | 42 min |
| 5 | Documentation & PR | 10 min | 52 min |

**Total Estimated Time**: ~1 hour

---

## Notes

- All refactored code should use the operations layer exclusively
- No direct SQL generation in business logic
- All database dialect logic encapsulated in persistence layer
- Full PostgreSQL compatibility guaranteed by query builder
- Extensible to future database backends (MySQL, MariaDB, etc.)
