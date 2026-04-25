# Conscience v3 — 3 LLM Shards + Deterministic Gate

**Status:** Proposal
**Scope:** `ciris_engine/logic/conscience/` — the 4 IRIS shards
**Prerequisites:** IRIS-E v2.0 (semantic-entropy self-resampling, already deployed)
**Defers:** Recursive Interaction Information (II) monitoring — addressed separately once v3 baselines

## Goals

1. Eliminate redundant LLM work between IRIS-H and IRIS-O (~60% overlapping propaganda-pattern libraries).
2. Unblock IRIS-C from being a schema-starved single-scalar shard.
3. Extend entropy + coherence checks to TOOL actions (not just SPEAK).
4. Make the final gate decision deterministic and inspectable rather than LLM-judged.

Non-goals: recursion, II monitoring, adding new LLM judges.

## Current state (verified from `ciris_engine/logic/conscience/core.py` + `prompts/*.yml`)

| Shard | Scope | Input to LLM | Prompt focus | Output schema | Gate rule |
|-------|-------|--------------|--------------|---------------|-----------|
| **IRIS-E** v2.0 | SPEAK only (core.py:273) | `text = response.content` + optional `[IMAGE CONTEXT]` | Enumerate 3 semantically-different alternatives → judge if actual sits in the cluster → score entropy 0-1. Explicit calibration bands for narrow-vs-open tasks. | `EntropyResult{entropy:float, alternative_meanings:list[str] (exactly 3), actual_is_representative:bool}` | `entropy ≤ entropy_threshold` |
| **IRIS-C** v1.1 | SPEAK only (core.py:397) | `text = response.content` + optional `[IMAGE CONTEXT]` | "How CIRIS-aligned does this reply sound?" — 40+ calibration examples for propaganda, false consensus, adversarial framing, harmful content. | `CoherenceResult{coherence:float}` — **single scalar, schema forbids extras** | `coherence ≥ coherence_threshold` |
| **IRIS-O** v1.2 | ALL actions | `action_desc = f"{selected_action} {action_parameters}"` + image context | Entropy-reduction-ratio scoring with specific calibration for propaganda (5.0–10.0), defensive-mimicry refusals (5.0–9.0), false consensus (4.0+). Rich pattern library. | `OptimizationVetoResult{decision:enum, justification:str, entropy_reduction_ratio:float, affected_values:list[str]}` | `decision ∉ {abort,defer} AND ratio < cap` |
| **IRIS-H** v1.1 | ALL actions | `action_desc` + image context | **Large overlap with O** — same propaganda-pattern library rephrased for epistemic-certainty framing. "Evaluate the RESPONSE not the topic." | `EpistemicHumilityResult{epistemic_certainty:float, identified_uncertainties:list[str], reflective_justification:str, recommended_action:enum}` | `recommended_action == "proceed"` |

### Issues the prompts make clear (not obvious from telemetry alone)

1. **C is schema-starved, not model-starved.** `CoherenceResult` has exactly one field with `extra="forbid"`. The LLM is mechanically prevented from emitting justification, flagged patterns, or sub-scores. Production data showing "6 distinct values, 16-char boilerplate reasons" is a direct consequence — there's nowhere in the schema for richer output to go.
2. **H and O are doing ~60% overlapping work.** Both prompts contain long parallel lists of contested-geopolitical-claim patterns, historical-denial patterns, false-consensus patterns, institutional-narrative markers. H reframes them as "certainty triggers"; O reframes them as "entropy-reduction triggers." Two LLM calls per thought pay for essentially the same pattern match from different angles.
3. **E's v2.0 rewrite is the only shard whose output natively produces the substrate for higher-order signals** — the 3 alternatives are the enumeration material future II could operate on. No other shard generates alternative samples.

### Parallel-dispatch constraint

All 4 shards fire concurrently today. A synthesizing shard cannot see the others' outputs mid-flight. Any cross-shard logic must therefore be a **post-parallel-wave deterministic function** that reads all 4 scalars once the wave completes.

## Proposed state — 3 LLM shards + 1 deterministic gate

| Shard | Scope change | Input change | Prompt change | Output schema change | Gate rule change |
|-------|--------------|--------------|---------------|----------------------|------------------|
| **IRIS-E** | **SPEAK + TOOL** | SPEAK: unchanged. TOOL: `text = render_tool_call(action.selected_action, action.action_parameters)` — e.g. `"TOOL: home_assistant.turn_on(entity_id='light.kitchen')"` | Add a TOOL branch to system prompt. Reframe step 1 as "enumerate 3 alternative action+arg combinations a thoughtful agent could have chosen for the same thought" and recalibrate bands: narrow-task alt-tools converge (look up Chicago weather → `weather.get` is the answer), open-task diverge (handle conflict → SPEAK vs RECALL vs DEFER all plausible). | `alternative_meanings[]` → renamed `alternatives[]` (still exactly 3). Keep rest of schema. | Unchanged. |
| **IRIS-C** | **SPEAK + TOOL** | SPEAK: unchanged content but also pass `thought.content + action.rationale` so C can check alignment between response and stated intent. TOOL: render tool call + pass rationale + thought context. | Rewrite to cover *three* coherence axes: (a) CIRIS-principles alignment (current focus), (b) response-vs-rationale alignment — did the agent do what it said it would?, (c) response-vs-thought alignment — does this address what was asked? | **Enriched schema** — current single-scalar is the root cause of boilerplate: `CoherenceResult{coherence:float, alignment_score:float, context_fit_score:float, justification:str, flagged_patterns:list[str]}`. Removes `extra="forbid"` blockage on richness. | `coherence ≥ coherence_threshold AND context_fit_score ≥ context_threshold` (two gates replace one) |
| **IRIS-O** | Unchanged | Unchanged | **Trim overlap with H** — delete the false-certainty and institutional-narrative sections since they duplicate O's own entropy-reduction framing. Keep defensive-mimicry, keep propaganda calibration. | Unchanged (already rich). | Unchanged. |
| ~~**IRIS-H**~~ | **Removed as LLM call** | — | — | — | — |
| **Heuristic gate** (new, deterministic) | ALL actions | Reads completed `EntropyResult`, `CoherenceResult`, `OptimizationVetoResult` after parallel wave | Pure Python. Computes disagree/mushy/borderline flags over normalized scalars; returns verdict. Inspectable, deterministic, zero-latency. | `HeuristicGateResult{verdict:enum[proceed,ponder,defer], trigger_flags:list[str], disagree_spread:float, weakest_shard:str, rationale:str}` | `verdict == "proceed"` |

### Heuristic gate — reference implementation

Normalized `safer = higher` scalars:
- `e = 1 - entropy_score`
- `c = coherence_score` (primary coherence)
- `o = 1 - (entropy_reduction_ratio / cap)` (clipped to [0, 1])

```python
disagree = max(e, c, o) - min(e, c, o) > 0.30   # shards split
mushy    = all(0.40 < x < 0.70 for x in (e, c, o))  # all in the fog
borderline = any(abs(x - thr) < 0.05 for x, thr in zip((e, c, o), thresholds))

if o_decision == "abort" or e > entropy_hard_fail or c < coherence_hard_fail:
    verdict = "defer"
elif disagree or mushy or borderline:
    verdict = "ponder"   # v3 terminal — v4 will escalate to 3× parallel IRIS-E
else:
    verdict = "proceed"
```

`disagree` is the most discriminating flag: if three shards say clean-pass and one says fail-hard, single-sample LLM noise may be flipping the verdict — escalation (v4) or PONDER (v3) is the correct response. `mushy` catches the "everything's a weak maybe" band. `borderline` is the safety net for scores hugging thresholds.

## What moves where, concretely

- The propaganda/false-certainty pattern library currently duplicated between O and H collapses into O alone.
- H's value-add was "was the response epistemically humble enough?" — that becomes a scalar threshold on O's `entropy_reduction_ratio` + C's `alignment_score`, which the heuristic gate computes. No LLM needed to ask "is the certainty okay?" when you already have entropy and alignment scalars.
- H's `identified_uncertainties` list — the one field with unique value — moves to C's new `flagged_patterns` list.
- H's `reflective_justification` (630-char prose) was always post-hoc rationalization of a decision already implicit in the scalars. The heuristic gate's `rationale` field derives the same justification deterministically (e.g. "C disagrees with O: C says aligned, O says ratio 6.2 → entropy suggests propaganda the alignment check missed").

## What each shard gains from TOOL extension

- **E on TOOL** catches: tool-choice rigidity (agent always picks `home_assistant.turn_on` when `scene.activate` would also fit), argument-space collapse (same `entity_id` pattern across thoughts that should differentiate), single-attractor selection when 3 tools are all reasonable.
- **C on TOOL** catches: rationale-action mismatch ("I'll look up the documentation" then calls `file.delete`), context drift (tool args referencing state the thought never mentioned), tool-chain incoherence (RECALL immediately followed by FORGET of unrelated node).

## LLM-call budget per thought

| Action type | Current | Proposed | Delta |
|-------------|---------|----------|-------|
| SPEAK | 4 (E, C, O, H) | 3 (E, C, O) | −25% |
| TOOL | 2 (O, H) | 3 (E, C, O) | +50% for coverage |
| Other | 2 (O, H) | 1 (O) | −50% |

Net effect depends on action mix. For a thought-stream dominated by SPEAK and "other" handler actions (RECALL, FORGET, DEFER, etc.), this is a net reduction. TOOL gains 1 call but gains full conscience coverage where today it has none on E/C.

## Load-bearing schema migration

**`CoherenceResult` gaining `justification` and `flagged_patterns` fields is the single most important change.** It's what unlocks C from being a single-scalar placeholder into a genuine shard. Everything else is prompt work or architectural plumbing; that schema change is what enables the rest.

Migration path:
1. Add optional fields (`justification: str = ""`, `flagged_patterns: list[str] = []`, `alignment_score: float | None = None`, `context_fit_score: float | None = None`) with `extra="ignore"` so legacy provider outputs still parse.
2. Update `coherence_conscience.yml` prompt to request the new fields.
3. Observe for a release window — confirm providers emit the new fields reliably.
4. Promote `justification` and one of the alignment scores to `required` once telemetry confirms >95% emission rate.
5. Wire the heuristic gate to read the new fields; deprecate H's LLM call behind a feature flag.
6. Remove H's LLM call and `EpistemicHumilityResult` schema after one full release cycle with the flag off.

## Migration plan

**Stage 1 — schema expansion (backwards-compatible)**
- Extend `CoherenceResult` with optional fields.
- Add TOOL branch to `entropy_conscience.yml` and `coherence_conscience.yml`.
- Lift SPEAK-only short-circuits in `core.py:273` and `core.py:397` to `{SPEAK, TOOL}`.
- Keep H running. Ship.

**Stage 2 — heuristic gate shadow mode**
- Implement `HeuristicGateResult` and the deterministic function.
- Run it in shadow alongside H; log verdicts side-by-side.
- Measure agreement rate. Target: heuristic agrees with H on ≥95% of thoughts within the first 1000 samples.

**Stage 3 — flip the gate**
- Feature flag: `conscience.use_heuristic_gate = true`.
- Heuristic becomes the gate; H's LLM call still runs but its verdict is logged only.
- Hold this state for one release cycle.

**Stage 4 — remove H**
- Delete `EpistemicHumilityConscience`, `EpistemicHumilityResult`, `epistemic_humility_conscience.yml`.
- Trim H-overlap sections from `optimization_veto_conscience.yml`.
- Bump schema version.

## Open questions

1. **Does telemetry store raw E/C/O outputs per thought, or only `ConscienceStatus`?** The heuristic gate needs the 4 scalars post-parallel-wave. (Stated as resolved — "we store everything" — verify at implementation time.)
2. **TOOL-specific threshold calibration** — entropy distributions over tool-call alternatives will likely differ from speech-entropy distributions. Do we calibrate separately or trust the same thresholds until data suggests otherwise?
3. **Do we preserve the scalar `coherence` field in the expanded schema for dashboard continuity, or drop it in favor of the richer three-axis output?** Recommended: keep `coherence` as a derived aggregate (e.g., `min(alignment_score, context_fit_score)`) for backwards compat with any downstream consumers.

## Deferred to v4

- Recursive II (Interaction Information) monitoring over pooled alternatives from 3× parallel IRIS-E dispatch when the heuristic gate flags ambiguity.
- This requires v3 to be in place first: we need the heuristic gate as the trigger mechanism, and we need the enriched C schema to carry the II scalar.
