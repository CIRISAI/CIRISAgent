# CIRIS v1.0.2-RC1 Patch 2 Release Notes

## Release Overview
This patch release includes critical bug fixes for production issues, comprehensive privacy enhancements for anonymous users, and significant test coverage improvements.

## 🚨 Critical Production Fixes

### FetchedMessage Instantiation Error
- **Fixed**: Production error `FetchedMessage() argument after ** must be a mapping, not FetchedMessage`
- **Impact**: Prevented new agents from fetching messages properly
- **Solution**: Made all adapters consistently return `List[FetchedMessage]` and added robust type checking in communication bus

### WA Deferrals Endpoint 500 Error
- **Fixed**: Type annotation issue causing 500 errors on `/v1/wa/deferrals` endpoint
- **Impact**: Prevented fetching deferral status via API
- **Solution**: Corrected return type annotation from `List[dict]` to proper schema type

## 🔒 Privacy & Security Enhancements

### Anonymous User Privacy Protection
- **New**: Comprehensive privacy utilities for anonymous users
- **Features**:
  - Content hashing for audit trail verification while preserving privacy
  - PII redaction from audit logs and telemetry for anonymous users
  - Anti-gaming measures to detect consent stream manipulation
  - Trust score preservation through anonymization
- **Documentation**: Added comprehensive `ANONYMOUS_USER_HANDLING.md` guide

### Privacy Utilities (`privacy.py`)
- Sanitization functions for anonymous user data
- Redaction of emails, phone numbers, Discord mentions, URLs
- Content hash generation for future verification/refutation
- Support for consent streams: ANONYMOUS, EXPIRED, REVOKED

## 🧪 Test Coverage Improvements

### New Test Suites Added
- **Privacy Utils**: 18 comprehensive tests covering all privacy functions (100% coverage)
- **Anonymous Filter**: Full test coverage for anonymous user handling in AdaptiveFilterService
- **System Snapshot**: Tests for GraphQL consent attributes, resource monitor edge cases, tool service validation
- **Base Observer**: Tests for filter error handling and task signing with WA certificates

### Improved Test Coverage Areas
- Privacy utilities: From 0% to 100%
- System snapshot corruption handling: Added edge case coverage
- Base observer filter and signing: Previously uncovered error paths now tested

## 🛠️ Testing Infrastructure Improvements

### QA Runner Enhancements
- **Fixed**: WebSocket test hanging issue preventing test completion
- **Fixed**: SDK token refresh test failing due to missing `refresh_token` field
- **Fixed**: Token persistence - QA runner now updates token after refresh to prevent 401 errors
- **Fixed**: Server shutdown hanging on `psutil.net_connections()` call
- **Achievement**: 100% pass rate on all 37 QA runner tests across all modules

### Partnership Utilities Refactoring
- **Moved**: `partnership_handler.py` from handlers to utils (not an actual handler)
- **Fixed**: Removed async keyword from `create_partnership_task()` (not using async features)
- **Refactored**: Reduced cognitive complexity of `check_task_outcome()` from 35 to 15
- **Added**: 21 comprehensive tests achieving 100% coverage

## 🐛 Bug Fixes

### Discord Adapter
- Fixed Discord channel filtering to properly handle monitored channels
- Improved correlation creation for better message tracking
- Fixed import issues causing test failures

### System Snapshot Corruption
- Fixed and persisted corrupted `last_seen` attributes with template placeholders
- Added detection and auto-correction for placeholder values like `[INSERT_TIMESTAMP]`
- Improved corruption logging for debugging

### Code Quality
- Fixed SonarCloud code duplication issue by defining constants for redaction placeholders
- Addressed ReDoS vulnerability in email regex pattern

### Test Infrastructure
- Fixed MockConfigService missing `updated_by` parameter
- Fixed MockTimeService fixture issues
- Resolved circular import problems in tests

## 📊 Statistics
- **Files Changed**: 35
- **Lines Added**: 3,435
- **Lines Removed**: 1,200
- **Test Files Added**: 6 new comprehensive test suites
- **Tests Added**: 21 new tests for partnership utilities
- **Documentation Added**: 456 lines of privacy documentation

## 🔄 Breaking Changes
None - This is a backward-compatible patch release

## 📦 Dependencies
No new dependencies added

## 🚀 Deployment Notes

### Discord Bot Configuration
If using Discord adapter, ensure:
1. Bot is invited to server using: `https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=397552864336&scope=bot`
2. `DISCORD_SERVER_ID` environment variable matches your server ID
3. Bot has proper permissions in monitored channels

### Privacy Configuration
Anonymous user handling is automatic when consent stream is set to:
- `ANONYMOUS`
- `EXPIRED`  
- `REVOKED`

## 📝 Commit Summary (15 commits since main)

- `7c4d8e83` fix: Fix FetchedMessage import errors in tests
- `ea457a20` fix: Fix FetchedMessage instantiation error in production
- `b42f605f` test: Add coverage for base_observer filter errors and task signing
- `759c06ef` test: Add coverage for uncovered lines in system_snapshot.py
- `edeb11af` test: Add comprehensive test coverage for privacy utilities
- `e5068433` fix: Fix all remaining test failures in CI
- `ebcc964b` fix: Fix test failures in CI
- `4bc9a338` fix: Fix deferrals endpoint type annotation causing 500 errors
- `ca55bebd` fix: Properly fix and persist corrupted last_seen attributes
- `4e4daf50` feat: Add content hashing for anonymous user privacy protection
- `ba25aeac` fix: Add privacy protection for anonymous users in audit trails
- `73e4f4dc` feat: Enhance AdaptiveFilterService with privacy-preserving anonymous user handling
- `2c90bd2e` fix: Define constants for redaction placeholders to avoid code duplication
- `79f7cc54` fix: Fix QA runner WebSocket test hanging and achieve 100% pass rate
- `f6ca1457` fix: Resolve SonarCloud issues in partnership_utils.py

## 🙏 Acknowledgments
Thanks to the production users who reported the FetchedMessage and deferrals endpoint issues, enabling quick resolution.

---

*For questions or issues, please open a GitHub issue at https://github.com/CIRISAI/CIRISAgent*