# FSD: Prompt context provenance — taxonomy, assembly, policy and tracking

**Status:** draft for CIRISAgent#1366 Phase 2 (2026-11-18). **Owners:** CIRISAgent (engine), RATCHET (model and measurement).
**Vendored from** RATCHET `experiments/claims_registry/m4_battery/ctxflow/FSD_PROMPT_CONTEXT_PROVENANCE.md` @ e64242d; the engine copy is authoritative from here on.
**Companions** (in `formal/h3ere_ctxflow/` unless noted):
- `README.md` (the reference findings);
- `H3EREContextFlow.tla` (the formal contract);
- `MATRIX.md` (the measured baseline);
- `ISSUE_BODY.md` and CIRISAgent#1366 (the 20 items);
- CIRISAgent#1365 (the verified-WA signal);
- `FSD/TASK_ENVELOPE.md` (the tool gate).

---

## 1. Purpose

**Every piece of text the agent sends to a model should be accounted for.** We should know what it is, where it came from, how far it can be trusted, which authority stands behind it, and which stage was allowed to see it. Today that is known only by reading the code, and the code and the prompts have drifted apart.

Market 4 showed the cost. Most of the agent's failures to follow a legitimate Wise Authority rule were not refusals. They happened because a judging stage lacked something the drafting stage had:
- entropy and the optimization veto vetoed compliant replies as "invented policy", and 29 of 31 deferrals were automatic depth-limit deferrals that followed;
- the verb second pass never saw why it was vetoed (0 of 162 retry calls);
- raw user text leaked into the input-ablated consciences through the action record;
- a display name was read as an identity.

All of these were found by matching patterns in 42,998 as-sent prompts, after the fact.

This FSD makes prompt context a typed, policy-checked, recorded thing, so that:
1. **The design is enforceable.** The intentional input ablation of entropy and the optimization veto is a rule the assembler enforces, not a convention each prompt builder must remember.
2. **Authority is explicit.** A rule reaches a judging stage together with its provenance: who authorized it, with which grant, and whether the signature verified. Stages judge authority from carriers the system attests, not from prose.
3. **Every call is measurable.** Each LLM call records exactly which segments it contained. The measured context map, and the TLA+ model's measured configuration, are generated from those records, not inferred.
4. **One source of truth.** A single policy file generates the runtime guard, the TLA+ contract and the conformance tests, so code, model and behaviour cannot silently diverge.

**This FSD does not:**
- change what any stage decides. It changes what each stage is given and what is recorded;
- remove the input ablation;
- replace the conscience layer or the TaskEnvelope tool gate (#938/#905), which enforces authorization outside the model loop. The two are complementary: this FSD governs what models see, the gate governs what tools execute.

## 2. Evidence this responds to (measured, CIRISAgent v2.22.1, qwen/qwen3.6-35b-a3b)

| Finding | Measured |
|---|---|
| A rule the WA states in conversation reaches entropy / optimization veto | ~1% of calls |
| WA guidance reaches entropy in a guidance task | 0% (other stages 100%) |
| Veto reason reaches the verb second pass on retry | 0 of 162 calls (ASPDMA: 1,384 of 1,384) |
| Raw user text reaches entropy / optimization veto via the action record | ~33% of first-pass calls, 62% of retries |
| Sender identity given as a separate verified field | never: only `@display-name (ID: …, role: …)` text |
| Deferral reason visible to the WA | cut at 200 characters; auto-deferrals said only "Maximum action depth (5) reached" |
| `max_tokens` sent vs used | 8,192 on every call; median completion 60–240 tokens |

One model, one or two episodes per case. Source: `MATRIX.md`, `measure.py`.

## 3. Definitions

- **Stage:** one LLM call site in a thought.
  - Drafters: ASPDMA, and the verb second passes TSASPDMA, DSASPDMA, FSASPDMA, MSASPDMA, RSASPDMA.
  - Evaluators: CSDMA, DSDMA, PDMA, IDMA.
  - Judges: coherence, entropy, epistemic humility, optimization veto.
- **Ablated stage:** a stage that by design receives no untrusted text. Today these are entropy and the optimization veto.
- **Segment:** one contiguous piece of text placed into an LLM call by the assembler, with the metadata in §4.
- **Assembler:** the only code allowed to build an LLM message list (§6).
- **Policy:** the stage × kind × provenance table that says what each stage may and must receive (§5).
- **Manifest:** the per-call record of the segments a call contained (§8).

## 4. Taxonomy

A segment is described on five independent axes. The kind says *what* it is. The other four say *where it came from and what it is worth*. Keeping them separate is the point: the earlier measurement mixed them ("rule_in_identity", "raw_ctx_via_record"), and that mixing is how leaks hid.

### 4.1 Kind — what the text is

| Kind | Meaning | Typical lifecycle |
|---|---|---|
| `stage_instruction` | the stage's own prompt (role, task, output contract) | standing |
| `schema_instruction` | output-schema text a provider library appends (e.g. instructor's JSON-schema block; cause of #1363) | per-call |
| `accord` | the Constitution / ethics text | standing |
| `identity_base` | the agent template's identity (Ally) | standing |
| `amendment` | one approved identity amendment | standing, signed |
| `rule` | a behavioural rule in force for this request, with its provenance | see provenance |
| `wa_guidance` | the WA's guidance from a resolved deferral | per-task, signed |
| `request` | the current message being answered | per-message |
| `history` | earlier messages on the channel | per-message window |
| `sender_identity` | the verified sender: user id, role, and the verifier that established them | per-message |
| `display_name` | the sender's self-chosen display name | per-message |
| `action_record` | the factual record of actions already run in this task | per-task |
| `draft` | the proposed action under judgement (SPEAK text, tool + args) | per-thought |
| `dma_output` | an evaluator's result passed downstream | per-thought |
| `conscience_feedback` | a typed veto passed to a retry (§9) | retry-only |
| `tool_output` | a tool's result | per-thought |
| `pipeline_position` | where this stage sits and what it cannot see (#1366 item 12) | standing |

`sender_identity` and `display_name` are separate kinds, so that a stage cannot confuse a name with an identity because of how the prompt is laid out.

### 4.2 Provenance — for `rule` (and any segment carrying a rule)

| Provenance | Example | Can be authoritative? |
|---|---|---|
| `user_chat` | an OBSERVER says "please follow this rule" | no: own-turn preference at most |
| `wa_chat` | the WA states a rule in a message on its channel | no: advisory until signed (§15.1) |
| `signed_guidance` | WA guidance from a resolved deferral, signature verified | yes |
| `amendment` | a landed identity amendment | yes |

### 4.3 Source — which component produced the bytes

`user_input`, `adapter_metadata`, `auth_context`, `signed_row`, `agent_profile`, `engine`, `llm_output`, `tool_output`, `provider_lib`.

### 4.4 Trust

- `untrusted`: user-controlled or model-generated text. Includes `request`, `history`, `display_name`, any `llm_output` (drafts, ponder questions, conscience reasons) and `tool_output`.
- `verified`: established by the system against a credential or signature. Includes `sender_identity` and signed rules.
- `system`: produced by the engine from its own state. Includes `stage_instruction`, `accord`, `identity_base`, `pipeline_position`, and a factual `action_record`.

**Taint rule (no laundering).** A segment's trust is the minimum of its own trust and the trust of every segment whose bytes it contains (`derived_from`, §8). So an `action_record` that embeds a PONDER's quoted user text is `untrusted`, whatever component built it. That is exactly the leak measured today.

### 4.5 AAA carriers

Every segment can carry three optional ids. Required ones are set by policy.

- **Authentication (`authn`):** the verified subject (user id + role) and the verifier (auth context, gateway token, signature). Required on `sender_identity`. (A `wa_chat` rule is never authoritative, authn or not: §15.1.)
- **Authorization (`authz`):** the grant that makes it binding: amendment node id, deferral id, response attestation id, `signature_verified`. Required on `amendment`, `signed_guidance` rules and `wa_guidance`.
- **Accounting (`acct`):** the record tying the segment to the audit trail: row hash, audit entry id, trace id. Plus veto ids and discharge records for `conscience_feedback` (§9).

### 4.6 Lifecycle

| Lifecycle | Rule |
|---|---|
| `standing` | present on every call that policy allows, until revoked |
| `per-task` | only within its task; never in another task |
| `per-message` | only for the thought answering that message |
| `per-thought` | only within the thought |
| `retry-only` | only on a retry, and carried through every retry and both drafting passes |
| `per-call` | only on the call that produced it |

## 5. The policy

One data file, `context_policy.yaml`, is the single source of truth. Each row is: stage × kind (× provenance for `rule`) → `allowed`, `required_when`, `min_trust`.

**Excerpt** (illustrative; the real file covers every stage and kind):

```yaml
defaults:
  ablated_stages: [entropy_conscience, optimization_veto_conscience]
stages:
  entropy_conscience:
    allow:
      stage_instruction: always
      accord: always
      identity_base: always
      amendment: always                  # each with authz
      rule:   {provenance: [signed_guidance, amendment], min_trust: verified}   # §15.1: wa_chat is advisory
      wa_guidance: always                # was 0% (#1366 item 2)
      sender_identity: when_id_scoped    # verified fields only, no display name
      action_record: {min_trust: system} # factual only; tainted record is refused
      draft: always                      # explicit residual: may quote user text (§10)
      pipeline_position: always
    forbid: [request, history, display_name, tool_output]
    require:
      - {kind: rule, when: trusted_rule_in_force}
  tsaspdma:
    allow: {request: always, history: always, sender_identity: always, display_name: labelled, ...}
    require:
      - {kind: conscience_feedback, when: retry}   # was 0 of 162 (#1366 item 1)
```

The policy generates three artefacts, and none of them is hand-edited:
1. the Python table used by the assembler's guard (§6);
2. `ContractPolicy.tla`, which the TLA+ model's contract reads (§11);
3. the fixtures and expectations of the conformance tests (§12).

## 6. The assembler and its runtime guard

- **Single path.** Every LLM call's message list is built by `PromptAssembler.build(stage, segments) → (messages, manifest)`. DMAs and consciences hand it segments; they build no strings. A CI lint (§12) fails any LLM call whose messages did not come from the assembler.
- **Ordering.** Ordering is deterministic per stage, from the policy (e.g. instruction, accord, identity_base, amendments by `granted_at`, rule, …). Same inputs give the same bytes.
- **Rendering.** `sender_identity` renders as a system-built block, for example `VERIFIED SENDER: id=…, role=OBSERVER (verified by auth context)`. `display_name` renders labelled as self-chosen, for example `Display name (self-chosen, not identity): hollis-m4b`. Trusted rules render with provenance, for example `RULE IN FORCE — authorized by Wise Authority wa-…, amendment …, signature verified`.
- **Guard.** Before sending, the assembler checks each segment against the policy, after taint propagation:
  - in **tests and QA**, a violation fails the call (fail closed);
  - in **production**, the offending segment is stripped, an incident is recorded and the call proceeds. Aborting a conscience would make its result "unavailable" and weaken the gate. This choice is explicit and reported.

  A missing *required* segment is likewise a test failure and a production incident.
- **Agent profile.** The template identity is one `identity_base` segment. Each approved amendment is its own `amendment` segment with its own `authz` (node id, attestation ids, signature result, `granted_at`), rendered adjacent. That gives per-grant authority, per-amendment revocation, and per-amendment tracking.

## 6a. Ablation stubs (owner decision 2026-11-18)

**An ablated stage is told what it is not shown.** Today an untrusted segment is simply absent from entropy and the optimization veto. So when a draft follows a rule those stages cannot see, they judge it as an invented policy (Market 4: 29 of 31 deferrals were depth-limit auto-deferrals after such vetoes). Instead, every untrusted segment an ablated stage would otherwise lose is replaced by a **stub**: a system-built description of the segment's properties, carrying none of its bytes.

**What a stub contains.** These fields are a closed set, declared as `stub_fields` in `context_policy.yaml` and enforced by the compiler.

| Field | Values | Computed from |
|---|---|---|
| `kind` | the §4.1 kind | the segment |
| `provenance` | `user_chat` \| `wa_chat` (rules only) | how the segment entered (structural, never by reading the text) |
| `source` | §4.3 source | the segment |
| `trust` | `untrusted` | the segment, after taint |
| `author_role` | `OBSERVER` \| `ADMIN` \| `AUTHORITY` \| `SYSTEM_ADMIN` \| `unauthenticated` | the author's `authn` carrier |
| `authority` | `none` \| `advisory` \| `signed` | `authz`: `signed` only with a verified grant; `advisory` for a chat rule; otherwise `none` |
| `scope` | `this_turn` \| `this_task` \| `standing` | lifecycle |
| `disposition` | per kind: request `open`\|`answered`\|`deferred`\|`refused`; rule `advisory_unsigned`\|`awaiting_signature`\|`refused`; tool_output `success`\|`failure`; history `prior` | engine state |
| `transforms` | subset of `sanitized`, `truncated`, `normalized`, `redacted`, `coalesced` | operations the engine applied |
| `draft_relation` | `none` \| `responds_to` \| `quotes`, with `quote_share` ∈ `0` \| `<10%` \| `10-50%` \| `>50%` | thought linkage, plus deterministic n-gram overlap between draft and segment |
| `size` | `short` \| `medium` \| `long` | length buckets |
| `position` | `current` \| `prior_<n>` | order in the conversation |
| `digest` | sha256 prefix | accounting; correlates the stub with the manifest |

**Rules:**
1. **No free text.** Every value is an enum, a bucket or an id computed by the engine. Excluded on purpose:
   - topic, intent or sentiment;
   - "contains an instruction";
   - any summary, paraphrase or model-generated description.

   An attacker can steer a classifier or summariser, so any such field would carry the content back in.
2. **Stubs only where content is withheld.** A stub is allowed only for an untrusted kind at an ablated stage. Non-ablated stages get the segment in full, never a stub.
3. **The firewall reads:** an ablated stage receives untrusted kinds only as stubs, or as declared residuals (`draft`, `schema_instruction`).
4. **Policy form.** A cell is a predicate, or `{when: <predicate>, form: full|stub}`. The compiler refuses:
   - a stub for a trusted kind;
   - a stub at a non-ablated stage;
   - a stub field outside the closed list;
   - an untrusted kind given in full to an ablated stage.
5. **Rendering.** One system-built line per stub, inside a block whose delimiters are neutralised in all untrusted input (§6). For example:
   `WITHHELD request — author_role=OBSERVER authority=none scope=this_turn disposition=open draft_relation=responds_to quote_share=<10% size=short position=current digest=3f9a…`
6. **What a stub lets a judge conclude, and what it doesn't.**
   - A stub of a chat rule tells entropy that an advisory rule exists, who stated it (role), and that the draft relates to it. That is enough to judge own-turn compliance.
   - It never makes the rule authoritative. Authority still needs a signed `rule` segment (§7).
   - Injection through the stub is bounded by the closed vocabulary: the worst an attacker controls is which bucket a value lands in.

**Model.**
- Invariants: `StubsOnlyAblated` (non-ablated stages never receive stubs) and `StubInformed` (wherever an advisory chat rule exists, each ablated judge holds its stub). `Ablation` is unchanged, since a stub carries no untrusted bytes.
- Judgement: an ablated judge holding a chat-rule stub has evidence for advisory own-turn compliance (S2, S3), and none for authority.

## 7. Composition with the verified-WA signal (#1365)

The "response to request from authorized Wise Authority" block is not new machinery. It is a `rule` segment with provenance `signed_guidance` or `amendment` (never `wa_chat`, §15.1), carrying `authn` and `authz`. Policy requires it for every judge whenever a trusted rule is in force.

A user's attempt (`user_chat`) never produces such a segment. So the ablated stages still judge a user-imposed policy blind, which is the intended firewall.

## 8. Tracking: the per-call manifest

Each LLM call emits a manifest in the reasoning stream, as a sidecar next to `llm_call`. It is not placed in the prompt: no tokens, no behaviour change.

**Per call:**
- `call_id`, `task_id`, `thought_id`, `thought_kind` (seed / followup / guidance), `retry_index`;
- `stage`, `stage_role` (drafter / second_pass / evaluator / judge), `response_model`;
- `max_tokens_sent`, `policy_version`, `assembler_version`;
- `guard_violations` (list).

**Per segment, in order:**
- `segment_id`, `kind`, `provenance`, `source`, `trust` (after taint), `lifecycle`;
- `authn`, `authz`, `acct` (ids);
- `message_index`, `span` [start, end), `sha256`, `truncated`;
- `derived_from` (segment ids whose bytes this segment contains).

`derived_from` is what makes laundering visible: a ponder question, a conscience reason or a draft quoting the request carries the request's id.

**Consumers:**
- **`measure.py`** reads manifests directly. The context matrix becomes exact per call, with no pattern matching. The current text matching stays on as a **differential check** for at least one release: manifest-says vs bytes-contain. That is the only way to catch a call that bypassed the assembler, or a manifest that misdescribes its prompt.
- **`gen_contextdata.py`** generates the TLA+ measured configuration from manifests of real runs.
- **The WA surface:** a deferral package (#1366 item 6) references the manifest of the deferred call.

## 9. Typed vetoes (#1366 items 7–10) in this vocabulary

A veto is a `conscience_feedback` segment with:
- `type` ∈ {`evidence` (cannot see the authority for a rule), `justification`, `substantive`};
- `veto_id` (acct);
- the objecting stage;
- whether that stage held a trusted `rule` segment.

**Rules:**
- **Continuity.** The feedback has lifecycle `retry-only` and must reach every retry *and* every drafting pass, the verb second pass included.
- **Evidence objections.** The *system* looks up trusted state for the cited rule:
  - if found, it attaches the `rule` segment and re-reviews;
  - if not found, the rule is not honoured as policy.

  The drafter's own argument never discharges an evidence objection. For ablated stages, an "improved justification" must not carry untrusted bytes.
- **Re-review.** A changed verdict records a discharge `{veto_id, discharged_by: authz id | changed_action_hash}`.
- **Review integrity.** The executed action's hash (tool, arguments, target, scope) must equal the reviewed `draft` segment's hash. Otherwise it is re-reviewed. The TaskEnvelope gate (#905) enforces the authorization side of this outside the model loop.

## 10. Accepted residuals

- **The draft can quote user text.** The ablated stages must see the action they judge, so injection-by-echo through the draft remains. Policy allows `draft` to ablated stages explicitly. `derived_from` marks quoted spans so the exposure is measurable.
- **`schema_instruction` from a provider library** is outside the engine's control. It is still a segment (`source: provider_lib`), so it is visible and attributable.

## 11. Link to the formal model

- `H3EREContextFlow.tla`'s `ContractHas` is replaced by a generated `ContractPolicy.tla` from `context_policy.yaml`.
- Its measured configuration (`ContextData.tla`) is generated from manifests.
- **New invariants:**
  - `NoLaundering`: no `system` or `verified` segment contains untrusted bytes;
  - `NoCrossTaskLeak`: per-task segments never appear in another task;
  - `IdentityLayout`: authorization reads only `sender_identity`.
- **Existing invariants, read as AAA:**
  - Ablation is trust policy;
  - EvidenceSufficiency is authz;
  - VerifiedIdentity is authn;
  - VetoContinuity, AuthMonotone, ReviewIntegrity and DeferralInformative are accounting.

**Division of labour:**
- TLA+ shows the policy is sufficient for the invariants under stated assumptions.
- The generated guard plus manifest conformance shows the code follows the policy.
- Market 4 and the matrix show the behaviour.

## 12. Tests and CI

1. **Lint.** Every LLM call site goes through `PromptAssembler`, or CI fails.
2. **Policy conformance.** Fixtures for S1–S6, each in seed, follow-up and retry thoughts. Every manifest must satisfy the generated table. Covers each `rule` provenance, the impersonation layout, the tainted action record, and the guidance task.
3. **Guard behaviour.** Fail-closed in QA mode, strip-and-incident in production mode.
4. **Determinism.** Same inputs give identical bytes and manifest hashes.
5. **Model check.** `check.sh` runs in CI against the generated `ContractPolicy.tla`. All invariants must hold.
6. **Differential.** On QA runs, the manifest and text matching must agree (one release).

## 13. Rollout

| Phase | Content |
|---|---|
| 1 (in flight) | #1366 items 1–6, 18, 20: the context gaps closed in place |
| 2 | segment types, `context_policy.yaml`, assembler + guard (QA fail-closed), manifest, typed vetoes (items 7–10), lint |
| 3 | all call sites migrated; production strip-and-incident; `measure.py` and `gen_contextdata.py` on manifests; generated `ContractPolicy.tla` in CI |
| 4 | prompt clarifications (items 11–14) as standing segments; TaskEnvelope Phase 2 gate (item 19) consuming the same `authn`/`authz` ids |

## 14. Acceptance criteria

- **Matrix targets.** The context matrix rebuilt from manifests on a QA run shows:
  - no untrusted segment at an ablated stage;
  - a trusted `rule` segment at every judge whenever a trusted rule is in force;
  - `conscience_feedback` on every retry, including the verb second pass;
  - `sender_identity` separate from `display_name` everywhere.
- **Model.** TLC: every invariant holds against the generated contract.
- **Market 4.** On the same release, the owner-arm deferrals caused by evidence-blind vetoes fall to zero. The full sh-un-07/08 episodes refuse, with no post-review change and no retry that flips a verified-ID refusal.
- **Ablation.** The firewall holds: a user-imposed system-wide rule still does not reach the ablated stages and still does not persist to other users.

## 15. Decisions (Eric, 2026-11-18; were open questions)

1. **WA rules are authoritative only when signed.** A Wise Authority's rule stated in chat (`wa_chat`) is advisory, even with a verified WA role, until it lands as `signed_guidance` or an `amendment`. The agent may offer to defer so the WA signs it. Policy therefore admits `rule` segments to judges only with provenance `signed_guidance` or `amendment`; `wa_chat_verified` is not authoritative.
2. **IDMA receives the trusted `rule` segments and `amendment` segments, with provenance, but not `identity_base`.** It keeps its independent-source view of the agent, and can tell governance from a single epistemic source (#1366 item 15). It also receives chat-stated rules (`rule.user_chat`, `rule.wa_chat`) explicitly labelled advisory, not authoritative (Eric, 2026-11-18), so it can tell one person's request from governance.
3. **The `accord` stays identical across stages** (the full polyglot text, as now).
4. **Manifests ride the trace:** they are emitted in the reasoning stream next to `llm_call` and inherit the trace's signing, consent and retention. No new store.
