# CIRIS Telemetry Architecture Documentation
*Version: 1.4.5*
*Last Updated: 2025-08-21*

## Executive Summary

The CIRIS telemetry system provides comprehensive observability for all system components through a unified collection pipeline. The architecture supports dynamic service registration, parallel metric collection, and real-time health monitoring.

**Service Architecture:**
- **Base Count**: 32 services (21 core + 6 buses + 2 runtime objects + 3 bootstrap)
- **Dynamic Count**: 9+ adapter services (3 per adapter instance)
- **Total Range**: 32-50+ services depending on active adapters

## Service Taxonomy & Collection Methods

### 1. Core Services (21 Services)

These services form the foundation of CIRIS and are collected directly by name:

#### Graph Services (6)
- `memory` - Graph-based memory storage and retrieval
- `config` - Configuration management via graph
- `telemetry` - Metrics collection and aggregation
- `audit` - Audit trail and compliance logging
- `incident_management` - Incident tracking and resolution
- `tsdb_consolidation` - Time-series data consolidation (6-hour windows)

#### Infrastructure Services (7)
- `time` - Centralized time service with UTC timezone awareness
- `shutdown` - Graceful shutdown coordination with Ed25519 signatures
- `initialization` - Multi-phase startup orchestration
- `authentication` - JWT-based auth with role-based access control
- `resource_monitor` - CPU, memory, and disk usage tracking
- `database_maintenance` - SQLite optimization and cleanup
- `secrets` - Secure secrets management with encryption

#### Governance Services (4)
- `wise_authority` - Ethical guidance and decision oversight
- `adaptive_filter` - Dynamic content filtering and moderation
- `visibility` - Transparency feeds and DSAR compliance
- `self_observation` - Pattern analysis and identity variance monitoring

#### Runtime Services (3)
- `llm` - LLM provider management (OpenAI, Anthropic, local models)
- `runtime_control` - Processing control and state management
- `task_scheduler` - Background task scheduling and execution

#### Tool Services (1)
- `secrets_tool` - Tool interface for secrets management

### 2. Message Buses (6 Buses)

Message buses enable decoupled communication and support multiple providers:

- `communication_bus` - Routes messages between adapters and core
- `llm_bus` - Load balances across LLM providers with circuit breakers
- `memory_bus` - Manages graph operations with broadcast support
- `runtime_control_bus` - Handles runtime commands and emergency stops
- `tool_bus` - Tool registration and execution routing
- `wise_bus` - Wisdom provider fan-out with medical domain blocking

### 3. Adapter Services (Dynamic)

Each adapter instance registers 3 services with unique instance IDs:

#### API Adapter Services
- `ServiceType.COMMUNICATION_api_{id}` - REST API message handling
- `ServiceType.TOOL_api_tool` - HTTP-based tool execution (curl, etc.)
- `ServiceType.RUNTIME_CONTROL_api_runtime` - Runtime control via API

#### CLI Adapter Services
- `ServiceType.COMMUNICATION_cli_{id}` - Terminal-based interaction
- `ServiceType.TOOL_cli_{id}` - CLI tool execution
- `ServiceType.WISE_AUTHORITY_cli_{id}` - CLI-based guidance

#### Discord Adapter Services
- `ServiceType.COMMUNICATION_discord_{id}` - Discord message handling
- `ServiceType.TOOL_discord_{id}` - Discord-specific tools
- `ServiceType.WISE_AUTHORITY_discord_{id}` - Discord moderation guidance

### 4. Runtime Objects (2 Services)

Core runtime components with telemetry:

- `agent_processor` - Cognitive state machine (6 states: WAKEUP, WORK, PLAY, SOLITUDE, DREAM, SHUTDOWN)
- `service_registry` - Service discovery with circuit breakers and health checks

### 5. Bootstrap Services (Per-Adapter)

Adapter initialization tracking:
- `{adapter}_bootstrap` - Tracks adapter startup and configuration

## Collection Methods Analysis

### Collection Types

1. **Direct Collection**
   - Core services collected by name
   - Message buses collected with "_bus" suffix
   - Uses BaseService.get_metrics() interface

2. **Registry Collection**
   - Adapter services collected via ServiceRegistry
   - Dynamic instance IDs appended to service names
   - Supports multiple instances of same adapter type

3. **Error Handling**
   - Services without proper metrics return unhealthy status
   - No fake data or fallback metrics ever generated
   - Failed collections logged as warnings in telemetry service

## Architecture Deltas

### Expected vs Actual

| Component | Expected | Actual | Status | Notes |
|-----------|----------|--------|--------|-------|
| Core Services | 21 | 21 | ✅ | All present, collected by name |
| Message Buses | 6 | 6 | ✅ | All healthy with metrics |
| Adapter Services | 9 | 9 | ✅ | 3 per adapter type |
| Runtime Objects | 2+ | 2 | ✅ | agent_processor, service_registry |
| Bootstrap Services | - | 3 | ✅ | One per adapter |
| **TOTAL** | 38+ | 41 | ✅ | |

### Key Observations

1. **ServiceType Enumeration**: Adapter services use `ServiceType.SERVICE_adapter_id` format with instance IDs
2. **Core Services**: Collected directly by name, not through ServiceType enum
3. **Double Registration Prevention**: Fixed to prevent duplicate entries
4. **Telemetry Flow**: All services → TelemetryAggregator → Unified endpoint
5. **Health Determination**: Based on `_started` flag in BaseService

## Metrics Quality

### Non-Null Metrics Summary

- **Custom Metrics**: 11/41 services report custom metrics
- **Uptime**: 38/41 services report valid uptime (>0)
- **Error Tracking**: All services track errors (0 errors = healthy system)
- **Request Handling**: Adapter services track requests

### Notable Custom Metrics

1. **agent_processor**:
   - Current state: shutdown (state #5)
   - 12 thoughts processed
   - 4 state transitions

2. **service_registry**:
   - 19 services registered
   - 643 lookups (100% hit rate)
   - 0 circuit breakers open

3. **Buses**:
   - LLM Bus: 72 requests, 2.3ms avg latency
   - Memory Bus: 617 operations
   - Communication Bus: 6 messages sent

## Telemetry Collection Pipeline

```
Services
  ├─> Core Services (collected by name)
  ├─> Adapter Services (collected via ServiceRegistry)
  └─> Buses (collected by name + "_bus")
      ↓
TelemetryAggregator.collect_all_telemetry()
  ├─> collect_service() for each core service
  ├─> collect_from_registry() for adapter services
  └─> Parallel collection with asyncio.gather()
      ↓
ServiceTelemetryData objects
      ↓
/v1/telemetry/unified endpoint
```

## Health Requirements (Covenant Compliance)

Per COVENANT requirements for system observability:
- ✅ **Integrity**: All services report health status
- ✅ **Accountability**: Audit trail via telemetry
- ✅ **Self-Assessment**: Real-time health monitoring
- ✅ **Transparency**: Unified telemetry endpoint

## Recommendations

1. **Discord Services**: Will be healthy with valid bot token
2. **Monitoring**: All services properly instrumented
3. **Coverage**: 100% service coverage achieved
4. **Performance**: Parallel collection ensures <1s response time
