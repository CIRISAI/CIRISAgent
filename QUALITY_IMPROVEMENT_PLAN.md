# Quality Improvement Plan
**Version**: 1.5.5
**Date**: 2025-10-31

## Overview

This plan addresses three verified architectural issues that undermine CIRIS's core philosophy of type safety, consistency, and production quality.

---

## Issue 1: Telemetry Short-Circuit Bug (CRITICAL)

### Problem
The `collect_service()` method has an outdented return statement that executes after every successful collection, overwriting healthy metrics with `healthy=False`.

### Root Cause
```python
try:
    return metrics  # Executes successfully
except Exception as e:
    logger.error(...)
return ServiceTelemetryData(healthy=False)  # OUTDENTED - always executes!
```

### Solution Approach

**Phase 1: Fix the Bug**
1. Read `ciris_engine/logic/services/graph/telemetry_service/service.py:523-528`
2. Indent the return statement inside the except block
3. Verify no other return statements have this issue

**Phase 2: Add Regression Tests**
1. Create unit test: `test_collect_service_returns_healthy_metrics`
   - Mock a healthy service with metrics
   - Call `collect_service()`
   - Assert `result.healthy is True`
   - Assert uptime/error_count match expected values

2. Create unit test: `test_collect_service_exception_returns_unhealthy`
   - Mock service that raises exception
   - Call `collect_service()`
   - Assert `result.healthy is False`

3. Create integration test: `test_telemetry_unified_endpoint_shows_healthy_services`
   - Start API server with mock services
   - GET `/v1/telemetry/unified`
   - Assert `services_online > 0`
   - Assert at least one service reports `healthy: true`

**Phase 3: Verify Production Impact**
1. Deploy fix to test environment
2. Check `/v1/telemetry/unified` endpoint
3. Verify services report healthy status
4. Monitor for 24 hours

### Files to Modify
- `ciris_engine/logic/services/graph/telemetry_service/service.py`
- `tests/ciris_engine/logic/services/graph/test_telemetry_service_collection.py` (new)
- `tests/integration/test_telemetry_endpoints.py` (new or extend existing)

### Success Criteria
- [ ] Return statement indented inside except block
- [ ] 3 new tests passing
- [ ] All existing tests still passing
- [ ] Production telemetry shows healthy services

---

## Issue 2: Registry Wiring Bypass Pattern

### Problem
Three services use private `_set_service_registry()` methods called from ServiceInitializer, violating the "No Bypass Patterns" philosophy.

### Root Cause
Services need registry access after construction, but adding it to `__init__` would break existing instantiation. Private method calls became the workaround.

### Solution Approach

**Phase 1: Define Protocol**
1. Create `RegistryAwareServiceProtocol` in `ciris_engine/protocols/infrastructure.py`
   - Define `async def attach_registry(registry: ServiceRegistryProtocol) -> None`
   - Document purpose: post-construction registry injection
   - Add to protocol exports

2. Update protocol documentation
   - Add usage examples
   - Explain when to use vs constructor injection
   - Document bus discovery pattern

**Phase 2: Update Services**
1. GraphTelemetryService
   - Implement `RegistryAwareServiceProtocol`
   - Rename `_set_service_registry()` to `attach_registry()`
   - Make method public
   - Update docstring

2. SelfObservationService
   - Same changes as GraphTelemetryService

3. GraphAuditService
   - Same changes as GraphTelemetryService

**Phase 3: Update ServiceInitializer**
1. Replace direct private method calls with protocol-based check:
   ```python
   if isinstance(service, RegistryAwareServiceProtocol):
       await service.attach_registry(self.service_registry)
   ```

2. Update for all three services:
   - Line 568: telemetry_service_impl
   - Line 688: self_observation_service
   - Line 900: graph_audit

**Phase 4: Add Tests**
1. Create protocol compliance test
   - Verify all three services implement protocol
   - Verify `attach_registry()` is callable
   - Verify registry is stored correctly

2. Create integration test
   - Initialize services through ServiceInitializer
   - Verify services can access buses via registry
   - Verify services function correctly after attachment

**Phase 5: Cleanup**
1. Search codebase for any other `_set_service_registry` usage
2. Remove or update any remaining references
3. Update CLAUDE.md with protocol usage example

### Files to Modify
- `ciris_engine/protocols/infrastructure.py` (new protocol)
- `ciris_engine/logic/services/graph/telemetry_service/service.py`
- `ciris_engine/logic/services/governance/self_observation/service.py`
- `ciris_engine/logic/services/graph/audit_service/service.py`
- `ciris_engine/logic/runtime/service_initializer.py`
- `tests/protocols/test_registry_aware_protocol.py` (new)
- `CLAUDE.md` (add example)

### Success Criteria
- [ ] `RegistryAwareServiceProtocol` defined and documented
- [ ] All three services implement protocol with public method
- [ ] ServiceInitializer uses protocol-based injection
- [ ] All tests passing
- [ ] No remaining `_set_service_registry` private calls

---

## Issue 3: ServiceInitializer Monolith Refactoring

### Problem
ServiceInitializer is a 1,333-line monolith mixing 6 distinct concerns with weak typing (`config: Any` in 6 methods).

### Root Cause
Organic growth - every new service type added another initialization method, no architectural boundaries enforced.

### Solution Approach

**Phase 1: Define Architecture**
1. Design component structure:
   - `ConfigurationAdapter` - Environment → Typed Config
   - `InfrastructureBootstrapper` - Core services (memory, secrets, auth)
   - `ObservabilityComposer` - Telemetry, audit, monitoring
   - `GovernanceComposer` - WiseAuthority, filtering, self-observation
   - `ServiceOrchestrator` - Coordinates composers

2. Create typed configuration models:
   - `MemoryConfig` - Backend type, connection string, pool size
   - `LLMConfig` - Providers, API keys, fallback strategy
   - `AuthConfig` - JWT settings, password policy, session config
   - `TelemetryConfig` - Collection interval, retention policy
   - `WiseAuthorityConfig` - Deferral thresholds, notification settings

3. Document protocols:
   - Each composer returns protocol-typed bundles
   - All dependencies injected via constructor
   - No environment access inside composers

**Phase 2: Create Configuration Models**
1. Create `ciris_engine/schemas/config/` directory structure
2. Implement typed config models using Pydantic
3. Add validation rules and defaults
4. Write config model tests

**Phase 3: Create ConfigurationAdapter**
1. Extract environment probing logic from ServiceInitializer
2. Implement typed config loading methods
3. Handle environment variable resolution
4. Add configuration validation
5. Test all config loading paths

**Phase 4: Create InfrastructureBootstrapper**
1. Extract memory service initialization
2. Extract secrets service initialization
3. Extract authentication service initialization
4. Each method accepts typed config, returns protocol
5. Test each initialization path independently

**Phase 5: Create ObservabilityComposer**
1. Extract telemetry service initialization
2. Extract audit service initialization
3. Extract incident management initialization
4. Extract TSDB consolidation initialization
5. Test observability stack initialization

**Phase 6: Create GovernanceComposer**
1. Extract WiseAuthority initialization
2. Extract adaptive filter initialization
3. Extract self-observation initialization
4. Extract visibility service initialization
5. Test governance stack initialization

**Phase 7: Create ServiceOrchestrator**
1. Implement orchestration logic
2. Wire composers together with dependency injection
3. Manage initialization order and dependencies
4. Handle service lifecycle (start/stop/health)
5. Maintain backward compatibility with existing code

**Phase 8: Migrate ServiceInitializer**
1. Update ServiceInitializer to use new composers
2. Maintain existing public interface (no breaking changes)
3. Delegate to composers for actual initialization
4. Keep adapter-specific logic in ServiceInitializer
5. Preserve all existing tests

**Phase 9: Gradual Cutover**
1. Run both old and new paths in parallel (feature flag)
2. Verify identical behavior in test environment
3. Monitor production metrics during cutover
4. Remove old code path after validation period
5. Clean up deprecated methods

**Phase 10: Documentation and Cleanup**
1. Update architecture documentation
2. Add initialization flow diagrams
3. Document new composer patterns
4. Update CLAUDE.md with examples
5. Remove deprecated code comments

### Files to Create
- `ciris_engine/schemas/config/memory_config.py`
- `ciris_engine/schemas/config/llm_config.py`
- `ciris_engine/schemas/config/auth_config.py`
- `ciris_engine/schemas/config/telemetry_config.py`
- `ciris_engine/schemas/config/governance_config.py`
- `ciris_engine/logic/initialization/configuration_adapter.py`
- `ciris_engine/logic/initialization/infrastructure_bootstrapper.py`
- `ciris_engine/logic/initialization/observability_composer.py`
- `ciris_engine/logic/initialization/governance_composer.py`
- `ciris_engine/logic/initialization/service_orchestrator.py`

### Files to Modify
- `ciris_engine/logic/runtime/service_initializer.py` (delegate to composers)
- `docs/architecture/initialization.md` (update diagrams)
- `CLAUDE.md` (add initialization patterns)

### Tests to Create
- `tests/schemas/config/test_memory_config.py`
- `tests/schemas/config/test_llm_config.py`
- `tests/logic/initialization/test_configuration_adapter.py`
- `tests/logic/initialization/test_infrastructure_bootstrapper.py`
- `tests/logic/initialization/test_observability_composer.py`
- `tests/logic/initialization/test_governance_composer.py`
- `tests/logic/initialization/test_service_orchestrator.py`
- `tests/integration/test_initialization_flow.py`

### Success Criteria
- [ ] All typed config models created with validation
- [ ] ConfigurationAdapter loads all config types
- [ ] All composers create services independently
- [ ] ServiceOrchestrator coordinates full initialization
- [ ] ServiceInitializer delegates to composers
- [ ] All existing tests still passing
- [ ] No `config: Any` parameters remaining
- [ ] Architecture documentation updated
- [ ] CLAUDE.md includes initialization examples

---

## Sequencing and Dependencies

### Recommended Order

**Sprint 1: Critical Bug Fix**
- Issue 1: Telemetry Short-Circuit
  - Immediate production impact
  - Unblocks health monitoring
  - Small, focused change
  - Can deploy as hotfix

**Sprint 2: Architectural Cleanup**
- Issue 2: Registry Wiring Bypass
  - Depends on: Issue 1 (telemetry service working)
  - Low risk, clear pattern
  - Improves consistency
  - Sets precedent for protocol usage

**Sprint 3-6: Major Refactoring**
- Issue 3: ServiceInitializer Monolith
  - Depends on: Issue 2 (protocol patterns established)
  - High complexity, gradual rollout
  - Enables future extensibility
  - Requires careful validation

### Dependencies Between Issues

```
Issue 1 (Telemetry Bug)
    ↓
Issue 2 (Registry Protocol)
    ↓
Issue 3 (Initializer Refactor)
```

- Issue 2 requires Issue 1 to verify telemetry service works correctly
- Issue 3 requires Issue 2 to establish protocol-based injection pattern
- All three can share the same test infrastructure improvements

---

## Risk Mitigation

### Issue 1 Risks
- **Risk**: Breaking existing telemetry consumers
- **Mitigation**: Comprehensive integration tests before deploy

### Issue 2 Risks
- **Risk**: Missing other services that need registry access
- **Mitigation**: Search entire codebase for `_set_*` patterns

### Issue 3 Risks
- **Risk**: Breaking existing initialization flows
- **Mitigation**: Parallel execution with feature flag, gradual cutover

### General Risks
- **Risk**: Introducing new bugs during refactoring
- **Mitigation**: Maintain 100% test pass rate at every step
- **Mitigation**: Deploy to staging environment first
- **Mitigation**: Monitor production metrics during rollout

---

## Success Metrics

### Code Quality
- Zero `config: Any` parameters in initialization code
- Zero private `_set_*` method calls from external code
- ServiceInitializer < 500 lines

### Test Coverage
- Telemetry collection: 100% branch coverage
- Registry protocol: All implementations tested
- Initialization flow: End-to-end integration tests

### Production Health
- `/v1/telemetry/unified` shows accurate health status
- All services report metrics correctly
- No regressions in service initialization time

### Maintainability
- New service types can be added without modifying ServiceInitializer
- Configuration changes don't require code changes
- Clear separation of concerns in initialization code

---

## Next Steps

1. **Review this plan** with team/stakeholders
2. **Create tracking issues** for each phase
3. **Start with Issue 1** (telemetry bug fix)
4. **Validate in staging** before production deploy
5. **Monitor production** after each deployment
6. **Iterate based on learnings** from each phase
