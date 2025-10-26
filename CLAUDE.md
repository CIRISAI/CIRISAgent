# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the CIRIS codebase.

## 🎯 CURRENT FOCUS: Production Quality & Stability

**Goal**: Maintain production-grade quality, stability, and test coverage

### Priority Areas

1. **Test Coverage** - Target 80%
   - Focus on critical path services
   - Integration tests for complex flows
   - Edge case coverage

2. **Bug Fixes & Stability**
   - Address any production issues from agents.ciris.ai
   - Fix flaky tests
   - Resolve memory leaks or performance issues

3. **Documentation & Code Quality**
   - Update outdated documentation
   - Remove dead code and TODOs
   - Ensure all APIs are properly documented

4. **Security Hardening**
   - Review authentication flows
   - Audit secret handling
   - Validate input sanitization

### ⚠️ CRITICAL: Medical Domain Prohibition

**NEVER implement in main repo:**
- Medical/health capabilities
- Diagnosis/treatment logic
- Patient data handling
- Clinical decision support

**These are BLOCKED at the bus level.** See `PROHIBITED_CAPABILITIES` in `wise_bus.py`.

---

## Project Overview

CIRIS (Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude) is an ethical AI platform:
- **Production**: Discord moderation + API at agents.ciris.ai
- **Architecture**: 22 core services, 6 message buses, strict type safety
- **Philosophy**: No Untyped Dicts, No Bypass Patterns, No Exceptions
- **Target**: 4GB RAM, offline-capable deployment

## Core Philosophy: Type Safety First

🚧 **PROGRESS: Minimizing `Dict[str, Any]` usage in production code**

### The Three Rules

1. **No Untyped Dicts**: All data uses Pydantic models instead of `Dict[str, Any]`
2. **No Bypass Patterns**: Every component follows consistent rules and patterns
3. **No Exceptions**: No special cases, emergency overrides, or privileged code paths

### Before Creating ANY New Type

```bash
# ALWAYS search first:
grep -r "class.*YourThingHere" --include="*.py"
# The schema already exists. Use it.
```

### Type Safety Best Practices

1. **Replace Untyped Dicts with Pydantic Models**
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

4. **Avoid Bypass Patterns - Follow Consistent Rules**
   ```python
   # ❌ Bad - Special bypass for "emergency"
   if emergency_mode:
       return process_without_validation(data)

   # ✅ Good - Same validation rules apply everywhere
   validated_data = validate_request(data)
   return process_validated_data(validated_data)
   ```

5. **Use Enums for Constants**
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

6. **Enhanced Mypy Configuration**
   - `strict = True` enabled in mypy.ini with additional strictness flags
   - `disallow_any_explicit = True` temporarily disabled (too many false positives)
   - Minimal Dict[str, Any] usage remaining, none in critical code paths
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
3. **Checking CI too frequently** - CI takes time to complete. Check periodically.
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


## Service Architecture

### 22 Core Services

**Graph Services (7):**
memory, consent, config, telemetry, audit, incident_management, tsdb_consolidation

**Infrastructure Services (4):**
authentication, resource_monitor, database_maintenance, secrets

**Lifecycle Services (4):**
initialization, shutdown, time, task_scheduler

**Governance Services (4):**
wise_authority, adaptive_filter, visibility, self_observation

**Runtime Services (2):**
llm, runtime_control

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

# Direct pytest (ALWAYS use -n 16 for parallel execution with 5+ minute timeout)
pytest -n 16 tests/ --timeout=300

# Coverage analysis
python -m tools.quality_analyzer       # Find gaps

# SonarCloud quality analysis
python -m tools.analysis.sonar quality-gate  # PR + main quality gate status (IMPORTANT!)
python -m tools.analysis.sonar status        # Main branch status only
python -m tools.analysis.sonar_tool status   # Alternative main branch status
```

### QA Runner - API Test Suite

The CIRIS QA Runner provides comprehensive API testing with automatic server lifecycle management:

```bash
# Run all tests (default) - QA runner manages server lifecycle
python -m tools.qa_runner                # Run all test modules

# Quick module testing
python -m tools.qa_runner auth          # Authentication tests
python -m tools.qa_runner agent         # Agent interaction tests
python -m tools.qa_runner memory        # Memory system tests
python -m tools.qa_runner telemetry     # Telemetry & metrics tests
python -m tools.qa_runner system        # System management tests
python -m tools.qa_runner audit         # Audit trail tests
python -m tools.qa_runner tools         # Tool integration tests
python -m tools.qa_runner guidance      # Wise Authority guidance tests
python -m tools.qa_runner handlers      # Message handler tests
python -m tools.qa_runner filters       # Adaptive filtering tests (36 tests)
python -m tools.qa_runner sdk           # SDK compatibility tests
python -m tools.qa_runner streaming     # H3ERE pipeline streaming tests

# Comprehensive test suites
python -m tools.qa_runner extended_api  # Extended API coverage (24 tests)
python -m tools.qa_runner api_full      # Complete API test suite (24 tests)

# Full verbose output for debugging
python -m tools.qa_runner <module> --verbose

# Multi-backend testing (sequential by default)
python -m tools.qa_runner auth --database-backends sqlite postgres

# Parallel backend testing (run SQLite and PostgreSQL simultaneously)
python -m tools.qa_runner auth --database-backends sqlite postgres --parallel-backends
```

**QA Runner Features:**
- 🤖 **Automatic Lifecycle Management** - Starts/stops API server automatically
- 🔑 **Smart Token Management** - Auto re-authentication after logout/refresh tests
- ⚡ **Fast Execution** - Most modules complete quickly
- 🧪 **Comprehensive Coverage** - Authentication, API endpoints, streaming, filtering
- 🔍 **Detailed Reporting** - Success rates, duration, failure analysis
- 🚀 **Production Ready** - Validates all critical system functionality
- 🔄 **Multi-Backend Support** - Test against SQLite and PostgreSQL (sequential or parallel)

**IMPORTANT - Server Lifecycle:**
- QA runner automatically starts and stops the API server
- DO NOT manually start the server before running QA tests
- If you have a server already running, kill it first: `pkill -f "python main.py --adapter api"`
- Use `--no-auto-start` only if you need to debug with an existing server

### Testing API Locally

```bash
# 1. Start API server with mock LLM
python main.py --adapter api --mock-llm --port 8000

# 2. Get auth token (in another terminal)
TOKEN=$(curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ciris_admin_password"}' \
  2>/dev/null | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

# 3. Check telemetry (should show 35/35 services when fully working)
curl -X GET http://localhost:8000/v1/telemetry/unified \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null | \
  python -c "import json,sys; d=json.load(sys.stdin); print(f'{d[\"services_online\"]}/{d[\"services_total\"]} services healthy')"

# 4. List unhealthy services
curl -X GET http://localhost:8000/v1/telemetry/unified \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null | \
  python -c "import json,sys; d=json.load(sys.stdin); print('Unhealthy:', [k for k,v in d['services'].items() if not v['healthy']])"

# 5. Interactive agent test
curl -X POST http://localhost:8000/v1/agent/interact \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello, how are you?"}' 2>/dev/null | python -m json.tool
```

### Version Management

```bash
# ALWAYS bump version after significant changes
python tools/dev/bump_version.py patch     # Bug fixes
python tools/dev/bump_version.py minor     # New features
python tools/dev/bump_version.py major     # Breaking changes
```

## Critical URLs & Paths

### Production
- **Main**: https://agents.ciris.ai
- **API**: https://agents.ciris.ai/api/datum/v1/
- **OAuth**: https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback

### Production Server Access
- **SSH**: `ssh -i ~/.ssh/ciris_deploy root@108.61.119.117`
- **Agent Locations**: `/opt/ciris/agents/`
- **Common Commands**:
  ```bash
  # Find agent containers
  cd /opt/ciris/agents && ls -la

  # Check specific agent status
  cd /opt/ciris/agents/echo-speculative-4fc6ru
  docker-compose ps

  # View agent logs
  docker-compose logs --tail=50 echo-speculative-4fc6ru

  # Execute commands in container
  docker-compose exec echo-speculative-4fc6ru python -c "print('hello')"

  # Check database files
  docker-compose exec echo-speculative-4fc6ru find /app -name '*.db'
  ```

**Service Tokens** (for API access):
- Use format: `Authorization: Bearer service:TOKEN_VALUE`
- Manager tokens found in agent deployment configs
- Example: `curl -H "Authorization: Bearer service:abc123..." https://agents.ciris.ai/api/agent-id/v1/system/health`

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
| CI failing | Wait for CI to complete, check SonarCloud |
| OAuth not working | Check callback URL format |
| Service not found | Check ServiceRegistry capabilities |
| WA deferral failing | Check WiseBus broadcast logic |

## Command Timeouts

Long-running commands may need timeout parameters for CI operations and comprehensive test runs.

## Important Reminders

1. **OAuth Format**: `/v1/auth/oauth/{agent_id}/{provider}/callback`
2. **Default Auth**: admin/ciris_admin_password (dev only)
3. **Service Count**: 22 core services (complete, don't add more)
4. **No Service Creates Services**: Only ServiceInitializer
5. **Version After Changes**: Always bump version
6. **Medical Prohibition**: Zero medical code in main repo
7. **Check Existing Schemas**: They already exist
8. **NEVER PUSH DIRECTLY TO MAIN**: Always create a branch, bump version, NO merge to main without explicit permission

## Quality Standards

- **Type Safety**: Minimal Dict[str, Any] usage
- **Test Coverage**: Target 80%
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
