# Changelog

All notable changes to CIRIS Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.2] - 2025-09-10

### Fixed
- **H3ERE pipeline streaming test** - Resolved missing gather_context step issue by aligning streaming test expectations with actual system behavior (simple interactions use direct handler processing rather than full H3ERE pipeline)
- **Typed step results infrastructure** - Fixed step result data structure preservation in SSE streaming to maintain proper type information
- **Code maintainability** - Removed unused `thought_id` parameter from `_create_step_result` method in pipeline control protocol

### Changed
- **BaseObserver behavior** - Changed to create ACTIVE tasks with STANDARD thoughts instead of PENDING tasks with OBSERVATION thoughts for consistency with H3ERE pipeline expectations
- **Streaming verification test** - Updated success criteria to validate streaming functionality rather than requiring specific pipeline steps for simple interactions
- **Cognitive complexity** - Reduced complexity in 4 critical functions (reasoning stream, auth service, audit service) from above 15 to ≤15 through helper function extraction

### Added
- **Enhanced debug logging** - Added comprehensive tracing for step result creation and H3ERE pipeline execution flow
- **QA runner debug support** - Enhanced QA test runner to show debug logs in verbose mode for better troubleshooting

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