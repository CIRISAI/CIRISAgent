# Release Notes - v1.4.6

## Overview
This release introduces the Consensual Evolution Protocol v0.2 with the new ConsentService as CIRIS's 22nd core service, alongside distributed tracing support with comprehensive task/thought correlation. The consent system provides GDPR-compliant data management with three consent streams and bilateral agreement for partnerships.

## Key Features

### 🤝 Consensual Evolution Protocol v0.2
- **22nd Core Service**: ConsentService provides comprehensive consent management
- **Three Consent Streams**:
  - TEMPORARY: 14-day auto-expiry (default for all new users)
  - PARTNERED: Requires bilateral agreement between user and agent
  - ANONYMOUS: Statistics only, no PII retained
- **Bilateral Consent**: Partnership upgrades require agent approval via task system
- **Decay Protocol**: 90-day gradual anonymization instead of immediate deletion
- **DSAR Integration**: Full support for Data Subject Access Requests with legal basis tracking

### 🔍 Distributed Tracing with Task/Thought Correlation
- **Complete OTLP Support**: Full OpenTelemetry Protocol compliance for traces export
- **Task/Thought Linkage**: All trace spans are automatically correlated to their originating tasks and thoughts
- **Persistent Storage**: Traces are stored as graph nodes for long-term analysis
- **Real-time Collection**: Service correlations are captured and stored in real-time

### 🛠️ Critical Fixes
- **Memory Visualization**: Fixed HTML variable naming conflict preventing node visualization
- **RuntimeAdapterStatus**: Resolved validation errors by renaming AdapterStatus throughout codebase
- **Memorize Handler**: Simplified follow-up guidance to be less prescriptive
- **Graceful Shutdown**: Fixed timeout handling to ensure proper shutdown sequence
- **AuthContext**: Fixed username to user_id field references throughout codebase
- **Async/Await**: Fixed missing async/await in consent service methods
- **Test Compatibility**: Made consent service gracefully handle test environments

## Technical Details

### New Components
1. **ConsentService**: Full consent management with three streams and bilateral agreements
2. **PartnershipRequestHandler**: Handles bilateral consent for PARTNERED upgrades
3. **Consent API Routes**: 9 new endpoints for consent management
4. **TelemetryService._store_correlation()**: Persists trace spans as graph nodes with task/thought linkage
5. **VisibilityService.get_recent_traces()**: Retrieves stored correlations for analysis
6. **Enhanced OTLP Converter**: Properly handles task/thought attributes in trace spans

### Architecture Improvements
- Traces are stored with `correlation/{id}` node IDs in the memory graph
- Each trace includes task_id and thought_id attributes when available
- Parent-child span relationships are preserved
- Execution time and error information is captured

## API Changes

### New Consent Endpoints
- `GET /v1/consent/status` - Get current consent status (creates default TEMPORARY if none)
- `POST /v1/consent/grant` - Grant or update consent (PARTNERED requires agent approval)
- `POST /v1/consent/revoke` - Revoke consent and start decay protocol
- `GET /v1/consent/impact` - Get impact report showing contribution to collective learning
- `GET /v1/consent/audit` - Get immutable audit trail of consent changes
- `GET /v1/consent/streams` - Get available consent streams and descriptions
- `GET /v1/consent/categories` - Get consent categories for PARTNERED stream
- `GET /v1/consent/partnership/status` - Check partnership request status
- `POST /v1/consent/cleanup` - Clean up expired TEMPORARY consents (admin only)

### Enhanced Telemetry Endpoints
- `GET /v1/telemetry/otlp/traces` now returns properly formatted OTLP traces with:
  - Task and thought correlation attributes
  - Proper span hierarchies with parent span IDs
  - Execution timing and success/failure status
  - Service and handler information

## Testing
- All 2612 tests passing in CI/CD pipeline
- Consent service endpoints tested and verified working
- Partnership bilateral consent flow validated
- Import validation passes for all adapter management changes
- Pre-commit hooks pass with formatting applied
- SonarCloud issues resolved (reliability and security ratings improved)

## Migration Notes
- No breaking changes
- All users automatically get TEMPORARY consent on first interaction
- Existing systems will automatically benefit from enhanced tracing
- RuntimeAdapterStatus is backward compatible with previous AdapterStatus usage
- Consent data stored in graph nodes with proper expiry handling

## Contributors
- Implementation guided by CIRIS Covenant principles
- Aligned with Meta-Goal M-1: Promoting sustainable adaptive coherence

## Next Steps
- Deploy to production for trace collection validation
- Monitor OTLP export performance with real workloads
- Consider adding trace sampling for high-volume scenarios
