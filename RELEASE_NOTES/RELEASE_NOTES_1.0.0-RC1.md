# Release Notes - v1.0.0-RC1

## Overview
Release Candidate 1 for CIRIS v1.0.0 marks a major milestone combining the Consensual Evolution Protocol v0.2, enhanced distributed tracing, comprehensive bug fixes, and full API stability. This release candidate features 100% passing tests in the CI/CD pipeline, introduces the 22nd core service (ConsentService), and resolves all critical issues discovered during QA testing.

## Key Achievements

### 🎯 100% CI/CD Test Pass Rate
- All 2,727 tests passing successfully
- Full test coverage across all adapters (CLI, API, Discord)
- Comprehensive QA test suite with Python SDK validation

### 🤝 Consensual Evolution Protocol v0.2
- **22nd Core Service**: ConsentService provides comprehensive consent management
- **Three Consent Streams**:
  - TEMPORARY: 14-day auto-expiry (default for all new users)
  - PARTNERED: Requires bilateral agreement between user and agent
  - ANONYMOUS: Statistics only, no PII retained
- **Bilateral Consent**: Partnership upgrades require agent approval via task system
- **Decay Protocol**: 90-day gradual anonymization instead of immediate deletion
- **DSAR Integration**: Full support for Data Subject Access Requests with legal basis tracking
- **9 New API Endpoints**: Complete consent management suite

### 🔍 Enhanced Distributed Tracing
- **Complete OTLP Support**: Full OpenTelemetry Protocol compliance for traces export
- **Task/Thought Linkage**: All trace spans automatically correlated to originating tasks and thoughts
- **Persistent Storage**: Traces stored as graph nodes for long-term analysis
- **Real-time Collection**: Service correlations captured and stored in real-time

### 🔧 Critical Bug Fixes
- **Async/Await Consistency**: Fixed multiple missing await statements across services
- **API Response Routing**: Resolved API interaction timeouts with proper response handling
- **Memory Operations**: Fixed forget endpoint and circular import issues
- **Discord Integration**: Corrected tools loading to properly show all 18 available tools
- **Consent Service**: Fixed async/await in consent methods and test environment handling

### 📊 Production Readiness
- **Stable API**: 82 endpoints fully operational and tested
- **Type Safety**: Zero `Dict[str, Any]` in production code maintained
- **Service Architecture**: 22 core services + adapter services running smoothly
- **Performance**: Sub-second API response times achieved

## Critical Fixes in This Release

### Async/Await Bugs Resolved
1. **Memory Forget Endpoint** - Added missing await to `memory_service.forget()`
2. **Discord Tool Service** - Fixed `get_all_tool_info()` returning coroutines instead of data
3. **API Response Routing** - Corrected function name from `notify_interact_response` to `store_message_response`

### Import and Module Fixes
4. **Memory Endpoint Imports** - Resolved circular import by moving imports inside functions
5. **API Parameter Alignment** - Fixed memorize() method parameter mismatch

### Logic and Behavior Improvements
6. **ObserveHandler** - Eliminated duplicate follow-up thought creation on errors
7. **Test Infrastructure** - Corrected mock configurations and fixtures
8. **Tools Metadata** - Added missing fields to tools endpoint responses
9. **System Uptime** - Removed hardcoded values for accurate tracking

## API Stability

### Endpoints Verified (82 Total)
- **Authentication**: Login, OAuth, JWT validation
- **Memory**: Store, query, forget, timeline, statistics
- **Tools**: List, execute, metadata retrieval
- **Telemetry**: Unified metrics, OTLP traces, health checks
- **Runtime Control**: Pause, resume, queue management

### New Consent Management Endpoints (9)
- `GET /v1/consent/status` - Get current consent status (creates default TEMPORARY if none)
- `POST /v1/consent/grant` - Grant or update consent (PARTNERED requires agent approval)
- `POST /v1/consent/revoke` - Revoke consent and start decay protocol
- `GET /v1/consent/impact` - Get impact report showing contribution to collective learning
- `GET /v1/consent/audit` - Get immutable audit trail of consent changes
- `GET /v1/consent/streams` - Get available consent streams and descriptions
- `GET /v1/consent/categories` - Get consent categories for PARTNERED stream
- `GET /v1/consent/partnership/status` - Check partnership request status
- `POST /v1/consent/cleanup` - Clean up expired TEMPORARY consents (admin only)

### Performance Metrics
- Average response time: < 1 second
- Memory usage: Within 4GB target
- Service startup: < 30 seconds
- Concurrent request handling: Stable under load

## Testing Coverage

### QA Test Suite
- Comprehensive SDK-based testing (`qa_scripts/qa_v1.0_sdk_comprehensive.py`)
- Service health monitoring and diagnostics
- Discord adapter integration validation
- Memory operations verification

### CI/CD Pipeline
- GitHub Actions: All workflows passing
- Pre-commit hooks: Grace gatekeeper validation
- Type checking: mypy strict mode passing
- Code quality: SonarCloud metrics maintained

## Technical Architecture

### New Components
1. **ConsentService**: Full consent management with three streams and bilateral agreements
2. **PartnershipRequestHandler**: Handles bilateral consent for PARTNERED upgrades
3. **Consent API Routes**: 9 new endpoints for consent management
4. **TelemetryService._store_correlation()**: Persists trace spans as graph nodes with task/thought linkage
5. **VisibilityService.get_recent_traces()**: Retrieves stored correlations for analysis
6. **Enhanced OTLP Converter**: Properly handles task/thought attributes in trace spans

### Architecture Improvements
- Traces stored with `correlation/{id}` node IDs in the memory graph
- Each trace includes task_id and thought_id attributes when available
- Parent-child span relationships preserved
- Execution time and error information captured
- Consent data stored in graph nodes with proper expiry handling

## Migration Notes
- No breaking changes from v1.4.6-beta
- All existing configurations remain compatible
- Database schemas unchanged
- API contracts maintained
- All users automatically get TEMPORARY consent on first interaction
- Existing systems automatically benefit from enhanced tracing

## Service Health Status
- **Core Services**: 22/22 healthy
- **Discord Services**: 4/4 operational (with valid token)
- **API Services**: 3/3 responsive
- **CLI Services**: 1/1 functional

## Known Considerations
- Discord services show as unhealthy with invalid tokens (expected behavior)
- Log file permissions may require adjustment in containerized environments
- OTLP trace export requires external collector configuration

## Deployment Readiness
✅ **Production Ready** - All critical systems operational
- Docker containerization tested and verified
- Kubernetes manifests validated
- Environment variable configuration documented
- Secrets management properly implemented

## Contributors
- Bug fixes and testing guided by comprehensive QA processes
- Aligned with CIRIS architectural principles
- Type safety and audit requirements maintained

## Next Steps for v1.0.0 Final
1. Extended production testing period
2. Performance optimization based on real-world usage
3. Documentation updates for new features
4. Security audit completion

## Upgrade Instructions
```bash
# Pull the latest RC1 branch
git pull origin 1.0-RC1

# Install dependencies
pip install -r requirements.txt

# Run migrations (if any)
python -m ciris_engine.tools.migrate

# Start with your adapter of choice
python main.py --adapter api --port 8000
```

## Support
- Issues: https://github.com/CIRISAI/CIRISAgent/issues
- Documentation: https://docs.ciris.ai
- Discord: https://discord.gg/ciris

---

**Note**: This is a Release Candidate. While extensively tested, please report any issues discovered during deployment.
