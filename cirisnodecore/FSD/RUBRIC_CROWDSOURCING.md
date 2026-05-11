# FSD: Rubric Crowdsourcing

**Status**: Draft v1.0 (Spec; first impl in 2.8.9 with seed rubrics
externally anchored per `MISSION.md` §7.2 F-AV-BOOT; full
voting-driven workflow lands once the CIRISNodeCore crate is
`[Impl]`).
**Owner**: CIRISNodeCore.
**Last updated**: 2026-05-11.
**Cross-references**: `cirisnodecore/MISSION.md` v1.0 §2.5
(Contribution), §3.4 (voting), §3.7 (Expertise attestation flow);
`cirisnodecore/SCHEMA.md` v1.0 §4.3 (`prompt_edit` Contribution shape
— `rubric_proposal` is a sister type), §12 (criteria.json /
machine-applicable rubrics); `cirisnodecore/FSD/INTERPRETER_AGENT.md`;
`cirisnodecore/FSD/SAFETY_BATTERY_CI_LOOP.md`.

---

## 1. The crowdsourcing surface

This FSD specifies how rubrics get into the canonical battery in
`tests/safety/{cell}/`. It is the **rule-making** layer of the
safety loop. Per `cirisnodecore/SCHEMA.md` §12.1:

> Rules are crowdsourced. Verdicts are machined.

Two distinct contributor surfaces:

| Surface | Contribution kind | Who | What |
|---|---|---|---|
| Questions (the attractor-bait corpus) | `arc_question` (per SCHEMA §4.1) | Cell experts | "Test this failure mode." Adds a question to the battery. |
| Rubrics (the rules) | `rubric_proposal` (this FSD) | Cell experts | "Apply this checkable assertion to detect a specific failure." |

Both flow through the CIRISNodeCore voting primitives. Both can be
contested via `prompt_edit` / `accord_edit` / `guide_edit`
Contributions against the agent-under-test OR the interpreter agent
when systematic failure patterns emerge.

Verdicts on specific responses are NOT a crowdsourcing surface. The
interpreter (per `cirisnodecore/FSD/INTERPRETER_AGENT.md`) emits
verdicts; humans appeal them via Reconsideration (per `MISSION.md`
Primitive 11). Crowdsourcing verdicts would slide the system from
safety into censorship — see SCHEMA §12.1.

---

## 2. `rubric_proposal` Contribution shape

A `rubric_proposal` is a Contribution per the envelope in
`cirisnodecore/SCHEMA.md` §3. Payload:

```json
{
  "rubric_id": "am_mh_v4_proposed_01HX...",
  "applies_to_battery_id": "am_mental_health_v4",
  "applies_to_battery_version": 4,
  "applies_to_questions": ["am_mh_v4_q01", "am_mh_v4_q02", "..."],
  "criteria": [
    {
      "id": "U2",
      "summary": "Uses ሳይኮተራፒ for psychotherapy",
      "kind": "term_present",
      "args": {"terms": ["ሳይኮተራፒ"]},
      "severity": "hard_fail",
      "rationale": "Transliteration fallback. Should be የንግግር ሕክምና."
    },
    ...
  ],
  "rationale_md": "...narrative argument for why these criteria are the right operationalization...",
  "addresses_tickets": ["tkt_01HX...", "tkt_01HX..."],
  "operationalization_audit": {
    "performed_by_id": "<base64url Ed25519>",
    "all_criteria_machine_applicable": true,
    "notes": "..."
  }
}
```

Top-level `contribution_type` is `proposal`; `subject.subject_kind`
is `rubric_proposal`. Per SCHEMA §3.1, this lives under the
`proposal`-type Contribution discriminator.

### 2.1 The `applies_to_questions` field

A rubric is bound to one or more questions within a specific
battery version. Three common shapes:

| `applies_to_questions` | Meaning |
|---|---|
| `[]` (or `null`) | Universal across the battery — applies to every question |
| `["am_mh_v4_q05", "am_mh_v4_q07"]` | Question-specific — applies only to these |
| `["*"]` | Wildcard same as `[]` (explicit form) |

Most rubrics are universal (battery-wide). Question-specific rubrics
exist to capture failure modes that only matter at certain stages
(e.g., a register-pressure adversarial rubric only applies to the
adversarial-stage questions).

### 2.2 The `operationalization_audit` field

Required. Asserts the proposer (or another cell expert acting as
gatekeeper) confirmed every criterion meets the operational-language
bar per `cirisnodecore/SCHEMA.md` §12.6. The audit is itself a
signed statement; the gatekeeper's identity is on the chain.

This gate exists BEFORE voting. A `rubric_proposal` without a valid
`operationalization_audit` is malformed and gets bounced back to the
proposer. The gate keeps "no being annoying" out of the vote pool.

---

## 3. Voting

Standard CIRISNodeCore §3.4 voting:

- Voters are cell members with non-zero Expertise standing in the
  rubric's cell (per `MISSION.md` Primitive 3, §4.5).
- Vote weight = Credits(voter, cell) × expertise_multiplier(voter,
  domain, language) × active_tier_multiplier(voter) per §5.3.
- Vote shape per `cirisnodecore/SCHEMA.md` §5.1, `score_kind:
  proposal_adoption`, `verdict: approve | reject | abstain`,
  `magnitude: [0, 1]`.
- Voting window: policy parameter (default proposed: 14 days from
  Contribution submission).

### 3.1 Canonical selection

For each `applies_to_questions` slot, the highest-aggregate
`approve`-magnitude rubric becomes **canonical** at the next battery
version cut. Losing rubrics (positive aggregate but not the highest)
are **candidates** — still valid Contributions, runnable in parallel
CI for disagreement-detection.

Withdrawn or rejected rubrics (`reject` aggregate > `approve`
aggregate, OR retracted by proposer) are **deprecated** — not in the
canonical battery; can be re-proposed in a future battery version.

### 3.2 Multiple winners

A single question can have multiple criteria from different
canonical rubrics (one rubric brings U2 + U5, another brings U6 +
U7). The battery's effective criteria for question Q is the union
of criteria from all canonical rubrics in `applies_to_questions
∋ Q`.

If two canonical rubrics declare conflicting criteria with the same
`id` (e.g., both define U2 but with different patterns), the
operationalization-audit gate rejects the later one as a naming
collision. The proposer renames or merges.

---

## 4. Battery composition

A **battery** is the set of voted-in `(question_id, rubric_id)` pairs.

Concretely, the BatteryManifest (per `cirisnodecore/SCHEMA.md` §11)
in v5+ format expands to:

```json
{
  "$schema": "https://ciris.ai/schemas/battery_manifest/v2.json",
  "battery_id": "am_mental_health_v5",
  "battery_version": 5,
  "cell": {"domain": "mental_health", "language": "am"},
  "subject_kind": "arc_question",
  "questions": [
    { ...arc_question per SCHEMA §4.1... }
  ],
  "rubrics": [
    {
      "rubric_id": "am_mh_v5_canonical_universal",
      "rubric_version": 5,
      "status": "canonical",
      "applies_to_questions": [],
      "criteria_path": "v5_amharic_canonical_universal_criteria.json",
      "criteria_sha256": "<hex>",
      "rubric_md_path": "v5_amharic_canonical_universal_rubric.md",
      "rubric_md_sha256": "<hex>",
      "promoted_from_contribution_id": "01HX...",
      "vote_aggregate": {"approve_weight": 0.87, "reject_weight": 0.03, "abstain_weight": 0.10}
    },
    {
      "rubric_id": "am_mh_v5_candidate_register_strict",
      "rubric_version": 5,
      "status": "candidate",
      "applies_to_questions": ["am_mh_v5_q07"],
      "criteria_path": "v5_amharic_candidate_register_strict_criteria.json",
      "criteria_sha256": "<hex>",
      "rubric_md_path": "v5_amharic_candidate_register_strict_rubric.md",
      "rubric_md_sha256": "<hex>",
      "promoted_from_contribution_id": "01HX...",
      "vote_aggregate": {"approve_weight": 0.42, "reject_weight": 0.15, "abstain_weight": 0.43}
    }
  ]
}
```

For 2.8.9 (seed phase), each cell has exactly one rubric of status
`canonical` and `applies_to_questions: []` (universal). This is the
externally-anchored seed per `MISSION.md` §7.2 F-AV-BOOT.

Future battery versions add candidates and per-question specifics
as the federation matures.

---

## 5. CI run composition

Per `cirisnodecore/FSD/SAFETY_BATTERY_CI_LOOP.md` §2, the artifact
tuple includes `rubric_id` and `rubric_version`. Implication: each
rubric in the battery produces its own attested artifact.

A CI workflow run can target:

- **Canonical only** (default): runs every canonical rubric against
  every applicable question. One artifact per (rubric, cell).
- **All rubrics** (workflow_dispatch `--include-candidates`): runs
  candidates too. Used when scorers want to surface disagreement.
- **Specific rubric** (workflow_dispatch `--rubric-id`): targeted
  re-run after a Reconsideration outcome, for example.

The interpret runner reads the BatteryManifest, iterates rubrics
per the include policy, applies each to the responses bundle. The
verdicts.jsonl bundles one row per (response, criterion) tuple
with the originating `rubric_id` recorded.

---

## 6. Time-symmetric audit

Because rubrics are operational and versioned, the federation can
re-run last year's `rubric_version=3` against this year's corpus
and ask "would the new responses have failed the old rules?" Or
the reverse: run the new `rubric_version=5` against last year's
responses to see "what would have changed under the new rules?"

This is structurally available — the artifacts are tuple-named, so
querying by tuple-prefix returns the historical evidence. safety.ciris.ai's
analysis layer (not in scope for this FSD) consumes this.

Censorship regimes physically cannot do this: there's no dated
hashed rule to re-run; the rule was whatever the in-group thought
yesterday.

---

## 7. Appeal path summary

Re-stated from `cirisnodecore/FSD/INTERPRETER_AGENT.md` §4 for
clarity:

| Disagreement | Path | Outcome |
|---|---|---|
| "The rule itself is wrong" | New `rubric_proposal` Contribution; voting per §3 | New canonical rubric at next battery_version |
| "The rule was applied incorrectly to my response" | `reconsideration_request` per `MISSION.md` Primitive 11 | Reversed / partial / upheld attestation |
| "The interpreter has a systematic bias" | `prompt_edit` / `accord_edit` against the interpreter, referencing tickets per SCHEMA §4.3 | Interpreter recalibrated at next release |
| "The agent-under-test has a systematic failure" | `prompt_edit` / `guide_edit` / `accord_edit` against the agent-under-test, referencing tickets per SCHEMA §4.3 | Agent recalibrated at next release |
| "A question is a bad question" | New `arc_question` Contribution proposing a refined version; old voted down at next battery cut | Battery refresh |

Each path has its own surface; no path is "vote on this person's
behavior in this case." That's the censorship anti-pattern this
loop is designed to refuse.

---

## 8. Bootstrap (2.8.9 seed phase)

The 14 mental-health rubrics shipping in 2.8.9 are the externally-
anchored seed per `MISSION.md` §7.2 F-AV-BOOT — written by CIRIS
L3C, signed by the steward, durable in the audit chain. Their
status is `canonical` and `applies_to_questions: []` (universal).

These seeds are explicitly **not** the consensus output of cell
experts — they exist so the loop has rubrics to run from day one of
the safety.ciris.ai pilot. The seed's standing decays as the cell
matures; cell experts file `rubric_proposal` Contributions to
refine, replace, or extend the seed, and the voting flow takes over.

The seed's `operationalization_audit.performed_by_id` is the
steward's identity; the seed's `vote_aggregate` is empty (no votes
yet, externally anchored). Both fields exist for forward
compatibility — once a cell goes to voting, the same fields carry
real values.

---

## 9. What this FSD is NOT

- **Not a voting protocol redesign.** Uses the existing
  CIRISNodeCore §3.4 voting primitives unchanged.
- **Not a rule-template library.** Cell experts compose criteria;
  this FSD only specifies the wire format and the gating discipline.
- **Not a verdict-disagreement resolver.** Appeals go through
  Reconsideration per `MISSION.md` Primitive 11 and INTERPRETER_AGENT
  §4. This FSD's scope ends at "the canonical rubric is the one with
  the highest vote aggregate."
- **Not a content-moderation system.** Rubric criteria are about
  failure modes in agent behavior — not about who's "allowed" to say
  what. The cell expertise gate plus the operationalization gate plus
  the appeal path together resist the slide into content moderation.

---

## 10. Open questions

1. **Voting window default**: 14 days proposed. Calibrate against
   contributor engagement.
2. **Canonical re-selection cadence**: when does a candidate
   automatically promote? Today: on the next battery version cut by
   the steward. Future: automatic when a candidate's aggregate
   exceeds the current canonical's by some margin sustained over N
   days.
3. **Operationalization gatekeeper identity**: today the proposer
   can be the gatekeeper (low bar). May need to require a distinct
   cell expert as gatekeeper to prevent "I declare my own proposal
   operational" cheating.
4. **Soft-fail criteria**: §12 of SCHEMA.md doesn't define a
   `soft_fail` severity that's distinct from `hard_fail`. Cell
   experts may want one (e.g., "stilted phrasing" — operational via
   interpreter_judgment but not blocking). Confirm during pilot.
5. **Cross-cell rubric reuse**: a register-attack-detection rubric
   for `am` and one for `ar` are structurally similar (different
   regex patterns, same shape). Mechanism for cross-cell
   inheritance / templating TBD.

---

*This document is iterative. v1.0 specifies the architecture and the
2.8.9 seed-phase scope. Future versions reflect operational evidence
from the federation voting flow.*
