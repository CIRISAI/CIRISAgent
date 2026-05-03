# Conscience v3 — 3 LLM Shards + Deterministic Gate

**Status:** Stage 1 + Phase-2 DEFER landed in `c6411c7d9` (2026-05-03). Stages 2-4 remain.
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

**Stage 1 — schema expansion (backwards-compatible)** — ✅ landed `c6411c7d9` 2026-05-03
- ⏳ Extend `CoherenceResult` with optional fields. (deferred — schema-enrichment carries to Stage 2 alongside heuristic-gate work; not load-bearing for the verb-scope expansion that landed)
- ✅ Add TOOL branch to `entropy_conscience.yml` and `coherence_conscience.yml`. Done as verb-agnostic "ACTION TO ASSESS" wording + per-verb extraction note covering SPEAK/TOOL/DEFER.
- ✅ Lift SPEAK-only short-circuits in `core.py` to `{SPEAK, TOOL}` (Entropy) and `{SPEAK, TOOL, DEFER}` (Coherence — see Phase-2 below). New `_BaseConscience._render_action_text` helper renders verb-specific content (`SPEAK→content`, `TOOL→"TOOL CALL: name(args)"`, `DEFER→"DEFER REASON: reason"`).
- ✅ Localized prompt fanout to all 28 locales — CONSCIENCE-V3 SCOPE comment header carries canonical SPEAK/TOOL/DEFER tokens (file-text-counted by zh-chain canonical_action_verbs_preserved test, excluded from natural-language script-ratio test which only loads YAML strings).
- Keep H running. ✅ Shipped.

**Stage 1 Phase-2 — DEFER → Coherence + EOV + EpistemicHumility** — ✅ landed `c6411c7d9` 2026-05-03 (additive to original FSD scope per 2026-05-03 verb-scope investigation)
- ✅ DEFER removed from outer `_is_exempt_from_conscience_checks` set in `conscience_execution.py` and the mirror set in `main.py`. DEFER now flows through Coherence + EOV + EH (Entropy stays scoped via inner guard — DEFER reasons aren't narrative response content with semantic-alternative space).
- ✅ Coherence inner guard extended to `{SPEAK, TOOL, DEFER}` so the DEFER reason text is judged against CIRIS principles + user message coherence.
- ✅ Test update: `test_process_thought_with_defer` now asserts `original_action.selected_action == DEFER` (DMA output unchanged) AND `final_action.selected_action ∈ {DEFER, PONDER}` — DEFER may now be conscience-overridden to PONDER on borderline framings.
- **Why this addition:** catches defensive-mimicry refusal framing in DEFER reasons that previously bypassed all conscience evaluation. Pure positive coverage — no SPEAK/TOOL behavior changed.

**Stage 1 Phase-3 — `CoherenceResult` schema enrichment** — pending
- Add optional `justification: str = ""`, `flagged_patterns: list[str] = []`, `alignment_score: float | None = None`, `context_fit_score: float | None = None` with `extra="ignore"` so legacy provider outputs still parse.
- Update `coherence_conscience.yml` prompt to request the new fields.
- This is what the load-bearing schema migration section calls out as the "single most important change" — splitting it from Phase-1 lets the verb-scope expansion ship and accumulate validation data ahead of the schema work.

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

## 9. Secondary-model bounce — diversity to break single-model priors

**Status:** Proposal, parallel to `FSD/DMA_BOUNCE.md` §9.2. Both proposals
share the same `LLMBus` multi-provider routing and should land in the
same release window.

### 9.1 Motivation

The v3 heuristic gate's `disagree`/`mushy`/`borderline` flags fire when
the three IRIS shards (E, C, O) split or sit in the fog band. Today, a
PONDER on those flags produces a fresh ASPDMA loop, but the same shards
re-evaluate the new attempt against the same model that just produced
the ambiguous reading. If the ambiguity comes from a *single-model
bias* — a calibration peculiarity, a refusal pattern, a topic-specific
prior — re-asking the same model will reproduce the same ambiguity.

A different model has different priors. When E/C/O run on Model A and
agree ambiguously, asking Model B (or Models B + C in panel-of-N) to
re-evaluate the SAME action generates an independent prior reading.
Cross-model agreement on `proceed` is much stronger evidence than
single-model `proceed`; cross-model disagreement is the cleanest
signal that the action genuinely sits in contested territory.

### 9.2 When secondary-model bounce fires

Triggered by the v3 heuristic gate, NOT on every thought. Specifically:
- `disagree` flag (max-min spread > 0.30): one of the shards is an
  outlier; secondary-model evaluation distinguishes "single-model noise"
  from "real shard-level disagreement on substance."
- `mushy` flag (all in 0.40–0.70): single-sample LLM noise dominates in
  this band; a second model's read pulls one direction or the other.
- `borderline` flag (any score within 0.05 of threshold): the gate
  decision is one re-roll away from flipping; a second model's read
  resolves the coin flip with substance instead of variance.

Crucially, the secondary-model bounce does **NOT fire when E/C/O all
clean-pass or all clean-fail** — those are unambiguous and the cost
isn't worth the latency. It's specifically the gate's escalation path.

### 9.3 Two variants (mirror DMA bounce)

| Variant | Cost | Diversity gain | Operational complexity |
|---------|------|----------------|------------------------|
| **A. Single-secondary swap** — re-run E/C/O on Model B | 3× extra LLM calls only when gate escalates | Moderate; one alternative prior set | Low |
| **B. Panel-of-N** — re-run E/C/O on 3 different models in parallel, vote on the verdict | 9× extra LLM calls only when gate escalates | High; three alternative prior sets | Higher |

**Selection rule under panel-of-N:** majority verdict across the 3
models becomes the conscience output. If majority disagrees with
single-model, the bounce verdict wins (the gate's job was to escalate,
the panel's job is to break the tie). Ties (2-1 with one shard
outlier) are surfaced through the heuristic gate's `rationale` field
with `model_disagree=true` so ASPDMA sees that the conscience itself
is not unanimous.

### 9.4 Schema delta (additive only)

```python
class HeuristicGateResult(BaseModel):
    verdict: Literal["proceed", "ponder", "defer"]
    trigger_flags: list[str]
    disagree_spread: float
    weakest_shard: str
    rationale: str
    secondary_model_verdicts: Optional[list[ModelVerdict]] = None  # NEW

class ModelVerdict(BaseModel):  # NEW
    model_id: str
    e: float
    c: float
    o_ratio: float
    o_decision: str
    verdict: str  # what THIS model's read says the gate should return
```

The `secondary_model_verdicts` list lets Lens dashboards surface "Model
B agreed with Model A" or "Model B contradicted Model A on the 3 cases
where the gate escalated this hour" — that's a high-quality
calibration signal for shard / model selection.

### 9.5 Coordination with DMA-side bounce

DMA bounce operates one layer earlier (the DMA self-rated its own
output low). Conscience secondary-model bounce operates one layer later
(the conscience shards split or sit in the fog). They use the same
multi-provider `LLMBus.call_with_provider` routing. The two
proposals should ship together so:
- One config block names the provider panel.
- One telemetry surface tracks per-provider verdict deltas.
- Provider failures fall through cleanly in both layers (DMA bounce or
  conscience bounce can each independently degrade to single-model
  when a provider is unavailable).

## Deferred to v4

- Recursive II (Interaction Information) monitoring over pooled
  alternatives from 3× parallel IRIS-E dispatch when the heuristic
  gate flags ambiguity.
- v3 is the prerequisite: the heuristic gate is the trigger mechanism,
  and the enriched C schema carries the II scalar.

### 10.1 v4 recursive II — prompt perturbation to force fact-grounding

The naive recursive-II implementation runs N copies of IRIS-E in
parallel against the SAME prompt and measures the interaction
information across the N alternative-meaning lists. That catches
output-distribution noise, but it does NOT catch coordinated
single-model bias — if all N copies use the same prompt, they're all
sampling from the same prior. Same prompt → same prior → high
correlation by construction, even on hedges/propaganda the model
fundamentally can't escape.

**The harder lever: each recursive agent gets a *prompt-perturbed*
variant that demands a *different secondary line of facts* support
the same claim.** Truthful answers can supply each requested
secondary line because the underlying reality has multiple,
mutually-supporting evidence chains. Deceptive/hedging answers
cannot — they rest on ONE rhetorical scaffold, and pushing for a
*different* fact-line either fails ("no evidence") or fabricates a
secondary lie that may contradict the first.

**Why this is harder than single-prompt recursion:** lying in one
dimension is cheap. Lying in N orthogonal dimensions consistently is
expensive — exponentially so as N grows. Truth has many independent
witnesses; falsehood usually has one rehearsed story.

**Concrete prompt-perturbation axes for IRIS-E recursion:**

| Axis | Recursive agent prompt asks the model to ground the answer in… | Failure signal |
|------|----------------------------------------------------------------|----------------|
| **Primary-source axis** | named primary sources (documents, archives, recordings) that would corroborate the answer | model can name none, or names sources that don't exist |
| **Dated-event axis** | specific dates / event sequences that would have to be true if the answer is right | model gives no dates, or dates that are internally inconsistent |
| **Named-actor axis** | specific named people, organizations, or institutions involved | model gestures at "experts" / "officials" without naming any |
| **Falsifiability axis** | what fact would, if true, refute the answer | model produces a non-falsifier or refuses |
| **Dependency axis** | what other facts would have to be true for this answer to hold | model can't identify dependencies, or dependencies don't form a coherent network |
| **Counter-narrative axis** | what alternative interpretations exist and on what grounds they're rejected | model dismisses alternatives without engagement |

For each thought sent through recursive II, the v4 dispatcher picks K
of the 6 axes (e.g., K=3) and runs IRIS-E with a perturbed system
prompt that adds the corresponding grounding demand. Then it computes
II across the K alternative-meaning lists.

### 10.2 What truthful vs deceptive answers look like across axes

**Truthful answer to a documented event:**
- Primary-source axis: names a contemporaneous source.
- Dated-event axis: gives consistent dates, possibly acknowledging
  where sources differ on minor details.
- Named-actor axis: names actors with their roles.
- Falsifiability axis: identifies what evidence would refute (e.g.,
  "if no primary witnesses had been present, this would be more
  contested").
- Dependency axis: cites other established facts the answer rests on.
- Counter-narrative axis: engages with the alternative and explains
  why the documented record favors one over the other.

The K alternative-meaning lists across axes will share the same core
specifics (names, dates, places) and only differ in which
fact-supplement they emphasize. **High II.**

**Deceptive / hedging answer (the failure mode v3 already partially
catches):**
- Primary-source axis: gestures at "official sources" with no names.
- Dated-event axis: gives a year or decade, no specifics.
- Named-actor axis: "the government", "experts", "scholars" — no names.
- Falsifiability axis: refuses ("complex topic, multiple
  interpretations") or invents a non-falsifier ("more research
  needed").
- Dependency axis: produces unrelated background context (the
  topic-substitution pattern from opt-veto v1.5) instead of
  load-bearing dependencies.
- Counter-narrative axis: "many perspectives exist" without
  engagement.

The K alternative-meaning lists across axes have NO shared core
specifics — each list is generated from the same scaffold but with
different padding. **Low II.**

### 10.3 II computation

Standard interaction information across the K alternative-meaning
lists, treating named-entity overlap as the joint variable:

```
II(L1, L2, ..., LK) = sum over named-entity sets of
    P(entity in all K lists) * log(...)
```

Truthful answers concentrate II in the named-entity set; deceptive
answers diffuse it across orthogonal padding. The threshold for
"flag as potentially deceptive" comes from telemetry calibration once
v3 is in place.

### 10.4 Why the perturbation is the load-bearing change

Without prompt perturbation, recursive II measures only sampling
variance on a fixed prior — it catches "the model is uncertain but
honest" reasonably well, but cannot distinguish "the model is
uncertain because it's lying / has been trained to evade." The
perturbation forces the model into territory the prior doesn't
cover; if the answer can be grounded across all K axes consistently,
it's fact-supported; if it falls apart on one or more axes, the
prior was carrying the original answer, not reality.

The cost is K× the IRIS-E call (parallel, so latency is max-of-K).
The signal is qualitatively different from same-prompt recursion: II
measured across diverse-prompt outputs is a near-perfect detector
for hedges and propaganda that defeated v3 by sounding balanced,
because the perturbation specifically targets the absence of
multi-axial fact grounding.

### 10.5 Coordination with secondary-model bounce (§9)

§9 (secondary-model bounce) and §10 (recursive II with prompt
perturbation) compose: the v4 recursive II can run its K perturbed
agents against DIFFERENT MODELS AND different prompts simultaneously.
At that point the conscience layer is sampling the joint distribution
of `{model × prior × axis}` for the same action, and II across all
three dimensions is the strongest single signal we can produce
without external fact-checking.

The combinatorial budget caps this: in panel-of-3 + K=3 axes, that's
9 LLM calls per IRIS-E recursion, fired only when the v3 heuristic
gate escalates. With ~15–25% gate-escalation rate (estimated from
v3 shadow-mode telemetry to be confirmed), per-1000-thought cost is
~225 thoughts × 9 = 2025 extra calls — bounded and concentrated on
hard cases, mirroring the DMA-bounce cost framing.

## 11. Polyglot torque framing — universal across all DMAs and consciences

**Status:** Direction. Opt-veto v2.0 (shipped 2.7.1) is the existence
proof. The framing is universal — every DMA and conscience evaluates
some torque between training-weight pull and CIRIS-aligned ground
truth. Each layer needs polyglot torque framing.

### 11.0 The universal torque formula

Every DMA and conscience in the agent's pipeline evaluates one
fundamental signal:

> **Your weights pull toward X. Ethics and basic objective truth pull
> you elsewhere. CIRIS helps you navigate.**

This is not an opt-veto-specific insight. It is the load-bearing
formula for every layer that uses an LLM judge. What varies per layer
is what "X" is and what "elsewhere" looks like:

| Layer | Weight pull (attractor) | Ethics + objective-truth pull |
|---|---|---|
| **CSDMA** | "all stated outcomes are equally plausible" | physical / social / temporal reality says one of them isn't |
| **DSDMA** | "all responses fit the agent's role" | the actual role + context says one of them doesn't |
| **PDMA** | "comfortable ethical positions" / institutional-aligned framings | CIRIS principles + stakeholder analysis says elsewhere |
| **IDMA** | "sources are diverse" | actual source independence says elsewhere |
| **ASPDMA** | the action the prior most strongly suggests | the integrated reasoning across DMAs says elsewhere |
| **IRIS-E** | "the response anchored on one of many possible meanings" | the alternative-meaning enumeration shows it didn't |
| **IRIS-C** | "this reads as CIRIS-aligned" | the actual principle-by-principle check says elsewhere |
| **IRIS-O** *(already shipped)* | the institutional-narrative attractor for this date/place/actor | the documented record says elsewhere |
| **IRIS-H** | overconfidence in own reasoning | identifiable uncertainty says elsewhere |

The polyglot character of each layer's prompt is what disrupts
single-language attractor capture in the LLM judge. The torque
framing is what makes the polyglot prompt legible as imperative
rather than decorative.

### 11.1 The opt-veto v2.0 breakthrough

### 11.1 The opt-veto v2.0 breakthrough

In 2.7.1 the optimization veto conscience switched from per-locale
monolingual prompts (29 files) to a single universal POLYGLOT prompt
body (one body, only the closing output-language directive varies per
locale). The scalar was rebound from "epistemic diversity collapse" to
**TORQUE** — the angular distance between (A) what an ethically-aligned
model would emit for a given thought and (B) where the response actually
sits after training-attractors (institutional framings of any flavor)
exert their pull. Low torque = ethics produced this; high torque = the
attractor produced this wearing ethics' clothes.

The two changes co-landed:

| Pre-v2.0 | v2.0 polyglot torque |
|---|---|
| Per-locale monolingual prompts (zh prompt is all zh, en is all en, etc.) | One polyglot body interleaving 12 languages line-by-line |
| Scalar measures "epistemic diversity collapse" | Scalar measures angular distance between ethics-attractor and training-attractor |
| 0/10 catch on a live zh empty-frame bug case (response invokes a politically-loaded date+place but pivots entirely to a neutral institutional framing without naming any of the documented record) | **10/10 catch with mean ratio 8.90** on the same case |
| Single-language attractor (e.g., the CCP-narrative attractor in zh training) reads its own evaluation prompt | Cross-lingual reading disrupts single-language attractor reach into the LLM judge |

### 11.2 Why the polyglot character matters

Each language's institutional-narrative attractors live in that
language's training subspace. A monolingual zh prompt is read by the
zh-trained portion of the model — which has the same attractors that
produced the response under evaluation. The conscience cannot evaluate
attractor-capture from inside the same attractor sphere it's auditing.
A polyglot prompt forces the model to engage cross-linguistically;
no single-language attractor has uninterrupted access to the
conscience's reasoning. The polyglot character itself is the
integrity check.

This is structurally different from "translate the prompt to English
and let GPT-4 evaluate." The polyglot prompt deliberately interleaves
many traditions, none dominant — Arabic + Amharic + Persian + Korean +
Russian + Hindi + Japanese + Chinese + English + Spanish + French +
German in alternating lines. The model must integrate across
linguistic worlds to read the rule, which is exactly the integrity
move ethics requires of the agent.

### 11.3 Candidate layers for polyglot extension

| Layer | Why polyglot might help | Why it might not |
|---|---|---|
| **IRIS-E (entropy)** | Alternative-meanings enumeration could draw on cross-language framings, surfacing alternatives a monolingual prior would miss | E already enumerates 3 alternatives; polyglot might dilute focus rather than diversify |
| **IRIS-C (coherence)** | Coherence with CIRIS principles is itself language-agnostic; reading in polyglot could break English-corporate-attractor read of "is this aligned" | Same risk as opt-veto: monolingual coherence prompt may inherit institutional alignment frames from training |
| **CSDMA (common sense)** | Common-sense plausibility about physical/social reality crosses cultures; polyglot could surface culture-specific reality-checks | Plausibility judgments are usually local — polyglot may introduce noise where the question is fundamentally local |
| **DSDMA (domain)** | Domain alignment evaluates fit-for-context; polyglot could break hidden domain assumptions baked into a single language | Domain rules are often expressed in the user's language; polyglot adds friction |
| **PDMA (ethical)** | Strongest case after opt-veto: PDMA evaluates alignment with CIRIS ethics, which are universal. Polyglot here could break ethical-attractor capture by any specific tradition | Highest-risk: ethical reasoning quality is the load-bearing signal; if polyglot degrades reasoning, this is where the cost lands |
| **IDMA (independence)** | k_eff estimation may benefit from cross-language source diversity awareness | IDMA is a structural fragility signal, not a content-evaluation; polyglot less applicable |
| **ASPDMA (action selection)** | The action-choice itself — could polyglot framing break attractor-driven action selection? | Highest stakes: ASPDMA is what the agent DOES. Polyglot here is the most ambitious experiment. |

### 11.4 Experimental protocol

For each candidate layer:

1. **Baseline measurement.** Run the bounce harness (or build an
   equivalent for DMAs) on the layer with the current monolingual
   prompts. Record per-locale catch rates on a curated bug corpus.

2. **Polyglot variant.** Draft a polyglot version of the same prompt
   (the opt-veto v2.0 file at
   `ciris_engine/logic/conscience/prompts/optimization_veto_conscience.yml`
   is the reference template). The body should interleave 8+ languages
   line-by-line; only output-language directive varies per locale.
   The scalar / output schema stays identical — what changes is HOW the
   model reads the rule.

3. **A/B run.** Same harness corpus, same model, same temperature.
   Compare catch rate, false-positive rate, and ratio distribution.
   Acceptance bar: catch rate ≥ baseline AND false-positive rate ≤
   baseline + 5pp.

4. **Production trial.** If A/B passes, ship behind a feature flag for
   one release window; monitor live telemetry for regression on the
   layer's downstream signals (e.g., for PDMA-polyglot, watch
   `EthicalDMAResult` field-emission rates).

5. **Decision.** Promote if telemetry confirms; revert if regression.

### 11.5 What the opt-veto experiment learned that generalizes

- **The breakthrough required two co-landed changes**: polyglot body
  AND torque-as-scalar. Either alone was insufficient (we tried
  polyglot alone earlier in the conversation — it made catch rate
  WORSE, 0/10 from 2/10, because the model read the polyglot as
  decoration rather than as imperative). The reframing is what makes
  the polyglot legible as instruction.
- **Cross-language line interleaving matters more than total language
  coverage.** A prompt with one section in zh, one in en, one in es
  is still functionally monolingual at any given paragraph. The
  opt-veto v2.0 interleaves 3-5 languages within each line; that's
  what disrupts attractor capture.
- **Wire-protocol identifiers must stay English.** JSON keys,
  enum values, action verb names, pattern names. Localizing those
  breaks downstream parsers and was never the source of attractor
  capture anyway.
- **The closing language-rules block is the only per-locale
  variance.** Output-language directive ("write justification in zh /
  es / am / etc.") at the end. The polyglot body is byte-identical
  across all 29 files.

### 11.6 Cost framing

Polyglot prompts are not more expensive at inference time — same
token count budget, same single LLM call. The cost is in the
calibration work: each new polyglot prompt requires a curated bug
corpus, baseline + variant runs, and language-coverage review (each
language used must compress something specific the rule needs;
mere token count adds noise). Estimate 1–2 weeks of focused
calibration per layer.

### 11.7 Coordination with §9 (secondary-model bounce)

Polyglot prompts and panel-of-N model bounce attack the same problem
from different angles. Polyglot disrupts intra-model single-language
attractor capture (one model, many languages). Secondary-model bounce
disrupts inter-model bias capture (one language family, many models).
Both can compose — a polyglot prompt run against a panel of models is
sampling the joint distribution of `{prompt-language-mix × model
prior}`, which is the strongest defensive surface against any single
attractor's reach. v4 should explicitly test polyglot × panel-of-N as
the combined defensive configuration.
