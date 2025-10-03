# Changelog

All notable changes to CIRIS Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] - 2025-10-03

### Added
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
- **🧠 Conscience Schema Refactoring**: Separated epistemic metrics from conscience override fields
  - `EpistemicData` now contains only pure epistemic metrics (entropy, coherence, uncertainty, reasoning transparency)
  - Moved `replacement_action` and `CIRIS_OBSERVATION_UPDATED_STATUS` to `ConscienceCheckResult` top-level fields
  - Updated `UpdatedStatusConscience` and `ThoughtDepthGuardrail` to use new structure
  - Updated conscience execution logic in `conscience_execution.py` and `main.py` to access `replacement_action` from top level
- **🔧 Type Safety**: Eliminated 97% of `Dict[str, Any]` from schemas/protocols (225 replacements)
  - Replaced with semantic type aliases: `NodeAttributes`, `JSONDict`, `JSONValue`
  - All internal schemas now use typed structures
  - Only external interfaces (OTLP, GraphQL, OAuth) retain `Dict[str, Any]` with NOQA markers

### Fixed
- **📊 DMA Results Streaming**: Fixed DMA_RESULTS SSE event showing null values
  - Corrected field names: `csdma`, `dsdma`, `pdma` (was incorrectly using `aspdma_options`)
  - Now properly extracts DMA result objects from `InitialDMAResults` at PERFORM_ASPDMA step
  - Event broadcasts with actual CSDMA, DSDMA, and PDMA (ethical) decision results
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
