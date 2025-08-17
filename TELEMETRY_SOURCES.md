# CIRIS v1.4.3 Telemetry Sources

**Total: 45 Unique Metric Sources**

## 📦 Core Services (21 Total)

### Base Services (4)
1. **BaseService** - Foundation for all services, provides 5 base metrics
2. **BaseGraphService** - Base for graph-backed services
3. **BaseInfrastructureService** - Base for infrastructure services
4. **BaseScheduledService** - Base for scheduled services

### Graph Services (6)
5. **AuditService** - Audit trail and compliance tracking
6. **ConfigService** - Configuration management
7. **IncidentManagementService** - Incident tracking and resolution
8. **MemoryService** - Graph memory operations
9. **TelemetryService** - Telemetry collection and aggregation
10. **TSDBConsolidationService** - Time-series data consolidation

### Infrastructure Services (6)
11. **AuthenticationService** - Authentication and authorization
12. **InitializationService** - System initialization
13. **ResourceMonitorService** - Resource monitoring
14. **ShutdownService** - Graceful shutdown management
15. **TaskSchedulerService** - Task scheduling and execution
16. **TimeService** - Time synchronization and management

### Governance Services (4)
17. **AdaptiveFilterService** - Message filtering and moderation
18. **SelfObservationService** - Self-monitoring and adaptation
19. **VisibilityService** - Transparency and observability
20. **WiseAuthorityService** - Ethical decision oversight

### Runtime Services (2)
21. **LLMService** - Large Language Model interactions
22. **RuntimeControlService** - Runtime control and management

### Tool Services (1)
23. **SecretsToolService** - Secrets management tools

## 🚌 Message Buses (6)
24. **CommunicationBus** - Message routing between adapters
25. **LLMBus** - LLM provider routing
26. **MemoryBus** - Memory service routing
27. **RuntimeControlBus** - Runtime control routing
28. **ToolBus** - Tool execution routing
29. **WiseBus** - Wisdom provider routing

## 🔌 Adapters (5)
30. **APIAdapter** - REST API interface
31. **CLIAdapter** - Command-line interface
32. **DiscordAdapter** - Discord bot interface
33. **TelemetryRoute** - API telemetry endpoints
34. **TelemetryHelpers** - Telemetry utility functions

## 🧠 Processors (3)
35. **MainProcessor** - Main message processing
36. **BaseProcessor** - Base processor implementation
37. **ProcessorBase** - Processor protocol definition

## 📊 System Components (11)

### Registries (2)
38. **ServiceRegistry** - Service registration and discovery
39. **CircuitBreaker** - Circuit breaker for resilience

### Other Components (9)
40. **DatabaseMaintenanceService** - Database maintenance operations
41. **SecretsService** - Core secrets management
42. **ServiceInitializer** - Service initialization
43. **QueueStatus** - Processing queue status
44. **Correlations** - Event correlation tracking
45. **ExampleUsage** - Example metric implementations

---

## Metric Collection Methods

Each source implements one or more of these methods:
- `get_metrics()` - Public interface for pulling metrics
- `_collect_metrics()` - Internal base metric collection
- `_collect_custom_metrics()` - Service-specific metrics
- `get_telemetry()` - Telemetry-specific metrics

## Metric Categories

### Pull Metrics (Real-time, on-demand)
- Retrieved via `/telemetry/metrics` API endpoint
- Not persisted unless explicitly pushed
- ~163 unique metric names

### Push Metrics (Historical, stored in TSDB)
- Stored via `memorize_metric()` calls
- Available for historical queries
- ~18 metrics tracked historically

### Base Metrics (All services)
- `uptime_seconds` - Service uptime
- `request_count` - Total requests handled
- `error_count` - Total errors encountered
- `error_rate` - Error rate calculation
- `healthy` - Health status (0.0 or 1.0)

## v1.4.3 Metrics Per Source

Average metrics per source: ~5-10 metrics
- Base services: 5 base metrics
- Specialized services: 5 base + 4-10 custom metrics
- Buses: 3-4 metrics
- Registries: 10-14 metrics (ServiceRegistry has the most)
