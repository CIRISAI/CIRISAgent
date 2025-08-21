# Release Notes - v1.4.6-beta

## Overview
This release introduces distributed tracing support with comprehensive task/thought correlation, fixes critical UI issues, and improves the memorize handler guidance. All traces are now properly linked to their originating tasks and thoughts, ensuring full observability across the CIRIS system.

## Key Features

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

## Technical Details

### New Components
1. **TelemetryService._store_correlation()**: Persists trace spans as graph nodes with task/thought linkage
2. **VisibilityService.get_recent_traces()**: Retrieves stored correlations for analysis
3. **Enhanced OTLP Converter**: Properly handles task/thought attributes in trace spans

### Architecture Improvements
- Traces are stored with `correlation/{id}` node IDs in the memory graph
- Each trace includes task_id and thought_id attributes when available
- Parent-child span relationships are preserved
- Execution time and error information is captured

## API Changes

### New Endpoints Enhancement
- `GET /v1/telemetry/otlp/traces` now returns properly formatted OTLP traces with:
  - Task and thought correlation attributes
  - Proper span hierarchies with parent span IDs
  - Execution timing and success/failure status
  - Service and handler information

## Testing
- Import validation passes for all adapter management changes
- Pre-commit hooks pass with formatting applied
- Grace gatekeeper approved with quality reminders

## Migration Notes
- No breaking changes
- Existing systems will automatically benefit from enhanced tracing
- RuntimeAdapterStatus is backward compatible with previous AdapterStatus usage

## Known Issues
- Dict[str, Any] usage remains in 204 locations (planned for future cleanup)

## Contributors
- Implementation guided by CIRIS Covenant principles
- Aligned with Meta-Goal M-1: Promoting sustainable adaptive coherence

## Next Steps
- Deploy to production for trace collection validation
- Monitor OTLP export performance with real workloads
- Consider adding trace sampling for high-volume scenarios
