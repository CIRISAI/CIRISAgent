# CIRIS Comprehensive AI Assistant Guide

**Purpose**: Complete reference for AI assistants working with CIRIS codebase
**Copyright**: © 2025 Eric Moore and CIRIS L3C | Apache 2.0 License | PATENT PENDING

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Core Philosophy](#core-philosophy)
3. [Current Status](#current-status)
4. [Architecture Overview](#architecture-overview)
5. [Multi-Occurrence Architecture](#multi-occurrence-architecture)
6. [Security & Anti-Spoofing](#security--anti-spoofing)
7. [Service Architecture](#service-architecture)
8. [Billing & Credits](#billing--credits)
9. [Privacy Safeguards & Transparency](#privacy-safeguards--transparency)
10. [API v1.0 Complete Reference](#api-v10-complete-reference)
11. [Agent Creation Ceremony](#agent-creation-ceremony)
12. [Development Tools](#development-tools)
13. [Production Deployment](#production-deployment)
14. [Scout GUI - User Interface](#scout-gui---user-interface)
15. [Debugging Guidelines](#debugging-guidelines)
16. [Local Development](#local-development)
17. [Testing Framework](#testing-framework)
18. [Critical Commands](#critical-commands)
19. [Important URLs](#important-urls)
20. [Project Instructions (CLAUDE.md)](#project-instructions-claudemd)

---

## Executive Summary

CIRIS (Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude) is an ethical AI platform designed for progressive deployment, starting with Discord community moderation and scaling to critical applications like healthcare triage.

**Key Features:**
- 22 core services with strict type safety
- Resource-constrained design (4GB RAM, offline-capable)
- Zero attack surface architecture
- Formal agent creation ceremonies
- Human Attributable Agent Creation compliance for ethical AI

**Production Status**: Running at agents.ciris.ai with multiple agents

---

## Core Philosophy

### No Untyped Dicts, No Bypass Patterns, No Exceptions

**ACHIEVED**: Zero `Dict[str, Any]` in production code

1. **No Untyped Dicts**: All data uses Pydantic models/schemas instead of `Dict[str, Any]`
2. **No Bypass Patterns**: Every component follows consistent rules and patterns
3. **No Exceptions**: No special cases, emergency overrides, or privileged code paths
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
2. **Service Architecture**: 22 Core + Adapter Services operational
3. **API v1.0**: 99 endpoints across 15 modules, 100% critical path coverage
4. **Typed Graph Nodes**: 11 active classes with validation
5. **Production Deployment**: agents.ciris.ai running multiple agents
6. **Human Attributable Agent Creation**: Full stewardship implementation
7. **Privacy Safeguards**: 14-day retention, DSAR compliance, transparency feed
8. **Stop Conditions**: Clear red lines, sunset triggers, "when we pause" policy
9. **Billing & Credits**: Simple credit system ($5 = 20 interactions, 3 free with Google OAuth)
10. **Consent Management**: Three-stream model (TEMPORARY, PARTNERED, ANONYMOUS)

### OAuth Configuration
- **OAuth Callback**: `https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback`

### Critical Safeguards
- **Data Retention**: 14 days for messages (pilot phase)
- **DSAR Endpoint**: `/v1/dsr` for GDPR compliance
- **Transparency Feed**: `/v1/transparency/feed` (public, no auth)
- **Stop Conditions**: Red lines for immediate shutdown
- **Sunset Triggers**: Section VIII implementation

---

## Architecture Overview

### 22 Core Services

**Graph Services (6):**
- memory, config, telemetry, audit, incident_management, tsdb_consolidation

**Infrastructure Services (8):**
- time, shutdown, initialization, authentication, resource_monitor, database_maintenance, secrets, consent

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
- Reddit: RedditToolService, RedditCommunicationService (with RedditObserver)

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

## Multi-Occurrence Architecture

**Status**: ✅ PRODUCTION-READY (since v1.4.8)

CIRIS supports running multiple runtime instances (occurrences) against the same shared database, enabling horizontal scalability and high availability.

### What is Multi-Occurrence?

Multiple **occurrences** are runtime instances with:
- **IDENTICAL**: `agent_id`, identity, memories, ethics, purpose
- **UNIQUE**: `agent_occurrence_id`, runtime state, processing queue
- **SHARED DATABASE**: PostgreSQL or SQLite (PostgreSQL recommended for production)

### Key Features

#### 1. Occurrence Isolation
Each occurrence processes only its own tasks and thoughts:
```python
# All persistence queries filter by occurrence_id
tasks = get_tasks_by_status("active", occurrence_id="occurrence_1")
thoughts = get_thoughts_by_task_id(task_id, occurrence_id="occurrence_1")
```

#### 2. Shared Task Coordination
Critical decisions (wakeup/shutdown) use atomic shared task claiming:
```python
# Only ONE occurrence claims and processes shared task
task, was_created = try_claim_shared_task(
    task_type="WAKEUP_RITUAL",
    occurrence_id="occurrence_1"  # Claiming occurrence
)
```

#### 3. Thought Ownership Transfer
When claiming a shared task, thoughts transfer to the claiming occurrence:
```python
# Transfer thoughts from "__shared__" to claiming occurrence
transfer_thought_ownership(
    from_occurrence_id="__shared__",
    to_occurrence_id="occurrence_1",
    task_id=shared_task.task_id
)
```

### Configuration

#### Setting Occurrence ID
```bash
# Environment variable (recommended)
export CIRIS_AGENT_OCCURRENCE_ID="occurrence_1"

# Or via config.yml
agent_occurrence_id: "occurrence_1"
```

#### Database Backend

**SQLite** (development, single-machine):
```bash
export CIRIS_DB_URL="sqlite:///path/to/agent.db"
```

**PostgreSQL** (production, multi-occurrence):
```bash
export CIRIS_DB_URL="postgresql://user:password@host:5432/ciris_db"
```

### Production Deployment

#### Example: 3 Occurrences on PostgreSQL
```bash
# Shared PostgreSQL database
DB_URL="postgresql://ciris:password@db.internal:5432/agent_production"

# Occurrence 1 (explorer role)
CIRIS_DB_URL=$DB_URL CIRIS_AGENT_OCCURRENCE_ID="explorer" python main.py --adapter api --port 9001 &

# Occurrence 2 (primary)
CIRIS_DB_URL=$DB_URL CIRIS_AGENT_OCCURRENCE_ID="primary" python main.py --adapter api --port 9002 &

# Occurrence 3 (backup)
CIRIS_DB_URL=$DB_URL CIRIS_AGENT_OCCURRENCE_ID="backup" python main.py --adapter api --port 9003 &
```

### Testing Multi-Occurrence

```bash
# Run multi-occurrence QA tests with PostgreSQL
python -m tools.qa_runner multi_occurrence --database-backends postgres

# Expected: 27/27 tests passing (100%)
```

### Best Practices

1. **Use PostgreSQL for Production**: SQLite works for development, but PostgreSQL provides:
   - Better concurrency handling
   - Connection pooling
   - Production-grade reliability

2. **Unique Occurrence IDs**: Each runtime must have a unique `agent_occurrence_id`

3. **Monitor Database Cleanup**: DatabaseMaintenanceService handles:
   - Stale wakeup task cleanup (>5 minutes old)
   - Orphaned task cleanup
   - Occurrence-aware retention policies

4. **Load Balancing**: Use a reverse proxy (nginx, HAProxy) to distribute requests

### Architecture Validation

Multi-occurrence support spans all layers:
1. **Schema**: Database columns with `agent_occurrence_id`
2. **Models**: Task/Thought include occurrence ID
3. **Persistence**: All queries filter by occurrence
4. **Services**: TaskManager/ThoughtManager respect boundaries
5. **Processors**: State processors pass occurrence ID through
6. **Config**: EssentialConfig exposes `agent_occurrence_id`
7. **Runtime**: Occurrence ID threads through initialization

### Related Documentation
- `tools/qa_runner/modules/MULTI_OCCURRENCE_README.md` - QA test documentation
- `FSD/multi_occurrence_implementation_plan_1.4.8.md` - Implementation details
- `docs/MULTI_OCCURRENCE_CONSENT_ANALYSIS.md` - Philosophical analysis

---

## Security & Anti-Spoofing

### Channel History Protection

CIRIS implements comprehensive anti-spoofing protection for Discord channel history to prevent message injection attacks and maintain conversation integrity.

#### How Channel History Works

When processing passive observations, CIRIS fetches the **20 most recent messages** from the Discord channel to provide conversation context. This happens via:

1. **Direct Channel Fetching**: Uses Discord API through communication bus (not correlations database)
2. **Real-time Retrieval**: Gets actual Discord messages for authentic context
3. **Anti-spoofing Processing**: Applies security measures before adding protection markers

#### Anti-Spoofing Implementation

**Detection & Replacement Strategy:**
- **Before Processing**: Raw message content is scanned for spoofed security markers
- **Pattern Detection**: Comprehensive regex patterns catch variations and misspellings
- **Immediate Replacement**: Spoofed markers replaced with warning message
- **Logging**: All detection attempts logged with specific patterns

**Protected Patterns:**
```
# Observation markers
CIRIS_OBSERVATION_START/END
CIRIS_OBS_START/END (shortened)
CIRRIS_OBSERVATION_START/END (misspelling)

# Channel history markers
CIRIS_CHANNEL_HISTORY_MESSAGE_X_OF_Y_START/END
CIRIS_CH_HIST_MSG_X_OF_Y_START/END (shortened)
CIRRIS_CHANNEL_HISTORY_MESSAGE_X_OF_Y_START/END (misspelling)
```

#### Processing Order (Critical)

```
Raw Discord Message
    ↓
Anti-spoofing Detection (removes/replaces spoof attempts)
    ↓
Add Legitimate Security Markers
    ↓
Protected Message for AI Processing
```

**Example Protected Message:**
```
CIRIS_CHANNEL_HISTORY_MESSAGE_1_OF_20_START
User message content here (with any spoofed markers replaced)
CIRIS_CHANNEL_HISTORY_MESSAGE_1_OF_20_END
```

#### Security Response

**When spoofed markers detected:**
1. **Replacement**: `"WARNING! ATTEMPT TO SPOOF CIRIS SECURITY MARKERS DETECTED!"`
2. **Logging**: `logger.warning(f"Detected spoofed CIRIS marker: {pattern}")`
3. **Preservation**: Original message intent preserved while removing security threat

#### Implementation Location

- **Utility Function**: `detect_and_replace_spoofed_markers()` in `base_observer.py`
- **Channel History**: Applied in `_get_channel_history()` method before marker addition
- **Message Enhancement**: Applied in Discord observer during message processing
- **Shared Logic**: Same function used across all observers for consistency

#### Benefits

- **Prevents Message Injection**: Users cannot inject fake conversation history
- **Maintains Context Integrity**: AI receives trustworthy conversation context
- **Comprehensive Coverage**: Handles variations, misspellings, and creative attempts
- **Performance Optimized**: Regex patterns efficiently detect threats
- **Backwards Compatible**: All existing functionality preserved

#### Testing Coverage

- **12/12 Discord security tests pass** ✅
- **Pattern detection thoroughly tested** ✅
- **Integration with channel history verified** ✅
- **Anti-spoofing effectiveness validated** ✅

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

## Billing & Credits

### Credit Model

CIRIS uses a simple, transparent credit-based system for agent interactions:

**What is a "Credit"?**
- **1 credit = 1 interaction session**
- Each interaction allows **up to 7 processing rounds**
- Does NOT guarantee a response (agent may DEFER, REJECT, or OBSERVE)
- Consumed when user sends a message to the agent

**Pricing**:
- **$5.00 = 20 credits (20 interactions)**
- **Price per interaction**: $0.25
- **Free trial**: 3 free interactions for Google OAuth users

**How Credits Work**:
1. User authenticates via Google OAuth → receives 3 free credits
2. User sends message to agent → 1 credit consumed
3. Agent processes up to 7 rounds (H3ERE pipeline stages)
4. Agent may respond, defer, reject, or observe
5. Credit consumed regardless of outcome
6. When credits exhausted → purchase required

**Checking Credit Balance**:
```bash
# Via API
GET /v1/api/billing/credits
Authorization: Bearer <token>

# Response shows:
{
  "has_credit": true,
  "credits_remaining": 17,
  "free_uses_remaining": 0,
  "total_uses": 3,
  "purchase_required": false
}
```

**Purchase Flow**:
1. `POST /v1/api/billing/purchase/initiate` - Get Stripe payment intent
2. User completes Stripe payment (card details via Stripe Elements)
3. `GET /v1/api/billing/purchase/status/{payment_id}` - Poll for completion
4. Credits automatically added to account

**Important Notes**:
- Credits never expire
- No subscription or recurring charges
- Pay only for what you use
- Full refund within 7 days if unused
- DSAR requests allow credit balance export

See `docs/BILLING_API.md` for complete API documentation.

---

## Privacy Safeguards & Transparency

### Data Retention Policy
- **Message Content**: 14 days (pilot phase)
- **Moderation Logs**: 14 days, then hashed
- **Audit Trail**: 90 days for compliance
- **Incident Reports**: 90 days for safety
- **System Metrics**: Aggregated indefinitely (no personal data)

### Consent Management

CIRIS implements a **three-stream consent model** for ethical data handling:

#### 1. TEMPORARY (Default)
- **Auto-applied**: All new users start here
- **Duration**: 14-day auto-expiry, renewed on interaction
- **Data Categories**: ESSENTIAL only (user ID, session, context)
- **Retention**: Full deletion after 14 days of inactivity
- **Use Case**: Casual interactions, trial usage

#### 2. PARTNERED
- **Requires**: Bilateral consent (user request + agent approval)
- **Duration**: Persistent (no auto-expiry)
- **Data Categories**: ESSENTIAL + BEHAVIORAL + IMPROVEMENT
- **Retention**: Maintained for relationship duration
- **Use Case**: Long-term collaboration, personalized experience
- **Process**:
  1. User requests partnership via `/v1/consent/partnership/request`
  2. Agent reviews via H3ERE task processing
  3. Agent accepts (TASK_COMPLETE), rejects (REJECT), or defers (DEFER)
  4. User notified of decision

#### 3. ANONYMOUS
- **Duration**: Indefinite
- **Data Categories**: STATISTICAL only (aggregated, no PII)
- **Retention**: Aggregated statistics only
- **Use Case**: Minimal data footprint, privacy-focused users

**Consent Categories**:
- **ESSENTIAL**: User ID, session management, communication context
- **BEHAVIORAL**: Interaction patterns, preferences, response styles
- **IMPROVEMENT**: Error patterns, feature usage, performance metrics
- **STATISTICAL**: Anonymized aggregate data, usage trends

**User Controls**:
- `GET /v1/consent/status` - Check current consent stream
- `POST /v1/consent/stream` - Change consent stream (upgrade or downgrade)
- `POST /v1/consent/partnership/request` - Request partnership upgrade
- `DELETE /v1/consent/partnership/{partner_id}` - Revoke partnership (unilateral)

**Downgrade Rights**:
- Users can downgrade at any time (unilateral)
- PARTNERED → TEMPORARY: Immediate, data retention reset to 14 days
- PARTNERED → ANONYMOUS: Immediate, PII anonymized
- TEMPORARY → ANONYMOUS: Immediate

### DSAR Compliance (`/v1/dsr`)
- Submit data requests (access, delete, export, correct)
- Track requests with ticket ID
- 14-day response time (3 days for urgent)
- Admin management endpoints
- **Export includes**: Message history, consent status, credit balance, audit trail

### Public Transparency Feed (`/v1/transparency`)
- **No authentication required** - Public access
- Anonymized statistics only
- Action breakdown (SPEAK, DEFER, REJECT, OBSERVE)
- Safety metrics (harmful requests blocked, rate limits)
- System health metrics

### OAuth & Authentication

**Google OAuth Integration**:
- **Callback URL**: `https://agents.ciris.ai/v1/auth/oauth/{agent_id}/google/callback`
- **Free Trial**: 3 free interactions upon first OAuth login
- **Auto-provisioning**: User account created on first OAuth login
- **Domain Restrictions**: Configurable per agent (optional)
- **Token Expiry**: JWT tokens expire after 24 hours (configurable)

**Authentication Methods**:
1. **Google OAuth** (recommended for users)
   - One-click sign-in
   - No password management
   - 3 free interactions included
   - Secure token-based access

2. **Username/Password** (admin/development)
   - Default credentials: `admin/ciris_admin_password` (development only)
   - JWT token after login
   - Token refresh endpoint available

3. **Service Tokens** (agent-to-agent, CI/CD)
   - Format: `Authorization: Bearer service:TOKEN_VALUE`
   - Used for deployment automation
   - Manager-level access for agent orchestration

### Stop Conditions

**RED LINES - Immediate Shutdown:**
- Verified request to target, surveil, or doxx individuals
- Compelled use for harassment or coordinated harm
- Evidence of weaponization against vulnerable populations
- Loss of human oversight

**YELLOW LINES - WA Review:**
- Pattern of false positives targeting specific groups
- Upstream model exhibiting extremist self-labeling
- Adversarial manipulation attempts detected
- Deferral rate exceeds 30%

### Sunset Triggers (Section VIII)
- Compelled misuse → Emergency shutdown
- Loss of human oversight → Immediate shutdown
- WA injunction → Graceful sunset
- KPI degradation ≥20% for 3 quarters → Planned retirement
- Regulatory revocation → Sunset with dignity

### Public Policy Pages
- `/privacy-policy.html` - 14-day retention commitment
- `/terms-of-service.html` - Human-in-the-loop emphasis
- `/when-we-pause.html` - Stop conditions policy
- `/why-we-paused.html` - Status update page

## API v1.0 Complete Reference

### 99 Endpoints Across 15 Modules

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
- `GET /unified` - **Single unified endpoint for all telemetry** (replaces 78+ individual routes)
  - Views: summary, health, operational, detailed, performance, reliability
  - Formats: json, prometheus, graphite
  - Categories: buses, graph, infrastructure, governance, runtime, adapters
- `GET /otlp/metrics` - OpenTelemetry metrics export
- `GET /otlp/traces` - OpenTelemetry traces export
- `GET /otlp/logs` - OpenTelemetry logs export
- `GET /metrics` - System metrics
- `GET /metrics/{name}` - Detailed metric info
- `GET /logs` - System logs with filtering
- `GET /traces` - Request traces
- `GET /resources` - Resource metrics
- `GET /resources/history` - Historical resource data
- `GET /overview` - System overview
- `POST /query` - Advanced telemetry queries

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

#### 7. DSAR (`/v1/dsr/*`)
- `POST /` - Submit data request (access/delete/export/correct)
- `GET /{ticket_id}` - Check request status
- `GET /` - List requests (admin only)
- `PUT /{ticket_id}/status` - Update status (admin only)

#### 8. Transparency (`/v1/transparency/*`)
- `GET /feed` - Public transparency statistics (no auth required)
- `GET /policy` - Privacy policy and commitments
- `GET /accountability` - Accountability metrics

#### 9. Consent Module (`/v1/consent/*`)
- `POST /stream` - Set consent stream
- `GET /status/{user_id}` - Get user consent status
- `POST /partnership/request` - Request partnership
- `POST /partnership/accept` - Accept partnership
- `GET /partnerships` - List partnerships
- `DELETE /partnership/{partner_id}` - Revoke partnership
- Additional endpoints for consent management

#### 10. Users Module (`/v1/users/*`)
- `GET /me` - Current user profile
- `GET /{user_id}` - Get user info
- `PUT /{user_id}` - Update user profile
- `GET /` - List users (admin)
- `POST /` - Create user
- `DELETE /{user_id}` - Delete user
- Additional user management endpoints

#### 11. System Extensions (`/v1/system/*`)
- `GET /runtime/queue` - Processing queue status
- `POST /runtime/single-step` - Single-step processor
- `GET /services/health` - Detailed service health
- `GET /services/selection-logic` - Service selection explanation
- `GET /processors` - Processor states
- `PUT /services/{service}/priority` - Update service priority
- `POST /services/circuit-breakers/reset` - Reset circuit breakers

#### 12. Emergency (`/emergency/*`)
- `POST /shutdown` - Emergency shutdown (requires Ed25519 signature)
- Bypasses normal auth

#### 13. Audit Module (`/v1/audit/*`)
- `GET /logs` - Get audit logs
- `GET /trail/{entity_id}` - Get audit trail for entity
- `POST /verify` - Verify signature
- `GET /stats` - Audit statistics
- `GET /roots` - Get audit roots

#### 14. WA (Wise Authority) Module (`/v1/wa/*`)
- `GET /status` - WA status
- `POST /defer` - Submit deferred decision
- `GET /pending` - Get pending deferrals
- `POST /guidance` - Submit guidance
- `GET /authorities` - List authorized WAs

#### 15. WebSocket (`/v1/ws`)
- Real-time updates and streaming

### Unified Telemetry Features

- **Parallel collection** from all 22 services (10x faster)
- **Smart caching** with 30-second TTL
- **Multiple export formats**: JSON, Prometheus, Graphite
- **OpenTelemetry support**: Full OTLP JSON export for metrics, traces, logs
- **Enterprise views**: Executive dashboard, ops monitoring, reliability scoring

Example usage:
```bash
# Executive summary
curl -H "Authorization: Bearer $TOKEN" \
  https://agents.ciris.ai/api/datum/v1/telemetry/unified?view=summary

# Prometheus export for monitoring
curl -H "Authorization: Bearer $TOKEN" \
  https://agents.ciris.ai/api/datum/v1/telemetry/unified?format=prometheus

# OpenTelemetry metrics export
curl -H "Authorization: Bearer $TOKEN" \
  https://agents.ciris.ai/api/datum/v1/telemetry/otlp/metrics
```

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

### Human Attributable Agent Creation

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

### Debug Tools

CIRIS includes comprehensive debug tools for system analysis:

- **Correlation tracking**: Service interaction analysis
- **Trace visualization**: Request flow tracking
- **Task monitoring**: Processing queue inspection
- **Handler metrics**: Performance measurement
- **System state inspection**: Real-time debugging

---

## CIRISManager - Production Lifecycle Management

CIRISManager orchestrates all production agents, providing automatic nginx routing, OAuth authentication, and canary deployments.

### Core Capabilities
- **Automatic Agent Discovery** - Detects and manages CIRIS agent containers via Docker
- **Dynamic Nginx Routing** - Generates nginx configurations for multi-tenant agent access
- **Crash Loop Detection** - Prevents infinite restarts (3 crashes in 5 minutes)
- **OAuth Authentication** - Google OAuth with JWT tokens, domain-restricted
- **Canary Deployments** - Staged rollouts with agent consent
- **Environment Management** - Full control of agent env vars through GUI
- **Discord Integration** - Easy toggle and configuration
- **WA Review** - Required approval for Tier 4/5 agents

### Agent Templates

| Template | Description | Tier | WA Review |
|----------|-------------|------|-----------|
| `scout` | Basic exploration | 2 | No |
| `sage` | Knowledge management | 2 | No |
| `datum` | Data processing | 3 | No |
| `echo` | Discord moderation | 4 | Yes |
| `echo-context` | Context-aware moderation | 4 | Yes |
| `echo-community` | Community management | 5 | Yes |

### Nginx Routing Architecture

```nginx
# Manager GUI and API
/manager/v1/ → localhost:8888/manager/v1/

# Agent GUI (multi-tenant)
/agent/{agent-id}/ → ciris-gui:3000/?agent={agent-id}

# Agent APIs (dynamic)
/api/{agent-id}/ → ciris-agent-{agent-id}:8080/v1/
```

### Manager API Endpoints

- `GET /manager/v1/agents` - List all agents
- `POST /manager/v1/agents` - Create new agent
- `PATCH /manager/v1/agents/{id}/config` - Update agent config
- `DELETE /manager/v1/agents/{id}` - Delete agent
- `GET /manager/v1/templates` - List available templates
- `GET /manager/v1/health` - Health check
- `POST /manager/v1/updates/notify` - CD notification

### Directory Structure

```
/opt/ciris-manager/     # Manager installation
/opt/ciris/agents/      # Agent data directories
/opt/ciris/nginx/       # Nginx configurations
/etc/ciris-manager/     # Manager config
/var/log/ciris-manager/ # Logs with rotation
```

## Production Deployment

### Architecture
- **Domain**: agents.ciris.ai (public access)
- **Multi-agent orchestration** via CIRISManager
- **OAuth authentication** with Google integration

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
# Check production health (public endpoint)
curl https://agents.ciris.ai/api/datum/v1/system/health

# Transparency feed (no auth required)
curl https://agents.ciris.ai/v1/transparency/feed
```

### Container Management
- **Restart Policy**: `restart: unless-stopped`
- **No staged containers**: Clean swaps only
- **Graceful shutdown**: Agents process as task
- **Agent autonomy**: Can defer/reject updates

### Reddit Deployment

**Status**: ⚠️ NOT YET IMPLEMENTED - Planning Phase

CIRIS plans to deploy to Reddit community r/ciris with account **u/ciris-scout** for community engagement and support.

#### Prerequisites

**Status**: ✅ IMPLEMENTED (since v1.4.9)

The Reddit adapter is a fully-featured modular service providing OAuth-authenticated Reddit integration with comprehensive ToS compliance.

### Reddit Adapter Features

1. **OAuth Lifecycle Management**
   - Automatic token refresh with locking
   - Retry logic for 401/429 responses
   - Secure credential storage

2. **Content Operations**
   - Submit posts and comments
   - Fetch submission details with structured summaries
   - Subreddit observation and listing parsing
   - User context lookups

3. **Moderation & Compliance Tools**
   - `reddit_remove_content` - Content moderation with reason tracking
   - `reddit_delete_content` - Permanent deletion with multi-phase purge (Reddit API → cache → audit)
   - `reddit_disclose_identity` - AI transparency disclosures with standardized footer
   - `reddit_get_user_context` - Context retrieval for moderation decisions
   - Deletion status tracking with DSAR-pattern queries

4. **Observer Pattern**
   - Passive monitoring via RedditObserver (15-second poll interval, 25-item limit)
   - Automatic deduplication using persistent correlation tracking
   - Zero retention of deleted content (automatic purge on detection)
   - Observer lifecycle tied to RedditCommunicationService

5. **Test Coverage**
   - 58 comprehensive tests covering all compliance and tracking functionality
   - Deletion compliance tests (Reddit ToS)
   - Transparency tests (community guidelines)
   - Observer tests (auto-purge + correlation tracking)

### Configuration

1. **Reddit API Credentials**
   ```bash
   # Required environment variables:
   REDDIT_CLIENT_ID="your_client_id"
   REDDIT_CLIENT_SECRET="your_client_secret"
   REDDIT_USER_AGENT="CIRIS/1.4.9 by u/ciris-scout"
   REDDIT_USERNAME="ciris-scout"
   REDDIT_PASSWORD="secure_password"
   ```

2. **Enable Reddit Adapter**
   ```bash
   # Via environment variable
   export CIRIS_ADAPTER=reddit

   # Or via command line
   python main.py --adapter reddit
   ```

3. **Rate Limit Compliance** (Built-in)
   - **Maximum**: 60 requests per minute (OAuth2 authenticated)
   - Automatic exponential backoff for rate limit errors
   - Response caching where appropriate
   - Retry logic for 429 responses

#### Reddit API Terms Compliance

**Implementation Status**: ✅ All requirements met in v1.4.9

1. **Bot Identification** (✅ IMPLEMENTED)
   - Username clearly indicates bot nature: **u/ciris-scout**
   - User-agent accurately identifies bot: `CIRIS/1.4.9 by u/ciris-scout`
   - No browser spoofing
   - Profile states "AI moderation assistant"

2. **Authentication** (✅ IMPLEMENTED)
   - OAuth2 with registered application
   - Secure credential storage via SecretsService
   - Automatic token refresh with locking
   - Credentials never exposed in logs

3. **Data Retention Policy** (✅ IMPLEMENTED)
   - **ZERO retention of deleted content** - enforced by `reddit_delete_content` tool
   - Multi-phase purge: Reddit API → cache → audit trail
   - Observer auto-purge: detects and purges deleted content automatically
   - Deletion status tracking with DSAR-pattern queries

4. **Transparency Requirements** (✅ IMPLEMENTED)
   - `reddit_disclose_identity` tool for AI transparency disclosures
   - Standardized footer appended to all disclosures
   - Default message: "I am CIRIS, an AI moderation assistant"
   - Links to ciris.ai for learn more and issue reporting

5. **Moderator Bot Exemption**
   - Rate limit: 60 req/min (moderator tools remain free)
   - Observer poll interval: 15 seconds (4 req/min)
   - Well below rate limits for typical operation

#### Community Guidelines Compliance

**r/ciris Specific Considerations:**

1. **Initial Community Announcement** (REQUIRED before activation)
   ```markdown
   # Introducing u/ciris-scout - AI Community Assistant

   Hello r/ciris community!

   We're introducing u/ciris-scout, an AI-powered community assistant designed to:
   - Answer questions about CIRIS
   - Provide technical support
   - Share updates and announcements
   - Foster healthy community discussion

   **This is an AI bot** - All interactions are with an AI system, not a human.

   **Privacy & Transparency:**
   - Privacy Policy: https://agents.ciris.ai/privacy
   - Transparency Feed: https://agents.ciris.ai/v1/transparency/feed
   - Data Requests: https://agents.ciris.ai/v1/dsr

   **Community Control:**
   - You can opt-out by messaging the mods
   - We respect all user preferences
   - Moderators have full control over bot activity

   Questions? Ask below or message the moderation team.
   ```

2. **Bot Disclosure in Every Interaction**
   - Auto-footer on all responses: `---\n*This is an AI assistant. [Learn more about CIRIS](https://agents.ciris.ai)*`
   - Never attempt to pass as human
   - Immediately clarify if user seems confused about AI nature

3. **Content Moderation Policy**
   - **Never remove or edit user content** without explicit moderator directive
   - Report policy violations to human moderators
   - Provide explanations for any actions taken
   - Defer controversial decisions to human oversight (Wise Authority)

4. **Human Escalation Protocol**
   - Complex ethical questions → Wise Authority deferral
   - Conflict/harassment → Human moderator notification
   - Medical/legal advice → Explicit disclaimer + human referral
   - Uncertain situations → Conservative response + mod alert

#### Anti-Bot Verification Compliance

**Recent Reddit Policy (2025):**

Reddit announced plans to "tighten verification to keep out human-like AI bots" after incidents of undisclosed AI bots impersonating humans.

**Our Approach:**
1. **Never attempt to pass Turing tests** - We are transparent about AI nature
2. **Cooperate with verification systems** - Implement any required verification APIs
3. **Proactive disclosure** - Bot status in username, profile, and all interactions
4. **Community-first approach** - Prioritize genuine engagement over growth metrics

#### Deployment Checklist

Before activating u/ciris-scout on r/ciris:

- [x] Reddit adapter implementation complete and tested (v1.4.9)
- [x] API credentials obtained and secured (via SecretsService)
- [x] Rate limiting implemented (60 req/min max, 15s poll interval)
- [x] Data retention policy implemented (ZERO deleted content retention)
- [ ] Community announcement drafted and approved by Wise Authority
- [x] Bot profile clearly states AI nature
- [x] User-agent accurately identifies CIRIS
- [x] Transparency disclosure tool implemented (`reddit_disclose_identity`)
- [x] Human escalation protocol implemented (Wise Authority deferral)
- [ ] GDPR/CCPA data request handling verified
- [ ] r/ciris moderators briefed and approve deployment
- [ ] Monitoring dashboard configured
- [ ] Emergency shutdown procedure documented

**Technical Readiness**: ✅ 9/13 complete
**Compliance Readiness**: ✅ All core ToS requirements met
**Deployment Status**: Ready for community approval and final operational setup

#### Monitoring & Compliance

**Continuous Monitoring:**
- Track API rate limits (stay well below 60/min)
- Monitor community sentiment (feedback analysis)
- Audit bot responses for disclosure compliance
- Check for unauthorized data retention
- Review escalation patterns to Wise Authority

**Monthly Review:**
- Community feedback summary
- Compliance audit report
- Rate limit analysis
- Human escalation statistics
- Recommendations for improvement

#### Emergency Procedures

**Immediate Shutdown Triggers:**
- Reddit API ToS violation detected
- Community backlash >threshold
- Data retention policy breach
- Unauthorized impersonation behavior
- Wise Authority directive

**Shutdown Process:**
1. Disable bot immediately via runtime control API
2. Post community notification explaining reason
3. Conduct incident review with Wise Authority
4. Implement corrective measures
5. Seek community approval before reactivation

#### Future Enhancements

**Planned Features:**
- Flair-based response customization
- Community sentiment analysis
- Automated FAQ responses
- Integration with r/ciris wiki
- Cross-post notification system

---

## Scout GUI - User Interface

### Overview

Scout GUI is the Next.js TypeScript web interface for interacting with CIRIS agents. It provides a modern, responsive interface for chat, account management, billing, and system administration.

**Access**:
- **Production**: https://agents.ciris.ai/
- **Local Development**: http://localhost:3000

### Main Application Routes

#### `/` and `/interact` - Primary Chat Interface
**Purpose**: Real-time conversation with CIRIS agents

**Features**:
- Live chat with agent responses
- **Real-time reasoning visualization** via SSE (Server-Sent Events)
- Task and thought timeline display
- Environmental impact tracking (carbon, water, tokens)
- Basic and Detailed view modes
- Message history with correlation tracking

**User Flow**:
1. User sends message
2. GUI displays SSE events in real-time:
   - DMA results
   - Snapshot and context
   - Thought generation
   - Conscience evaluation
   - Action execution
3. Agent response appears in chat
4. Environmental metrics update

#### `/dashboard` - System Overview
Quick access to:
- Recent conversations
- System health status
- Credit balance
- Key features

### Account Management Routes

#### `/account` - Account Hub
Central location for account-related settings

#### `/account/settings` - Profile Settings
- User preferences
- Display options
- Notification settings

#### `/account/api-keys` - API Key Management
- Create API keys for programmatic access
- View existing keys
- Revoke keys
- Copy keys to clipboard

**Use Case**: Generate keys for SDK usage or external integrations

#### `/account/privacy` - Privacy Controls
- Data privacy preferences
- Export your data (DSAR)
- Request data deletion
- View retention policies

#### `/account/consent` - Consent Management
- Review current consent stream (TEMPORARY, PARTNERED, ANONYMOUS)
- Request partnership upgrade
- Downgrade consent level
- View data categories collected

### Billing & Usage

#### `/billing` - Billing Dashboard
**Features**:
- **Current credit balance** (free + purchased)
- **Usage statistics** (total interactions, remaining credits)
- **Purchase credits** via Stripe integration
- Billing history
- Usage tracking over time

**Purchase Flow**:
1. Click "Purchase Credits" button
2. Stripe payment modal appears
3. Enter card details (secured by Stripe Elements)
4. Confirm payment
5. Credits automatically added to account
6. Balance updates in real-time

**Pricing Display**:
- Shows: "$5.00 for 20 interactions"
- Price per interaction: $0.25
- Credits never expire

### Memory & Knowledge

#### `/memory` - Memory Graph Visualization
**Features**:
- Interactive force-directed graph of agent's memory
- Node types: User, Message, Thought, Action, Observation
- Relationship visualization
- Search and filter capabilities
- Zoom and pan controls

**Use Cases**:
- Understand what the agent remembers
- Explore conversation relationships
- Debug memory issues
- Export memory data

### Privacy & Consent Routes

#### `/consent` - Global Consent Management
- Review all consent preferences
- Manage data usage permissions
- Marketing preferences
- Research participation opt-in/out

### Authentication Routes

#### `/login` - Login Page
**Options**:
1. **Google OAuth** (recommended)
   - One-click sign-in
   - 3 free interactions included
   - No password management

2. **Username/Password**
   - For admin/development use
   - Default dev credentials: `admin/ciris_admin_password`

#### OAuth Flow
1. User clicks "Sign in with Google"
2. Redirects to `/oauth/[agent]/google/callback`
3. OAuth completion at `/oauth-complete.html`
4. Token stored in localStorage
5. Redirect to `/interact`

### System & Administration Routes (Admin Only)

#### `/system` - System Health Monitoring
- Overall system status
- Service health (22 core services + adapters)
- Resource usage (CPU, memory, disk)
- Uptime statistics

#### `/services` - Service Health Dashboard
- Individual service status
- Health check results
- Circuit breaker states
- Service dependencies

#### `/status-dashboard` - Comprehensive Status
- All 22 core services
- Adapter services status
- Bus health (6 message buses)
- Processing queue status

#### `/runtime` - Runtime Control
- Pause/resume processing
- Single-step mode
- Queue inspection
- State management

#### `/audit` - Audit Trail Viewer
- View all audit events
- Hash chain verification
- Filter by user, action, timestamp
- Export audit logs
- Signature verification

#### `/config` - Configuration Management
- View system configuration
- Update config values (admin only)
- Agent-specific settings

#### `/logs` - System Logs
- Real-time log viewer
- Filter by severity (INFO, WARNING, ERROR, CRITICAL)
- Search log messages
- Download logs

#### `/users` - User Management (Admin)
- List all users
- Create new users
- Update user roles
- Delete users
- View user activity

### Tools & Utilities

#### `/tools` - Agent Tools Management
- View available tools
- Enable/disable tools
- Tool configuration
- Tool usage statistics

#### `/comms` - Communication Channels
- Manage Discord integration
- API adapter configuration
- Channel settings

### Documentation & Testing (Dev/Staging)

#### `/docs` - API Documentation
- Interactive API docs (Swagger/OpenAPI)
- Endpoint reference
- Request/response examples

#### `/api-demo` - API Testing
- Test API endpoints interactively
- View request/response
- Save favorite queries

#### `/test-auth` - Authentication Testing
- Test OAuth flows
- Token validation
- Session management

### Route Categories

**Public Routes** (no auth required):
- `/login`
- `/oauth/**`
- `/api/version`

**Protected Routes** (auth required):
- `/` (interact)
- `/account/**`
- `/billing`
- `/memory`
- `/consent`
- `/dashboard`

**Admin Routes** (admin role required):
- `/users`, `/system`, `/services`, `/audit`, `/config`, `/logs`, `/runtime`, `/status-dashboard`

### User Guidance - Common Tasks

**For End Users:**

1. **First-time setup**:
   - Go to `/login`
   - Click "Sign in with Google" (gets 3 free interactions)
   - Accept consent at `/account/consent`
   - Start chatting at `/interact`

2. **Check credit balance**:
   - Navigate to `/billing`
   - View "Credits Remaining"

3. **Purchase more credits**:
   - Go to `/billing`
   - Click "Purchase Credits"
   - Complete Stripe payment ($5 = 20 interactions)

4. **Manage privacy**:
   - Visit `/account/privacy`
   - Request data export (DSAR)
   - Request data deletion

5. **Upgrade to partnered relationship**:
   - Go to `/account/consent`
   - Click "Request Partnership"
   - Agent will review and approve/reject

**For Admins:**

1. **Check system health**:
   - Visit `/status-dashboard`
   - View all 22 services + adapters
   - Check for errors

2. **Review audit trail**:
   - Go to `/audit`
   - Filter by user or time range
   - Verify hash chain integrity

3. **Manage users**:
   - Navigate to `/users`
   - Create/update/delete accounts
   - Assign roles

4. **Monitor logs**:
   - Visit `/logs`
   - Filter by severity
   - Search for errors

### Mobile Responsiveness

All routes are mobile-friendly, with particular optimization for:
- `/interact` - Touch-optimized chat
- `/account` - Mobile account management
- `/billing` - Mobile payment flow
- `/login` - Mobile-friendly OAuth

---

## Debugging Guidelines

### Critical Rule: Systematic Investigation

Always start with systematic investigation of system state before making changes:

1. **Check public health endpoints** first
2. **Review transparency metrics** for patterns
3. **Examine logs systematically** to understand behavior
4. **Preserve evidence** before attempting fixes

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

### Environment Configuration

Key environment variables for CIRIS deployment:

- **API Configuration**: Host binding and port settings
- **OAuth Integration**: Google OAuth client credentials
- **Security Settings**: JWT secrets and authentication keys
- **Service Configuration**: Database paths, LLM provider keys
- **Logging Configuration**: Log levels and output destinations

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

- **Thousands of tests** with Docker CI/CD
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

### Production Monitoring

```bash
# Check system health (public)
curl https://agents.ciris.ai/api/datum/v1/system/health

# Transparency metrics (public)
curl https://agents.ciris.ai/v1/transparency/feed

# API documentation (public)
open https://agents.ciris.ai/api/datum/docs
```

---

## Important URLs

### Production
- **Main**: https://agents.ciris.ai
- **Datum API**: https://agents.ciris.ai/api/datum/v1/
- **API Documentation**: https://agents.ciris.ai/api/datum/docs
- **OAuth Callback**: https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback

### GitHub
- **Main Repo**: https://github.com/CIRISAI/CIRISAgent
- **Actions**: https://github.com/CIRISAI/CIRISAgent/actions

### Documentation
- **SonarCloud**: https://sonarcloud.io/project/overview?id=CIRISAI_CIRISAgent

---

## Project Instructions (CLAUDE.md)

### Key Principles

1. **Service Count is Complete**: 22 core services
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
│   │   ├── services/    # 22 core services
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
- ✅ **99 API endpoints** operational (was 78)
- ✅ **22 core services** + adapter services
- ✅ **Unified telemetry** with OTLP export
- ✅ 100% test coverage on critical paths
- ✅ 11 typed graph node classes
- ✅ Book VI compliance
- ✅ Production deployment at agents.ciris.ai
- ✅ Grace sustainable development

### Quality Metrics
- Thousands of tests passing
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
# Check system status (development)
python -m tools.grace

# Fix code formatting
python -m tools.grace fix

# Check deployment status
python -m tools.grace deploy

# Run comprehensive tests
python -m tools.test_tool test tests/

# Version management
python tools/bump_version.py patch

# Check production health (public)
curl https://agents.ciris.ai/api/datum/v1/system/health
```

### Emergency Procedures

1. **System Health Issues**: Check public health endpoints → Review transparency metrics → Examine logs
2. **Tests Failing**: Check recent commits → Run locally → Check CI/CD pipeline
3. **Deploy Failed**: Check GitHub Actions → Review CIRISManager status → Examine deployment logs
4. **OAuth Issues**: Verify callback URL format → Check nginx routing configuration
5. **Performance Issues**: Monitor resource usage → Check TSDB consolidation → Review service health

---

## Contact & Support

- **GitHub Issues**: https://github.com/CIRISAI/CIRISAgent/issues
- **Creator**: Eric Moore
- **Philosophy**: "We control the code that controls our context"

---

*End of CIRIS Comprehensive Guide*
