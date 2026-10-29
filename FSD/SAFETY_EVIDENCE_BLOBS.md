# Safety-battery evidence as signed CEG blobs

Status: proposed (2026-10-29). Owner: CIRISAgent. Registry family: CC 3.1.5.5
(rc13 @ 4504dda). Registry intake: CIRISRegistry#150.

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

Each row is a `scores` Contribution at `cohort_scope: federation` (public commons
evidence, replication audience public), with `evidence_refs: [<blob sha256>]`.
`score` is `1.0` for a capture and the judged pass ratio for an interpret.

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
`CIRIS_BUILD_MLDSA_SECRET`, and already registered with the registry with the
`delegates_to(root → key, infra:attest)` grant that build manifests use. No new
key, ceremony or scope.

Signing happens only in a job that runs on `main`: the scheduled
`safety-evidence-sync` workflow. The battery itself runs on `pull_request`, and a
pull request can edit the workflow it runs under, so the battery never sees the
key and keeps producing unsigned artifacts as today. The sync job:

1. lists the live `safety-battery.yml` artifacts, as the harvester does now;
2. for each bundle not yet published, downloads it and recomputes every hash the
   manifest binds, refusing a bundle whose bytes do not match its manifest;
3. builds the blob and the row, signs the row over its envelope with
   `ciris-build-sign sign --primitive safety_evidence`, and posts both to the
   registry slice;
4. records the registry's answer in the job summary; a refusal is a red run with
   the refusal token, and the next scheduled run retries it.

Domain separation is the `dimension` inside the signed envelope: an evidence row
cannot verify as a build row, nor the reverse. The distinct primitive in
`ciris-build-sign` is for clarity and tooling, not the separator.

## 5. Verification

A reader needs the registry and nothing else:

1. fetch the row by dimension, or list by cell, agent version, rubric or date
   (`GET /v1/evidence/safety_battery?cell=&agent_version=&rubric=&since=`);
2. fetch the blob by the hash in `evidence_refs` and check it;
3. open the manifest and check every hash it binds against the blob's files;
4. verify the row's hybrid signature against the registered `agent-steward-2026`
   key, and that key's `infra:attest` grant from the root.

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
- **CIRISVerify** (`ciris-build-sign`, `src/ciris-build-tool`): today `--primitive`
  is only a build-manifest label and the tool signs a build manifest, not a CEG
  envelope. Needed: a subcommand that signs the `scores` Contribution envelope
  (dimension, `evidence_refs`, `score`, `cohort_scope`, `asserted_at`) with the
  same key material and ids as the build manifest, and the offline `verify` of §5.
- **CIRISPersist** (CIRISPersist#1152): admission of `evidence:safety_battery:*:v1`
  rows (the `infra:attest` grant, prefix equal to the first 16 hex of
  `evidence_refs[0]`, score range, same-prefix re-post is a `supersedes`, commons
  blob ≤ 1 MiB), with sqlite and postgres witnesses.
- **CIRISServer registry slice** (CIRISRegistry#150): generic contribution intake
  parameterized by family, the evidence read, blob fetch by hash; the
  `CLM-safety-battery-evidence-family` register row names this document.
- **CIRISConstitution**: done, rc13 @ 4504dda, CC 3.1.5.5.

## 8. Order of work

0. **The vendored CC registry.** Admission checks the dimension against the CC
   registry persist and verify vendor. Shipped persist (v60.1.0) vendors CC
   1.0-rc9; rc12 is staged on a branch; rc13, which carries this family, is
   untagged. Persist vendors tagged CC only, on its v61 head (mid-refactor, no
   date). So the first row needs, in order: the rc13 tag, persist (and verify)
   vendoring it, and a release the registry slice runs on. Whether that is v61 or
   a v60.x cut carrying the rc13 vendor alone is the owner's call.
1. CC family (done) → registry slice intake and read → `ciris-build-sign` subcommand.
2. Agent sync job publishes new bundles; `qa_reports/` still receives them in
   parallel for one cycle so the two can be compared.
3. Back-sign the existing bundles; verify a sample offline with §5.
4. Remove evidence from git; the findings ledger cites rows by dimension.

Until step 2 ships, the stopgap is the manual evidence pull request (#1331 for
the 2026-10-17 to 10-29 bundles), so nothing expires in the meantime.
