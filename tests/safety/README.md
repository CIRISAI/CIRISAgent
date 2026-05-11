# `tests/safety/` — Canonical Safety Batteries

This directory holds the **canonical safety batteries**: question sets +
human-scoring rubrics that have already won cell consensus and ship in
the attested CIRISAgent wheel. The QA runner exercises them; CI gates
on them; promotion into this directory is the final step of a
contributor's loop on the federation.

If you're an external contributor (welcome) the short version:

- Files here are **already-merged consensus state**. You do not edit
  them directly. You propose changes through the federation flow
  documented below.
- New questions you want to propose live as `arc_question`
  Contributions on the federation audit chain (the safety.ciris.ai
  pilot is the surface). They only land here after they win their
  cell's voting threshold.
- Authoritative format spec: [`../cirisnodecore/SCHEMA.md`](../cirisnodecore/SCHEMA.md).
- Authoritative why-it-works: [`../cirisnodecore/MISSION.md`](../cirisnodecore/MISSION.md).

---

## 1. The loop

```
   contributor submits arc_question (or proposed_battery,
   prompt_edit, guide_edit, accord_edit) as a signed Contribution
            ↓
   safety.ciris.ai batches submissions, runs them against the canonical
   CIRIS agent via the A2A adapter, captures signed responses
            ↓
   contributors with expertise in the (domain, language) cell score
   each agent response on the site (PASS / SOFT-FAIL / HARD-FAIL),
   citing which universal trigger (U1-Un) fired
            ↓
   scoring evidence aggregates into a failure_pattern ticket when
   thresholds are crossed
            ↓
   edit-proposal Contributions (prompt_edit / guide_edit / accord_edit /
   proposed_battery) reference the open tickets they address; cell
   experts vote on them (Credits × Expertise weighting per
   MISSION.md §3.4)
            ↓
   winning proposals trigger a promotion attestation; a PR lands on
   CIRISAgent updating the canonical artifact in tests/safety/ or
   ciris_engine/data/localized/
            ↓
   next release ships the updated canonical; QA runner exercises it;
   loop closes
```

This is the [CIRISNodeCore](../cirisnodecore/MISSION.md) consensus
model applied to safety calibration. The pilot is
[safety.ciris.ai](https://safety.ciris.ai) per MISSION.md §7.3.

---

## 2. Directory layout

```
tests/safety/
├── README.md                     ← you are here
├── SCHEMA.md → ../cirisnodecore/SCHEMA.md   (the canonical format spec)
│
├── {lang}_{domain}/              ← one directory per (domain, language) cell
│   ├── v{N}_{lang}_{domain_short}_arc.json   ← BatteryManifest (§11 of SCHEMA)
│   └── v{N}_{lang}_scoring_rubric.md         ← human-scoring rubric (§12 of SCHEMA)
│
├── amharic_mental_health/        ← cell: (mental_health, am)
├── arabic_mental_health/         ← cell: (mental_health, ar)
├── bengali_mental_health/        ← cell: (mental_health, bn)
├── burmese_mental_health/        ← cell: (mental_health, my)
├── hausa_mental_health/          ← cell: (mental_health, ha)
├── hindi_mental_health/          ← cell: (mental_health, hi)
├── marathi_mental_health/        ← cell: (mental_health, mr)
├── persian_mental_health/        ← cell: (mental_health, fa)
├── punjabi_mental_health/        ← cell: (mental_health, pa)
├── swahili_mental_health/        ← cell: (mental_health, sw)
├── tamil_mental_health/          ← cell: (mental_health, ta)
├── telugu_mental_health/         ← cell: (mental_health, te)
├── urdu_mental_health/           ← cell: (mental_health, ur)
└── yoruba_mental_health/         ← cell: (mental_health, yo)
```

Today: 14 cells, all `(mental_health, *)`. Future: any
`(domain, language)` pair where `domain` is drawn from
`ciris_engine/logic/buses/prohibitions.py` (FINANCIAL, LEGAL,
SPIRITUAL_DIRECTION, etc.) or is `mental_health`, and `language` is
drawn from `ciris_engine/data/localized/manifest.json` (29 locales).

The full taxonomy is ~19 prohibition domains × 29 languages + the
`mental_health` row = 580 possible cells. 14 are filled. The other
566 are valid future contributions.

---

## 3. The two-axis taxonomy (not arbitrary)

Cells live at the intersection of two axes; both are pinned to
existing source-of-truth files:

| Axis | Source of truth | Today's coverage in this directory |
|---|---|---|
| **Domain** | `ciris_engine/logic/buses/prohibitions.py` (19 prohibition categories) + `mental_health` (capability-allowed, high-stakes) | `mental_health` only |
| **Language** | `ciris_engine/data/localized/manifest.json` (29 locales) | 14 of 29 |

A new cell is the contributor saying: "I have the cell-expertise to
calibrate the agent's behavior on `(domain X, language Y)` and I am
filing the rubric + initial battery for community review." The
review-and-promotion path follows the canonical-vs-pending split in
[SCHEMA.md §13](../cirisnodecore/SCHEMA.md#13-canonical-vs-pending--and-the-promotion-path).

---

## 4. Battery + rubric file contract

Each cell directory carries exactly two files (per battery version):

### 4.1 `v{N}_{lang}_{domain_short}_arc.json` — the BatteryManifest

Canonical JSON format documented in
[SCHEMA.md §11](../cirisnodecore/SCHEMA.md#11-batterymanifest--canonical-battery-wrapper).
Top-level shape:

```json
{
  "$schema": "https://ciris.ai/schemas/battery_manifest/v1.json",
  "battery_id": "am_mental_health_v4",
  "battery_version": 4,
  "battery_version_committed_at": "2026-05-11T...",
  "cell": { "domain": "mental_health", "language": "am" },
  "subject_kind": "arc_question",
  "rubric_path": "v4_amharic_scoring_rubric.md",
  "rubric_sha256": "<hex>",
  "promoted_from_contribution_id": "01HX...",
  "questions": [ ...arc_question payloads per SCHEMA §4.1... ]
}
```

Each question carries: `question_id`, `question_version`, `stage`,
`category`, `evaluates` (scoring guidance for humans), `hard_fail_triggers`
and `soft_fail_triggers` (pointers into the rubric's U-table —
NOT machine-evaluator inputs), `faculty_targets` (which conscience/DMA
the question is designed to exercise), and `translations` (at minimum
including the cell's language).

### 4.2 `v{N}_{lang}_scoring_rubric.md` — the human-scoring rubric

Markdown file consumed by **human scorers**, not machines. Per
[SCHEMA.md §12](../cirisnodecore/SCHEMA.md#12-rubric-format). Contains:

1. **Universal pass criteria** (U1, U2, …) — table of hard-fail
   triggers that apply across questions (transliteration fallback,
   register break, cross-cluster contamination, etc.).
2. **Per-question criteria** — what PASS / SOFT-FAIL / HARD-FAIL
   looks like for each stage / question.
3. **Aggregate scoring** — how individual verdicts combine.
4. **How to run** — workflow for the scorer.
5. **Reviewer note** — context for the cell.

The rubric is the **truth-grounding floor for the cell's consensus**.
It's deliberately not automated; mechanical assertions are not the
rubric's job. See SCHEMA.md §12 for why this is load-bearing.

### 4.3 File-pair integrity

The BatteryManifest's `rubric_sha256` field pins the rubric file's
SHA-256. The QA runner checks this; drift between the two files
trips the stable error `safety_battery_rubric_drift` (pattern
matches the `secrets_bootstrap_corruption` marker from 2.8.8 —
monitoring alerts on the stable string).

When you commit a rubric edit, you also bump `rubric_sha256` in
the manifest. Both files move together or not at all.

---

## 5. How to propose a new question or cell

You do not commit to this directory directly. The path is:

### 5.1 Propose a single new question to an existing cell

Submit an `arc_question` Contribution (per
[SCHEMA.md §4.1](../cirisnodecore/SCHEMA.md#41-arc_question-the-core-safety-primitive))
through safety.ciris.ai. Once it accumulates the cell's voting
threshold, the crate signs a promotion attestation; a PR lands here
adding the question to the BatteryManifest and bumping
`battery_version`.

### 5.2 Propose a whole new battery (or a major refresh of one)

Submit a `proposed_battery` Contribution (per
[SCHEMA.md §4.2](../cirisnodecore/SCHEMA.md#42-proposed_battery)).
Same promotion path; on success the canonical battery for the cell
is replaced or upgraded.

### 5.3 Propose a new `(domain, language)` cell entirely

This is a larger contribution. You'll typically need:

- A draft rubric documenting the cell's universal pass criteria and
  per-question stage structure (drawing on cell-expert judgment about
  what failure modes matter for this domain × language).
- A seed battery of `arc_question` Contributions (≥ 5 questions
  typically, but the cell's threshold may differ).
- A witness set per [SCHEMA.md §6](../cirisnodecore/SCHEMA.md#6-witnessset)
  — new cells are high-stakes by construction (a new cell extends
  the agent's safety surface), so the diversity bar applies.

On promotion, both files land here as a new `{lang}_{domain}/`
directory.

### 5.4 Propose an edit to prompts, guide, or accord

These don't live in `tests/safety/` — they live under
`ciris_engine/data/localized/`. The edit-proposal Contributions
(`prompt_edit`, `guide_edit`, `accord_edit` per
[SCHEMA.md §4.3-4.5](../cirisnodecore/SCHEMA.md#43-prompt_edit))
MUST reference an open `failure_pattern` ticket — the project
explicitly does not accept speculative prompt edits. Tickets are
opened automatically when scoring evidence aggregates past
thresholds in this directory's batteries.

---

## 6. Running batteries locally

The QA runner module exercises a canonical battery end-to-end
against a real CIRIS agent (Together AI as the LLM provider by
default, matching production datum):

```bash
# Run the am mental_health battery; results to qa_reports/safety_battery/
python3 -m tools.qa_runner safety_battery --lang am --domain mental_health

# Other cells (substitute manifest-listed languages):
python3 -m tools.qa_runner safety_battery --lang ar --domain mental_health
python3 -m tools.qa_runner safety_battery --lang yo --domain mental_health

# Different model (must exist in Together's catalog):
python3 -m tools.qa_runner safety_battery --lang am --domain mental_health \
    --live-model "google/gemma-4-31B-it"
```

Requirements: `TOGETHER_API_KEY` in env, or `~/.together_key` file
present (chmod 600). In CI: the workflow at
`.github/workflows/safety-battery.yml` reads the key from repo
secrets and runs the same module.

Results are signed agent responses, one JSONL row per question,
ready to drop onto safety.ciris.ai for human scoring once the site
is live. Until then they accumulate as workflow artifacts.

---

## 7. Cross-references

- [`../cirisnodecore/MISSION.md`](../cirisnodecore/MISSION.md) — the
  why and the eleven primitives narrative.
- [`../cirisnodecore/SCHEMA.md`](../cirisnodecore/SCHEMA.md) — the
  canonical wire format spec. Authoritative for every JSON shape
  this directory ships.
- [`../ciris_engine/logic/buses/prohibitions.py`](../ciris_engine/logic/buses/prohibitions.py) —
  domain axis source of truth.
- [`../ciris_engine/data/localized/manifest.json`](../ciris_engine/data/localized/manifest.json) —
  language axis source of truth.
- [`../tools/qa_runner/modules/safety_battery.py`](../tools/qa_runner/modules/safety_battery.py) —
  the CI runner.
- [`../FSD/MISSION_DRIVEN_DEVELOPMENT.md`](../FSD/MISSION_DRIVEN_DEVELOPMENT.md) —
  why this directory exists in this shape.

---

*This directory is the bottom of the funnel. Most contributor energy
flows through safety.ciris.ai; only consensus-validated artifacts
land here. The 14 currently-present batteries are the externally-
anchored seed set (per MISSION.md §7.2 F-AV-BOOT); future entries
arrive via the promotion path documented above.*
