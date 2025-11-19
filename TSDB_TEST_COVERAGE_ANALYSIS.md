# TSDB Test Coverage Analysis for Release 1.6.2

## Changes Made in 1.6.2

### 1. PostgreSQL Placeholder Fix (Commit 10267671)
**Files Changed:**
- `ciris_engine/logic/services/graph/tsdb_consolidation/edge_manager.py` (5 locations)

**Changes:**
```python
# BEFORE (hardcoded SQLite placeholder):
cursor.execute("SELECT node_id FROM graph_nodes WHERE node_id = ?", (...))

# AFTER (dialect-aware):
adapter = get_adapter()
ph = adapter.placeholder()
cursor.execute(f"SELECT node_id FROM graph_nodes WHERE node_id = {ph}", (...))
```

**Locations Fixed:**
1. Line 74: `create_summary_edges()`
2. Line 155: `create_summary_edges()`
3. Line 399: `get_previous_summary_id()` ⚠️ **CRITICAL**
4. Line 480: `create_user_participation_edges()`
5. Line 838: `link_to_next_period()`

### 2. Timeline Gap Fix (Commit 74c756e5)
**Files Changed:**
- `ciris_engine/logic/services/graph/tsdb_consolidation/edge_manager.py`
- `ciris_engine/logic/services/graph/tsdb_consolidation/service.py`

**Changes:**
```python
# BEFORE (assumed 6-hour intervals):
def get_previous_summary_id(self, node_type_prefix: str, previous_period_id: str)
    node_id_pattern = f"{node_type_prefix}_{previous_period_id}"
    cursor.execute("SELECT node_id ... WHERE node_id = ?", (node_id_pattern,))

# AFTER (handles any gap):
def get_previous_summary_id(self, node_type_prefix: str, current_node_id: str)
    cursor.execute("""
        SELECT node_id FROM graph_nodes
        WHERE node_id LIKE ? AND node_id < ?
        ORDER BY node_id DESC LIMIT 1
    """, (f"{node_type_prefix}_%", current_node_id))
```

## Current Test Coverage Issues

### ❌ BROKEN TESTS (Using Old Signature)

**File:** `tests/ciris_engine/logic/services/graph/test_tsdb_edge_creation.py`

**Line 1154** - `test_get_previous_summary_id_daily()`:
```python
# WRONG - Uses old signature (period_id)
result = edge_manager.get_previous_summary_id("tsdb_summary_daily", "20250714")

# SHOULD BE - New signature (current_node_id)
result = edge_manager.get_previous_summary_id(
    "tsdb_summary_daily",
    "tsdb_summary_daily_20250715"  # Current node, not period
)
```

**Line 1194** - `test_get_previous_summary_id_regular()`:
```python
# WRONG
result = edge_manager.get_previous_summary_id("tsdb_summary", previous_period_id)

# SHOULD BE
result = edge_manager.get_previous_summary_id(
    "tsdb_summary",
    f"tsdb_summary_{current_period_id}"
)
```

### ⚠️ COVERAGE GAPS

1. **PostgreSQL Dialect Testing**
   - ✅ Tests use SQLite (mock_db_connection)
   - ❌ No tests verify PostgreSQL placeholder (`%s` vs `?`)
   - ❌ No tests for all 5 locations where placeholders were fixed

2. **Timeline Gap Scenarios**
   - ✅ `test_gap_in_temporal_chain()` exists but uses manual edge creation
   - ❌ Doesn't test `get_previous_summary_id()` with multi-day gaps
   - ❌ Doesn't test multi-week gaps (production bug scenario)

3. **Service Integration**
   - ✅ `test_create_daily_summary_edges_correct_id_parsing()` tests service
   - ❌ Doesn't verify the new `get_previous_summary_id()` is called correctly
   - ❌ Doesn't test service behavior with gaps in consolidation schedule

## Recommended Test Additions

### 1. Fix Existing Tests (CRITICAL)
```python
# tests/ciris_engine/logic/services/graph/test_tsdb_edge_creation.py

def test_get_previous_summary_id_with_gaps(self, edge_manager, mock_db_connection):
    """Test get_previous_summary_id finds previous summary despite gaps."""
    # Create summaries with 9-day gap (like production bug)
    # Nov 7, Nov 9, Nov 17
    # Query for Nov 17 should find Nov 9, not Nov 16

def test_get_previous_summary_id_no_previous(self, edge_manager, mock_db_connection):
    """Test get_previous_summary_id returns None for first summary."""
    # First summary ever - should return None

def test_get_previous_summary_id_with_prefix_collision(self, edge_manager, mock_db_connection):
    """Test prefix matching doesn't match similar prefixes."""
    # tsdb_summary vs tsdb_summary_daily - should not cross-match
```

### 2. Add PostgreSQL Dialect Tests
```python
def test_placeholder_compatibility_postgresql(self, edge_manager):
    """Test that queries use dialect-aware placeholders for PostgreSQL."""
    # Mock PostgreSQL adapter, verify %s is used instead of ?

def test_all_edge_manager_queries_use_placeholders(self):
    """Verify all 5 fixed locations use adapter.placeholder()."""
    # Static analysis or mocking to ensure no hardcoded ? remains
```

### 3. Add Integration Tests
```python
def test_consolidation_with_multi_day_gap(self):
    """Test full consolidation flow with 9-day gap between consolidations."""
    # Simulate production scenario: Scout 001 with gaps

def test_temporal_chain_integrity_after_gap(self):
    """Verify temporal edges form complete chain despite gaps."""
    # Create summaries with gaps, verify TEMPORAL_NEXT/PREV navigate correctly
```

## Impact Assessment

### High Risk Areas (Low Coverage):
1. ⚠️ **`edge_manager.get_previous_summary_id()` NEW logic** - 0% coverage with new signature
2. ⚠️ **PostgreSQL placeholder handling** - 0% multi-dialect coverage
3. ⚠️ **Timeline gap edge creation** - Partial coverage (manual edges, not via service)

### Well-Covered Areas:
1. ✅ Temporal edge creation (general case)
2. ✅ Same-day cross-type edges
3. ✅ Duplicate prevention
4. ✅ Edge attributes and JSON handling
5. ✅ Cleanup and retry logic

## Action Items

1. **IMMEDIATE** - Fix broken tests using old signature (Lines 1154, 1194)
2. **HIGH PRIORITY** - Add gap scenario tests for `get_previous_summary_id()`
3. **MEDIUM PRIORITY** - Add PostgreSQL dialect tests
4. **LOW PRIORITY** - Add integration tests for full consolidation with gaps

## SonarCloud Coverage Metrics

**Before Fixes:**
- Likely showing lines 399-420 in edge_manager.py as uncovered (new query logic)
- Lines calling `get_previous_summary_id()` in service.py as uncovered

**After Test Fixes:**
- Should cover dialect adapter usage
- Should cover timeline gap query logic
- Should verify correct function signature usage
