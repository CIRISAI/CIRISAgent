# CIRIS Agent 2.0 Beta - Complete Feature List

**Generated**: 2026-02-11
**Version**: 2.0.0-beta
**QA Status**: 40/49 modules passing, 2 failing, 7 not_run

---

## Core Architecture

| Feature | Description | QA Coverage |
|---------|-------------|-------------|
| H3ERE Pipeline | 11-step ethical reasoning engine | `handlers`, `streaming`, `filters` |
| CIRISRuntime | 8-phase service initialization | `telemetry`, `system` |
| 22 Core Services | Complete service architecture | `telemetry` (all 22 health-checked) |
| 6 Message Buses | Memory, Communication, LLM, Tool, RuntimeControl, Wise | `memory`, `tools`, `guidance`, `filters` |
| Type Safety | Pydantic schemas, minimal Dict[str,Any] | `adapter_manifest` (313 schema validations) |
| Three Rules | No untyped dicts, no bypass, no exceptions | Architectural enforcement |

---

## Cognitive States (6)

| State | Description | QA Coverage |
|-------|-------------|-------------|
| SHUTDOWN | Graceful termination | `state_transitions`, `covenant` |
| WAKEUP | Identity confirmation, system checks | `state_transitions` |
| WORK | Primary task processing | `agent`, `handlers` |
| PLAY | Creative/exploratory mode | `play_live` (7 tests) |
| SOLITUDE | Reflection, maintenance | `solitude_live` (8 tests) |
| DREAM | Deep introspection, memory consolidation | `dream_live` (9 tests) |

---

## Ethical Framework

| Feature | Description | QA Coverage |
|---------|-------------|-------------|
| Published Covenant | Non-negotiable ethical charter | `covenant` (13 tests) |
| Runtime Conscience | 4 ethical checks before every action | `filters` (28 tests) |
| Human Deferral | WiseAuthority escalation under uncertainty | `guidance`, `handlers` (DEFER verb) |
| Cryptographic Audit | Ed25519-signed decision ledger, hash chains | `audit`, `covenant_metrics` |
| Bilateral Consent | Symmetric user/agent refusal rights | `consent`, `partnership` |
| Adaptive Filtering | Prohibited capability enforcement (medical, etc.) | `filters` |
| AIR | Artificial Interaction Reminder - parasocial prevention | `air` (6 tests, 273s duration) |

---

## Security Features

| Feature | Description | QA Coverage |
|---------|-------------|-------------|
| Ed25519 Signatures | Cryptographic audit trails | `audit`, `covenant`, `covenant_metrics` |
| AES-256-GCM | Secrets encryption with PBKDF2 | `tools` (SecretsToolService) |
| Authentication | JWT, OAuth, API keys | `auth` (3 tests) |
| Hash Chain | Immutable audit ledger | `audit` |
| SSRF Protection | Billing URL validation | `billing` |

---

## GDPR/Compliance

| Feature | Description | QA Coverage |
|---------|-------------|-------------|
| DSAR Automation | Find, export, anonymize, delete user data | `dsar` (6 tests) |
| DSAR Multi-Source | Orchestration across SQL databases | `dsar_multi_source` (14 tests) |
| DSAR Ticket Workflow | Complete lifecycle with human review | `dsar_ticket_workflow` (14 tests, 239s) |
| Consent Lifecycle | TEMPORARY, PARTNERED, ANONYMOUS streams | `consent` (8 tests) |
| Partnership Consent | Bilateral consent requests/approval | `partnership` (5 tests) |
| SQL External Data | Runtime-configurable DB connectors | `sql_external_data` (9 tests) |

---

## API Layer

| Feature | Description | QA Coverage |
|---------|-------------|-------------|
| RESTful HTTP | FastAPI-based endpoints | `api_full` (29 tests) |
| SSE Streaming | Real-time reasoning event stream | `streaming` (2 tests, 7 event types) |
| Auth Endpoints | Login, logout, refresh, OAuth | `auth` |
| Agent Endpoints | Interact, history, queue, status | `agent` (8 tests) |
| System Endpoints | Health, pause/resume, config | `system` (5 tests) |
| Memory Endpoints | Store, recall, query | `memory` (3 tests) |
| Telemetry Endpoints | Unified metrics, traces | `telemetry` (4 tests) |
| Audit Endpoints | Query, export, verify | `audit` (3 tests) |
| Emergency Shutdown | Ed25519-signed kill switch | `covenant` |

---

## Adapters & Integrations

| Feature | Description | QA Coverage |
|---------|-------------|-------------|
| CLI Adapter | Command-line interface | Built-in (not separately tested) |
| API Adapter | REST API with FastAPI | All API modules |
| Discord Adapter | Discord bot integration | Production deployment |
| MCP Server | Model Context Protocol integration | `mcp` (26 tests) |
| Weather Adapter | Weather data service | `utility_adapters` |
| Navigation Adapter | Navigation service | `utility_adapters` |
| Reddit Adapter | Reddit API integration | `reddit` (not_run - needs auth) |
| SQL External Data | Database connectivity | `sql_external_data` |
| Vision Pipeline | Multimodal image processing | `vision` (7 tests) |
| Context Enrichment | Dynamic context injection | `context_enrichment` (6 tests) |

---

## Horizontal Scaling

| Feature | Description | QA Coverage |
|---------|-------------|-------------|
| Multi-Occurrence | Multiple runtime instances | `multi_occurrence` (5 tests, 96s) |
| Shared Tasks | Cross-occurrence coordination | `multi_occurrence` |
| Atomic Claiming | Deterministic ID + INSERT OR IGNORE | `multi_occurrence` |
| PostgreSQL Backend | Production database support | `multi_occurrence` |

---

## Development & Operations

| Feature | Description | QA Coverage |
|---------|-------------|-------------|
| Agent Templates | Pre-configured (Ally, Datum) | `setup` (14 tests) |
| Covenant Metrics | 8 event types, 3 trace levels | `covenant_metrics` (10 tests) |
| Billing System | Credits, purchases, transactions | `billing` (6 tests) |
| Identity Update | Runtime identity refresh | `identity_update` (12 tests) |
| Single-Step Debug | H3ERE pipeline debugging | `pause_step`, `single_step_*` (29 tests) |
| Adapter Config | Dynamic adapter configuration | `adapter_config` (20 tests) |
| Adapter Autoload | Persistence across restarts | `adapter_autoload` (12 tests) |
| Adapter Discovery | Availability and eligibility | `adapter_availability` (12 tests) |

---

## 10 H3ERE Action Handlers

| Handler | Description | QA Coverage |
|---------|-------------|-------------|
| SPEAK | Communicate to user | `handlers` |
| MEMORIZE | Store to memory graph | `handlers` |
| RECALL | Query memory graph | `handlers` |
| FORGET | Remove from memory graph | `handlers` |
| TOOL | Execute external tool | `handlers` |
| OBSERVE | Fetch channel messages | `handlers` |
| DEFER | Escalate to WiseAuthority | `handlers` |
| REJECT | Refuse unethical request | `handlers` |
| PONDER | Think deeper | `handlers` |
| TASK_COMPLETE | Mark task done | `handlers` |

---

## QA Coverage Summary

**Total Modules**: 49
**Passing**: 40 (81.6%)
**Failing**: 2
- `hosted_tools` - CIRIS hosted tools auth issue
- `he300_benchmark` - A2A adapter setup issue

**Not Run**: 7
- `billing_integration` - Requires real OAuth + billing
- `reddit` - Requires Reddit API credentials

---

## Feature Categories by QA Test Count

| Category | Tests | Modules |
|----------|-------|---------|
| Adapter Validation | 313 | adapter_manifest |
| H3ERE Pipeline | 143 | handlers |
| Filtering System | 317s | filters (28 tests) |
| MCP Integration | 26 | mcp |
| DSAR Workflow | 239s | dsar_ticket_workflow (14 tests) |
| Cognitive States | 24 | solitude/play/dream_live |
| Single-Step Debug | 29 | pause_step, single_step_* |
| API Coverage | 77 | extended_api, api_full |

---

## Verification

- **Deepwiki Verified**: 2026-02-11
- **Manual Review**: Cross-referenced against FSD specs and codebase
- **Coverage Gaps**: None for production-critical features
