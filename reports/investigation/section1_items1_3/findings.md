# Section 1 (Items 1–3) — Grant Readiness Findings

Date: 2026-04-22 (UTC)
Scope: Verify grant claims for service inventory, ten-verb framework, and H3ERE conscience faculties.

## Item 1 — "22 microservices across three strata"

### Verdict
**Partial / contradictory naming.**

- The codebase does define **22 core services**.
- However, service organization in code is split into **6 categories** (Graph, Infrastructure, Lifecycle, Governance, Runtime, Tool), not 3 strata as claimed.
- There is also documentation/comment drift in at least one runtime file.

### Evidence

Primary canonical list in API service configuration:

- `Graph (7)` + `Infrastructure (4)` + `Lifecycle (4)` + `Governance (4)` + `Runtime (2)` + `Tool (1)` = **22**.
- Source: `ciris_engine/logic/adapters/api/service_configuration.py` lines 34–45 and 49–107.

Startup sequence also enumerates 22 named services in order:

- Source: `ciris_engine/logic/runtime/startup_logging.py` lines 13–20 and 26–49.

### Enumerated service inventory (from code)

| Service | Category in code | Path evidence | Purpose (from description/comments) |
|---|---|---|---|
| memory_service | Graph | `service_configuration.py` L50–52 | Graph-based memory storage/retrieval |
| consent_service | Graph | `service_configuration.py` L53–56 | Consent, retention, DSAR automation |
| config_service | Graph | `service_configuration.py` L57 | Configuration management |
| telemetry_service | Graph | `service_configuration.py` L58 | Telemetry collection/storage |
| audit_service | Graph | `service_configuration.py` L59 | Audit trail and compliance logging |
| incident_management_service | Graph | `service_configuration.py` L60 | Incident tracking and management |
| tsdb_consolidation_service | Graph | `service_configuration.py` L61 | Time-series consolidation |
| authentication_service | Infrastructure | `service_configuration.py` L66–70 | Auth + session management |
| resource_monitor | Infrastructure | `service_configuration.py` L71 | Resource monitoring |
| database_maintenance_service | Infrastructure | `service_configuration.py` L72 | DB maintenance operations |
| secrets_service | Infrastructure | `service_configuration.py` L73 | Secrets/credential management |
| time_service | Lifecycle | `service_configuration.py` L78 | Centralized time management |
| shutdown_service | Lifecycle | `service_configuration.py` L79 | Graceful shutdown coordination |
| initialization_service | Lifecycle | `service_configuration.py` L80 | Service initialization management |
| task_scheduler | Lifecycle | `service_configuration.py` L81 | Task scheduling/execution |
| wa_auth_system | Governance | `service_configuration.py` L87 | Wise Authority decision system |
| adaptive_filter_service | Governance | `service_configuration.py` L89 | Adaptive content filtering |
| visibility_service | Governance | `service_configuration.py` L90 | Visibility and monitoring |
| self_observation_service | Governance | `service_configuration.py` L91 | Self-monitoring/adaptation |
| llm_service | Runtime | `service_configuration.py` L96 | LLM integration |
| runtime_control_service | Runtime | `service_configuration.py` L97–101 | Runtime control |
| secrets_tool_service | Tool | `service_configuration.py` L105–106 | Secrets-management tool |

### Drift / gaps

1. **Three-strata claim mismatch**: repo code uses six categories, not three strata.
2. **Comment drift in API app state initializer (fixed in this branch)**:
   - `app.py` previously labeled "Infrastructure Services (7)" and "Runtime Services (3)" and grouped `task_scheduler` under runtime comments.
   - This branch updates comments/grouping to `Lifecycle Services (4)`, `Infrastructure Services (4)`, and `Runtime Services (2)` to match canonical service configuration.

### Recommended action

- **Ship-before-June-1**: revise grant copy to say "22 core services across six service categories" unless you explicitly define a translation layer from 6 categories -> 3 strata.
- **Done in this branch**: corrected category/count comments in `ciris_engine/logic/adapters/api/app.py` to eliminate auditor-visible inconsistency.

---

## Item 2 — "Ten-verb action framework"

### Verdict
**Confirmed (implemented).**

### Canonical definition

- `HandlerActionType` enum in `ciris_engine/schemas/runtime/enums.py` lines 52–71 contains:
  `OBSERVE, SPEAK, TOOL, REJECT, PONDER, DEFER, MEMORIZE, RECALL, FORGET, TASK_COMPLETE`.

### Implementation coverage evidence

All ten verbs are wired into the runtime dispatcher registry:

- `ciris_engine/logic/infrastructure/handlers/handler_registry.py` lines 45–56 map each enum action to a concrete handler class.

### Test coverage evidence

- Dedicated handler test files exist for 9/10 handlers under `tests/ciris_engine/logic/handlers/...`.
- `SPEAK` is covered in `tests/handlers/test_speak_handler.py`.
- Collection check found **147 tests** across the handler suite + conscience core subset in this pass.

### TODO/FIXME scan

- No TODO/FIXME markers found in action handler implementation files or `conscience/core.py` during this scoped pass.

### Recommended action

- **Ship-before-June-1**: include a compact matrix (verb -> enum -> handler -> test file) in grant appendix.
- **Ship-this-quarter**: standardize SPEAK tests path into the same handler-domain directory tree for consistency.

---

## Item 3 — "H3ERE Conscience Module with entropy, coherence, optimization veto, epistemic humility"

### Verdict
**Confirmed (implemented with tests), with one naming nuance.**

### Faculty implementations

1. `EntropyConscience` — `ciris_engine/logic/conscience/core.py` line 211
2. `CoherenceConscience` — `ciris_engine/logic/conscience/core.py` line 311
3. `OptimizationVetoConscience` — `ciris_engine/logic/conscience/core.py` line 409
4. `EpistemicHumilityConscience` — `ciris_engine/logic/conscience/core.py` line 509

### Input/output contract evidence

- Shared check input contract: `check(self, action: ActionSelectionDMAResult, context: ConscienceCheckContext)` across each faculty.
- Shared output contract: returns `ConscienceCheckResult` (includes faculty-specific fields in `ciris_engine/schemas/conscience/core.py` lines 109–127).

### Test coverage

- `tests/test_conscience_core.py` explicitly declares all four faculty test classes (lines 220, 424, 565, 724).
- File-level header also states all four are covered (lines 4–8).

### Nuance / risk

- Grant text says "faculties" as named components; code names are classes (`*Conscience`) rather than separate module-per-faculty packages. Functionally present, naming differs.

### Recommended action

- **Ship-before-June-1**: in grant copy, describe as "four conscience faculties implemented as dedicated `*Conscience` evaluators in `conscience/core.py`" to avoid semantics disputes.
- **Ship-this-quarter**: add a short architecture doc snippet mapping "faculty" term to concrete class names and schemas.

---

## Prioritized action list

### Ship-before-June-1
1. Align external copy: 22 services are confirmed, but architecture taxonomy is six categories in-code (unless a formal 3-strata mapping is added).
2. Validate no additional category/count drift remains outside `ciris_engine/logic/adapters/api/app.py` after this branch fix.
3. Add verb/faculty mapping appendix (enum -> implementation -> tests) for auditor-facing evidence.

### Ship-this-quarter
1. Normalize test file placement (move/alias SPEAK tests into `tests/ciris_engine/logic/handlers/external/`).
2. Add a single source-of-truth architecture taxonomy doc consumed by both grant docs and runtime comments.

### Nice-to-have
1. Auto-generate a markdown inventory from service configuration and handler registry as a CI artifact.

## Flagged-for-human

1. Decide whether to:
   - keep six-category language (most truthful to code), or
   - introduce an explicit documented mapping from six categories into the proposed three strata for grant narrative continuity.
