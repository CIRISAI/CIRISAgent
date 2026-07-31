# TaskEnvelope — task-scoped authorization, Phase 1

**Issue:** CIRISAgent#938 (this phase) · #905 (enforcement, Phases 2–4)
**Status:** Phase 1 landed. **No enforcement ships in this phase.**
**Scope:** the *subject* a tool gate would authorize, and the plumbing that
puts that subject in front of the gate. Not the gate.

---

## 0. What this does NOT do

Read this section first. Everything below is easier to over-read than it is to
under-read.

- **It does not deny anything.** `ToolBus.execute_tool` runs exactly as it did
  before. A tool call with no envelope, with an empty envelope, or with an
  envelope that names no tools still reaches the provider. The gate is #905
  Ask 1 and it is deliberately out of scope: a half-built gate is worse than
  none.
- **It does not deliver per-task least privilege.** By design the envelope is
  identical for every task in a deployment (§2). It shrinks nothing today.
- **It does not gate CommunicationBus, MemoryBus or LLMBus.** Outward messages,
  memory writes and context egress carry the same argument and are named
  follow-on work in #938, not silently covered.
- **It does not cover the context-enrichment path.** `context_enrichment=True`
  providers are invoked directly against the tool service in
  `ciris_engine/logic/context/system_snapshot_helpers.py:1239`, bypassing
  `ToolBus` entirely. Phase 2 gating the bus would not see them. See §8.
- **It does not make the reasoning loop unable to mint an envelope in a
  sandbox sense.** It makes an accidental mint fail loudly and a deliberate one
  require editing a file that has a test watching it. See §5.
- **It does not replace the conscience layer or Wisdom-Based Deferral.** The
  control on consequential tools is judgement about the specific content, and
  that stays exactly where it is. See §3.

---

## 1. The DRY verdict

**Verdict: mint a new object. `TaskEnvelope` does not project the consent/CEG
attestation primitive.** Reasoning, since #938 asks for it explicitly.

Candidates searched (`grep -r "class .*Envelope\|class .*Grant\|class .*Capability\|class .*Scope\b" --include="*.py"`):

| Existing primitive | Where | Why it does not fit |
|---|---|---|
| `ConsentAttestationEnvelope`, `StructuralAttestationEnvelope`, `LocalAttestationInput` | `logic/services/governance/consent/attestation.py` | These are **CEG wire artifacts**: an `attestation_type` ("scores"/"withdraws"/…), a versioned `dimension` that is the persist upsert key, a `score`/`confidence` pair on the CEG calibration axis, and a claim body that is opaque to persist. Their subject is a *user's standing toward the agent*, asserted outward to a federation. A task envelope's subject is *this process's authority over this task for the next few seconds* and never leaves the node. Projecting it would mean minting a `task_envelope:<task>:v1` dimension per task, which turns a per-task, seconds-lived, node-local object into a federation-visible attestation row — a privacy and volume regression with no consumer. |
| `WACertificate.scopes`, `AuthorizationContext.scopes`, `WAPermission`, `PermissionEntry` | `schemas/services/authority_core.py`, `schemas/services/authority/wise_authority.py` | This *is* the identity-scoped privilege model #938 says is the defect. `scopes` is a JSON array of free-form strings attached to a **certificate** — one identity, one privilege set, process lifetime. Extending it would deepen the thing being fixed. It is also the human/API RBAC surface, not the agent's own action path. |
| `UserRole` | `schemas/api/auth.py` | **Reused.** `RequesterAuthorization.role` is a `UserRole`, not a parallel role enum. |
| `CapabilityCheckResult`, `LicenseStatusResponse` | `ciris_adapters/ciris_verify/ffi_bindings/types.py` | Licence-tier capability checks (`medical:*`, `legal:*`) against the CIRISVerify licence. Categorical and deployment-wide, not task-bound; wildcard-bearing by construction (`"medical:*"`), which is the property we must not inherit. |
| `authorize_delegated` / `CapabilityVerb` (CIRISServer) | `ciris_server._native` | **Not available.** #905 describes this as running in-process via the adopted wheel. It does not: the only occurrences in the installed `_native.abi3.so` are conformance strings reading `proposed:src/auth/gate.rs#authorize_delegated (FSD Status: PROPOSED, not yet wired - CIRISServer#304)`. There is no substrate authorization primitive to project onto. This corrects a factual claim in #905's Gap section. |
| `ActionContext` | `schemas/handlers/context.py` | Closest existing shape to `ToolInvocationSubject` (`task_id`, `thought_id`, `correlation_id`). Rejected: it is an **audit** record — it requires `initiated_by`, `reason`, and a duplicate copy of the action parameters, it has no slot for an envelope, and it cannot be absent (absence is the denial signal we need to represent). |

The one structural idea we *did* take from the consent/CEG side is
**attenuation-by-reissue**: an envelope is immutable and narrowing produces a
new object referencing its parent (`attenuated_from`), the same shape as a CEG
`supersedes`. We did not take the transport.

**Where the envelope is stored is, however, pure reuse** — see §6. It rides in
`TaskContext`, which the persist substrate already round-trips verbatim (the
same channel `__agent_images__` uses). No new table, no migration, no second
lifetime to manage.

---

## 2. The issuance model

> Corrected on #938 after the first draft. The original text said issuance
> could be "derived deterministically from the task source". That framing
> implies task *purpose* is knowable at creation. It is not.

**We cannot know a task's type when it is created.** For ally deployments every
task is a generic assistant task. What is genuinely knowable is four things:

1. **environment tier** — `CIRIS_ENV` → production / qa / development / local
2. **agent role/template** — `CIRIS_TEMPLATE`, `CIRIS_AGENT_ID`
3. **the set of tools this deployment enabled** — resolved live from the tool
   registry via `ToolBus.get_all_tool_info()`
4. **the requester's authorization** — originating user, `UserRole`, channel,
   whether they hold WA standing

`TaskEnvelope` resolves from exactly those. **Task purpose is not an input.**

### The default grant is every enabled tool, and that is correct

Echo ships `discord_ban_user`. It is genuinely consequential, and **every task
must carry it**, because we do not know at creation whether an inbound message
is someone saying hello or someone sharing CSAM. Pre-authorizing by task type
guarantees that the one task which needed the ban is the one that could not
issue it. The same holds for the `context_enrichment=True` providers (weather,
navigation, Home Assistant status), which **auto-run during context gathering**
before the model has selected anything and therefore cannot be declared in
advance, and for web search, which is needed opportunistically.

So: the envelope is **identical for every task in a deployment** by default. It
stays bound per task for attribution and for future narrowing, not because the
grant differs.

### Issuance paths

| Function | Guard | Used by |
|---|---|---|
| `issue_deployment_envelope(...)` (async) | refuses inside a reasoning scope | `BaseObserver._sign_and_add_task` — every adapter's user-message → task path; `DiscordObserver` guidance tasks |
| `issue_deployment_envelope_from_cache(...)` (sync) | refuses inside a reasoning scope | `TaskManager.create_task`, wakeup root/step tasks |
| `issue_authority_envelope(...)` | refuses inside a reasoning scope; requires a named WA/owner id | nothing in the product path yet — the route for declared target roots and issued credentials (Phases 3–4) |
| `attenuate_envelope(...)` | **permitted** inside a reasoning scope | nothing in the product path — see §4 |

`resolve_envelope_for_task_id` (read-only, in a separate module with no minting
surface) is what the handler layer uses at the bus call site.

### Threat assumptions

- **The datastore is not an authorization boundary, and the reasoning loop can
  already write task rows.** The envelope lives in the task row, so anything
  that can write a task row can write an envelope. The mint guard (§5) is on
  the *issuer*, not on the *write*, and there is at least one reasoning-loop
  path that writes a task row today:
  `logic/conscience/updated_status_conscience.py:140` does a read-modify-write
  (`task_get` → `_persist_row_to_task` → flip `updated_info_available` →
  `_task_to_persist_payload` → `task_upsert`) to clear the
  updated-observation flag. It runs inside the conscience layer, i.e. inside
  the reasoning scope.

  Today that path is **safe by accident and by construction**: it round-trips
  the envelope through the same helpers that serialize and decode it, so the
  envelope survives unchanged — locked in by
  `test_conscience_style_read_modify_write_preserves_the_envelope`. But it is a
  write, and a future edit there could set `context.envelope` to anything
  without the issuer guard firing.

  Nothing under `logic/handlers/` or `logic/dma/` constructs a `Task` or calls
  `add_task`/`task_upsert` (verified by grep). Do not restate this as "the
  reasoning layer cannot write task rows" — it can, once, and that is the
  weakest link in Phase 1's issuance story. Closing it means signing the
  envelope and verifying on read (§9), or moving it out of the task row into a
  store the reasoning loop has no write path to.
- **The envelope is not signed.** `Task` already carries `signed_by` /
  `signature` (observer-WA signing at `base_observer._sign_and_add_task`), which
  covers the row the envelope rides in but is not verified on read anywhere.
  Signing the envelope itself is deferred; it buys nothing until something
  enforces it.
- **In-process Python is not a boundary.** §5.
- **A compromised high-privilege task remains unconstrained within its
  envelope.** Task-scoping shrinks blast radius; with a near-total grant it
  shrinks it by very little today. That is what the conscience layer and WBD
  are for, and they are semantic, not deterministic.

---

## 3. Consequential tools stay in the envelope

Anything carrying `ToolDMAGuidance(requires_approval=True)` — kick/ban,
financial tools, destructive tools — is controlled by **judgement about the
specific content**: the four epistemic consciences plus Wisdom-Based Deferral
to a human. That is the existing design and it is the right one.

**Phase 1 does not model "requires approval" as an envelope-level denial, and
Phase 2 must not either.** An envelope-level pre-authorization decision cannot
see the content and would either block the ban that was needed or wave through
the one that was not. Duplicating the check would also mean two places to
misconfigure and a false sense that the deterministic layer is doing work the
semantic layer is actually doing.

`ToolCapability.MODERATE_CHANNEL` exists so the effect class is *nameable*
(Phase 4 needs to distinguish read from write from moderate), not so it can be
withheld. `test_consequential_tools_are_grantable_and_not_schema_denied` locks
this in.

---

## 4. Attenuation ships; no narrowing policy ships

`TaskEnvelope.attenuate()` returns a strictly narrower envelope for the same
task. Every axis is subset-checked; any superset argument raises
`EnvelopeWideningError`. There is **no widening operation anywhere in the
module** — `test_no_widening_entry_point_exists_on_the_model` asserts the
absence by name.

**CIRISAgent ships no narrowing policy.** Nothing in `ciris_engine/` calls
`attenuate_envelope`, and `test_no_narrowing_policy_ships_for_cirisagent`
fails if that changes without justification.

The capability exists because the vertical deployments — CIRISMedical,
CIRISFinancial — have **typed tasks**, where purpose *is* knowable at creation
and narrowing is meaningful. Forward-compatible architecture, honest that
today's grant is near-total.

---

## 5. What "the reasoning path cannot mint" actually proves

`ciris_engine/logic/infrastructure/authorization/reasoning_scope.py` is a
`contextvars` marker. `ThoughtProcessor.process_thought` and
`ActionDispatcher.dispatch` enter it; every mint entry point raises
`EnvelopeIssuanceForbidden` while it is set.

**Proven** (`test_reasoning_cannot_mint.py`, 19 tests):

1. Every mint entry point raises inside the scope, including from
   `asyncio.create_task` children (contextvars are copied into child tasks).
2. `ActionDispatcher.dispatch` really sets the marker — verified by *executing*
   it with a recording subclass, not by reading source.
3. `ThoughtProcessor.process_thought` contains the `reasoning_scope(` call
   (AST-level; a functional run needs the whole H3ERE pipeline stood up).
4. No module under `logic/dma/`, `logic/conscience/` or `logic/handlers/`
   imports `envelope_issuer` — AST-level import scan.
5. The handler layer reads envelopes through `envelope_reader`, and
   `envelope_reader` has no minting surface (asserted by content check).
6. Attenuation *is* permitted inside the scope and still cannot widen.

**Not proven.** This is one Python process; anything that can `import` can
reach anything.

- (3) asserts the call is present, not that it wraps every path through the
  function. A refactor could move work outside the `with` block.
- (4) is a static scan of `import` statements. `importlib.import_module` would
  slip past it, as would re-exporting the issuer from a module the scan does
  not watch.
- A future processor that dispatches handlers without entering the scope would
  evade (1) and (2) entirely. (4) is the independent check that would still
  fire, which is why both exist.
- Nothing stops a direct `contextvars` reset by code that wants to.

**The honest claim:** an accidental mint from the reasoning path fails loudly at
runtime, and a deliberate one cannot be added without changing a file these
tests watch. It is not a sandbox and must not be described as one. A real
boundary would be process separation — the issuer running outside the runtime
that hosts the model loop. That is the successor design, not this one.

---

## 6. Storage, lifetime, restart, multi-occurrence

The envelope is a typed field on `TaskContext`
(`schemas/runtime/models.py`), so it is stored **in the task row**.

- **Lifetime = the task's, by construction.** The envelope is written with the
  row and disappears with it. No separate expiry, no registry to reap, no way
  for an envelope to outlive its task.
- **Restart.** `TaskContext` round-trips through persist's `context` JSON blob
  (`_task_to_persist_payload` / `_persist_row_to_task`), so a task resumed after
  a restart still holds the envelope it was issued. An in-memory registry keyed
  by `task_id` would have lost it, and under Phase 2 that would silently
  disable every in-flight task's tools after a restart.
- **Multi-occurrence.** Persist is the shared store, so occurrence B reading a
  task written by occurrence A sees the same envelope.
  `deployment.agent_occurrence_id` records who issued it, which is the input a
  Phase 2 policy would need to decide whether cross-occurrence borrowing is
  acceptable. Phase 1 does not decide that.
- **Decode failure ⇒ `None` ⇒ denial.** `_decode_envelope` (both the persist
  path and the legacy `map_row_to_task` path) logs loudly and returns `None`. A
  corrupt envelope must never fall back to "unconstrained".
- **No migration.** Persist stores `context` as opaque JSON; adding a field
  needs no schema change. Old task rows simply have no `envelope` key, which
  decodes to `None`, which is denial.

---

## 7. Is blanket-allow unrepresentable?

**On every axis where "unbounded" could be written: yes.** On "exhaustive
enumeration": no, and that is intentional.

What the schema refuses:

- `ToolCapability` has **no wildcard member**; `granted_tools` rejects any entry
  containing `*` or `?` or failing `^[A-Za-z0-9][A-Za-z0-9_.:\-]*$`
  (`test_granted_tools_rejects_every_pattern_shape`, 6 shapes).
- There is **no `allow_all` / `unrestricted` / `bypass` / `sandbox_mode` field**
  — asserted by name in `test_no_allow_all_style_field_exists`, specifically
  because `ToolHandlerData.sandbox_mode` is the failure this work exists to
  avoid repeating.
- There is **no "`None` means unrestricted" state**. Every grant axis defaults
  to empty, and empty means *nothing*. `permits_tool` on an empty set is
  `False`, not `True`.
- `TargetRoot.host` and `path_prefix` reject patterns; `*.example.com` and `*`
  raise.
- `IssuedCredential.credential_ref` rejects patterns.
- The model is `frozen=True, extra="forbid"` — no post-issuance mutation, no
  smuggled field.

**The residual, stated plainly.** "Every tool this deployment enabled is
granted" is expressible — as the resolved, explicitly enumerated set of names
the registry returned, frozen into the envelope. So is "every effect class", as
`ALL_TOOL_CAPABILITIES`, a literal enumeration of all 12 members. A schema
cannot distinguish "a complete set" from "a set that happens to contain
everything", and it should not try: for CIRISAgent the complete set is the
*correct* grant (§2).

The distinction that matters is auditability, and it holds. `granted_tools`
lists 40-odd literal names that change visibly in a diff when an adapter is
added or removed; `allow: ["*"]` is one token that never changes and tells a
reviewer nothing. An enumerated complete set is diffable, greppable and
attestable. That is the property we are actually buying.

**The one bounded wildcard-like affordance** is
`TargetRoot.include_subdomains: bool`. It is a boolean under an already-named
literal parent host: it can only expand within one registrable domain and can
never reach an unrelated host. It exists because Phase 4 (#905 Ask 3) needs
"same registrable domain by default". It is isolated to `TargetRoot` and
documented on the class.

**Where the pressure will come from.** Requiring every deployment to enumerate
tool names is what usually drives someone to add `"*"`. That pressure is
already relieved: the enumeration is *resolved*, not hand-written — nobody
maintains a list. If a Phase 2 reviewer proposes a wildcard, the answer is
"resolve the set from the registry", not "add a wildcard".

---

## 8. What Phase 2 consumes, and what it must not do

Phase 2 (#905 Ask 1) gates `ToolBus.execute_tool` and receives:

```python
subject: Optional[ToolInvocationSubject]
  .origin        # reasoning | context_enrichment | governance_service | operator_api | adapter_lifecycle
  .task_id       # present iff task-bound
  .thought_id    # present iff task-bound
  .envelope      # Optional[TaskEnvelope] — None means DENY
  .component     # present iff not task-bound
```

Policy input is `(identity, task envelope, tool name)` and nothing else
model-authored. `origin` and `component` are set by CIRIS code at the call
site; the model cannot choose them, and the schema makes it impossible for a
task-bound subject to masquerade as a component subject or vice versa.

**Rules Phase 2 must follow:**

1. **Gate on `granted_tools` (the tool-name axis), not on `capabilities`.**
   There is no tool → capability-class registry, and inferring one would deny
   legitimate, deployment-enabled tools. `capabilities` is Phase 4's read/write/
   credential-surface axis. Do not turn it into a second tool gate.
2. **Do not duplicate `requires_approval`.** §3.
3. **`subject is None` and `subject.envelope is None` are both denials**, never
   exemptions. The fail-closed predicates already exist:
   `envelope_permits_tool(None, x) is False`.
4. **Decide explicitly about non-task origins.** `GOVERNANCE_SERVICE` (DSAR),
   `OPERATOR_API` and `ADAPTER_LIFECYCLE` are named so they cannot inherit a
   silent exemption. They are not model-authored; they are also not covered by
   task-scoped authorization. Pick a policy and write it down.
5. **Route denial to WBD deferral where a human is reachable.** A fail-closed
   gate that is not survivable gets switched off.
6. **Attest denials.** A signed trace of denials is evidence; "we deny X" is a
   claim.

**Blockers Phase 2 must clear first — these are real and named:**

- **Cold-cache issuance.** If a task is created before any adapter has
  registered a tool service, the envelope is issued with an **empty** grant and
  a `WARNING`. Inert today; under Phase 2 that task can use no tools at all.
  Phase 2 must prime the enabled-tool set at runtime bootstrap (before the first
  observer can create a task) and should fail startup rather than issue empty
  envelopes.
- **Unwired task-creation sites.** Envelopes are issued at
  `BaseObserver._sign_and_add_task` (covers every adapter's user-message path),
  `DiscordObserver` unsolicited-guidance tasks, `TaskManager.create_task`, and
  the WAKEUP root + step tasks. **Not yet wired**, verified by grep:
  - `logic/processors/states/minimal_dream_processor.py:210` — dream tasks
  - `logic/utils/consent/partnership_utils.py:97` — partnership request tasks
  - `persistence/models/tasks.py::try_claim_shared_task` — the shared
    `WAKEUP_SHARED_*` / `SHUTDOWN_SHARED_*` tasks in the `__shared__`
    occurrence namespace. Multi-occurrence coordination tasks, so whichever
    occurrence claims one inherits an envelope-less task.
  - `persistence/models/tasks.py::add_system_task` — signs then delegates to
    `add_task`; no envelope.
  - `logic/services/governance/wise_authority/service.py:782` — WA guidance
    tasks are written with a hand-built payload straight to
    `engine.task_upsert`, bypassing `add_task` entirely. Anything added to
    `add_task` will not reach this path.

  All of these resolve to `None`, which under Phase 2 denies. Wire them or
  exempt them deliberately — do not discover this when wakeup stops working.
- **The context-enrichment bypass.** `context_enrichment=True` providers are
  called directly on the tool service in `system_snapshot_helpers.py:1239` and
  never touch `ToolBus`. Gating the bus leaves this path ungated — which is
  *safe* for availability (weather keeps working) but means the gate's coverage
  claim must exclude it, or the path must be routed through the bus first.
  `ToolCallOrigin.CONTEXT_ENRICHMENT` exists ready for that rerouting.
- **`correlation_id` is still a fresh uuid4** at `tool_bus.py` (unchanged by
  design — `get_tool_result(correlation_id)` consumers depend on the format).
  The subject, not the correlation id, is now the identity carrier.

---

## 9. Deferred / open

- **Signing the envelope.** Worth doing when something enforces it; pointless
  before. Would need an issuer key and verification on read.
- **Process separation for the issuer.** The only thing that turns §5's "fails
  loudly" into "cannot".
- **Environment-tier separation** (`deployment.environment_tier`) is recorded at
  issuance and **not enforced in Phase 1**. It is Phase 2's input for "a dev
  deployment must not reach production targets". Naming it here rather than
  pretending otherwise.
- **`target_roots` / `credentials` are empty for every CIRISAgent envelope
  today.** Nothing declares roots and no credential is envelope-scoped yet. They
  are not decoration: the cross-field invariant "every issued credential must
  bind to a declared target root" is enforced at issuance and tested, and it is
  the provisioning-side change #905 Ask 2 says is required. They become
  load-bearing in Phases 3–4.
- **Other buses.** CommunicationBus, MemoryBus, LLMBus carry the same argument
  and are not covered.

---

## 10. Files

| Path | Role |
|---|---|
| `ciris_engine/schemas/runtime/task_envelope.py` | `TaskEnvelope`, `ToolCapability`, `ToolInvocationSubject`, `DeploymentScope`, `RequesterAuthorization`, `TargetRoot`, `IssuedCredential`, fail-closed predicates |
| `ciris_engine/logic/infrastructure/authorization/reasoning_scope.py` | the contextvars marker |
| `ciris_engine/logic/infrastructure/authorization/deployment.py` | tier / agent / template resolution |
| `ciris_engine/logic/infrastructure/authorization/enabled_tools.py` | resolved + cached enabled-tool set |
| `ciris_engine/logic/infrastructure/authorization/envelope_issuer.py` | the three mint paths + attenuation + binding; guarded |
| `ciris_engine/logic/infrastructure/authorization/envelope_reader.py` | read-only lookup; no minting surface |
| `ciris_engine/schemas/runtime/models.py` | `TaskContext.envelope` |
| `ciris_engine/logic/persistence/models/tasks.py`, `.../persistence/utils.py` | round-trip + fail-closed decode |
| `ciris_engine/logic/buses/tool_bus.py` | `execute_tool(..., subject=...)`, identity-less warning, registers as enabled-tool source |
| `ciris_engine/logic/handlers/external/tool_handler.py` | builds the reasoning subject |
| `ciris_engine/logic/infrastructure/handlers/action_dispatcher.py`, `.../thought_processor/main.py` | enter the reasoning scope |
