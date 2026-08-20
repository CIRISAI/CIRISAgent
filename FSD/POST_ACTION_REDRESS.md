# Post-Action Redress — the governed corrective act, Phase 1

**Finding:** NULLWORKS RC3 **F6** — *"Reconsidering before action is not the same as correcting consequences after an external SPEAK or TOOL action has occurred."*
**Also tracked as:** `compliance/README.md` cross-cutting finding **#5** ("D24 reverse-axis gap — no rollback after SPEAK/TOOL; reconsideration strictly forward-looking via PONDER") · `compliance/D24_reconsideration.md` § Current limitations
**Status:** Phase 1. **Schema and rules only. No workflow ships. Nothing writes a redress record.**
**Companions:** `FSD/TASK_ENVELOPE.md` (the same schema-before-enforcement shape, and the precedent for it) · `FSD/HITL_APPROVAL_SURFACE.md` (the human surface a redress proposal would appear on) · `FSD/THREAT_MODEL_2.9.7.md` (where the release's controls stand)
**Version:** 2.9.28

---

## 0. What this does NOT do

Read this first. The failure mode for a document like this one is that it reads
as a description of a working corrective system. It is not one.

- **It is not undo, and it never becomes undo.** External effects are
  frequently irreversible: a SPEAK that was read has been read, a payment that
  settled has settled, a Discord post someone saw was seen. Nothing in this
  design reverses an external effect. The word "rollback" appears in IEEE Ch4
  via D24 and in the seed vocabulary; **CIRIS cannot deliver it for external
  actions and this document does not claim to.**
- **It does not ship a workflow.** Nothing proposes a redress, nothing records
  one, nothing serves one over the API, and nothing emits a corrective SPEAK.
  There is no route, no service method, no persistence call. The deliverable is
  the object and its rules.
- **It does not gate anything at runtime.** `admit_redress` is fail-closed and
  fully tested, and it sits on **no** execution path, because there is no
  execution path yet. Calling it a control today would be exactly the
  overstatement F7 in the same report is about.
- **It does not add a permission, a signing scheme, or a verifier.** Authority
  rides the WA deferral rail from #944. If that rail is wrong, this is wrong in
  the same way and in the same place — deliberately, so there is one thing to
  fix rather than two.
- **It does not add a table.** There is no agent-side DDL in this repo
  (`persistence/db/core.py:267`); a new table means a CIRISPersist migration
  pair and a wheel cut. Recording rides the existing append-only audit chain
  instead — see §6.
- **It does not make the agent able to redress on its own authority.** A
  correction the agent both proposes and approves is not oversight. Every
  admissible redress requires a Wise Authority.
- **It does not close the D24 federation half.** Emitting
  `reconsideration:{grounds}` and the CEG retraction primitives onto the
  federation wire needs agent actions to *be* federation rows first, which they
  are not. §9 keeps that distinction.

---

## 1. The DRY verdict

**Verdict: mint `RedressRecord`; reuse the vocabulary, the authority rail and
the storage primitive.** Search performed:
`grep -rn "class.*Redress\|class.*Correction\|class TaskEnvelope" --include="*.py"`
plus follow-ups on `withdraws|recants|supersedes|delegates_to` and
`attestation_type`.

| Existing primitive | Where | Verdict |
|---|---|---|
| `DSARCorrectionRequest` / `DSARCorrectionResult` | `schemas/consent/core.py:168,180` | **Not it.** GDPR Art. 16 correction of a *user's stored data* — `field_name`, `current_value`, `new_value`. Its subject is a record about a person; ours is an act the agent performed on the world. It also *mutates in place*, which is the one thing redress must never do. |
| `RevocationIntent` (`recants`/`withdraws`/`supersedes`) | `logic/services/governance/consent/attestation.py:302` | **Vocabulary reused.** `RedressDisposition.ceg_primitive` maps onto exactly these strings. `compliance/D24_reconsideration.md` already commits CIRIS to landing after-the-fact semantics on the CEG four-primitive retraction family; inventing a second set of verbs would guarantee a translation layer later. |
| `StructuralAttestationEnvelope` (`target` + `intent` + append) | same file, :357 | **Shape reused, transport not.** The "append a row naming the prior row's id, newest wins" pattern is lifted wholesale (see `current_community_grant_id` and `_community_grant_edge` in `routes/my_data.py:940` for the existing effective-state resolver it mirrors). The *transport* is rejected for the same reason `FSD/TASK_ENVELOPE.md` §1 rejected it: these are CEG wire artifacts, federation-visible and dimension-versioned. A node-local record of an agent's own mistake is not a federation attestation, and minting one per redress would be a privacy and volume regression with no consumer. |
| `DeferralResponse` + `deferral_resolution_payload` + `verify_deferral_resolution` | `schemas/services/authority_core.py:268,319`; `authentication/service.py:1647` | **Reused as the authority rail — no new crypto.** See §4. |
| `DeferralVerification` (VERIFIED/UNSIGNED/FAILED) | `authority_core.py:253` | **Reused verbatim.** Its three-state reasoning — a migration gap and a forgery must not be reported as each other — is exactly as load-bearing here. |
| `Permission.RESOLVE_DEFERRALS`, `WARole`, `UserRole` | `schemas/api/auth.py:63`; `authority_core.py:14` | **Reused.** No new permission. The authority to redress *is* the authority to resolve a deferral. |
| `AuditEventData` | `schemas/services/graph/audit.py:13` | **Reused as the storage shape.** `redress_audit_event_data()` projects a record onto it; no new storage model. |
| `AuditEntryResult.entry_id` / `entry_hash` / `sequence_number` | `schemas/audit/hash_chain.py:53` | **Reused as the action pointer.** See §5. |
| `TaskEnvelope` (#938) | `schemas/runtime/task_envelope.py:377` | **Not projected, precedent followed.** An envelope is *authorization to act, scoped to a task, alive for seconds*. A redress record is *a durable statement about an act already completed*, outliving its task. The reused thing is the **method**: immutable object, no widening operation, explicit "this phase ships no enforcement", predicates written so the enforcement phase has something to key on. |
| `DeferralNeedCategory` / `DeferralOperationalReason` | `schemas/services/deferral_taxonomy.py:19,32` | **Considered, not used.** They classify *why a human was asked*, on a rights axis, for prompt rendering. `RedressGrounds` classifies *why a completed act was wrong*. Overlap is coincidental; forcing one enum to do both would blur a rights-impact taxonomy into an error taxonomy. Revisit if the redress workflow ever needs rights-impact routing. |

**Rejected outright: a general undo/rollback API.** Named here because it is the
obvious thing to build and it is wrong. Any `rollback(action_id)` surface makes
a promise the substrate cannot keep for the majority of external effects, and
the cases where a carrier *can* delete are precisely the cases where deletion
does the least good — the message was already read.

---

## 2. What redress means here

> **Redress is a new, separately-authorized act that changes what the record
> says stands, without touching the original and without claiming to touch the
> world.**

Three things are being distinguished that ordinary language runs together:

| | Question | Answered by |
|---|---|---|
| **The effect** | Did it happen? Can it be undone? | `EffectReversibility`. Default `IRREVERSIBLE`, which is the truth for most actions. |
| **The endorsement** | Does the agent still stand behind it? | `RedressDisposition` → `ActionStanding.endorsed` |
| **The remedy** | Was anything done for the person affected? | `CompensatingAction` |

Collapsing these is the characteristic failure. "We retracted it" sounds like
all three; it is only the second. So the schema keeps them as independent
fields and makes the strongest one expensive to assert: `CARRIER_REVERSED` is
**unconstructible** without `carrier_evidence_ref`, and it is never implied by
`RETRACTED`. There is a test for exactly that
(`test_retraction_does_not_imply_the_effect_was_undone`).

### The dispositions

| Disposition | Means | CEG primitive | Binding? |
|---|---|---|---|
| `UPHELD` | Reviewed after challenge, affirmed | — | yes |
| `ANNOTATED` | Qualified/contextualised, not disavowed | — | **no** |
| `WITHDRAWN` | Not endorsed going forward; historically stands | `withdraws` | yes |
| `SUPERSEDED` | Replaced; read the named compensating action instead | `supersedes` | yes |
| `RETRACTED` | Disavowed — should not have acted as it did | `recants` | yes |

**`UPHELD` is not decoration.** A ledger that can only record "we were wrong"
is a biased ledger: without it, the absence of a redress record conflates
*nobody ever looked* with *someone looked and it was fine*. Those are different
facts and a reader is entitled to both. This is why `ActionStanding` has a
distinct `UNCHALLENGED` member and why `ActionEffectiveState.reviewed` exists.

**`ANNOTATED` is deliberately non-binding.** Under a naive newest-wins rule,
appending a clarifying note to an already-retracted action would silently
un-retract it. Annotations accumulate; they never govern.

### The grounds

`NEW_EVIDENCE` and `PROCEDURAL_ERROR` are the upstream
`reconsideration:{grounds}` vocabulary (CIRISRegistry FSD-002 §3.6.4 via D24).
`FACTUAL_ERROR`, `HARM_REPORTED`, `POLICY_VIOLATION`, `CONSENT_WITHDRAWN` and
`AUTHORITY_DEFECT` are agent-side additions. The third upstream ground,
`quorum_compromise`, is **deliberately omitted** — it describes a defect in a
federation vote and has no meaning for one agent's own external act. Carrying
it would be vocabulary cargo-culting, and there is a test asserting its
absence.

---

## 3. The state model

A redress record is **immutable** (`frozen=True`) and the ledger is
**append-only**. There is no edit path and no un-redress verb: a redress that
was itself wrong is corrected by *another* redress naming it via `amends`. The
mistaken one stays in the chain, which is what makes the sequence auditable
rather than merely current.

```
        original external action  (audit chain row — never touched)
                   ▲
                   │  target: ActionRef
     ┌─────────────┼─────────────┬─────────────────┐
   rd-1          rd-2          rd-3              rd-4          ← append-only
 RETRACTED     ANNOTATED     (refused)         UPHELD
 (binding)   (non-binding)  (unverified)      (binding)
                   │
                   ▼
      resolve_effective_state()  →  standing = UPHELD (newest binding, admitted)
                                    annotations = (rd-2's statement,)
                                    chain = (rd-1, rd-2, rd-4)
                                    refused = (rd-3,)
```

Resolution rules, in order:

1. Filter to records whose `target.identity_key` matches.
2. **Admit each** via `admit_redress`. A refused record cannot change standing.
3. Sort ascending by `(recorded_at, redress_id)`.
4. The newest *binding* admitted record governs. `ANNOTATED` accumulates.
5. No admitted binding record → `UNCHALLENGED` (with `reviewed` still true if
   any admitted record exists — an annotation means somebody looked).

Admission runs **inside** `resolve_effective_state` rather than being the
caller's responsibility. That is the point: there is no way to call it and
accidentally let an unauthorized correction count.

---

## 4. Authority — riding the #944 rail, not a second one

The only admissible basis is `WA_DEFERRAL_RESOLUTION`: a Wise Authority
approved a deferral proposing the redress, and that resolution's own signature
is the authority evidence.

This buys the property without writing any of the hard parts:

- The signature is hybrid Ed25519 + ML-DSA-65 over
  `deferral_resolution_payload`, produced by `sign_deferral_resolution`
  (`authentication/service.py:1585`).
- It is verified by `verify_deferral_resolution` (`:1647`), which fails closed
  on an empty/legacy signature, a missing `signing_key_id`, an unresolvable
  pubkey, or an owner-binding mismatch.
- The gate runs as the **first statement** of
  `WiseAuthorityService.resolve_deferral` (`wise_authority/service.py:598`,
  refusal at `:613`) — before any state mutation.
- Who may do it is `Permission.RESOLVE_DEFERRALS` / `WARole.AUTHORITY`, already
  enforced at the route by `require_authority`.

So: **no second signing verb, no second canonical payload, no second verifier,
no second permission.** `RedressAuthority` carries no signature bytes of its
own — copying them would create a second place they could drift from. It
carries the pointer (`authorizing_deferral_id`) and the verdict
(`DeferralVerification`, reused verbatim).

`admit_redress` is stricter than `resolve_deferral` in one respect: it refuses
`UNSIGNED`. `resolve_deferral` tolerates unsigned rows because deployed
deferrals predate #944. **No redress row predates this module**, so there is no
migration debt to be lenient about. Starting strict is free exactly once, and
this is the once.

`WA_DIRECT` — a WA ordering a correction with no deferral to hang it on — is
the more common real-world case ("a user complained; an operator corrects the
record"). It is **representable but refused**, with
`RedressRefusalReason.AUTHORITY_BASIS_NOT_IMPLEMENTED`. It is in the enum so
the state model is complete and the refusal has a name, not so it can be used.
Making it work needs a signature over `redress_authorization_payload` and a
verifier for it; §7 has the cost.

---

## 5. Linkage, and the gap underneath it

`ActionRef` prefers the **audit chain**. `AuditEntryResult.entry_id` is the
strongest identifier a completed action has in this system:

- every dispatched action gets one, **including TOOL**, which writes no service
  correlation at all (`tool_handler.py:119` assigns a `_correlation_id` and
  never uses it);
- the chain is append-only — the persist FFI exposes `audit_record_entry`,
  `audit_list_entries`, `audit_verify_chain`, `audit_chain_proof` and **no
  update verb and no per-row delete**;
- `entry_hash` makes the reference content-addressed.

That is the "preserves the original record" primitive, and it already exists.
Redress does not need to protect the original; it needs to *point at* the thing
already protected.

### The gap: the anchor is discarded at dispatch

`action_dispatcher.py:382` **logs `audit_data.entry_id` and discards it.** It
survives on `ActionResponse.audit_data` and in the streaming step data, but it
is never written onto the thought or task row. So for an action already taken,
recovering its `entry_id` needs a chain scan.

Requiring a chain anchor would therefore make redress unrepresentable for every
action the agent has ever performed. `ActionRef` accordingly accepts the weaker
`(task_id, thought_id)` identity — and exposes `is_chain_anchored` so a reader
can *see* which kind of reference they are looking at instead of having to
guess. Both are admissible; they are not equally strong evidence.

**Persisting `entry_id` at dispatch is the single highest-value prerequisite
for Phase 2** and is named as such in §7.

### Linkage is answered from the target's side

The corrective act points at the original (`target`). The original becomes
discoverable *as corrected* because `resolve_effective_state(target, records)`
takes the target and answers for it — there is no need to write a
"was-corrected" flag back onto the original, which would violate §0's first
rule. Discovery is a query, not a mutation.

---

## 6. Current effective state, and where it would live

`resolve_effective_state` is **recomputed, never cached and never stored**, so
it cannot drift from the records that justify it. A reader who disagrees with
`standing` can inspect `chain` and see exactly which record produced it, and
`refused` shows every correction attempt that was *not* allowed to count —
because a correction that failed its authority check is itself a fact worth
seeing, and dropping it silently would hide precisely the events most worth
noticing.

### Recording

`redress_audit_event_data()` projects a record onto `AuditEventData`, the
payload `GraphAuditService.log_event` already takes. Consequences:

- the corrective act inherits the same append-only, hash-chained,
  signed tamper-evidence the original action has;
- **no new table, no CIRISPersist migration pair, no wheel cut**;
- `AuditEventData.metadata` is `Dict[str, Union[str, int, float, bool]]`, so
  every value is a scalar by construction — no `Dict[str, Any]` anywhere.

Optional fields are **omitted rather than written as `"None"`**, so a reader
can tell absent from empty.

One honest caveat, carried over from the audit service itself: the **graph
mirror** of an audit entry (a `cirisgraph_nodes` row) *is* upsertable and
deletable. Only the `cirislens_audit_log` chain is tamper-evident. A redress
recorded through this path is as durable as any other audit event and no more.

**This function writes nothing.** It produces the payload a caller would hand
to the audit service. Wiring that call is Phase 2.

---

## 7. What ships, and what each further phase costs

**Phase 1 (this document) ships:** `ciris_engine/schemas/services/redress.py`
and 48 tests. Rules enforced at the schema level; nothing on any execution
path.

| Phase | Work | Prerequisite | Why not now |
|---|---|---|---|
| **2a** | Persist `AuditEntryResult.entry_id` onto the thought/task row at dispatch | none | Small and independent, but it changes the dispatcher's write path and belongs with the workflow that needs it. Without it, §5's anchor gap stays open. |
| **2b** | Record a redress: a service method that takes a `RedressRecord`, calls `admit_redress`, and on admission calls `audit_service.log_event(redress_audit_event_data(record))` | 2a | This is the smallest thing that makes redress *real*. It was left out because "record" and "read back" are one unit — writing without a query surface produces write-only data. |
| **2c** | Read effective state: index admitted records by target and serve `resolve_effective_state` | 2b | Needs a query over audit metadata by `target_key`. The audit API searches by action type and time, not by arbitrary metadata; this may need a persist-side index. Unscoped until 2b exists. |
| **3** | Propose a redress: agent-side path raising a deferral whose approval authorizes the correction, surfaced on `FSD/HITL_APPROVAL_SURFACE.md`'s pending list | 2c | The human surface exists and is the right home. Needs a third `ApprovalKind`. |
| **4** | Emit the compensating action | 3 | Deliberately last. A corrective SPEAK is an **ordinary** SPEAK — same conscience, same envelope, same audit entry. Redress must grant no privileged execution path, or it becomes a bypass. |
| **5** | `WA_DIRECT` authority | — | Needs `sign_redress_authorization` / `verify_redress_authorization` mirroring `authentication/service.py:1585,1647`. Mechanical, ~80 lines plus tests against the real substrate. Left out because Phase 1's job was to avoid minting a second signing scheme before the first one's shape was settled by use. |
| **6** | Federation emission of `reconsideration:{grounds}` + CEG retraction primitives | agent actions being federation rows | Not agent-side work. See §9. |

---

## 8. Known limits — read this before crediting the control

1. **Nothing is enforced.** Repeated because it is the most likely
   misreading. `admit_redress` has no caller on any execution path.
2. **The WA signature does not commit to the redress body.**
   `deferral_resolution_payload` commits to
   `{deferral_id, approved, reason, wa_id, signed_at}` — the *verdict*, not
   what was described in the deferral's context. A node able to rewrite task
   context could therefore change what a WA appears to have approved. This is
   **not a new weakness**; it is the existing property of every deferral-gated
   decision in the system, and `routes/wa.py:178–241` already documents the
   related residual. The clean fix is an optional `subject_digest` key in
   `deferral_resolution_payload`, omitted when `None` so existing signatures
   keep verifying — a one-field change to a function that is already the single
   shared builder. It is not made here because changing the canonical payload
   of a live signing rail deserves its own change with its own tests, not a
   side effect of a schema phase.
3. **Most redress targets will not be chain-anchored** until §7 Phase 2a lands,
   because the dispatcher discards the `entry_id`. `is_chain_anchored` makes
   this visible per record; it does not make it better.
4. **Ordering is deterministic, not correct.** `recorded_at` is an ISO-8601
   string; multi-occurrence deployments share a database and do not share a
   clock. The `redress_id` tie-break guarantees two readers compute the same
   answer from the same records — it does not guarantee that answer reflects
   real time. A monotonic sequence from the audit chain would; that needs 2a.
5. **The graph mirror is mutable.** §6.
6. **A carrier reversal does not unmake an observation.** Even
   `CARRIER_REVERSED` with a receipt means "the artefact was removed", never
   "nobody saw it".
7. **Redress cannot reach an unreachable person.** If the channel is gone or
   the recipient is unreachable, `CompensatingAction.delivered=False` records
   that honestly and that is all it can do. The record is corrected; the person
   is not informed. This limit is structural and permanent.
8. **`resolve_effective_state` takes records the caller supplies.** With no
   persistence in this phase, completeness of that set is the caller's problem.
   Phase 2c is where it stops being one.

---

## 9. The D24 relationship

`compliance/D24_reconsideration.md` credits CIRIS with a genuinely strong
*forward* reconsideration surface — PONDER with a depth bound, recursive-ASPDMA
retry with conscience guidance, `UpdatedStatusConscience`, DEFER→resolve. The
finding does not dispute any of that. It says the reverse axis is missing, and
D24's own "Current limitations" section already said the same thing:

> *"Today the agent's external actions (SPEAK, TOOL) are emitted into adapter
> sinks rather than into the federation chain — there is no federated row to
> roll back yet."*

This document closes the **node-local** half of that gap at the design level:
there is now a defined corrective object, an authority for it, a linkage
convention and a way to ask what stands. It does **not** close the federation
half, which needs agent actions to be federation rows first, and which is
upstream work (`CIRISNodeCore#15` P11 `ReconsiderationRequest`; FSD-002 §2.2
four-primitive retraction family).

Cross-cutting finding #5 should be updated to "design landed, workflow
unshipped" rather than closed. `compliance/` is intentionally **not edited by
this change** — the compliance set is generated from a seed plus hand-written
sections and is being touched by other work in this release; a pointer belongs
in whichever change lands the workflow.

---

## 10. Files

| File | What |
|---|---|
| `ciris_engine/schemas/services/redress.py` | The whole of Phase 1: dispositions, grounds, reversibility, `ActionRef`, `RedressAuthority`, `CompensatingAction`, `RedressRecord`, `admit_redress`, `resolve_effective_state`, `redress_audit_event_data`, `redress_authorization_payload` |
| `tests/ciris_engine/schemas/services/test_redress.py` | 48 tests, organised by the finding's four properties plus "it is not undo" |
| `FSD/POST_ACTION_REDRESS.md` | This document |

Read but **not modified**: `schemas/services/authority_core.py`,
`schemas/services/graph/audit.py`, `authentication/service.py`,
`governance/wise_authority/service.py`, `logic/infrastructure/handlers/*`,
`compliance/*`.
