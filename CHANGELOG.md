# Changelog

All notable changes to CIRIS Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.8.8] - 2026-01-19

### Fixed

- **Adapter Auto-Restore on Restart (Complete Fix)** - Adapters now properly restore after restart
  - Added missing "Load Saved Adapters" initialization step registration in `CIRISRuntime`
  - Root cause: step was defined in `initialization_steps.py` but never registered in `_register_initialization_steps()`
  - This is the actual fix; 1.8.7 only preserved configs but never loaded them

## [1.8.7] - 2026-01-19

### Fixed

- **Adapter Auto-Restore on Restart** - Persisted adapter configs now survive restarts and auto-load
  - Database maintenance cleanup no longer deletes persisted adapter configs
  - Preserves `adapter.startup.*` configs (explicit `persist=True` from API)
  - Preserves `adapter.{id}.*` configs created by `runtime_adapter_manager` (dynamic loads)
  - **Critical fix**: Added missing "Load Saved Adapters" initialization step to `CIRISRuntime`
  - Root cause 1: cleanup was deleting all `adapter.*` configs regardless of persistence intent
  - Root cause 2: `_register_initialization_steps` in ciris_runtime.py was missing the restore step

### Changed

- **Database Maintenance Cleanup Logic** - More selective config cleanup
  - Added protection for adapter configs marked for auto-restore
  - Updated README with accurate preservation rules
  - Refactored `_cleanup_runtime_config` to reduce cognitive complexity (23 → ~10)
  - Extracted helper methods: `_should_preserve_config`, `_is_runtime_config`, `_delete_ephemeral_configs`
  - Added 12 unit tests for config preservation logic

## [1.8.6] - 2026-01-19

### Added

- **Unified Ed25519 Signing Key** - Single signing key shared between audit and covenant metrics
  - New `signing_protocol.py` with algorithm-agnostic signing protocol
  - `UnifiedSigningKey` singleton at `data/agent_signing.key` (32 bytes Ed25519)
  - Key ID format: `agent-{sha256(pubkey)[:12]}`
  - PQC-ready design with migration path to ML-DSA/SLH-DSA

- **RSA to Ed25519 Migration Utility** - Migrate existing audit chains
  - `AuditKeyMigration` class for atomic chain migration with rollback
  - Re-signs entire audit chain preserving original timestamps
  - `database_maintenance.migrate_audit_key_to_ed25519()` method for admin access
  - RSA-2048 verification maintained for backward compatibility

- **CIRISLens Public Key Registration** - Automatic key registration on startup
  - Covenant metrics adapter registers public key before sending connect event
  - Enables CIRISLens to verify trace signatures

### Changed

- **AuditSignatureManager now uses Ed25519** - No longer generates RSA-2048 keys
  - New installations automatically use unified Ed25519 key
  - Legacy RSA verification maintained for existing audit chains
  - Key rotation deprecated in favor of unified key management

### Fixed

- **Covenant Metrics agent_id_hash** - Traces now include proper agent ID hash instead of "unknown"
  - Service now receives agent_id from persistence during adapter loading
  - Agent identity retrieved from graph when initializing modular adapters
  - Preserved legacy `runtime.agent_id` fallback for mocks and lightweight runtimes
  - Fixes lens team reported issue with traces showing `agent_id_hash: "unknown"`

- **Covenant Metrics cognitive_state** - Traces now include cognitive state in SNAPSHOT_AND_CONTEXT
  - Added `cognitive_state` field to SystemSnapshot schema
  - Populated from `agent_processor.get_current_state()` during context building
  - Fixes lens team reported issue with `cognitive_state: null` in traces

## [1.8.5] - 2026-01-18

### Added

- **Multi-Occurrence Adapter Support** - Adapters now track which occurrence loaded them
  - `occurrence_id` saved with adapter config in graph
  - On startup, only loads adapters matching current occurrence
  - Prevents duplicate adapter loading in multi-occurrence deployments

- **Covenant Metrics Connectivity Events** - Adapter notifies CIRISLens on startup/shutdown
  - Sends `startup` event to `/covenant/connected` when service starts
  - Sends `shutdown` event before HTTP session closes
  - Includes agent hash, trace level, version, and correlation metadata
  - Enables monitoring agent connectivity without waiting for interactions

### Fixed

- **services_registered API Response** - Adapter status now shows registered services
  - Added `services_registered` field to `AdapterInfo` schema
  - API endpoints now return actual registered services instead of empty array
  - Fixes visibility into which services each adapter provides

### Changed

- **Adapter Loading Behavior** - Adapters without occurrence_id treated as "default" occurrence
  - Legacy adapters seamlessly work with single-occurrence deployments
  - Multi-occurrence deployments require explicit occurrence matching

## [1.8.4] - 2026-01-18

### Fixed

- **P1 Security: Adapter Config Sanitization** - Fixed `_sanitize_config_params` dropping `adapter_config` field
  - Both `settings` and `adapter_config` fields now properly sanitized before exposing to observers
  - Sensitive fields masked with `***MASKED***` pattern

- **Adapter Config Persistence** - Config passed during adapter load now returned in `get_adapter_info` API
  - Added `config_params` field to `AdapterInfo` schema
  - Config properly propagated through RuntimeControlService to API endpoints

- **Scout Template Validation** - Fixed schema compliance in scout.yaml
  - Converted nested lists to semicolon-delimited strings for `high_stakes_architecture` fields

### Changed

- **Reduced Cognitive Complexity** - Refactored `_sanitize_config_params` from complexity 20 to ~8
  - Extracted module-level constants: `SENSITIVE_FIELDS_BY_ADAPTER_TYPE`, `DEFAULT_SENSITIVE_PATTERNS`, `MASKED_VALUE`
  - Extracted helper functions: `_should_mask_field()`, `_sanitize_dict()`
  - Added 21 unit tests for extracted functions

## [1.8.3] - 2026-01-17

### Added

- **QA Test Modules** - New comprehensive API test modules
  - `adapter_autoload_tests.py` - Tests adapter persistence and auto-load functionality
  - `identity_update_tests.py` - Tests identity refresh from template

- **Adapter Auto-Load** - Saved adapters now auto-load from graph on startup
  - Adapter configs persisted to graph during load
  - Configs retrieved and adapters reloaded on runtime initialization

### Fixed

- **ConfigNode Value Extraction (P1)** - Fixed adapter loading from persisted configs
  - `ConfigNode` values now properly extracted before passing to adapter loader
  - Prevents validation errors when loading adapters from graph storage

- **Type Annotations** - Added proper type annotations for mypy strict mode compliance

## [1.8.2] - 2026-01-17

### Added

- **Identity Update from Template** - Admin operation to refresh identity from template updates
  - New `--identity-update` CLI flag (requires `--template`)
  - Uses `update_agent_identity()` for proper version tracking and signing
  - Preserves creation metadata while updating template fields

### Changed

- **Code Modularization** - Refactored largest files for maintainability
  - `system.py` (3049 lines) → 10 focused modules in `system/` package
  - `telemetry_service.py` (2429→1120 lines) → extracted `aggregator.py`, `storage.py`
  - `TelemetryAggregator` (1221→457 lines) → 5 focused modules
  - `ciris_runtime.py` (2342→1401 lines) → 7 helper modules
  - Backward compatibility maintained via `__init__.py` re-exports

- **Reduced Cognitive Complexity** - SonarCloud fixes in system routes and LLM bus

### Fixed

- **Billing Provider** - Explicit `api_key` now takes precedence over env-sourced `google_id_token`

- **MCP Tool Execution** - Fixed Mock LLM handling of MCP tool calls

- **Adapter Status Reporting** - Fixed `AdapterStatus` enum comparison issues

- **Security** - Removed debug logging that could leak sensitive adapter configs

## [1.8.1] - 2026-01-15

### Added

- **Covenant Metrics Trace Detail Levels** - Three privacy levels for trace capture
  - `generic` (default): Numeric scores only - powers [ciris.ai/ciris-scoring](https://ciris.ai/ciris-scoring)
  - `detailed`: Adds actionable lists (sources_identified, stakeholders, flags)
  - `full_traces`: Complete reasoning text for Coherence Ratchet corpus
  - Configurable via `CIRIS_COVENANT_METRICS_TRACE_LEVEL` env var or `trace_level` config

### Fixed

- **Multi-Occurrence Task Lookup** - Fixed `__shared__` task visibility across occurrences
  - `gather_context.py` now uses `get_task_by_id_any_occurrence()` to fetch parent tasks
  - Thoughts can now find their parent tasks regardless of occurrence_id (including `__shared__` tasks)
  - Fixes "Could not fetch task" errors in multi-occurrence scout deployments
  - Exported `get_task_by_id_any_occurrence` from persistence module for consistency

- **Covenant Stego Logging** - Reduced noise from stego scanning normal messages
  - Zero-match results now log at DEBUG level (expected for non-stego messages)
  - Only partial matches (>0 but <expected) log at WARNING (possible corruption)
  - Fixes log spam from defensive scanning of user input

- **Covenant Metrics IDMA Field Extraction** - Fixed incorrect field names in trace capture
  - Changed `source_assessments` to `sources_identified` (matching IDMAResult schema)
  - Added missing `correlation_risk` and `correlation_factors` fields
  - Ensures complete IDMA/CCA data is captured for Coherence Ratchet corpus

## [1.8.0] - 2026-01-02

### Added

- **IDMA (Intuition Decision Making Algorithm)** - Semantic implementation of Coherence Collapse Analysis (CCA)
  - Applies k_eff formula: `k_eff = k / (1 + ρ(k-1))` to evaluate source independence
  - Phase classification: chaos (contradictory) / healthy (diverse) / rigidity (echo chamber)
  - Fragility detection when k_eff < 2 OR phase = "rigidity"
  - Integrated as 4th DMA in pipeline, runs after PDMA/CSDMA/DSDMA
  - Results passed to ASPDMA for action selection context
  - Non-fatal: pipeline continues with warning if IDMA fails

- **Covenant v1.2-Beta** - Added Book IX: The Mathematics of Coherence
  - The Coherence Ratchet mathematical framework for agents
  - CCA principles for detecting correlation-driven failure modes
  - Rationale document explaining why agents have access to this knowledge
  - Updated constants to reference new covenant file

- **Coherence Ratchet Trace Capture** - Full 6-component reasoning trace for corpus building
  - Captures: situation_analysis, ethical_pdma, csdma, action_selection, conscience_check, guardrails
  - Cryptographic signing of complete traces for immutability
  - Mock logshipper endpoint for testing trace collection
  - Transparency API endpoints for trace retrieval (`/v1/transparency/traces/latest`)

- **OpenRouter Provider Routing** - Select/ignore specific LLM backends
  - Environment variables: `OPENROUTER_PROVIDER_ORDER`, `OPENROUTER_IGNORE_PROVIDERS`
  - Provider config passed via `extra_body` to Instructor
  - Success logging: `[OPENROUTER] SUCCESS - Provider: {name}`

- **System/Error Message Visibility** - Messages visible to all users via system channel
  - System and error messages emitted to agent history
  - `is_agent=True` on system/error messages prevents agent self-observation
  - System channel included in all user channel queries

### Changed

- **LLM Bus Retry Logic** - 3 retries per service before failover
  - Configurable retry count with exponential backoff
  - Log deduplication for repeated failures (WARNING instead of ERROR)
  - Circuit breaker integration with retry exhaustion

- **Changelog Rotation** - Archived 2025 changelog
  - `CHANGELOG-2025.md` contains v1.1.1 through v1.7.9
  - Fresh `CHANGELOG.md` for 2026

### Fixed

- **ServiceRegistry Lookup for Modular Adapters** - Transparency routes now query ServiceRegistry
  - Modular adapters register with ServiceRegistry, not runtime.adapters
  - Fixed trace API returning 404/500 for covenant_metrics traces

- **Streaming Verification Test** - Added `action_parameters` to expected fields
  - ActionResultEvent schema includes action_parameters but test validation was missing it
  - QA runner streaming tests now pass with full schema validation

## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

---

## Previous Years

- [2025 Changelog](./CHANGELOG-2025.md) - v1.1.1 through v1.7.9
