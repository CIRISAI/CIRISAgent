# Telemetry Investigation Report - 10 Unhealthy Services

## Summary
10 out of 40 services (25%) are reporting as unhealthy with 0 uptime. These services are being instantiated but not properly tracked by the telemetry system.

## Unhealthy Services by Category

### 1. Graph Services (2)
- `ServiceType.CONFIG_graph` - GraphConfigService
- `ServiceType.MEMORY_local_graph` - LocalGraphMemoryService

### 2. API Adapter Services (3)
- `ServiceType.COMMUNICATION_api_026080` - APICommunicationService
- `ServiceType.RUNTIME_CONTROL_api_runtime` - APIRuntimeControlService
- `ServiceType.TOOL_api_tool` - APIToolService

### 3. Tool Services (1)
- `ServiceType.TOOL_secrets` - SecretsToolService

### 4. Mock Services (1)
- `ServiceType.LLM_mock` - MockLLMService

### 5. Infrastructure Services (1)
- `ServiceType.TIME_time` - TimeService

### 6. Governance Services (1)
- `ServiceType.WISE_AUTHORITY_wise_authority` - WiseAuthorityService

### 7. Special Services (1)
- `ServiceType.TSDB_CONSOLIDATION_tsdbconsolidation_*` - TSDBConsolidationService

## Root Cause Analysis

### Pattern 1: Services Not Calling Parent start()
Many of these services likely override `start()` without calling `super().start()` or `BaseService.start(self)`.

### Pattern 2: Direct Service Creation
Some services (like TimeService) are created directly without going through ServiceRegistry, missing telemetry initialization.

### Pattern 3: Adapter Services Missing Initialization
API adapter services inherit from BaseService but may not properly initialize telemetry tracking.

### Pattern 4: Mock Services Not Integrated
MockLLMService was recently changed to inherit from BaseService but may not be fully integrated.

## Investigation Steps

1. **Check TimeService** - Core infrastructure service, should be simplest to fix
2. **Fix GraphConfigService** - Graph service telemetry
3. **Fix LocalGraphMemoryService** - Memory bus provider
4. **Fix WiseAuthorityService** - Governance service
5. **Fix TSDBConsolidationService** - Already has telemetry, timing issue?
6. **Fix MockLLMService** - Recently modified, verify integration
7. **Fix API Adapter Services** - APICommunicationService, APIRuntimeControlService, APIToolService
8. **Fix SecretsToolService** - Tool service telemetry

## Next Actions
1. Verify each service calls parent start() method
2. Ensure _start_time is set in start()
3. Verify services are registered with ServiceRegistry
4. Check TelemetryAggregator collection logic
