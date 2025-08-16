# Module-Level Telemetry Documentation Plan

## Why Module-Level Documentation?

Each module in CIRIS collects telemetry differently and stores it in different places. API developers need to know:
- **What data is available** (metrics, events, states)
- **Where it's stored** (memory dict, graph node, Redis, log file)
- **How to access it** (direct method, graph query, aggregation needed)
- **Update frequency** (real-time, batched, periodic)

---

## Documentation Template

Each `MODULE_TELEMETRY.md` file will follow this structure:

```markdown
# [Module Name] Telemetry

## Overview
Brief description of what this module tracks and why.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| example_metric | counter | in-memory dict | real-time | `module.get_metrics()` |

## Data Structures

### Metric Name
```python
{
    "field1": "description",
    "field2": "description"
}
```

## API Access Patterns

### Current Access
- How it's accessed today (if at all)

### Recommended Endpoint
- Suggested API endpoint design

## Graph Storage (if applicable)

### Node Types Created
- Node type and schema

### Edge Relationships
- Edge types and meanings

## Example Usage

```python
# How to get this telemetry
```

## Testing

- Test file: `test_telemetry_[module].py`
- Validation: How to verify data is flowing
```

---

## Modules Requiring Documentation

### Priority 1: Message Buses (6 files)

#### 1. LLM_BUS_TELEMETRY.md
```
Source: ciris_engine/logic/buses/llm_bus.py
Key Data:
- service_metrics: dict[str, ServiceMetrics] (in-memory)
- circuit_breakers: dict[str, CircuitBreaker] (in-memory)
- round_robin_index: dict[int, int] (in-memory)

Access:
- get_service_stats() → aggregated metrics
- get_stats() → bus statistics

Storage: IN-MEMORY ONLY (needs persistence strategy)
```

#### 2. MEMORY_BUS_TELEMETRY.md
```
Source: ciris_engine/logic/buses/memory_bus.py
Key Data:
- Graph operations count
- Node creation metrics
- Edge creation metrics

Access:
- Through MemoryService methods
- Graph queries

Storage: GRAPH (persistent)
```

#### 3. COMMUNICATION_BUS_TELEMETRY.md
```
Source: ciris_engine/logic/buses/communication_bus.py
Key Data:
- Message counts by channel
- Processing latencies
- Adapter metrics

Access:
- Per-adapter statistics
- Channel activity

Storage: MIXED (memory + audit log)
```

#### 4. WISE_BUS_TELEMETRY.md
```
Source: ciris_engine/logic/buses/wise_bus.py
Key Data:
- Deferral counts
- Guidance requests
- Broadcast success rates

Access:
- Through WiseAuthority service
- Audit trail

Storage: AUDIT LOG (graph)
```

#### 5. TOOL_BUS_TELEMETRY.md
```
Source: ciris_engine/logic/buses/tool_bus.py
Key Data:
- Tool invocations by type
- Execution times
- Success/failure rates

Access:
- Tool registry statistics
- Audit events

Storage: AUDIT LOG (graph)
```

#### 6. RUNTIME_CONTROL_BUS_TELEMETRY.md
```
Source: ciris_engine/logic/buses/runtime_control_bus.py
Key Data:
- State transitions
- Queue depths
- Control operations

Access:
- RuntimeControlService methods
- System status endpoints

Storage: IN-MEMORY + AUDIT
```

### Priority 2: Core Services (21 files)

#### Graph Services (6)

##### MEMORY_SERVICE_TELEMETRY.md
```
Source: ciris_engine/logic/services/graph/memory_service.py
Key Data:
- Node counts by type
- Edge counts by relationship
- Memory operations/second
- Graph size metrics

Storage: GRAPH (self-tracking)
Access: get_statistics(), query methods
```

##### TELEMETRY_SERVICE_TELEMETRY.md
```
Source: ciris_engine/logic/services/graph/telemetry_service.py
Key Data:
- memorize_metric() calls
- Metric nodes created
- Aggregation operations

Storage: GRAPH (metric nodes)
Access: Graph queries with time filters
```

##### AUDIT_SERVICE_TELEMETRY.md
```
Source: ciris_engine/logic/services/graph/audit_service.py
Key Data:
- Audit events by type
- Actor activity
- Compliance metrics

Storage: GRAPH (audit nodes)
Access: get_entries(), search()
```

##### INCIDENT_SERVICE_TELEMETRY.md
```
Source: ciris_engine/logic/services/graph/incident_service.py
Key Data:
- Incident counts by severity
- Resolution times
- Incident patterns

Storage: GRAPH (incident nodes)
Access: get_recent_incidents()
```

##### CONFIG_SERVICE_TELEMETRY.md
```
Source: ciris_engine/logic/services/graph/config_service.py
Key Data:
- Config access patterns
- Change frequency
- Popular configs

Storage: GRAPH (config nodes)
Access: Through config API
```

##### TSDB_CONSOLIDATION_SERVICE_TELEMETRY.md
```
Source: ciris_engine/logic/services/graph/tsdb_consolidation_service.py
Key Data:
- Consolidation runs
- Compression ratios
- Nodes consolidated

Storage: GRAPH (summary nodes)
Access: Consolidation status
```

#### Infrastructure Services (7)

##### RESOURCE_MONITOR_SERVICE_TELEMETRY.md
```
Source: ciris_engine/logic/services/infrastructure/resource_monitor.py
Key Data:
- CPU usage
- Memory usage
- Disk usage
- Network connections

Storage: IN-MEMORY + GRAPH (via telemetry service)
Access: get_current_snapshot(), get_history()
```

##### TIME_SERVICE_TELEMETRY.md
```
Source: ciris_engine/logic/services/infrastructure/time_service.py
Key Data:
- Time drift
- Sync status
- Uptime

Storage: IN-MEMORY
Access: get_time(), get_uptime()
```

##### AUTHENTICATION_SERVICE_TELEMETRY.md
```
Source: ciris_engine/logic/services/infrastructure/authentication.py
Key Data:
- Auth attempts
- Success/failure rates
- Token usage

Storage: AUDIT LOG
Access: Through audit queries
```

[Continue for all 21 services...]

### Priority 3: Supporting Components

#### SERVICE_REGISTRY_TELEMETRY.md
```
Source: ciris_engine/logic/registries/base.py
Key Data:
- Service health states
- Circuit breaker states
- Provider selection metrics

Storage: IN-MEMORY
Access: get_provider_info()
```

#### PROCESSING_QUEUE_TELEMETRY.md
```
Source: ciris_engine/logic/runtime/processing_queue.py
Key Data:
- Queue depth
- Item age
- Processing rate

Storage: IN-MEMORY
Access: get_queue_status()
```

#### CIRCUIT_BREAKER_TELEMETRY.md
```
Source: ciris_engine/logic/registries/circuit_breaker.py
Key Data:
- State changes
- Failure counts
- Recovery attempts

Storage: IN-MEMORY
Access: get_stats()
```

---

## Implementation Plan

### Phase 1: Document What Exists
```
Week 1:
- [ ] Create all 6 bus telemetry docs
- [ ] Create all 6 graph service telemetry docs
- [ ] Validate against running system

Week 2:
- [ ] Create all 7 infrastructure service telemetry docs
- [ ] Create all 4 governance service telemetry docs
- [ ] Create all 3 runtime service telemetry docs

Week 3:
- [ ] Create supporting component telemetry docs
- [ ] Create cross-reference matrix
- [ ] Validate completeness
```

### Phase 2: Identify Gaps
```
- [ ] Mark metrics that SHOULD be collected but aren't
- [ ] Mark metrics that ARE collected but not accessible
- [ ] Mark metrics that need persistence
```

### Phase 3: Create Access Layer
```
- [ ] Design API endpoints for each module's telemetry
- [ ] Update SDK with access methods
- [ ] Create aggregation strategies where needed
```

---

## Validation Checklist

For each MODULE_TELEMETRY.md file:

```
- [ ] All metrics listed with accurate types
- [ ] Storage location verified in code
- [ ] Access method tested
- [ ] Update frequency confirmed
- [ ] Example data captured from production
- [ ] API endpoint recommended
- [ ] SDK method proposed
```

---

## Success Criteria

1. **Complete Coverage**: Every module with telemetry documented
2. **Accurate Information**: Storage and access patterns verified
3. **Actionable Guidance**: Clear path to API exposure
4. **Testable Claims**: Each metric can be validated
5. **Developer Friendly**: Easy to find what you need

---

## Why This Matters

### For API Developers:
- Know exactly what data is available
- Understand storage patterns for efficient access
- Design appropriate endpoints

### For SDK Developers:
- Know what methods to implement
- Understand data structures
- Handle different storage backends

### For Module Owners:
- Clear telemetry responsibilities
- Standardized patterns
- Testing requirements

### For CIRISManager:
- Complete inventory of available telemetry
- Clear access patterns
- Integration guidance

---

## Deliverables

1. **33+ MODULE_TELEMETRY.md files**
   - 6 buses
   - 21 services
   - 6+ supporting components

2. **TELEMETRY_MATRIX.md**
   - Cross-reference of all metrics
   - Storage type summary
   - Access pattern overview

3. **API_TELEMETRY_DESIGN.md**
   - Recommended endpoints for each module
   - Aggregation strategies
   - Performance considerations

4. **SDK_TELEMETRY_METHODS.md**
   - Required SDK methods
   - Data structure definitions
   - Error handling patterns

---

## Example: LLM_BUS_TELEMETRY.md

```markdown
# LLM Bus Telemetry

## Overview
The LLM Bus tracks all language model interactions, provider health, and selection metrics.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| total_requests | counter | in-memory dict | real-time | `get_service_stats()` |
| failed_requests | counter | in-memory dict | real-time | `get_service_stats()` |
| total_latency_ms | gauge | in-memory dict | real-time | `get_service_stats()` |
| tokens_used | counter | telemetry graph | per-call | graph query |
| circuit_breaker_state | enum | in-memory | on change | `get_provider_info()` |

## Data Structures

### ServiceMetrics
```python
{
    "total_requests": 15234,
    "failed_requests": 23,
    "total_latency_ms": 6891234.5,
    "average_latency_ms": 452.3,
    "last_request_time": "2025-08-14T13:30:00Z",
    "consecutive_failures": 0
}
```

## API Access Patterns

### Current Access
- None (internal only)

### Recommended Endpoint
```
GET /telemetry/llm/usage
Returns: Aggregated metrics for all LLM providers
```

## Example Usage
```python
llm_bus = service_registry.get_service(ServiceType.LLM)
stats = llm_bus.get_service_stats()
# Returns dict with all provider metrics
```

## Testing
- Test file: `test_telemetry_llm_bus.py`
- Validation: Make LLM call, verify metrics increment
```

This gives API developers everything they need to expose this telemetry!
