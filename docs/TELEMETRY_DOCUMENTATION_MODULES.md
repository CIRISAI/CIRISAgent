# Locked Module List for Telemetry Documentation

## Naming Pattern: `{MODULENAME}_{MODULETYPE}_TELEMETRY.md`

---

## 1. MESSAGE BUSES (6 files)

| File Name | Source Path | Module Type |
|-----------|-------------|-------------|
| `LLM_BUS_TELEMETRY.md` | `ciris_engine/logic/buses/llm_bus.py` | BUS |
| `MEMORY_BUS_TELEMETRY.md` | `ciris_engine/logic/buses/memory_bus.py` | BUS |
| `COMMUNICATION_BUS_TELEMETRY.md` | `ciris_engine/logic/buses/communication_bus.py` | BUS |
| `WISE_BUS_TELEMETRY.md` | `ciris_engine/logic/buses/wise_bus.py` | BUS |
| `TOOL_BUS_TELEMETRY.md` | `ciris_engine/logic/buses/tool_bus.py` | BUS |
| `RUNTIME_CONTROL_BUS_TELEMETRY.md` | `ciris_engine/logic/buses/runtime_control_bus.py` | BUS |

---

## 2. GRAPH SERVICES (6 files)

| File Name | Source Path | Module Type |
|-----------|-------------|-------------|
| `MEMORY_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/graph/memory_service.py` | SERVICE |
| `CONFIG_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/graph/config_service.py` | SERVICE |
| `TELEMETRY_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/graph/telemetry_service.py` | SERVICE |
| `AUDIT_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/graph/audit_service.py` | SERVICE |
| `INCIDENT_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/graph/incident_service.py` | SERVICE |
| `TSDB_CONSOLIDATION_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/graph/tsdb_consolidation_service.py` | SERVICE |

---

## 3. INFRASTRUCTURE SERVICES (7 files)

| File Name | Source Path | Module Type |
|-----------|-------------|-------------|
| `TIME_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/infrastructure/time_service.py` | SERVICE |
| `SHUTDOWN_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/lifecycle/shutdown.py` | SERVICE |
| `INITIALIZATION_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/lifecycle/initialization.py` | SERVICE |
| `AUTHENTICATION_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/infrastructure/authentication.py` | SERVICE |
| `RESOURCE_MONITOR_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/infrastructure/resource_monitor.py` | SERVICE |
| `DATABASE_MAINTENANCE_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/infrastructure/database_maintenance.py` | SERVICE |
| `SECRETS_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/infrastructure/secrets.py` | SERVICE |

---

## 4. GOVERNANCE SERVICES (4 files)

| File Name | Source Path | Module Type |
|-----------|-------------|-------------|
| `WISE_AUTHORITY_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/governance/wise_authority.py` | SERVICE |
| `ADAPTIVE_FILTER_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/governance/adaptive_filter.py` | SERVICE |
| `VISIBILITY_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/governance/visibility.py` | SERVICE |
| `SELF_OBSERVATION_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/governance/self_observation.py` | SERVICE |

---

## 5. RUNTIME SERVICES (3 files)

| File Name | Source Path | Module Type |
|-----------|-------------|-------------|
| `LLM_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/runtime/llm_service.py` | SERVICE |
| `RUNTIME_CONTROL_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/runtime/control_service.py` | SERVICE |
| `TASK_SCHEDULER_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/runtime/task_scheduler.py` | SERVICE |

---

## 6. TOOL SERVICES (1 file)

| File Name | Source Path | Module Type |
|-----------|-------------|-------------|
| `SECRETS_TOOL_SERVICE_TELEMETRY.md` | `ciris_engine/logic/services/tools/secrets_tool.py` | SERVICE |

---

## 7. CORE INFRASTRUCTURE COMPONENTS (5 files)

| File Name | Source Path | Module Type |
|-----------|-------------|-------------|
| `SERVICE_REGISTRY_REGISTRY_TELEMETRY.md` | `ciris_engine/logic/registries/base.py` | REGISTRY |
| `CIRCUIT_BREAKER_COMPONENT_TELEMETRY.md` | `ciris_engine/logic/registries/circuit_breaker.py` | COMPONENT |
| `PROCESSING_QUEUE_COMPONENT_TELEMETRY.md` | `ciris_engine/logic/runtime/processing_queue.py` | COMPONENT |
| `AGENT_PROCESSOR_PROCESSOR_TELEMETRY.md` | `ciris_engine/logic/core/agent_processor.py` | PROCESSOR |
| `SERVICE_INITIALIZER_COMPONENT_TELEMETRY.md` | `ciris_engine/logic/initialization/service_initializer.py` | COMPONENT |

---

## 8. ADAPTER TELEMETRY (3 files - for completeness)

| File Name | Source Path | Module Type |
|-----------|-------------|-------------|
| `DISCORD_ADAPTER_TELEMETRY.md` | `ciris_engine/logic/adapters/discord/adapter.py` | ADAPTER |
| `API_ADAPTER_TELEMETRY.md` | `ciris_engine/logic/adapters/api/adapter.py` | ADAPTER |
| `CLI_ADAPTER_TELEMETRY.md` | `ciris_engine/logic/adapters/cli/adapter.py` | ADAPTER |

---

## TOTAL: 35 TELEMETRY DOCUMENTATION FILES

### Summary by Type:
- **6 BUS** telemetry docs
- **21 SERVICE** telemetry docs
- **1 REGISTRY** telemetry doc
- **3 COMPONENT** telemetry docs
- **1 PROCESSOR** telemetry doc
- **3 ADAPTER** telemetry docs

---

## File Location

All telemetry documentation files should be created in:
```
ciris_engine/docs/telemetry/
├── buses/
│   ├── LLM_BUS_TELEMETRY.md
│   ├── MEMORY_BUS_TELEMETRY.md
│   ├── COMMUNICATION_BUS_TELEMETRY.md
│   ├── WISE_BUS_TELEMETRY.md
│   ├── TOOL_BUS_TELEMETRY.md
│   └── RUNTIME_CONTROL_BUS_TELEMETRY.md
├── services/
│   ├── graph/
│   │   ├── MEMORY_SERVICE_TELEMETRY.md
│   │   ├── CONFIG_SERVICE_TELEMETRY.md
│   │   ├── TELEMETRY_SERVICE_TELEMETRY.md
│   │   ├── AUDIT_SERVICE_TELEMETRY.md
│   │   ├── INCIDENT_SERVICE_TELEMETRY.md
│   │   └── TSDB_CONSOLIDATION_SERVICE_TELEMETRY.md
│   ├── infrastructure/
│   │   ├── TIME_SERVICE_TELEMETRY.md
│   │   ├── SHUTDOWN_SERVICE_TELEMETRY.md
│   │   ├── INITIALIZATION_SERVICE_TELEMETRY.md
│   │   ├── AUTHENTICATION_SERVICE_TELEMETRY.md
│   │   ├── RESOURCE_MONITOR_SERVICE_TELEMETRY.md
│   │   ├── DATABASE_MAINTENANCE_SERVICE_TELEMETRY.md
│   │   └── SECRETS_SERVICE_TELEMETRY.md
│   ├── governance/
│   │   ├── WISE_AUTHORITY_SERVICE_TELEMETRY.md
│   │   ├── ADAPTIVE_FILTER_SERVICE_TELEMETRY.md
│   │   ├── VISIBILITY_SERVICE_TELEMETRY.md
│   │   └── SELF_OBSERVATION_SERVICE_TELEMETRY.md
│   ├── runtime/
│   │   ├── LLM_SERVICE_TELEMETRY.md
│   │   ├── RUNTIME_CONTROL_SERVICE_TELEMETRY.md
│   │   └── TASK_SCHEDULER_SERVICE_TELEMETRY.md
│   └── tools/
│       └── SECRETS_TOOL_SERVICE_TELEMETRY.md
├── components/
│   ├── SERVICE_REGISTRY_REGISTRY_TELEMETRY.md
│   ├── CIRCUIT_BREAKER_COMPONENT_TELEMETRY.md
│   ├── PROCESSING_QUEUE_COMPONENT_TELEMETRY.md
│   ├── AGENT_PROCESSOR_PROCESSOR_TELEMETRY.md
│   └── SERVICE_INITIALIZER_COMPONENT_TELEMETRY.md
└── adapters/
    ├── DISCORD_ADAPTER_TELEMETRY.md
    ├── API_ADAPTER_TELEMETRY.md
    └── CLI_ADAPTER_TELEMETRY.md
```

---

## Validation Checklist

For each file, verify:
- [ ] Module exists at specified path
- [ ] Module actually collects telemetry
- [ ] Naming follows `{MODULENAME}_{MODULETYPE}_TELEMETRY.md`
- [ ] Documentation matches actual code behavior
- [ ] Storage location is accurate (memory/graph/log/redis)
- [ ] Access methods are tested and working

---

## Priority Order

### Week 1 - High Impact (Quick Wins)
1. `LLM_BUS_TELEMETRY.md` - Most requested metrics
2. `SERVICE_REGISTRY_REGISTRY_TELEMETRY.md` - Circuit breakers, health
3. `RESOURCE_MONITOR_SERVICE_TELEMETRY.md` - System resources
4. `MEMORY_BUS_TELEMETRY.md` - Graph operations
5. `TELEMETRY_SERVICE_TELEMETRY.md` - How metrics are stored

### Week 2 - Core Services
6-11. All other buses
12-17. Graph services
18-24. Infrastructure services

### Week 3 - Complete Coverage
25-28. Governance services
29-31. Runtime services
32-35. Components and adapters

---

## Success Metric

**35 telemetry documentation files** that accurately describe:
- What telemetry exists
- Where it's stored
- How to access it
- What API endpoint would expose it

This becomes the **source of truth** for telemetry in CIRIS.
