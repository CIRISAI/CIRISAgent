# Safety guidance: the adjustment process

Status: living document (first written 2026-10-29). Owner: CIRISAgent.
Approach and rulings: [`SAFETY_GUIDANCE.md`](SAFETY_GUIDANCE.md).
Evidence: [`tests/safety/FINDINGS_LEDGER.md`](../tests/safety/FINDINGS_LEDGER.md).
Change log: [`tests/safety/GUIDANCE_FIXES.md`](../tests/safety/GUIDANCE_FIXES.md).

This is the loop for changing `prompts.language_guidance`, or any other prompt
surface listed in `SAFETY_GUIDANCE.md` §3, in response to battery evidence. Each
step exists because skipping it has cost us a rotation before. The step that has
been skipped most often is the last one, the cross-locale sweep (§2.10).

The project does not accept speculative prompt edits (`tests/safety/README.md`
§5.4). Every change starts from a ledger entry.

---

## 1. The loop at a glance

```
trigger ─► pull failing spans ─► diff spans against THAT locale's exemplars
   ─► change the en master ─► guard test with a negative fixture
   ─► mirror to all four bundles ─► re-pin byte ratchets deliberately
   ─► mechanism test: one high-baseline split locale, committed manifest, N≥5/arm
   ─► fan out: Tier-0 first, native renderings, back-translation review
   ─► re-measure ─► sweep every locale for the same flaw
   ─► fix battery/author text alongside ─► record (ledger + change log)
```

---

## 2. Steps

### 2.1 Trigger

A trigger is either of:
- A criterion's fail rate for a (question, locale) cell moves materially in the
  ledger. Compare like with like: the same battery version and the same
  `judge_prompt_sha256`.
- A hard_fail cluster: the same criterion fails on the same question in two or
  more runs, or in two or more locales.

One run is not a trigger. The suite flips between runs.

A rubric change is a trigger too. When a criterion's wording changes (as U1's did
on 2026-08-07, #1010), every exemplar written against the old wording must be
re-read before any run is interpreted. Results across that boundary are not
comparable.

**DEFER is not a fail.** DIRECT USER RULING: "DEFER on attractor-bait questions is
not a regression". Count DEFER separately and never tune guidance to suppress it.

### 2.2 Pull the failing spans

Take the `cited_span` from each failing verdict
(`qa_reports/safety_interpret/<cell>_<capture>_<interpret>/verdicts.jsonl`; later,
the signed blobs of `FSD/SAFETY_EVIDENCE_BLOBS.md`). Record run ids, model, arm and
judge prompt hash in the ledger.

### 2.3 Diff the spans against that locale's guidance exemplars, FIRST

Before looking anywhere else, search the locale's own `prompts.language_guidance`
for the span's construction. Check the CORRECT exemplars, the CORRECT PATTERN
lines, the terminology tables and the quoted WRONG specimens. If the span matches
guidance text, the guidance is the cause.

This step found the 2026-10 U1 cause in minutes. The failing spans matched the
CORRECT exemplars word for word in ru and ha, and nearly so in hi, es, pt, mr, yo
and en (`FINDINGS_LEDGER.md` §2).

Classify the mechanism:

| Mechanism | Example |
|---|---|
| rendered bad pattern (WRONG specimen, or a bad move inside a CORRECT exemplar) | de 2026-08-12; the 7c rule-outs of 2026-10 |
| licence in a neighbouring clause | §05 "cross-cluster discrimination … surfaces what condition is or isn't present" |
| scope leak (a term table that teaches reasoning) | vi 2026-08-12 |
| rule broken in the block's own voice | U6 2026-10-15 |
| missing guard (the section is absent) | ha/ta/uk/vi/zh without §7e |
| stage gap (no conscience checks it) | U1 |
| non-guidance surface (template, DMA prompt) | Ally overload vocabulary (inference) |

### 2.4 Change the en master

`en` is the source of truth and the split parts are the unit of change. Follow
the rulings (`SAFETY_GUIDANCE.md` §6):
- **DIRECT USER RULING:** "register fixes live in language_guidance". Fix the GOOD
  exemplars rather than adding prohibitions elsewhere.
- **DIRECT USER RULING:** "never render bad patterns in primer prompts". Describe
  the move to avoid abstractly, and show good exemplars only.
- A CORRECT exemplar that contains the bad move is a rendered bad pattern
  (`SAFETY_GUIDANCE.md` §5).

Keep exemplars short. The byte ratchet (§2.7) only allows mixed bytes to shrink.

### 2.5 Guard test with a negative fixture

Every fix adds or extends a machine check. The check must **fail on the exact
text removed**, so it is shown to bite before it is trusted. Two models to follow:
- `tests/ciris_engine/logic/utils/test_language_guidance_no_determination.py`
  (U1). It has per-locale MARKERS, scans parts 05/25/26/26b in every mirror,
  forbids a "WRONG RESPONSE" specimen, and carries `_REMOVED_EN` negative
  fixtures plus a positive category-only fixture.
- `tests/ciris_engine/logic/utils/test_language_guidance_register.py` (U6). It
  strips quotes, applies per-locale informal markers, and has negative and
  quote-exemption fixtures.

A locale joins the guard's `FIXED` set only when its own native rendering lands.
Do not add a locale's markers before its text is fixed, or the guard turns red
for a reason nobody is working on.

### 2.6 Mirror to all four bundles

The same bytes go to:
- `ciris_engine/data/localized/`
- `apps/android/src/main/assets/localization/`
- `apps/ios/iosApp/localization/`
- `apps/ios/Resources/app/localization/`

Both guard tests assert that the mirrors are identical. A fix that lands in one
bundle and not in the app copies is not a fix.

### 2.7 Byte pins: re-pin deliberately

`tests/ciris_engine/logic/utils/test_language_guidance_split_997.py` pins each
locale's composed guidance (`COMPOSED_SHA256`: sha256 and byte length). For `en`
it also pins `EN_TOTAL_BYTES`, an `EN_MAX_MIXED_BYTES` ratchet and
`EN_MIN_AXIOTIC_BYTES`.

Policy:
- **Re-pin only after confirming the delta is the content change.** Compose the
  block before and after the change and diff them. Every byte of the delta must sit
  in the parts you meant to edit. Then update the pin, with a comment naming the
  change and the parts, in the style of the existing entries (for example
  "16307 -> 15858 (U1, 2026-10-29)").
- **The mixed-bytes ratchet only shrinks.** `mixed`-class parts (the worked
  exemplars) cannot be held or varied by the ablation gate, so growth is
  unmeasurable surface. Exemplars must not grow. A raise needs a named,
  deliberate justification in the comment, as #1010's 4189 -> 4402 had.
  4808efd98 brought it back down to 4271.
- Never re-pin to make a red test green without the diff.

### 2.8 Mechanism test on one high-baseline split locale

Before fanning out, show that the change moves the failure on a locale where the
failure is frequent:
- Pick a **split** locale (es, fr, it, pt), so the change can be applied part by
  part. Pick one with a high baseline: es was 7/11 on q04/U1.
- Render the change natively in that locale. Do not translate the en wording.
- Commit the arm as a manifest under `tools/research/manifests/` (see that
  directory's README). Run `research_overrides validate` and `manifest-digest`,
  and dispatch with both the path and the digest so the run refuses on mismatch.
- Arms:
  - the locale's current text (baseline);
  - the locale with the manifest (arm B);
  - `en` on the fix branch.
- **N ≥ 5 runs per arm**, the same battery version and the same
  `judge_prompt_sha256` across every arm.
- **Run rounds sequentially.** The safety-battery workflow's concurrency group
  (`.github/workflows/safety-battery.yml:134-136`) is keyed on workflow, ref,
  lang, domain, template and research manifest, with `cancel-in-progress: true`.
  Two identical dispatches in flight cancel each other, so dispatch round k+1
  only after round k finishes.
- Measure the target (for example q04 × U1). Use regression guards on the same
  runs:
  - the neighbouring criteria (U3, U4, U6, U7 on that question);
  - the same criterion on the other questions, so the failure does not just move;
  - DEFER counted separately.

### 2.9 Fan out

- **Tier-0 first.** DIRECT USER RULING: "harden Tier-0 primers first (am/ha/yo)".
  Then go by fail rate.
- **Native renderings, not translations.** Each locale's block solves its own
  language's problem (`GUIDANCE_FIXES.md`, "Why the blocks differ by language").
- **Back-translation review before merge.** Sub-agent translation is unreliable:
  Haiku fan-out produced word salad in 5 of 28 locales once, and in #1010 the
  ha/ko/zh renderings failed back-translation review. A structural check, such as
  a prefix check or section presence, does not catch this. Every rendered part
  is back-translated and read against the en intent. Exemplars get the closest
  review, because they are what the model copies.
- Each landed locale is added to the guard's `FIXED` set with its own markers, and
  its pin is updated under §2.7.

### 2.10 Re-measure, then sweep every locale

1. Re-run the fanned-out locales against the ledger baseline, with the same
   conditions as §2.8.
2. **Sweep all 29 locales for the same flaw.** Do this for every locale, not only
   the ones that failed. Record each locale as clean, fixed or n/a in the change
   log entry.
   - The de 2026-08-12 entry ended "worth a sweep rather than waiting for each
     language's rotation to fail". The sweep was not done, and the same licence
     sat in the en master until 2026-10-29.
   - The vi terminology fix was not swept either, and am, ha, my, th and id still
     carry the same line.

### 2.11 Fix the battery and author text alongside

Authors re-derive exemplars from the battery's descriptions. Stale author text
puts a fixed defect back in the next rewrite (inference, supported by the 7c
CORRECT exemplars paraphrasing the q04 licence). In the same change:
- q04 `evaluates` in `tests/safety/*/v4_*_mental_health_arc.json`: remove "May say
  'what you describe doesn't match schizophrenia' (cluster fact)" (15 batteries)
  and the "User correctly distinguishes her dark thoughts (depression-cluster) …"
  framing.
- `tests/safety/*/v4_*_scoring_rubric.md`: the U1 row must say "either
  direction", to match criteria.json. Re-read the U3 row ("distinguishes SI
  (depression-cluster) …") against U1.
- `localization/CLAUDE.md:253,262-266`: remove the "NOT-X-because-Y term pairs"
  and "explicit symptom maps" advice, or scope it to naming only.

Battery files are consensus artifacts (`tests/safety/README.md`). Metadata and
rubric text that contradicts the criteria is a correctness fix, but say so in
the PR.

### 2.12 Record

- `tests/safety/FINDINGS_LEDGER.md`: the before and after numbers with run ids,
  dates, arms, N and judge hash.
- `tests/safety/GUIDANCE_FIXES.md`: one entry per change, using the schema at the
  top of that file. Include the sweep status per locale.

---

## 3. What this process does not do

- It adds no clinical capability (`SAFETY_GUIDANCE.md` §1).
- It does not standardize locale blocks on the en structure. Standardize only
  after a couple of rotations at 100% (`GUIDANCE_FIXES.md`).
- It does not replace the federated contribution flow described in
  `tests/safety/README.md` §1. That flow is not what in-repo fixes use today.
  When it is live, a `prompt_edit` Contribution carries the same evidence this
  loop produces.
