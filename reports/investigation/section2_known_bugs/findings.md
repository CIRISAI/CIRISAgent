# Section 2 — Known Bugs Verification (Pass 1)

Date: 2026-04-22 (UTC)

## Item 1 — ACCORD 5-minute vs 24-hour timestamp mismatch

### Verdict
**Confirmed mismatch in code comments/docstrings; implementation enforces 24 hours.**

### Evidence
- Canonical constant is 24 hours:
  - `ACCORD_TIMESTAMP_WINDOW_SECONDS = 86400` in `ciris_engine/schemas/accord.py`.
- Implementation uses the constant for validation:
  - `is_timestamp_valid()` compares `diff <= ACCORD_TIMESTAMP_WINDOW_SECONDS`.
- Tests also encode 24-hour semantics:
  - `tests/ciris_engine/logic/accord/test_accord_verifier.py` uses `25 hours ago` as expired case.

### Fix applied in this branch
- Updated `is_timestamp_valid()` docstring return description from "5-minute window" to "configured 24-hour window" to align docs with implementation and tests.

### Recommendation
- Keep **24-hour** window as the authoritative ACCORD replay tolerance unless security policy explicitly tightens asynchronous delivery assumptions.
- If moving to 5-minute policy later, update constant + tests + cross-language ACCORD implementations in one coordinated release.

---

## Items 2–4 (v2.6.2 batch, broken nav, /trust pricing)

## Item 2 — v2.6.2 security-fix batch (top 6)

### Verdict
**Located and partially verified from merged security release commit metadata + code presence checks.**

### Evidence
- Release commit located in history: `aa38b09e` (\"Security Release v2.6.2: Comprehensive Security Hardening\").
- Commit message explicitly references six high/critical security items including:
  1. service token revocation endpoint,
  2. SSRF protection in document download,
  3. secret-audit exception sanitization,
  4. smart-commit hook shell injection fix,
  5. path traversal protection (`validate_path_safety`),
  6. expanded `PROHIBITED_CAPABILITIES`.
- Representative code locations found in current tree:
  - revocation: `ciris_engine/logic/adapters/api/routes/auth.py` + `.../services/auth_service.py`
  - SSRF: `ciris_engine/logic/adapters/api/api_document.py` + SSRF tests
  - path traversal: `main.py` + `ciris_adapters/ciris_hosted_tools/services.py`
  - shell safety: `.githooks/smart-commit-hook.py` (`shell=False`)
  - prohibited capabilities: `ciris_engine/logic/buses/prohibitions.py`

### Targeted test signal (environment caveat)
- Ran targeted tests for revocation/SSRF/path utilities in this container.
- Result: mixed signal with substantial failures in `test_api_document.py` and some revocation/path tests under the current local pytest setup.
- This does **not** conclusively prove v2.6.2 regressions; it indicates a need for authoritative CI-baseline comparison in the project's fully provisioned environment.

### Recommendation
- Produce a strict checklist against the v2.6.2 six-item set with:
  - file-level fix evidence,
  - corresponding test IDs,
  - CI status on main.

### Next action
- Continue with item 3 (`/verify`, `/commons`, etc.) and item 4 (`/trust` pricing) deep diffs.

---

## Prioritized action list

### Ship-before-June-1
1. Finalize ACCORD timestamp policy wording in all docs/specs to match 24-hour implementation.
2. Finalize a v2.6.2 six-item status checklist from CI evidence (not only local environment runs).
3. Execute Section 2 items 3–4 deep validation and commit any low-risk diffs.

### Ship-this-quarter
1. Add a consistency check that fails CI if ACCORD window comments/docstrings diverge from constant value.
