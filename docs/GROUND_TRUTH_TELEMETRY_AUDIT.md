# Ground Truth Telemetry Audit Plan

## Why This Approach?

In a 130K line codebase with 21 services and 6 buses, documentation is always wrong.
We need to establish GROUND TRUTH - what the code ACTUALLY does, not what we think it does.

---

## PHASE 1: TELEMETRY DISCOVERY AUDIT

### Step 1.1: Identify ALL Telemetry Collection Points

#### A. The 6 Message Buses (Primary Collection Points)
```
- [ ] LLMBus: Audit llm_bus.py for ALL metrics collection
  - [ ] Document: service_metrics dictionary structure
  - [ ] Document: circuit_breakers tracking
  - [ ] Document: _record_success() and _record_failure() methods
  - [ ] Document: get_service_stats() output format

- [ ] MemoryBus: Audit memory operations tracking
  - [ ] Document: memorize_metric() calls
  - [ ] Document: graph node creation metrics
  - [ ] Document: edge creation metrics

- [ ] CommunicationBus: Audit message flow metrics
  - [ ] Document: message counts per channel
  - [ ] Document: processing latencies
  - [ ] Document: adapter-specific metrics

- [ ] WiseBus: Audit wisdom authority metrics
  - [ ] Document: deferral counts
  - [ ] Document: guidance requests
  - [ ] Document: broadcast success rates

- [ ] ToolBus: Audit tool invocation metrics
  - [ ] Document: tool usage by type
  - [ ] Document: execution times
  - [ ] Document: failure rates

- [ ] RuntimeControlBus: Audit runtime metrics
  - [ ] Document: state transitions
  - [ ] Document: queue depths
  - [ ] Document: processor states
```

#### B. The 21 Core Services (Secondary Collection Points)

**Graph Services (6):**
```
- [ ] MemoryService: Document graph metrics collection
- [ ] ConfigService: Document config access patterns
- [ ] TelemetryService: Document memorize_metric() implementation
- [ ] AuditService: Document audit event storage
- [ ] IncidentService: Document incident creation/storage
- [ ] TSDBConsolidationService: Document consolidation metrics
```

**Infrastructure Services (7):**
```
- [ ] TimeService: Document time sync metrics
- [ ] ShutdownService: Document shutdown event tracking
- [ ] InitializationService: Document startup metrics
- [ ] AuthenticationService: Document auth attempts/failures
- [ ] ResourceMonitorService: Document resource snapshots
- [ ] DatabaseMaintenanceService: Document maintenance operations
- [ ] SecretsService: Document secret access patterns
```

**Governance Services (4):**
```
- [ ] WiseAuthorityService: Document decision metrics
- [ ] AdaptiveFilterService: Document filtering metrics
- [ ] VisibilityService: Document visibility queries
- [ ] SelfObservationService: Document self-metrics
```

**Runtime Services (3):**
```
- [ ] LLMService: Document LLM call metrics
- [ ] RuntimeControlService: Document control operations
- [ ] TaskSchedulerService: Document task execution metrics
```

**Tool Services (1):**
```
- [ ] SecretsToolService: Document tool invocations
```

#### C. Hidden Telemetry Collectors
```
- [ ] ProcessingQueue: Document queue metrics
- [ ] ServiceRegistry: Document service health checks
- [ ] CircuitBreaker: Document breaker state changes
- [ ] AgentProcessor: Document thought processing metrics
- [ ] HandlerFramework: Document handler invocations
```

---

## PHASE 2: MODULE DOCUMENTATION CREATION

### Step 2.1: Create Module-Level Telemetry Docs

For EACH telemetry collection point identified above:

```
- [ ] Create {module}_telemetry.md documenting:
  - [ ] What data is collected
  - [ ] Where it's stored (memory/graph/log)
  - [ ] How often it's collected
  - [ ] Data retention policy
  - [ ] Access methods available
  - [ ] Example data structure
```

### Step 2.2: Document Data Flow Paths

```
- [ ] Create TELEMETRY_FLOW.md showing:
  - [ ] Source → Collection → Storage → Access paths
  - [ ] Which services write telemetry
  - [ ] Which services read telemetry
  - [ ] Graph node types created
  - [ ] Edge relationships used
```

---

## PHASE 3: VALIDATION TESTING

### Step 3.1: Create Unit Tests for Each Collection Point

For EACH telemetry collection point:

```python
# test_telemetry_{module}.py

- [ ] Test data is actually collected
- [ ] Test data structure matches documentation
- [ ] Test data persistence (if applicable)
- [ ] Test data retrieval methods
- [ ] Test edge cases (nulls, errors)
- [ ] Test data cleanup/rotation
```

### Step 3.2: Create Integration Tests for Data Flow

```python
# test_telemetry_integration.py

- [ ] Test end-to-end: Action → Collection → Storage → Retrieval
- [ ] Test cross-service telemetry (e.g., LLM call → multiple metrics)
- [ ] Test aggregation accuracy
- [ ] Test concurrent collection
- [ ] Test failure scenarios
```

### Step 3.3: Create Verification Scripts

```python
# verify_telemetry.py

- [ ] Script to dump ALL telemetry from running system
- [ ] Script to validate telemetry against docs
- [ ] Script to detect missing telemetry
- [ ] Script to find orphaned metrics
```

---

## PHASE 4: TRUTH RECONCILIATION

### Step 4.1: Compare Documentation vs Reality

```
- [ ] For each module:
  - [ ] Run verification script
  - [ ] Compare actual vs documented
  - [ ] Update documentation to match reality
  - [ ] Mark any non-functional telemetry
```

### Step 4.2: Create Truth Report

```
- [ ] Generate TELEMETRY_TRUTH_REPORT.md containing:
  - [ ] Complete list of WORKING telemetry
  - [ ] Complete list of BROKEN telemetry
  - [ ] Complete list of MISSING telemetry
  - [ ] Data availability matrix (what's accessible where)
```

---

## PHASE 5: GROUND TRUTH DOCUMENTATION

### Step 5.1: Create Master Telemetry Inventory

```markdown
# TELEMETRY_INVENTORY.md

## Actually Collected Metrics

### LLM Metrics
- Source: LLMBus.service_metrics
- Storage: In-memory dictionary
- Access: LLMBus.get_service_stats()
- Contains: requests, tokens, latency, failures
- Tested: ✓ test_telemetry_llm.py

### Circuit Breaker States
- Source: ServiceRegistry._circuit_breakers
- Storage: In-memory
- Access: get_provider_info()
- Contains: state, counts, thresholds
- Tested: ✓ test_telemetry_registry.py

[... continue for ALL telemetry ...]
```

### Step 5.2: Create Telemetry Access Guide

```markdown
# TELEMETRY_ACCESS_GUIDE.md

## How to Access Each Metric

### Get LLM Token Usage
```python
llm_bus = get_service(ServiceType.LLM)
stats = llm_bus.get_service_stats()
```

### Get Circuit Breaker Status
```python
registry = get_global_registry()
info = registry.get_provider_info()
```

[... continue for ALL metrics ...]
```

---

## VALIDATION CHECKLIST

### Per Module:
```
- [ ] Code audited for telemetry collection
- [ ] Documentation created
- [ ] Unit tests written and passing
- [ ] Verification script validates data
- [ ] Access method documented
```

### Per Service Type:
```
- [ ] All services of type audited
- [ ] Cross-service telemetry mapped
- [ ] Integration tests passing
```

### Overall:
```
- [ ] All 21 services audited
- [ ] All 6 buses audited
- [ ] All hidden collectors found
- [ ] Master inventory complete
- [ ] Access guide complete
- [ ] Truth report generated
```

---

## SUCCESS CRITERIA

1. **100% Discovery**: Every telemetry collection point identified
2. **100% Documentation**: Every metric documented with example
3. **100% Testing**: Every metric has validation test
4. **100% Truth**: Documentation matches code exactly
5. **100% Accessibility**: Know how to access every metric

---

## WHY THIS MATTERS

In a 130K line codebase:
- **Assumptions kill** - "I think it collects X" is dangerous
- **Hidden gems exist** - Telemetry you didn't know about
- **Broken dreams abound** - Telemetry that doesn't work
- **Truth enables action** - Can't expose what you don't know exists

This audit gives us GROUND TRUTH - the foundation for any telemetry work.

---

## DELIVERABLES

1. **Module Telemetry Docs** (27+ files)
   - One per service + buses + hidden collectors

2. **Test Suite** (27+ test files)
   - Unit tests per module
   - Integration test suite

3. **Verification Scripts** (3-4 scripts)
   - Dump, validate, detect, find

4. **Truth Documents** (4 files)
   - TELEMETRY_INVENTORY.md
   - TELEMETRY_ACCESS_GUIDE.md
   - TELEMETRY_FLOW.md
   - TELEMETRY_TRUTH_REPORT.md

5. **Executive Summary**
   - What works
   - What doesn't
   - What's missing
   - Recommendations

---

## ESTIMATED SCOPE

- **27+ modules to audit** (21 services + 6 buses + extras)
- **~5,000 lines of telemetry code** (estimated)
- **100+ metrics to document** (conservative estimate)
- **27+ test files to create**
- **4 major documentation deliverables**

This is a FORENSIC AUDIT - we're doing archaeology on our own codebase.
