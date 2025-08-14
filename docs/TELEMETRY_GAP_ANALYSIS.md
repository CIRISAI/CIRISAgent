# Telemetry Gap Analysis

## Executive Summary

The telemetry guide documents 36 endpoints, but only 6 (20%) actually exist. This analysis identifies:
1. What telemetry data IS collected internally
2. Where it's exposed (if anywhere)
3. What needs to be built

---

## 1. CLAIMED vs ACTUAL ENDPOINTS

### ✅ WORKING (6 endpoints)
| Endpoint | Actual Path | Data Source |
|----------|------------|-------------|
| System Health | `/system/health` | ResourceMonitor + ServiceRegistry |
| System Time | `/system/time` | TimeService |
| System Resources | `/system/resources` | ResourceMonitor |
| System Services | `/system/services` | ServiceRegistry |
| Memory Stats | `/memory/stats` | MemoryService (graph stats) |
| Memory Timeline | `/memory/timeline` | MemoryService (graph queries) |

### ❌ MISSING (24 endpoints claimed but not implemented)
| Claimed Endpoint | Should Show | Currently Collected? | Where? |
|-----------------|-------------|---------------------|--------|
| `/telemetry/service-registry` | Service details, capabilities | YES | ServiceRegistry has all data |
| `/telemetry/llm/usage` | Token counts, costs | YES | LLMBus tracks metrics |
| `/telemetry/circuit-breakers` | CB states | YES | ServiceRegistry._circuit_breakers |
| `/telemetry/handlers` | Handler invocations | PARTIAL | Some in audit log |
| `/telemetry/errors` | Recent errors | YES | IncidentManagementService |
| `/telemetry/discord/status` | Discord health | YES | DiscordAdapter has connection info |
| `/telemetry/tsdb/status` | TSDB consolidation | YES | TSDBConsolidationService |
| `/telemetry/aggregates/hourly` | Hourly metrics | NO | Not aggregated |
| `/telemetry/rate-limits` | API rate limits | NO | Not implemented |
| `/visibility/cognitive-state` | Current state | YES | RuntimeControlService |
| `/visibility/thoughts` | Active thoughts | YES | ProcessingQueue |
| `/visibility/system-snapshot` | Full state | PARTIAL | Various services |
| `/incidents/recent` | Recent incidents | YES | IncidentManagementService |
| `/audit/recent` | Recent audit events | YES | AuditService (different path) |
| `/runtime/queue/status` | Queue depth | YES | RuntimeControlService |

---

## 2. WHERE IS THE DATA?

### 🎯 Data That EXISTS But Isn't Exposed

#### LLM Metrics (LLMBus)
```python
# ciris_engine/logic/buses/llm_bus.py
self.service_metrics: dict[str, ServiceMetrics] = defaultdict(ServiceMetrics)
# Tracks: total_requests, failed_requests, total_latency_ms, average_latency_ms
# But NO endpoint exposes this!
```

#### Circuit Breakers (ServiceRegistry)
```python
# ciris_engine/logic/registries/base.py
self._circuit_breakers: Dict[str, CircuitBreaker] = {}
# Has state, failure_count, success_count, last_failure
# Only exposed via get_provider_info() partially
```

#### Handler Metrics
```python
# Currently scattered:
# - Some in AuditService (handler actions)
# - Some in telemetry.memorize_metric() calls
# - No central handler tracking
```

#### Incident Data (IncidentManagementService)
```python
# ciris_engine/logic/services/graph/incident_management.py
# Stores incidents in graph but no API endpoint
# Only logs to incidents_latest.log file
```

#### Discord Status
```python
# ciris_engine/logic/adapters/discord/discord_connection_manager.py
# Has connected, latency, reconnect_count
# Not exposed via API
```

### 📊 Data That's PARTIALLY Collected

#### Resource History
- Current: ResourceMonitor has current snapshot
- History: TelemetryService memorizes metrics to graph
- Gap: No time-series query endpoint

#### Processing Queue
- Exists in RuntimeControlService
- Has `/system/runtime/queue` but different format than documented

#### Cognitive State
- Exists in multiple places
- Shown in `/system/health` but not dedicated endpoint

---

## 3. ACTUAL DATA FLOW

### How Telemetry Currently Works:

```
1. Services generate metrics
   ↓
2. TelemetryService.memorize_metric() → Graph Memory
   ↓
3. TSDBConsolidationService (every 6 hours) → Consolidates
   ↓
4. Graph queries possible but no REST endpoints
```

### Where It's Stuck:
- Data goes INTO graph
- No endpoints to get it OUT (except memory/timeline)
- No aggregation layer
- No rate limiting implementation

---

## 4. BOTTOMS-UP IMPLEMENTATION SPIKE

### Phase 1: Expose What Already Exists

#### A. LLM Metrics Endpoint
```python
# NEW: /telemetry/llm/usage
# Source: LLMBus.service_metrics + get_service_stats()
# Returns: Requests, tokens, costs, latencies per provider
```

#### B. Circuit Breaker Status
```python
# NEW: /telemetry/circuit-breakers
# Source: ServiceRegistry._circuit_breakers
# Returns: All CBs with state, counts, last failure
```

#### C. Incident Stream
```python
# NEW: /incidents/recent
# Source: IncidentManagementService.get_recent_incidents()
# Returns: Graph query of incident nodes
```

#### D. Handler Metrics
```python
# NEW: /telemetry/handlers
# Source: Build new HandlerMetricsCollector
# Track: Every handler invocation via decorator
```

### Phase 2: Build Missing Aggregation

#### E. Metrics Aggregation Service
```python
# NEW SERVICE: MetricsAggregationService
# - Queries graph every hour
# - Computes hourly/daily aggregates
# - Stores back to graph with AGGREGATED_FROM edges
```

#### F. Rate Limiter Implementation
```python
# NEW: RateLimiterMiddleware
# - Track requests per API key
# - Return X-RateLimit headers
# - Expose via /telemetry/rate-limits
```

### Phase 3: Unify Visibility

#### G. System Snapshot Endpoint
```python
# NEW: /visibility/system-snapshot
# Combines:
# - Cognitive state
# - Active thoughts (from queue)
# - Resource usage
# - Service health
# - Recent decisions (from audit)
```

#### H. Extended Status Endpoints
```python
# NEW: /visibility/cognitive-state
# NEW: /visibility/thoughts
# Source: RuntimeControlService + ProcessingQueue
```

---

## 5. DATA COLLECTION GAPS

### Not Currently Collected:
1. **API Request Metrics** - No per-endpoint tracking
2. **Rate Limit Tracking** - Not implemented
3. **Hourly Aggregates** - Raw data only
4. **Error Stack Traces** - Logged but not stored
5. **Backup Status** - No backup system

### Collected But Lost:
1. **Handler Timing** - Not consistently stored
2. **WebSocket Events** - Not tracked
3. **Service Start Times** - Not preserved

---

## 6. QUICK WINS vs LONG TERM

### 🎯 Quick Wins (Can implement TODAY):
1. Expose LLMBus metrics - Data exists
2. Circuit breaker status - Data exists
3. Queue status - Already partial endpoint
4. Discord status - Connection manager has it

### 📅 Medium Term (Needs new code):
1. Handler metrics collector
2. Incident query endpoint
3. Hourly aggregation
4. Rate limiter

### 🔮 Long Term (Architectural):
1. Time-series database
2. Metrics export (Prometheus)
3. WebSocket telemetry stream
4. Backup system

---

## RECOMMENDATIONS

### Immediate Actions:
1. **Stop claiming endpoints that don't exist** - Update guide
2. **Expose existing data** - LLM, CB, Queue endpoints
3. **Add handler tracking** - Decorator-based

### Architecture Decisions Needed:
1. **Should we aggregate in graph or separate DB?**
2. **Real-time streaming vs polling?**
3. **Retention policies for metrics?**

### Critical Missing Pieces:
1. **No request-level tracing** - Can't follow request through system
2. **No metric aggregation** - Can't see trends
3. **No export capability** - Can't integrate with monitoring tools
