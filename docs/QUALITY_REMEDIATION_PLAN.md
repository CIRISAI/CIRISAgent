# CIRIS Quality Remediation Plan v2.4.4

## Executive Summary

**Key Insight**: The schemas already exist. The problem is inconsistent usage.

The quality analysis shows 424 `Dict[str, Any]` occurrences across 135 files, but investigation reveals:
- `RetryState`, `EndpointStats`, `ErrorContext` schemas exist in `schemas/services/llm.py`
- `AdapterConfig`, `RuntimeAdapterStatus`, etc. exist in `schemas/runtime/adapter_management.py`
- Services are defining local `Dict[str, Any]` aliases instead of importing existing schemas

**Strategy**: Start with the crux (hardest problems) because fixing core abstractions automatically simplifies downstream fixes.

---

## Level 1: The Crux (Hardest - Do First)

### 1.1 LLM Service Schema Alignment
**File**: `ciris_engine/logic/services/runtime/llm_service/service.py`
**Issues**: 17 Dict[str,Any], 238 complexity
**Root Cause**: Defines local `ErrorContext = Dict[str, Any]` and `retry_state: Dict[str, Any]` instead of using existing schemas

**Action Items**:
- [ ] Replace `ErrorContext = Dict[str, Any]` (line 60) with import from `schemas/processors/error.py`
- [ ] Replace `retry_state: Dict[str, Any]` with `RetryState` from `schemas/services/llm.py` (already imported!)
- [ ] Replace `get_endpoint_stats() -> Dict[str, Any]` with `-> EndpointStats` (schema exists)
- [ ] Replace `_build_openrouter_provider_config() -> Dict[str, Any]` with typed `ProviderConfig`
- [ ] Type `extra_kwargs` and `extra_body` as `Dict[str, Union[str, int, float, bool, None]]` or create `LLMExtraParams` schema

**Impact**: Eliminates ~10 Dict[str,Any] in the most critical service

### 1.2 Adapter Manager Refactoring
**File**: `ciris_engine/logic/runtime/adapter_manager.py`
**Issues**: 4 Dict[str,Any], 398 complexity, 19.4% coverage
**Root Cause**: Complex orchestration logic spread across one file

**Action Items**:
- [ ] Use `AdapterConfig` schema consistently (it exists at `schemas/runtime/adapter_management.py`)
- [ ] Replace internal `AdapterInstance` class with proper Pydantic model
- [ ] Extract adapter discovery logic to separate module
- [ ] Extract adapter lifecycle management to separate module
- [ ] Add unit tests for each extracted module

**Impact**: Reduces complexity by ~50%, improves testability

---

## Level 2: Core Infrastructure

### 2.1 Authentication Service
**File**: `ciris_engine/logic/services/infrastructure/authentication/service.py`
**Issues**: 5 Dict[str,Any], 364 complexity, 39.5% coverage

**Action Items**:
- [ ] Identify each Dict usage and map to existing schemas
- [ ] Create missing schemas for auth-specific types (if any)
- [ ] Extract token management to separate module
- [ ] Extract OAuth flow handling to separate module
- [ ] Increase test coverage to 60%+

### 2.2 Database Maintenance Service
**File**: `ciris_engine/logic/services/infrastructure/database_maintenance/service.py`
**Issues**: 8 Dict[str,Any], 187 complexity

**Action Items**:
- [ ] Replace `all_configs: Dict[str, Any]` with typed config schemas
- [ ] Replace `adapter_instances: Dict[str, Dict[str, Any]]` with `Dict[str, AdapterConfig]`
- [ ] Type `migrate_audit_key_to_ed25519() -> Dict[str, Any]` return value

---

## Level 3: Supporting Systems

### 3.1 Tool Bus
**File**: `ciris_engine/logic/buses/tool_bus.py`
**Issues**: 1 Dict[str,Any], 145 complexity, 20.4% coverage

**Action Items**:
- [ ] Replace tool parameters Dict with existing `ToolParameters` schema
- [ ] Add tests for tool routing logic
- [ ] Add tests for tool execution flow

### 3.2 Communication Bus
**File**: `ciris_engine/logic/buses/communication_bus.py`
**Issues**: 0 Dict[str,Any], 152 complexity, 21.0% coverage

**Action Items**:
- [ ] Focus on test coverage (no type issues)
- [ ] Extract message routing logic to testable units

### 3.3 Skill Import Converter
**File**: `ciris_engine/logic/services/skill_import/converter.py`
**Issues**: 7 Dict[str,Any], 68 complexity

**Action Items**:
- [ ] Create `SkillInstallStep` schema for `_build_install_steps()` return type
- [ ] Create `SkillManifest` schema for manifest dict
- [ ] Type tool validation parameters

---

## Level 4: Quick Wins (Easy Fixes)

### 4.1 Schema Files (Internal Dict Cleanup)
These files have Dict[str,Any] in their own type definitions:

- [ ] `schemas/runtime/adapter_management.py` (3 Dict) - Line 43, 202: Required for flexibility, document why
- [ ] `schemas/types.py` (3 Dict) - Review if typed alternatives exist
- [ ] `schemas/identity.py` (3 Dict) - Review if typed alternatives exist
- [ ] `schemas/services/runtime_control.py` (3 Dict)
- [ ] `logic/persistence/stores/authentication_store.py` (3 Dict)

### 4.2 Small Protocol Files Needing Tests
Add simple unit tests to these small files:

- [ ] `protocols/adapters/configurable.py` (14 lines)
- [ ] `protocols/services/runtime/tool.py` (25 lines)
- [ ] `protocols/adapters/message.py` (32 lines)
- [ ] `protocols/consent.py` (19 lines)
- [ ] `protocols/faculties.py` (10 lines)

---

## Implementation Order

### Phase 1: Schema Usage Enforcement (Est. 8-10 hours)
1. LLM Service - Use existing RetryState, EndpointStats, ErrorContext
2. Adapter Manager - Use existing AdapterConfig, RuntimeAdapterStatus
3. Database Maintenance - Use existing adapter schemas

### Phase 2: Complexity Reduction (Est. 15-20 hours)
4. Extract adapter_manager.py into modules
5. Extract authentication service into modules
6. Extract main_processor.py logic into testable units

### Phase 3: Test Coverage Push (Est. 30-40 hours)
7. Add tests for extracted modules
8. Add tests for bus implementations
9. Add tests for protocol definitions

### Phase 4: Quick Wins & Cleanup (Est. 5-8 hours)
10. Schema file internal cleanup
11. Small file tests
12. Documentation updates

---

## Success Metrics

| Metric | Current | Target | Phase |
|--------|---------|--------|-------|
| Dict[str,Any] count | 424 | <200 | Phase 1 |
| Test coverage | ~45% | >60% | Phase 3 |
| High complexity files | 92 | <60 | Phase 2 |
| Tech debt hours | 65.9h | <40h | Phase 2 |

---

## Anti-Patterns to Avoid

1. **Creating new schemas when they exist** - ALWAYS search first
2. **Creating SchemaV2** - Fix the original schema
3. **Over-abstracting** - Simple direct usage beats clever indirection
4. **Backwards-compat hacks** - Delete unused code, don't rename to `_unused`

---

## Notes

- Many Dict[str,Any] in schema files (line 43, 202 of adapter_management.py) are intentional for dynamic adapter configs
- Some complexity in adapter_manager.py is inherent to the domain
- Focus on type safety at boundaries, trust internal code
