# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the CIRIS codebase.

## 🎯 CURRENT FOCUS: Wisdom Extension System (January 2025)

**Branch**: `wisdom-extension`
**FSD**: `FSD/019_WISDOM_EXTENSION_CAPABILITY_SYSTEM.md`
**Goal**: Enable specialized wisdom providers (geo, weather, sensor) WITHOUT medical liability

### ⚠️ CRITICAL: Medical Domain Prohibition

**NEVER implement in main repo:**
- Medical/health capabilities
- Diagnosis/treatment logic
- Patient data handling
- Clinical decision support

**These are BLOCKED at the bus level.** See `PROHIBITED_CAPABILITIES` in `wise_bus.py`.

### Current Tasks (wisdom-extension branch)
1. Implement medical capability blocklist in WiseBus
2. Add optional capability fields to GuidanceRequest/Response schemas
3. Create WisdomAdvice model with liability disclaimers
4. Add multi-provider support to ServiceRegistry
5. Implement request_guidance() with fan-out and arbitration
6. Create SAFE examples: GeoWisdomAdapter, WeatherWisdomAdapter

---

## Project Overview

CIRIS (Covenant-Integrated Responsible Intelligence System) is an ethical AI platform:
- **Production**: Discord moderation + API at agents.ciris.ai
- **Architecture**: 21 core services, 6 message buses, strict type safety
- **Philosophy**: No Dicts, No Strings, No Kings
- **Target**: 4GB RAM, offline-capable deployment

## Core Philosophy: Type Safety First

✅ **ACHIEVED: Zero `Dict[str, Any]` in production code**

### The Three Rules

1. **No Dicts**: All data uses Pydantic models
2. **No Strings**: Use enums and typed constants
3. **No Kings**: No special cases or bypass patterns

### Before Creating ANY New Type

```bash
# ALWAYS search first:
grep -r "class.*YourThingHere" --include="*.py"
# The schema already exists. Use it.
```

### Type Safety Best Practices

1. **Replace Dict[str, Any] with Pydantic Models**
   ```python
   # ❌ Bad
   def process_data(data: Dict[str, Any]) -> Dict[str, Any]:
       return {"result": data.get("value", 0) * 2}

   # ✅ Good
   class ProcessRequest(BaseModel):
       value: int = 0

   class ProcessResponse(BaseModel):
       result: int

   def process_data(data: ProcessRequest) -> ProcessResponse:
       return ProcessResponse(result=data.value * 2)
   ```

2. **Use Specific Types Instead of Any**
   ```python
   # ❌ Bad
   metrics: Dict[str, Any] = {"cpu": 0.5, "memory": 1024}

   # ✅ Good
   class SystemMetrics(BaseModel):
       cpu: float = Field(..., ge=0, le=1, description="CPU usage 0-1")
       memory: int = Field(..., gt=0, description="Memory in MB")

   metrics = SystemMetrics(cpu=0.5, memory=1024)
   ```

3. **Leverage Union Types for Flexibility**
   ```python
   # For gradual migration or multiple input types
   def process(data: Union[dict, ProcessRequest]) -> ProcessResponse:
       if isinstance(data, dict):
           data = ProcessRequest(**data)
       return ProcessResponse(result=data.value * 2)
   ```

4. **Use Enums for Constants**
   ```python
   # ❌ Bad
   status = "active"  # Magic string

   # ✅ Good
   class ServiceStatus(str, Enum):
       ACTIVE = "active"
       INACTIVE = "inactive"
       ERROR = "error"

   status = ServiceStatus.ACTIVE
   ```

5. **Strict Mypy Configuration**
   - Enable `strict = True` in mypy.ini
   - Use `disallow_any_explicit = True` to catch Dict[str, Any]
   - Run mypy as part of CI/CD pipeline

## CRITICAL: OAuth Callback URL Format

**PRODUCTION OAuth CALLBACK URL - DO NOT FORGET:**
```
https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback
```

Example for Datum + Google:
```
https://agents.ciris.ai/v1/auth/oauth/datum/google/callback
```

**REMEMBER:**
- Agent ID comes BEFORE provider
- /v1/ is at the ROOT level
- This is the DEFAULT route (not /api/{agent}/v1/)

## Current Status (January 2025)

### Major Achievements

1. **Complete Type Safety**
   - Zero `Dict[str, Any]` in production code
   - All data structures use Pydantic schemas
   - Full type validation throughout the system

2. **Service Architecture**: 21 Core Services + Adapter Services ✅
   - Graph Services (6): memory, config, telemetry, audit, incident_management, tsdb_consolidation
   - Infrastructure Services (7): time, shutdown, initialization, authentication, resource_monitor, database_maintenance, secrets
   - Governance Services (4): wise_authority, adaptive_filter, visibility, self_observation
   - Runtime Services (3): llm, runtime_control, task_scheduler
   - Tool Services (1): secrets_tool
   - **Note**: pattern_analysis_loop and identity_variance_monitor are sub-services within self_observation
   - **Adapter Services** (added at runtime):
     - CLI: 1 service (CLIAdapter)
     - API: 3 services (APICommunicationService, APIRuntimeControlService, APIToolService)
     - Discord: 3 services (Communication + WiseAuthority via DiscordAdapter, DiscordToolService)
   - **Total at runtime**: 22 (CLI), 24 (API), 24 (Discord)

3. **API v1.0**: Fully Operational
   - All 78 endpoints implemented and tested across 12 modules
   - 100% test pass rate with comprehensive coverage ✅
   - Role-based access control (OBSERVER/ADMIN/AUTHORITY/SYSTEM_ADMIN)
   - Emergency shutdown with Ed25519 signatures
   - Default dev credentials: admin/ciris_admin_password
   - WebSocket support for real-time streaming
   - Runtime control service fully integrated
   - Extended system management endpoints:
     - Processing queue status and single-step debugging
     - Service health monitoring and circuit breaker management
     - Service priority and selection strategy configuration
     - Processor state information (6 cognitive states)
   - Complete TypeScript SDK with 78+ methods
   - No TODO comments or stub implementations

4. **Typed Graph Node System**
   - 11 active TypedGraphNode classes with full validation
   - Automatic type registration via node registry
   - Clean serialization pattern with to_graph_node()/from_graph_node()
   - All nodes include required metadata fields

5. **Graph-Based Telemetry**
   - All telemetry flows through memory graph
   - Real-time metrics via memorize_metric()
   - 6-hour consolidation for long-term storage
   - Full resource tracking with model-specific pricing

6. **Clean Architecture**
   - Protocol-first design with clear interfaces
   - Services separated by concern
   - No circular dependencies
   - All logic under `logic/` directory
   - SelfConfiguration renamed to SelfObservation (complete refactor)

7. **Test Suite**
   - 1,180+ tests with Docker-based CI/CD
   - Background test runner for development

## Architecture Overview

### Message Bus Architecture (6 Buses)

Buses enable multiple providers for scalability:

**Bussed Services**:
- CommunicationBus → Multiple adapters (Discord, API, CLI)
- MemoryBus → Multiple graph backends (Neo4j, ArangoDB, in-memory)
- LLMBus → Multiple LLM providers (OpenAI, Anthropic, local models)
- ToolBus → Multiple tool providers from adapters
- RuntimeControlBus → Multiple control interfaces
- WiseBus → Multiple wisdom sources

**Direct Call Services**:
- All Graph Services (except memory)
- Core Services: secrets
- Infrastructure Services (except wise_authority)
- All Special Services

### Service Registry Usage

Only for multi-provider services:
1. **LLM** - Multiple providers
2. **Memory** - Multiple graph backends
3. **WiseAuthority** - Multiple wisdom sources
4. **RuntimeControl** - Adapter-provided only

### Cognitive States (6)
- **WAKEUP** - Identity confirmation
- **WORK** - Normal task processing
- **PLAY** - Creative mode
- **SOLITUDE** - Reflection
- **DREAM** - Deep introspection
- **SHUTDOWN** - Graceful termination

## Development Tools

### Grace - Sustainable Development Companion

Grace is your intelligent pre-commit gatekeeper and development assistant that ensures sustainable coding practices:

```bash
# Quick status check
python -m tools.grace status           # Current session, health, CI status

# CI/CD Monitoring (CRITICAL for Claude)
python -m tools.grace ci               # Current branch CI + PR summary (10min throttle)
python -m tools.grace ci prs           # All PRs with conflict/block detection
python -m tools.grace ci builds        # Build & Deploy status across branches
python -m tools.grace ci hints         # Common CI failure hints & existing schemas

# Pre-commit assistance
python -m tools.grace precommit        # Detailed pre-commit status and fixes
python -m tools.grace fix              # Auto-fix pre-commit issues

# Session management
python -m tools.grace morning          # Morning check-in
python -m tools.grace pause            # Save context before break
python -m tools.grace resume           # Resume after break
python -m tools.grace night            # Evening choice point

# Deployment & incidents
python -m tools.grace deploy           # Check deployment status
python -m tools.grace incidents        # Check production incidents

# Short forms: s, m, p, r, n, d, c, pc, f, i
```

**Grace Philosophy:**
- **Be strict about safety, gentle about style** - Blocks only critical issues (syntax errors, security)
- **Progress over perfection** - Quality issues are reminders, not blockers
- **Sustainable pace** - Tracks work sessions and encourages breaks

**Pre-commit Integration:**
Grace is the primary pre-commit hook. It:
1. Auto-formats with black and isort
2. Blocks critical issues (syntax, merge conflicts, secrets)
3. Reports quality issues as gentle reminders
4. Runs all checks concurrently for speed

### CRITICAL CI Guidance for Claude (You!)

**YOUR BAD HABITS TO STOP:**
1. **Creating new Dict[str, Any]** - A schema already exists. Always.
2. **Creating NewSchemaV2** - The original schema is fine. Use it.
3. **Checking CI every 30 seconds** - CI takes 12-15 minutes. Check every 10 minutes (600000ms).
4. **Making "temporary" helper classes** - They're never temporary. Use existing schemas.
5. **Creating elaborate abstractions** - Simple existing patterns work better.

**BEFORE CREATING ANY NEW TYPE:**
```bash
# ALWAYS search first:
grep -r "class.*YourThingHere" --include="*.py"
# The schema already exists. Use it.
```

### Schemas That Already Exist (Stop Recreating!)

- `AuditEventData` - ALL audit events
- `ServiceMetrics` - ALL metrics
- `SystemSnapshot` - System state
- `ProcessingQueueItem` - Queue items
- `ActionResponse` - Handler responses
- `ThoughtSchema` - Thoughts
- `GuidanceRequest/Response` - WA guidance

## Current Status (January 2025)

### Completed ✅
- 82 API endpoints fully operational
- Complete type safety (zero Dict[str, Any])
- 21 core services + adapter services
- Production deployment at agents.ciris.ai
- 1,180+ tests with Docker CI/CD
- DSAR compliance and transparency feeds
- Book VI stewardship implementation

### In Progress 🚧
- Wisdom Extension System (FSD-019)
- Test coverage improvement (currently 54%, target 80%)
- CIRISManager canary deployments

## Service Architecture

### 21 Core Services

**Graph Services (6):**
memory, config, telemetry, audit, incident_management, tsdb_consolidation

**Infrastructure Services (7):**
time, shutdown, initialization, authentication, resource_monitor, database_maintenance, secrets

**Governance Services (4):**
wise_authority, adaptive_filter, visibility, self_observation

**Runtime Services (3):**
llm, runtime_control, task_scheduler

**Tool Services (1):**
secrets_tool

### Message Buses (6)

- **CommunicationBus** → Multiple adapters
- **MemoryBus** → Multiple graph backends
- **LLMBus** → Multiple LLM providers
- **ToolBus** → Multiple tool providers
- **RuntimeControlBus** → Multiple control interfaces
- **WiseBus** → Multiple wisdom sources *(FOCUS AREA)*

## Development Workflow

### Grace - Your Development Companion

```bash
# Daily workflow
python -m tools.grace morning          # Start day
python -m tools.grace status           # Check health
python -m tools.grace precommit        # Before commits
python -m tools.grace night            # End day

# CI monitoring (WAIT 10 MINUTES between checks!)
python -m tools.grace_shepherd status  # Check CI
python -m tools.grace_shepherd wait    # Monitor CI
```

### Testing

```bash
# Docker-based testing (preferred)
python -m tools.test_tool test tests/
python -m tools.test_tool status
python -m tools.test_tool results

# Coverage analysis
python -m tools.quality_analyzer       # Find gaps
python -m tools.sonar_tool analyze     # SonarCloud metrics
```

### Version Management

```bash
# ALWAYS bump version after significant changes
python tools/bump_version.py patch     # Bug fixes
python tools/bump_version.py minor     # New features
python tools/bump_version.py major     # Breaking changes
```

## Critical URLs & Paths

### Production
- **Main**: https://agents.ciris.ai
- **API**: https://agents.ciris.ai/api/datum/v1/
- **OAuth**: https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback

### Repository Structure
```
CIRISAgent/
├── ciris_engine/         # Core engine
│   ├── logic/           # Business logic
│   ├── schemas/         # Pydantic models
│   └── protocols/       # Service interfaces
├── FSD/                 # Functional specifications
├── tools/               # Development tools
└── tests/               # Test suite
```

### Separate Repositories (LIABILITY ISOLATION)
```
CIRISMedical/            # PRIVATE - Medical implementation
└── NO medical code in main repo
```

## Debugging Best Practices

### The Golden Rule
**ALWAYS check incidents_latest.log FIRST:**
```bash
docker exec container tail -n 100 /app/logs/incidents_latest.log
```

### Debug Workflow
1. Check incidents log
2. Use debug_tools.py for traces
3. Verify with audit trail
4. Test incrementally

### Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Dict[str, Any] error | Schema already exists - search for it |
| CI failing | Wait 10 minutes, check SonarCloud |
| OAuth not working | Check callback URL format |
| Service not found | Check ServiceRegistry capabilities |
| WA deferral failing | Check WiseBus broadcast logic |

## Command Timeouts

Default: 2 minutes (120000ms)
Maximum: 10 minutes (600000ms)

```bash
# Long-running commands need timeout parameter
gh run watch --repo CIRISAI/CIRISAgent  # timeout: 600000ms
python -m pytest tests/                 # timeout: 300000ms
```

## Important Reminders

1. **OAuth Format**: `/v1/auth/oauth/{agent_id}/{provider}/callback`
2. **Default Auth**: admin/ciris_admin_password (dev only)
3. **Service Count**: 21 core services (complete, don't add more)
4. **No Service Creates Services**: Only ServiceInitializer
5. **Version After Changes**: Always bump version
6. **Medical Prohibition**: Zero medical code in main repo
7. **Check Existing Schemas**: They already exist

## Quality Standards

- **Type Safety**: Zero Dict[str, Any]
- **Test Coverage**: Target 80% (currently 54%)
- **Response Time**: <1s API responses
- **Memory**: 4GB RAM maximum
- **Security**: Ed25519 signatures throughout

## Getting Help

- **Issues**: https://github.com/CIRISAI/CIRISAgent/issues
- **CI Status**: `python -m tools.grace_shepherd status`
- **Coverage**: `python -m tools.quality_analyzer`
- **Incidents**: Check container logs first

---

*Remember: The schema you're about to create already exists. Search for it first.*
