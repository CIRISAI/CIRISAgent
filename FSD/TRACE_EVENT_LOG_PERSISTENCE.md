# Functional Specification Document: Trace Event-Log Persistence

Version: 0.1 (initial draft)
Date: 2026-04-30
Status: DRAFT — no implementation yet
Owner: Agent team
Related: FSD/DMA_BOUNCE.md, FSD/CONSCIENCE_V3.md, ciris_adapters/ciris_accord_metrics/

## 1. Purpose

The H3ERE pipeline broadcasts events at every step via the `@streaming_step` decorator
(`ciris_engine/logic/processors/core/step_decorators.py:194`). Each broadcast is
a discrete observation — a thought, a DMA bounce alternative, a conscience attempt,
a verb-specific second pass, a retry. The lens currently **collapses all
broadcasts for a single thought into one row**, persisting only the post-retry
final state. This is data loss against the framework's design intent.

This document specifies an event-log persistence model and a corresponding
generalization of the verb-specific second-pass stage so that the schema does
not multiply per verb.

## 2. Concrete losses today

Live evidence from a 2026-04-30 wakeup thought
(trace `trace-th_std_518a7abb-…-20260430001553`, agent Datum, llm_calls=13):

| Lossage source | What's broadcast | What lens persists |
|----------------|------------------|--------------------|
| **DMA bounces** (`dma_orchestrator.py:337-410`) — CSDMA/DSDMA/IDMA/PDMA each below threshold trigger `BOUNCE_PARALLELISM` alternatives | N alternative results per low-scoring DMA, each with own `score`, `reasoning_summary`, `prompt_used` | Best alternative only, as `dma_results` row |
| **Conscience overrides** (`conscience_execution.py`) — initial ASPDMA fails optveto / humility / entropy / coherence | One `CONSCIENCE_RESULT` event with override=true, override_reason, candidate action, candidate `speak_content` | Overwritten by next CONSCIENCE_RESULT (last-write-wins) |
| **Recursive ASPDMA** (`recursive_processing.py:165-200`) — up to 5 retries with conscience-guidance | Up to 5 `RECURSIVE_ASPDMA` events, each with own `selected_action`, `speak_content`, `reasoning_summary` | Final retry only |
| **Recursive conscience** — re-validation per retry | Up to 5 `RECURSIVE_CONSCIENCE` events | Final result only |
| **Verb-specific second pass** (TSASPDMA today; see §4 for generalization) | Per-verb second-pass result | Stored as a separate per-verb event type per verb (asymmetric — DSASPDMA has NO event today) |
| **PERFORM_ASPDMA retry-with-remediation** (`llm_service/service.py`, 2.7.4) | Up to 3 internal LLM retries on parsing failures | Aggregated cost only; failure reasons silent |

The cost columns (`llm_calls`, `tokens_used`, `cost_usd`) survive because they
sum across events. This is why `llm_calls=13` is currently the only fingerprint
of an override-and-retry journey: cost is summed, content is overwritten.

## 3. Design principle

**Every `@streaming_step` broadcast is a discrete observation worth keeping.**

The decorator was shaped specifically so each call broadcasts an event with its
own timestamp and payload — a contract encoded in the framework. Last-write-wins
persistence violates this contract.

Persistence design follows the contract: one DB row per broadcast, with a
thought-summary view derived on top. Not the other way around.

## 4. Generalize verb-specific second pass

**Currently: per-verb step points and per-verb reasoning events.**

```
StepPoint:           PERFORM_ASPDMA, RECURSIVE_ASPDMA
ReasoningEvent:      ASPDMA_RESULT, TSASPDMA_RESULT  (← only TOOL has its own event)
Dispatch (main.py):  await self._maybe_run_tsaspdma(...)
                     await self._maybe_run_dsaspdma(...)  (← no DSASPDMA_RESULT event)
```

This is already asymmetric. Adding one second-pass per verb means N more step
points, N more `_maybe_run_xsaspdma` methods, N more reasoning events, N more
event-builder branches in `accord_metrics/services.py`. Untenable for the
direction the codebase is heading (more verbs gain second passes).

**Proposed: one generic stage, verb as a payload discriminator.**

```python
# StepPoint additions (replaces the implicit per-verb fanout)
VERB_SECOND_PASS = "verb_second_pass"        # 4.5) Verb-specific second pass (optional)

# ReasoningEvent additions (replaces TSASPDMA_RESULT, future DSASPDMA_RESULT, etc.)
VERB_SECOND_PASS_RESULT = "verb_second_pass_result"
```

Single dispatch site:

```python
# main.py replaces _maybe_run_tsaspdma + _maybe_run_dsaspdma + future verbs
action_result = await self._maybe_run_verb_second_pass(thought_item, action_result, thought_context)
```

Each verb registers a handler in a dispatch table:

```python
VERB_SECOND_PASS_REGISTRY: Dict[HandlerActionType, VerbSecondPassEvaluator] = {
    HandlerActionType.TOOL: TSASPDMAEvaluator,
    HandlerActionType.DEFER: DSASPDMAEvaluator,
    # Future verbs append here without schema changes
}
```

Event payload carries `verb`, `original_action`, `final_action`, `verb_specific_data`
(jsonb — typed per verb at the model layer, opaque at the lens layer).

**Migration**:
- `TSASPDMA_RESULT` → `VERB_SECOND_PASS_RESULT` with `verb="tool"` + tool-specific
  fields under `verb_specific_data`
- `_maybe_run_dsaspdma` gains the same broadcast wiring it currently lacks (this
  is the existing asymmetry, fixed as a side effect)
- The four verb-specific fields the v2.7.0 schema carries explicitly for tool
  (`original_tool_name`, `final_tool_name`, `gotchas_acknowledged`,
  `tool_description`) move under `verb_specific_data`

**Why this matters for §5 below**: the trace_events table doesn't have to add a
new `step_point` enum value or a new `event_type` for every new verb. The verb
discriminator lives in the payload, not the schema.

## 5. Persistence model

### 5.1 Storage shape

Replace the current per-thought row writer with an event-log table:

```sql
CREATE TABLE trace_events (
  event_id        BIGSERIAL PRIMARY KEY,
  trace_id        TEXT NOT NULL,
  thought_id      TEXT NOT NULL,
  task_id         TEXT NOT NULL,
  step_point      TEXT NOT NULL,    -- enum: gather_context | perform_dmas | perform_aspdma |
                                    -- verb_second_pass | conscience_execution | recursive_aspdma |
                                    -- recursive_conscience | finalize_action | perform_action |
                                    -- action_complete | round_complete | ...
  event_type      TEXT NOT NULL,    -- ReasoningEvent.value
  attempt_index   INT NOT NULL,     -- monotonic per (thought_id, step_point); 0 for non-repeating steps
  ts              TIMESTAMPTZ NOT NULL,
  agent_id        TEXT NOT NULL,
  cognitive_state TEXT,
  payload         JSONB NOT NULL,   -- full event_data dict the adapter ships
  cost_llm_calls  INT,              -- denormalized from payload for fast aggregation
  cost_tokens     INT,
  cost_usd        NUMERIC(10,6),
  signature       TEXT,             -- Ed25519 signature of (trace_id, thought_id, step_point, attempt_index, payload_hash)
  signing_key_id  TEXT,
  schema_version  TEXT NOT NULL     -- "v2.8.0"
);

CREATE INDEX trace_events_lookup ON trace_events (trace_id, thought_id, step_point, attempt_index);
CREATE INDEX trace_events_journey ON trace_events (thought_id, ts);
```

**`attempt_index` semantics**:
- For step points that broadcast at most once per thought (`gather_context`,
  `finalize_action`, `perform_action`, `action_complete`, `round_complete`):
  always 0.
- For step points that may broadcast N times (`perform_dmas` bounce
  alternatives, `perform_aspdma` internal retries, `verb_second_pass` correction
  re-runs, `conscience_execution`, `recursive_aspdma`, `recursive_conscience`):
  monotonic from 0 in broadcast order.
- Lens write logic: `attempt_index = (max attempt_index for this (thought_id,
  step_point) so far) + 1`, atomic per-thought. No upsert; pure append.

### 5.2 Derived summary view

Existing tools that consume one-row-per-thought continue to work via:

```sql
CREATE MATERIALIZED VIEW trace_thought_summary AS
SELECT
  trace_id,
  thought_id,
  task_id,
  agent_id,
  -- final action: last finalize_action event payload
  (SELECT payload->>'final_action' FROM trace_events e2
    WHERE e2.thought_id = e.thought_id AND e2.step_point = 'finalize_action'
    ORDER BY ts DESC LIMIT 1) AS final_action,
  -- aggregate cost
  SUM(cost_llm_calls) AS llm_calls,
  SUM(cost_tokens) AS tokens,
  SUM(cost_usd) AS cost_usd,
  -- override fingerprint: count of conscience_execution + recursive_conscience events
  COUNT(*) FILTER (WHERE step_point IN ('conscience_execution', 'recursive_conscience')) AS conscience_attempts,
  COUNT(*) FILTER (WHERE step_point IN ('conscience_execution', 'recursive_conscience')
                   AND payload->>'action_was_overridden' = 'true') AS conscience_overrides,
  COUNT(*) FILTER (WHERE step_point = 'perform_dmas' AND attempt_index > 0) AS dma_bounces,
  MIN(ts) AS started_at,
  MAX(ts) AS ended_at
FROM trace_events e
GROUP BY trace_id, thought_id, task_id, agent_id;
```

This is the moral equivalent of the current per-thought row, but reconstructed
from the event log on demand. Tools that need the journey (DMA bounce
analysis, conscience-override studies, retry-distribution histograms) query
`trace_events` directly.

## 6. Adapter behavior — minimal change

`ciris_adapters/ciris_accord_metrics/services.py:1712-1767` already builds one
flat dict per broadcast event (CONSCIENCE_RESULT, ASPDMA_RESULT, etc.). The
existing `_send_events_batch` (line 886) ships them as a list. **No agent or
adapter logic changes for the existing event types.**

Required changes are localized:

1. **Add `attempt_index` to every event_data dict** at construction time. Already
   tracked implicitly by broadcast order; needs to be made explicit so the lens
   doesn't have to reconstruct it.
2. **Replace `TSASPDMA_RESULT` event with generic `VERB_SECOND_PASS_RESULT`**
   carrying `verb`, `original_action`, `final_action`, and verb-specific fields
   under `verb_specific_data`. Wire `DSASPDMAEvaluator` through the same path
   (closes the existing asymmetry where DEFER second-pass is silent).
3. **Schema bump** to `trace_format_v2_8_0.json` — recast as a per-event schema
   rather than per-thought. Old `ConscienceResultData` becomes the payload
   shape for `step_point ∈ {conscience_execution, recursive_conscience}` events.

## 7. Lens-side migration

1. **DDL**: create `trace_events` per §5.1. Initially populated by dual-writes
   from the existing event ingestion path.
2. **Switch ingestion** to insert one row per event into `trace_events` instead
   of upserting into the per-thought table.
3. **Build `trace_thought_summary` view** per §5.2. Existing dashboards keep
   working pointed at the view.
4. **Backfill** is not feasible — per-attempt data was never persisted. Pre-cutover
   data stays in the old shape; post-cutover data is event-log shaped. Tooling
   that needs uniform history queries against the union (old per-thought rows
   become single-event "summary" rows in the union, with `attempt_index=0` and
   `step_point=action_complete`).
5. **Cutover gate**: dual-write window of ~7 days, then drop the old per-thought
   ingestion path.

## 8. Schema versioning

`trace_format_v2_8_0.json` is a clean break from v2_7_0:
- v2_7_0 was per-thought-shaped (one ConscienceResultData per row)
- v2_8_0 is per-event-shaped (each event a self-contained payload, with the
  per-thought view derived)

Old payloads continue to validate against v2_7_0 indefinitely; the lens applies
v2_7_0 → v2_8_0 mapping on ingest for any agent that still emits v2_7_0
(needed for the rolling-deploy window where some agents are upgraded and some
are not).

## 9. Compliance / signing

Per-event signing fits naturally — each row carries its own
`signature(trace_id || thought_id || step_point || attempt_index || payload_hash)`
using the same Ed25519 signing protocol already in use
(`ciris_adapters/ciris_accord_metrics/services.py:208`). This actually
strengthens the audit story: every observation is independently verifiable,
not just the final summary. Tampering with one rejected attempt is detectable
without re-signing the whole thought.

## 10. Rollout

| Phase | Owner | Gate |
|-------|-------|------|
| 0 | Agent team — add `attempt_index` to event_data builders, wire DSASPDMA broadcast, generalize TSASPDMA→verb_second_pass | Adapter still ships old events; lens accepts both |
| 1 | Lens team — create `trace_events` table + dual-write ingestion + summary view | Old dashboards keep working; new event-log queries available for spot checks |
| 2 | Lens team — switch primary ingestion to event-log; old per-thought writer becomes derived view materialization | Dashboards now read from view; query parity verified |
| 3 | Agent team — emit `schema_version=v2.8.0` once all in-flight agents are upgraded | Drop v2_7_0 ingestion mapping after rolling-deploy window closes |

No phase requires breaking existing dashboards or replaying history.

## 11. Open questions

1. **Storage cost.** A typical wakeup thought generates ~13 LLM calls and on
   the order of 10-20 broadcast events. With every conscience round preserved,
   peak event count per thought is ~20-30. At current production volumes (TBD —
   need a number from the lens team), this is on the order of 10x current
   row count. Confirm storage budget before phase 1.
2. **PII / sensitive content in rejected attempts.** Conscience overrides
   sometimes reject SPEAK candidates that contain text the agent decided NOT
   to send. Persisting them in the lens means PII / sensitive content lives in
   logs that wouldn't have appeared in the final outbound message. Coordinate
   with privacy / DSAR review before phase 1; may want field-level
   redaction at write time for `payload.candidate_speak_content` based on
   conscience verdict.
3. **Replay semantics.** The single-step debugger
   (`step_decorators.step_point` at line 264, separate from `streaming_step`)
   uses the same step points but is paused-and-resumed rather than
   broadcast-and-continue. Confirm that single-step replay against a
   trace_events row sequence is well-defined — should be, since each row is
   a complete event payload.
4. **Verb-specific second pass for actions other than TOOL/DEFER.** §4 leaves
   the verb registry open for future verbs. A first concrete addition (which
   verb, why, what shape) would clarify whether `verb_specific_data` needs any
   structural constraints (free-form jsonb vs. discriminated union enforced
   at adapter side).

## 12. Non-goals

- Replay-driven re-execution of past thoughts. The trace events are an
  observational record, not a re-execution trace.
- Mid-thought rollback or "rewind to attempt N." The agent has no machinery
  for this and §10's rollout doesn't add any.
- Compression / dedup of repeated identical alternatives. If a DMA bounces
  five times with the same response, all five rows are kept. Compression is
  a future optimization that can run as a periodic batch over `trace_events`
  if storage pressure surfaces.
