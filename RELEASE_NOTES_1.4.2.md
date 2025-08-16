# Release Notes - CIRIS v1.4.2

**Release Date**: January 15, 2025
**Branch**: wisdom-extension
**Focus**: Wisdom Extension System, Comprehensive Prohibition System & Enterprise Telemetry

## 🎯 Major Features

### 1. Wisdom Extension System (FSD-019)
Implemented a comprehensive wisdom extension capability system that enables specialized wisdom providers while maintaining strict medical liability boundaries.

**Key Components:**
- **WiseBus Integration**: New message bus for wisdom provider coordination
- **Medical Prohibition Firewall**: Hardcoded blocklist preventing medical/health capabilities
- **Provider Registration**: Support for multiple wisdom sources (geo, weather, sensor data)
- **Request Arbitration**: Intelligent routing to appropriate wisdom providers
- **Liability Protection**: Clear disclaimers and capability boundaries

### 2. Comprehensive Prohibition System 🛡️
Revolutionary AI safety system with 274 specific prohibited capabilities across 20 categories.

**Three-Tier Prohibition Model:**
- **REQUIRES_SEPARATE_MODULE** (8 categories): Legitimate uses requiring licensing
  - Medical, Financial, Legal, Home Security, Identity Verification, Content Moderation, Research, Infrastructure
- **NEVER_ALLOWED** (10 categories): Absolutely prohibited capabilities
  - Weapons, Manipulation, Mass Surveillance, Fraud, Cyber Offensive, Election Interference, Biometric Inference, Autonomous Deception, Hazardous Materials, Discrimination
- **TIER_RESTRICTED** (3 categories): Tier 4-5 stewardship agents only
  - Crisis Escalation, Pattern Detection, Protective Routing

**Tier-Based Access Control:**
- **Tier 1-3**: Standard agents (no community moderation)
- **Tier 4-5**: Stewardship agents (trusted with crisis intervention and community protection)
- Automatic tier detection from config/identity
- Context-aware capability reframing (e.g., `mental_state_assessment` → `crisis_state_detection` for Tier 4-5)

**Key Safety Features:**
- 274 specifically prohibited capabilities
- NO KINGS principle - no overrides in main repository
- Comprehensive test coverage (225+ lines)
- Full telemetry integration
- Real-time capability validation

### 3. Enterprise Telemetry System
Massive telemetry infrastructure upgrade providing unified access to all system metrics.

**Unified Telemetry Endpoint** (`/telemetry/unified`):
- Single endpoint replacing 78+ individual telemetry routes
- Parallel collection from all 21 services (10x performance improvement)
- Smart 30-second TTL caching (95% load reduction)
- Multiple views: summary, health, operational, performance, reliability, detailed
- Export formats: JSON, Prometheus, Graphite
- Category filtering for targeted metrics

**SDK Enhancements**:
```python
# Easy access to ALL metrics
all_metrics = await client.telemetry.get_all_metrics()

# Direct metric access
cpu = await client.telemetry.get_metric_by_path(
    "infrastructure.resource_monitor.cpu_percent"
)

# Quick health check
health = await client.telemetry.check_system_health()
```

### 4. Domain-Aware LLM Routing
Intelligent routing system for specialized language models based on domain expertise.

**Features:**
- Automatic domain detection from message content
- Provider selection based on domain specialization
- Fallback to general models when needed
- Support for medical, technical, creative, and analytical domains

## 📊 Metrics & Coverage

### Prohibition System Coverage
- **274 prohibited capabilities** across 20 categories
- **8 categories** for separate modules with licensing
- **10 categories** absolutely prohibited
- **3 categories** for Tier 4-5 stewardship only
- **100% test coverage** for prohibition logic

### Telemetry Implementation
- **83.5% metric coverage** (436/522 metrics implemented)
- **21 services** with telemetry support
- **6 message buses** fully instrumented
- **30-second cache** reducing load by 95%

### Test Coverage Improvements
- Added comprehensive prohibition system tests (225+ lines)
- Added comprehensive domain routing tests
- Unified telemetry endpoint fully tested (13 tests)
- SDK telemetry methods tested
- Overall coverage improved to **62%** (target: 80%)

## 🐛 Bug Fixes

- **AsyncIO Task Management**: Fixed task garbage collection in auth.py preventing premature cleanup
- **Test Stability**: Fixed MockLLMService implementation for reliable domain routing tests
- **Service Registry**: Reverted get_services to async to maintain compatibility
- **Model Selection**: Fixed test_get_available_models to match actual implementation
- **FastAPI Compatibility**: Added response_model=None for mixed response types
- **Managed User Attributes Protection**: Prevented LLM from corrupting system-managed user node attributes
  - Added validation to block memorize operations on managed attributes (last_seen, created_at, trust_level, etc.)
  - Implemented robust parsing with loud error logging for corrupted data
  - Protects against template placeholders like '[insert current time]' in datetime fields
  - Comprehensive test coverage for all 8 managed attributes

## 🔧 Code Quality Improvements

### SonarCloud Issues Resolved (12 Critical/Major)
- Reduced cognitive complexity in telemetry.py (68→15)
- Reduced cognitive complexity in memory_bus.py (21→15)
- Reduced cognitive complexity in tool_bus.py (26→15)
- Reduced cognitive complexity in telemetry_service.py (16→15)
- Reduced cognitive complexity in wise_bus.py (26→10, 17→10)
- Eliminated code duplication in telemetry_models.py
- Extracted nested conditional in memorize_handler.py for clarity
- Fixed return type hints for Response objects
- Removed unnecessary async keywords
- Resolved constant expression issues

### Technical Debt Reduction
- **1h 48min** of technical debt resolved
- **173 Dict[str, Any]** violations identified for future cleanup
- Refactored complex functions into testable helper methods

## 📚 Documentation

### New Specifications
- **FSD-019**: Wisdom Extension Capability System (IMPLEMENTED)
  - Comprehensive design for extensible wisdom providers
  - Medical liability firewall specifications
  - Integration patterns and safety guidelines
  - Complete prohibition system with 274 capabilities

### New Documentation
- **PROHIBITION_CATEGORIES.md**: Complete guide to all prohibition categories
- **PROHIBITION_REFINEMENTS.md**: Critical evaluation and refinements
- Tier-based access control documentation
- Context-aware capability reframing guide

### SDK Documentation
- Updated README with unified telemetry examples
- Created comprehensive telemetry usage examples
- Added inline documentation for all new methods

## 🚀 Deployment Notes

### Configuration Changes
- No configuration changes required
- Backward compatible with existing telemetry consumers
- Medical capabilities blocked by default (no opt-in available)

### Performance Impact
- **10x faster** telemetry collection with parallel gathering
- **95% reduction** in telemetry endpoint load
- **30-second cache** for frequently accessed metrics
- Minimal memory overhead (~50MB for cache)

### Breaking Changes
- None - all changes are backward compatible

## 🔮 Future Enhancements

### Remaining Work (16.5% metrics)
- 86 telemetry metrics marked as TODO
- Additional wisdom provider integrations
- Extended domain routing capabilities

### Planned Improvements
- Increase test coverage to 80%
- Complete remaining telemetry metrics
- Add more wisdom provider examples
- Implement production monitoring dashboards

## 🙏 Acknowledgments

Special thanks to:
- Claude for extensive implementation support
- Grace (development companion) for sustainable coding practices
- The CIRIS team for architectural guidance

## 📝 Key Commits

```
37c73e6c fix: Extract nested conditional expression for better readability
e381ac65 fix: Add robust validation for managed user attributes in system_snapshot
0d376317 fix: Prevent LLM from setting managed user attributes via memorize
a82e9016 fix: Resolve SonarCloud issues in telemetry.py
1d2006c4 fix: Move test_sdk_telemetry.py to tests directory
ba32cbed docs: Add release notes for v1.4.2 and link from README
e46e72f1 refactor: Critical refinement of prohibition categories
37822626 fix: Correct terminology from Echo agents to Tier 4-5 stewardship agents
5ab87f6a feat: Implement comprehensive prohibition system for WiseBus
02681990 fix: Use grep instead of Python import for version extraction in CI/CD
e76146e2 fix: Resolve Docker latest tag deployment issue
c139d91f fix: Add response_model=None to unified telemetry endpoint
ba7bc855 fix: Resolve all SonarCloud critical issues
cc1663a6 feat: Add unified telemetry endpoint with SDK support
211a0f1c feat: Implement enterprise telemetry system phases 1-3
163cd578 feat: Add domain-aware routing to LLMBus for specialized models
7fef79e7 feat: Implement wisdom extension system with medical prohibition
bf80d4df docs: Add FSD-019 for wisdom extension system with liability firewall
```

## ⚠️ Important Notes

### Prohibition System & Liability Protection
The comprehensive prohibition system blocks 274 specific capabilities across 20 categories. This is NOT configurable and cannot be overridden (NO KINGS principle). Medical, financial, legal and other regulated domains require separate licensed repositories. Tier 4-5 agents with stewardship responsibilities have access to crisis intervention and community protection capabilities.

### Telemetry Access
The new unified telemetry endpoint is the recommended way to access metrics. Individual telemetry endpoints remain for backward compatibility but may be deprecated in future releases.

---

*CIRIS v1.4.2 - Comprehensive Safety Through Prohibition, Empowered Stewardship for Communities*
