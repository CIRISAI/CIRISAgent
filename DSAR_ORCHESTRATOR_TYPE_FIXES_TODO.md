# DSAR Orchestrator Type Fixes TODO

## Overview
The multi-source DSAR orchestrator implementation is functionally complete (~500 lines) but has 27 mypy --strict type errors that need to be fixed before merging.

## Mypy Errors Breakdown

### 1. MemoryBus Protocol Mismatch (4 errors)
**Lines**: 119, 231, 348, 459
**Error**: `Argument 2 to "resolve_user_identity" has incompatible type "MemoryBus"; expected "MemoryServiceProtocol"`

**Fix**:
```python
# Cast MemoryBus to MemoryServiceProtocol
identity_node = await resolve_user_identity(
    user_identifier,
    cast(MemoryServiceProtocol, self._memory_bus)
)
```

### 2. DSARAccessPackage Fallback Missing Fields (7 errors - line 129)
**Missing Required Fields**:
- `consent_status: ConsentStatus`
- `consent_history: List[ConsentAuditEntry]`
- `interaction_summary: dict[str, object]`
- `contribution_metrics: ConsentImpactReport`
- `data_categories: List[str]`
- `retention_periods: dict[str, str]`
- `processing_purposes: List[str]`

**Fix**:
```python
from ciris_engine.schemas.consent.core import DSARAccessPackage, ConsentAuditEntry

ciris_data = DSARAccessPackage(
    user_id=user_identifier,
    request_id=request_id,
    generated_at=self._now(),
    consent_status=ConsentStatus(
        user_id=user_identifier,
        stream=ConsentStream.TEMPORARY,
        categories=[],
        granted_at=self._now(),
        last_modified=self._now(),
    ),
    consent_history=[],
    interaction_summary={},
    contribution_metrics=ConsentImpactReport(
        user_id=user_identifier,
        total_interactions=0,
        patterns_contributed=0,
        users_helped=0,
        categories_active=[],
        impact_score=0.0,
        example_contributions=[],
    ),
    data_categories=[],
    retention_periods={},
    processing_purposes=[],
)
```

### 3. DSARAccessPackage No `total_records` Attribute (line 163)
**Error**: `"DSARAccessPackage" has no attribute "total_records"`

**Fix**: DSARAccessPackage doesn't have a total_records field. Calculate from external sources only:
```python
# Remove reference to ciris_data.total_records
total_records = sum(src.total_records for src in external_sources)
```

### 4. DSARExportPackage Fallback Missing Fields (3 errors - line 241)
**Missing Required Fields**:
- `file_size_bytes: int` (not `total_size_bytes`)
- `record_counts: dict[str, int]`
- `checksum: str`

**Fix**:
```python
ciris_export = DSARExportPackage(
    user_id=user_identifier,
    request_id=request_id,
    export_format=DSARExportFormat.JSON if not hasattr(export_format, "value") else export_format,
    generated_at=self._now(),
    file_path=None,
    file_size_bytes=0,
    record_counts={},
    checksum="",
    includes_readme=True,
)
```

### 5. DSARExportPackage Wrong Attribute Name (line 271)
**Error**: `"DSARExportPackage" has no attribute "total_size_bytes"; maybe "file_size_bytes"?`

**Fix**:
```python
# Change total_size_bytes → file_size_bytes
total_size_bytes = ciris_export.file_size_bytes + sum(...)
```

### 6. DSARDeletionStatus Fallback Missing Fields (5 errors - line 355)
**Missing Required Fields**:
- `ticket_id: str`
- `decay_started: datetime` (not `decay_start: str`)
- `current_phase: str`
- `completion_percentage: float`
- `milestones_completed: List[str]`

**Fix**:
```python
ciris_deletion = DSARDeletionStatus(
    ticket_id=request_id,
    user_id=user_identifier,
    decay_started=self._now(),
    current_phase="pending",
    completion_percentage=0.0,
    estimated_completion=self._now() + timedelta(days=90),
    milestones_completed=[],
    next_milestone="identity_severed",
    safety_patterns_retained=0,
)
```

### 7. ToolBus No `call_tool` Method (3 errors - lines 627, 682, 736)
**Error**: `"ToolBus" has no attribute "call_tool"`

**Fix**: Use `execute_tool` instead:
```python
# Change call_tool → execute_tool
result = await self._tool_bus.execute_tool(
    tool_name=tool_name,
    parameters={"user_identifier": user_identifier},
    handler_name="default"
)

# Result is ToolExecutionResult, access .result field
if isinstance(result.result, dict):
    data = result.result.get("data", {})
```

### 8. handle_correction_request Wrong Signature (2 errors - line 468)
**Error 1**: `Argument 1 to "handle_correction_request" of "DSARAutomationService" has incompatible type "str"; expected "DSARCorrectionRequest"`
**Error 2**: `Argument 2 to "handle_correction_request" of "DSARAutomationService" has incompatible type "dict[str, Any]"; expected "str | None"`

**Fix**: Create DSARCorrectionRequest object:
```python
from ciris_engine.schemas.consent.core import DSARCorrectionRequest

# Build correction requests for each field
for field_name, new_value in corrections.items():
    correction_req = DSARCorrectionRequest(
        user_id=user_identifier,
        field_name=field_name,
        current_value=None,  # Could query current value first
        new_value=str(new_value),
        reason="Multi-source DSAR correction request",
    )
    ciris_result = await self._dsar_automation.handle_correction_request(
        correction_req,
        request_id
    )
```

### 9. Returning Any from bool Function (line 741)
**Error**: `Returning Any from function declared to return "bool"`

**Fix**: Explicit bool conversion:
```python
zero_data_confirmed = bool(verify_result.get("zero_data_confirmed", False))
return zero_data_confirmed
```

## Implementation Priority

1. **High Priority** (blocks type checking):
   - Fix DSARAccessPackage fallback (7 errors)
   - Fix ToolBus.call_tool → execute_tool (3 errors)
   - Fix MemoryBus protocol (4 errors)

2. **Medium Priority** (breaks functionality):
   - Fix handle_correction_request signature (2 errors)
   - Fix DSARDeletionStatus fallback (5 errors)
   - Fix DSARExportPackage fallback (3 errors)

3. **Low Priority** (minor):
   - Fix total_records access (1 error)
   - Fix file_size_bytes naming (1 error)
   - Fix bool return type (1 error)

## Testing Plan

After type fixes:
1. Run `mypy --strict ciris_engine/logic/services/governance/dsar/orchestrator.py`
2. Verify 0 errors
3. Run unit tests (to be written)
4. Run integration tests with mock ToolBus and DSARAutomationService

## Additional Integration Needs

1. **ConsentService Access**: Add to DSAROrchestrator.__init__ for CIRIS deletion via revoke_consent()
2. **API Routes**: Expose multi-source endpoints in /v1/dsar/
3. **Tests**: Comprehensive unit + integration test coverage
4. **Documentation**: Update API docs with multi-source DSAR endpoints

## Estimated Effort

- Type fixes: 1-2 hours
- Unit tests: 2-3 hours
- Integration tests: 1-2 hours
- API routes: 1 hour
- Documentation: 1 hour

**Total**: 6-9 hours of focused work
