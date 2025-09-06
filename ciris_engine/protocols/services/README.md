# Service Protocols

This directory contains the protocol definitions for all 22 CIRIS services. Each protocol defines the exact interface that its corresponding service implementation must follow.

## Service Categories

### Graph Services (6)
Everything is memory - all state flows through these services:
- **[memory.py](./graph/memory.py)** - Core memory operations (memorize, recall, forget)
- **[config.py](./graph/config.py)** - Configuration as versioned nodes
- **[telemetry.py](./graph/telemetry.py)** - Metrics and telemetry data
- **[audit.py](./graph/audit.py)** - Unified audit (graph + file + hash chain)
- **[incident_management.py](./graph/incident_management.py)** - Incident tracking and management
- **[tsdb_consolidation.py](./graph/tsdb_consolidation.py)** - Time-series data consolidation

### Runtime Services (3)
Core runtime capabilities:
- **[llm.py](./runtime/llm.py)** - Primary language model interactions
- **[runtime_control.py](./runtime/runtime_control.py)** - Runtime coordination
- **[scheduler.py](./lifecycle/scheduler.py)** - Task scheduling and deferrals

### Infrastructure Services (7)
System foundations:
- **[time.py](./lifecycle/time.py)** - Centralized time operations (no datetime.now()!)
- **[shutdown.py](./lifecycle/shutdown.py)** - Graceful shutdown coordination
- **[initialization.py](./lifecycle/initialization.py)** - Service initialization sequencing
- **[authentication.py](./infrastructure/authentication.py)** - Authentication and authorization
- **[resource_monitor.py](./infrastructure/resource_monitor.py)** - Resource monitoring and limits
- **[database_maintenance.py](./infrastructure/database_maintenance.py)** - Database health and cleanup
- **[secrets.py](./runtime/secrets.py)** - Secrets management and filtering

### Governance Services (4)
System governance and control:
- **[wise_authority.py](./governance/wise_authority.py)** - Human oversight and deferrals
- **[filter.py](./governance/filter.py)** - Message filtering and prioritization
- **[visibility.py](./governance/visibility.py)** - API introspection and transparency
- **[self_observation.py](./adaptation/self_observation.py)** - Identity variance and pattern analysis

### Tool Services (1)
External tool integration:
- **[tool.py](./runtime/tool.py)** - External tool execution and coordination

## Bus Protocols (Not Services)

These define interfaces for adapter-provided functionality, not core services:
- **[communication.py](./governance/communication.py)** - Interface for adapter communication
- **[wa_auth.py](./governance/wa_auth.py)** - WA authorization interfaces

## Protocol Rules

1. **Exact Match**: Service implementations MUST implement every method in their protocol
2. **No Extras**: Service implementations MUST NOT have public methods outside the protocol
3. **Type Safety**: All parameters and returns must use typed schemas (no Dict[str, Any])
4. **Async First**: All operations that could be I/O bound must be async
5. **Health & Capabilities**: Every service must implement the base service methods

## Adding a New Service

1. Create the protocol file in this directory
2. Define the protocol interface extending from appropriate base
3. Update this README
4. Implement the service following the protocol exactly
5. Add protocol compliance tests

## Protocol Inheritance

All protocols inherit from base protocols in `ciris_engine/protocols/base.py`:
- `ServiceProtocol` - Base for all services (start, stop, is_healthy, get_capabilities)
- `GraphServiceProtocol` - Base for graph services (adds graph-specific methods)
- `CoreServiceProtocol` - Base for core services (adds core-specific methods)
