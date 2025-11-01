# ServiceInitializer Refactoring Checklist

**Version**: 1.0
**Date**: 2025-10-31


---

## Phase 1: Create Config Models (Week 1, Days 1-2)

### Infrastructure Config
- [ ] Create `ciris_engine/schemas/config/infrastructure_config.py`
- [ ] Implement `BillingConfig` with validation
  - [ ] Add `enabled`, `api_key`, `base_url`, `timeout_seconds`, `cache_ttl_seconds`, `fail_open` fields
  - [ ] Add `@field_validator` for API key requirement when enabled
  - [ ] Add `@classmethod from_env()` factory method
- [ ] Implement `SimpleCreditConfig`
  - [ ] Add `free_uses` field
  - [ ] Add `@classmethod from_env()` factory method
- [ ] Implement `ResourceMonitorConfig`
  - [ ] Add `credit_provider` enum field
  - [ ] Add `billing` and `simple` optional fields
  - [ ] Add validation for required config based on provider type
  - [ ] Add `@classmethod from_env()` with auto-detection
- [ ] Implement `DatabaseMaintenanceConfig`
  - [ ] Add `archive_dir_path`, `archive_older_than_hours` fields
- [ ] Implement `InfrastructureConfig` root
  - [ ] Combine ResourceMonitor and DatabaseMaintenance configs
  - [ ] Add `@classmethod from_env()`
- [ ] Write tests: `tests/schemas/config/test_infrastructure_config.py`
  - [ ] Test `BillingConfig.from_env()` loads all env vars correctly
  - [ ] Test `BillingConfig` validation fails when enabled but no API key
  - [ ] Test `SimpleCreditConfig.from_env()` loads free_uses
  - [ ] Test `ResourceMonitorConfig.from_env()` auto-detects billing vs simple
  - [ ] Test `InfrastructureConfig.from_env()` creates complete config

### Memory Config
- [ ] Create `ciris_engine/schemas/config/memory_config.py`
- [ ] Implement `MemoryConfig`
  - [ ] Add `secrets_key_path`, `secrets_db_path`, `memory_db_path` fields
  - [ ] Add `@classmethod from_essential_config()` factory method
- [ ] Write tests: `tests/schemas/config/test_memory_config.py`
  - [ ] Test `from_essential_config()` uses helper functions correctly
  - [ ] Test paths are converted to Path objects

### LLM Config
- [ ] Create `ciris_engine/schemas/config/llm_config.py`
- [ ] Implement `InstructorMode` enum
- [ ] Implement `LLMProviderConfig`
  - [ ] Add `api_key`, `base_url`, `model_name`, `instructor_mode`, `timeout_seconds`, `max_retries` fields
  - [ ] Add validation for timeout/retry ranges
- [ ] Implement `LLMConfig` root
  - [ ] Add `primary`, `secondary` (optional), `skip_initialization` fields
  - [ ] Add `@classmethod from_env_and_essential()`
- [ ] Write tests: `tests/schemas/config/test_llm_config.py`
  - [ ] Test primary LLM config loads from OPENAI_API_KEY
  - [ ] Test secondary LLM config loads from CIRIS_OPENAI_API_KEY_2
  - [ ] Test `skip_initialization=True` when requested
  - [ ] Test secondary is None when no key provided

### Observability Config
- [ ] Create `ciris_engine/schemas/config/observability_config.py`
- [ ] Implement `TelemetryConfig` (minimal, no fields needed currently)
- [ ] Implement `AuditConfig`
  - [ ] Add `export_path`, `export_format`, `enable_hash_chain`, `db_path`, `key_path`, `retention_days` fields
  - [ ] Add `@classmethod from_essential_config()`
- [ ] Implement `TSDBConfig`
  - [ ] Add `consolidation_interval_hours` (frozen at 6), `raw_retention_hours`, `db_path` fields
  - [ ] Add `@classmethod from_essential_config()`
- [ ] Implement `ObservabilityConfig` root
  - [ ] Combine Telemetry, Audit, TSDB configs
  - [ ] Add `@classmethod from_essential_config()`
- [ ] Write tests: `tests/schemas/config/test_observability_config.py`
  - [ ] Test `AuditConfig` loads all paths correctly
  - [ ] Test `TSDBConfig` respects frozen consolidation interval
  - [ ] Test `ObservabilityConfig.from_essential_config()` creates complete config

### Governance Config
- [ ] Create `ciris_engine/schemas/config/governance_config.py`
- [ ] Implement `AdaptiveFilterConfig` (minimal, uses injected dependencies)
- [ ] Implement `SelfObservationConfig`
  - [ ] Add `variance_threshold`, `observation_interval_hours` fields
  - [ ] Add validation for threshold range (0.0-1.0)
- [ ] Implement `VisibilityConfig`
  - [ ] Add `db_path` field
  - [ ] Add `@classmethod from_essential_config()`
- [ ] Implement `ConsentConfig`
  - [ ] Add `db_path` field
  - [ ] Add `@classmethod from_essential_config()`
- [ ] Implement `GovernanceConfig` root
  - [ ] Combine all governance configs
  - [ ] Add `@classmethod from_essential_config()`
- [ ] Write tests: `tests/schemas/config/test_governance_config.py`
  - [ ] Test `SelfObservationConfig` validates threshold range
  - [ ] Test configs load db paths correctly
  - [ ] Test `GovernanceConfig.from_essential_config()` creates complete config

### Root Config
- [ ] Create `ciris_engine/schemas/config/initialization_config.py`
- [ ] Implement `InitializationConfig` root
  - [ ] Add `infrastructure`, `memory`, `llm`, `observability`, `governance` fields
  - [ ] Add `@classmethod from_essential_config()` that coordinates all sub-configs
- [ ] Write tests: `tests/schemas/config/test_initialization_config.py`
  - [ ] Test `from_essential_config()` creates complete config tree
  - [ ] Test `skip_llm_init` propagates to LLMConfig
  - [ ] Test all sub-configs are properly typed

### Phase 1 Validation
- [ ] All config models import without errors
- [ ] No circular import dependencies
- [ ] All unit tests pass
- [ ] Run mypy on config modules - no errors

---

## Phase 2: Create ConfigurationAdapter (Week 1, Day 3)

### Implementation
- [ ] Create `ciris_engine/logic/initialization/` directory
- [ ] Create `configuration_adapter.py`
- [ ] Implement `ConfigurationAdapter` class
  - [ ] Add `__init__(essential_config: EssentialConfig)`
  - [ ] Add `_cached_config` attribute
  - [ ] Implement `load_config(skip_llm_init: bool = False) -> InitializationConfig`
  - [ ] Implement `reload_config(skip_llm_init: bool = False) -> InitializationConfig`
  - [ ] Add docstrings explaining single responsibility

### Testing
- [ ] Create `tests/logic/initialization/test_configuration_adapter.py`
- [ ] Test `load_config()` creates complete InitializationConfig
- [ ] Test `load_config()` caches result (same object returned twice)
- [ ] Test `reload_config()` clears cache and creates new config
- [ ] Test `skip_llm_init=True` propagates to LLMConfig
- [ ] Test with different EssentialConfig variations

### Phase 2 Validation
- [ ] ConfigurationAdapter has exactly 2 public methods
- [ ] No direct `os.getenv()` calls in adapter (all delegated to config models)
- [ ] All unit tests pass
- [ ] Config caching works correctly

---

## Phase 3: Create InfrastructureBootstrapper (Week 1, Days 4-5)

### Implementation
- [ ] Create `infrastructure_bootstrapper.py`
- [ ] Define `InfrastructureBundle` dataclass/model with protocol-typed fields
  - [ ] `time_service: TimeServiceProtocol`
  - [ ] `shutdown_service`, `initialization_service`, `resource_monitor_service`
  - [ ] `secrets_service: SecretsServiceProtocol`
  - [ ] `memory_service: MemoryServiceProtocol`
  - [ ] `config_service: ConfigServiceProtocol`
  - [ ] `secrets_tool_service`, `auth_service`, `wise_authority_service`
- [ ] Implement `InfrastructureBootstrapper` class
  - [ ] Add `__init__(infrastructure_config, memory_config)`
  - [ ] Implement `async def bootstrap() -> InfrastructureBundle`
  - [ ] Implement `async def _create_time_service()`
  - [ ] Implement `async def _create_shutdown_service()`
  - [ ] Implement `async def _create_initialization_service(time_service)`
  - [ ] Implement `async def _create_resource_monitor(time_service)`
  - [ ] Implement `async def _create_secrets_service(time_service)`
  - [ ] Implement `async def _create_memory_service(time_service, secrets_service)`
  - [ ] Implement `async def _create_config_service(memory_service, time_service)`
  - [ ] Implement `async def _create_secrets_tool_service(secrets_service, time_service)`
  - [ ] Implement `async def _create_auth_service(time_service)`
  - [ ] Implement `async def _create_wise_authority_service(time_service, auth_service)`

### Extract from ServiceInitializer
- [ ] Copy TimeService creation from lines 102-112
- [ ] Copy ShutdownService creation from lines 118-121
- [ ] Copy InitializationService creation from lines 123-127
- [ ] Copy ResourceMonitorService creation from lines 129-181 (with billing logic)
- [ ] Copy SecretsService creation from lines 186-271
- [ ] Copy LocalGraphMemoryService creation from lines 283-290
- [ ] Copy GraphConfigService creation from lines 293-322
- [ ] Copy SecretsToolService creation from lines 273-281
- [ ] Copy AuthenticationService creation from lines 381-402
- [ ] Copy WiseAuthorityService creation from lines 404-411

### Testing
- [ ] Create `tests/logic/initialization/test_infrastructure_bootstrapper.py`
- [ ] Test `bootstrap()` creates all 10 services
- [ ] Test services created in correct dependency order (mock and track call order)
- [ ] Test each `_create_X_service()` method independently
- [ ] Test with billing enabled config
- [ ] Test with simple credit provider config
- [ ] Test error propagation when service fails to start

### Phase 3 Validation
- [ ] Returns `InfrastructureBundle` with all 10 services
- [ ] No `config: Any` parameters
- [ ] No direct environment variable access
- [ ] All unit tests pass
- [ ] Dependency order enforced and documented

---

## Phase 4: Create ObservabilityComposer (Week 2, Days 1-2)

### Implementation
- [ ] Create `observability_composer.py`
- [ ] Define `ObservabilityBundle` dataclass
  - [ ] `telemetry_service: TelemetryServiceProtocol`
  - [ ] `audit_service: GraphAuditService`
  - [ ] `incident_service`, `tsdb_service`, `maintenance_service`
- [ ] Implement `ObservabilityComposer` class
  - [ ] Add `__init__(observability_config, infrastructure_bundle, service_registry, bus_manager)`
  - [ ] Implement `async def compose() -> ObservabilityBundle`
  - [ ] Implement `async def _create_telemetry_service()`
  - [ ] Implement `async def _create_audit_service()`
  - [ ] Implement `async def _create_incident_service()`
  - [ ] Implement `async def _create_tsdb_service()`
  - [ ] Implement `async def _create_maintenance_service()`
  - [ ] Implement `async def _attach_registry_if_needed(service)`

### Extract from ServiceInitializer
- [ ] Copy GraphTelemetryService creation from lines 554-578
- [ ] Copy GraphAuditService creation from lines 871-918
- [ ] Copy IncidentManagementService creation from lines 920-929
- [ ] Copy TSDBConsolidationService creation from lines 624-658
- [ ] Copy DatabaseMaintenanceService creation from lines 661-673

### Testing
- [ ] Create `tests/logic/initialization/test_observability_composer.py`
- [ ] Test `compose()` creates all 5 services
- [ ] Test services receive correct dependencies from infrastructure bundle
- [ ] Test `_attach_registry_if_needed()` calls `attach_registry()` for protocol-compliant services
- [ ] Test each service creation method independently
- [ ] Test with different ObservabilityConfig variations

### Phase 4 Validation
- [ ] Returns `ObservabilityBundle` with all 5 services
- [ ] Uses `RegistryAwareServiceProtocol` for registry attachment
- [ ] Depends on `InfrastructureBundle` (enforces initialization order)
- [ ] All unit tests pass

---

## Phase 5: Create GovernanceComposer (Week 2, Days 3-4)

### Implementation
- [ ] Create `governance_composer.py`
- [ ] Define `GovernanceBundle` dataclass
  - [ ] `adaptive_filter`, `self_observation`, `visibility`, `consent`, `runtime_control`, `task_scheduler`
- [ ] Implement `GovernanceComposer` class
  - [ ] Add `__init__(governance_config, infrastructure_bundle, llm_service, service_registry, bus_manager)`
  - [ ] Implement `async def compose() -> GovernanceBundle`
  - [ ] Implement `async def _create_adaptive_filter()`
  - [ ] Implement `async def _create_task_scheduler()`
  - [ ] Implement `async def _create_self_observation()`
  - [ ] Implement `async def _create_visibility()`
  - [ ] Implement `async def _create_consent()`
  - [ ] Implement `async def _create_runtime_control()`

### Extract from ServiceInitializer
- [ ] Copy AdaptiveFilterService creation from lines 593-603
- [ ] Copy TaskSchedulerService creation from lines 615-622
- [ ] Copy SelfObservationService creation from lines 676-692
- [ ] Copy VisibilityService creation from lines 695-706
- [ ] Copy ConsentService creation from lines 709-720
- [ ] Copy RuntimeControlService creation from lines 723-735

### Testing
- [ ] Create `tests/logic/initialization/test_governance_composer.py`
- [ ] Test `compose()` creates all 6 services
- [ ] Test with LLM service provided
- [ ] Test with LLM service = None (mock mode)
- [ ] Test each service creation method independently
- [ ] Test services receive correct dependencies

### Phase 5 Validation
- [ ] Returns `GovernanceBundle` with all 6 services
- [ ] Handles optional LLM service gracefully
- [ ] All unit tests pass

---

## Phase 6: Create ServiceOrchestrator (Week 2, Day 5)

### Implementation
- [ ] Create `service_orchestrator.py`
- [ ] Define `InitializedServices` dataclass
  - [ ] `infrastructure: InfrastructureBundle`
  - [ ] `observability: ObservabilityBundle`
  - [ ] `governance: GovernanceBundle`
  - [ ] `llm_service: Optional[LLMServiceProtocol]`
  - [ ] `service_registry: ServiceRegistry`
  - [ ] `bus_manager: BusManager`
- [ ] Implement `ServiceOrchestrator` class
  - [ ] Add `__init__(config: InitializationConfig, essential_config: EssentialConfig)`
  - [ ] Add metrics tracking attributes
  - [ ] Implement `async def initialize_all() -> InitializedServices`
  - [ ] Implement `def _create_service_registry() -> ServiceRegistry`
  - [ ] Implement `def _create_bus_manager(...) -> BusManager`
  - [ ] Implement `async def _initialize_llm_services() -> Optional[LLMServiceProtocol]`
  - [ ] Implement `def _register_infrastructure_services(...)`
  - [ ] Implement `def _register_all_services(...)`
  - [ ] Implement `async def _migrate_config_to_graph(...)`
  - [ ] Implement `def get_metrics() -> Dict[str, float]`

### Testing
- [ ] Create `tests/logic/initialization/test_service_orchestrator.py`
- [ ] Test `initialize_all()` creates complete system
- [ ] Test initialization phases execute in correct order
- [ ] Test metrics collection (compatible with v1.4.3 format)
- [ ] Test service registry population
- [ ] Test BusManager wiring with telemetry/audit
- [ ] Test LLM initialization with primary only
- [ ] Test LLM initialization with primary + secondary
- [ ] Test LLM skipped when `skip_initialization=True`
- [ ] Test error propagation from failed phase

### Phase 6 Validation
- [ ] Orchestrator coordinates all composers
- [ ] Metrics format matches v1.4.3 exactly
- [ ] Service registry fully populated
- [ ] BusManager wired correctly with telemetry/audit
- [ ] All unit tests pass

---

## Phase 7: Update ServiceInitializer (Week 3, Days 1-2)

### Implementation
- [ ] Add feature flag support to ServiceInitializer
  - [ ] Add `_use_new_initialization` attribute (reads `CIRIS_USE_NEW_INIT` env var)
  - [ ] Add `_config_adapter: Optional[ConfigurationAdapter]` attribute
  - [ ] Add `_orchestrator: Optional[ServiceOrchestrator]` attribute
  - [ ] Add `_initialized_services: Optional[InitializedServices]` attribute
- [ ] Implement new initialization path
  - [ ] Implement `async def _initialize_infrastructure_new()`
  - [ ] Implement `def _check_for_mock_modules() -> bool`
  - [ ] Implement `def _wire_services_to_attributes()`
- [ ] Update `initialize_infrastructure_services()`
  - [ ] Add feature flag check
  - [ ] Route to `_initialize_infrastructure_new()` or existing code
- [ ] Preserve old initialization path
  - [ ] Rename existing methods to `_initialize_infrastructure_old()` etc.
  - [ ] Keep all existing logic intact
- [ ] Update other public methods
  - [ ] `initialize_memory_service()` - delegate if new path
  - [ ] `initialize_security_services()` - delegate if new path
  - [ ] `initialize_all_services()` - delegate if new path
  - [ ] `get_metrics()` - route to orchestrator or old code

### Testing
- [ ] Update `tests/ciris_engine/logic/runtime/test_service_initializer.py`
  - [ ] Test new path with `CIRIS_USE_NEW_INIT=true`
  - [ ] Test old path with `CIRIS_USE_NEW_INIT=false`
  - [ ] Test feature flag switching
  - [ ] Test compatibility wiring preserves attribute access
  - [ ] Verify all existing tests still pass
  - [ ] Add test for `_wire_services_to_attributes()`

### Phase 7 Validation
- [ ] Feature flag controls path selection
- [ ] New path creates orchestrator and delegates
- [ ] Compatibility wiring preserves all existing attributes
- [ ] All public methods work in both modes
- [ ] All existing tests pass without modification

---

## Phase 8: Parallel Execution Testing (Week 3, Days 3-4)

### Create Comparison Test Harness
- [ ] Create `tests/integration/test_initialization_comparison.py`
- [ ] Implement test that runs both paths
- [ ] Implement service comparison logic
- [ ] Implement metrics comparison logic
- [ ] Implement registry comparison logic

### Comparison Tests
- [ ] Test both paths create same service types
- [ ] Test both paths populate registry identically
- [ ] Test both paths produce compatible metrics
- [ ] Test both paths handle mock modules identically
- [ ] Test both paths handle missing LLM keys identically
- [ ] Test both paths create same number of services

### Regression Testing
- [ ] Run full test suite with old path
- [ ] Run full test suite with new path
- [ ] Compare test results
- [ ] Run QA runner with old path
- [ ] Run QA runner with new path
- [ ] Compare QA results

### Phase 8 Validation
- [ ] Both paths create identical services (by type)
- [ ] Both paths populate registry identically
- [ ] Both paths produce compatible metrics
- [ ] No test regressions with new path
- [ ] QA runner passes with both paths

---

## Phase 9: Gradual Cutover (Week 3, Day 5 + Week 4, Days 1-2) [Variable]

### Staging Deployment
- [ ] Deploy code to staging with `CIRIS_USE_NEW_INIT=false`
- [ ] Verify staging works with old path
- [ ] Enable feature flag: `CIRIS_USE_NEW_INIT=true`
- [ ] Monitor staging for 24 hours
  - [ ] Check error logs for initialization failures
  - [ ] Check metrics for startup time changes
  - [ ] Verify all services healthy
- [ ] Run full QA suite in staging
- [ ] Review QA results for regressions

### Production Deployment
- [ ] Deploy code to production with `CIRIS_USE_NEW_INIT=false`
- [ ] Verify production works with old path
- [ ] Enable feature flag in production: `CIRIS_USE_NEW_INIT=true`
- [ ] Monitor production for 48 hours
  - [ ] Check incident logs
  - [ ] Monitor `initializer_startup_time_ms` metric
  - [ ] Verify service health
  - [ ] Check for any user-reported issues

### Rollback Plan (if needed)
- [ ] Document rollback procedure:
  ```bash
  export CIRIS_USE_NEW_INIT=false
  systemctl restart ciris-agent
  ```
- [ ] Test rollback in staging
- [ ] Keep rollback ready during production cutover

### Phase 9 Validation
- [ ] Staging runs successfully for 24 hours with new path
- [ ] QA tests pass in staging
- [ ] Production runs successfully for 48 hours with new path
- [ ] No incidents related to initialization
- [ ] Metrics within expected range

---

## Phase 10: Cleanup and Documentation (Week 4, Days 3-5)

### Code Cleanup
- [ ] Remove old initialization methods from ServiceInitializer
  - [ ] Remove `_initialize_infrastructure_old()`
  - [ ] Remove `_initialize_memory_old()`
  - [ ] Remove `_initialize_security_old()`
  - [ ] Remove old LLM initialization logic
- [ ] Remove feature flag logic
  - [ ] Remove `_use_new_initialization` attribute
  - [ ] Remove env var check
  - [ ] Remove path routing logic
- [ ] Simplify ServiceInitializer
  - [ ] Make new path the only path
  - [ ] Remove compatibility wiring (no longer needed)
  - [ ] Update docstrings
- [ ] Remove deprecated methods
  - [ ] Mark `initialize_memory_service(config: Any)` as fully removed
  - [ ] Mark `initialize_security_services(config: Any, app_config: Any)` as fully removed

### Update CLAUDE.md
- [ ] Add section: "Service Initialization Architecture"
- [ ] Document config model usage pattern
- [ ] Add example: Creating typed config
- [ ] Add example: Using ConfigurationAdapter
- [ ] Add example: Using ServiceOrchestrator directly
- [ ] Document component responsibilities
- [ ] Update "Getting Started" with new initialization

### Update Architecture Documentation
- [ ] Create `docs/architecture/initialization.md`
  - [ ] Add initialization flow diagram
  - [ ] Document each component
  - [ ] Show dependency graph
  - [ ] Explain config loading process
- [ ] Update `docs/architecture/services.md`
  - [ ] Add config model reference
  - [ ] Show how to add new service types
- [ ] Update `FSD/` specifications if needed

### Example Code
- [ ] Create `examples/initialization_example.py`
  - [ ] Show standard initialization flow
  - [ ] Show custom service bundle creation
  - [ ] Show config model validation
- [ ] Create `examples/custom_service_initialization.py`
  - [ ] Show how to add new service type
  - [ ] Show how to extend composers

### Final Validation
- [ ] Run full test suite - all tests pass
- [ ] Run QA runner - all tests pass
- [ ] Check code coverage - no regressions
- [ ] Run mypy - no new errors
- [ ] Check SonarCloud quality gate - passing

### Phase 10 Validation
- [ ] No old initialization code remains
- [ ] Feature flag removed
- [ ] CLAUDE.md updated with initialization patterns
- [ ] Architecture docs updated
- [ ] Example code created
- [ ] All tests passing
- [ ] No `config: Any` anywhere in initialization code

---

## Overall Success Criteria

### Type Safety
- [ ] Zero `config: Any` parameters in entire initialization system
- [ ] All config models use Pydantic with strict validation
- [ ] All service bundles use protocol-typed fields
- [ ] Mypy passes on all initialization code

### Code Quality
- [ ] ServiceInitializer under 200 lines (delegating version)
- [ ] Each component under 250 lines
- [ ] All components have single clear responsibility
- [ ] No environment variable access outside ConfigurationAdapter/config models

### Testing
- [ ] 100% of initialization code covered by unit tests
- [ ] Integration tests validate full initialization flow
- [ ] Comparison tests validate old/new path equivalence
- [ ] QA runner passes with new initialization

### Production
- [ ] Zero incidents related to initialization in 48-hour monitoring
- [ ] Startup time within 10% of baseline
- [ ] All services healthy after cutover
- [ ] No user-reported issues

### Documentation
- [ ] CLAUDE.md includes initialization patterns and examples
- [ ] Architecture docs updated with flow diagrams
- [ ] Config models fully documented
- [ ] Component responsibilities clearly documented

---

**Next Action**: Begin Phase 1 - Create Config Models
