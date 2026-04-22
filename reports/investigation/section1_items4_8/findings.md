# Section 1 (Items 4–8) — Grant Readiness Findings (Pass 1)

Date: 2026-04-22 (UTC)
Scope: Claims 4–8 from Section 1 (tests count, endpoint count, audit chain, RAM, OAuth+retention).

## Item 4 — "3,500+ unit tests passing"

### Verdict
**Not yet confirmed as passing in this environment.**

### Evidence
- Collection-only run found **10,662 tests collected** before interruption due import/plugin issues.
- Collection failed with **37 collection errors**, including missing `pytest_asyncio` in this environment.
- Evidence log excerpt: `reports/investigation/section1_items4_8/evidence/pytest_collect_all_excerpt.txt`.

### Interpretation
- The "3,500+" magnitude is plausible based on collected volume.
- The specific claim "passing" is unverified here because the suite does not currently execute cleanly in this container.

### Recommended action
- **Ship-before-June-1**: produce a deterministic CI artifact with exact pass/fail/skip counts from a fully provisioned test env and attach to grant packet.

---

## Item 5 — "99 REST endpoints"

### Verdict
**Contradicted by static inventory (current pass).**

### Evidence
- Added static inventory tool: `tools/investigation/generate_endpoint_inventory.py`.
- Static decorator scan over API route modules currently reports **256 endpoints**.
- Evidence file: `reports/investigation/section1_items4_8/evidence/endpoints.json`.
- Added auth-dependency heuristic pass:
  - endpoints with auth-like dependency: **13**
  - endpoints without auth-like dependency: **243**
  - summary: `reports/investigation/section1_items4_8/evidence/endpoint_auth_summary.md`.

### Caveat
- This count is static/decorator-based and may include internal/setup/testing routes. A production-filtered OpenAPI export is still required for final claim language.
- Auth classification is heuristic and currently undercounts routes that enforce auth outside `Depends(...)` function signatures (middleware/route wrappers/service-layer checks).

### Recommended action
- **Ship-before-June-1**: replace claim "99 endpoints" with a versioned endpoint count generated from OpenAPI at release time.
- **Ship-this-quarter**: annotate each endpoint with auth/rate-limit/doc status in generated report.

---

## Item 6 — "Ed25519 audit chain"

### Verdict
**Partially confirmed; architecture present, end-to-end verb trace not yet completed in this pass.**

### Evidence
- Hash-chain schema includes `previous_hash` + signature fields:
  - `ciris_engine/schemas/audit/hash_chain.py`
  - persistence tables include `previous_hash` and `signature` columns in SQLite/Postgres schemas.
- ACCORD schema explicitly defines Ed25519 signature format + sign/verify helpers:
  - `ciris_engine/schemas/accord.py`.
- Audit chain verifier references re-anchor handling:
  - `ciris_engine/logic/audit/hash_chain.py`, `ciris_engine/logic/audit/verifier.py`.

### Gap
- This pass did not execute a full runtime SPEAK action and trace audit emission/persistence/verification end-to-end.

### Recommended action
- **Ship-before-June-1**: add an integration test that triggers `SPEAK` and asserts:
  1. audit entry emitted,
  2. previous hash linkage,
  3. signature verification success,
  4. persistence row present in audit DB.

---

## Item 7 — "228MB RAM per agent"

### Verdict
**Unverified in this pass.**

### Gap
- No controlled memory benchmark (cold-start, +100 msgs, +1,000 msgs) was executed yet.

### Recommended action
- **Ship-before-June-1**: run standardized benchmark harness with RSS snapshots and leak slope calculation.
- **Flagged-for-human**: decide authoritative deployment target environment for memory numbers (local Docker vs production container class).

---

## Item 8 — "OAuth2 via Google, 14-day rolling retention"

### Verdict
**Mostly confirmed in code, with operational verification pending.**

### Evidence (OAuth2 via Google)
- OAuth callback pattern and provider handling present in API auth routes:
  - `ciris_engine/logic/adapters/api/routes/auth.py` (`/auth/oauth/{provider}/login`, `/auth/oauth/{provider}/callback`, Google token verification flow).

### Evidence (14-day retention)
- Consent service defaults to 14-day temporary consent and includes hard-delete cleanup path:
  - `ciris_engine/logic/services/governance/consent/service.py` (14-day expiry + `cleanup_expired()` docs and delete routines).
- Partnership and handler references include 14-day expiry semantics:
  - `ciris_engine/logic/services/governance/consent/partnership.py`
  - `ciris_engine/logic/infrastructure/handlers/shared_helpers.py`.

### Gap
- This pass did not run a data-retention integration test proving expired data is actually deleted from storage layers in a live run.

### Recommended action
- **Ship-before-June-1**: add integration test that creates temporary consent data, advances clock >14 days, runs cleanup, and verifies graph+cache deletion.

---

## Prioritized action list

### Ship-before-June-1
1. Produce CI-backed test pass/fail/skip metrics in a fully provisioned environment (replace local collection-only evidence).
2. Replace static "99 endpoints" claim with generated OpenAPI-derived count and freeze it per release.
3. Add end-to-end SPEAK→audit-chain verification integration test.
4. Add 14-day retention deletion integration test (graph + cache verification).
5. Run RAM benchmark at cold / +100 / +1,000 messages with artifacted logs.

### Ship-this-quarter
1. Extend endpoint inventory tooling with authN/authZ/rate-limit metadata extraction.
2. Create one-click grant evidence exporter from investigation artifacts.

### Nice-to-have
1. Add CI job that fails if public claim constants (endpoint count/service taxonomy/test count) drift from generated evidence.

## Flagged-for-human

1. Decide whether public endpoint claim should count all routes or only external/public routes.
2. Decide canonical environment for RAM claim publication.
