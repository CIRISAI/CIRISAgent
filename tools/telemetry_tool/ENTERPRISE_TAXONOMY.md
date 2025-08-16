# CIRIS Enterprise Metrics Taxonomy

## The Complete Hierarchy

```
CIRIS SYSTEM
│
├── CORE SERVICES (21) - Always running, singleton instances
│   ├── Graph Services (6) - Data persistence layer
│   ├── Infrastructure Services (7) - System foundation
│   ├── Governance Services (4) - Decision & control
│   ├── Runtime Services (3) - Execution layer
│   └── Tool Services (1) - Extended capabilities
│
├── MESSAGE BUSES (6) - Multi-provider routing layer
│   ├── CommunicationBus → routes to adapters
│   ├── MemoryBus → routes to memory service
│   ├── LLMBus → routes to LLM providers
│   ├── ToolBus → routes to tool providers
│   ├── RuntimeControlBus → routes to control interfaces
│   └── WiseBus → routes to wisdom sources
│
├── ADAPTERS (3 types, 7 total services at runtime)
│   ├── DiscordAdapter (adds 3 services)
│   ├── APIAdapter (adds 3 services)
│   └── CLIAdapter (adds 1 service)
│
├── RUNTIME OBJECTS (Not services, but metric sources)
│   ├── AgentProcessor - The main thought processor
│   ├── ProcessingQueue - Request queue manager
│   ├── CircuitBreaker - Per-service protection
│   ├── ServiceRegistry - Service discovery
│   ├── ServiceInitializer - Bootstrap coordinator
│   └── ActionDispatcher - Handler routing
│
└── HANDLERS (10) - Action executors
    ├── DeferHandler
    ├── ForgetHandler
    ├── MemorizeHandler
    ├── ObserveHandler
    ├── PonderHandler
    ├── RecallHandler
    ├── RejectHandler
    ├── SpeakHandler
    ├── TaskCompleteHandler
    └── ToolHandler
```

## The Math That Actually Works

**Current State (136 metrics):**
- 82 PULL metrics (from get_metrics/_collect_custom_metrics)
- 19 PUSH metrics (record_metric/memorize_metric)
- 44 Handler metrics (automatic)
- **Note**: Some overlap/double-counting in current scan

**Target: 250 metrics**
**Real Gap: 114 metrics**

**Smart Distribution Plan:**
```
Phase 1 - High-Value Services (5 × 12 = 60 metrics)
- llm_service: 12 metrics (token economics, model performance)
- runtime_control: 12 metrics (queue, processing, state)
- wise_authority: 12 metrics (decisions, deferrals, overrides)
- audit_service: 12 metrics (events, compliance, exports)
- telemetry_service: 12 metrics (aggregation, caching, consolidation)

Phase 2 - Runtime Objects (6 × 8 = 48 metrics)
- AgentProcessor: 8 metrics (thoughts, state transitions)
- ProcessingQueue: 8 metrics (depth, latency, throughput)
- CircuitBreaker: 8 metrics (trips, resets, states)
- ServiceRegistry: 8 metrics (registrations, lookups)
- ServiceInitializer: 8 metrics (startup time, dependencies)
- ActionDispatcher: 8 metrics (routing, fallbacks)

Phase 3 - Fill Remaining (6-10 metrics total)
- Add 1-2 metrics to existing services that need them

Total: 60 + 48 + 10 = 118 metrics (slightly over gap, perfect!)
```

## Enterprise Metrics Schema Design

### 1. Metric Namespacing
```
{layer}.{component}.{category}.{metric}

Examples:
- service.llm.token.input_count
- bus.memory.routing.requests_per_second
- adapter.discord.connection.latency_ms
- runtime.processor.thought.processing_time_ms
- handler.speak.execution.success_rate
```

### 2. Metric Categories (Universal across all components)

**Availability Metrics**
- `healthy` - Binary health status (0.0 or 1.0)
- `uptime_seconds` - Time since last restart
- `availability_percent` - Uptime percentage over window

**Performance Metrics**
- `latency_p50_ms` - Median latency
- `latency_p95_ms` - 95th percentile latency
- `latency_p99_ms` - 99th percentile latency
- `throughput_per_second` - Operations per second
- `queue_depth` - Current queue size

**Resource Metrics**
- `memory_mb` - Memory usage in MB
- `cpu_percent` - CPU utilization
- `connections_active` - Active connections
- `storage_mb` - Storage used

**Business Metrics**
- `requests_total` - Total requests handled
- `errors_total` - Total errors encountered
- `success_rate` - Success percentage
- `cost_cents` - Accumulated cost
- `revenue_cents` - Generated revenue (if applicable)

**Quality Metrics**
- `error_rate` - Error percentage
- `retry_count` - Number of retries
- `timeout_count` - Number of timeouts
- `validation_failures` - Failed validations

### 3. Collection Strategy by Component Type

**Services (21)** - All get BaseService metrics FREE
- Inherit: uptime, health, requests, errors, error_rate
- Add via _collect_custom_metrics(): 7-12 service-specific

**Buses (6)** - Routing and aggregation metrics
- Provider count, routing decisions, fallback usage
- Collected via bus-specific instrumentation

**Adapters (3 types)** - Communication metrics
- Connection state, message rates, protocol-specific
- Collected via adapter hooks

**Runtime Objects (6)** - Core processing metrics
- Not services, but have metric methods
- Collected via direct instrumentation

**Handlers (10)** - Automatic collection
- Already tracked by ActionDispatcher
- No additional implementation needed

### 4. Enterprise Features Needed

**Metric Metadata**
```python
@dataclass
class MetricDefinition:
    name: str
    type: Literal["counter", "gauge", "histogram", "summary"]
    unit: str  # "bytes", "seconds", "requests", "percent"
    description: str
    labels: Dict[str, str]  # For dimensional metrics
    retention_days: int
    alert_thresholds: Optional[Dict[str, float]]
```

**Aggregation Levels**
- Instance level (single service)
- Service type level (all memory services)
- Layer level (all graph services)
- System level (entire CIRIS)

**Export Formats**
- Prometheus exposition format
- OpenTelemetry OTLP
- CloudWatch EMF
- StatsD
- JSON streaming

### 5. The Tracker Design

```python
class EnterpriseMetricsTracker:
    """Track metric implementation across all components."""

    def __init__(self):
        self.components = {
            "services": {},      # 21 core services
            "buses": {},         # 6 message buses
            "adapters": {},      # 3 adapter types
            "runtime": {},       # 6 runtime objects
            "handlers": {}       # 10 handlers
        }

    def scan_implementation(self):
        """Scan codebase for metric implementations."""
        # For each component type, check:
        # 1. Has get_metrics()? (services)
        # 2. Has instrumentation? (buses, runtime)
        # 3. Has handler metrics? (automatic)

    def calculate_coverage(self):
        """Calculate metric coverage by component."""
        return {
            "services": self._count_service_metrics(),
            "buses": self._count_bus_metrics(),
            "adapters": self._count_adapter_metrics(),
            "runtime": self._count_runtime_metrics(),
            "handlers": 44,  # Always 44 (automatic)
            "total": self._sum_all_metrics()
        }

    def generate_dashboard(self):
        """Generate implementation dashboard."""
        # Show:
        # - Coverage by component type
        # - Implementation status (red/yellow/green)
        # - Missing high-value metrics
        # - Progress toward 250 target
```

### 6. Why This Architecture Scales

**Separation of Concerns**
- Services: Business logic metrics
- Buses: Routing metrics
- Adapters: Protocol metrics
- Runtime: Processing metrics
- Handlers: Execution metrics

**No Metric Sprawl**
- Each component has defined metric categories
- Naming convention prevents duplicates
- Clear ownership model

**Enterprise Integration**
- Standard export formats
- Dimensional metrics with labels
- Proper retention policies
- Alert threshold definitions

**Performance**
- PULL metrics computed on-demand (no overhead)
- PUSH metrics batched to TSDB
- Consolidation reduces storage
- Efficient aggregation paths

### 7. Dream Enterprise Schema

```yaml
# metrics-definition.yaml
version: "1.0"
namespace: "ciris"

dimensions:
  - service_name
  - service_type
  - adapter_type
  - environment
  - region
  - tenant_id

metrics:
  # Service Metrics
  - name: service.{service_name}.health
    type: gauge
    unit: ratio
    description: "Service health status"
    retention_days: 30
    alerts:
      critical: "< 0.5"
      warning: "< 0.9"

  - name: service.{service_name}.latency
    type: histogram
    unit: milliseconds
    buckets: [10, 50, 100, 500, 1000, 5000]
    description: "Service operation latency"
    retention_days: 90

  # Bus Metrics
  - name: bus.{bus_name}.providers.active
    type: gauge
    unit: count
    description: "Active providers for this bus"

  # Runtime Metrics
  - name: runtime.processor.thoughts.processed
    type: counter
    unit: thoughts
    description: "Total thoughts processed"

  # Cost Metrics
  - name: llm.cost.total
    type: counter
    unit: cents
    description: "Total LLM costs"
    labels:
      model: "{model_name}"
      provider: "{provider_name}"
    alerts:
      budget_warning: "> 10000"  # $100
```

## The Path Forward

1. **Implement Phase 1**: Add _collect_custom_metrics to 5 high-value services (60 metrics)
2. **Instrument Runtime Objects**: Add metric methods to 6 runtime objects (48 metrics)
3. **Update Tracker**: Make it understand this full taxonomy
4. **Create Metric Registry**: Central definition of all metrics
5. **Build Export Pipeline**: Prometheus/OTel/CloudWatch exporters
6. **Add Dashboards**: Grafana dashboards by component type

This gets us to 250 metrics with room to grow, while maintaining clarity and preventing metric explosion.
