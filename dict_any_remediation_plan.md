# Dict[str, Any] Remediation Plan

**Generated:** 2025-10-14
**Total Violations:** 25 in production code
**Legitimate Uses:** 6-7 (type aliases + serialization)
**Fixable Violations:** 10-12
**Need Review:** 6

---

## Executive Summary

Of the 25 `Dict[str, Any]` violations in production code:
- **6-7 are LEGITIMATE** (type aliases in `types.py` and serialization methods)
- **10-12 can be FIXED** using existing schemas or simple type alias changes
- **6 need REVIEW** (protocol definitions that may have legitimate uses)

**Good News:** We already have schemas for most use cases! The principle "The schema already exists. Use it." applies here.

---

## Category 1: LEGITIMATE - No Action Required (6-7 violations)

### Type Aliases (schemas/types.py) - 3 violations
These are the **foundation** type aliases that define `JSONDict` and `JSONValue`. They are intentionally `Dict[str, Any]` because they represent JSON-compatible data.

```python
# Line 23, 29, 37
JSONValue = Union[str, int, float, bool, None, List[Any], Dict[str, Any]]
JSONDict = Dict[str, JSONValue]
SerializedModel = Dict[str, Any]  # For model_dump() output
```

**Status:** ✅ LEGITIMATE - These are the base types used everywhere else.

---

### Serialization Methods - 3-4 violations
Methods that convert Pydantic models to dicts for API responses or storage.

1. **dma/prompts.py:110** - `PromptCollection.to_dict()`
   ```python
   def to_dict(self) -> Dict[str, Any]:
       """Serialize to dict for API responses"""
   ```
   **Status:** ✅ LEGITIMATE - Serialization method

2. **graph_typed_nodes.py:48,66** - `TypedGraphNode._serialize_extra_fields()`
   ```python
   def _serialize_extra_fields(self) -> Dict[str, Any]:
       """Serialize dynamic fields for storage"""
   ```
   **Status:** ✅ LEGITIMATE - Handles dynamic node attributes

3. **wa_updates.py:72** - `WACertificateUpdate.get_update_fields()`
   ```python
   def get_update_fields(self) -> Dict[str, Any]:
       """Get only changed fields for partial updates"""
   ```
   **Status:** ✅ LEGITIMATE - Partial update pattern

---

## Category 2: FIXABLE with Existing Schemas (10-12 violations)

### 🔥 HIGH PRIORITY: Core Services (4 violations)

#### 1. control_service/service.py (3 violations)

**Lines:** 1385, 1395, 1399
**Functions:** `_find_provider_in_registry`, `_apply_priority_updates`
**Current:** `Dict[str, Any]` for provider metadata and priority updates

**EXISTING SCHEMAS TO USE:**
```python
# These already exist in schemas/services/core/runtime.py:
- ServiceMetrics
- ProcessorControlResponse
- ProcessorState

# Or from schemas/runtime/models.py:
- ServiceInfo
- ProviderMetadata
```

**RECOMMENDED FIX:**
```python
# Before:
def _find_provider_in_registry(self, ...) -> Optional[Dict[str, Any]]:
    provider_data: Dict[str, Any] = {"name": ..., "priority": ...}

# After:
from ciris_engine.schemas.services.core.runtime import ServiceMetrics

def _find_provider_in_registry(self, ...) -> Optional[ServiceMetrics]:
    return ServiceMetrics(name=..., priority=..., healthy=True, ...)
```

---

#### 2. tool_bus.py:407

**Function:** `collect_telemetry`
**Current:** `Dict[str, Any]` for telemetry data

**EXISTING SCHEMA TO USE:**
```python
# From schemas/services/core/runtime.py
from ciris_engine.schemas.services.core.runtime import ServiceMetrics
```

**RECOMMENDED FIX:**
```python
# Before:
def collect_telemetry(self) -> Dict[str, Any]:
    return {"service": "tool_bus", "healthy": True, ...}

# After:
def collect_telemetry(self) -> ServiceMetrics:
    return ServiceMetrics(
        service_name="tool_bus",
        healthy=True,
        providers_count=len(self._providers),
        ...
    )
```

---

### 📊 MEDIUM PRIORITY: API Routes (4 violations)

#### 3. routes/audit.py (4 violations)

**Lines:** 256, 269, 305, 351
**Functions:** `_process_graph_entries`, `_process_sqlite_entries`, `_process_jsonl_entries`, `_merge_audit_sources`
**Current:** `Dict[str, Any]` for temporary merge dict: `{"entry": AuditEntryResponse, "sources": List[str]}`

**NO EXISTING SCHEMA** - But easy to create!

**RECOMMENDED FIX:**
```python
# Create new schema in ciris_engine/logic/adapters/api/routes/audit.py:

class _MergedAuditEntry(BaseModel):
    """Internal: Audit entry with source tracking during merge."""
    entry: AuditEntryResponse
    sources: List[str]

# Then change:
# Before:
def _merge_audit_sources(...) -> List[AuditEntryResponse]:
    merged: Dict[str, Any] = {}

# After:
def _merge_audit_sources(...) -> List[AuditEntryResponse]:
    merged: Dict[str, _MergedAuditEntry] = {}
```

**Impact:** Fixes 4 violations with one simple internal model.

---

### 🔧 LOW PRIORITY: Simple Replacements (3-4 violations)

#### 4. thought_processor/main.py:598

**Function:** `_apply_conscience_simple`
**Current:** `Dict[str, Any]` for conscience context

**EXISTING SCHEMA:**
```python
# From schemas/processors/core.py
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
```

**RECOMMENDED FIX:**
```python
# Before:
def _apply_conscience_simple(self, context: Dict[str, Any]) -> ...:

# After:
def _apply_conscience_simple(self, context: ConscienceApplicationResult) -> ...:
```

---

#### 5. runtime_control.py:150

**Class:** `SpanAttribute`
**Current:** `value: Dict[str, Any]`

**EXISTING TYPE ALIAS:**
```python
# Already available in types.py
from ciris_engine.schemas.types import JSONDict
```

**RECOMMENDED FIX:**
```python
# Before:
class SpanAttribute(BaseModel):
    value: Dict[str, Any]

# After:
class SpanAttribute(BaseModel):
    value: JSONDict
```

---

#### 6. core/runtime.py:228

**Class:** `ConfigSnapshot`
**Current:** `config: Dict[str, Any]`

**EXISTING SCHEMA:**
```python
# From schemas/services/graph/config.py
from ciris_engine.schemas.services.graph.config import ConfigData
```

**RECOMMENDED FIX:**
```python
# Before:
class ConfigSnapshot(BaseModel):
    config: Dict[str, Any]

# After:
class ConfigSnapshot(BaseModel):
    config: ConfigData
```

---

#### 7. graph/node_data.py:147

**Function:** `create_node_data`
**Current:** `attributes: Dict[str, Any]`

**EXISTING TYPE ALIAS:**
```python
from ciris_engine.schemas.types import JSONDict
```

**RECOMMENDED FIX:**
```python
# Before:
def create_node_data(attributes: Dict[str, Any]) -> ...:

# After:
def create_node_data(attributes: JSONDict) -> ...:
```

---

## Category 3: NEED REVIEW - Protocol Definitions (6 violations)

These are in protocol files and may have legitimate reasons for `Dict[str, Any]`:

1. **pipeline_control.py:20** - `SerializedModel` type alias (likely legitimate)
2. **adapters/message.py:90** - Protocol parameter type
3. **authentication.py:85** - `verify_token_sync` return type
4. **wa_auth.py:180** - `create_oauth_wa` parameters
5. **scheduler.py:39** - `schedule_deferred_task` parameters
6. **api_tools.py:134** - `_curl` parameters

**RECOMMENDATION:** Review each protocol to see if specific schemas exist:
- Token payloads → `TokenPayload` schema
- OAuth parameters → `OAuthRequest` schema
- Task parameters → `TaskRequest` schema
- Tool parameters → `ToolExecutionRequest` schema

---

## Implementation Priority

### Phase 1: Quick Wins (3-4 violations, 1 hour)
Replace `Dict[str, Any]` with `JSONDict` type alias:
- ✅ runtime_control.py:150
- ✅ graph/node_data.py:147

### Phase 2: Core Services (4 violations, 2-3 hours)
Use existing ServiceMetrics/ProcessorControlResponse:
- ✅ control_service/service.py (3 violations)
- ✅ tool_bus.py:407

### Phase 3: API Routes (4 violations, 1-2 hours)
Create `_MergedAuditEntry` internal model:
- ✅ routes/audit.py (4 violations)

### Phase 4: Misc Fixes (2 violations, 1 hour)
- ✅ thought_processor/main.py:598 → ConscienceApplicationResult
- ✅ core/runtime.py:228 → ConfigData

### Phase 5: Protocol Review (6 violations, 2-3 hours)
Review and potentially type protocol definitions.

---

## Expected Outcome

**Before:** 25 violations
**After Phase 1-4:** 13 violations (48% reduction)
**After Phase 5:** 7-8 violations (68-72% reduction)

**Remaining:** Only legitimate type aliases and serialization methods.

---

## Key Takeaway

**The schemas already exist!** We don't need to create many new schemas. The violations are mainly:
1. Not using existing schemas (ServiceMetrics, ProcessorControlResponse, etc.)
2. Not using the JSONDict type alias for JSON data
3. One new internal model needed (_MergedAuditEntry)

This aligns perfectly with the CLAUDE.md principle:
> "The schema already exists. Use it."
