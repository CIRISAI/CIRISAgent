# NLnet Grant Investigation Execution Plan (CIRISAgent)

This runbook turns the grant-readiness investigation prompts into an executable, checkpointed workflow that can be completed in focused sessions and converted into PR-ready artifacts.

## Why this plan

The investigation scope spans multiple repositories, multiple languages (Python, Rust, Lean, polyglot ACCORD), and production claims with strict evidence requirements. Running all sections in one session will produce incomplete evidence and high context drift.

This plan enforces:

1. **Evidence-first outputs** (file paths + line numbers + command output)
2. **Session-bounded deliverables** (one section per session)
3. **Grant deadline focus** (ship-before-June-1 priorities first)
4. **Humanity-first guardrails** (no medical capability expansion, no bypass patterns)

---

## Execution order (recommended)

### Phase A — Before June 1 (grant claim integrity)

1. Section 1: Grant-readiness verification
2. Section 2: Known bugs + trivial diffs
3. Section 8: Test coverage against thesis
4. Section 9: Undocumented invariants and API drift

### Phase B — Security + audit prep

5. Section 3: Security surface mapping
6. Section 10: Deployment and ops parity

### Phase C — Deep technical claim substantiation

7. Section 4: Polyglot ACCORD coherence
8. Section 5: Lean 4 theorem extraction
9. Section 6: RATCHET harness validation

### Phase D — Sustainability and roadmap truthfulness

10. Section 7: Bus-factor and succession
11. Section 11: Rust crates (separate sessions)
12. Section 12: Commons graph status

---

## Standard evidence bundle for each section

For every section, produce **all** of the following in the same branch:

1. `reports/investigation/<section>/findings.md`
2. `reports/investigation/<section>/evidence/commands.txt`
3. `reports/investigation/<section>/evidence/summary.json`
4. Optional patch files for low-risk fixes in `reports/investigation/<section>/patches/`

Each finding entry should include:

- Claim under test
- Verdict (`confirmed`, `partial`, `not_found`, `contradicted`)
- Evidence references (file path + line range, command output excerpt)
- Risk level (`critical`, `high`, `medium`, `low`)
- Recommendation (`code_fix`, `copy_revision`, `human_decision`)

---

## Session template (copy/paste)

Use this template at the beginning of each investigation session:

```markdown
## Scope
Section X — <title>

## Commands run
- <command>

## Findings
- [ID] <claim>: <verdict>
  - Evidence: <path:lines>, <command output>
  - Gap: <what does not hold>
  - Recommendation: <specific fix>

## Prioritized actions
### Ship-before-June-1
- ...

### Ship-this-quarter
- ...

### Nice-to-have
- ...

## Flagged-for-human
- ...
```

---

## Section-specific accelerator commands

> Run from repository root.

### Service + architecture inventory

```bash
rg "class .*Service|def .*service|ServiceRegistry|register" ciris_engine ciris_adapters
```

### Ten-verb action framework inventory

```bash
rg "OBSERVE|SPEAK|TOOL|MEMORIZE|RECALL|FORGET|REJECT|PONDER|DEFER|TASK_COMPLETE" ciris_engine tests
```

### H3ERE faculty discovery

```bash
rg "entropy|coherence|optimization veto|epistemic humility|H3ERE|conscience" ciris_engine tests
```

### Endpoint inventory seed

```bash
rg "@router\.(get|post|put|patch|delete)|APIRouter|add_api_route" ciris_engine
```

### OAuth + retention claims

```bash
rg "oauth|google|retention|14.?day|delete|purge" ciris_engine config tests
```

### Audit chain and Ed25519

```bash
rg "Ed25519|ed25519|sign|verify|audit" ciris_engine ciris_sdk tests
```

### Env-var surface

```bash
rg "os\.environ|getenv|environ\[" ciris_engine ciris_adapters ciris_sdk tools
```

### Dead code candidate seed

```bash
python -m vulture ciris_engine ciris_adapters
```

---

## Acceptance criteria per section

A section is complete only when:

1. Every claim in that section has a verdict.
2. Every verdict has at least one concrete evidence reference.
3. Gaps are mapped to either a code diff or copy revision.
4. Actions are prioritized into the three required buckets.
5. Judgment-dependent items are explicitly flagged for human decision.

---

## Risk controls for this investigation

1. **Do not silently normalize claim drift.** If code and docs disagree, report both.
2. **Do not infer production state from local code alone.** Mark as unverified if deployment evidence is absent.
3. **Do not merge broad refactors during evidence gathering.** Keep fixes minimal and claim-linked.
4. **Do not expand prohibited domains.** Medical/clinical capability remains out of scope.

---

## Suggested branch strategy

- `investigation/section-1-grant-readiness`
- `investigation/section-2-known-bugs`
- `investigation/section-3-security-surface`
- ...

Keep each section atomic. If a section produces implementation fixes, split into:

- `investigation/...` for evidence/reporting
- `fix/...` for production code changes

---

## Immediate next step

Start with **Section 1, items 1–3 only** in the next session to establish:

1. Service count and strata evidence
2. Ten-verb framework canonical definition + tests
3. H3ERE faculties implementation and coverage

Then checkpoint findings before running full test-suite and endpoint/auth analysis.
