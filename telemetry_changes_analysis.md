# Telemetry Investigation: Changes Analysis

## Summary
The telemetry-investigation branch contains changes aimed at improving telemetry reporting. While some changes are beneficial, others introduce issues that need to be addressed.

## Changes Overview

### Files Modified
- `ciris_engine/logic/services/graph/telemetry_service.py` - Bus metric name mapping
- `ciris_engine/logic/adapters/api/api_tools.py` - BaseService integration
- `ciris_engine/logic/adapters/cli/cli_tools.py` - BaseService integration
- `ciris_engine/logic/buses/bus_manager.py` - Telemetry service injection
- `ciris_engine/logic/buses/*.py` - All 6 buses updated for telemetry
- `ciris_engine/logic/runtime/service_initializer.py` - TSDB registration
- `ciris_engine/schemas/runtime/enums.py` - Added TSDB_CONSOLIDATION enum

## Safe to Adopt ✅

### 1. Bus-Specific Metric Name Mapping
**File**: `telemetry_service.py`
**Change**: Maps bus names to their specific uptime metrics
```python
uptime_metric_map = {
    "llm_bus": "llm_uptime_seconds",
    "memory_bus": "memory_uptime_seconds",
    "communication_bus": "communication_uptime_seconds",
    "wise_bus": "wise_uptime_seconds",
    "tool_bus": "tool_uptime_seconds",
    "runtime_control_bus": "runtime_control_uptime_seconds",
}
```
**Impact**: Fixes bus uptime metrics showing 0.0
**Risk**: None - purely additive fix

### 2. BaseService Integration for Tool Services
**Files**: `api_tools.py`, `cli_tools.py`
**Change**: Adds BaseService inheritance for telemetry infrastructure
**Impact**: Enables proper telemetry tracking for tool services
**Risk**: Low - follows established pattern

### 3. ServiceType.TSDB_CONSOLIDATION Enum
**File**: `schemas/runtime/enums.py`
**Change**: Adds missing enum value
**Impact**: Allows proper service registration
**Risk**: None - required for service registry

## Needs Modification ⚠️

### 1. Bus Telemetry Service Parameter
**Files**: All bus files and `bus_manager.py`
**Issue**: Adding telemetry_service parameter breaks TSDBConsolidationService
**Problem**: TSDB creates its own MemoryBus without telemetry service
**Solution**:
- Keep the telemetry parameter addition
- Fix TSDBConsolidationService to use shared BusManager's memory bus
- OR make telemetry_service optional with default None

### 2. TSDBConsolidationService Registration
**File**: `service_initializer.py`
**Issue**: Creates isolated MemoryBus instance
```python
# PROBLEMATIC CODE:
memory_bus = MemoryBus(registry, self.time_service, None)  # Creates isolated bus!
```
**Solution**: Use the existing memory_bus from BusManager:
```python
# FIXED CODE:
self.tsdb_consolidation_service = TSDBConsolidationService(
    memory_bus=self.bus_manager.memory,  # Use shared bus
    time_service=self.time_service
)
```

## Not Recommended ❌

### 1. Investigation Scripts
**Files**: `error_telemetry_investigation.py`, `error_telemetry_investigation_report.md`
**Reason**: Development/debugging artifacts, not production code

## Metrics Improvement

### Before (1.4.5)
- 234 total metrics
- 56 non-zero (23.9%)
- Bus uptime metrics all showing 0.0

### After (with fixes)
- 240 total metrics
- 62 non-zero (25.8%)
- Bus uptime metrics showing actual values (~30 seconds)
- 6 new working metrics

## Recommended Adoption Strategy

### Phase 1: Safe Changes (Can adopt immediately)
1. Bus-specific metric name mapping in telemetry_service.py
2. ServiceType.TSDB_CONSOLIDATION enum addition
3. BaseService integration for APIToolService and CLIToolService

### Phase 2: Modified Changes (Need fixes first)
1. Fix TSDBConsolidationService to use shared memory bus
2. Add telemetry_service parameter to all buses (with proper TSDB fix)
3. Register TSDBConsolidationService in service registry

### Phase 3: Skip
1. Don't include investigation scripts
2. Don't include temporary log files

## Implementation Recommendation

Create a new clean branch from 1.4.5-code-quality-qa and:
1. Apply Phase 1 changes (safe, immediate benefit)
2. Apply Phase 2 changes with the TSDB fix
3. Test thoroughly before merging
4. Expected result: ~26% non-zero metrics (up from 24%)

## Code to Cherry-Pick

```bash
# Create new branch
git checkout 1.4.5-code-quality-qa
git checkout -b telemetry-fixes-clean

# Cherry-pick specific changes
# 1. Telemetry service bus metric mapping
git diff 1.4.5-code-quality-qa..telemetry-investigation -- ciris_engine/logic/services/graph/telemetry_service.py | git apply

# 2. BaseService integration for tools
git diff 1.4.5-code-quality-qa..telemetry-investigation -- ciris_engine/logic/adapters/api/api_tools.py | git apply
git diff 1.4.5-code-quality-qa..telemetry-investigation -- ciris_engine/logic/adapters/cli/cli_tools.py | git apply

# 3. Enum addition
git diff 1.4.5-code-quality-qa..telemetry-investigation -- ciris_engine/schemas/runtime/enums.py | git apply

# 4. Apply bus changes WITH modification to TSDB fix
# (Manual editing required for service_initializer.py)
```

## Key Insight
The main issue is architectural: TSDBConsolidationService shouldn't create its own MemoryBus. It should receive the shared bus from BusManager. This ensures all services use the same message bus infrastructure with consistent telemetry tracking.
