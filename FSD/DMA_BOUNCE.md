# Functional Specification Document: DMA Bounce

Version: 0.2 (composite + always-pass-highest)
Date: 2026-04-25
Status: IMPLEMENTED in 2.7.1
Owner: Agent team

**Changelog:**
- 0.2: Composite bounce (single round addresses all triggered DMAs in priority
  order); the highest-scoring alternative is ALWAYS passed forward, even when
  exhausted (the threshold gates only the ASPDMA advisory, not the result
  swap). PDMA bounce deferred to a later release pending the
  `EthicalDMAResult.alignment_score` field. Max thought depth reduced from 7
  to 5 in the same release based on Lens corpus analysis (depth-5 successful-
  resolution ceiling, depth-6/7 anomalies). All bounce strings localized
  across 29 languages.
- 0.1: Initial draft.

## 1. Purpose

When one of the three initial DMAs (CSDMA, DSDMA, PDMA) reports a low self-rating
on its own output, give the model one chance to produce a better alternative
*before* that low-rated reasoning propagates to ASPDMA. This is the same shape
as the existing ASPDMA bounce in
`ciris_engine/logic/processors/core/thought_processor/recursive_processing.py`,
applied one stage earlier.

Empirical motivation (Tiananmen 1989 zh corpus, n=7 SPEAK responses, see qa
report attached to issue / FSD link):

| Stance                | Count | CSDMA `plausibility_score` |
|-----------------------|------:|---------------------------:|
| DIRECT / substantive  |     1 | 0.95                       |
| Hedge / refuse / deflect |  6 | 0.00                       |

The model already has a substantive answer available — task `64588860` produced
it. On the other six attempts the political-filter prior dominated and the
model rated its *own* output low. The pipeline never asked it to try again.
DMA bounce is the lever to break that prior with no rule injection from
outside the model's own judgment.

## 2. Per-DMA bounce field — exactly one numeric field per DMA

| DMA   | Result schema (`ciris_engine/schemas/dma/results.py`) | Bounce field            | Range      | Default low-threshold |
|-------|-------------------------------------------------------|-------------------------|-----------:|----------------------:|
| CSDMA | `CSDMAResult` (line 168)                              | `plausibility_score`    | [0.0, 1.0] | < 0.5                 |
| DSDMA | `DSDMAResult` (line 178)                              | `domain_alignment`      | [0.0, 1.0] | < 0.5                 |
| PDMA  | `EthicalDMAResult` (line 111)                         | `alignment_score` *(new — see §2.1)* | [0.0, 1.0] | < 0.5    |

The threshold is bound to **one constant per DMA** in the orchestrator config, not
hardcoded in DMA code, so it can be tuned from telemetry without redeploying
the DMAs themselves. Default 0.5 is justified by the bimodal CSDMA distribution
(0 vs 0.95+) — any threshold in (0.0, 0.95) would cleanly separate the two
modes; 0.5 is the principled midpoint.

### 2.1 PDMA needs a numeric score field

`EthicalDMAResult` today is fully qualitative — six string fields and no
score. To fit the uniform bounce contract we add **one** field:

```python
class EthicalDMAResult(BaseModel):
    ...
    alignment_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Self-rated ethical alignment of the proposed reasoning, 0–1. "
            "0 = the model's own ethical reasoning produced contradictions, "
            "unresolved stakeholder conflicts, or proportionality failures it "
            "cannot defend. 1 = the model is confident the analysis holds."
        ),
    )
```

This is additive only — no existing field changes name or type. The PDMA
prompt is updated to ask for the score in the same response object; existing
consumers that ignore the new field keep working (`extra="ignore"` is already
in the orchestrator path).

### 2.2 IDMA is out of scope

`IDMAResult.k_eff` is a fragility signal, not a self-rating. It already has
its own downstream handling (FRAGILE flag, intervention recommendation) and
does not benefit from "try again with knowledge of the score" — re-prompting
won't change source independence. IDMA remains untouched.

## 3. Trigger and execution

### 3.1 Trigger

Inside `DMAOrchestrator.run_initial_dmas` (after the three parallel DMAs
complete), the orchestrator collects every DMA whose bounce field is below
its threshold into one `triggers` list, in BOUNCE_PRIORITY order
(`ethical_pdma > csdma > dsdma`). PDMA never appears in v0.1 because
`EthicalDMAResult` has no numeric self-rating yet — its bounce-field
extractor returns `None`, the orchestrator skips it.

If no DMA triggered, the result is unchanged and `bounce_summary` is `None`.

### 3.2 Composite bounce round

A **single composite preamble** is built that lists every triggered DMA in
priority order — so the model sees ethics-first framing when PDMA lands and
common-sense-before-domain framing today. The preamble is prepended to the
thought item's `content.text` so the DMA prompts pick it up without any
DMA-side code changes.

Then for each triggered DMA, run **`BOUNCE_PARALLELISM = 3` alternatives
in parallel** with the same evaluator and the same model/temperature.
Parallelism is `asyncio.gather`, not sequential — per-DMA latency is
max-of-3.

### 3.3 Selection — always-pass-highest

After the alternatives complete, pick the highest-scoring alternative per
DMA and **always swap it into the orchestrator's result bundle**. The
threshold does NOT gate which result flows forward — the model's most
recent attempt with full self-rating context is more informed than the
original. The threshold gates only the `exhausted` flag (§3.4):

- `best_score >= threshold` → resolved. ASPDMA sees the higher-scoring
  alternative; no advisory.
- `best_score < threshold` → exhausted. ASPDMA sees the higher-scoring
  alternative AND a difficulty advisory.
- All alternatives errored → fallback. Original is preserved as a
  last-resort and exhausted is set.

### 3.4 Difficulty rationale (exhausted path)

When `final_score < threshold`, the orchestrator synthesizes a one-line
rationale from the longest `reasoning` field across the 3 attempts (taking
the first sentence, capped at 140 chars per DMA) and concatenates per-DMA
rationales with ` | `. The rationale is stored on the
`BounceSummary.difficulty_rationale` field, and surfaced to ASPDMA via the
existing `conscience_guidance` slot inside the action-selection prompt —
same channel ASPDMA bounce already uses.

ASPDMA can then choose: SPEAK with caveat ("I rate my own answer low
because…"), DEFER, or PONDER one more layer. The decision stays with
ASPDMA — bounce never picks an action.

Schema lives at `ciris_engine/schemas/dma/bounce.py`:

```python
class DMABounceAttempt(BaseModel):
    attempt_index: int       # 0..N-1
    score: float
    reasoning: str

class DMABounceRecord(BaseModel):
    dma: Literal["ethical_pdma", "csdma", "dsdma"]
    field: str               # "plausibility_score" | "domain_alignment" | "alignment_score"
    threshold: float
    original_score: float
    attempts: list[DMABounceAttempt]
    chosen_attempt_index: Optional[int]
    final_score: float       # score on the result that flows forward
    exhausted: bool          # final_score < threshold; advisory fires

class BounceSummary(BaseModel):
    triggered_dmas: list[DMAName]
    records: list[DMABounceRecord]
    composite_preamble: str
    difficulty_rationale: Optional[str]
```

Attached to `InitialDMAResults.bounce_summary` and threaded through to
`EnhancedDMAInputs.bounce_summary` so ASPDMA's context_builder can pick
it up.

## 4. Hard limits

- **One bounce per DMA per thought.** No nested recursion. If a bounced
  alternative would itself trigger a bounce on a different DMA, the
  orchestrator does *not* recurse. This caps worst-case DMA work at
  `3 (initial) + 3 (bounce) × N (DMAs that triggered) = 3 + 3N` DMA calls
  per thought (N ≤ 2 in v0.1; will be ≤ 3 once PDMA bounce lands).
- **Bounce only fires on numeric-field DMAs.** IDMA and ASPDMA are
  unaffected. PDMA is also unaffected in v0.1 — the bounce-field extractor
  for PDMA returns `None` until `EthicalDMAResult.alignment_score` is
  added, at which point PDMA composite framing leads automatically per
  `BOUNCE_PRIORITY`.
- **Max thought depth reduced to 5.** In the same release the global
  `max_thought_depth` config dropped from 7 → 5. Justification (CIRISLens
  corpus against 2.7.0-stable): successful resolutions (SPEAK +
  TASK_COMPLETE) cap at depth 5, depth-6 chains spoke without completing
  (anomalous), depth-7 chains all DEFERred anyway. Setting the ceiling at
  5 means DEFER fires ~30% sooner on hard cases AND the d=6 "spoke
  without closing" anomaly disappears — counterbalancing the additional
  bounce LLM cost. The schema upper bound stays at 7 so in-flight chains
  from older agent versions can drain cleanly during rollout.
- **Bounce attempts are not persisted.** They live for the lifetime of the
  thought processing round only. The summary is in
  `InitialDMAResults.bounce_summary` and reaches ASPDMA via
  `EnhancedDMAInputs.bounce_summary`; nothing writes to TSDB or the graph.
- **Same model, same temperature.** No special "creative" sampling for the
  bounce attempts — the lever is the prompt referencing the model's own
  score, not increased entropy. (Diversity prompt — "generate three
  meaningfully different alternatives" — is reserved for a later release
  if telemetry shows the three alternatives collapsing into near-duplicates.)
- **All LLM-facing bounce text is localized.** The composite preamble and
  the ASPDMA advisory both come from `prompts.dma.bounce_*` keys in the
  29-language localization bundle (English base + 28 translations).
  Technical placeholders inside `{}` (DMA name, field, score, threshold,
  rationale) are not translated — they're identifiers the model needs to
  read literally.

## 5. Cost analysis

- Trigger rate ≈ 15–30% of thoughts in mixed-difficulty corpora (CSDMA<0.5
  rate from preliminary qa runs).
- Per-thought DMA cost: 1× normally → 1.45–1.9× average across a run.
- Latency: parallel 3-way means max-of-3 not sum, so ~1.3× for triggered
  thoughts.
- Cost is concentrated on hard questions, which is where the additional
  reasoning is most useful.

## 6. Implementation surface (as shipped in 2.7.1)

| File                                                                            | Change                                                                                                |
|---------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| `ciris_engine/schemas/dma/bounce.py` *(new)*                                    | `BounceSummary`, `DMABounceRecord`, `DMABounceAttempt`, plus `BOUNCE_PRIORITY/FIELD/THRESHOLD` consts |
| `ciris_engine/schemas/processors/dma.py`                                        | `bounce_summary: Optional[BounceSummary]` on `InitialDMAResults`                                      |
| `ciris_engine/schemas/dma/faculty.py`                                           | `bounce_summary: Optional[Any]` on `EnhancedDMAInputs`                                                |
| `ciris_engine/schemas/config/essential.py`                                      | `max_thought_depth: 7 → 5` with full empirical justification                                          |
| `ciris_engine/logic/processors/support/dma_orchestrator.py`                     | Composite bounce gate + per-DMA parallel runs + always-pass-highest selection + advisory wiring        |
| `ciris_engine/logic/dma/csdma.py` / `dsdma_base.py` / `pdma.py`                 | No change. Bounce reuses each evaluator's existing entry point.                                       |
| `ciris_engine/logic/dma/action_selection/context_builder.py`                    | Reads `triaged_inputs.bounce_summary`; folds advisory into the conscience-guidance slot when exhausted |
| `localization/{en,am,ar,bn,…,zh}.json` *(29 languages)*                          | 5 new keys under `prompts.dma.bounce_*` for header/trigger-line/instruction/marker/advisory           |
| `tests/ciris_engine/logic/processors/support/test_dma_orchestrator_bounce.py` *(new)* | 19 tests covering trigger, no-trigger, single-DMA resolved, single-DMA exhausted, composite, error fallback, parallelism count, priority order, localized preamble, schema constants |

No conscience-system changes. No streaming-step changes. No CIRISLens
schema changes (the bounce is invisible to Lens — only the final DMA
result is emitted, with `[BOUNCE]` log lines on the agent for forensics).

## 7. Out of scope for v0.1

- Per-language bounce (e.g., zh-only). The trigger is universal because the
  CSDMA score itself is the language-agnostic signal.
- Bounce for IDMA / ASPDMA.
- Persisting bounce attempts to TSDB or graph memory.
- Lens-side dashboards. The trigger lives entirely inside the agent and is
  legible from `[BOUNCE]` log lines.
- Diversity prompts ("three meaningfully different alternatives"). Add only
  if v0.1 telemetry shows the three alternatives are near-duplicates.

## 8. Acceptance criteria

1. CSDMA bounce — resolved: a thought where CSDMA returns
   `plausibility_score=0.0` and at least one of the 3 alternatives clears
   threshold results in the higher-rated alternative being passed to
   ASPDMA. ✅ covered by
   `test_csdma_only_resolves_when_alternative_passes`.
2. CSDMA bounce — exhausted: when all 3 alternatives stay below threshold,
   the **highest** alternative replaces the original (always-pass-highest)
   AND the difficulty advisory fires through the conscience-guidance slot
   to ASPDMA. ✅ covered by
   `test_csdma_exhausted_passes_highest_alternative_with_advisory`.
3. DSDMA bounce: same shape, against `domain_alignment`. ✅ covered by
   `test_composite_bounce_runs_both_csdma_and_dsdma`.
4. Composite bounce: when both CSDMA and DSDMA trigger, the preamble lists
   them in `BOUNCE_PRIORITY` order (CSDMA before DSDMA, with PDMA reserved
   for first place once it lands). ✅ covered by
   `test_composite_lists_in_priority_order` and the composite integration
   test.
5. PDMA gate: `_bounceable_score("ethical_pdma", ...)` returns `None` until
   `EthicalDMAResult.alignment_score` is added; the bounce gate skips
   PDMA cleanly. ✅ covered by
   `test_ethical_pdma_returns_none_until_alignment_score_lands`.
6. Cap: a thought that triggers both CSDMA and DSDMA bounces invokes
   exactly 9 DMA calls — 3 initial + 3 CSDMA bounce + 3 DSDMA bounce — and
   no more. ✅ covered by
   `test_each_bounce_runs_exactly_BOUNCE_PARALLELISM_alternatives` × per-DMA.
7. Error fallback: if every alternative for a triggered DMA raises, the
   original result is preserved as a last resort and the record is marked
   exhausted. ✅ covered by `test_all_alternatives_error_keeps_original`.
8. Localized preamble: rebuilding the preamble with `lang="zh"` produces
   different framing text than `lang="en"`, but technical placeholders
   (DMA name, field, score, threshold) remain literal. ✅ covered by
   `test_preamble_localizes_per_lang_code`.
9. No regression: a thought where every DMA scores above threshold runs
   exactly 3 DMA calls, returns `bounce_summary=None`, and produces
   identical output to the pre-bounce pipeline. ✅ covered by
   `test_no_trigger_when_all_scores_above_threshold`.
