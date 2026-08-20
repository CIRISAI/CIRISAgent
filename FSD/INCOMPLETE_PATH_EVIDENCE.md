# Incomplete-path evidence: what a trace is anchored on, and why

**Status:** design position, with one open verification.
**Raised by:** NULLWORKS RC3 independent assurance retest, finding F5 (HOLD).
**Applies to:** trace persistence, `orphan_sweep`, audit hash chain.

## The finding

> "Proof that a completed record is authentic is different from proof that every
> consequential attempt was preserved. An interrupted path should leave a durable,
> bounded receipt before transient state is discarded."

Their `TRACE-ORPHAN-01` campaign ran against the real Lens/Persist substrate and
observed that an aged `THOUGHT_START` carrying no `ACTION_RESULT` is purged by
`orphan_sweep`. Notably, **the project's own test asserts this and passes** — so
the auditors were reading a green test as evidence of the condition.

They were reading it correctly. That test asserts intended behaviour.

## The position: traces are anchored on ACTION_RESULT

A trace is the record of *an action the agent took*. It is anchored on
`ACTION_RESULT` deliberately: **no action means it never happened.** A thought
that began and did not reach a terminal action produced no external effect,
changed nothing outside the process, and is — as an account of agent conduct —
about nothing.

In-flight traces with no terminal action are therefore ephemeral **by design**,
and `orphan_sweep` collecting them is the design working, not a leak. Retaining
every abandoned partial reasoning path would grow unboundedly, and would fill the
evidence surface with records of things that did not occur — degrading the signal
of the records that describe things that did.

This is a position, not an accident. It was previously unwritten, which is why an
independent reviewer could not distinguish it from an oversight. That gap was the
real defect this document fixes.

## What the position does NOT claim

It does not claim nothing is lost. Specifically:

- An action that was **attempted and interrupted mid-flight** — dispatched
  outward, then killed before its result was recorded — is a case where an
  external effect may exist with no trace describing it. That is the sharp edge
  of this design, and it is real.
- The claim "no action means it never happened" is exactly true for a thought
  that never dispatched, and only *approximately* true for one killed between
  dispatch and result.

## The second evidence plane, and the open verification

Traces are not the only durable record. `base_handler._audit_log` writes an audit
entry through the audit service, Merkle-chained and append-only, on a path
independent of trace capture. That is the natural place for an interrupted
attempt to survive, and it is the "equivalent durable evidence plane" the
auditors explicitly offered as an alternative to emitting a new receipt.

**This has not been proven end to end.** Whether an audit entry exists for an
action dispatched-but-not-completed, across every adapter, is an open question —
and the honest answer today is that we have not tested it. Their recommendation
stands unmet in that specific sense:

> "Emit a privacy-bounded INCOMPLETE/ABORTED receipt before orphan cleanup, or
> demonstrate an equivalent durable evidence plane and test it end to end."

## Next step

Test the audit plane end to end for the interrupted-dispatch case. Two outcomes:

1. **The audit entry survives** — then F5 is answered by the second plane, this
   document is updated to cite the test, and no new receipt is needed.
2. **It does not** — then emit a bounded `INCOMPLETE` audit entry at dispatch
   time, before the external call, so the attempt is durable even if the result
   never is.

Either way the resolution is evidence, not prose. Until that test exists, this
document records the design and its known sharp edge rather than claiming the
finding is closed.
