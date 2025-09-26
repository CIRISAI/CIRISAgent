# Changelog

All notable changes to CIRIS Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - v1.1.4

### Major Achievements
- **🔐 Critical Deferral Resolution Fix**: Fixed WA deferral resolution authentication bug preventing Wise Authorities from resolving deferred decisions
- **👥 Multiple WA Support**: Complete migration from single WA_USER_ID to multiple WA_USER_IDS with comma-separated list support
- **📄 Document Processing**: Added secure document parsing for PDF and DOCX attachments with comprehensive test coverage (91.28%)
- **💬 Discord Reply Processing**: Implemented Discord reply detection with attachment inheritance and priority rules for enhanced context management

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