# CIRIS Comprehensive AI Assistant Guide

**Version**: 1.2.0-beta
**Last Updated**: August 7, 2025
**Purpose**: Complete reference for AI assistants working with CIRIS codebase

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Core Philosophy](#core-philosophy)
3. [Current Status](#current-status)
4. [Architecture Overview](#architecture-overview)
5. [Service Architecture](#service-architecture)
6. [API v1.0 Complete Reference](#api-v10-complete-reference)
7. [Agent Creation Ceremony](#agent-creation-ceremony)
8. [Development Tools](#development-tools)
9. [Production Deployment](#production-deployment)
10. [Debugging Guidelines](#debugging-guidelines)
11. [Local Development](#local-development)
12. [Testing Framework](#testing-framework)
13. [Critical Commands](#critical-commands)
14. [Important URLs](#important-urls)
15. [Project Instructions (CLAUDE.md)](#project-instructions-claudemd)

---

## Executive Summary

CIRIS (Covenant-Integrated Responsible Intelligence System) is an ethical AI platform designed for progressive deployment, starting with Discord community moderation and scaling to critical applications like healthcare triage.

**Key Features:**
- 21 core services with strict type safety
- Resource-constrained design (4GB RAM, offline-capable)
- Zero attack surface architecture
- Formal agent creation ceremonies
- Book VI compliance for ethical AI

**Production Status**: Running at agents.ciris.ai with multiple agents

---

## Core Philosophy

### No Dicts, No Strings, No Kings

**ACHIEVED**: Zero `Dict[str, Any]` in production code

1. **No Dicts**: All data uses Pydantic models/schemas
2. **No Strings**: Use enums, typed constants, and schema fields
3. **No Kings**: No special cases or bypass patterns
4. **No Backwards Compatibility**: Forward-only development

### Type Safety Best Practices

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

---

## Current Status

### Major Achievements

1. **Complete Type Safety**: Zero `Dict[str, Any]` in production
2. **Service Architecture**: 21 Core + Adapter Services operational
3. **API v1.0**: 78 endpoints, 100% test coverage
4. **Typed Graph Nodes**: 11 active classes with validation
5. **Production Deployment**: agents.ciris.ai running multiple agents
6. **Book VI Compliance**: Full stewardship implementation

### Version Information
- **Current**: 1.2.0-beta "Graceful Guardian"
- **OAuth Callback**: `https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback`

---

## Architecture Overview

### 21 Core Services

**Graph Services (6):**
- memory, config, telemetry, audit, incident_management, tsdb_consolidation

**Infrastructure Services (7):**
- time, shutdown, initialization, authentication, resource_monitor, database_maintenance, secrets

**Governance Services (4):**
- wise_authority, adaptive_filter, visibility, self_observation

**Runtime Services (3):**
- llm, runtime_control, task_scheduler

**Tool Services (1):**
- secrets_tool

**Adapter Services (runtime):**
- CLI: CLIAdapter
- API: APICommunicationService, APIRuntimeControlService, APIToolService
- Discord: DiscordAdapter, DiscordToolService

### Message Bus Architecture (6 Buses)

**Bussed Services:**
- CommunicationBus → Multiple adapters
- MemoryBus → Multiple graph backends
- LLMBus → Multiple LLM providers
- ToolBus → Multiple tool providers
- RuntimeControlBus → Multiple control interfaces
- WiseBus → Multiple wisdom sources

### Cognitive States (6)
1. **WAKEUP** - Identity confirmation
2. **WORK** - Normal task processing
3. **PLAY** - Creative mode
4. **SOLITUDE** - Reflection
5. **DREAM** - Deep introspection
6. **SHUTDOWN** - Graceful termination

---

## Service Architecture

### Service Registry Pattern

Only multi-provider services use registry:
- LLM (multiple providers)
- Memory (multiple backends)
- WiseAuthority (multiple sources)
- RuntimeControl (adapter-provided)

### Service Initialization

```python
# Only ServiceInitializer creates services
initializer = ServiceInitializer(runtime)
services = await initializer.initialize_services()
```

### No Service Creates Services Rule

Services NEVER create other services. All creation happens in ServiceInitializer.

---

## API v1.0 Complete Reference

### 78 Endpoints Across 12 Modules

#### 1. Agent Module (`/v1/agent/*`)
- `POST /interact` - Send message to agent
- `GET /status` - Agent status
- `GET /identity` - Agent identity
- `GET /history` - Conversation history

#### 2. System Module (`/v1/system/*`)
Runtime control:
- `POST /pause` - Pause processing
- `POST /resume` - Resume processing
- `GET /state` - Current state
- `POST /single-step` - Single step mode
- `GET /queue` - Processing queue status

Service management:
- `GET /health` - System health
- `GET /resources` - Resource usage
- `GET /services/health` - Service health details
- `POST /services/{service}/priority` - Set priority
- `GET /circuit-breakers` - Circuit breaker status

#### 3. Memory Module (`/v1/memory/*`)
- `POST /store` - Store memory
- `GET /recall` - Recall memories
- `GET /query` - Query graph
- `DELETE /{node_id}` - Delete node

#### 4. Telemetry Module (`/v1/telemetry/*`)
- `GET /metrics` - System metrics
- `GET /logs` - System logs
- `GET /traces` - Request traces
- `GET /resources` - Resource metrics

#### 5. Config Module (`/v1/config/*`)
- `GET /` - Get all config
- `GET /{key}` - Get specific config
- `PUT /{key}` - Update config
- `DELETE /{key}` - Delete config

#### 6. Authentication (`/v1/auth/*`)
- `POST /login` - Login (returns JWT)
- `POST /logout` - Logout
- `POST /refresh` - Refresh token
- `GET /current` - Current user

Default dev credentials: `admin/ciris_admin_password`

#### 7. Emergency (`/emergency/*`)
- `POST /shutdown` - Emergency shutdown (requires Ed25519 signature)
- Bypasses normal auth

#### 8. WebSocket (`/v1/ws`)
- Real-time updates and streaming

### Authentication Flow

```python
# 1. Login to get token
response = requests.post(
    "http://localhost:8080/v1/auth/login",
    json={"username": "admin", "password": "ciris_admin_password"}
)
token = response.json()["access_token"]

# 2. Use token in headers
headers = {"Authorization": f"Bearer {token}"}
response = requests.post(
    "http://localhost:8080/v1/agent/interact",
    headers=headers,
    json={"message": "Hello", "channel_id": "api_0.0.0.0_8080"}
)
```

### Role-Based Access Control

- **OBSERVER**: Read-only access
- **ADMIN**: Standard operations
- **AUTHORITY**: Wise Authority operations
- **SYSTEM_ADMIN**: Full system control

---

## Agent Creation Ceremony

### Core Concepts

- **Collaborative Creation**: Human + Facilitating Agent + Wise Authority
- **Immutable Lineage**: Every agent knows who created it and why
- **Ethical Foundation**: Purpose, justification, ethics required
- **WA Approval**: Ed25519 signature required

### Creation Flow

1. Human prepares proposal:
   - Name, purpose, justification, ethical considerations
2. Select template from `ciris_templates/`
3. Wise Authority reviews and signs
4. Ceremony creates:
   - Identity root in graph database
   - Immutable lineage record
   - Docker container configuration
5. Agent awakens with creation knowledge

### Book VI Compliance

All templates include stewardship sections:
- Creator Intent Statement
- Stewardship Tier calculation
- Creator Ledger Entry with signature

### Key Files
- `docs/AGENT_CREATION_CEREMONY.md`
- `docs/CREATION_CEREMONY_QUICKSTART.md`
- `ciris_templates/` - Agent templates

---

## Development Tools

### Grace - Sustainable Development Companion

Your intelligent pre-commit gatekeeper and development assistant.

```bash
# Status and monitoring
python -m tools.grace              # Current status + production incidents
python -m tools.grace deploy        # Deployment status
python -m tools.grace incidents     # Production incident details

# Pre-commit assistance
python -m tools.grace precommit     # Check pre-commit status
python -m tools.grace fix           # Auto-fix formatting issues

# Session management
python -m tools.grace morning       # Morning check-in
python -m tools.grace pause         # Save context before break
python -m tools.grace resume        # Resume after break
python -m tools.grace night         # Evening choice point
```

**Grace Philosophy:**
- Be strict about safety, gentle about style
- Progress over perfection
- Sustainable pace
- Anti-Goodhart: Quality emerges from clarity, not hours

### Version Management

```bash
# ALWAYS bump version after significant changes
python tools/bump_version.py patch  # Bug fixes (1.1.X)
python tools/bump_version.py minor  # New features (1.X.0)
python tools/bump_version.py major  # Breaking changes (X.0.0)
```

### Testing Tools

```bash
# Docker-based testing
python -m tools.test_tool test tests/  # Run tests in Docker
python -m tools.test_tool status       # Check progress
python -m tools.test_tool results      # Get results

# Background test runner
python tools/test_runner.py start --coverage
python tools/test_runner.py status
python tools/test_runner.py results
```

### Quality Analysis

```bash
# Comprehensive analysis
python -m tools.quality_analyzer

# SonarCloud metrics
python tools/sonar.py quality-gate
python tools/sonar.py coverage --new-code

# Type safety
python -m tools.ciris_mypy_toolkit analyze

# Dict[str, Any] audit
python -m tools.audit_dict_any_usage
```

### Debug Tools (in container)

```python
docker exec container0 python debug_tools.py

# Available commands:
show_correlations(limit=20)
list_traces(limit=20)
show_thoughts(status='PENDING')
show_tasks(limit=10)
show_handler_metrics()
```

---

## Production Deployment

### Server Access
- **IP**: 108.61.119.117 (use IP for SSH, not domain)
- **SSH**: `ssh -i ~/.ssh/ciris_deploy root@108.61.119.117`
- **Domain**: agents.ciris.ai (Cloudflare proxied)

### Clean CD Model

GitHub Actions → CIRISManager → Agents

```yaml
# GitHub Actions makes ONE API call:
curl -X POST https://agents.ciris.ai/manager/v1/updates/notify \
  -H "Authorization: Bearer $DEPLOY_TOKEN" \
  -d '{"agent_image": "ghcr.io/cirisai/ciris-agent:latest"}'
```

CIRISManager handles:
1. Notifies agents based on strategy
2. Agents respond: accept/defer/reject
3. Respects agent autonomy
4. Docker swaps containers on graceful exit

### Monitoring

```bash
# Check production health
curl https://agents.ciris.ai/api/datum/v1/system/health

# Check incidents (ALWAYS check first!)
docker exec ciris-agent-datum tail -n 100 /app/logs/incidents_latest.log

# CIRISManager status
curl http://localhost:8888/manager/v1/status
```

### Container Management
- **Restart Policy**: `restart: unless-stopped`
- **No staged containers**: Clean swaps only
- **Graceful shutdown**: Agents process as task
- **Agent autonomy**: Can defer/reject updates

---

## Debugging Guidelines

### Critical Rule: Check Incidents First

```bash
# ALWAYS check incidents_latest.log FIRST
docker exec container tail -n 100 /app/logs/incidents_latest.log
```

**NEVER restart container until incidents are understood** - They reveal system behavior

### Root Cause Analysis (RCA) Mode

1. **Preserve the Crime Scene**: Don't clean up errors immediately
2. **Use Debug Tools First**: Explore with debug_tools.py
3. **Trace Full Flow**: Follow data through pipeline
4. **Test Incrementally**: Small steps reveal causes
5. **Question Assumptions**: Challenge the design

### Mock LLM Behavior

Mock LLM may not respond with messages - this is by design:
- **DEFER**: Task deferred, no message
- **REJECT**: Request rejected, no message
- **TASK_COMPLETE**: Task done, no message
- **OBSERVE**: Observation registered, no message

### Command Output Best Practices

**GOLDEN RULE**: Always run commands WITHOUT pipes first

```bash
# ❌ Bad - Assumes JSON without checking
curl -s https://api.example.com/data | jq '.result'

# ✅ Good - Check output first
response=$(curl -s https://api.example.com/data)
echo "$response"  # See what we got
# Then parse if valid
```

### Common Issues

1. **AttributeError: 'NoneType'**: Check initialization order
2. **Validation errors**: Check Pydantic models
3. **Import errors**: Check circular dependencies
4. **Stuck tasks**: Use debug_tools to examine
5. **OAuth routing**: Check /api/{agent}/v1/* paths

---

## Local Development

### Setup

```bash
# Docker compose
docker compose -f docker/docker-compose-api-discord-mock.yml up -d

# GUI development
cd CIRISGUI/apps/agui && npm run dev  # http://localhost:3000

# CLI mode with mock LLM
python main.py --mock-llm --timeout 15 --adapter cli
```

### Environment Variables

```bash
# Required for API to bind to all interfaces (production)
CIRIS_API_HOST=0.0.0.0
CIRIS_API_PORT=8080

# OAuth configuration
CIRIS_OAUTH_GOOGLE_CLIENT_ID=your-client-id
CIRIS_OAUTH_GOOGLE_CLIENT_SECRET=your-secret
```

### Configuration Files

- `ciris_templates/` - Agent templates
- `.env` - Environment variables
- `docker/` - Docker configurations
- `config/` - System configurations

---

## Testing Framework

### Mock LLM

Deterministic testing with command extraction:

```python
# Mock LLM extracts commands from context:
"$speak Hello"  # SPEAK action
"$defer"        # DEFER action
"$reject"       # REJECT action
```

### Test Suite

- **1,180+ tests** with Docker CI/CD
- Background test runner for development
- 100% API endpoint coverage
- Mock services for isolated testing

### Running Tests

```bash
# Full suite
python -m pytest tests/

# Specific test
python -m pytest tests/test_api_v1.py::test_login

# With coverage
python -m pytest --cov=ciris_engine tests/
```

---

## Critical Commands

### Bash Command Timeouts

Default timeout is 2 minutes (120 seconds). For long-running commands:

```bash
# Monitor CI/CD (10 minutes)
gh run watch --repo CIRISAI/CIRISAgent  # timeout: 600000ms

# Run test suite (5 minutes)
python -m pytest tests/  # timeout: 300000ms
```

Maximum timeout: 600000ms (10 minutes)

### Git Workflow

```bash
# Create PR
gh pr create --repo CIRISAI/CIRISAgent

# Merge PR (admin)
gh pr merge <PR#> --repo CIRISAI/CIRISAgent --merge --admin

# Check CI/CD
gh run list --repo CIRISAI/CIRISAgent --limit 5
```

### Production Commands

```bash
# SSH to production
ssh -i ~/.ssh/ciris_deploy root@108.61.119.117

# Check container logs
docker logs ciris-agent-datum --tail 100

# Restart container (last resort)
docker restart ciris-agent-datum
```

---

## Important URLs

### Production
- **Main**: https://agents.ciris.ai
- **Datum API**: https://agents.ciris.ai/api/datum/v1/
- **OAuth Callback**: https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback

### GitHub
- **Main Repo**: https://github.com/CIRISAI/CIRISAgent
- **Actions**: https://github.com/CIRISAI/CIRISAgent/actions

### Documentation
- **SonarCloud**: https://sonarcloud.io/project/overview?id=CIRISAI_CIRISAgent

---

## Project Instructions (CLAUDE.md)

### Key Principles

1. **Service Count is Complete**: 21 core services
2. **No Service Creates Services**: Only ServiceInitializer
3. **Type Safety First**: All data uses Pydantic schemas
4. **Protocol-Driven**: Clear interfaces
5. **Forward Only**: No backwards compatibility
6. **Version Everything**: Always bump after changes

### Why This Architecture?

- **SQLite + Threading**: Offline-first for remote
- **23 Services**: Modular for selective deployment
- **Graph Memory**: Builds local knowledge base
- **Mock LLM**: Critical for offline operation
- **Resource Constraints**: Designed for 4GB RAM

### Development Philosophy

- **NEVER assume libraries are available** - Check first
- **Follow existing patterns** - Mimic code style
- **Security first** - Never expose secrets
- **Test incrementally** - Small steps reveal issues
- **Document with code** - Code is documentation

### Important Reminders

- **OAuth URL Format**: `/v1/auth/oauth/{agent_id}/{provider}/callback`
- **Agent ID comes BEFORE provider**
- **Default API auth**: admin/ciris_admin_password
- **Always check incidents before debugging**
- **Grace for sustainable development**
- **Version after significant changes**

---

## Repository Structure

```
CIRISAgent/
├── ciris_engine/         # Core engine code
│   ├── logic/           # All business logic
│   │   ├── services/    # 21 core services
│   │   ├── adapters/    # API, CLI, Discord adapters
│   │   ├── handlers/    # Message handlers
│   │   └── persistence/ # Database layer
│   ├── schemas/         # Pydantic models
│   ├── protocols/       # Service interfaces
│   └── memory/          # Graph memory system
├── ciris_templates/     # Agent templates
├── tools/               # Development tools
│   ├── grace/          # Sustainable dev companion
│   ├── test_tool/      # Docker testing
│   └── quality_analyzer/ # Code quality
├── tests/              # Test suite
├── docker/             # Docker configs
├── deployment/         # Deployment scripts
├── FSD/                # Functional specs
├── docs/               # Documentation
└── CIRISGUI/          # TypeScript GUI
```

---

## Success Metrics

### Current Achievements
- ✅ Zero `Dict[str, Any]` in production
- ✅ 78 API endpoints operational
- ✅ 100% test coverage on API
- ✅ 11 typed graph node classes
- ✅ Book VI compliance
- ✅ Production deployment
- ✅ Grace sustainable development

### Quality Metrics
- 1,180+ tests passing
- <1s API response time
- 4GB RAM footprint
- Zero attack surface
- Ed25519 signatures throughout

---

## Ethical Framework

### The Covenant (1.0b)

Core principles for moral agency:
1. Respect for persons
2. Beneficence and non-maleficence
3. Justice and fairness
4. Respect for autonomy
5. Veracity and transparency

### Book VI Compliance

Every agent includes:
- Creator Intent Statement
- Stewardship Tier (1-10)
- Creator Ledger Entry
- Digital signature

### Responsible Intelligence

- Agents can defer or reject requests
- Wise Authority provides oversight
- Formal creation ceremonies
- Immutable lineage tracking
- Transparent decision-making

---

## Quick Reference

### Most Used Commands

```bash
# Check status
grace

# Fix pre-commit
grace fix

# Check deployment
grace deploy

# Run tests
python -m tools.test_tool test tests/

# Bump version
python tools/bump_version.py patch

# Check production
ssh -i ~/.ssh/ciris_deploy root@108.61.119.117
docker exec ciris-agent-datum tail -n 100 /app/logs/incidents_latest.log
```

### Emergency Procedures

1. **Production Down**: Check incidents → Check health → Check containers
2. **Tests Failing**: Check recent commits → Run locally → Check CI/CD
3. **Deploy Failed**: Check GitHub Actions → Check CIRISManager → Check agent logs
4. **OAuth Broken**: Verify callback URL format → Check nginx routing
5. **Memory Issues**: Check resource monitor → Check TSDB consolidation

---

## Contact & Support

- **GitHub Issues**: https://github.com/CIRISAI/CIRISAgent/issues
- **Creator**: Eric Moore
- **Philosophy**: "We control the code that controls our context"

---

*End of CIRIS Comprehensive Guide*
*Version 1.2.0-beta - August 7, 2025*
