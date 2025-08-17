# CIRIS v1.4.3 Telemetry Sources Analysis - VALIDATED REALITY

## Critical Understanding: Types vs Instances vs External Modules

**ADAPTERS CREATE SERVICE INSTANCES WITH UNIQUE IDs:**
- Adapter instances use IDs like `discord_0567`, `discord_759F` (NOT agent names)
- Each adapter creates SERVICE instances that register on message buses
- These service instances are additional occurrences of bussed services

**EXTERNAL MODULE LOADING (`ciris_modular_services`):**
- External modules can register as service occurrences on buses
- Example: `mock_llm` module registers on the LLMBus
- Wisdom modules (geo_wisdom, weather_wisdom, sensor_wisdom) register on WiseBus
- Each module is an ADDITIONAL occurrence of the bus service type

## Metric Source Architecture

### Static Type Count vs Dynamic Instance Count

**STATIC (Design Time): ~36 Source Types**
- These are the classes/types that CAN produce metrics
- Counted once regardless of runtime instances

**DYNAMIC (Runtime): Unbounded Service Instances**
- Each adapter creates multiple service instances
- Each external module adds service instances
- Buses aggregate metrics from ALL registered instances

## Complete Table of ~36 Real Metric Source TYPES

| Category | Service Name | Type | Methods | Notes |
|----------|-------------|------|---------|-------|
| **Base Services (4)** | | | | |
| | BaseService | Abstract | get_metrics, _collect_metrics, _collect_custom_metrics | Parent class for all services |
| | BaseGraphService | Abstract | _collect_custom_metrics | Parent for graph services |
| | BaseInfrastructureService | Abstract | _collect_custom_metrics | Parent for infrastructure services |
| | BaseScheduledService | Abstract | _collect_custom_metrics | Parent for scheduled services |
| **Graph Services (7)** | | | | |
| | AuditService | Core | get_metrics, _collect_custom_metrics | GraphAuditService implementation |
| | ConfigService | Core | get_metrics | GraphConfigService implementation |
| | IncidentManagementService | Core | get_metrics | Incident tracking |
| | MemoryService | Core | _collect_custom_metrics | LocalGraphMemoryService |
| | TelemetryService | Core | get_metrics, _collect_custom_metrics, get_telemetry | GraphTelemetryService - META SERVICE |
| | TSDBConsolidationService | Core | get_metrics | Time-series consolidation |
| | Service* | Duplicate? | get_metrics | Generic "Service" class |
| **Infrastructure Services (7)** | | | | |
| | AuthenticationService | Core | get_metrics, _collect_custom_metrics | Auth management |
| | InitializationService | Core | get_metrics, _collect_custom_metrics | Service startup |
| | ResourceMonitorService | Core | _collect_custom_metrics | Resource tracking |
| | ShutdownService | Core | get_metrics, _collect_custom_metrics | Graceful shutdown |
| | TaskSchedulerService | Core | get_metrics, _collect_custom_metrics | Task scheduling |
| | TimeService | Core | get_metrics, _collect_custom_metrics | Time synchronization |
| | DatabaseMaintenanceService | Core | get_metrics, _collect_custom_metrics | DB optimization |
| **Governance Services (4)** | | | | |
| | AdaptiveFilterService | Core | get_metrics, _collect_custom_metrics | Content filtering |
| | SelfObservationService | Core | get_metrics, _collect_custom_metrics | Self-monitoring |
| | VisibilityService | Core | _collect_custom_metrics | Transparency |
| | WiseAuthorityService | Core | _collect_custom_metrics | WA deferrals |
| **Runtime Services (3)** | | | | |
| | LLMService | Core | get_metrics, _collect_custom_metrics | LLM operations |
| | RuntimeControlService | Core | get_metrics, _collect_custom_metrics | Runtime control |
| | SecretsService | Core | get_metrics, _collect_custom_metrics | Secrets management |
| **Tool Services (1)** | | | | |
| | SecretsToolService | Core | get_metrics, _collect_custom_metrics | Secrets tool execution |
| **Message Buses (6)** | | | | |
| | CommunicationBus | Bus | get_metrics, _collect_metrics | Inter-service comms |
| | LLMBus | Bus | get_metrics, _collect_metrics | LLM routing |
| | MemoryBus | Bus | get_metrics, _collect_metrics | Memory operations |
| | ToolBus | Bus | get_metrics, _collect_metrics | Tool coordination |
| | RuntimeControlBus | Bus | get_metrics, _collect_metrics | Runtime commands |
| | WiseBus | Bus | get_metrics, _collect_metrics | WA broadcasts |
| **Adapters (5)** | | | | |
| | APIAdapter | Adapter | get_metrics | API interface |
| | CLIAdapter | Adapter | get_metrics | CLI interface |
| | DiscordAdapter | Adapter | get_metrics | Discord interface |
| | TelemetryHelpers* | Helper | get_telemetry | API route helper |
| | TelemetryRoute* | Route | get_telemetry | API route handler |
| **Processors (3)** | | | | |
| | AgentProcessor | Core | get_metrics | Main agent processor |
| | BaseProcessor | Abstract | get_metrics | Processor parent class |
| | MainProcessor* | Duplicate? | get_metrics | Likely same as AgentProcessor |
| **Registries (2)** | | | | |
| | ServiceRegistry | Core | get_metrics | Service discovery |
| | CircuitBreaker | Component | get_metrics | Service protection |
| **Other/Miscellaneous (5)** | | | | |
| | ServiceInitializer | Core | get_metrics | Service bootstrapping |
| | QueueStatus* | Component | get_metrics | Queue monitoring |
| | Correlations* | Helper | get_metrics | Correlation tracking |
| | ExampleUsage* | Example | get_metrics | Example code |
| | HotColdConfig* | Config | get_telemetry | Path configuration |

## Analysis of Duplicates and Edge Cases

### 1. **Identified Duplicates/Confusion**

- **TimeService** appears in both Infrastructure Services AND Message Buses categories (error in tool output)
- **"Service"** - Generic class name that's too vague
- **MainProcessor vs AgentProcessor** - Likely the same thing
- **SecretsService vs SecretsToolService** - Two different services for secrets handling

### 2. **Edge Cases & Misclassifications**

- **TelemetryHelpers/TelemetryRoute** - These are API route helpers, not true metric sources
- **ExampleUsage** - Documentation/example code, shouldn't count
- **HotColdConfig** - Configuration object, not a service
- **QueueStatus** - More of a data structure than a service
- **Correlations** - Helper utility, not a service

### 3. **Missing from Aggregator**

The TelemetryAggregator.CATEGORIES (41 sources) is missing:
- DatabaseMaintenanceService
- SecretsService (different from SecretsToolService)
- AgentProcessor
- ServiceRegistry
- CircuitBreaker
- ServiceInitializer

## Recommended Hierarchy & Categories

```
CIRIS Telemetry Sources (v1.4.3)
│
├── Core Services (21) - The actual CIRIS services
│   ├── Graph Services (6)
│   │   ├── Memory
│   │   ├── Config
│   │   ├── Telemetry (META)
│   │   ├── Audit
│   │   ├── IncidentManagement
│   │   └── TSDBConsolidation
│   │
│   ├── Infrastructure Services (7)
│   │   ├── Time
│   │   ├── Shutdown
│   │   ├── Initialization
│   │   ├── Authentication
│   │   ├── ResourceMonitor
│   │   ├── DatabaseMaintenance
│   │   └── Secrets
│   │
│   ├── Governance Services (4)
│   │   ├── WiseAuthority
│   │   ├── AdaptiveFilter
│   │   ├── Visibility
│   │   └── SelfObservation
│   │
│   └── Runtime Services (4)
│       ├── LLM
│       ├── RuntimeControl
│       ├── TaskScheduler
│       └── SecretsToolService
│
├── Message Buses (6) - Communication infrastructure
│   ├── CommunicationBus
│   ├── LLMBus
│   ├── MemoryBus
│   ├── ToolBus
│   ├── RuntimeControlBus
│   └── WiseBus
│
├── Adapters (3) - External interfaces
│   ├── APIAdapter
│   ├── CLIAdapter
│   └── DiscordAdapter
│
├── Core Components (5) - Infrastructure components
│   ├── AgentProcessor
│   ├── ServiceRegistry
│   ├── CircuitBreaker
│   ├── ServiceInitializer
│   └── ProcessingQueue
│
└── Base Classes (4) - Abstract implementations (don't count as sources)
    ├── BaseService
    ├── BaseGraphService
    ├── BaseInfrastructureService
    └── BaseScheduledService
```

## Final Validated Count (Tool-Confirmed)

**TRUE METRIC SOURCE TYPES: 38**
- 22 Core Services (7 Graph + 8 Infrastructure + 4 Governance + 2 Runtime + 1 Tool)
- 6 Message Buses
- 5 Core Components (AgentProcessor, ServiceRegistry, CircuitBreaker, ServiceInitializer, ProcessorProtocol)
- 5 Adapter Types (API, CLI, Discord + 2 helpers that shouldn't count)

**Reality Check - Actually: 36 REAL SOURCE TYPES**
- Excluding TelemetryHelpers and QueryResponse (API route helpers)
- = 3 true Adapter types (API, CLI, Discord)

**Excluded from count:**
- 5 Base Classes (abstract)
- 2 Helpers/Routes (TelemetryHelpers, QueryResponse)
- 1 Example (MetricsEnabledAdapter)
- 1 Config (HotColdConfig)
- 2 Misc parsing errors ("def", "class")

## Key Insights About Runtime Behavior

### How Runtime Service Registration Actually Works

**Adapters Create Service Instances:**
1. Each adapter (e.g., `discord_0567`) creates multiple service instances:
   - `DiscordCommunicationService` → registers on CommunicationBus
   - `DiscordWiseAuthorityService` → registers on WiseBus
   - `DiscordToolService` → registers on ToolBus

2. **Bus Registration Pattern:**
   - Buses support MULTIPLE service occurrences
   - Each adapter's services register as additional occurrences
   - Example: CommunicationBus might have:
     - `APICommunicationService` (from api_759F)
     - `DiscordCommunicationService` (from discord_0567)
     - `DiscordCommunicationService` (from discord_123A)
     - `CLICommunicationService` (from cli_8901)

**External Modules Add More Occurrences:**
- `mock_llm` → registers on LLMBus alongside OpenAI/Anthropic services
- `geo_wisdom` → registers on WiseBus
- `weather_wisdom` → registers on WiseBus
- `sensor_wisdom` → registers on WiseBus

### Implications for CIRISLens Visibility Platform

**Metric Aggregation Levels:**
1. **Bus Level**: Total metrics across ALL service instances on a bus
   - Example: LLMBus aggregates OpenAI + Anthropic + mock_llm + any others

2. **Service Type Level**: Metrics grouped by service type
   - All DiscordCommunicationService instances together
   - All APICommunicationService instances together

3. **Instance Level**: Individual service instance metrics
   - `discord_0567/DiscordCommunicationService` specifically
   - `api_759F/APICommunicationService` specifically

**Dynamic Nature:**
- Service instances can be created/destroyed at runtime
- External modules can be loaded/unloaded dynamically
- Adapter instances spawn/terminate based on connections
- CIRISLens must handle this dynamic topology

## Action Items

1. **Update TelemetryAggregator.CATEGORIES** to match reality:
   - Add DatabaseMaintenanceService to infrastructure
   - Add SecretsService to infrastructure
   - Add AgentProcessor to components
   - Remove TimeService duplicate (it's NOT in buses)

2. **Document adapter instance behavior:**
   - Each agent (datum, ciris) gets its own adapter instances
   - Metrics are PER INSTANCE, not per type
   - Registry tracks all instances separately

3. **Fix tool parsing errors:**
   - "def" and "class" being picked up as service names
   - RuntimeControlService showing as "def"

4. **CIRISLens should:**
   - Show total metrics across all adapter instances
   - Allow drilling down to specific instance metrics
   - Track instance lifecycle (creation/destruction)
