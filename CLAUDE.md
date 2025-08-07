# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

CIRIS is an ethical AI platform designed for progressive deployment:
- **Current Production**: Discord community moderation + API access
- **Architecture**: 21 core services, 6 buses, strict type safety
- **Target**: Resource-constrained environments (4GB RAM, offline-capable)
- **Philosophy**: Start simple (Discord bot), scale to critical (healthcare triage)

## Core Philosophy: No Dicts, No Strings, No Kings

The CIRIS codebase follows strict typing principles:

- **No Dicts**: ✅ ACHIEVED! Zero `Dict[str, Any]` in production code. All data uses Pydantic models/schemas.
- **No Strings**: Avoid magic strings. Use enums, typed constants, and schema fields instead.
- **No Kings**: No special cases or bypass patterns. Every component follows the same typed, validated patterns.
- **No Backwards Compatibility**: The codebase moves forward only. No legacy support code.

This ensures type safety, validation, and clear contracts throughout the system.

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

## Current Status (August 2025)

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
python -m tools.grace status           # Current session, health, reminders

# Pre-commit assistance
python -m tools.grace precommit        # Detailed pre-commit status and fixes

# Session management
python -m tools.grace morning          # Morning check-in
python -m tools.grace pause            # Save context before break
python -m tools.grace resume           # Resume after break
python -m tools.grace night            # Evening choice point

# Deployment monitoring
python -m tools.grace deploy           # Check deployment status
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

### Essential Tools

```bash
# Version Management (ALWAYS bump version after significant changes)
python tools/bump_version.py patch     # Bug fixes (1.1.X)
python tools/bump_version.py minor     # New features (1.X.0)
python tools/bump_version.py major     # Breaking changes (X.0.0)
python tools/bump_version.py build     # Build increment only (1.1.4-betaX)

# SonarCloud Analysis
python tools/sonar.py quality-gate      # Check quality gate status
python tools/sonar.py hotspots         # List security hotspots
python tools/sonar.py coverage --new-code  # Coverage metrics
python tools/sonar.py list --severity CRITICAL  # List issues

# Background Test Runner
python tools/test_runner.py start --coverage  # Start tests in Docker
python tools/test_runner.py status     # Check progress
python tools/test_runner.py logs       # View output
python tools/test_runner.py results    # Summary when done

# Test Tool (Docker-based testing)
python -m tools.test_tool test tests/  # Run tests in Docker
python -m tools.test_tool status       # Check test progress
python -m tools.test_tool results      # Get test results

# Debug Tools (run inside container)
docker exec <container> python debug_tools.py  # Interactive debugging
```

### Critical: Bash Command Timeout

**The default Bash tool timeout is 2 minutes (120 seconds).** For long-running commands like CI/CD monitoring, Docker builds, or test suites, use the timeout parameter:

```bash
# Example: Monitor CI/CD with 10-minute timeout
gh run watch --repo CIRISAI/CIRISAgent  # timeout: 600000ms

# Example: Run full test suite with 5-minute timeout
python -m pytest tests/  # timeout: 300000ms

# Maximum allowed timeout is 600000ms (10 minutes)
```

This is crucial for commands that:
- Monitor CI/CD workflows
- Build Docker images
- Run comprehensive test suites
- Watch for deployment completions
- Execute database migrations

### Local Development Setup
```bash
# Docker compose files in docker/
docker compose -f docker/docker-compose-api-discord-mock.yml up -d

# GUI development
cd CIRISGUI/apps/agui && npm run dev  # http://localhost:3000

# CLI mode with mock LLM
python main.py --mock-llm --timeout 15 --adapter cli
```

### API Authentication
```python
# Default development credentials (DEV ONLY - disabled in production)
# Production uses OAuth exclusively via Discord/Google
username = "admin"
password = "ciris_admin_password"

# Authentication flow for API v1:
# 1. Login to get token
response = requests.post(
    "http://localhost:8080/v1/auth/login",
    json={"username": "admin", "password": "ciris_admin_password"}
)
token = response.json()["access_token"]

# 2. Use token in Authorization header
headers = {"Authorization": f"Bearer {token}"}
response = requests.post(
    "http://localhost:8080/v1/agent/interact",
    headers=headers,
    json={"message": "Hello", "channel_id": "api_0.0.0.0_8080"}
)

# Note: Some endpoints accept Bearer admin:ciris_admin_password directly
# Example: GET /v1/system/health -H "Authorization: Bearer admin:ciris_admin_password"
```

## Key Principles

1. **Service Count is Complete**: 21 core services
2. **No Service Creates Services**: Only ServiceInitializer creates services
3. **Type Safety First**: All data uses Pydantic schemas
4. **Protocol-Driven**: All services implement clear protocols
5. **Forward Only**: No backwards compatibility
6. **Version Everything**: Always bump version after significant changes

## Why This Architecture?

- **SQLite + Threading**: Offline-first for remote deployments
- **23 Services**: Modular for selective deployment
- **Graph Memory**: Builds local knowledge base
- **Mock LLM**: Critical for offline operation
- **Resource Constraints**: Designed for 4GB RAM environments

## Agent Creation Ceremony

CIRIS agents are not simply deployed - they are created through a formal ceremony:

### Core Concepts
- **Collaborative Creation**: Human + Facilitating Agent + Wise Authority
- **Immutable Lineage**: Every agent knows who created it and why
- **Ethical Foundation**: Purpose, justification, and ethical considerations required
- **WA Approval**: Ed25519 signature required for all creations

### Creation Flow
1. Human prepares proposal (name, purpose, justification, ethics)
2. Selects template (echo, teacher, etc.) from `ciris_templates/`
3. Wise Authority reviews and signs
4. Ceremony creates:
   - Identity root in graph database
   - Immutable lineage record
   - Docker container configuration
5. Agent awakens with knowledge of its creation

### Key Files
- **Ceremony Docs**: `docs/AGENT_CREATION_CEREMONY.md`
- **Technical Guide**: `docs/technical/IMPLEMENTING_CREATION_CEREMONY.md`
- **Quick Start**: `docs/CREATION_CEREMONY_QUICKSTART.md`
- **Templates**: `ciris_templates/` directory
- **Schemas**: `ciris_engine/schemas/runtime/extended.py`

### Important Notes
- Creation is permanent - identities are immutable
- Changes to core identity require WA approval
- Every agent maintains its creation ceremony record
- Templates are starting points, not fixed configurations


### Debug Tool Usage

The `debug_tools.py` provides essential commands for troubleshooting production issues:

#### Available Commands
```python
# Show recent service correlations with trace hierarchy
show_correlations(limit=20)           # Show last 20 correlations
show_correlations(trace_id="...")     # Show all correlations for a specific trace

# List recent unique trace IDs with span counts
list_traces(limit=20)                 # Show last 20 traces

# Show thoughts by status
show_thoughts(status='PENDING')       # Show pending thoughts
show_thoughts(status='PROCESSING')    # Show processing thoughts
show_thoughts(status='COMPLETED')     # Show completed thoughts

# Show tasks and their thoughts
show_tasks(limit=10)                  # Show recent tasks with thought counts

# Show handler metrics
show_handler_metrics()                # Display handler execution counts and timings
```

#### Debug Process for Handler Issues
1. **Check container incidents log**:
   ```bash
   docker exec container0 tail -n 100 /app/logs/incidents_latest.log
   ```

2. **Use debug tool to analyze traces**:
   ```bash
   docker exec container0 python debug_tools.py
   ```
   ```python
   # In the Python shell:
   from debug_tools import *

   # Find recent traces
   list_traces(limit=10)

   # Examine a specific trace hierarchy
   show_correlations(trace_id="your-trace-id")

   # Check for stuck thoughts
   show_thoughts(status='PENDING')
   show_thoughts(status='PROCESSING')
   ```

3. **Understanding trace hierarchies**:
   - Each API request creates a root trace
   - Handlers create child spans under the trace
   - Parent-child relationships show execution flow
   - Timing data helps identify bottlenecks

4. **Common debugging patterns**:
   - **"Thought not found" errors**: Check if thoughts are being completed before creating follow-ups
   - **Stuck thoughts**: Look for PENDING/PROCESSING thoughts that aren't progressing
   - **Handler failures**: Use trace hierarchy to see which handler failed
   - **Performance issues**: Check handler metrics and trace timings

### API v1.0 Complete Endpoint Reference

The API provides 78 endpoints across 12 modules:

1. **Agent** (`/v1/agent/*`) - 7 endpoints
   - `POST /interact` - Send message to agent
   - `GET /status` - Agent status
   - `GET /identity` - Agent identity
   - `GET /history` - Conversation history

2. **System** (`/v1/system/*`) - 18 endpoints
   - Runtime control: pause/resume/state/single-step/queue
   - Service management: health/priorities/circuit-breakers/selection-logic
   - Adapter management: list/get/register/unregister/reload
   - Resource monitoring: health/resources/time/processors

3. **Memory** (`/v1/memory/*`) - 6 endpoints
   - CRUD operations plus query/timeline/recall

4. **Telemetry** (`/v1/telemetry/*`) - 8 endpoints
   - Metrics, logs, traces, resources, queries

5. **Config** (`/v1/config/*`) - 5 endpoints
   - Full configuration management

6. **Audit** (`/v1/audit/*`) - 5 endpoints
   - Audit trail with search/export/verify

7. **Auth** (`/v1/auth/*`) - 4 endpoints
   - Login/logout/refresh/current user

8. **Wise Authority** (`/v1/wa/*`) - 5 endpoints
   - Deferrals, guidance, permissions

9. **Emergency** (`/emergency/*`) - 2 endpoints
   - Bypass auth for emergency shutdown

10. **WebSocket** (`/v1/ws`) - Real-time updates

11. **OpenAPI** (`/openapi.json`) - API specification

### SDK Implementation

Complete TypeScript SDK with:
- 78+ methods across 9 resource modules
- Full type safety with TypeScript
- Automatic token management
- WebSocket support
- No stubs or TODOs - 100% implemented

Example usage:
```typescript
const client = new CIRISClient({ baseURL: 'http://localhost:8080' });
await client.auth.login('admin', 'ciris_admin_password');
const status = await client.system.getServiceHealthDetails();
const queue = await client.system.getProcessingQueueStatus();
```

## Critical Debugging Guidelines

### Container Incidents Log
**ALWAYS check incidents_latest.log FIRST** - This is your primary debugging tool:
```bash
docker exec <container> tail -n 100 /app/logs/incidents_latest.log
```

**NEVER restart the container until everything in incidents_latest.log has been understood and addressed** - These are opportunities to discover flaws in the software. Each error message is valuable debugging information.

### Root Cause Analysis (RCA) Mode

When debugging issues, especially "smoking guns", follow this RCA methodology:

1. **Preserve the Crime Scene**: Don't clean up stuck tasks or errors immediately - they reveal system behavior
2. **Use Debug Tools First**:
   ```python
   docker exec container python debug_tools.py
   # Then explore with commands like:
   show_thoughts(status='PENDING')
   show_correlations(trace_id="...")
   ```
3. **Trace the Full Flow**: Follow data through the entire pipeline before making changes
4. **Test Incrementally**: Add debug logging, rebuild, test - small steps reveal root causes
5. **Question Assumptions**: "Active observations" vs "passive observations" - challenge the design

**Example RCA Success**: ObserveHandler Issue
- **Symptom**: 35 tasks stuck in ACTIVE state
- **Initial Instinct**: Clean them up ❌
- **RCA Approach**:
  1. Used debug_tools to examine stuck tasks
  2. Found they all had observation thoughts with no follow-ups
  3. Added debug logging to trace the flow
  4. Discovered mock LLM defaulted to `active=False`
  5. Root cause: Passive observations don't create follow-ups
  6. Solution: Remove passive observation capability entirely

### The Value of Errors

**Errors are not failures - they are insights into system behavior**:
- A stuck task reveals a missing state transition
- A crash exposes a race condition
- Silent failures show where logging is needed
- Unexpected behavior challenges our mental model

**Never suppress errors without understanding them** - They are the system trying to tell you something important.

### Mock LLM Behavior
The mock LLM may not always respond with a message - **this is by design**:
- **DEFER**: Task is deferred, no message sent back
- **REJECT**: Request is rejected, no message sent back
- **TASK_COMPLETE**: Task marked complete, no message sent back
- **OBSERVE**: Observation registered, no immediate message

This is normal behavior. You can use audit logs or debug tools to verify the action was performed correctly.

### API Authentication with curl
```bash
# 1. Login to get token
curl -X POST http://localhost:8080/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "ciris_admin_password"}'

# 2. Use the token (Note: JSON requires proper escaping)
curl -X POST http://localhost:8080/v1/agent/interact \
  -H "Authorization: Bearer <your-token-here>" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"\$speak Hello!\", \"channel_id\": \"api_SYSTEM_ADMIN\"}"
```

### Mock LLM Command Extraction
The mock LLM extracts commands from user context in this order:
1. **Passive Observation**: Looks for `"You observed @<author> (ID: <id>) in channel <channel> say: <message>"`
2. **ASPDMA Messages**: Extracts from `"Original Thought:"` field
3. **Command Detection**: Checks if message starts with `$`
4. **Context Storage**: Adds `forced_action:<action>` and `action_params:<params>` to context

### Debugging Workflow
1. **Check Health**: `curl http://localhost:8080/v1/system/health`
2. **Check Incidents**: `docker exec <container> tail /app/logs/incidents_latest.log`
3. **Use Debug Tools**: `docker exec <container> python debug_tools.py`
4. **Verify Actions**: Check traces and correlations for handler execution
5. **Never Assume**: Always verify mock LLM behavior matches expectations

### Container Best Practices
- **Always rebuild**: `docker-compose -f docker-compose-api-mock.yml build --no-cache`
- **Check uptime**: If health shows hours when just started, rebuild needed
- **Parallel testing**: Use multiple containers (ports 8080-8089)
- **Incident logs are gold**: Every error reveals system behavior

### Command Output Best Practices
**🚨 CRITICAL: NEVER pipe output to grep or jq without understanding the output format first 🚨**

**Why this matters**:
1. **Error messages look like data**: Many tools output errors as JSON or structured text that can be parsed incorrectly
2. **Silent failures**: `jq` returns null or empty when parsing fails, hiding the actual error
3. **Lost debugging info**: Piping immediately loses HTTP status codes, headers, and error details
4. **Cascading confusion**: Wrong assumptions about output format lead to wrong conclusions about system state
5. **Wasted debugging time**: You'll spend hours chasing ghosts when the real error was hidden by jq

**GOLDEN RULE**: Always run the command WITHOUT pipes first, examine the output, THEN add parsing.

**Best practices**:
```bash
# ❌ Bad - Assumes output is JSON without checking
curl -s https://api.example.com/data | jq '.result'

# ✅ Good - Check output first, then parse
response=$(curl -s -w "\nHTTP_STATUS:%{http_code}" https://api.example.com/data)
echo "$response"  # See what we actually got
# Then parse if it's valid JSON

# ❌ Bad - Assumes field exists
docker inspect container | jq -r '.[0].Image'

# ✅ Good - Check structure first
docker inspect container  # See the actual structure
# Then extract fields safely

# ❌ Bad - Grep on unknown output
some_command | grep -i error

# ✅ Good - Examine output first
some_command  # See all output
# Then search for specific patterns

# ❌ WORST - Chaining pipes without checking
curl -s http://localhost:8080/v1/system/health | jq -r '.status' | grep healthy

# ✅ BEST - Step by step verification
# Step 1: Check raw response
curl -s http://localhost:8080/v1/system/health
# Step 2: If JSON, check with jq
curl -s http://localhost:8080/v1/system/health | jq '.'
# Step 3: Extract specific field only after confirming structure
curl -s http://localhost:8080/v1/system/health | jq -r '.status'
```

**Common mistakes that waste hours**:
- Parsing HTML as JSON (e.g., Cloudflare 502 pages, web server error pages)
- Assuming API errors return JSON (many return plain text or HTML)
- Using `jq` on null/empty responses (hides connection failures)
- Grepping for patterns that don't exist in the actual output
- Container not running but jq hides the "connection refused" error
- Service returning 500 error with HTML but jq shows null

### Production Deployment - agents.ciris.ai

**Deployment Philosophy**:
CIRIS deployment follows a clean, agent-respecting model:
- **CD builds and notifies**: GitHub Actions builds images and calls CIRISManager API
- **CIRISManager orchestrates**: Handles canary deployment, respects agent autonomy
- **Agents decide**: Each agent can accept, defer, or reject updates via graceful shutdown
- **No staged containers**: Docker's `restart: unless-stopped` handles the swap

**Clean CD Model (Implemented August 2025)**:
```yaml
# GitHub Actions makes ONE API call:
curl -X POST https://agents.ciris.ai/manager/v1/updates/notify \
  -H "Authorization: Bearer ${{ secrets.DEPLOY_TOKEN }}" \
  -d '{"agent_image": "ghcr.io/cirisai/ciris-agent:latest", "strategy": "canary"}'
```

That's it. CIRISManager handles everything else:
1. Notifies agents based on deployment strategy (canary/immediate/manual)
2. Each agent receives update notification at `/v1/system/update`
3. Agents respond: accept (TASK_COMPLETE), defer (DEFER), or reject (REJECT)
4. CIRISManager respects these decisions
5. Docker automatically swaps containers on graceful exit

**Server Access**:
- **IP**: 108.61.119.117 (Cloudflare proxied - must use IP for SSH, not domain)
- **SSH Key**: `~/.ssh/ciris_deploy`
- **User**: root
- **Example**: `ssh -i ~/.ssh/ciris_deploy root@108.61.119.117`

**Repository Locations**:
- **CIRISAgent**: `/home/ciris/CIRISAgent`
- **CIRISManager**: `/opt/ciris-manager` (separate repo)
- **Upstream**: CIRISAI/CIRISAgent (not personal forks)

**Deployment Process**:
1. **Create PR**: `gh pr create --repo CIRISAI/CIRISAgent`
2. **Merge PR**: `gh pr merge <PR#> --repo CIRISAI/CIRISAgent --merge --admin`
3. **Automatic deployment**:
   - GitHub Actions builds and tests
   - Pushes images to ghcr.io
   - Notifies CIRISManager via API
   - CIRISManager orchestrates the rest

**Container Management**:
- **Restart Policy**: `restart: unless-stopped` (critical for clean swaps)
- **No staged containers**: Eliminated complexity
- **Graceful shutdown**: Agents process shutdown as a task
- **Agent autonomy**: Can defer or reject updates

**Graceful Shutdown Protocol**:
```bash
# CIRISManager calls agent's update endpoint
# Agent processes as normal task through cognitive loop
# Response determines action:
# - TASK_COMPLETE: Agent exits gracefully (exit 0)
# - DEFER: Agent continues, update scheduled for later
# - REJECT: Agent continues, update cancelled
```

**Important Environment Variables**:
- `CIRIS_API_HOST=0.0.0.0` - Required for API to bind to all interfaces
- `CIRIS_API_PORT=8080` - API port (default)

**Current Production Setup**:
- Multiple agents managed by CIRISManager
- GUI supports dual-mode deployment (standalone or managed)
- CIRISManager handles all nginx routing
- OAuth shared across agents via mounted volumes
- Canary deployments protect agent stability

**Monitoring**:
```bash
# Check CIRISManager status
curl http://localhost:8888/manager/v1/status

# Check agent health
curl http://localhost:8080/v1/system/health

# View deployment status
curl http://localhost:8888/manager/v1/updates/status

# Check incidents (always check this first!)
docker exec ciris-agent-datum tail -n 100 /app/logs/incidents_latest.log
```

**The Beauty**: One API call triggers everything. No SSH scripts, no staged containers, no manual intervention. Just clean orchestration that respects agent autonomy.


## Type Safety Best Practices

### Overview
CIRIS follows strict type safety principles to ensure code reliability and maintainability. These practices align with our "No Dicts, No Strings, No Kings" philosophy.

### Key Principles

1. **Always Use Pydantic Models**
   - Replace `Dict[str, Any]` with specific Pydantic models
   - Define clear schemas for all data structures
   - Use field validators for business logic constraints

2. **Strict MyPy Configuration**
   - Enable `strict = True` in mypy.ini
   - Run mypy checks before committing code
   - Fix type errors immediately, don't use `# type: ignore`

3. **Type-Safe Patterns**
   ```python
   # ❌ Bad - Using Dict[str, Any]
   def process_data(data: Dict[str, Any]) -> Dict[str, Any]:
       return {"result": data.get("value", 0) * 2}

   # ✅ Good - Using Pydantic models
   class ProcessInput(BaseModel):
       value: float = Field(default=0.0)

   class ProcessOutput(BaseModel):
       result: float

   def process_data(data: ProcessInput) -> ProcessOutput:
       return ProcessOutput(result=data.value * 2)
   ```

4. **API Route Type Safety**
   - Always define request/response models
   - Use FastAPI's automatic validation
   - Document models with Field descriptions

5. **Database Query Results**
   - Create typed result models for complex queries
   - Use data converters to transform raw results
   - Avoid passing raw database rows around

### Migration Guide

When encountering `Dict[str, Any]`:

1. **Identify the structure** - What fields does this dict contain?
2. **Create a Pydantic model** - Define fields with proper types
3. **Add validation** - Use validators for business rules
4. **Update signatures** - Replace Dict with the new model
5. **Test thoroughly** - Ensure backward compatibility

### Common Patterns

1. **Configuration Objects**
   ```python
   class ServiceConfig(BaseModel):
       host: str = Field(default="127.0.0.1")
       port: int = Field(default=8080, ge=1, le=65535)
       timeout: float = Field(default=30.0, gt=0)
   ```

2. **API Responses**
   ```python
   class APIResponse(BaseModel, Generic[T]):
       success: bool
       data: Optional[T] = None
       error: Optional[str] = None
   ```

3. **Event Data**
   ```python
   class EventData(BaseModel):
       event_type: str
       timestamp: datetime
       payload: BaseModel  # Specific payload model
   ```

### Tools and Automation

- **ciris_mypy_toolkit** - Run compliance analysis for type safety
- **quality_analyzer** - Cross-analyze type safety, code quality, and test coverage
- **sonar_tool** - Detailed SonarCloud analysis with AI time estimates
- **test_tool** - Docker-based test execution with automatic rebuilding
- **mypy** - Static type checking
- **pydantic** - Runtime validation
- **FastAPI** - Automatic API documentation

### Security Benefits

Type safety provides security benefits:
- Prevents injection attacks through validation
- Ensures data integrity
- Makes code behavior predictable
- Reduces attack surface

Remember: Every `Dict[str, Any]` is a potential bug. Replace them with proper types!

## Quality Analysis Tools

CIRIS includes several complementary tools for code quality analysis:

### 1. quality_analyzer
Unified analysis that cross-references multiple quality dimensions:
```bash
# Run comprehensive analysis
python -m tools.quality_analyzer

# Shows files with multiple issues (type safety + complexity + coverage)
# Generates prioritized improvement plan with AI time estimates
```

### 2. sonar_tool
Deep dive into SonarCloud metrics:
```bash
# Coverage analysis with strategic targets
python -m tools.sonar_tool analyze

# Technical debt analysis
python -m tools.sonar_tool tech-debt

# Find specific file coverage
python -m tools.sonar_tool find <pattern>
```

### 3. ciris_mypy_toolkit
Type safety and protocol compliance:
```bash
# Check protocol-module-schema alignment
python -m ciris_mypy_toolkit check-protocols

# Full compliance analysis
python -m ciris_mypy_toolkit analyze
```

### 4. test_tool
Docker-based test execution:
```bash
# Run tests in Docker with auto-rebuild
python -m tools.test_tool run tests/

# Run specific test file
python -m tools.test_tool run tests/test_api_v1.py
```

**Best Practice**: Use quality_analyzer first to identify high-priority targets, then use specialized tools for deeper analysis.
