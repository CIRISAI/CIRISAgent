# CIRIS Comprehensive Guide

**Version 1.6.0** | Last Updated: 2025-11-08

CIRIS (Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude) is an ethical AI platform designed for production-grade GDPR compliance, multi-occurrence deployment, and sustainable development practices.

## Table of Contents

1. [Introduction](#introduction)
2. [Core Philosophy](#core-philosophy)
3. [Architecture Overview](#architecture-overview)
4. [Getting Started](#getting-started)
5. [GDPR Compliance & DSAR Automation](#gdpr-compliance--dsar-automation)
6. [Development Workflow](#development-workflow)
7. [Testing & Quality Assurance](#testing--quality-assurance)
8. [Deployment](#deployment)
9. [Security](#security)
10. [Troubleshooting](#troubleshooting)

---

## Introduction

### What is CIRIS?

CIRIS is a production-ready AI agent framework with:
- **22 Core Services** - Complete service architecture
- **6 Message Buses** - Scalable multi-provider design
- **6 Cognitive States** - Ethical AI behavior patterns
- **GDPR Compliance** - Full DSAR automation (Articles 15-20)
- **Multi-Occurrence** - Horizontal scaling with atomic coordination
- **4GB RAM Target** - Efficient resource usage
- **Offline-Capable** - Works without internet connectivity

### Production Deployments

- **Discord Moderation**: Community management and content moderation
- **API at agents.ciris.ai**: RESTful API with OAuth integration
- **GDPR Automation**: Automated Data Subject Access Requests

---

## Core Philosophy

### The Three Rules

1. **No Untyped Dicts**: All data uses Pydantic models instead of `Dict[str, Any]`
2. **No Bypass Patterns**: Every component follows consistent rules and patterns
3. **No Exceptions**: No special cases, emergency overrides, or privileged code paths

### Type Safety First

CIRIS enforces strict type safety with:
- Pydantic models for all data structures
- Mypy static type checking (strict mode)
- Union types for flexibility
- Enums for constants

**Example:**
```python
# ❌ Bad - Untyped Dict
def process_data(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"result": data.get("value", 0) * 2}

# ✅ Good - Pydantic Models
class ProcessRequest(BaseModel):
    value: int = 0

class ProcessResponse(BaseModel):
    result: int

def process_data(data: ProcessRequest) -> ProcessResponse:
    return ProcessResponse(result=data.value * 2)
```

### Medical Domain Prohibition

**NEVER implement in main repo:**
- Medical/health capabilities
- Diagnosis/treatment logic
- Patient data handling
- Clinical decision support

**These are BLOCKED at the bus level** in `wise_bus.py`.

---

## Architecture Overview

### 22 Core Services

**Graph Services (7):**
- `memory` - Graph-based memory storage
- `consent` - GDPR consent management
- `config` - Configuration storage
- `telemetry` - Metrics collection
- `audit` - Immutable audit trail
- `incident_management` - Error tracking
- `tsdb_consolidation` - Time-series data

**Infrastructure Services (4):**
- `authentication` - Ed25519-based auth
- `resource_monitor` - System health tracking
- `database_maintenance` - DB cleanup
- `secrets` - Secret management

**Lifecycle Services (4):**
- `initialization` - Startup orchestration
- `shutdown` - Graceful termination
- `time` - Clock synchronization
- `task_scheduler` - Cron-like scheduling

**Governance Services (4):**
- `wise_authority` - Ethical guidance
- `adaptive_filter` - Content filtering
- `visibility` - Transparency logging
- `self_observation` - Introspection

**Runtime Services (2):**
- `llm` - LLM provider abstraction
- `runtime_control` - Runtime coordination

**Tool Services (1):**
- `secrets_tool` - Secrets access for agents

### 6 Message Buses

Message buses enable multiple providers for scalability:

**Bussed Services:**
- **CommunicationBus** → Multiple adapters (Discord, API, CLI)
- **MemoryBus** → Multiple graph backends (Neo4j, ArangoDB, in-memory)
- **LLMBus** → Multiple LLM providers (OpenAI, Anthropic, local)
- **ToolBus** → Multiple tool providers from adapters
- **RuntimeControlBus** → Multiple control interfaces
- **WiseBus** → Multiple wisdom sources

**Direct Call Services:**
- All Graph Services (except memory)
- Core Services: secrets
- Infrastructure Services (except wise_authority)
- All Special Services

### 6 Cognitive States

CIRIS agents operate in six distinct cognitive states:

1. **WAKEUP** - Identity confirmation and startup
2. **WORK** - Normal task processing
3. **PLAY** - Creative exploration mode
4. **SOLITUDE** - Reflection and introspection
5. **DREAM** - Deep introspection and learning
6. **SHUTDOWN** - Graceful termination

---

## Getting Started

### Prerequisites

- Python 3.12+
- SQLite or PostgreSQL
- Git
- Docker (optional, for production deployment)

### Installation

```bash
# Clone repository
git clone https://github.com/CIRISAI/CIRISAgent.git
cd CIRISAgent

# Install dependencies
pip install -r requirements.txt

# Initialize database
python main.py --adapter api --init-only

# Run with Mock LLM (no API keys needed)
python main.py --adapter api --mock-llm
```

### First Steps

1. **Start API Server:**
   ```bash
   python main.py --adapter api --mock-llm --port 8000
   ```

2. **Get Auth Token:**
   ```bash
   TOKEN=$(curl -X POST http://localhost:8000/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"ciris_admin_password"}' \
     2>/dev/null | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
   ```

3. **Check System Health:**
   ```bash
   curl -X GET http://localhost:8000/v1/telemetry/unified \
     -H "Authorization: Bearer $TOKEN" 2>/dev/null | \
     python -c "import json,sys; d=json.load(sys.stdin); print(f'{d[\"services_online\"]}/{d[\"services_total\"]} services healthy')"
   ```

4. **Interact with Agent:**
   ```bash
   curl -X POST http://localhost:8000/v1/agent/interact \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"message":"Hello, how are you?"}' 2>/dev/null | python -m json.tool
   ```

### Quick Reference

**Default Credentials (Development Only):**
- Username: `admin`
- Password: `ciris_admin_password`

**Important URLs:**
- Production: https://agents.ciris.ai
- API: https://agents.ciris.ai/api/datum/v1/
- OAuth: https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback

---

## GDPR Compliance & DSAR Automation

### Universal Ticket System

CIRIS provides a universal ticket system for GDPR compliance:

**Ticket Types:**
- **DSAR** (Data Subject Access Requests) - Required for all agents
- **Custom Types** - Agent-specific workflows (appointments, incidents, etc.)

**Ticket Lifecycle:**
```
pending → assigned → in_progress → completed
                                 ↓
                        blocked / deferred
```

**Status Definitions:**
- `pending` - New ticket, available for claiming
- `assigned` - Claimed by specific occurrence
- `in_progress` - Active processing
- `blocked` - Requires external intervention (stops task generation)
- `deferred` - Postponed to future time (stops task generation)
- `completed` - Successfully finished
- `cancelled` - Manually cancelled
- `failed` - Processing failed

### DSAR Operations

CIRIS supports all GDPR DSAR operations:

**Article 15 - Access:**
```python
# Create DSAR access request
response = await client._transport.request("POST", "/v1/tickets/",
    json={
        "sop": "DSAR_ACCESS",
        "email": "user@example.com",
        "user_identifier": "user_001",
    }
)
```

**Article 17 - Deletion:**
```python
# Create DSAR deletion request
response = await client._transport.request("POST", "/v1/tickets/",
    json={
        "sop": "DSAR_DELETE",
        "email": "user@example.com",
        "user_identifier": "user_001",
    }
)
```

**Article 20 - Portability:**
```python
# Create DSAR export request
response = await client._transport.request("POST", "/v1/tickets/",
    json={
        "sop": "DSAR_EXPORT",
        "email": "user@example.com",
        "user_identifier": "user_001",
    }
)
```

### Multi-Source DSAR Orchestration

CIRIS can orchestrate DSAR requests across multiple data sources:

**Supported Sources:**
- CIRIS internal data (consent system, memory graph)
- External SQL databases (via connectors)
- Custom tool providers

**SQL Connector Registration:**
```python
# Register external SQL database
response = await client._transport.request("POST", "/v1/dsar/connectors",
    json={
        "name": "customer_db",
        "connection_string": "postgresql://user:pass@host:5432/db",
        "privacy_schema": {...},  # PII field definitions
    }
)
```

### Ticket Stage Progression

Tickets follow stage-based workflows defined in agent templates:

**Example - DSAR Delete Stages:**
1. `identity_resolution` - Verify user identity
2. `deletion_verification` - Confirm deletion intent
3. `ciris_data_deletion` - Delete CIRIS internal data
4. `external_data_deletion` - Delete external database data

**Stage Metadata:**
```json
{
  "stages": {
    "identity_resolution": {
      "status": "completed",
      "started_at": "2025-11-08T10:00:00Z",
      "completed_at": "2025-11-08T10:05:00Z",
      "result": "identity_confirmed"
    },
    "deletion_verification": {
      "status": "in_progress",
      "started_at": "2025-11-08T10:05:00Z",
      "completed_at": null,
      "result": null
    }
  },
  "current_stage": "deletion_verification"
}
```

### Ticket Tools for Agents

Agents have access to ticket management tools:

**Available Tools:**
- `update_ticket` - Update status or metadata
- `block_ticket` - Block ticket (requires external intervention)
- `defer_ticket` - Defer ticket to future time
- `complete_ticket` - Mark ticket as completed
- `fail_ticket` - Mark ticket as failed

**Example - Update Ticket:**
```python
# Agent uses tool to update ticket metadata
message = f'$tool update_ticket ticket_id="{ticket_id}" metadata="{metadata_json}"'
response = await client.agent.interact(message)
```

---

## Development Workflow

### Grace - Your Development Companion

Grace is the intelligent pre-commit gatekeeper and development assistant:

```bash
# Daily workflow
python -m tools.grace morning          # Start day with context
python -m tools.grace status           # Check system health
python -m tools.grace precommit        # Before commits
python -m tools.grace night            # End day choice point

# CI monitoring (WAIT 10 MINUTES between checks!)
python -m tools.grace ci               # Current branch CI + PR summary
python -m tools.grace ci prs           # All PRs with conflict detection
python -m tools.grace ci builds        # Build & Deploy status
python -m tools.grace ci hints         # CI failure hints

# Pre-commit assistance
python -m tools.grace fix              # Auto-fix issues

# Deployment & incidents
python -m tools.grace deploy           # Check deployment status
python -m tools.grace incidents        # Check production incidents
```

**Grace Philosophy:**
- **Be strict about safety, gentle about style**
- **Progress over perfection**
- **Sustainable pace** - Tracks work sessions, encourages breaks

### Version Management

Always bump version after significant changes:

```bash
python tools/dev/bump_version.py patch     # Bug fixes
python tools/dev/bump_version.py minor     # New features
python tools/dev/bump_version.py major     # Breaking changes
```

### Git Workflow

**NEVER PUSH DIRECTLY TO MAIN** - Always create a branch:

```bash
# Create feature branch
git checkout -b feat/your-feature-name

# Bump version
python tools/dev/bump_version.py minor

# Make changes, commit with Grace
python -m tools.grace precommit
git add .
git commit -m "feat: Your feature description"

# Push and create PR
git push -u origin feat/your-feature-name
gh pr create --title "Your PR Title" --body "PR description"
```

### Before Creating ANY New Type

**ALWAYS search first - the schema already exists:**

```bash
grep -r "class.*YourThingHere" --include="*.py"
```

---

## Testing & Quality Assurance

### QA Runner - API Test Suite

The CIRIS QA Runner provides comprehensive API testing:

```bash
# Run all tests
python -m tools.qa_runner

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
python -m tools.qa_runner filters       # Adaptive filtering tests
python -m tools.qa_runner sdk           # SDK compatibility tests
python -m tools.qa_runner streaming     # H3ERE pipeline streaming tests

# DSAR-specific tests
python -m tools.qa_runner dsar_ticket_workflow    # Ticket lifecycle (14 tests)
python -m tools.qa_runner dsar_multi_source       # Multi-source operations (13 tests)

# Full verbose output
python -m tools.qa_runner <module> --verbose

# Multi-backend testing
python -m tools.qa_runner auth --database-backends sqlite postgres
python -m tools.qa_runner auth --database-backends sqlite postgres --parallel-backends
```

**QA Runner Features:**
- 🤖 **Automatic Lifecycle Management** - Starts/stops API server automatically
- 🔑 **Smart Token Management** - Auto re-authentication after logout/refresh tests
- ⚡ **Fast Execution** - Most modules complete quickly
- 🧪 **Comprehensive Coverage** - Authentication, API endpoints, streaming, filtering
- 🔍 **Detailed Reporting** - Success rates, duration, failure analysis
- 🚀 **Production Ready** - Validates all critical system functionality
- 🔄 **Multi-Backend Support** - Test against SQLite and PostgreSQL

### Pytest - Unit Tests

```bash
# Run all tests (ALWAYS use -n 16 for parallel execution)
pytest -n 16 tests/ --timeout=300

# Run specific test module
pytest tests/ciris_engine/logic/services/test_authentication.py

# Run with coverage
pytest --cov=ciris_engine --cov-report=html

# Coverage analysis
python -m tools.quality_analyzer
```

### SonarCloud Quality Analysis

```bash
# Check quality gate status
python -m tools.analysis.sonar quality-gate  # PR + main status
python -m tools.analysis.sonar status        # Main branch only
```

### Mock LLM for Testing

CIRIS includes a Mock LLM for deterministic testing without API keys:

**Tool Call Syntax:**
```
$tool <tool_name> param1="value1" param2="value2"
```

**Example:**
```python
# Mock LLM will parse and execute tool call
message = '$tool update_ticket ticket_id="DSAR-20251108-ABC123" status="completed"'
response = await client.agent.interact(message)
```

**Benefits:**
- No API keys needed
- Deterministic results
- Fast test execution
- Full tool integration testing

---

## Deployment

### Self-Sovereign Install (pip)

CIRIS now supports self-sovereign deployment via pip, allowing anyone to run their own agent instance without Docker or manual source installation:

```bash
# Install from PyPI (includes built-in GUI)
pip install ciris-agent

# Start API server with web interface
ciris-agent --adapter api --port 8000

# Start with Discord adapter
ciris-agent --adapter discord --guild-id YOUR_GUILD_ID

# Use mock LLM for testing (no API keys required)
ciris-agent --adapter api --mock-llm --port 8000
```

**Key Features:**
- **Self-contained**: Includes all dependencies and built-in web GUI
- **No Docker required**: Direct Python installation
- **Cross-platform**: Windows, macOS, Linux support via PyPI
- **System integration**: Includes systemd service configuration for Linux
- **Data sovereignty**: All data stored locally in `~/.ciris/`

**Configuration:**
- Config file: `~/.ciris/.env`
- Data directory: `~/.ciris/data/`
- Database: `~/.ciris/data/ciris.db`

### Local Development (Source)

```bash
# Clone repository
git clone https://github.com/CIRISAI/CIRISAgent.git
cd CIRISAgent

# Install dependencies
pip install -r requirements.txt

# Start API server
python main.py --adapter api --mock-llm --port 8000

# Start Discord adapter
python main.py --adapter discord
```

### Docker Deployment

```bash
# Build image
docker build -t ciris-agent:latest .

# Run container
docker run -d \
  --name ciris-agent \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e AGENT_ID=your-agent-id \
  -e ADAPTER=api \
  ciris-agent:latest
```

### Multi-Occurrence Deployment

CIRIS supports horizontal scaling with multi-occurrence deployment:

```bash
# Set occurrence ID (defaults to "default")
export AGENT_OCCURRENCE_ID="occurrence-1"

# Set total occurrence count for discovery
export AGENT_OCCURRENCE_COUNT="9"

# Start occurrence
python main.py --adapter api
```

**Key Concepts:**
- **Occurrence**: Single runtime instance (process/container)
- **Shared Tasks**: Agent-level tasks using `agent_occurrence_id="__shared__"`
- **Atomic Claiming**: Race-free task claiming using deterministic IDs

**Implementation:**
- `try_claim_shared_task()` - Atomic task claiming
- `is_shared_task_completed()` - Check if another occurrence decided
- `get_latest_shared_task()` - Retrieve shared decision
- Deterministic task IDs: `WAKEUP_SHARED_20251027`, `SHUTDOWN_SHARED_20251027`

### Production Server Access

**SSH Access:**
```bash
ssh -i ~/.ssh/ciris_deploy root@108.61.119.117
```

**Agent Locations:**
```bash
cd /opt/ciris/agents/
ls -la
```

**Log Files:**
Logs are always written to files inside containers at `/app/logs/`:
- `/app/logs/incidents_latest.log` - Current incidents (ALWAYS CHECK FIRST)
- `/app/logs/application.log` - General application logs
- `/app/logs/ciris_YYYY-MM-DD.log` - Daily log files

**Common Commands:**
```bash
# Check agent status
cd /opt/ciris/agents/echo-speculative-4fc6ru
docker-compose ps

# View incidents log
docker exec echo-speculative-4fc6ru tail -100 /app/logs/incidents_latest.log

# Check consolidation activity
docker exec echo-speculative-4fc6ru grep -i "consolidat" /app/logs/incidents_latest.log | tail -20

# Check shutdown status
docker exec echo-speculative-4fc6ru grep -i "shutdown" /app/logs/incidents_latest.log | tail -20
```

---

## Security

### Authentication

CIRIS uses Ed25519-based authentication:

**Token Format:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Service Tokens:**
```
Authorization: Bearer service:<TOKEN_VALUE>
```

**OAuth Providers:**
- Google
- Discord
- Reddit

**OAuth Callback URL Format:**
```
https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback
```

### Secret Management

```bash
# Store secret
curl -X POST http://localhost:8000/v1/secrets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"my_secret","value":"secret_value"}'

# Retrieve secret
curl -X GET http://localhost:8000/v1/secrets/my_secret \
  -H "Authorization: Bearer $TOKEN"
```

### Ed25519 Signatures

CIRIS uses Ed25519 signatures for:
- Audit trail integrity
- Deletion verification (GDPR Article 17)
- Token signing
- Message authentication

### Input Validation

All inputs are validated with Pydantic models:
- SQL injection prevention
- XSS protection
- Command injection prevention
- Path traversal prevention

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Dict[str, Any] error | Schema already exists - search for it |
| CI failing | Wait for CI to complete, check SonarCloud |
| OAuth not working | Check callback URL format |
| Service not found | Check ServiceRegistry capabilities |
| WA deferral failing | Check WiseBus broadcast logic |

### Debugging Workflow

1. **Check incidents log FIRST:**
   ```bash
   docker exec container tail -n 100 /app/logs/incidents_latest.log
   ```

2. **Use debug tools:**
   ```python
   python -m tools.debug_tools trace
   ```

3. **Verify with audit trail:**
   ```bash
   curl -X GET http://localhost:8000/v1/audit/events \
     -H "Authorization: Bearer $TOKEN"
   ```

4. **Test incrementally:**
   - Start with smallest test case
   - Add complexity gradually
   - Check logs after each step

### Grace Pre-commit Issues

If Grace blocks your commit:

```bash
# Check what's wrong
python -m tools.grace precommit

# Auto-fix issues
python -m tools.grace fix

# Try again
git commit
```

### Production Incidents

```bash
# Check production incidents
python -m tools.grace incidents

# View specific agent logs
docker exec agent-name tail -100 /app/logs/incidents_latest.log
```

---

## Additional Resources

- **GitHub Issues**: https://github.com/CIRISAI/CIRISAgent/issues
- **API Documentation**: `/docs/API_SPEC.md`
- **Architecture Guide**: `/docs/ARCHITECTURE.md`
- **Deployment Guide**: `/docs/DEPLOYMENT_GUIDE.md`
- **Security Setup**: `/docs/SECURITY_SETUP.md`
- **OAuth Setup**: `/docs/OAUTH_CONFIGURATION_GUIDE.md`

---

## Quick Command Reference

### Development
```bash
# Grace workflow
python -m tools.grace morning
python -m tools.grace status
python -m tools.grace precommit
python -m tools.grace night

# Version management
python tools/dev/bump_version.py minor

# Quality checks
python -m tools.quality_analyzer
python -m tools.analysis.sonar quality-gate
```

### Testing
```bash
# QA Runner
python -m tools.qa_runner                    # All tests
python -m tools.qa_runner dsar_ticket_workflow  # DSAR tickets

# Pytest
pytest -n 16 tests/ --timeout=300

# Mypy
mypy ciris_engine/
```

### Deployment
```bash
# Local
python main.py --adapter api --mock-llm

# Docker
docker-compose up -d

# Production logs
docker exec agent tail -100 /app/logs/incidents_latest.log
```

---

**Remember:** The schema you're about to create already exists. Search for it first.
