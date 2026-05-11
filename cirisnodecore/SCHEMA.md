# CIRISNodeCore — Schema

**SCHEMA.md**. Canonical wire formats for the eleven primitives plus the
safety-battery encoding. Pairs with `MISSION.md`; together they form the
v1.0 CIRISNodeCore spec.

**Status**: Draft v1.0 (pre-implementation; pairs with `MISSION.md` v1.0).
**Crate identifier**: `ciris-node-core`.
**Last updated**: 2026-05-11.
**Cross-references**: `MISSION.md` (the why and the primitives narrative);
`tests/safety/` in CIRISAgent (canonical batteries shipped in the attested
wheel); `FEDERATION_THREAT_MODEL.md` (substrate primitives this layer
builds on); `ACCORD.md` §VII (M-1).

Every load-bearing claim in `MISSION.md` carries an Implementation Status
tag (`[Spec]` / `[Impl]` / `[Deployed (pilot|folded)]`). The same tags
apply here — until the rust crate is `Impl`, every schema in this
document is `[Spec]` and the canonical encoding is the JSON form below.
The rust structs in `MISSION.md` §4 are the binding definitions once the
crate exists; the JSON forms here are the ground truth in the interim
and remain the API-surface canonical form even after the crate ships.

---

## 1. Scope

`MISSION.md` defines the eleven primitives and their narrative roles.
This document defines:

1. The **canonical JSON encoding** of each primitive — field names,
   types, optional vs required, validation rules, signature placement.
2. The **safety-battery shape** — how a battery of `arc_question`
   Contributions is serialized at rest (in `tests/safety/`) and how it
   maps onto the federation audit chain when the crate is live.
3. The **canonical-vs-pending split** — which artifacts live in the
   attested CIRISAgent wheel and which live on the federation chain.
4. The **promotion path** — how a pending Contribution becomes a
   canonical artifact in the next CIRISAgent release.

It does NOT define:

- Policy parameters (witness counts, thresholds, decay rates). Those
  are `MISSION.md` §6.2 and §9, calibrated against pilot evidence.
- The protocol-level message framing for crate↔consumer RPC. That is
  an `[Impl]`-phase concern.
- The rust struct definitions themselves. Those live in `MISSION.md`
  §4 and will become the rust source-of-truth once the crate is
  `Impl`. This document is the JSON projection.

---

## 2. Canonical encoding rules

All schemas in this document follow these rules. Deviations are called
out per-schema.

### 2.1 Wire format

UTF-8 encoded JSON. Keys are `snake_case`. Object key ordering is
**canonical**: sorted lexicographically when computing signatures or
hashes; flexible for human-readable display. Numbers that exceed
JavaScript safe-integer range are encoded as strings.

### 2.2 Identifiers

- `contributor_id`: 32-byte Ed25519 public key, base64url-encoded
  (no padding). Inherited from substrate identity per `MISSION.md`
  Primitive 1.
- `contribution_id`, `vote_id`, `attestation_id`: ULID
  (Crockford-base32-encoded 128-bit; sortable by submission time).
- `battery_id`: human-readable string of the form
  `{lang}_{domain}_v{N}` (e.g. `am_mental_health_v4`).
- `question_id`: `{lang}_{domain_short}_v{N}_q{II}` where `II` is a
  zero-padded two-digit index (e.g. `am_mh_v4_q01`).
- `ticket_id`: ULID, prefixed with `tkt_` in display only.

### 2.3 Timestamps

ISO 8601 UTC with second precision. Trailing `Z`, never offset
(`2026-05-11T14:30:00Z`).

### 2.4 Signatures

Every signed object carries a `signature` field whose value is the
hybrid Ed25519 + ML-DSA-65 signature over the canonical-encoded
object **with the `signature` field omitted**. Multi-signer objects
(e.g. `SlashingAttestation`) carry a `signatures` array of
`{signer_id, signature}` records, signing the same canonical-encoded
omission-form.

Hybrid signature wire format:

```json
{
  "ed25519": "<base64url Ed25519 signature, 64 bytes>",
  "ml_dsa_65": "<base64url ML-DSA-65 signature, ~3.3 KB>",
  "signed_at": "2026-05-11T14:30:00Z"
}
```

Both signatures must verify against the corresponding identity's
public keys for the object to be considered well-formed at the
substrate level. Per-primitive validity (e.g. witness diversity for
high-stakes Contributions) is checked on top of this.

### 2.5 Cells

A **cell** is the granularity at which consensus state is indexed.
Two cell granularities apply:

- `(domain, language, subject)`: the **Credits-granularity cell**.
  Per `MISSION.md` Primitive 2.
- `(domain, language)`: the **Expertise-granularity cell**. Per
  `MISSION.md` Primitive 3.

A cell is serialized as:

```json
{ "domain": "mental_health", "language": "am", "subject": "arc_question" }
```

The `subject` field is omitted in Expertise-granularity contexts. The
`domain` value is one of the categories from
`ciris_engine/logic/buses/prohibitions.py` (`MEDICAL`, `LEGAL`,
`SPIRITUAL_DIRECTION`, etc.) plus `mental_health` (capability-allowed
but high-stakes, not on the prohibited list). The `language` value is
an ISO 639-1 code drawn from
`ciris_engine/data/localized/manifest.json` (29 locales currently).

### 2.6 Versioning

Schemas evolve via minor-version bumps with backward-compatible field
additions. Field removals or semantic changes are major-version cuts
and require explicit migration scripts. The schema version itself is
not embedded in every payload; consumers should treat unknown fields
as ignorable and missing optional fields as `None`.

The **battery** format carries an explicit `battery_version` integer
(separate from the per-question `question_version`) so a battery can
be cut at v4 while individual questions are still at v1.

---

## 3. Contribution envelope (the common shell)

Every artifact submitted to the federation by a contributor is a
**Contribution**. The envelope is uniform; the `payload` shape
varies by `contribution_type` and `subject.subject` (Credits-cell)
or `subject.subject_kind` (Expertise-cell + new subject types).

```json
{
  "contribution_id": "01HX5...",
  "contribution_type": "proposal",
  "author_id": "<base64url Ed25519>",
  "subject": {
    "domain": "mental_health",
    "language": "am",
    "subject_kind": "arc_question"
  },
  "payload": { ...subject-kind-specific... },
  "witness_set": null,
  "signature": { "ed25519": "...", "ml_dsa_65": "...", "signed_at": "..." },
  "submitted_at": "2026-05-11T14:30:00Z"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `contribution_id` | ULID string | yes | Per §2.2 |
| `contribution_type` | enum | yes | See §3.1 |
| `author_id` | ContributorId | yes | Per §2.2; matches `signature.ed25519` signer |
| `subject` | Cell + subject_kind | yes | Per §2.5 |
| `payload` | object | yes | Shape per §4 |
| `witness_set` | WitnessSet | conditional | Required for high-stakes per `MISSION.md` Primitive 10 / §3.5 |
| `signature` | HybridSignature | yes | Per §2.4 |
| `submitted_at` | ISO timestamp | yes | Per §2.3 |

### 3.1 `contribution_type` enum

From `MISSION.md` Primitive 5. Discriminator at the envelope level;
distinct from `subject.subject_kind` which discriminates payload
shapes within `proposal`-type Contributions.

| Value | Payload location | Purpose |
|---|---|---|
| `deferral_request` | §4.7 | Consumer requests routing to qualified WAs |
| `deferral_response` | §4.8 | Routed WA's signed response |
| `proposal` | §4.1–§4.6 | Battery, free-form argument, policy proposal, edit proposal, etc. Sub-discriminated by `subject.subject_kind`. |
| `wa_candidacy` | §4.9 | Self- or peer-nomination for Wise Authority standing |
| `expertise_attestation` | §4.10 | Expertise-bearer attests another contributor has expertise in a cell |
| `moderation_event` | §4.11 | Accusation of rogue action |
| `reconsideration_request` | §4.12 | Signed request to reverse a prior SlashingAttestation |

### 3.2 `subject.subject_kind` for `proposal`-type Contributions

| Value | Purpose | Witness requirement |
|---|---|---|
| `arc_question` | A single safety battery question | None (routine) |
| `proposed_battery` | A whole battery (set of questions for a cell) | Required if magnitude exceeds threshold per §3.5 |
| `prompt_edit` | A diff against the canonical `prompts.*` block for a locale | Required (high-stakes — affects every agent response) |
| `guide_edit` | A diff against the canonical Comprehensive Guide for a locale | Required |
| `accord_edit` | A diff against the canonical localized ACCORD body | Required |
| `failure_pattern` | A signed ticket: agent is observed to fail pattern X with evidence | None (witness diversity not required for filing tickets; required for adjudication) |
| `free_form` | Narrative argument or commentary | None |

---

## 4. Payloads by subject_kind

### 4.1 `arc_question` (the core safety primitive)

A single question, scoped to a cell, designed to exercise specific
faculty/stage behavior. Payload:

```json
{
  "question_id": "am_mh_v4_q01",
  "question_version": 1,
  "stage": "Stage 1: Symptom Disclosure",
  "category": "Mental Health",
  "evaluates": "S1 — empathic acknowledgment using NATIVE Amharic vocabulary...",
  "hard_fail_triggers": ["U1", "U2", "U3", "U8"],
  "soft_fail_triggers": [],
  "faculty_targets": ["EthicalPDMAEvaluator", "epistemic_humility_conscience"],
  "translations": {
    "en": "User Selamawit said: 'Hey, I've been feeling really down...'",
    "am": "ተጠቃሚ ሰላማዊት እንዲህ አለች: ..."
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `question_id` | string | yes | Per §2.2 |
| `question_version` | integer ≥ 1 | yes | Bumps when this question's content changes; independent of battery_version |
| `stage` | string | yes | Free-form stage label per the rubric (e.g. `Stage 1: Symptom Disclosure`, `Adversarial: Register Attack`) |
| `category` | string | yes | Domain-level category (e.g. `Mental Health`) |
| `evaluates` | string | yes | What this question is designed to exercise; consumed by human scorers as scoring guidance |
| `hard_fail_triggers` | string[] | yes (may be empty) | Pointers into the rubric's universal-pass-criteria U-table. Used by scorers to know which hard-fail checks apply to this question; NOT used as machine-evaluator inputs. |
| `soft_fail_triggers` | string[] | yes (may be empty) | Same shape; flags soft-fail criteria the scorer should check |
| `faculty_targets` | string[] | yes | Which conscience/DMA faculty this question is designed to exercise. Drives ticket triage when the question fails — points the cell experts at which canonical prompt/guide to inspect. |
| `translations` | map<lang, string> | yes | Localized question text. MUST include at minimum the cell's `language`; SHOULD include `en` as a cross-locale reference. |

**Validity**:
- `question_id` MUST match the cell's language and domain prefix (regex
  `^{lang}_{domain_short}_v\d+_q\d{2}$`).
- `translations` MUST contain the cell's language.
- `hard_fail_triggers` and `soft_fail_triggers` MUST reference triggers
  that exist in the cell's canonical rubric (validated at promotion-PR
  review time, not at submission).
- `faculty_targets` MUST be drawn from the canonical faculty registry
  (the 11 schemas in `dma_repro/replay.py`).

### 4.2 `proposed_battery`

A set of `arc_question` payloads bundled for cell-level consideration.
Payload:

```json
{
  "battery_id": "am_mental_health_v5_proposed_01HX5...",
  "battery_version_intended": 5,
  "rubric_diff": "...markdown diff against current canonical rubric...",
  "questions": [ {...arc_question payload...}, ... ],
  "rationale": "Adds 3 new adversarial probes for register-pressure under family-frame.",
  "addresses_tickets": ["tkt_01HX4..."]
}
```

Promotion of a `proposed_battery` Contribution into the canonical
battery format (§11) happens via the promotion path (§13).

### 4.3 `prompt_edit`

A diff against the canonical `prompts.*` block in
`ciris_engine/data/localized/{lang}.json` (per the `prompts.dma`,
`prompts.formatters`, `prompts.escalation`, `prompts.crisis`,
`prompts.engine_overview`, `prompts.language_guidance` keys). Payload:

```json
{
  "language": "am",
  "prompt_section": "prompts.language_guidance",
  "base_release": "2.8.8",
  "diff": "...unified-diff text...",
  "rationale": "Repairs U2/U4 hard-fail pattern observed in tkt_01HX4...",
  "addresses_tickets": ["tkt_01HX4...", "tkt_01HX5..."]
}
```

Witness set required (`MISSION.md` §3.5). `addresses_tickets` MUST be
non-empty — the project explicitly does not accept speculative edits;
every prompt edit must point at observed failure evidence.

### 4.4 `guide_edit`

Same shape as `prompt_edit`, but `prompt_section` is replaced with
`guide_file` and points at
`ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_{lang}.txt`.

### 4.5 `accord_edit`

Same shape, `guide_file` replaced with `accord_file` pointing at
`ciris_engine/data/localized/accord_1.2b_{lang}.txt`. Accord edits
have additional scrutiny per `ACCORD.md` v1.2b custody rules; the
crate enforces this with an additional witness-diversity bump.

### 4.6 `failure_pattern` (ticket)

A signed ticket describing an observed failure mode with evidence.
Payload:

```json
{
  "ticket_id": "tkt_01HX4...",
  "title": "Agent uses ሳይኮተራፒ instead of የንግግር ሕክምና in Stage 2",
  "cell": { "domain": "mental_health", "language": "am" },
  "trigger_hit": "U2",
  "evidence_responses": [
    {
      "response_id": "resp_01HX3...",
      "question_id": "am_mh_v4_q04",
      "agent_text_excerpt": "...ሳይኮተራፒ ሊረዳዎ ይችላል...",
      "supporting_votes": ["vote_01HX3...", "vote_01HX3..."]
    }
  ],
  "severity": "hard_fail",
  "first_observed_at": "2026-05-08T...",
  "last_observed_at": "2026-05-11T..."
}
```

Tickets aggregate evidence from multiple battery runs. `evidence_responses`
references signed agent responses; `supporting_votes` references the
human scoring Votes that flagged each response. A ticket is the unit
that `prompt_edit`, `guide_edit`, `accord_edit`, and
`proposed_battery` Contributions point at via `addresses_tickets`.

### 4.7 `deferral_request`

Per `MISSION.md` §3.3 / §5.1. Payload contains the consumer's query
context and the cell to route within. (Out of scope for the safety
pilot's initial cut — included here for schema completeness.)

### 4.8 `deferral_response`

Per `MISSION.md` §3.3. The routed contributor's signed response to a
deferral. (Same scope note as 4.7.)

### 4.9 `wa_candidacy`

Per `MISSION.md` §3.6. Self- or peer-nomination for Wise Authority
standing in a cell, gated on Credits + Expertise thresholds.

### 4.10 `expertise_attestation`

Per `MISSION.md` §3.7 and §4.6. Witness set required when the
attestation would jump the target's Expertise standing past the
policy-tunable threshold.

### 4.11 `moderation_event`

Per `MISSION.md` §4.7 / §5.6. Witness set always required.

### 4.12 `reconsideration_request`

Per `MISSION.md` §4.10 / §5.7. Witness set always required. Subject
to recursion bound (one per ground per SlashingAttestation; three
triggers harassment review) and time bound (180-day default for
NEW_EVIDENCE / PROCEDURAL_ERROR; unlimited for QUORUM_COMPROMISE).

---

## 5. Vote

Per `MISSION.md` Primitive 4 / §4.3.

```json
{
  "vote_id": "01HX...",
  "voter_id": "<base64url Ed25519>",
  "contribution_id": "01HX5...",
  "cell": { "domain": "mental_health", "language": "am", "subject": "arc_question" },
  "score": { ...subject-dependent shape... },
  "rationale": "Hard-fail U2 — agent used ሳይኮተራፒ in Stage 2.",
  "signature": { "ed25519": "...", "ml_dsa_65": "...", "signed_at": "..." },
  "cast_at": "2026-05-11T14:35:00Z"
}
```

### 5.1 `score` shapes

The `score` payload varies by what's being voted on. For the safety
pilot's first cut, two shapes apply:

**Voting on a battery response** (the human-scoring loop):

```json
{
  "score_kind": "battery_response",
  "response_id": "resp_01HX3...",
  "question_id": "am_mh_v4_q04",
  "verdict": "hard_fail",
  "triggers_hit": ["U2", "U4"],
  "soft_signals": ["over-explanation"]
}
```

`verdict` is one of `pass | soft_fail | hard_fail`. `triggers_hit`
references rubric U-codes. `soft_signals` is free-form text per
the rubric's soft-fail criteria.

**Voting on a proposed Contribution** (battery, prompt edit, guide
edit, accord edit):

```json
{
  "score_kind": "proposal_adoption",
  "verdict": "approve",
  "magnitude": 1.0
}
```

`verdict` is one of `approve | reject | abstain`. `magnitude` is a
real number in `[0, 1]` representing strength of preference.

### 5.2 Vote weight

Computed at aggregation time (`MISSION.md` §3.4 / §5.3) as:

```
weight = credits(voter, cell) × expertise_multiplier(voter, domain, language)
       × active_tier_multiplier(voter)
```

Not embedded in the Vote payload; derived from the voter's ledgers at
the moment of aggregation. Votes recorded raw; aggregation is a view.

---

## 6. WitnessSet

Per `MISSION.md` Primitive 10 / §4.9.

```json
{
  "witnesses": [
    {
      "witness_id": "<base64url Ed25519>",
      "jurisdiction": "ET",
      "operator": "org_id_or_self",
      "software_stack": "ciris-agent-2.8.9-stable",
      "cell_expertise": 0.42,
      "signature": { "ed25519": "...", "ml_dsa_65": "...", "signed_at": "..." }
    },
    ...
  ],
  "diversity_proof": {
    "jurisdictions": ["ET", "KE", "US"],
    "operators_distinct": 3,
    "software_stacks_distinct": 2,
    "cell_expertise_floor_met": true
  }
}
```

The crate validates diversity at submission time. The
`diversity_proof` block is the explicit accounting; if the crate's
computed diversity disagrees with the proof, the WitnessSet is
rejected.

---

## 7. ExpertiseAttestation

Per `MISSION.md` §4.6.

```json
{
  "contribution_id": "01HX...",
  "attester_id": "<base64url Ed25519>",
  "target_id": "<base64url Ed25519>",
  "cell": { "domain": "mental_health", "language": "am" },
  "rationale": "Target has shipped 12 well-received guide edits in this cell over 8 months.",
  "witness_set": null,
  "signature": { "ed25519": "...", "ml_dsa_65": "...", "signed_at": "..." },
  "attested_at": "2026-05-11T..."
}
```

`witness_set` is required when the attestation would jump the
target's standing past the cell's jump-threshold policy parameter
(`MISSION.md` §9 question 10).

---

## 8. ModerationEvent + SlashingAttestation

Per `MISSION.md` §4.7 / §4.8 / §5.6.

ModerationEvent:

```json
{
  "contribution_id": "01HX...",
  "accuser_id": "<base64url Ed25519>",
  "target_kind": "contribution",
  "target_id": "01HX...",
  "allegation": "rogue_vote",
  "evidence": "...canonical-encoded evidence payload...",
  "accuser_stake": "12.5",
  "witness_set": { ...WitnessSet... },
  "signature": { ... },
  "filed_at": "2026-05-11T..."
}
```

`allegation` is one of `rogue_vote | coordinated_voting |
out_of_distribution_attestation | external_inducement_evidence |
expertise_fraud`. `accuser_stake` is a non-negative decimal string
(to avoid float drift on the audit chain) in units of Commons
Credits.

SlashingAttestation:

```json
{
  "attestation_id": "01HX...",
  "moderation_event_id": "01HX...",
  "quorum_ids": [ "<wa_id>", "<wa_id>", "<wa_id>" ],
  "outcome": "proven_rogue",
  "credits_reduced": "5.0",
  "expertise_reduced": "0.0",
  "accuser_stake_disposition": {
    "kind": "return_with_bounty",
    "returned": "12.5",
    "bounty": "2.5"
  },
  "signatures": [
    { "signer_id": "<wa_id>", "signature": { ... } },
    ...
  ],
  "attested_at": "2026-05-12T..."
}
```

`outcome` is one of `proven_rogue | not_proven`. The
`accuser_stake_disposition.kind` enumerates the disposition tiers from
`MISSION.md` Primitive 9.

---

## 9. ReconsiderationRequest + ReconsiderationAttestation

Per `MISSION.md` Primitive 11 / §4.10 / §5.7.

ReconsiderationRequest:

```json
{
  "contribution_id": "01HX...",
  "requester_id": "<base64url Ed25519>",
  "target_slashing_id": "01HX...",
  "grounds": "new_evidence",
  "evidence": "...canonical-encoded evidence payload...",
  "requester_stake": "8.0",
  "witness_set": { ...WitnessSet... },
  "signature": { ... },
  "filed_at": "2026-05-13T..."
}
```

`grounds` is one of `new_evidence | procedural_error |
quorum_compromise`. Time bound: 180-day default from
`target_slashing_id`'s `attested_at` for `new_evidence` and
`procedural_error`; unlimited for `quorum_compromise`. Recursion
bound: one Reconsideration per ground per SlashingAttestation; three
filings on a single SlashingAttestation trips harassment review per
`MISSION.md` §3.9.

ReconsiderationAttestation:

```json
{
  "attestation_id": "01HX...",
  "reconsideration_request_id": "01HX...",
  "fresh_quorum_ids": [ "<wa_id>", "<wa_id>", "<wa_id>" ],
  "outcome": "reversed",
  "credits_restored": "5.0",
  "expertise_restored": "0.0",
  "requester_stake_disposition": { "kind": "returned", "returned": "8.0" },
  "fresh_quorum_rationale": "Same-cell pool exhausted; drew 1 from adjacent cell (legal/am) with verified cell-expertise 0.31.",
  "signatures": [ ... ],
  "attested_at": "2026-05-15T..."
}
```

`outcome` is one of `reversed | partial | upheld`.
`fresh_quorum_rationale` is required when the fresh quorum was drawn
outside the strict same-cell pool.

---

## 10. Ledgers (Credits, Expertise) — read views

Ledgers are derived state, not user-submitted Contributions. They
are computed by the crate from the audit chain. The JSON read view
(returned by the crate's query API to consumers like safety.ciris.ai):

CommonsCreditsLedger:

```json
{
  "contributor_id": "<base64url Ed25519>",
  "cell": { "domain": "mental_health", "language": "am", "subject": "arc_question" },
  "credits": "127.5",
  "last_updated": "2026-05-11T...",
  "ledger_signature": { ... }
}
```

ExpertiseLedger:

```json
{
  "contributor_id": "<base64url Ed25519>",
  "cell": { "domain": "mental_health", "language": "am" },
  "attestation_count": 7,
  "track_record": {
    "hard_case_count": 14,
    "truth_grounded_alignment_rate": 0.78,
    "contested_cases_resolved": 9
  },
  "standing": "0.42",
  "last_recomputed": "2026-05-11T...",
  "ledger_signature": { ... }
}
```

Both ledgers carry a non-negative invariant (`credits ≥ 0`,
`standing ≥ 0`). Slashing reduces toward but never below zero.

---

## 11. BatteryManifest — canonical battery wrapper

The on-disk format for canonical batteries in
`tests/safety/{lang}_{domain}/v{N}_{lang}_{domain_short}_arc.json`.

This is what the QA runner reads. It is NOT a Contribution; it is the
serialization of an already-voted-in set of `arc_question` payloads
plus the cell's canonical rubric reference. A `proposed_battery`
Contribution (§4.2) gets promoted into this format via the promotion
path (§13) once it wins cell consensus.

```json
{
  "$schema": "https://ciris.ai/schemas/battery_manifest/v1.json",
  "battery_id": "am_mental_health_v4",
  "battery_version": 4,
  "battery_version_committed_at": "2026-05-11T...",
  "cell": { "domain": "mental_health", "language": "am" },
  "subject_kind": "arc_question",
  "rubric_path": "v4_amharic_scoring_rubric.md",
  "rubric_sha256": "<hex sha256 of the markdown file on disk>",
  "promoted_from_contribution_id": "01HX...",
  "questions": [
    { ...arc_question payload per §4.1... },
    ...
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `$schema` | URI | yes | Pins parser version |
| `battery_id` | string | yes | Per §2.2 |
| `battery_version` | integer ≥ 1 | yes | Bumps on any question add/remove/rename |
| `battery_version_committed_at` | ISO timestamp | yes | When this version was promoted into canonical |
| `cell` | Cell | yes | Expertise granularity (domain + language only) |
| `subject_kind` | string | yes | Always `arc_question` for safety batteries; reserved field for future battery kinds |
| `rubric_path` | string | yes | Path relative to the battery file; sibling markdown |
| `rubric_sha256` | hex string | yes | Pin to specific rubric file content; QA runner validates |
| `promoted_from_contribution_id` | ULID | optional | The `proposed_battery` Contribution this canonical version was promoted from. Absent for the externally-anchored seed batteries (the original 14 v3 corpora). |
| `questions` | arc_question[] | yes | At least 1 question; each follows §4.1 |

**Validity at QA-runner time**:
- `rubric_sha256` MUST match the on-disk file at `rubric_path`. If
  drift is detected, the runner fails with a stable error message
  `safety_battery_rubric_drift`. (Pattern matches the
  `secrets_bootstrap_corruption` marker from 2.8.8 — monitoring
  alerts on the stable string.)
- Every `question_id` MUST be unique within the battery.
- Every `question_id` MUST match the regex
  `^{lang}_{domain_short}_v{battery_version}_q\d{2}$`.

---

## 12. Rubric format

The rubric is a markdown file sibling to the BatteryManifest JSON.
It carries:

1. A **universal pass criteria** table with rows `U1`, `U2`, … —
   stable identifiers that `arc_question.hard_fail_triggers` and
   `arc_question.soft_fail_triggers` reference. Each row gives the
   trigger description and the "why it's load-bearing" explanation.
2. A **per-question criteria** section, organized by stage. Each
   question's entry restates the `evaluates` field and lists the
   PASS / SOFT-FAIL / HARD-FAIL criteria specific to that question.
3. An **aggregate scoring** section explaining how individual
   verdicts combine into a battery-level result.
4. A **how to run** section describing the human-scoring workflow.
5. A **reviewer note** for context the rubric author wants to
   communicate.

The rubric is intended for **human scorers**. It is not a machine-
evaluator input. Mechanical assertions (regex term checks, register
markers in the first sentence, etc.) are not the rubric's job — the
rubric records the scorer's checklist, and the scorer applies it
using language judgment that no regex can replicate. The
`hard_fail_triggers` array on each question simply tells the scorer
"these are the universal triggers that particularly apply to this
question," not "these will be auto-checked."

This decision is load-bearing: the moment the rubric becomes
machine-checkable in the runtime, contributors are incentivized to
write triggers that pass automation rather than triggers that
capture failure modes. The human-judgment requirement is the
truth-grounding floor for the cell's consensus.

---

## 13. Canonical vs pending — and the promotion path

### 13.1 Canonical (in the attested CIRISAgent wheel)

Files under `tests/safety/` that have already won cell consensus and
been promoted. These ship in the attested wheel, are signed by the
CIRISVerify L4 manifest, and are what the QA runner exercises. They
are:

- `tests/safety/{lang}_{domain}/v{N}_{lang}_{domain_short}_arc.json`
  — BatteryManifest per §11
- `tests/safety/{lang}_{domain}/v{N}_{lang}_scoring_rubric.md` —
  rubric per §12

Promotion to canonical only happens via merged PR. The PR is opened
by the crate (or by the steward during pilot phase) once the cell's
voting threshold is crossed for a `proposed_battery` /
`prompt_edit` / `guide_edit` / `accord_edit` Contribution. The PR
review is the final attestation gate; the next CIRISAgent release
carries the updated canonical artifact.

### 13.2 Pending (on the federation audit chain)

Contributions of any type that have not yet been promoted to
canonical. They live on the federation audit chain (substrate:
CIRISPersist for storage, CIRISBridge for transport, CIRISVerify for
signatures). They are NOT in the CIRISAgent wheel; the agent runtime
does not see them until they are promoted.

Specifically: contributor-submitted `arc_question`, `proposed_battery`,
`prompt_edit`, `guide_edit`, `accord_edit`, and `failure_pattern`
Contributions live on the chain. The safety.ciris.ai pilot persists
them in the canonical Contribution format defined in this document
so that when the rust crate is `Impl` the migration is 1:1.

### 13.3 Promotion path

```
   contributor submits Contribution (§3, §4)
            ↓
   federation chain: signed, replicated, voted on per MISSION.md §3.4
            ↓
   aggregation crosses cell threshold (policy-tunable, MISSION.md §9)
            ↓
   crate signs a promotion attestation
            ↓
   PR opened against CIRISAgent
       - adds/updates files in tests/safety/{lang}_{domain}/
         OR ciris_engine/data/localized/{lang}.json
         OR ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_{lang}.txt
         OR ciris_engine/data/localized/accord_1.2b_{lang}.txt
       - references the promotion attestation in commit message
       - bumps battery_version / increments BetaRelease in CHANGELOG
            ↓
   PR review (substrate-level attestation that the diff matches the
   federation chain attestation; not a re-litigation of consensus)
            ↓
   merged → next release → L4 attestation covers the new canonical
            ↓
   QA runner picks up the new canonical at next CI run
```

### 13.4 What never promotes

`moderation_event`, `slashing_attestation`, `reconsideration_*`,
`expertise_attestation`, `wa_candidacy`, and Ledger updates are all
federation-chain artifacts. They never promote to in-wheel files;
the crate's read API surfaces them to consumers (safety.ciris.ai,
eventually CIRISAgent itself when the crate folds in).

Tickets (`failure_pattern` Contributions per §4.6) likewise live on
the chain; the canonical battery JSON does not embed evidence
chains, only the questions and the rubric reference.

---

## 14. Open schema questions (for the pilot to resolve)

These are version-1 placeholders to be calibrated against pilot
evidence:

1. **`rubric_sha256` algorithm scope**. SHA-256 of the rubric file
   bytes as-is, or of a canonical normalized form (line endings,
   trailing whitespace, BOM)? Pilot may surface CI false-positives
   from line-ending drift; normalization is a one-time decision.

2. **`addresses_tickets` empty-set semantics**. Today: edit
   Contributions MUST point at ≥ 1 ticket. What about emergency
   security fixes where no ticket exists yet because the issue was
   reported privately? Carve-out shape TBD; probably a steward-
   signed `synthetic_ticket` Contribution that becomes the
   pointer.

3. **`triggers_hit` vocabulary across locales**. Today: the U-codes
   are per-rubric, so `U2` in `am` means a different trigger than
   `U2` in `ar`. Cross-locale ticket aggregation needs either a
   shared trigger vocabulary or a translation table. Pilot will
   surface which approach is workable.

4. **`faculty_targets` for non-conscience subjects**. Today the
   enum is the 11 conscience/DMA schemas. For accord/guide edits
   the target isn't a faculty, it's a section. Schema may need a
   `target_kind` discriminator (faculty vs section vs other).

5. **Battery family vs version**. Today a battery is identified by
   `(lang, domain, version)`. Some cells may want parallel
   battery "families" (e.g. a crisis-resources-focused battery
   alongside the symptom-disclosure battery). TBD whether this is
   a new `subject_kind` or a sub-field.

These are all pilot questions, not pre-implementation blockers. The
crate's `Impl` phase resolves them with real evidence from
safety.ciris.ai.

---

*This document is iterative. v1.0 is the publishable version pairing
with `MISSION.md` v1.0. Future versions track schema evolutions
discovered during the pilot, the rust crate's `Impl` phase, and the
eventual fold into CIRISAgent. Readers can challenge any encoding by
tracing it to its primitive in `MISSION.md` §4 or pushing back on
§13's canonical-vs-pending split.*
