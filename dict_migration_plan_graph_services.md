# Graph Services Dict[str, Any] Migration Plan

## Overview
Graph services have **77 Dict[str, Any] occurrences** that need to be migrated to Pydantic models with attributes.

## Top Offenders

### 1. Telemetry Service (18 occurrences)
**File:** `ciris_engine/logic/services/graph/telemetry_service/service.py`

**Current Issues:**
```python
# Line 124: Cache uses Dict[str, Any]
self.cache: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}

# Line 127: Return type mixes ServiceTelemetryData and Dict[str, Any]
async def collect_all_parallel(self) -> Dict[str, Dict[str, Union[ServiceTelemetryData, Dict[str, Any]]]]:
```

**Existing Schema:**
- ✅ `ServiceTelemetryData` (schemas/services/graph/telemetry.py:123)
  - Already has: healthy, uptime_seconds, error_count, requests_handled, error_rate, memory_mb
  - Has `custom_metrics: Optional[Dict[str, Union[int, float, str]]]` for service-specific data

**Migration Strategy:**
1. **Cache Type**: Change cache to store `ServiceTelemetryData` directly
   ```python
   # BEFORE
   self.cache: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}

   # AFTER
   self.cache: Dict[str, Tuple[datetime, ServiceTelemetryData]] = {}
   ```

2. **Return Types**: Use `ServiceTelemetryData` consistently
   ```python
   # BEFORE
   async def collect_all_parallel(self) -> Dict[str, Dict[str, Union[ServiceTelemetryData, Dict[str, Any]]]]:

   # AFTER
   async def collect_all_parallel(self) -> Dict[str, Dict[str, ServiceTelemetryData]]:
   ```

3. **Service-Specific Data**: Use `custom_metrics` field instead of arbitrary dicts

---

### 2. TSDB Data Converter (14 occurrences)
**File:** `ciris_engine/logic/services/graph/tsdb_consolidation/data_converter.py`

**Current Issues:**
```python
# Lines 95-102: Fields use complex Dict unions
request_data: Optional[Dict[str, str | int | float | bool | List[Any] | Dict[str, Any] | None]]
response_data: Optional[Dict[str, str | int | float | bool | List[Any] | Dict[str, Any] | None]]
tags: Optional[Dict[str, str | int | float | bool]]
context: Optional[Dict[str, str | int | float | bool | List[Any]]]

# Line 143: Helper functions accept Dict[str, Any]
def safe_dict_get(data: Dict[str, Any] | str | int | float | List[Any] | None, key: str, default: Any = None):
```

**Existing Schemas:**
- ✅ `RequestData` (schemas/services/graph/consolidation.py)
- ✅ `ResponseData` (schemas/services/graph/consolidation.py)
- ✅ `InteractionContext` (schemas/services/graph/consolidation.py)
- ✅ `SpanTags` (schemas/services/graph/consolidation.py)

**Migration Strategy:**
1. **Raw Data Models**: These are ALREADY using proper schemas! The Dict[str, Any] is in the NESTED fields
   - `request_data`, `response_data`, `tags`, `context` are all properly typed
   - The issue is these are OPTIONAL with complex union types

2. **Simplify Field Types**: Use the existing Pydantic schemas instead of dicts
   ```python
   # BEFORE
   request_data: Optional[Dict[str, str | int | float | bool | List[Any] | Dict[str, Any] | None]]

   # AFTER
   request_data: Optional[RequestData] = None
   ```

3. **Helper Functions**: Already properly converting to RequestData/ResponseData
   - `build_request_data_from_raw()` - converts dict → RequestData ✅
   - `build_response_data_from_raw()` - converts dict → ResponseData ✅
   - These are CORRECT - they accept dict input and return typed output

**Status:** 🟢 **Already 80% migrated!** Just need to update the Raw* model field types.

---

### 3. Memory Service (9 occurrences)
**File:** `ciris_engine/logic/services/graph/memory_service.py`

**Current Issues:**
```python
# Line 160: _process_node_for_recall returns dict
def _process_node_for_recall(...) -> Dict[str, Any]:

# Line 265: _process_secrets_for_recall uses dicts
def _process_secrets_for_recall(...) -> Dict[str, Any]:
```

**Existing Schemas:**
- ✅ `GraphNode` (schemas/services/graph/node_data.py)
- ✅ `NodeAttributes` type alias (for node.attrs dictionary)
- ❌ No schema for "processed recall result"

**Migration Strategy:**
1. **Create RecallResult Schema**:
   ```python
   class RecallResult(BaseModel):
       """Result of processing a node for recall."""
       node_id: str
       node_type: str
       scope: str
       attributes: NodeAttributes  # Dict with semantic meaning
       created_at: datetime
       relationships: List[str] = Field(default_factory=list)
       secrets_data: Optional[SecretsData] = None
   ```

2. **Update Return Types**:
   ```python
   # BEFORE
   def _process_node_for_recall(...) -> Dict[str, Any]:
       return {
           "node_id": node.node_id,
           "type": node.node_type,
           # ...
       }

   # AFTER
   def _process_node_for_recall(...) -> RecallResult:
       return RecallResult(
           node_id=node.node_id,
           node_type=node.node_type,
           # ...
       )
   ```

---

### 4. Audit Service (9 occurrences)
**File:** `ciris_engine/logic/services/graph/audit_service/service.py`

**Current Issues:**
```python
# Line 812: _store_entry_in_graph - NodeAttributes
# Line 1066: _add_to_hash_chain - dict operations
# Line 1068: _write_to_chain - returns dict
```

**Existing Schemas:**
- ✅ `AuditEntry` (schemas/audit/core.py)
- ✅ `AuditEventData` (schemas/audit/events.py)
- ✅ `NodeAttributes` - semantic dict type

**Analysis:**
- `NodeAttributes` is INTENTIONALLY a dict because it stores variable node attributes
- This is **acceptable Dict usage** - it's a semantic type alias, not untyped data
- The `_write_to_chain` method returns hash chain data - should be typed

**Migration Strategy:**
1. **Create HashChainData Schema**:
   ```python
   class HashChainData(BaseModel):
       """Hash chain data for audit entry."""
       entry_hash: str
       previous_hash: Optional[str]
       signature: str
       sequence_number: int
       chain_validated: bool = True
   ```

2. **Update _write_to_chain**:
   ```python
   # BEFORE
   def _write_to_chain(...) -> Dict[str, Any]:
       return {
           "entry_hash": entry_hash,
           "previous_hash": previous_hash,
           # ...
       }

   # AFTER
   def _write_to_chain(...) -> HashChainData:
       return HashChainData(
           entry_hash=entry_hash,
           previous_hash=previous_hash,
           # ...
       )
   ```

---

### 5. TSDB Edge Manager (7 occurrences)
**File:** `ciris_engine/logic/services/graph/tsdb_consolidation/edge_manager.py`

**Current Issues:**
```python
# Line 650: _normalize_edge_specifications - processes dict
# Line 677-678: _normalize_edge_tuples - dict operations
```

**Existing Schemas:**
- ✅ `EdgeSpec` (ciris_engine/schemas/services/graph/edges.py or similar?)
- ❌ Need to verify if EdgeSpec exists

**Migration Strategy:**
1. **Check for EdgeSpec schema** - may already exist
2. **Create if missing**:
   ```python
   class EdgeSpec(BaseModel):
       """Edge specification for graph operations."""
       from_node: str
       to_node: str
       edge_type: str
       properties: Optional[Dict[str, Any]] = None  # Semantic - edge metadata
   ```

---

## Category Analysis

### ✅ Acceptable Dict Usage (Keep as-is)
These use `Dict[str, Any]` **semantically** with clear purpose:
1. **NodeAttributes** - Variable node attributes (different per node type)
2. **Custom Metrics** - ServiceTelemetryData.custom_metrics (service-specific)
3. **Edge Properties** - Variable edge metadata
4. **External API responses** - JSON data from external services (mark with NOQA)

### 🔧 Requires Migration
These can use existing or new Pydantic models:
1. **Return types** - Methods returning dicts → Return Pydantic models
2. **Cache storage** - Storing dicts → Store typed models
3. **Function parameters** - Dict parameters → Typed parameters
4. **Helper functions** - ONLY if they're returning untyped data (converters are OK)

---

## Migration Priority

### Phase 1: Low-Hanging Fruit (Est. 30 occurrences)
1. **Telemetry Service cache** - Change to ServiceTelemetryData
2. **Telemetry Service return types** - Remove Union with Dict[str, Any]
3. **Audit Service _write_to_chain** - Create HashChainData schema
4. **Memory Service recall** - Create RecallResult schema

### Phase 2: TSDB Consolidation (Est. 20 occurrences)
1. **RawCorrelationData fields** - Already using RequestData/ResponseData, just simplify types
2. **Helper function return types** - Mostly already correct
3. **Edge specifications** - Create/use EdgeSpec schema

### Phase 3: Review & Cleanup (Est. 27 occurrences)
1. **Mark semantic dicts** - Add comments explaining why Dict is appropriate
2. **External API dicts** - Add # noqa: Dict[str, Any] allowed for external APIs
3. **Consolidator get_edges** - Standardize edge return format

---

## New Schemas Needed

1. **RecallResult** - Memory service recall processing
2. **HashChainData** - Audit service hash chain
3. **EdgeSpec** - Edge specifications (check if exists first)
4. **TelemetryCacheEntry** - Wrap cached telemetry data

---

## Implementation Guidelines

### ✅ DO:
- Use existing schemas (`ServiceTelemetryData`, `RequestData`, `ResponseData`, etc.)
- Create focused schemas for specific return types
- Use `NodeAttributes` type alias for variable node data (it's semantic)
- Keep `custom_metrics: Dict[str, Union[int, float, str]]` for extensibility

### ❌ DON'T:
- Replace ALL dicts - some are semantic (NodeAttributes, custom_metrics, edge properties)
- Create overly complex schemas - keep them simple and focused
- Break backward compatibility - add schemas incrementally
- Remove helper functions that CONVERT dicts → Pydantic (those are correct!)

---

## Expected Impact

**Before:** 77 Dict[str, Any] occurrences
**After Phase 1:** ~47 occurrences (30 fixed)
**After Phase 2:** ~27 occurrences (20 fixed)
**After Phase 3:** ~20 occurrences (7 fixed, 20 marked as acceptable semantic usage)

**Final State:** ~20 occurrences of **semantic Dict usage** (properly documented)
**Reduction:** ~74% (57/77 occurrences eliminated)
