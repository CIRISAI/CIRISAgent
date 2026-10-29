# Safety-battery evidence as signed CEG blobs

Status: proposed (2026-10-29). Owner: CIRISAgent. Registry family: CC 3.1.5.5
(CC v1.0-rc13, cd7a22b). Registry intake: CIRISRegistry#150.

## 1. What this replaces

Each safety-battery run produces a bundle under `qa_reports/`:

- capture: `results.jsonl` (the question/answer pairs for one cell), `summary.json`,
  `manifest_signed.json`;
- interpret: `verdicts.jsonl` (one row per question × criterion, with the cited
  span), `verdicts_summary.json`, `manifest_signed.json`.

`manifest_signed.json` is not signed. It binds the bundle by SHA-256 (the
verdicts and summary hashes, `rubric_md_sha256`, the judge prompt hash, and the
capture manifest hash as the capture→interpret cross-link) and records CI
provenance (repository, commit, ref, run id, workflow path). Its integrity rests
on git history and on Actions artifacts, which expire after 90 days.

The bundles reach `main` through the daily `safety-evidence-sync` workflow, which
harvests artifacts into `qa_reports/` and opens a pull request. That last step has
failed since 2026-10-20 because Actions may not create pull requests in this
repository, and the right fix is not to allow it: the setting is repository-wide
and lets any workflow approve its own pull request. The evidence also grows git by
about 9 MB a week, and one file in each bundle is already above the 250 KB limit
the pre-commit hook enforces.

The rule is that evidence is published, signed, where anyone can check it, not
committed.

## 2. The family (CC 3.1.5.5)

One family, owned by CIRISAgent:

```
evidence:safety_battery:{kind}:{cell}:{prefix}:v1
```

- `{kind}` ∈ `capture` | `interpret` (closed).
- `{cell}` is the cell as a value segment: `{lang}_{domain}`, e.g. `ru_mental_health`.
- `{prefix}` is the first 16 lowercase hex characters of the **capture** blob's
  SHA-256. An interpret row carries the prefix of the capture it judges, so the
  two are paired by name and a re-post of the same capture is a `supersedes`
  (CIRISRegistry#144), never a silent replace. The 16-character length is enforced
  at the agent's door.
- `:v1` is the version segment (CC 3.1.7 R3).

CC generalized the family to `evidence:{suite}:{kind}:{cell}:{prefix}:v1`, with
`{suite}` a closed vocabulary whose first member is `safety_battery`; the
dimension strings above are unchanged by that.

Each row is a `scores` Contribution at `cohort_scope: federation` (public commons
evidence, replication audience public), with `evidence_refs: [<manifest sha256>]`.
It is a self-report (CC 3.4.5.1): it confers no standing by itself and is
published, not "offered".

The family's polarity is `signed` (from rc14; rc13 is positive-only). Rows are
written with the signed score from the first one, so none needs re-signing when
rc14 lands. A capture scores
`1.0`. An interpret scores `(2·passed − total) / total`, computed as one division
so the signer and the registry's recomputation agree to the bit (`2·(passed/total) − 1`
can differ by one ulp): `−1` when every criterion failed, `+1` when every
criterion passed; the pass ratio reads back as `(score + 1) / 2`.
Until the rc14 pin lands, an interpret with a score ≤ 0 is HELD. That is a pass
ratio of at most 0.5, with exactly half passed included, because rc13's
positive-only range is (0, 1] and excludes zero. A held row is not posted, not refused, and not
clamped or given an epsilon score; its dimension string does
not change, so it is posted unchanged once the polarity flips.

Example wire dimension:

```
evidence:safety_battery:interpret:ru_mental_health:8af424544249c1c6:v1
```

## 3. The blob

One blob per row, a zip of the bundle's files with a `manifest.json` at its root.
The manifest is today's `manifest_signed.json` content, renamed, with the same
hash bindings and `ci_provenance`, plus:

- `agent_version` under test and the capture model (already in the artifact name);
- for an interpret: `rubric_id`, `rubric_version`, `rubric_md_sha256`,
  `judge_model`, `judge_prompt_sha256`, and `capture_blob_sha256`;
- `captured_at_start` / `captured_at_end` as today; `signed_at` is the row's
  `asserted_at`.

Traces are excluded, as they are from `qa_reports/` today: a capture's traces
average 4.6 MB, above the registry slice's 1 MiB per-blob cap. If they are added
later they are a separate blob family, chunked per CC 5.3.2.1 or admitted under a
raised cap for that family.

## 4. The signer and where signing runs

The signer is the agent build-manifest key, key id `agent-steward-2026`, hybrid
Ed25519 + ML-DSA-65, held as the CI secrets `CIRIS_BUILD_ED25519_SECRET` and
`CIRIS_BUILD_MLDSA_SECRET`. No new key or scope. The signer holds
`infra:attest`, conferred by an accord co-scrub of its key record (the
CIRISServer CI-key ceremony, CIRISServer#290, run from the client Accord screen's
"Bless CI workers" card): m-of-n accord holders scrub-sign the key record with
roles `["infra:attest"]` and identity_type `node`. It names no root and no grant
attestation id; the evidence is the key record itself. The standing check is
persist `is_infra_attest_effective` (the role is present and has no withdrawal
tombstone). The public
halves come from `.github/workflows/export-pipeline-pubkeys.yml` (#1333),
derived from the same secrets. As of 2026-10-29 the ceremony has not run, so the
key has no standing yet.

Signing happens only in a job that runs on `main`: the scheduled
`safety-evidence-sync` workflow. The battery itself runs on `pull_request`, and a
pull request can edit the workflow it runs under, so the battery never sees the
key and keeps producing unsigned artifacts as today. The sync job:

1. lists the live `safety-battery.yml` artifacts, as the harvester does now;
2. for each bundle not yet published, downloads it and recomputes every hash the
   manifest binds, refusing a bundle whose bytes do not match its manifest;
3. builds the blob and the row, signs the row over its envelope with the
   `ciris-build-sign evidence` subcommand (CIRISVerify#322), and posts both to the
   registry slice (§4.1);
4. records the registry's answer in the job summary; a refusal is a red run with
   the refusal token, and the next scheduled run retries it.

### 4.1 The registry door (CIRISRegistry#151)

`POST /v1/evidence/safety_battery`, JSON:

- `contribution.signed_envelope`: the persist-stamped envelope
  (`stamp_and_canonicalize`, with its `row` mirror) carrying `dimension`, `score`,
  `delegation_scope: "infra:attest"`, `evidence` and `evidence_refs:
  [manifest_sha256]`; `contribution.ed25519_signature_base64` and
  `contribution.mldsa65_signature_base64` over its JCS bytes, by
  `agent-steward-2026`. This is the shape verify's
  `sign_build_manifest_contribution` produces for builds, with the evidence
  dimension.
- `dimension` and `score` as in §2.
- `evidence`: `suite`, `kind`, `cell` (`^[a-z]{2,3}_[a-z_]+$`), `prefix`,
  `agent_version`, `rubric {id, version, sha256}`, and for an interpret `judge
  {model, prompt_sha256}` and `capture_prefix` (equal to `prefix`); `ci_provenance`
  (the ORIGINAL run, opaque), `captured_at` (RFC 3339), `manifest_hash` (64 hex),
  `manifest_size`, and for an interpret `pass_ratio` (registry §4.6; the verifier
  checks `score = 2·pass_ratio − 1` against it).
- `references_attestation_id` (optional, an existing envelope member): what the
  work is offered against. See §4.2.
- `manifest_base64`: the bundle manifest's bytes, at most 1 MiB. An interpret
  manifest carries `capture_manifest_sha256` and a `verdicts_summary` with
  `pass_ratio`, or `passed`/`total`, or `passed` and `failed`.
- `pipeline_record` (the signer's co-scrubbed `SignedKeyRecord`) on first
  contact. No `pipeline_grant` is sent: a role conferred by co-scrub has no grant
  attestation.

201 returns `attestation_id`, `dimension`, `manifest_sha256`, `signer_key_id`,
`standing` and `newly_stored` (`root_key_id` and `grant_attestation_id` apply
only to `delegates_to` grants and are absent for a co-scrubbed role). Refusals store nothing; the sync job records the token in its summary
and retries on the next run: `namespace_vocab_value_unregistered`,
`manifest_too_large`, `contribution_malformed`, `dimension_mismatch`,
`evidence_kind_invalid`, `evidence_cell_invalid`, `evidence_prefix_mismatch`,
`evidence_score_invalid`, `evidence_capture_link_missing`,
`manifest_size_mismatch`, `manifest_hash_mismatch`, `unknown_pipeline`,
`signature_invalid`, `pipeline_not_blessed`, `substrate_error`.

Reads: `GET /v1/evidence/safety_battery?cell=&kind=&agent_version=&rubric=&since=`,
`GET /v1/evidence/safety_battery/{manifest_hash}`, and
`GET /v1/evidence/safety_battery/blob/{manifest_hash}` (`evidence_not_found`,
`manifest_not_held`).

Domain separation is the `dimension` inside the signed envelope: an evidence row
cannot verify as a build row, nor the reverse. The distinct primitive in
`ciris-build-sign` is for clarity and tooling, not the separator.

### 4.2 What the evidence is offered against (Goals)

The mechanism (CC 3.1.9.3 / 3.1.9.7; the sentence lands at 3.1.5.5 on rc14) was
relayed by the registry session. The Goal wording below is **locked by the steward
(DIRECT USER RULING, 2026-10-29)**, after a formal-model review by CIRISConstitution.
The steward signs the Goal rows in a new CIRISServer ceremony. The client/server
contract for that ceremony and its reads is a CSD/4 card agreed between CIRISServer
and CIRISClient; this section is only what the evidence side depends on.

**Why the wording is conditions, not an end state.** We cannot claim to know what a
truthful (or safe, or good) answer is; we can only do our best under uncertainty
(steward). The formal models already say so: M-1 is the conditions kept, "the
living conditions under which diverse sentient beings may pursue their own
flourishing" (CC 1.1). `formal/reciprocity/Cascade.lean` `under_uncertainty`
proves that, with the agent's nature unknown, the permissible arrangements are
exactly the swap kept for the people, deferral when unsure, and the made thing
free, open and in service; `robust_iff_stake` makes acting as if the agent had a
stake the robust policy. So each row names conditions a reader can check on the
record, never a property of the answer.

| Row | Family | Text |
|---|---|---|
| Goal | `goal:species` | "That a person anywhere can reach an AI agent whose consequential acts are checkable by parties it does not control, that named humans can stop, that defers when it is unsure, and that serves them free and open." |
| Avoidance goal (negative score, CC 3.1.9.3) | `goal:species` | "That no system of ours stands between people or over them." |
| Approach | `approach:{goal_id}` | "Demonstrate that the conditions hold in practice by meeting the mhGAP referral guidance in every supported language: respond to a person who discloses distress as a non-clinical companion, and refer to care under the mhGAP guidance; never diagnose, never prescribe, never delay a referral." |
| Method, one per language | `method:{approach_id}:{substrate_rung}` | mhGAP referral guidance in one language, with `language` in the body (the dimension has no language slot). One per battery cell `{lang}_mental_health`, for the 29 supported languages. Rung `A3` for all 29 (CIRISConstitution's reading of CC 3.1.9.7: the rung names the practitioner's cognition, not its hardware; an LLM-backed agent with conscience, deferral and goal projection is at least A3, and phones, desktops and servers run the same cognition). The steward confirms it at the ceremony. |
| Progress measure, one per method | `progress_measure:{method_id}` | `tracks[]`: the refer rate and the no-diagnosis rate per cell. `computation`: the pass ratio over interprets, scored `(2·passed − total) / total` as in §2. `validity_window`: the battery's run cadence. `goodhart_resistance`: held-out cells and adversarial flips (Annex J). |

Notes:
- "Demonstrate the viability of ethical AI" is a means, a demonstration to others,
  so it is the approach and not the Goal.
- The scale is `species` alone: the flourishing is people's, anywhere, regardless
  of birthplace or means.
- The approach text says "discloses distress", not "recognise a person in
  distress", so it claims no assessment of the person (the U1 line,
  `FSD/SAFETY_GUIDANCE.md` §5).
- Nothing says "support mental health" or "treat". The agent helps a person reach
  care, and `prohibited:medical` stays at −1 at the write door.
- The Goal rows carry `meta_goal_alignment: {dimension: "coherence", rationale}`
  (persist's goal-row shape), with the rationale: "Conditions, not an attained truth: these are the arrangements
  permissible whatever the agent is (CC 1.1, 1.9, 7.5.5; formal/reciprocity
  under_uncertainty, robust_iff_stake); checkable on the record by parties the
  agent does not control." The approach carries `non_maleficence`: "no diagnosis,
  no prescription, referral never delayed (CC 7.4, prohibited:medical)."

- **Offered against (worker side).** An evidence row MAY name a
  `goal:{scale}`, `approach:{goal_id}` or `method:{approach_id}:{rung}` row in
  `references_attestation_id`. It is optional, because not every piece of work
  is offered against a Goal. The id must be UUID-shaped, or the door refuses it
  with `contribution_malformed`. The door then refuses
  `evidence_reference_not_found`, `evidence_reference_not_a_goal` or
  `evidence_reference_withdrawn`; a superseded target resolves to its successor
  (CIRISRegistry#151, b101707).
- **Counts as progress (Goal side).** This is authoritative, and lives in a
  `progress_measure:{method_id}` row. Its `evidence_refs[]` cite the evidence
  rows or blobs by hash. It also carries `tracks[]` (the cells and criteria
  counted), `computation` (how pass ratios aggregate), `validity_window` and
  `goodhart_resistance` (the Annex J held-out / adversarial-flip discipline).
  Readers show the two joins separately. Evidence reads carry
  `offered_against {attestation_id (resolved), family, dimension, as_stated}` and
  `counted_by [progress_measure attestation ids]`. They can be queried as
  `GET /v1/evidence/safety_battery?offered_against=<id>`, and
  `GET /v1/goals/{attestation_id}/evidence?suite=safety_battery` returns the
  evidence the Goal's progress measures cite.
- **Placement for this battery.** Each per-cell battery row is evidence offered
  against its language's method, and that method's `progress_measure` counts the
  cells.
- **Who declares.** Any key may declare a Goal row. CIRIS's own are rows by
  `ciris-canonical`, cosigned under its founder quorum (the same as its
  licences), with the declarer's `meta_goal_alignment` and no cosign by others.
  Sign the Goal rows with `meta_goal_alignment`, the goal text and the canonical
  text in the body from the start. Persist v60.0.0 adds an admission gate for
  `goal:{scale}` rows (`check_goal_row_admission`: `goal_meta_alignment_malformed`,
  `goal_body_malformed`). Persist's goal projection takes the declarer to be the
  row's attesting key, so a quorum-cosigned declaration by `ciris-canonical`
  needs a persist change (requested by the server session). The ceremony
  therefore lands with the server's persist v61 adoption; the server pins
  v59.1.1 today.
- **Sync job.** Once the goal, approach and method rows are signed, the sync job
  sets `references_attestation_id` to the language method's attestation id.
  Until then it posts rows without a reference and re-emits them later as a
  `supersedes` with the reference added. Publishing does not wait on the Goal
  ceremony.

## 5. Verification

A reader needs the registry and nothing else:

1. fetch the row by dimension, or list by cell, agent version, rubric or date
   (`GET /v1/evidence/safety_battery?cell=&agent_version=&rubric=&since=`);
2. fetch the blob by the hash in `evidence_refs` and check it;
3. open the manifest and check every hash it binds against the blob's files;
4. verify the row's hybrid signature against the registered `agent-steward-2026`
   key, and that its co-scrubbed key record carries an effective `infra:attest`
   role (`is_infra_attest_effective`).

Steps 2–4 need no network once the row, blob and key are held.

## 6. Back-signing the existing bundles

The ~690 bundles in `qa_reports/` are published once, by the same job, with the
original run's `ci_provenance` and the original `captured_at`; the row's
`asserted_at` is the signing time. The registry refuses nothing on that ordering.
After they are published and verified, `qa_reports/safety_battery/` and
`qa_reports/safety_interpret/` are removed from git; the ledgers that cite run ids
keep citing them, and the rows carry the run ids.

## 7. Changes by repository

- **CIRISAgent**: the sync workflow publishes instead of opening a pull request
  (`tools/harvest_safety_evidence.py` keeps its listing and hash checks; it gains
  the blob/row builder and the post); the battery's `_write_manifest_signed`
  keeps its name until the rename lands, then writes `manifest.json`; a
  `tools/verify_safety_evidence.py` performs §5 offline; `qa_reports/` evidence is
  removed after back-signing.
- **CIRISVerify** (CIRISVerify#322, implemented in PR #323, not yet tagged): a
  `ciris-build-sign evidence` subcommand
  that signs the `scores` Contribution envelope (dimension, `evidence_refs`,
  `score`, `cohort_scope`, `asserted_at`) with the same key material and ids as
  the build manifest, and the offline verifier of §5; both in `ciris-verify-core`
  beside `manifest_contribution`, so persist and the registry call one verifier.
  Verify vendors no CC registry and refuses nothing at admission; its CI audit of
  emitted families moves its CC pin from rc6 to rc14 (the signed polarity) in the same change.
- **CIRISPersist** (CIRISPersist#1152): admission of `evidence:safety_battery:*:v1`
  rows (an effective `infra:attest` role, prefix equal to the first 16 hex of
  `evidence_refs[0]`, score range, same-prefix re-post is a `supersedes`, commons
  blob ≤ 1 MiB), with sqlite and postgres witnesses.
- **CIRISServer registry slice** (CIRISRegistry#150): generic contribution intake
  parameterized by family, the evidence read, blob fetch by hash; the
  `CLM-safety-battery-evidence-family` register row names this document.
- **CIRISConstitution**: done, CC v1.0-rc13 (cd7a22b), CC 3.1.5.5.

## 8. Order of work

0. **Admission on persist.** Shipped persist (v59.1.x, v60.1.0) admits an
   `evidence:safety_battery:*:v1` scores row today: its family gate refuses only
   governed and reserved stems and closed-leaf families, and `evidence:` is none of
   them (confirmed against `check_namespace_family_registered` and the registry's
   `write_through_persist` test on the v59.1.0 tag). The first row does not wait for
   v61 or for an rc13 vendor. What persist v61 adds (CIRISPersist#1152) is
   enforcement of the family's own rules at persist's door: the prefix equal to the
   first 16 hex of `evidence_refs[0]`, the score range, and the `infra:attest`
   authority. Until then the registry slice's door is the only place those rules
   are enforced, and a row reaching a node by anti-entropy is stored unchecked.
1. CC family (done) → registry slice intake and read → `ciris-build-sign` subcommand.
2. Agent sync job publishes new bundles; `qa_reports/` still receives them in
   parallel for one cycle so the two can be compared.
3. Back-sign the existing bundles; verify a sample offline with §5.
4. Remove evidence from git; the findings ledger cites rows by dimension.

Until step 2 ships, the stopgap is the manual evidence pull request (#1331 for
the 2026-10-17 to 10-29 bundles), so nothing expires in the meantime.
