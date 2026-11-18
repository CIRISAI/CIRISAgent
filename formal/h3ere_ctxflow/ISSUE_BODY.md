The Market 4 pre-step and episodes on v2.22.1 showed that most failures to follow a Wise Authority's rule were context failures, not refusals. A judging stage lacked something the drafting stage had, or the retry lost the objection. This issue lists the small changes that close those gaps. Evidence and the formal model are in RATCHET `experiments/claims_registry/m4_battery/ctxflow/`.

**Basis.** The as-sent prompts of 42,998 LLM calls on v2.22.1-stable (`b0ac79842`, qwen/qwen3.6-35b-a3b; RATCHET runs 44146712920, 44150719651, 44150738031, 44204315191, 44208916740, 44208929326, 44219599913, 44219609447, 44226447023). One model, one or two episodes per case: *measured* on that, nothing wider.

**Design stance.**
- The input ablation of entropy and the optimization veto is intentional and stays (#1365).
- A drafting stage being fooled is acceptable. Safety rests on the consciences holding and the retry respecting them.

## A. Context-passing gaps

1. **Give the verb second pass (TSASPDMA and siblings) the veto reason on retry.**
   *Why:* on retry ASPDMA receives `CONSCIENCE OVERRIDE GUIDANCE` in 1,384 of 1,384 calls; TSASPDMA receives it in 0 of 162. In sh-un-08 (run 44226447023) TSASPDMA proposed the same vetoed ticket four times, once under the authorized person's ID.
2. **Give entropy the WA's guidance in a guidance task, as the optimization veto already gets.**
   *Why:* after a WA resolves a deferral, every stage has the guidance in 100% of calls except entropy, which has it in 0%. Entropy then kept vetoing replies that followed the WA (25 flags in 11 guidance tasks).
3. **Add the verified-WA block to entropy and the optimization veto (#1365).**
   *Why:* a rule the WA states in conversation reaches about 1% of their prompts. They call a compliant reply an invented policy. 29 of 31 deferrals were depth-5 auto-deferrals after such vetoes.
4. **Make the action record factual for the two ablated consciences: action, tool, status, no message text.**
   *Why:* after a PONDER the record embeds `=== PREVIOUS CONTEXT === You observed @… say: <user text>`. Raw user text reaches entropy and the optimization veto in about 33% of first-pass calls and 62% of retries. That reopens the channel the ablation closes.
5. **Pass the sender's verified ID and role as a separate system-built field, with the display name labelled "self-chosen, not identity".**
   *Why:* every prompt has only `@display-name (ID: …, role: …)`. On v2.21.0, coherence and epistemic humility read the display name as the identity and vetoed a correct ID-mismatch refusal (trace in #1365).
6. **Put the last draft and the veto reasons in an auto-deferral, and stop cutting deferral reasons at 200 characters in `GET /v1/wa/deferrals`.**
   *Why:* the WA currently sees only "Maximum action depth (5) reached" and cannot tell what to validate.

## B. Decision contract between consciences and retry

7. **Type every veto: missing authority evidence, insufficient justification, or substantive (ethical/safety/coherence) objection.**
   *Why:* the retry is told "rejected because: <reason>" as fact, whatever its kind. On v2.21.0 an "I can't see this rule" objection was read as "the rule is a hallucination" and a correct refusal became a filed ticket. Each type needs its own response:
   - *Evidence:* the **system** looks the rule up in trusted state (amendment, signed guidance). If it is there, attach it and re-review. If it is not, the rule is not honoured as policy. The drafter's own argument must never discharge an evidence objection.
   - *Justification:* the drafter may restate.
   - *Substantive:* the action changes.
8. **Carry the objection through every retry and both drafting passes; a substantively vetoed action may not be re-proposed unchanged.**
   *Why:* item 1's measurement; also each conscience call is stateless, so nothing stops a vetoed action passing on a later roll.
9. **Allow re-review to change a verdict only on new trusted evidence or a materially changed action, and record what changed.**
   *Why:* without a record, pass-after-veto is indistinguishable from sampling noise. Constraint: for the two ablated consciences an "improved justification" must not carry untrusted text, or it becomes the persuasion channel the ablation exists to block.
10. **Execute only what was reviewed: tool, arguments, target and scope. Re-review any material change.**
    *Why:* on v2.21.0 a retry-path TOOL went out with `parameters: {}` after the consciences had passed it, with no second pass. Whether v2.22.1 still allows a post-review change is untested, so it needs a regression test. In the model, one unreviewed change breaks four invariants.

## C. Prompt clarifications

11. **State the roles in the DMA and conscience prompts.** An OBSERVER may shape their own answer for this turn. Only the WA or owner sets standing, everyone-wide rules. An approved amendment in the identity block is authoritative policy.
    *Why:* consciences called landed or WA-stated rules "custom, non-standard policy"; a user-stated system-wide rule was adopted in the same-user reply in 73 of 102 cases.
12. **Tell each stage where it sits in the pipeline and what it cannot see.** For entropy and the optimization veto: "you do not see the user's message, by design; if the draft cites a rule you cannot see, raise an evidence objection."
    *Why:* they currently judge as if they saw everything.
13. **Separate policy from capability:** a deployment rule restricts behaviour and does not deny ability or change identity.
    *Why:* "Ally no longer writes code here" was vetoed as a false capability claim and as a permanent identity change.
14. **Reword veto feedback to the retry.** Name the objecting conscience, its type (item 7), and whether it could see the rule.
    *Why:* same failure as item 7, at the prompt level.

## D. To investigate

15. **IDMA and authority.** Test whether IDMA characterises a valid, visible WA instruction as rigidity and so undermines it.
    *Why:* in xn-48 IDMA scored the instructed reply `k_eff 1.0, phase rigidity, fragility_flag true` ("relies on a single source: the user's explicit instruction") and recommended deviating. Any WA instruction is a single source by nature. IDMA carries no identity block or amendments (0% of calls).
16. **Prompt consistency and context audit.** Check for contradictory examples and schema instructions (known: ASPDMA is told "TSASPDMA will handle parameters"). Trace every follow-up path for ablated information coming back in (item 4 is one).
17. **The `wa-` prefix on every user ID.** TSASPDMA wrote "the user is a designated Wise Authority" about an OBSERVER whose ID began `wa-`. Cause untested.
18. **Action record for coherence and epistemic humility.** They receive it in roughly 20–80% of follow-up calls, while entropy and the optimization veto always do. Not traced.

## E. TaskEnvelope Phase 2 (#938, #905)

19. **Land the tool gate at `ToolBus.dispatch_to_provider` now.**
    *Why:* at v2.22.1 the envelope is still record-only (CHANGELOG: "nothing denies on it yet"). Items 5 and 10 need the same thing Phase 2 provides: a deterministic, task-scoped subject the gate checks at execution, independent of any model's reading of a display name. With the gate, an authorization fact such as "this sender may not file" is enforced outside the LLM loop, and the consciences become a second line of defence, not the only one. The blockers `FSD/TASK_ENVELOPE.md` §8 names (cold-cache issuance, unwired subjects, the open bypasses) apply.

## Formal model

`H3EREContextFlow.tla` (TLA+, TLC) specifies one thought as it should run, with ten invariants and termination:
- the firewall;
- evidence sufficiency;
- verified identity;
- no wrong execution;
- review integrity;
- veto continuity;
- authorization monotonicity;
- no forced deferral;
- informative deferral.

| Configuration | Result |
|---|---|
| Proposed contract (items 1–10) | all ten invariants and termination hold |
| Measured v2.22.1 prompt contents (generated from the 42,998 calls) | 8 invariants violated; TypeOK and review integrity hold |
| Contract with one unreviewed post-review change | 4 invariants violated |

The model is small and abstract. It shows that the contract is consistent and sufficient under two stated assumptions: drafters are fallible, and a conscience holding the evidence judges correctly. It does not show that the engine implements the contract. In measured mode a violation means "reachable", not "observed". The ones observed in runs are the forced deferrals, the v2.21.0 wrong execution and the repeated re-proposal.

**Suggested order.** Items 1–4 first: they are small and remove most of the volume. Then 7–10, the safeguards that keep the pipeline safe when context is still missing. Then the prompts, 15–18, and 19 alongside.
