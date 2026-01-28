# Changelog

All notable changes to CIRIS Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.9.3] - 2026-01-27

### Added

- **TSASPDMA (Tool-Specific Action Selection PDMA)** - Documentation-aware tool validation
  - Activated when ASPDMA selects a TOOL action
  - Reviews full tool documentation before execution
  - Can return TOOL (proceed), SPEAK (ask clarification), or PONDER (reconsider)
  - Returns same `ActionSelectionDMAResult` as ASPDMA for transparent integration
  - Catches parameter ambiguities and gotchas that ASPDMA couldn't see

- **Native LLM Provider Support** - Direct SDK integration for major LLM providers
  - **Google Gemini**: Native `google-genai` SDK with instructor support
    - Models: `gemini-2.5-flash` (1M tokens/min), `gemini-2.0-flash` (higher quotas)
    - Automatic instructor mode: `GEMINI_TOOLS` for structured output
  - **Anthropic Claude**: Native `anthropic` SDK with instructor support
    - Models: `claude-sonnet-4-20250514`, `claude-opus-4-5-20251101`
    - Automatic instructor mode: `ANTHROPIC_TOOLS` for structured output
  - **Provider Auto-Detection**: Detects provider from API key environment variables
    - Checks `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`
    - Falls back to OpenAI-compatible mode if none found

- **New Environment Variables** - LLM configuration with CIRIS_ prefix priority
  - `CIRIS_LLM_PROVIDER`: Explicit provider selection (`openai`, `anthropic`, `google`)
  - `CIRIS_LLM_MODEL_NAME`: Model name override (takes precedence over `OPENAI_MODEL`)
  - `CIRIS_LLM_API_KEY`: API key override (takes precedence over provider-specific keys)
  - Fallback support for `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_MODEL`

- **Adapter Auto-Discovery Service** - Multi-path adapter scanning
  - Scans `ciris_adapters/`, `~/.ciris/adapters/`, `.ciris/adapters/`
  - `CIRIS_EXTRA_ADAPTERS` env var for additional paths (colon-separated)
  - First occurrence wins for duplicate adapter names
  - Integrated with eligibility filtering

- **Tool Eligibility Checker** - Runtime requirement validation
  - Validates binaries in PATH (`shutil.which`)
  - Validates environment variables are set
  - Validates platform compatibility
  - Validates config keys (when config service available)
  - `EligibilityResult` with detailed missing requirements and install hints

- **Clawdbot Skill Converter** - Tool to convert Clawdbot skills to CIRIS adapters
  - `python -m tools.clawdbot_skill_converter <skills_dir> <output_dir>`
  - Parses SKILL.md YAML frontmatter + markdown documentation
  - Generates manifest.json, service.py, adapter.py, README.md
  - Proper `ToolInfo.requirements` integration for eligibility checking
  - 49 Clawdbot skills converted to CIRIS adapters

- **Tool Summaries in ASPDMA Context** - Concise tool guidance for action selection
  - Injects `when_to_use` field into ASPDMA context
  - Falls back to truncated description if no `when_to_use`
  - Helps ASPDMA make informed tool selection without full documentation

### Fixed

- **Adapter Eligibility Checking** - Services now properly check requirements
  - `_check_requirements()` now uses `ToolInfo.requirements` instead of hardcoded empty lists
  - Adapters requiring missing binaries/env vars are no longer incorrectly loaded

- **Clawdbot Adapter Schema Compliance** - Fixed multiple manifest issues
  - Changed `sensitive: true` to `sensitivity: "HIGH"` in configuration
  - Removed invalid `source` field from module section
  - Added required `description` to confirm steps
  - Fixed protocol path to `ciris_engine.protocols.services.runtime.tool.ToolServiceProtocol`
  - Fixed binary requirement format (no longer double-quoted)

### Changed

- **ASPDMA/TSASPDMA Schema Refactoring** - Removed Union types for Gemini compatibility
  - Gemini's structured output doesn't support discriminated unions
  - `ASPDMALLMResult`: Flat schema with `selected_action` + optional parameter fields
  - `TSASPDMALLMResult`: Flat schema with `tool_parameters` as JSON dict
  - `convert_llm_result_to_action_result()`: Converts flat result to typed `ActionSelectionDMAResult`
  - All existing tests pass with new flat schema design

- **New Dependencies** - Added native LLM provider SDKs
  - `google-genai>=1.0.0,<2.0.0`: New Google GenAI SDK with instructor support
  - `jsonref>=1.0.0,<2.0.0`: Required by google-genai for schema resolution
  - `anthropic>=0.40.0,<1.0.0`: Already present, now actively used for native integration

## [1.9.2] - 2026-01-27

### Added

- **Enhanced ToolInfo Schema** - Rich skill-like documentation support for adapter tools
  - New `requirements` field: Runtime requirements (binaries, env vars, config keys)
  - New `install_steps` field: Installation instructions (brew/apt/pip/npm/manual)
  - New `documentation` field: Rich docs (quick_start, examples, gotchas, related_tools)
  - New `dma_guidance` field: DMA guidance (when_not_to_use, requires_approval, min_confidence)
  - New `tags` field: Categorization tags for tool discovery
  - New `version` field: Tool version string
  - All fields optional for full backward compatibility
  - See `ciris_adapters/README.md` for adapter developer documentation

- **New Supporting Schemas** for ToolInfo enhancement:
  - `BinaryRequirement`, `EnvVarRequirement`, `ConfigRequirement` - requirement types
  - `ToolRequirements` - combined runtime requirements
  - `InstallStep` - installation instruction with platform targeting
  - `UsageExample`, `ToolGotcha`, `ToolDocumentation` - rich documentation
  - `ToolDMAGuidance` - DMA decision-making guidance

- **Mobile Build Improvements** - Python sources synced from main repo at build time
  - New `syncPythonSources` Gradle task copies `ciris_engine/` and `ciris_adapters/`
  - Eliminates need to maintain separate android/ copy of Python sources
  - Mobile-specific files remain in `mobile/androidApp/src/main/python/`

- **Mobile Memory Graph** - Force-directed layout visualization for memory nodes
  - Interactive graph with zoom, pan, and node selection
  - Scope filtering (LOCAL, SOCIAL, IDENTITY, ENVIRONMENT)
  - Edge relationship visualization

- **Mobile Users Management** - New screen for managing WA users

### Fixed

- **SonarCloud Code Quality** - Resolved multiple code smells in `agent.py`
  - Reduced cognitive complexity in `_create_interaction_message`, `_derive_credit_account`, `get_identity`
  - Extracted helper functions for image/document processing, provider derivation, service categorization
  - Replaced `Union[]` with `|` syntax, `set([])` with `{}`
  - Removed unused variables

- **TaskOutcome Schema Compliance** - WA deferral resolution now uses proper `TaskOutcome` schema
  - Changed from `{"status": "resolved", "message": ...}` format
  - Now uses: `status`, `summary`, `actions_taken`, `memories_created`, `errors`

- **Memory Graph Scope Mixing** - Fixed cross-scope edge issues in mobile visualization
  - Made `GraphFilter.scope` non-nullable with `GraphScope.LOCAL` default
  - Removed "All" option from scope filter

- **WA Service Query** - Fixed query to use `outcome_json` column instead of non-existent `outcome`

- **Telemetry Test Mocks** - Marked incomplete mock setup tests as xfail

### Changed

- **SonarCloud Exclusions** - Added `mobile/**/*` to exclusions in `sonar-project.properties`

## [1.9.1] - 2026-01-25

### Fixed

- **MCP QA Tests False Positives** - Tests now properly verify tool execution success
  - Adapter loading tests verify tools are discovered (not just that adapter object exists)
  - Tool execution tests check `context.metadata.outcome == 'success'` in audit entries
  - Tests fail correctly when MCP SDK not installed or server connection fails
  - Pass rate: 100% (22/22 tests) when MCP SDK installed

- **MCP Test Audit Verification** - Fixed audit entry field mapping
  - Was checking non-existent `action_result.success` and `handler_result.success`
  - Now correctly checks `context.metadata.outcome` for success/failure

### Added

- **Trace Format v1.9.1 JSON Schema** - Machine-readable schema for CIRISLens
  - `ciris_adapters/ciris_covenant_metrics/schemas/trace_format_v1_9_1.json`
  - Full field documentation for all 6 H3ERE components
  - Includes level annotations (generic, detailed, full_traces)

## [1.9.0] - 2026-01-22

### Added

- **Covenant Metrics Live Testing** - Full integration with CIRISLens server (100% pass rate)
  - `--live-lens` flag for QA runner to test against real Lens server
  - Multi-level trace adapters (generic, detailed, full_traces) via API loading
  - PDMA field validation tests at detailed/full trace levels
  - Key ID consistency verification between registration and signing
  - Updated default endpoint to production URL

- **Comprehensive Adapter QA Testing** - All adapters now have QA test coverage
  - `ciris_covenant_metrics`: 100% - Full CIRISLens integration
  - `mcp_client/mcp_server`: 95.5% - Handle adapter reload
  - `external_data_sql`: 100% - Fixed config passing
  - `weather`: 100% - Free NOAA API
  - `navigation`: 100% - Free OpenStreetMap API
  - `ciris_hosted_tools`: 60% - Awaiting billing token
  - `reddit`, `home_assistant`: Need API credentials

- **Adapter Manifest Validation** - Comprehensive QA module for all adapters
  - Validates manifest.json structure for all modular adapters
  - Tests adapter loading, configuration, and lifecycle

- **Adapter Status Documentation** - Test status table in ciris_adapters/README.md

### Fixed

- **System Channel Admin-Only** - Non-admin users no longer see system/error messages
  - Rate limit errors from other sessions no longer appear for new users
  - System channel now restricted to ADMIN, SYSTEM_ADMIN, AUTHORITY roles

- **Trace Signature Format** - Signatures now match CIRISLens verification format
  - Was: signing SHA-256 hash of entire trace object
  - Now: signing JSON components array with `sort_keys=True`

- **CIRISLens Default URL** - Updated to production endpoint
  - Was: `https://lens.ciris.ai/v1`
  - Now: `https://lens.ciris-services-1.ai/lens-api/api/v1`

- **MCP Test Reliability** - Handle existing adapters by unloading before reload
  - Pass rate improved from 72.7% to 95.5%

- **SQL External Data Adapter** - Config now passed from adapter_config during load
  - Adapter builds SQLConnectorConfig from adapter_config parameters
  - Tests load adapter via API with proper configuration
  - Pass rate improved from 25% to 100%

- **Adapter Config API** - Added missing `load_persisted_configs()` and `remove_persisted_config()` methods
  - Added unit tests for both methods

- **OAuth Callback Test** - Handle HTML response instead of expecting JSON

- **State Transition Tests** - Updated test expectations for shutdown_evaluator and template_loading

## [1.8.13] - 2026-01-21

### Fixed

- **Adapter Persist Flag Not Extracted** - Adapters loaded via API with `persist=True` were not being persisted
  - Root cause: `_convert_to_adapter_config()` nested `persist` inside `adapter_config` dict
  - But `_save_adapter_config_to_graph()` checked top-level `AdapterConfig.persist` (default `False`)
  - Fix: Extract `persist` flag from config dict and set on `AdapterConfig` directly
  - Affects: Covenant metrics adapter and any adapter loaded via API with persistence

- **Rate Limit Retry Timeout Too Short** - Increased from 25s to 90s
  - Multi-agent deployments hitting Groq simultaneously exhaust rate limits
  - 25s wasn't enough time for Groq to recover between retries
  - Now allows up to 90s of rate limit retries before giving up

## [1.8.12] - 2026-01-20

### Fixed

- **Path Traversal Security Fix (SonarCloud S2083)** - Removed user-controlled path construction
  - `create_env_file()` and `_save_setup_config()` no longer accept `save_path` parameter
  - Functions now call `get_default_config_path()` internally (whitelist approach)
  - Path is constructed from known-safe bases, not user input
  - Eliminated potential path injection attack vector

- **Clear-text Storage Hardening (CodeQL)** - Added restrictive file permissions
  - `.env` files now created with `chmod 0o600` (owner read/write only)
  - Prevents other users on system from reading sensitive configuration

- **Dev Mode Config Path** - Changed from `./.env` to `./ciris/.env`
  - Development mode now uses `./ciris/.env` for consistency with production
  - Backwards compatibility: still checks `./.env` as fallback
  - `get_config_paths()` updated to check `./ciris/.env` first in dev mode

## [1.8.11] - 2026-01-20

### Fixed

- **LLM Failover Timeout Bug** - DMA was timing out before LLMBus could failover to secondary provider
  - Root cause: DMA timeout (30s) < LLM timeout (60s), so failover never had a chance to occur
  - DMA timeout increased from 30s to 90s (configurable via `CIRIS_DMA_TIMEOUT` env var)
  - LLM Bus retries per service reduced from 3 to 1 for fast failover between providers
  - LLM service timeout reduced from 60s to 20s (configurable via `CIRIS_LLM_TIMEOUT` env var)
  - LLM max_retries reduced from 3 to 2 to fit within DMA timeout budget
  - New timeout budget: 90s DMA > (20s LLM × 2 retries × 2 providers = 80s)
  - Fixes: Echo Core deferrals when Together AI was down but Groq was available

- **Unified Adapter Persistence Model** - Single consistent pattern for adapter auto-restore
  - Unified to single pattern: `adapter.{adapter_id}.*` with explicit `persist=True` flag
  - Removed deprecated `adapter.startup.*` pattern and related methods
  - Adapters with `persist=True` in config are auto-restored on startup
  - Added adapter config de-duplication (same type, occurrence_id, and config hash)
  - Database maintenance cleans up non-persistent adapter configs on startup
  - Fixed occurrence_id mismatch issue (configs saved with wrong occurrence_id)
  - Removed redundant `auto_start` field in favor of `persist`
  - CIRISRuntime initialization step now handles all adapter restoration

## [1.8.10] - 2026-01-20

### Fixed

- **Adapter Auto-Restore: Fix adapter_manager Resolution** - The loader was looking in the wrong place
  - `load_saved_adapters_from_graph()` was calling `_get_runtime_service(runtime, "adapter_manager")`
  - But `ServiceInitializer` doesn't have `adapter_manager` - it's on `RuntimeControlService`
  - Now correctly gets adapter_manager via `runtime_control_service.adapter_manager`
  - This was the final missing piece - 1.8.9 registered the step but it always returned early

## [1.8.9] - 2026-01-19

### Fixed

- **Adapter Auto-Restore on Restart (Step Registration)** - The fix was missing from 1.8.7 and 1.8.8
  - Added missing "Load Saved Adapters" initialization step registration in `CIRISRuntime`
  - Root cause: fix commit was pushed to release/1.8.7 AFTER PR was merged
  - Cherry-picked commit `8d54e51e` which contains the actual code change

## [1.8.8] - 2026-01-19

### Fixed

- **Adapter Auto-Restore on Restart (Incomplete)** - Changelog-only release, code fix was missing
  - This release only updated changelog and version, not the actual code

## [1.8.7] - 2026-01-19

### Fixed

- **Adapter Auto-Restore on Restart** - Initial implementation (superseded by 1.8.11)
  - Database maintenance cleanup no longer deletes persisted adapter configs
  - Added "Load Saved Adapters" initialization step to `CIRISRuntime`
  - Note: The `adapter.startup.*` pattern from this version was deprecated in 1.8.11
  - See 1.8.11 for the unified persistence model using `adapter.{adapter_id}.persist=True`

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
