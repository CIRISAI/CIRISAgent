# Changelog

All notable changes to CIRIS Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.5] - 2025-10-15

### Added
- **💳 OAuth Billing Integration**: Automatic billing user creation on OAuth login
  - Added `_trigger_billing_credit_check_if_enabled()` helper function in auth.py
  - Triggers billing credit check after successful OAuth login (non-blocking)
  - Ensures billing users are created immediately so frontend can display available credits
  - Works with both `SimpleCreditProvider` (free credits) and `CIRISBillingProvider` (paid credits)
  - OAuth login succeeds even if billing backend is unavailable (fail-safe design)
  - Passes user email and marketing_opt_in to billing context for user creation
- **🌐 Environment-Driven OAuth Redirect Configuration**: Flexible OAuth redirect URL management
  - Added `OAUTH_FRONTEND_URL` environment variable for separate frontend/backend domains
  - Added `OAUTH_FRONTEND_PATH` environment variable (default: `/oauth-complete.html`)
  - Added `OAUTH_REDIRECT_PARAMS` environment variable for configurable parameter list
  - Supports Scout architecture: `scout.ciris.ai` frontend + `scoutapi.ciris.ai` backend
  - Maintains backward compatibility with relative path redirects
  - Extracts marketing_opt_in from redirect_uri query parameters
  - Created comprehensive documentation: `docs/OAUTH_REDIRECT_CONFIGURATION.md`

### Fixed
- **🔗 OAuth Redirect Query Parameter Preservation**: Fixed redirect_uri stripping existing query params
  - **Root Cause**: `_build_redirect_response` was using `.split("?")[0]` to strip all query params from redirect_uri
  - **Impact**: Frontend routing parameters like `?next=/dashboard` or `?return_to=/profile` were being lost
  - **Solution**: Parse existing query params with urllib.parse, merge with server params (server params override on conflict)
  - **Security**: Server-generated params (access_token, role, etc.) take precedence if there's a naming conflict
  - **Testing**: Added comprehensive test validating preservation of multiple frontend params alongside server params
  - Located at `auth.py:752-763`
- **🐛 OAuth Callback Tests**: Fixed 3 failing tests not updated for new `request` parameter
  - Updated `test_oauth_callback_with_redirect_uri_in_state` to pass mock request
  - Updated `test_oauth_callback_without_redirect_uri_in_state` to pass mock request
  - Updated `test_oauth_callback_malformed_state` to pass mock request
- **🔧 Billing Metadata Type**: Fixed boolean to string conversion for CreditContext
  - CreditContext.metadata requires `Dict[str, str]`
  - Updated billing integration to convert `marketing_opt_in` boolean to string

### Testing
- **✅ Comprehensive Test Coverage**: 100% coverage of new features
  - Added 7 new tests in `test_auth_routes_coverage.py::TestBillingIntegration`:
    - `test_trigger_billing_credit_check_enabled_success` - Successful billing check
    - `test_trigger_billing_credit_check_no_resource_monitor` - Graceful no-op when billing disabled
    - `test_trigger_billing_credit_check_no_credit_provider` - Backward compatibility
    - `test_trigger_billing_credit_check_failure_non_blocking` - Non-blocking failure behavior
    - `test_trigger_billing_credit_check_simple_provider` - SimpleCreditProvider compatibility
    - `test_trigger_billing_credit_check_no_email` - Edge case handling
    - `test_oauth_callback_with_billing_integration` - End-to-end integration test
  - Added 1 new test in `test_auth_routes_coverage.py::TestOAuthRedirectURI`:
    - `test_oauth_callback_preserves_redirect_uri_query_params` - Validates query param merging
  - All 10 OAuth redirect tests passing (9 existing + 1 new)
  - All 7 billing integration tests passing
  - Full test suite: 5186 passed, 117 skipped

## [1.3.4] - 2025-10-14

### Fixed
- **🎯 Type Safety Migration**: Migrated test mocks from dicts to Pydantic models
  - Updated `test_control_service_bugs.py` to use `SingleStepResult` models instead of dict mocks
  - Updated `test_pipeline_stepping.py` fixture to return `SingleStepResult` with proper field mappings
  - Updated `test_control_service_coverage.py` to use `SingleStepResult` with serialized fields
  - Fixed control service to map `SingleStepResult.message` to error when `success=False`
  - Fixed control service to use internal `thoughts_processed` counter instead of non-existent field
  - Converted `step_results` and `pipeline_state` to dicts using `.model_dump()` for `SerializedModel` compatibility
  - All 60 tests now passing (100% success rate)
- **🔗 OAuth Callback URL Construction**: Fixed malformed query parameter URLs
  - Issue: Backend was blindly appending `?access_token=...` even when `redirect_uri` already contained `?`
  - Result: Invalid URLs like `callback?marketing_opt_in=false?access_token=xxx`
  - Fix: Added separator detection to use `&` when `redirect_uri` already has query parameters
  - Now generates valid URLs like `callback?marketing_opt_in=false&access_token=xxx`
  - Located at `auth.py:703-705`
- **🔧 Mypy Type Errors**: Resolved 3 type errors causing CI failures
  - `context_utils.py:97` - Added `isinstance(channel_id, str)` check before passing to `create_channel_context()`
  - `recall_handler.py:126` - Added `JSONDict` type annotation for attributes dict
  - `recall_handler.py:167` - Added `JSONDict` type annotation for connected_attrs dict
  - All mypy checks now pass (556 files checked, 0 errors)

### Changed
- **🎯 Control Service Response Mapping**: Enhanced SingleStepResult to ProcessorControlResponse conversion
  - Maps `result.message` to error field when operation fails
  - Uses internal metrics counter for `thoughts_processed` tracking
  - Maintains backward compatibility with existing response structure

### Testing
- **✅ Unit Tests**: 60/60 tests passing in control service test suite
- **✅ QA Tests**: 127/128 tests passing (99.2% success rate)
- **✅ Mypy**: 556 source files, 0 errors (100% type safety)

## [1.3.3] - 2025-10-14

### Fixed
- **🧪 Test Failures**: Fixed 7 test failures from type-safety improvements
  - Updated `ProcessingRoundResult` and `SingleStepResult` import paths
  - Fixed field name from `thoughts_processed` to `thoughts_advanced`
  - Added required `message` field to `SingleStepResult` instantiations

### Added
- **🔐 OAuth Cross-Domain Support**: Enhanced OAuth flow for separate frontend/API domains
  - Added `redirect_uri` parameter support in oauth_login endpoint
  - State parameter now encodes redirect_uri for proper cross-domain redirects
  - Maintains backward compatibility with relative path redirects
  - 8 comprehensive tests for OAuth redirect_uri functionality
- **📊 Multi-Occurrence Architecture**: Infrastructure for multiple API instances
  - Added `occurrence_id` database migration (004_add_occurrence_id.sql)
  - Created telemetry architecture documentation
  - Added multi-occurrence isolation tests

### Changed
- **🎯 Type Safety**: Strongly typed telemetry for services
  - Replaced untyped dicts with concrete Pydantic schemas
  - Enhanced service telemetry data structures with proper typing

### Testing
- **✅ QA Test Suite**: Complete test coverage across 20 modules
  - Updated ALL module to run comprehensive test suite (128 tests)
  - Added multi-occurrence tests and documentation
  - 100% compatibility with new type-safe schemas

## [1.3.2] - 2025-10-10

### Fixed
- **🔒 CRITICAL SECURITY: JWT Rate Limiter Signature Verification**: Fixed JWT tokens being accepted without signature verification in rate limiter
  - **Vulnerability**: Rate limiter was decoding JWT tokens without verifying signatures, allowing attackers to forge tokens with arbitrary user IDs to bypass rate limiting
  - **Root Cause**: `_extract_user_id_from_jwt()` used `jwt.decode(token, options={"verify_signature": False})` at line 160 of rate_limiter.py
  - **Solution**: Implemented proper JWT signature verification with gateway_secret before trusting token contents
  - **Implementation**: Lazy-load gateway_secret from authentication service via request.app.state, fallback to IP-based rate limiting if verification fails
  - **Impact**: All JWT tokens must now have valid signatures before being used for per-user rate limiting, preventing rate limit bypass attacks
  - **Security Level**: HIGH - CWE privacy vulnerability - JWT signature verification is mandatory for security
- **📊 LLM Call Tracking for Conscience Checks**: Fixed conscience LLM calls not being tracked in telemetry metrics
  - **Root Cause**: All 4 conscience LLM calls (entropy, coherence, optimization_veto, epistemic_humility) were not passing `thought_id` parameter to `call_llm_structured()`
  - **Solution**: Updated all 4 conscience checks in `core.py` to pass `thought_id=context.thought.thought_id` parameter
  - **Impact**: SPEAK thoughts now correctly show 8 LLM calls (4 DMA + 4 conscience) in ACTION_RESULT events, TASK_COMPLETE thoughts correctly show 4 calls (4 DMA, conscience exempt)
  - **Verification**: Telemetry metrics now properly track all LLM calls by `thought_id` tag for accurate resource accounting
- **🔌 Together AI Provider Compatibility**: Fixed API errors with Together AI rejecting null values in messages
  - **Root Cause**: Together AI and some other providers reject messages containing null/None values for optional fields (e.g., `name: None`)
  - **Solution**: Added `exclude_none=True` to `model_dump()` for LLMMessage objects and strip None values from dict messages in `llm_bus.py:153-159`
  - **Impact**: LLM calls now work correctly with Together AI provider without 400 errors
  - **Scope**: Applied to both LLMMessage objects and dict messages for consistency across all providers

## [1.3.1] - 2025-10-09

### Fixed
- **🔄 Circuit Breaker Recovery**: Fixed critical bug preventing circuit breaker recovery
  - **Root Cause**: `record_failure()` was resetting `last_failure_time` even when circuit breaker was OPEN, preventing 60s recovery timer from elapsing
  - **Solution**: Only update `failure_count` and `last_failure_time` when NOT OPEN, allowing recovery timer to work correctly
  - **Impact**: Circuit breakers now properly transition to HALF_OPEN after 60 seconds, ending infinite retry loops (Echo-Nemesis fix)
- **⏱️ LLM Timeout Configuration**: Reduced timeout from 30s to 5s to enable faster failover
  - Configured in OpenAI SDK at provider level (service.py:36, service.py:78)
  - Allows 25 seconds for failover before DMA timeout (30s)
  - Circuit breaker timeout duration also reduced to 5.0s for consistency
  - Recovery timeout standardized to 60.0s across all circuit breakers
- **📝 Enhanced LLM Error Logging**: Added detailed context for debugging LLM failures
  - Schema validation errors: Shows expected schema, validation details, first 500 chars
  - Timeout errors: Reports timeout duration and context
  - Service errors (503): Detailed provider and model information
  - Rate limit errors (429): Enhanced diagnostic context
  - Content filter blocks: Guardrail detection and reporting
  - All errors include: model, provider, CB state, consecutive failures
- **🧠 PDMA Ethical Prompt Fix**: Corrected prompt causing schema validation errors
  - Fixed incorrect principle count (4 → 6 principles)
  - Changed `alignment_check` from structured dict to single paragraph string
  - Added warning about context red herrings and non sequiturs
  - Eliminated schema validation failures that appeared as "provider issues"
- **🔐 Audit Signature Persistence**: Fixed audit entries stored in graph without signatures
  - **Root Cause**: Signatures generated AFTER storing node in graph, never updated
  - **Solution**: Generate hash chain data FIRST, then create node with signature already set
  - Fixed in `log_event()` and `log_action()` - reordered operations
  - Updated `_store_entry_in_graph()` to accept and use hash_chain_data parameter
  - All audit entries now have populated `signature` and `hash_chain` fields in graph_nodes
- **🔒 OBSERVER Role Privacy**: Added task information redaction in SSE streaming
  - OBSERVER users now have `recently_completed_tasks_summary` and `top_pending_tasks_summary` redacted from SNAPSHOT_AND_CONTEXT events
  - Redaction applied after channel filtering but before streaming events
  - Uses deep copy to avoid mutating original events
  - ADMIN+ users bypass redaction (see all events unchanged)
  - 7 comprehensive tests cover all edge cases
- **📊 Unified Batch Context Consolidation**: Complete refactoring of system snapshot building (27d5fa28)
  - Consolidated 6 separate code paths into single `BatchContextData` architecture
  - Eliminated redundant database queries and memory service calls
  - Fixed 17 test failures through unified context building
  - All components now use `build_batch_context()` for consistent snapshot data
- **🎯 Code Quality (SonarCloud)**: Resolved 4 critical code quality issues (21fbf325)
  - Removed unnecessary f-string in system_snapshot_helpers.py:938
  - Merged nested if statement in batch_context.py:355
  - Reduced cognitive complexity in gather_context.py (16→15)
  - Reduced cognitive complexity in system_extensions.py (27→4 via 4 helper functions)
- **🔑 DSDMA Identity Mapping**: Fixed agent stuck in WAKEUP state (210507b8)
  - **Root Cause**: Batch context preserved all identity attributes with `dict(attrs)` but lost critical `role_description` → `role` mapping
  - **Solution**: Added explicit field mapping after attribute copy to ensure DSDMA gets required `role` field
  - Fixed: "CRITICAL: role is missing from identity in DSDMA domain 'Datum'!"
- **👥 User Profile Enrichment**: Fixed empty user_profiles in SSE streaming events (12dc43b3)
  - **Root Cause**: JSON serialization failed on datetime objects in connected node attributes during user enrichment
  - **Solution**: Added datetime handler to collect_memorized_attributes for proper serialization
  - Fixed: "Object of type datetime is not JSON serializable" error
  - User profiles now populate correctly in all system snapshots and SSE events

### Added
- **Billing & API Keys**: Production billing system integration (billing.ciris.ai)
  - CIRISBillingProvider with API key auth, oauth: prefix handling, idempotency
  - API endpoints: `/api/billing/credits`, `/api/billing/purchase/*`
  - User API key management: create/list/revoke with 30min-7day expiry
  - SimpleCreditProvider: Configurable free uses per OAuth user (default: 0, env: `CIRIS_SIMPLE_FREE_USES`)
- **Resource Tracking**: Per-thought metrics in H3ERE events (tokens, cost, carbon, energy)
- **API Documentation**: Complete specification in `docs/API_SPEC.md`
- **Marketing Opt-in**: GDPR-compliant consent capture in OAuth flow

### Testing
- **✅ QA Test Suite**: 128/128 tests passing (100% success rate)
  - Streaming: 2/2 (100%) - User profiles now populate correctly in SSE events
  - Guidance, Handlers, Filters: 43/43 (100%)
  - All other modules: 83/83 (100%)
- **✅ Unit Tests**: 5,100+ tests passing with zero failures
- **✅ Mypy**: 555 source files, 0 errors (100% type safety)
- **⏳ SonarCloud**: CI in progress (4 issues resolved, awaiting new analysis)

## [1.3.0] - 2025-10-07

### Added
- **🔴 Circuit Breaker State in Telemetry**: Complete circuit breaker tracking across all buses
  - Added `circuit_breaker` field to `TelemetrySummary` schema (`Dict[str, Any]`)
  - New `collect_circuit_breaker_state()` helper walks all buses via `runtime.bus_manager`
  - Collects state from LLM, Memory, Communication, Tool, Wise, and RuntimeControl buses
  - Returns dict mapping service names to `{state, failures, requests, failure_rate, etc}`
  - Visible in SSE `snapshot_and_context` events and telemetry endpoints
  - Empty dict when no circuit breakers triggered (normal operation)
  - Populated with detailed data when failures occur in production
- **✅ QA Circuit Breaker Validation**: Enhanced streaming verification module
  - Added validation to ensure `telemetry_summary.circuit_breaker` exists and is not null
  - Prints circuit_breaker data prominently in verbose test output
  - Test fails if field is missing or null (catches schema regressions)

### Fixed
- **🔄 LLM Failover**: Secondary LLM services now properly used when primary fails
  - **Root Cause**: `_get_prioritized_services()` was filtering out services with open circuit breakers before failover logic could execute
  - **Solution**: Removed health check from service filtering - circuit breaker check now happens during service selection
  - Services with open circuit breakers are skipped in favor of lower-priority services
  - Removed unused `_is_service_healthy()` method
  - **Impact**: Secondary LLM automatically used when primary circuit breaker opens
  - Expected failure rate drop from 48% to <5% during single-provider outages in production
  - Updated `test_circuit_breaker_skips_to_lower_priority` to verify new behavior
- **📋 Domain Routing Tests**: Updated 2 tests to match new LLM failover behavior
  - `test_domain_filtering_with_unhealthy_services` - Now tests failover when service calls fail (not just health check)
  - `test_service_health_check_failure` → `test_service_failure_propagates` - Renamed and updated to test actual call failures
  - Both tests verify correct failover behavior where services are tried in priority order
- **🐛 Code Quality**: Fixed OpenAI timeout configuration and telemetry provider disambiguation
  - OpenAI client timeout was silently ignoring user settings (used `getattr()` instead of direct attribute access)
  - Telemetry aggregator couldn't disambiguate multiple instances of same provider class
  - Both issues fixed with tests to prevent regression
- **🛡️ Conscience Exempt Actions**: Added RECALL and OBSERVE to exempt actions list
  - **Before**: Only 3 actions exempt (TASK_COMPLETE, DEFER, REJECT)
  - **After**: 5 actions exempt (RECALL, TASK_COMPLETE, OBSERVE, DEFER, REJECT)
  - Conscience now runs for exactly 5 actions: SPEAK, TOOL, PONDER, MEMORIZE, FORGET
  - Rationale: RECALL/OBSERVE are passive operations with no ethical implications

### Changed
- **🎯 Type Safety: Dict[str, Any] Elimination** - Replaced ~22 untyped dict usages with concrete Pydantic schemas
  - **shutdown_processor.py**: All return values now use `ShutdownResult` schema
    - Extended `ShutdownResult` with `status`, `action`, `message`, `reason`, `task_status`, `thoughts` fields
    - Eliminated 10+ Dict[str, Any] return statements in `_process_shutdown()` and `_check_failure_reason()`
  - **conscience/core.py**: All conscience checks now fully typed
    - Created `ConscienceCheckContext` schema to replace Dict[str, Any] context parameter
    - Updated all 4 conscience types: Entropy, Coherence, OptimizationVeto, EpistemicHumility
    - Message creation methods now return `List[LLMMessage]` instead of `List[Dict[str, str]]`
  - **ProcessorServices**: Extended with `time_service`, `resource_monitor`, `communication_bus` fields
  - **BaseProcessor**: Accepts Union[Dict[str, Any], ProcessorServices] for backward compatibility
  - **Related Updates**:
    - `ConscienceInterface` protocol signature updated to use `ConscienceCheckContext`
    - `updated_status_conscience.py` and `thought_depth_guardrail.py` updated to use new context type
    - `main_processor.py` converts dict to ProcessorServices when creating ShutdownProcessor
    - `ciris_runtime.py` uses ShutdownResult attributes instead of `.get()` method
  - **Impact**: Mypy clean with zero errors, significantly improved type safety
- **🧹 Dead Code Removal**: Removed 204 lines of deprecated code
  - Removed 3 deprecated audit methods in Discord adapter
  - Removed 5 deprecated SDK methods (including non-functional `stream()` placeholder)
  - Removed unused TYPE_CHECKING imports
  - Suppressed vulture false positives for TYPE_CHECKING imports with noqa comments
  - Vulture warnings: 11 → 0 (100% clean)
- **🧠 Reduced Cognitive Complexity**: Refactored `collect_circuit_breaker_state()` from complexity 59 to <15
  - Extracted 5 focused helper functions for clarity and maintainability
  - `_extract_service_stats_cb_data()` - Extract CB data from stats dict
  - `_extract_direct_cb_data()` - Extract CB data from CB object
  - `_collect_from_service_stats()` - Collect from bus.get_service_stats()
  - `_collect_from_direct_cb_attribute()` - Collect from bus.circuit_breakers
  - `_collect_from_single_bus()` - Orchestrate collection from one bus
  - Main function now has simple control flow with early returns
  - Functionality preserved, all tests pass

### Testing
- **🧪 Conscience Core Test Coverage**: 20.5% → 88.37% (+67.87%)
  - Added 28 comprehensive tests for `conscience/core.py`
  - Tests cover all 4 conscience types: Entropy, Coherence, OptimizationVeto, EpistemicHumility
  - Tests include: Non-SPEAK actions, sink unavailable, no content, LLM evaluation, error handling, message creation
  - Priority #1 file from quality analyzer (was highest priority with lowest coverage)
- **🧪 Shutdown Processor Test Coverage**: 32.4% → 78.61% (+46.21%)
  - Added 24 comprehensive tests for `shutdown_processor.py`
  - Tests cover: Task creation with emergency auth validation, shutdown flow and status transitions, consent handling, thought processing during shutdown, failure reason detection (REJECT vs error), cleanup operations
  - Tests include: Emergency shutdown authorization (ROOT/AUTHORITY roles), normal shutdown flow, rejection handling, error scenarios
  - Priority #6 file from quality analyzer (59.4/100 priority score)
  - 17/24 tests passing (critical shutdown flows validated)
- All 46 LLM bus tests pass (21 basic + 25 domain routing)
- All 2 QA streaming tests pass (100%)
- All 28 conscience core tests pass (100%)
- Mypy clean: 0 errors in 552 source files
- Zero vulture warnings

## [1.2.5] - 2025-10-06

### Added
- **📊 Shutdown Consent & Reason Tracking**: System now persists shutdown consent status and reasons
  - **Consent Status** (`consent_status` field): Tracks whether shutdown was consensual
    - `"accepted"`: Agent agreed to shutdown (task completed gracefully)
    - `"rejected"`: Agent refused shutdown (task failed/rejected)
    - `"manual"`: No negotiation (crashes, SIGTERM signals, forced restarts)
  - **Shutdown Reason** (`reason` field): Contextual reason (e.g., "Signal 15", "Graceful shutdown")
  - `ContinuitySummary.last_shutdown_consent` and `last_shutdown_reason` fields now populated
  - Runtime checks `agent_processor.shutdown_processor.shutdown_result` to determine consent
  - Uses flexible `NodeAttributes` (dict) to store both fields alongside standard attributes
  - Future shutdowns include both consent and reason; existing 761+ historical shutdowns remain None
  - Visible in SSE `snapshot_and_context` events and system telemetry

### Changed
- **🎯 ServiceMetadata Type Safety Enforcement**: Complete metadata dict → Pydantic schema migration
  - Merged `refactor-metadata-handling` branch - replaced `Dict[str, Any]` with typed `ServiceMetadata`
  - Fixed all 4 services still using `metadata.update()`: LLM, SecretsToolService, Scheduler, RuntimeControl
  - Extended `ServiceMetadata` schema with service-specific optional fields instead of arbitrary dicts
  - Added typed fields: `model`, `adapter`, `tool_count`, `features`, `cron_support`, `description`, etc.
  - All services now use `metadata.model_copy(update={...})` pattern for type-safe metadata updates
  - Maintains "No Untyped Dicts" principle - `extra="forbid"` enforced on ServiceMetadata
  - ciris_engine/logic/services: 0 mypy errors (80 files)
  - All base service tests passing (10/10)

### Fixed
- **🧠 PDMA Prompt Optimization**: Improved context clarity and reduced over-deferral
  - Moved system snapshot context from user message to system message - eliminates redundancy
  - User message now contains only thought content + strong anti-deferral guidance
  - Added explicit instruction: "Do not select defer unless the only possible ethical response in this situation is deferral, most situations call for speak or task_complete"
  - Reduces token usage and improves prompt clarity for ethical evaluation
- **📋 System Snapshot Task Filtering**: Fixed `top_pending_tasks_summary` including non-pending tasks
  - `get_top_tasks()` now correctly filters to PENDING status only (was including COMPLETED, DEFERRED, FAILED, REJECTED)
  - System snapshot now accurately represents only actionable pending tasks
  - Aligns with schema field name `top_pending_tasks_summary`

## [1.2.4] - 2025-10-05

### Fixed
- **🧠 PDMA Ethical Evaluation**: Reduced over-cautious deferral to Wise Authority
  - Updated `EthicalDMAResult` schema to prefer "MOST ethically appropriate action(s)" instead of listing all actions that "could be ethical"
  - Added guidance to "Prefer helpful actions or inaction when ethically clear"
  - Clarified that `defer` should be reserved "only for genuine ethical uncertainty requiring human wisdom, not routine observations"
  - Updated autonomous agent framing: "observations" instead of "requests"
  - Aligns with CIRIS Covenant principles: "Constructed Courage" to act decisively when alignment confirmed, WBD (Wisdom-Based Deferral) for genuine uncertainty only
- **📡 SSE Schema Cleanup**: Removed redundant `context` string field from `SnapshotAndContextResult`
  - Eliminated duplication - `context` was 36k+ char string representation of data already in `system_snapshot`
  - Only structured `system_snapshot` field remains (contains all context data)
  - UI can calculate context size downstream if needed
  - Updated QA streaming verification and tests
- **🎯 EpistemicData Type Safety**: Replaced Dict with proper Pydantic schema
  - Removed `EpistemicData = Dict[str, Union[...]]` type alias from types.py
  - Now using `EpistemicData` schema with 4 concrete fields: entropy_level, coherence_level, uncertainty_acknowledged, reasoning_transparency
  - SSE ConscienceResultEvent now returns structured object instead of JSON string in "aggregated" key
  - Updated ConscienceApplicationResult, conscience_execution, and recursive_processing
  - UI can now access epistemic data via attributes instead of dict keys
  - ciris_engine: 0 mypy errors (553 files)

### Changed
- **⚡ CSDMA Complexity Reduction & Legacy Path Removal**: Refactored `evaluate_thought` method
  - CC 33 → ~5 (~85% reduction)
  - Removed legacy `initial_context` dict-based path - modern context parameter only
  - Simplified from 4 helper methods to 2:
    - `_extract_context_data`: Handles modern context objects
    - `_build_context_summary`: Creates context summary string
  - Main method reduced from 65 lines to 8 lines
  - Removed ~40 lines of legacy dict handling code
  - Enforces single correct path through code
  - All 42 DMA tests passing with zero regressions
  - ciris_engine: 0 mypy errors (553 files)

## [1.2.3] - 2025-10-05

### Added
- **📊 Telemetry Service Refactoring**: Eliminated all SonarCloud complexity violations
  - Created 23 new focused helper functions (15 in helpers.py, 8 extracted methods)
  - Average 69% complexity reduction across all 4 high-CC methods
  - Zero functions over CC 15 threshold (was 4)
  - All 4,950 tests passing with zero regressions

### Fixed
- **🔧 Telemetry Service Type Safety**: Fixed mypy type annotation error
  - Added explicit `Dict[str, ServiceTelemetryData]` annotation in `_collect_from_bootstrap_adapters`
  - ciris_engine: 0 mypy errors (553 files)
- **🧹 Code Quality**: Removed unused parameter from helper function
  - Removed unused `service_type` parameter from `generate_semantic_service_name()` (SonarCloud python:S1172)
  - Improved function signature clarity and maintainability

### Changed
- **⚡ Telemetry Service Complexity Reduction**: Comprehensive refactoring of high-complexity methods
  - `query_metrics`: CC 22 → 9 (59% reduction) - Extracted 5 filtering/conversion helpers
  - `_generate_semantic_service_name`: CC 16 → 8 (50% reduction) - Used dispatch table pattern
  - `collect_from_adapter_instances`: CC 19 → 2 (89% reduction) - Extracted 5 collection helpers
  - `_try_collect_metrics`: CC 19 → 4 (79% reduction) - Extracted 4 method-specific helpers
  - All helper functions maintain full type safety with Pydantic schemas
  - No new Dict[str, Any] introduced
  - Full mypy compliance maintained

## [1.2.2] - 2025-10-04

### Added
- **🎯 100% Type Safety**: Complete mypy cleanup across all three codebases
  - ciris_sdk: 0 errors (was 194 errors across 23 files)
  - ciris_engine: 0 errors (553 files)
  - ciris_modular_services: 0 errors (14 files)
  - Total: 204 errors fixed using parallel Task workers
- **✅ 100% QA Test Coverage**: All 131 tests passing across 14 modules
  - Individual modules: 79/79 tests (auth, agent, memory, telemetry, system, audit, tools, guidance, handlers, filters, sdk, streaming)
  - Comprehensive suites: 52/52 tests (extended_api, api_full)
  - Perfect system reliability validation with no critical incidents
- **📊 TSDB Consolidation Helpers**: Extracted 38 helper functions into 6 focused modules
  - date_calculation_helpers.py (5 functions)
  - db_query_helpers.py (5 functions)
  - aggregation_helpers.py (8 functions + 2 classes)
  - cleanup_helpers.py (9 functions)
  - profound_helpers.py (5 functions)
  - extensive_helpers.py (6 functions)
  - 135 tests with 96.4%+ coverage on all modules

### Fixed
- **🔧 SDK Type Safety** (194 errors fixed):
  - Added `assert data is not None` before dict unpacking operations
  - Fixed Generic type parameters (List[Any], Task[Any], Queue[T], Callable)
  - Fixed Dict types to Dict[str, Any] with proper Union types for params
  - Added field_serializer annotations (_info: Any → Optional[str])
  - Fixed Optional attribute access with isinstance checks
  - Installed types-setuptools for mypy stub support
- **🔧 Mock LLM Type Safety** (10 errors fixed):
  - Fixed ServiceCapabilities/ServiceStatus schema usage
  - Added return type annotations to response generators
  - Fixed variable name collisions (node_type redefinition)
  - Renamed _start_time to _start_time_float to avoid type conflict
- **🔒 SQL Injection Vulnerability** (CodeQL py/sql-injection):
  - Changed LIMIT/OFFSET from f-string interpolation to parameterized queries
  - Before: `f"LIMIT {limit} OFFSET {offset}"`
  - After: `"LIMIT ? OFFSET ?"` with `params.extend([limit, offset])`
  - Added explicit `List[Any]` type annotation for params list
- **🔒 Weak Cryptographic Hashing** (CodeQL py/weak-sensitive-data-hashing):
  - Replaced SHA256 with bcrypt for API key hashing (12 rounds)
  - Added `_verify_key()` method using bcrypt.checkpw()
  - Updated storage to use key_id instead of hash as dictionary key
  - Protects against rainbow table and brute-force attacks
  - All 86 authentication tests passing
- **📦 Dependency Update**: Updated websockets from >=12.0,<13.0 to >=14.0
  - SDK uses `websockets.asyncio.client` which requires version 13.0+
  - Fixed 6 CI test failures related to websockets import
- **🐛 SSE Streaming Bugs**: Fixed 3 critical H3ERE pipeline SSE event bugs (100% QA test pass rate)
  - **BUG 1**: action_rationale empty - Extract from input action at CONSCIENCE_EXECUTION step, add default in mock_llm
  - **BUG 2**: epistemic_data/updated_status_available missing - Make REQUIRED with EXEMPT markers, add to ConscienceResultEvent schema
  - **BUG 3**: 4 audit fields missing - Wire ActionResponse with AuditEntryResult, make all fields REQUIRED
- **📡 Production Timing Bug**: Fixed conscience/action selection results emitted simultaneously - ASPDMA_RESULT now correctly emitted at CONSCIENCE_EXECUTION step (before conscience validation)
- **🔒 Type Safety**: ActionDispatcher now returns typed ActionResponse (was None), fixed missing return statements in error paths
- **⚙️ Audit Service**: log_action now returns AuditEntryResult (was None), wired through component_builder to action_dispatcher
- **🔁 Duplicate Audit Entries**: Fixed duplicate audit logging causing 2x entries (graph, sqlite, jsonl) for every action
  - Removed 27 duplicate _audit_log calls from all 10 handlers
  - Removed duplicate audit from base_handler._handle_error
  - Centralized audit logging now ONLY in action_dispatcher (3 locations: registry timeout, success, error)
  - Each action now audited exactly ONCE

### Changed
- **📊 PDMA Prompt Enhancement**: Updated ethical evaluation prompt
  - Listed all 10 handler actions explicitly (observe, speak, tool, reject, ponder, defer, memorize, recall, forget, task_complete)
  - Clarified "inaction is also an action" in decision evaluation
  - Enhanced schema documentation for handler action evaluation
- **🧹 Type Safety Patterns**: Established consistent patterns across codebase
  - Assert-before-unpack pattern for Optional dict handling
  - Generic type parameters for all collections
  - Explicit type annotations for kwargs and **params
  - Type narrowing with isinstance() and assert statements
- **⚡ TSDB Consolidation Complexity Reduction**: service.py from 2,024 → 1,491 lines (26.3% reduction)
  - `_cleanup_old_data`: CC 19 → 9 (52.6% reduction)
  - `_run_profound_consolidation`: CC 22 → 7 (68.2% reduction)
  - `_run_extensive_consolidation`: CC 34 → 13 (61.8% reduction)
  - `_create_all_edges`: CC 18 → 13 (27.8% reduction)
  - All functions now meet CC ≤ 15 SonarCloud threshold
- **🧹 Code Quality**: Fixed SonarCloud issues in TSDB helpers
  - Extracted duplicate error message strings to constants
  - Removed unnecessary f-string in cleanup_helpers.py
- **✅ REQUIRED Fields**: Made critical SSE/audit fields non-optional throughout schemas
  - ActionSelectionDMAResult.rationale, ConscienceApplicationResult.epistemic_data
  - AuditEntryResult: sequence_number, entry_hash, signature
  - ConscienceExecutionStepData.action_rationale, ConscienceResultEvent.updated_status_available
- **🎯 Fail-Fast**: Removed all fallback logic - system fails loud with detailed errors when required data missing

## [1.2.1] - 2025-10-04

### Fixed
- **🧪 Test Compatibility**: Fixed `test_check_pause_state_paused_with_event` to use real `asyncio.Event` instead of `AsyncMock` for isinstance() guard compatibility
- **📦 Dependency Upgrade**: Upgraded instructor from 1.3.3 to 1.11.3, eliminating 34 DeprecationWarning about FUNCTIONS mode
- **⚠️ Warning Reduction**: Reduced test warnings by 68% (50 → 16 warnings, all non-critical pytest internals)
- **🔧 Code Quality**: Removed unused `consent_service` variable in graph.py (SonarCloud code smell)
- **📋 Schema Conflicts**: Removed duplicate AgentIdentityRoot from self_observation.py __all__ exports
- **🐛 Identity Variance Monitor**: Fixed multiple implementation bugs in identity_variance_monitor.py
  - Fixed system_state type mismatch (expects Dict[str, str] not string)
  - Fixed identity_root serialization (expects dict not AgentIdentityRoot object)
  - Fixed MemoryOpStatus comparison (use enum not string value)
  - Fixed None time_service handling in __init__
  - Fixed VarianceCheckMetadata previous_check validation (expects datetime not string)
  - Created 48 comprehensive tests (100% passing)

### Added
- **🔍 Guidance Observation Auditing**: Added audit logging for WA guidance observations
  - Tracks both solicited (with recommendation) and unsolicited guidance requests
  - Logs guidance_provided vs no_guidance outcomes
  - Recorded as observations via `log_event` with action="observe"
- **📬 Async Message API Endpoint**: New `/agent/message` endpoint for immediate task_id return
  - Returns immediately with `task_id` for tracking (no blocking wait)
  - Comprehensive status tracking via `MessageHandlingStatus` enum (9 status types)
  - Rejection reasons: FILTERED_OUT, CREDIT_DENIED, CREDIT_CHECK_FAILED, PROCESSOR_PAUSED, etc.
  - Adaptive filter integration with priority levels (CRITICAL, HIGH, MEDIUM, LOW, IGNORE)
  - Existing task update detection (tracks when messages update existing tasks vs creating new)
  - Credit policy enforcement with detailed rejection messages
  - 39 comprehensive tests covering all scenarios
- **📊 Message Handling Schemas**: New typed schemas for complete message flow
  - `MessageHandlingStatus` enum: TASK_CREATED, UPDATED_EXISTING_TASK, FILTERED_OUT, CREDIT_DENIED, etc.
  - `PassiveObservationResult`: Result of observation task creation with metadata
  - `MessageHandlingResult`: Complete message handling result with status, task_id, and rejection info
  - Full propagation of results through BaseObserver call chain
- **🆔 Identity Context Formatting**: Created human-readable identity formatter for system snapshots
  - Replaces raw escaped dict dump with clean formatted text
  - Shows "First Start" from earliest startup or shutdown event
  - Displays last 5 shutdowns with timestamps
  - Supports both old ("consciousness_preservation") and new ("continuity_awareness") terminology
  - Provides foundation for future uptime/downtime statistics
- **⏱️ Startup Node Tracking**: Added automatic startup node creation for continuity awareness
  - Creates GraphNode on each startup with tags `["startup", "continuity_awareness"]`
  - Stored in IDENTITY scope alongside shutdown nodes
  - Enables future calculation of session duration and availability metrics

### Changed
- **🔒 Audit System Cleanup**: Reduced audit verbosity to only important events
  - Fixed `log_event` trace correlation to extract action type from event data
  - Deprecated verbose Discord audit methods (messages, connections) - already covered by handler actions
  - Hash chain now always enabled (fails fast if initialization fails)
  - Audit events now logged: handler actions, WA operations, guidance observations, system shutdown, Discord mod actions only
- **📉 Reduced Cognitive Complexity**: Refactored base_processor.py dispatch_action method
  - Cognitive complexity reduced from 25 → ~8 (below 15 threshold)
  - Extracted 4 helper methods: _get_time_service(), _stream_perform_action_step(), _extract_action_name(), _calculate_dispatch_time()
  - Improved maintainability and readability while preserving functionality
  - Added 20 comprehensive unit tests covering all helper methods and integration scenarios
- **🐛 Data Loss Bug Fix**: Fixed missing execution metrics in ACTION_COMPLETE events
  - dispatch_time_ms and action_name were calculated but not passed to decorator
  - Now enriches dispatch_result with execution_time_ms, action_type, dispatch_end_time
  - The _action_complete_step decorator now receives timing data for SSE streaming
- **🧹 Code Quality Improvements**: Fixed SonarCloud issues in step_decorators.py
  - Removed unnecessary f-string (L1164) - replaced with normal string
  - Removed unused `result` parameter from _create_action_result_event() (L1252)
- **🐛 Critical Bug Fix**: Implemented missing _perform_aspdma_with_guidance method
  - Renamed _perform_aspdma_with_retry → _perform_aspdma_with_guidance (recursive_processing.py:117)
  - Method was called but never defined (suppressed by type: ignore[attr-defined])
  - Now properly uses typed conscience results (ConscienceApplicationResult) to guide retry attempts
  - Enriches thought context with conscience_guidance containing override_reason and epistemic_data
  - Fixed unused action_result parameter in _handle_conscience_retry_without_override (main.py:703)
- **📉 Reduced Cognitive Complexity**: Refactored telemetry helpers aggregate_metric_by_type
  - Cognitive complexity reduced from 27 → ~8 (below 15 threshold)
  - Extracted 9 metric-specific handler functions with dispatch table pattern
  - Created _update_windowed_metric helper to reduce duplication
  - All 384 telemetry tests pass
- **🐛 Timing Bug Fix**: Fixed window_start parameter in get_average_thought_depth
  - Parameter was accepted but ignored - SQL used hardcoded datetime('now', '-24 hours')
  - Now properly uses window_start parameter for timing consistency with other telemetry
  - Prevents timing drift between telemetry calculation start and SQL execution
- **📉 Reduced Cognitive Complexity**: Refactored edge_manager.py create_edges method
  - Cognitive complexity reduced from 39 → ~8 (below 15 threshold)
  - Extracted 6 helper methods: _normalize_edge_specifications(), _normalize_edge_tuples(), _create_missing_channel_node(), _create_missing_nodes(), _build_edge_record(), _build_edge_data()
  - Removed unused nodes_to_create variable (dead code - creation handled inline)
  - All 144 edge-related tests pass, 19 tsdb_consolidation tests pass
- **⚡ QA Test Optimization - 3x Performance Improvement**: Updated handlers and filters tests to use SSE streaming
  - Handlers tests: 48.38s (down from 151.93s) - 3.1x speedup
  - Filters tests: 169.40s (down from 600+s) - 3.5x+ speedup
  - Changed from blocking `/agent/interact` to async `/agent/message` endpoint
  - Implemented SSE-based completion detection for ANY action (speak, memorize, recall, etc.)
  - Reduced timeouts from 120s to 30s
  - 100% pass rate maintained (5/5 handlers, 36/36 filters)
- **📊 Event Streaming Log Cleanup**: Reduced INFO-level logging noise
  - Changed broadcast and audit debug logs from INFO to DEBUG level
  - Cleaner production logs during SSE streaming
- **🧠 Conscience Schema Refactoring**: Separated epistemic metrics from conscience override fields
  - `EpistemicData` now contains only pure epistemic metrics (entropy, coherence, uncertainty, reasoning transparency)
  - Moved `replacement_action` and `CIRIS_OBSERVATION_UPDATED_STATUS` to `ConscienceCheckResult` top-level fields
  - Updated `UpdatedStatusConscience` and `ThoughtDepthGuardrail` to use new structure
  - Updated conscience execution logic in `conscience_execution.py` and `main.py` to access `replacement_action` from top level
- **🔧 Type Safety**: Eliminated 97% of `Dict[str, Any]` from schemas/protocols (225 replacements)
  - Replaced with semantic type aliases: `NodeAttributes`, `JSONDict`, `JSONValue`
  - All internal schemas now use typed structures
  - Only external interfaces (OTLP, GraphQL, OAuth) retain `Dict[str, Any]` with NOQA markers
- **📉 Reduced Cognitive Complexity**: Refactored DiscordPlatform.__init__ method
  - Cognitive complexity reduced from 120 → ~8 (46% below 15 threshold)
  - Extracted CIRISDiscordClient to separate file (ciris_discord_client.py, 157 lines)
  - Created 4 helper methods: _initialize_config(), _initialize_discord_client(), _initialize_discord_adapter(), _configure_monitored_channels()
  - Reduced __init__ from ~250 lines to 19 lines (92% reduction)
  - adapter.py: 810 → 711 lines (-99 lines)
  - All 458 Discord tests passing (zero functionality changes)
  - Improved maintainability and testability

### Fixed
- **🎯 H3ERE SSE Streaming - 100% Schema Validation**: Complete concrete type enforcement for all 6 reasoning events
  - **Duplicate Events**: Removed duplicate ACTION_COMPLETE broadcast (base_processor manual broadcast conflicted with decorator)
  - **DMA Results**: All 3 DMAs (ethical_pdma, csdma, dsdma) now required and strongly-typed throughout pipeline
    - DMA orchestrator fails fast if DSDMA not configured
    - DMA factory raises RuntimeError instead of returning None
    - InitialDMAResults schema requires all 3 fields (non-optional)
  - **SystemSnapshot**: snapshot_and_context event now includes full SystemSnapshot from thought context
    - Extracts complete system state: channel_context, user_profiles, agent_identity, task details
    - Step decorators pass thought_item to event creation for context extraction
  - **Schema Validation**: QA runner now validates SystemSnapshot field types deeply
  - Test results: 100% SSE validation (6/6 events, 0 duplicates, 0 schema errors)
- **📚 SSE Documentation**: Added comprehensive docs/SSE_EVENT_DETAILS.md
  - Complete schemas for all 6 H3ERE reasoning events
  - Usage patterns for /agent/message endpoint and SSE streaming
  - Client examples (JavaScript, Python, cURL)
  - Error handling and best practices
- **📡 ACTION_RESULT Event Data**: Fixed missing follow_up_thought_id and audit trail data
  - Added `follow_up_thought_id` field to `ActionCompleteStepData` schema
  - Updated `_create_action_complete_data` to extract audit fields from dispatch_result dict
  - ACTION_RESULT events now include full audit trail (entry_id, sequence_number, hash, signature)
- **🧪 Test Fixes**: Updated 8 tests for schema changes
  - Fixed DMA_RESULTS event test to pass `dma_results` parameter with proper InitialDMAResults mock
  - Fixed ACTION_RESULT event tests to use `follow_up_thought_id` from step_data
  - Fixed ConversationSummaryNode test to include required `correlation_id` field
  - Fixed UpdatedStatusConscience tests to access `replacement_action` from top level instead of `epistemic_data`

## [1.2.0] - 2025-10-01

### Added
- **⏰ System Time Display**: Fixed system snapshot formatter to display "Time of System Snapshot" with UTC, Chicago, and Tokyo times
- **📋 Task Update Tracking**: New 6th conscience check (UpdatedStatusConscience) detects new observations arriving during task processing
  - Automatically forces PONDER when new messages arrive in active task's channel
  - Stores observations in thought payload under `CIRIS_OBSERVATION_UPDATED_STATUS`
  - Only updates tasks that haven't committed to non-PONDER actions
  - Database migration 003 adds `updated_info_available` and `updated_info_content` to tasks table
- **🔐 Memory Access Control (OBSERVER Filtering)**: Complete role-based filtering for memory query/search endpoints
  - **TaskSummaryNode Enhancement**: Now preserves user attribution data for DSAR/consent/filtering
    - Added `user_list` (all unique user IDs involved in tasks)
    - Added `tasks_by_user` (task count per user)
    - Added `user_id` field to individual task summaries
  - **Double-Protection Filtering**: Two-layer defense for OBSERVER users
    - Layer 1: SQL-level filtering (ACTIVE - filters at database query level using JSON extraction and LIKE patterns)
    - Layer 2: Post-query result filtering (ACTIVE - filters by `created_by`, `user_list`, `task_summaries[].user_id`, `conversations_by_channel[].author_id`)
  - **Protected Endpoints**:
    - `POST /memory/query` - OBSERVER users see only their memories
    - `GET /memory/timeline` - Filtered timeline view
    - `GET /memory/{node_id}` - Returns 403 Forbidden if unauthorized (not 404)
    - `GET /memory/recall/{node_id}` - Same protection as above
  - **OAuth Integration**: Automatically includes memories from linked Discord/Google accounts
  - **ADMIN Bypass**: ADMIN/AUTHORITY/SYSTEM_ADMIN see all memories without filtering
  - **DSAR Ready**: User attribution preserved across all consolidated nodes for GDPR compliance

### Fixed
- **🔐 OAuth Account Linking Permissions**: Users can now link/unlink their own OAuth accounts without admin privileges
  - `POST /v1/users/{user_id}/oauth-links` - Users can link to their own account, SYSTEM_ADMIN can link to any
  - `DELETE /v1/users/{user_id}/oauth-links/{provider}/{external_id}` - Users can unlink from their own account, SYSTEM_ADMIN can unlink from any
  - Removed `users.write` permission requirement when operating on own account
  - Enables self-service OAuth account management for all authenticated users
- **🐛 Memory Service Startup**: Fixed missing `await` on `memory_service.start()` causing circuit breaker failures
  - `service_initializer.py:268` - Added missing `await` keyword
  - Resolves RuntimeWarning: "coroutine 'LocalGraphMemoryService.start' was never awaited"
  - Prevents memory service circuit breaker opening during TSDB consolidation at startup
- **🐛 ConscienceApplicationResult Handling**: Fixed handlers receiving wrong result type
  - `action_dispatcher.py:93-100,193` - Extract `final_action` from `ConscienceApplicationResult` before passing to handlers
  - `shutdown_processor.py:338-339,347` - Extract action type from `final_action`
  - Handlers expect `ActionSelectionDMAResult` but were receiving `ConscienceApplicationResult`
  - Architecture: ASDMA produces `ActionSelectionDMAResult`, conscience wraps it in `ConscienceApplicationResult` with `original_action` and `final_action` fields
  - Resolves AttributeError: 'ConscienceApplicationResult' object has no attribute 'action_parameters'
- **🐛 Graceful Shutdown BrokenPipeError**: Fixed crash during shutdown when stdout is closed
  - `state_manager.py:144` - Wrapped `print()` in try-except to catch BrokenPipeError/OSError
  - Prevents processing loop crashes during graceful shutdown in non-interactive contexts (QA runner, systemd)
- **🎯 ACTION_RESULT Event Streaming**: Fixed critical bugs preventing ACTION_RESULT events from streaming
  - **Attribute Access Bugs**: Fixed 3 bugs where code accessed `result.selected_action` instead of `result.final_action.selected_action`
    - `thought_processor/main.py:357` - Fixed telemetry recording
    - `thought_processor/round_complete.py:44` - Fixed metric recording
    - `action_dispatcher.py:92` - **Root cause**: Fixed action type extraction from ConscienceApplicationResult
  - All 5 reasoning events (SNAPSHOT_AND_CONTEXT, DMA_RESULTS, ASPDMA_RESULT, CONSCIENCE_RESULT, ACTION_RESULT) now streaming correctly via SSE
- **🤝 Discord Inter-Agent Awareness**: Complete fix for agents seeing other agents' messages
  - **Conversation History**: Changed Discord fetch_messages() to prioritize Discord API over correlation database
    - Now includes messages from all users and bots in history lookups
    - Maintains fallback to correlation database if Discord API unavailable
  - **Real-time Observations**: Removed bot message filter from on_message handler
    - Agents now create passive observations for messages from other agents
    - Enables full multi-agent awareness in monitored Discord channels

### Added
- **🔐 Role-Based Event Filtering**: Secure event filtering for SSE reasoning stream endpoint
  - **OBSERVER Role**: Users see only events for tasks they created (matched by user_id or linked OAuth accounts)
  - **ADMIN+ Roles**: ADMIN/AUTHORITY/SYSTEM_ADMIN users see all events without filtering
  - **Security**: Whitelist-based filtering with parameterized SQL queries to prevent SQL injection
  - **Performance**: Batch database lookups and per-connection caching minimize database queries
  - **OAuth Integration**: Automatically includes events from user's linked Discord/Google accounts

## [1.1.9] - 2025-09-30

### Fixed
- **🔧 SonarCloud Issues**: Resolved 7 code quality issues
  - Reduced channel resolution cognitive complexity from 27 to ~10 by extracting 4 helper functions
  - Fixed 6 pipeline control return types from dict to Pydantic SingleStepResult/ThoughtProcessingResult
  - Updated main_processor to support both dict and Pydantic model responses
- **🐛 Production Channel History Bug**: Fixed BusManager API misuse causing empty conversation history
  - Changed from `bus_manager.get_bus()` (non-existent) to `bus_manager.communication` (direct property access)
  - Fixed production Datum agent empty conversation history issue
- **🔧 Runtime Errors**: Fixed NameError in context builder (undefined `resolution_source` variable)
- **🔒 Security Updates**: Fixed Dependabot vulnerabilities
  - Upgraded pypdf from 4.x to 6.x (CVE RAM exhaustion fix)
  - Upgraded SonarQube action from v5 to v6 (argument injection fix)
- **✨ Pydantic v2 Migration**: Complete migration reducing warnings by 86% (1834→262)
  - Migrated all `.dict()` calls to `.model_dump()` across codebase
  - Updated test mocks to match Pydantic v2 API
  - Fixed async test warnings by aligning mocks with actual service interfaces
  - Renamed test helper classes to avoid pytest collection warnings (TestService→MockServiceForTesting)

### Added
- **💳 Credit Gating System**: Unlimit commerce integration for usage-based billing
  - New schemas: CreditAccount, CreditContext, CreditCheckResult, CreditSpendRequest/Result
  - CreditGateProtocol for multi-provider support with async operations
  - UnlimitCreditProvider with 15s TTL caching and fail-open/fail-closed modes
  - BaseObserver credit enforcement with CreditCheckFailed/CreditDenied exceptions
  - API credit gating on `/v1/agent/interact` (402 Payment Required on denial)
- **🔗 OAuth Identity Linking**: Link multiple OAuth providers to single user account
  - `POST /v1/users/oauth-links` - Link OAuth account
  - `DELETE /v1/users/oauth-links/{provider}` - Unlink OAuth account
  - Dual-key user storage (both wa_id and oauth:provider keys point to same User object)

### Enhanced
- **✅ Test Coverage**: Added 29 new tests (26 channel resolution, 10 pipeline control, 9 integration)
  - Enhanced test_buses_coverage.py with 3 fetch_messages tests
  - Created TestChannelHistoryFetch with 6 comprehensive tests validating BusManager fix
  - All tests updated for new billing dual-key OAuth user storage behavior

### Tested
- **✅ Complete Test Suite**: 75/75 QA tests passing (100% success rate)
- **✅ Integration Tests**: 20 billing tests passing (credit gate, OAuth linking, resource monitor)

## [1.1.8] - 2025-09-30

### Major Runtime Refactoring & Type Safety Improvements - "Beast Conquered" 🐉→✨

### Fixed
- **🔧 SonarCloud Code Quality Issues**: Resolved 5 critical code smells
  - Fixed duplicate if-else blocks in base_adapter.py
  - Converted Union types to Python 3.10+ | syntax in runtime_control.py
  - Reduced cognitive complexity in ciris_runtime.__init__ from 32 to ~10
  - Eliminated nested conditionals in memory_service.py
  - Reduced _fetch_connected_nodes complexity from 18 to ~10
- **🔧 Type Safety Migration**: Complete migration from untyped dicts to Pydantic models
  - Replaced all runtime/adapter kwargs plumbing with RuntimeBootstrapConfig
  - Fixed adapter configuration passing to use typed AdapterConfig
  - Ensured all adapters (API, Discord, CLI) use proper typed configs
  - Fixed ToolInfo validation error (schema → parameters field)

### Tested
- **✅ Complete QA Test Suite Validation**: All 94 tests passing across all modules
  - auth: 5/5 tests passing
  - agent: 6/6 tests passing
  - memory: 3/3 tests passing
  - telemetry: 5/5 tests passing
  - system: 4/4 tests passing
  - audit: 3/3 tests passing
  - tools: 1/1 tests passing
  - guidance: 2/2 tests passing
  - handlers: 5/5 tests passing
  - filters: 36/36 tests passing
  - api_full: 24/24 tests passing
  - **Total: 94/94 tests (100% success rate)**
- **ConsentService Critical Fixes**:
  - Fixed `check_expiry()` to propagate `ConsentNotFoundError` (fail fast, fail loud philosophy)
  - Added 21 comprehensive tests for critical paths (get_consent, revoke_consent, impact reports)
  - Coverage increased from 59.35% to 74.12% with all 70 tests passing
- **TaskSelectionCriteria Bug Fix**: Added missing `configs` field preventing `AttributeError` in runtime control
- **Critical Emergency Shutdown Fix**: Fixed ServiceRegistry.get_service() call with proper handler and ServiceType parameters
- **ConfigValueMap Fix**: Added missing dict-like methods (get/set/update/keys/items/values) preventing AttributeError in config operations
- **Adapter Unload Fix**: Fixed critical crash using correct GraphConfigService API (list_configs + set_config instead of non-existent get_all/delete)
- **🚀 MASSIVE Complexity Reduction**: Transformed the most complex runtime methods to production-grade excellence
  - `shutdown` method: CC 75 → CC 3 (96% reduction, 368 lines → 45 lines)
  - `run` method: CC 32 → CC 14 (56% reduction, 100 lines → 45 lines)
  - `_start_adapter_connections` method: CC 23 → CC 3 (87% reduction, 95 lines → 25 lines)
  - All methods now SonarCloud compliant (under CC 15 threshold)
  - Zero regressions: All 38 runtime tests + 65 helper tests passing (100% success rate)

### Added
- **🛠️ Production-Grade Helper Functions (23+)**: Comprehensive helper function suite with focused responsibilities
  - **Shutdown Helpers (8 functions)**: validate_shutdown_preconditions, prepare_shutdown_maintenance_tasks, execute_service_shutdown_sequence, handle_adapter_shutdown_cleanup, preserve_critical_system_state, finalize_shutdown_logging, cleanup_runtime_resources, validate_shutdown_completion
  - **Run Method Helpers (6 functions)**: setup_runtime_monitoring_tasks, monitor_runtime_shutdown_signals, handle_runtime_agent_task_completion, handle_runtime_task_failures, finalize_runtime_execution
  - **Adapter Connection Helpers (4 functions)**: log_adapter_configuration_details, create_adapter_lifecycle_tasks, wait_for_adapter_readiness, verify_adapter_service_registration
- **🧪 Robust Test Infrastructure**: Schema-based testing fixtures for production-grade validation
  - tests/ciris_engine/logic/runtime/conftest.py: 343 lines of comprehensive fixtures
  - tests/ciris_engine/logic/runtime/test_ciris_runtime_helpers.py: 441 lines of helper function tests
  - Schema integration: AgentState, AdapterConfig, ServiceMetadata for proper behavioral modeling
  - Fixed 6 failing helper function tests with proper asyncio task handling and schema validation
- **📋 Runtime Refactoring Documentation**: Complete battle plan and success metrics
  - RUNTIME_REFACTORING_PLAN.md: Comprehensive refactoring strategy and implementation roadmap
  - Technical achievements: 861 lines of helpers added, 584 lines reduced in main runtime

### Enhanced
- **⚡ Maintainability Revolution**: Core runtime transformed from unmaintainable to production-grade
  - Clear separation of concerns with modular helper functions
  - Comprehensive test coverage with robust schema-based fixtures
  - Scalable architecture enabling easy future development
  - Type-safe error handling throughout shutdown and runtime sequences
- **🔧 Advanced Type Safety**: Enhanced Dict[str, Any] elimination with 2,806 audit findings
  - Created dict_any_audit_results.json for comprehensive tracking
  - Added 41 new type-safe schemas across runtime, streaming, and adapter management
  - Enhanced audit tools for systematic Dict[str, Any] detection and remediation
- **📊 Extensive Test Improvements**: Multi-module test enhancement for stability
  - Enhanced step decorator tests: 454 additional lines for comprehensive coverage
  - Improved streaming tests: 837 additional lines for reasoning stream validation
  - Expanded adapter manager tests: 547 additional lines for runtime adapter coverage
  - Infrastructure test improvements across step streaming, system snapshot, privacy utilities

### Technical Achievements
- **📈 Code Quality Metrics**: Largest single improvement to CIRIS core maintainability
  - 7,815 insertions, 1,238 deletions (net +6,577 lines of improvements)
  - 46 files modified with systematic quality improvements
  - Foundation established for all future development excellence
- **🎯 Zero Regression Policy**: 100% behavioral compatibility maintained throughout refactoring
  - All existing functionality preserved with enhanced robustness
  - Complete test suite validation ensuring production readiness
  - Systematic approach enabling confident deployment

## [1.1.7] - 2025-09-28

### Fixed
- **🔧 H3ERE Pipeline Type Safety**: Migrated step decorators from Dict[str, Any] to typed Pydantic schemas
  - Replaced all 18 _add_*_data functions with _create_*_data functions returning typed objects
  - Added 11 comprehensive StepData schemas eliminating 42 Dict[str, Any] violations
  - Implemented fail-fast error handling throughout H3ERE pipeline
  - Fixed all 60 step decorator tests with enhanced Mock configurations and type-safe assertions
  - All QA modules pass (119 tests) confirming no regressions from major refactoring
- **🔧 Time Service Integration**: Completed time service wiring for enhanced system snapshot functionality
  - Added time_service parameter to ContextBuilder initialization in ComponentBuilder
  - Enhanced QA Runner with 120s timeouts for agent interaction tests
  - All QA modules now pass with full functionality restored
- **🔧 Time Service Dependencies**: Resolved time_service dependency integration across test suite
  - Added time_service parameter to test method signatures and build_system_snapshot calls
  - Enhanced time service integration with fail-fast error handling
- **🔧 Async Mock Setup Issues**: Fixed secrets service integration test async mock patching
  - Used new_callable=AsyncMock for proper async function mocking eliminating coroutine warnings
  - Resolved secrets_service.get_secrets_data() async boundary issues in test infrastructure
- **🔧 Logger Patching Issues**: Fixed incorrect logger patching in user profile extraction tests
  - Changed from system_snapshot.persistence to system_snapshot_helpers.persistence for correlation history extraction
  - Fixed comprehensive user profile extraction test patching addressing modular architecture dependencies
  - Added missing user profile logging to maintain robust testing of System Under Test (SUT)
- **🔧 Test Expectation Updates**: Updated corruption fix tests to expect FIELD_FAILED_VALIDATION warnings
  - Removed obsolete corruption fix test file (logic was replaced with field validation warnings)
  - Fixed comprehensive user profile extraction test patching issues
- **🔧 Cognitive State Reporting**: Fixed cognitive state context building with proper time service dependency
  - Resolved time service dependency issues in gather_context.py affecting cognitive state transitions
  - Enhanced thought processor context gathering with fail-fast time service validation

### Added
- **📊 Enhanced System Snapshot Functionality**: Added user profile logging for improved observability
  - New logging: "[CONTEXT BUILD] N User Profiles queried - X bytes added to context"
  - Added localized time fields to SystemSnapshot schema (London, Chicago, Tokyo timezones)
  - Enhanced time service integration with fail-fast error handling
- **🧪 New Test Infrastructure**: Comprehensive test fixtures and validation
  - tests/test_system_snapshot_localized_times.py: Time localization validation tests
  - tests/fixtures/system_snapshot_fixtures.py: Reusable test fixtures for system snapshot testing
  - tests/test_system_snapshot_architecture_fix.py: Architecture validation and dependency injection tests

### Removed
- **🗑️ Obsolete Test Files**: Removed tests for functionality that no longer exists
  - Deleted tests/test_system_snapshot_corruption_fix.py (corruption fixing logic was replaced with validation warnings)

### Technical Details
- **Test Coverage**: All 11 previously failing tests now pass with enhanced error handling
- **Architecture**: Maintained robust testing of System Under Test while fixing modular dependency issues
- **Performance**: Enhanced observability with comprehensive logging and fail-fast error detection
- **Files Changed**: 17 files modified (1,076 insertions, 605 deletions) with 3 new test files created

## [1.1.6] - 2025-09-27

### Added
- **🛡️ Anti-Spoofing Security System**: Comprehensive protection against security marker spoofing
  - Channel history anti-spoofing with `CIRIS_CHANNEL_HISTORY_MESSAGE_X_OF_Y_START/END` markers
  - Shared anti-spoofing utility function in `base_observer.py` for code reuse
  - Pattern detection for spoofed observation markers (`CIRIS_OBSERVATION_START/END`)
  - Proper execution order: raw content → anti-spoofing detection → legitimate marker injection
  - Warning message replacement: "WARNING! ATTEMPT TO SPOOF CIRIS SECURITY MARKERS DETECTED!"
- **🔧 Development Tools Enhancement**: Improved version management and release automation
  - Enhanced `bump_version.py` with smart STABLE/BETA release type detection
  - Automatic README.md release status switching based on version stage
  - Flexible pattern matching for both "STABLE RELEASE" and "BETA RELEASE" formats

### Fixed
- **🔧 TSDB Consolidation Edge Creation**: Fixed temporal edge creation for daily telemetry nodes
  - Resolved database connection mocking issues in `test_tsdb_edge_creation.py`
  - Added proper `db_path=":memory:"` configuration for test isolation
  - Fixed double database connection patching for edge manager functionality
- **🔧 Anti-Spoofing Test Suite**: Updated security test expectations for new warning messages
  - Fixed 6 test references from "CONVERSATION MARKERS" to "SECURITY MARKERS"
  - Updated Discord observer security tests for enhanced anti-spoofing functionality
  - All 12 Discord security tests now passing with proper warning message validation
- **🔧 Discord Timeout Logging**: Reduced production log noise from Discord health checks
  - Changed healthy timeout logs from WARNING to DEBUG level
  - Only logs warnings when Discord client is actually unresponsive/closed
  - Added comprehensive unit tests for all timeout scenarios (healthy, unresponsive, no client)
- **🔧 Cognitive State Reporting**: Fixed false status reporting in API endpoints
  - Resolved critical issue where agent status endpoint reported WORK when agent was stuck in other states
  - Changed default return from WORK to UNKNOWN for transparency when state manager is inaccessible
  - Added proper error handling and logging for state manager access failures
  - Improved enum-to-string conversion for AgentState values in API responses
- **🔄 Async Boundary Consistency**: Enhanced async protocol compatibility for future Rust conversion
  - Fixed async/await boundary consistency in StateManager methods (`can_transition_to`, `transition_to`)
  - Updated all state transition callers across runtime and processor modules to use proper async patterns
  - Enhanced test fixtures with AsyncMock compatibility for state manager operations
  - Eliminated RuntimeWarnings about unawaited coroutines in state management system
  - Achieved 100% test pass rate with parallel execution (pytest -n 16) maintaining 4x+ performance improvements
- **🧹 Cognitive Complexity Refactoring**: Resolved all SonarCloud critical complexity issues in API routes
  - Refactored `get_history` function: reduced complexity from 48 to ≤15 with 24 helper functions
  - Refactored `get_status` function: reduced complexity from 20 to ≤15 with 4 helper functions
  - Refactored `websocket_stream` function: reduced complexity from 16 to ≤15 with 7 helper functions
  - Created 35 total helper functions with single responsibility principle and comprehensive error handling
  - Achieved 100% test pass rate (57/57 tests) with comprehensive coverage across all helper functions

## [1.1.5] - 2025-09-26

### Major Achievements
- **💰 External LLM Pricing Configuration**: Complete migration from hardcoded pricing to external JSON configuration system
- **🧪 Robust Centralized Testing Infrastructure**: 100% pytest green achievement with comprehensive fixture-based testing
- **🔄 Enhanced LLM Provider Redundancy**: Improved fallback mechanisms with proper circuit breaker integration

### Added
- **💰 External Pricing Configuration System**: Comprehensive external LLM pricing management
  - `PRICING_DATA.json`: Centralized pricing database with 4 providers (OpenAI, Anthropic, Together AI, Lambda Labs)
  - `LLMPricingCalculator`: Type-safe pricing calculation engine with environmental impact tracking
  - Pydantic models for configuration validation and type safety (`PricingConfig`, `ProviderConfig`, `ModelConfig`)
  - Pattern matching for backward compatibility with existing model names
  - Energy consumption and carbon footprint calculation per model and region
  - Fallback pricing for unknown models with comprehensive error handling
  - Semantic versioning support for pricing configuration schema evolution
- **🧪 Centralized Testing Infrastructure**: Robust fixture-based testing system
  - Comprehensive `mock_pricing_config` fixtures with rich test data across all modules
  - Function-scoped service registry fixtures preventing test interference
  - `MockInstructorRetryException` for consistent instructor exception testing
  - Enhanced LLM service fixtures with proper mock integration
  - Centralized helper functions for test setup and teardown
- **🎭 Discord Adapter Refactoring**: Enhanced reliability and comprehensive test coverage
  - Extracted 6 helper functions from high-complexity methods (D-28 → A-2 complexity reduction)
  - Comprehensive test coverage: 123 test cases across 14 QA modules (100% success rate)
  - Robust error handling with circuit breaker patterns and graceful failures
  - Reply processing with attachment inheritance and context building
  - Enhanced channel management with proper access validation

### Fixed
- **🔧 LLM Bus Service Registration**: Resolved security violations in mock service registration
  - Fixed service registry security checks preventing mock service conflicts
  - Proper metadata marking for mock services with `provider: "mock"` identification
  - Function-scoped fixtures ensuring test isolation and preventing shared state issues
  - Corrected call counting in custom mock service implementations
  - Updated circuit breaker logic accounting for proper failure thresholds (5 failures)
- **🔧 Instructor Exception Handling**: Eliminated AttributeError on non-existent instructor.exceptions module
  - Replaced direct `instructor.exceptions` imports with centralized `MockInstructorRetryException`
  - Updated all instructor exception tests to use centralized `llm_service_with_exceptions` fixture
  - Proper exception expectation alignment with mock behavior
- **🔧 Test Configuration Missing Fixtures**: Fixed pricing config tests missing required fixtures
  - Created dedicated `tests/ciris_engine/config/conftest.py` with comprehensive pricing fixtures
  - All 31 pricing configuration tests now passing with proper fixture support
  - Enhanced test coverage for edge cases and validation scenarios
- **🔧 Discord Type Hint Accuracy**: Corrected return type annotation for `_build_reply_context`
  - Updated type hint from `str` to `str | None` to match actual return behavior
  - Improved type safety and maintainability for Discord message processing

### Changed
- **LLM Service Architecture**: Migrated from hardcoded pricing (50+ lines) to external configuration
  - Replaced embedded cost calculations with `LLMPricingCalculator.calculate_cost_and_impact()`
  - Maintained backward compatibility with existing model naming patterns
  - Enhanced resource usage tracking with model-specific environmental data
- **Testing Standards**: Achieved 100% pytest green on critical test suites
  - All LLM bus tests passing (3/3 TestServiceUnavailableFailover)
  - All pricing configuration tests passing (31/31)
  - Instructor exception tests using proper centralized mocks
  - Enhanced debugging capabilities with clear error messages

### Technical Details
- **Files Created**: `ciris_engine/config/PRICING_DATA.json`, `ciris_engine/config/pricing_models.py`, `ciris_engine/logic/services/runtime/llm_service/pricing_calculator.py`, `tests/ciris_engine/config/conftest.py`
- **Test Coverage**: 100% success rate on originally failing tests, comprehensive fixture coverage
- **Performance**: Efficient pricing calculation with caching and lazy loading
- **Security**: Proper service isolation and mock security validation

## [Released] - v1.1.4

### Major Achievements
- **🔐 Critical Deferral Resolution Fix**: Fixed WA deferral resolution authentication bug preventing Wise Authorities from resolving deferred decisions
- **👥 Multiple WA Support**: Complete migration from single WA_USER_ID to multiple WA_USER_IDS with comma-separated list support
- **📄 Document Processing**: Added secure document parsing for PDF and DOCX attachments with comprehensive test coverage (91.28%)
- **💬 Discord Reply Processing**: Implemented Discord reply detection with attachment inheritance and priority rules for enhanced context management
- **📋 AI Assistant Enhancement**: Integrated comprehensive CIRIS guide into system prompts providing complete technical context for all AI interactions
- **🧪 QA Excellence Achievement**: Achieved 100% test success rate across all 61 test cases in 15 modules with perfect system stability validation

### Fixed
- **WA Deferral Resolution 403 Error**: Fixed critical authentication bug where users with AUTHORITY role couldn't resolve deferrals
  - Root cause: AUTHORITY role missing `"wa.resolve_deferral"` permission despite having WA certificates with correct scopes
  - Solution: Added `"wa.resolve_deferral"` permission to AUTHORITY role permissions in `auth_service.py:719`
  - Impact: OAuth users minted as Wise Authorities can now properly resolve deferred decisions via API and UI
  - Comprehensive unit tests added covering authentication layers and permission validation

### Added
- **👥 Multiple Wise Authority Support**: Complete WA_USER_IDS migration supporting multiple WA users
  - Discord adapter now parses comma-separated WA_USER_IDS with robust whitespace and empty entry handling
  - Updated shell scripts (register_discord.sh, register_discord_from_env.sh) with proper JSON array building
  - Enhanced Python registration tools (dev/ops) with comma-separated parsing
  - Comprehensive test coverage (27/27 tests passing) including edge cases for spaces, duplicates, and empty entries
- **📄 Document Parsing Support**: Minimal secure document parser for PDF and DOCX attachments
  - Security-first design with 1MB file size limit, 3 attachments max, 30-second processing timeout
  - Whitelist-based filtering (PDF and DOCX only) with content type validation
  - Text-only extraction with 50k character output limit and length truncation
  - Universal adapter support through BaseObserver integration
  - Discord attachment processing with error handling and status reporting
  - Dependencies: pypdf (>=4.0.0) and docx2txt (>=0.8) with CVE-aware selection
  - Comprehensive test suite: 51 tests passing with 91.28% code coverage
- **💬 Discord Reply Processing**: Complete reply detection and attachment inheritance system
  - Reply detection using Discord's `message.reference` system with automatic referenced message fetching
  - Attachment inheritance with strict priority rules: "Reply wins" - reply attachments take precedence over original
  - Smart attachment limits: Maximum 1 image and 3 documents total across both reply and original messages
  - Context management: Original message text included as reply context for enhanced conversation understanding
  - Vision and document processing integration: Processes images and documents from both messages efficiently
  - Enhanced message workflow: Seamless integration with existing message enhancement pipeline
  - Vision helper enhancements: Added `process_image_attachments_list()` for pre-filtered image processing
  - Anti-spoofing protection: Maintains security for CIRIS observation markers in reply content
  - Comprehensive test coverage: 240 tests total (32 reply-specific tests) with 72.55% Discord observer coverage
  - Error handling: Graceful handling of missing references, fetch failures, and malformed attachment data
- **📋 CIRIS Comprehensive Guide Integration**: Complete technical reference integrated into system prompts
  - Created comprehensive AI assistant guide covering all CIRIS architecture, services, and development practices
  - Sanitized guide by removing over-detailed development specifics while preserving essential technical information
  - Integrated guide into system prompts after covenant for universal AI assistant context
  - All AI interactions now receive complete codebase context including API documentation, debugging procedures, and operational guidelines
  - Maintains existing covenant usage patterns without requiring code changes across multiple modules
- **🧪 QA Test Suite Excellence**: Perfect test reliability across all system components
  - **100% Success Rate**: All 61 test cases across 15 modules passing without failures
  - **Comprehensive Coverage**: Authentication, telemetry, agent interaction, system management, memory, audit, tools, guidance, handlers, streaming, SDK, and debugging features
  - **Stable Performance**: All tests completed within extended timeout windows (10-minute limits)
  - **System Reliability**: Consistent API server startup and request handling across all test modules
  - **Production Readiness Validation**: Full end-to-end testing confirms system stability for deployment
- **Comprehensive unit test coverage** for WA permission system including auth service and authentication dependency layers

### Changed
- **Environment Variable Format**: WA_USER_IDS now supports comma-separated lists (e.g., "user1,user2,user3")
- **Documentation Updates**: Environment variables documentation clarifies comma-separated list support
- **Registration Scripts**: All Discord adapter registration tools updated for multiple WA support

### Removed
- **DEFAULT_WA Constant**: Completely removed DEFAULT_WA references across codebase with no backwards compatibility
  - Removed from constants.py, imports, thought processor, and test cases
  - WA_DISCORD_USER environment variable removed entirely
  - Simplified deferral context by removing target_wa_ual field

## [1.1.3] - 2025-09-11

### Major Achievements
- **🔍 Enhanced Conscience Transparency**: Complete conscience evaluation transparency with all 4 typed conscience results (entropy, coherence, optimization veto, epistemic humility) in step streaming and audit trails
- **🧪 Comprehensive QA Validation**: Robust QA runner validation ensuring all required conscience data structures are present and properly formatted
- **📊 Full Epistemic Reporting**: Detailed reporting of ethical decision-making processes with metrics, reasoning, and complete audit trail

### Added
- **Comprehensive conscience result generation** - Added `_create_comprehensive_conscience_result()` function that generates full `ConscienceCheckResult` with all 4 typed evaluations
- **Enhanced step data transparency** - Modified `_add_conscience_execution_data()` to include detailed conscience results in step streaming and traces
- **Robust QA validation** - Enhanced QA runner streaming verification to validate all 4 required conscience check results with field-level validation
- **Typed conscience evaluations** - Complete implementation of entropy check, coherence check, optimization veto check, and epistemic humility check with proper metrics and reasoning

### Changed
- **Conscience step streaming** - Step data now includes comprehensive `conscience_result` field alongside basic `conscience_passed` for full transparency
- **QA runner validation** - Enhanced conscience execution validation to verify presence and structure of all required typed conscience results

## [1.1.2] - 2025-09-10

### Major Achievements
- **🎯 Massive Cognitive Complexity Reduction**: Reduced SonarCloud complexity from 400+ to ≤15 across 7+ critical functions
- **🔒 Complete Type Safety Migration**: Eliminated Dict[str, Any] usage across core systems with proper Pydantic schemas
- **🧹 Comprehensive Code Quality**: Integrated Vulture unused code detection and cleaned up 50+ dead code issues
- **🔧 H3ERE Pipeline Enhancement**: Added typed step results streaming and fixed pipeline test infrastructure

### Fixed
- **Authentication audit log spam** - Removed audit logging for authentication failures to prevent log spam from monitoring systems and invalid token attempts
- **H3ERE pipeline streaming verification** - Moved gather_context from conditional to required steps in streaming verification tests for accurate pipeline validation
- **Typed step results infrastructure** - Fixed step result data structure preservation in SSE streaming to maintain proper type information
- **OAuth WA duplicate user records** - OAuth users minted as Wise Authorities no longer create separate user records, maintaining single record integrity
- **Missing telemetry endpoints** - Added missing @router.post decorator for query_telemetry endpoint and missing fields to TelemetryQueryFilters schema
- **LLM service type safety** - Updated LLM service and tests for proper ExtractedJSONData schema usage
- **Code maintainability issues** - Removed unused parameters, duplicate imports, orphaned code, and indentation errors across multiple modules

### Changed
- **🏗️ Telemetry Routes Architecture** - Completely refactored telemetry routes reducing complexity from 400+ to ~15:
  - `get_reasoning_traces` (137→15) - Extracted 8 helper functions
  - `query_telemetry` (38→15) - Extracted 6 query type handlers
  - `get_otlp_telemetry` (104→15) - Extracted 6 OTLP export helpers
  - `get_detailed_metrics` (82→15) - Extracted 5 metric processing helpers
- **🔧 Audit Service Refactoring** - Reduced complexity from 20→15 with 6 extracted helper functions for ID extraction and processing
- **💾 Type Safety Migration** - Replaced Dict[str, Any] with proper typed schemas across:
  - Pipeline control protocols
  - LLM service schemas
  - Audit service operations
  - Telemetry data structures
  - API route handlers
- **BaseObserver behavior** - Changed to create ACTIVE tasks with STANDARD thoughts for H3ERE pipeline consistency
- **Streaming verification test** - Updated success criteria to validate actual streaming functionality

### Added
- **🔍 Vulture Integration** - Comprehensive unused code detection with CI pipeline integration:
  - Added pyproject.toml with Vulture configuration
  - Created whitelist for legitimate unused code patterns
  - Automated dead code detection in CI/CD pipeline
- **📊 Typed Step Results** - Enhanced reasoning stream with strongly typed step result population
- **🔍 Enhanced H3ERE Tracing** - Rich trace data in step streaming decorators with OTLP compatibility:
  - Added trace context with proper span/trace ID correlation
  - Enhanced span attributes with step-specific metadata
  - Unified data structure between step streaming and OTLP traces
  - Added processor context and thought lifecycle attributes
- **🐛 Enhanced Debug Infrastructure** - Comprehensive tracing for step result creation and H3ERE pipeline execution flow
- **🧪 Test Coverage Expansion** - Added comprehensive test coverage for OAuth WA fixes and LLM service improvements
- **⚙️ QA Runner Enhancement** - Enhanced test runner with debug log support for better troubleshooting

### Removed
- **Dead Code Cleanup** - Systematic removal of unused imports, unreachable code, and unimplemented parameters:
  - Removed duplicate UTC_TIMEZONE_SUFFIX constant
  - Cleaned up unused Union imports from typing
  - Eliminated orphaned code blocks
  - Removed unused function parameters across multiple modules

## [1.1.1] - 2025-09-09

### Fixed
- **Emergency shutdown force termination** - Emergency shutdown endpoint now calls `emergency_shutdown()` instead of `request_shutdown()` for proper SIGKILL termination
- **ThoughtDepthGuardrail DEFER mechanism** - Fixed guardrail not returning DEFER actions to conscience, enabling proper action chain depth limiting
- **OAuth WA minting duplicate records** - OAuth users minted as Wise Authorities no longer create separate user records, maintaining single record integrity
- **Server lifecycle corruption bug** - Long-running API servers no longer accumulate state corruption causing test timeouts

### Security
- **Weak crypto hashing vulnerabilities** - Address CodeQL vulnerabilities #29 and #31 with proper SHA256 hash handling and API key generation

### Added
- **Comprehensive QA test suite** - 125 test cases across 15 modules with 100% success rate validation
- **Dead code cleanup automation** - Systematic removal of unused imports, unreachable code, and unimplemented parameters via Vulture analysis
- **Enhanced test coverage** - Authentication routes coverage increased from 23.63% to 40.07% (+16.44%)

### Changed
- **Cognitive complexity reduction** - Reduced complexity below SonarCloud threshold (15) for 4 critical functions in auth.py, audit.py, and agent.py routes
- **Code maintainability improvements** - Removed 8 high-confidence dead code issues, improving overall code quality

### Removed
- **Unused code cleanup** - Removed unused imports, unreachable code statements, and unimplemented function parameters across core engine modules

## [Unreleased]

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security

---

## Release History

For releases prior to 1.1.1, see individual release notes in `docs/releases/`:
- [1.0.0-RC1](docs/releases/RELEASE_NOTES_1.0.0-RC1.md)
- [1.4.1](docs/releases/RELEASE_NOTES_1.4.1.md) through [1.4.6](docs/releases/RELEASE_NOTES_1.4.6.md)

[1.1.2]: https://github.com/CIRISAI/CIRISAgent/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/CIRISAI/CIRISAgent/compare/v1.1.0...v1.1.1
