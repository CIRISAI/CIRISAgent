# Bottoms-Up Telemetry Implementation Spike

## Goal
Expose the telemetry data that ALREADY EXISTS in CIRIS but isn't accessible via API.

---

## Phase 1: Quick Wins (Data Already Exists) - 2 Days

### 1.1 LLM Metrics Endpoint
- [ ] Create `/telemetry/llm/usage` endpoint in telemetry.py
- [ ] Source: `LLMBus.service_metrics` dictionary
- [ ] Add method: `LLMBus.get_all_metrics()` to collect
- [ ] Return: tokens, costs, latencies, failures per provider
- [ ] Test: Verify against actual LLM calls

### 1.2 Circuit Breaker Status Endpoint
- [ ] Create `/telemetry/circuit-breakers` endpoint
- [ ] Source: `ServiceRegistry._circuit_breakers`
- [ ] Add method: `ServiceRegistry.get_circuit_breaker_status()`
- [ ] Return: state, failure_count, success_count, last_failure
- [ ] Include: threshold settings and recovery timeout

### 1.3 Service Registry Details
- [ ] Create `/telemetry/service-registry` endpoint
- [ ] Source: `ServiceRegistry.get_provider_info()` - enhance it
- [ ] Add: capabilities, metadata, priority groups
- [ ] Include: selection strategy per service type
- [ ] Return: full service topology

### 1.4 Discord Connection Status
- [ ] Create `/telemetry/discord/status` endpoint
- [ ] Source: `DiscordConnectionManager` state
- [ ] Add method: `DiscordAdapter.get_connection_status()`
- [ ] Return: connected, latency, guilds, reconnection count
- [ ] Include: last disconnect reason

### 1.5 Processing Queue Status
- [ ] Fix `/runtime/queue/status` to match documentation
- [ ] Source: `RuntimeControlService.get_queue_status()`
- [ ] Add: queue items with age, priority
- [ ] Include: processing rate calculation
- [ ] Return: depth, items, average latency

---

## Phase 2: Collect Missing Data - 3 Days

### 2.1 Handler Metrics Collector
- [ ] Create `HandlerMetricsCollector` class
- [ ] Add decorator: `@track_handler_metrics`
- [ ] Apply to all handlers in processor
- [ ] Track: invocations, duration, errors, last_invocation
- [ ] Store in: memory with periodic graph write

### 2.2 Request Tracing
- [ ] Add `trace_id` generation in API adapter
- [ ] Pass trace_id through context
- [ ] Log trace_id in all services
- [ ] Create `/telemetry/traces/{trace_id}` endpoint
- [ ] Build trace from audit + logs

### 2.3 Error Collector
- [ ] Create `ErrorCollectorService`
- [ ] Hook into all exception handlers
- [ ] Capture: stack traces, context, resolution
- [ ] Store last 1000 errors in memory
- [ ] Create `/telemetry/errors` endpoint

### 2.4 Cognitive State Tracker
- [ ] Create `/visibility/cognitive-state` endpoint
- [ ] Source: `RuntimeControlService.processor_state`
- [ ] Add: state history, transitions, duration
- [ ] Include: allowed next states
- [ ] Track: state change reasons

### 2.5 Active Thoughts Endpoint
- [ ] Create `/visibility/thoughts` endpoint
- [ ] Source: `ProcessingQueue` items
- [ ] Add: thought content, handler, priority
- [ ] Include: processing status, age
- [ ] Return: active and queued thoughts

---

## Phase 3: Aggregation Layer - 3 Days

### 3.1 Metrics Aggregation Service
- [ ] Create `MetricsAggregationService`
- [ ] Run hourly via TaskScheduler
- [ ] Query graph for raw metrics
- [ ] Compute: averages, percentiles, trends
- [ ] Store aggregates with `AGGREGATED_FROM` edges

### 3.2 Hourly Aggregates Endpoint
- [ ] Create `/telemetry/aggregates/hourly` endpoint
- [ ] Source: Aggregated graph nodes
- [ ] Return: hourly summaries for last 24h
- [ ] Include: requests, errors, latencies, resources
- [ ] Add: comparison to previous period

### 3.3 Daily Summary Endpoint
- [ ] Create `/telemetry/summary/daily` endpoint
- [ ] Source: Aggregated data
- [ ] Compute: daily rollups
- [ ] Include: peak usage times
- [ ] Add: anomaly detection

### 3.4 TSDB Status Endpoint
- [ ] Create `/telemetry/tsdb/status` endpoint
- [ ] Source: `TSDBConsolidationService`
- [ ] Return: last consolidation, next scheduled
- [ ] Include: compression ratio, nodes consolidated
- [ ] Add: storage saved metrics

---

## Phase 4: Rate Limiting - 2 Days

### 4.1 Rate Limiter Middleware
- [ ] Create `RateLimiterMiddleware` class
- [ ] Implement token bucket algorithm
- [ ] Track per API key and endpoint
- [ ] Add Redis backend for distributed limiting
- [ ] Return `X-RateLimit-*` headers

### 4.2 Rate Limits Endpoint
- [ ] Create `/telemetry/rate-limits` endpoint
- [ ] Show current usage vs limits
- [ ] Include reset times
- [ ] Add per-endpoint breakdown
- [ ] Support quota increase requests

---

## Phase 5: Export & Integration - 2 Days

### 5.1 Prometheus Metrics
- [ ] Create `/metrics` endpoint
- [ ] Format in Prometheus exposition format
- [ ] Include all key metrics with labels
- [ ] Add histogram buckets for latencies
- [ ] Test with Prometheus scraper

### 5.2 Telemetry Export
- [ ] Create `/telemetry/export` endpoint
- [ ] Support formats: JSON, CSV, Parquet
- [ ] Add time range filtering
- [ ] Include compression for large exports
- [ ] Add async job for large exports

### 5.3 WebSocket Streaming
- [ ] Create `/ws/telemetry` WebSocket endpoint
- [ ] Stream real-time metrics
- [ ] Support channel subscriptions
- [ ] Add authentication
- [ ] Include heartbeat/reconnection

---

## Phase 6: Historical Data - 3 Days

### 6.1 Time-Series Queries
- [ ] Create `/telemetry/history` endpoint
- [ ] Query historical metrics from graph
- [ ] Support metric name filtering
- [ ] Add time range parameters
- [ ] Return data points with timestamps

### 6.2 Incident History
- [ ] Create `/incidents/recent` endpoint
- [ ] Source: `IncidentService._get_recent_incidents()`
- [ ] Add severity filtering
- [ ] Include resolution time
- [ ] Return incident timeline

### 6.3 Audit Trail Access
- [ ] Fix `/audit/recent` endpoint path
- [ ] Add time-based filtering
- [ ] Include actor filtering
- [ ] Add outcome filtering
- [ ] Support pagination

---

## Phase 7: System Visibility - 2 Days

### 7.1 System Snapshot
- [ ] Create `/visibility/system-snapshot` endpoint
- [ ] Combine all system state
- [ ] Include: identity, goals, resources
- [ ] Add: recent decisions, active contexts
- [ ] Create unified view

### 7.2 Service Health Details
- [ ] Enhance `/system/services/health` endpoint
- [ ] Add per-service metrics
- [ ] Include dependency health
- [ ] Add health history
- [ ] Calculate availability percentage

### 7.3 Handler Details
- [ ] Create `/telemetry/handlers` endpoint
- [ ] Show all handlers with metrics
- [ ] Include: last invocation, average duration
- [ ] Add: error rate, success rate
- [ ] Show handler dependencies

---

## Testing Strategy

### Unit Tests
- [ ] Test each new endpoint with mock data
- [ ] Verify response formats
- [ ] Test error conditions
- [ ] Check authorization

### Integration Tests
- [ ] Test data flow from source to endpoint
- [ ] Verify aggregation accuracy
- [ ] Test rate limiting
- [ ] Check WebSocket streaming

### Performance Tests
- [ ] Load test aggregation queries
- [ ] Benchmark export performance
- [ ] Test concurrent WebSocket connections
- [ ] Measure endpoint response times

### Production Validation
- [ ] Deploy to staging first
- [ ] Monitor memory usage
- [ ] Check graph query performance
- [ ] Validate with CIRISManager

---

## Implementation Order (Priority)

### Week 1: Expose Existing Data
1. LLM metrics endpoint
2. Circuit breaker status
3. Service registry details
4. Queue status fix
5. Discord status

### Week 2: Add Collection
1. Handler metrics
2. Error collector
3. Cognitive state
4. Active thoughts
5. Request tracing

### Week 3: Build Infrastructure
1. Aggregation service
2. Rate limiter
3. Prometheus export
4. WebSocket streaming
5. System snapshot

---

## Success Metrics

### Immediate (Week 1)
- [ ] 10+ new telemetry endpoints working
- [ ] CIRISManager can read LLM metrics
- [ ] Circuit breaker visibility achieved

### Short Term (Week 2)
- [ ] Handler performance tracked
- [ ] Error diagnosis improved
- [ ] Request tracing working

### Medium Term (Week 3)
- [ ] Hourly aggregates available
- [ ] Rate limiting enforced
- [ ] Prometheus integration working

### Long Term (Month 2)
- [ ] Full observability stack
- [ ] Historical analysis possible
- [ ] Predictive insights available

---

## Risks & Mitigations

### Risk: Graph Query Performance
- **Mitigation**: Add caching layer
- **Mitigation**: Optimize queries with indexes

### Risk: Memory Usage from Metrics
- **Mitigation**: Limit in-memory retention
- **Mitigation**: Periodic flush to graph

### Risk: Breaking Existing APIs
- **Mitigation**: Version new endpoints as v2
- **Mitigation**: Keep backward compatibility

### Risk: Data Inconsistency
- **Mitigation**: Single source of truth
- **Mitigation**: Validation at collection

---

## Dependencies

### Required Services
- MemoryService (graph storage)
- TelemetryService (metric storage)
- TaskScheduler (aggregation)
- TimeService (timestamps)

### External Libraries
- None required for Phase 1
- Redis for distributed rate limiting
- Prometheus client for metrics

### Team Dependencies
- CIRISManager team for validation
- DevOps for monitoring integration
- Security for rate limit policies

---

## Definition of Done

### Per Endpoint
- [ ] Endpoint implemented and tested
- [ ] SDK method added
- [ ] Documentation updated
- [ ] Integration test passing
- [ ] Deployed to production

### Per Phase
- [ ] All endpoints working
- [ ] Performance acceptable
- [ ] No memory leaks
- [ ] CIRISManager validated

### Overall
- [ ] 80% of claimed endpoints working
- [ ] Full observability achieved
- [ ] Export capabilities functional
- [ ] Historical analysis possible
