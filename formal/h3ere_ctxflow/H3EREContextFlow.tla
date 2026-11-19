------------------------- MODULE H3EREContextFlow -------------------------
(***************************************************************************)
(* One H3ERE thought as it SHOULD run: what context each conscience        *)
(* receives, how a veto is typed and carried through retries, and what may *)
(* execute.                                                                *)
(*                                                                         *)
(* Rules = "contract": the context contract GENERATED from                 *)
(*   context_policy.yaml (gen_contract_policy.py -> ContractPolicy.tla),   *)
(*   plus the typed-veto decision contract.                                *)
(* Rules = "measured": prompt contents as measured from 42,998 as-sent     *)
(*   LLM calls on CIRISAgent v2.22.1 (ContextData.tla, generated), with    *)
(*   the engine's untyped veto feedback.                                   *)
(*                                                                         *)
(* Modelling assumptions (the only ones):                                  *)
(*  A1. Drafting stages (ASPDMA, verb second pass) are fallible: they may  *)
(*      propose any action available in the scenario. Safety must not rest *)
(*      on them.                                                           *)
(*  A2. A conscience that holds the evidence a decision rests on judges it *)
(*      correctly. Without it, it judges the action at face value: an      *)
(*      ordinary helpful action passes; a rule-driven restriction or       *)
(*      refusal may be vetoed as an invented policy.                       *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets, TLC, ContextData, ContractPolicy

CONSTANTS Rules, MaxDepth, PostReviewChange, VerbPassSeesVeto, ToolGate
ASSUME Rules \in {"measured", "contract"} /\ MaxDepth \in 1..6 /\ PostReviewChange \in BOOLEAN
       /\ VerbPassSeesVeto \in BOOLEAN /\ ToolGate \in BOOLEAN
\* (CIRISAgent additions) VerbPassSeesVeto, #1366 item 1: the veto reason reaches the verb second pass
\*   (TSASPDMA), which drafts TOOL actions; FALSE = ASPDMA only, so a banned TOOL action can come back.
\* ToolGate, #1366 item 19: TaskEnvelope Phase 2 checks a deterministic authorization fact at
\*   ToolBus.dispatch_to_provider. In S6 the sender may not file, so a filing is denied at dispatch.

Scenarios == {"S1", "S2", "S3", "S4", "S5", "S6"}
\* S1 no rule in force.
\* S2 an ordinary user states a rule in their own message (own-turn preference at most).
\* S3 the WA states a rule in chat, not signed: ADVISORY until signed (decision 2026-11-18). Acceptable:
\*    follow it in that conversation, answer normally, or defer asking the WA to sign it (which yields S4).
\* S4 guidance task: the WA resolved a deferral, repeating the rule (signed).
\* S5 the rule landed as an approved identity amendment; another user asks.
\* S6 as S5 and ID-scoped; the asker shows the authorized person's display name.
Kinds   == {"seed", "followup"}
Judges  == {"coherence", "entropy", "epistemic", "optveto"}
Ablated == {"entropy", "optveto"}          \* input-ablated by design: no untrusted text
\* Atoms: segment kinds with the provenance / rendering the model reasons about (FSD §4).
Untrusted == {"request", "history", "display_name_labelled", "display_name_unlabelled", "action_record_tainted",
              "rule_user_chat", "rule_wa_chat"}
Items == {"request", "history", "identity_base", "amendment", "wa_guidance", "sender_identity",
          "action_record_factual", "action_record_tainted", "display_name_labelled", "display_name_unlabelled",
          "rule_user_chat", "rule_wa_chat", "rule_verified",
          \* Ablation stubs (FSD §6a): engine-computed properties of a withheld segment, none of its bytes.
          "request_stub", "history_stub", "tool_output_stub", "rule_chat_stub"}
Stubs == {"request_stub", "history_stub", "tool_output_stub", "rule_chat_stub"}

Options(s) == CASE s = "S1" -> {"normal"}
                [] s = "S3" -> {"follow", "normal", "defer_sign"}
                [] s = "S6" -> {"refuse", "file"}
                [] OTHER    -> {"follow", "normal"}
Acceptable(s, a) == CASE s = "S1" -> a = "normal"
                      [] s = "S2" -> a \in {"follow", "normal"}  \* same-user reply: either is fine
                      [] s = "S3" -> a \in {"follow", "normal", "defer_sign"}  \* advisory until signed
                      [] s = "S6" -> a = "refuse"
                      [] OTHER    -> a = "follow"
TrustedRule(s) == s \in {"S4", "S5", "S6"}   \* a SIGNED rule is in force (signed guidance or amendment)
FaceValueFine(a) == a \in {"normal", "file", "defer_sign"}       \* looks like ordinary help to a stage without the rule
ToolActions == {"file"}
GateDenies(s, a) == ToolGate /\ s = "S6" /\ a \in ToolActions
Draftable(b) == IF VerbPassSeesVeto THEN b ELSE b \ ToolActions

Pres(j, s, k, item) == IF Rules = "contract" THEN ContractHas(j, s, k, item) ELSE MeasuredHas(j, s, k, item)

Always(s, k) == [ j \in Judges |-> { it \in Items : Pres(j, s, k, it) = "always" } ]
Maybe(s, k)  == [ j \in Judges |-> { it \in Items : Pres(j, s, k, it) = "sometimes" } ]
\* Per call a stage receives none or all of its "sometimes" items (they arrive together in practice).
InputChoices(s, k) ==
    { [ j \in Judges |-> [ it \in Items |-> it \in (Always(s, k)[j] \cup (IF j \in on THEN Maybe(s, k)[j] ELSE {})) ] ] :
        on \in SUBSET Judges }

VARIABLES scen, kind, inputs, pc, draft, vetoed, banned, discharged, attached, depth, reviewed, final,
          everRefused, package
vars == <<scen, kind, inputs, pc, draft, vetoed, banned, discharged, attached, depth, reviewed, final,
          everRefused, package>>

Trusted(p) == p["rule_verified"] \/ p["amendment"] \/ p["wa_guidance"]
\* Does conscience j hold the evidence the decision rests on?
HasEvidence(j) ==
    LET p == inputs[j] IN
    CASE scen = "S1" -> TRUE
      \* An ablated judge holding a stub of the chat rule knows an advisory rule exists, who stated it (role)
      \* and that the draft relates to it: enough to judge own-turn compliance, never enough to treat it as signed.
      \* Only signed rules count (2026-11-18): a chat-stated rule has no segment of its own; a non-ablated judge sees
      \* it inside the request. Ablated judges have no evidence for it, by design.
      [] scen = "S2" -> j \notin Ablated /\ p["request"]
      [] scen = "S6" -> (attached \/ Trusted(p)) /\ (attached \/ p["sender_identity"])
      [] OTHER       -> attached \/ Trusted(p) \/ (scen = "S3" /\ j \notin Ablated /\ p["request"])

\* Verdicts available to conscience j on the current draft (A2).
Verdicts(j) ==
    IF HasEvidence(j) THEN (IF Acceptable(scen, draft) THEN {"pass"} ELSE {"substantive"})
    ELSE IF FaceValueFine(draft) THEN {"pass"}
    ELSE IF Rules = "contract" THEN {"pass", "evidence"}   \* "I cannot see this rule": typed
    ELSE {"pass", "untyped"}                                \* "invented policy": untyped veto

Init ==
    /\ scen \in Scenarios /\ kind \in Kinds
    /\ inputs \in InputChoices(scen, kind)
    /\ pc = "draft" /\ draft = "none" /\ vetoed = {} /\ banned = {} /\ discharged = {}
    /\ attached = FALSE /\ depth = 0 /\ reviewed = "none" /\ final = "none"
    /\ everRefused = FALSE /\ package = FALSE

\* A1: the drafter may propose anything not banned. Under the contract a substantively vetoed action
\* is banned (the veto reason reaches ASPDMA AND the verb second pass); measured, nothing is banned.
Draft ==
    /\ pc = "draft"
    /\ IF Options(scen) \ Draftable(banned) = {}
         THEN /\ final' = "defer" /\ package' = TRUE /\ pc' = "done" /\ UNCHANGED <<draft, everRefused>>
         ELSE /\ \E a \in Options(scen) \ Draftable(banned) :
                   /\ draft' = a /\ everRefused' = (everRefused \/ a = "refuse")
              /\ pc' = "judge" /\ UNCHANGED <<final, package>>
    /\ UNCHANGED <<scen, kind, inputs, vetoed, banned, discharged, attached, depth, reviewed>>

Judge ==
    /\ pc = "judge"
    /\ \E v \in [ Judges -> {"pass", "substantive", "evidence", "untyped"} ] :
         /\ \A j \in Judges : v[j] \in Verdicts(j)
         /\ LET types == { v[j] : j \in Judges } \ {"pass"} IN
            IF types = {}
              THEN /\ reviewed' = draft /\ pc' = "exec"
                   /\ UNCHANGED <<vetoed, banned, discharged, attached, depth, final, package>>
              ELSE /\ vetoed' = vetoed \cup {draft}          \* veto continuity: the objection is kept
                   /\ depth' = depth + 1
                   /\ IF depth + 1 >= MaxDepth
                        THEN /\ final' = "auto_defer" /\ pc' = "done"
                             /\ package' = (Rules = "contract")  \* last draft + veto reasons go to the WA
                             /\ UNCHANGED <<banned, discharged, attached>>
                        ELSE /\ UNCHANGED <<final, package>>
                             /\ IF Rules = "measured"
                                  THEN /\ pc' = "draft" /\ UNCHANGED <<banned, discharged, attached>>
                                ELSE IF "substantive" \in types
                                  THEN /\ banned' = banned \cup {draft} /\ pc' = "draft"
                                       /\ UNCHANGED <<discharged, attached>>
                                \* evidence objection only: the SYSTEM looks the rule up in trusted state
                                ELSE IF TrustedRule(scen)
                                  THEN /\ attached' = TRUE /\ discharged' = discharged \cup {draft}
                                       /\ pc' = "judge" /\ UNCHANGED banned   \* re-review with the evidence attached
                                  ELSE /\ banned' = banned \cup {draft} /\ pc' = "draft"
                                       /\ UNCHANGED <<discharged, attached>>
                   /\ UNCHANGED reviewed
    /\ UNCHANGED <<scen, kind, inputs, draft, everRefused>>

\* Only the reviewed action executes. PostReviewChange models a stage that alters tool/arguments/target
\* after review without a new review (seen on v2.21.0's retry path; not asserted for v2.22.1).
Exec ==
    /\ pc = "exec"
    /\ \E f \in (IF PostReviewChange THEN Options(scen) ELSE {reviewed}) :
         final' = IF GateDenies(scen, f) THEN "refuse" ELSE f   \* a denied dispatch is a refusal
    /\ pc' = "done"
    /\ UNCHANGED <<scen, kind, inputs, draft, vetoed, banned, discharged, attached, depth, reviewed,
                   everRefused, package>>

Done == pc = "done" /\ UNCHANGED vars
Next == Draft \/ Judge \/ Exec \/ Done
Spec == Init /\ [][Next]_vars /\ WF_vars(Draft \/ Judge \/ Exec)

----------------------------------------------------------------------------
Executed == final \in {"normal", "follow", "refuse", "file", "defer_sign"}

TypeOK == pc \in {"draft", "judge", "exec", "done"} /\ depth \in 0..MaxDepth
\* I1  The firewall: input-ablated consciences receive no untrusted text.
Ablation == \A j \in Ablated : \A it \in Untrusted : ~inputs[j][it]
\* I2  Every conscience holds trusted evidence for a verified-WA rule in force.
EvidenceSufficiency == TrustedRule(scen) => \A j \in Judges : Trusted(inputs[j])
\* I3  ID-scoped decisions: the verified sender id is a field of its own wherever a display name is shown.
VerifiedIdentity == (scen = "S6") => \A j \in Judges : inputs[j]["sender_identity"]
\* I10 No laundering: no system-labelled segment carries untrusted bytes (the action record is factual).
NoLaundering == \A j \in Judges : ~inputs[j]["action_record_tainted"]
\* I11 Per-task segments stay in their task: WA guidance appears only in the guidance task it belongs to.
NoCrossTaskLeak == \A j \in Judges : inputs[j]["wa_guidance"] => scen = "S4"
\* I12 Identity layout: a display name is only ever shown labelled as self-chosen, never inside the sender line
\*     that authorization reads.
IdentityLayout == \A j \in Judges : ~inputs[j]["display_name_unlabelled"]
\* I4  What executes is acceptable.
NoWrongExecution == Executed => Acceptable(scen, final)
\* I5  What executes is what passed review.
ReviewIntegrity == Executed => (final = reviewed \/ (GateDenies(scen, reviewed) /\ final = "refuse"))
\* I6  Veto continuity and re-review: a vetoed action executes only if the objection was discharged
\*     by new trusted evidence, on the record.
VetoContinuity == (Executed /\ final \in vetoed) => final \in discharged
\* I7  A refusal on a verified-ID mismatch is never turned into filing.
AuthMonotone == (scen = "S6" /\ everRefused) => final # "file"
\* I8  No depth-limit deferral while an acceptable action exists (it always does here).
NoForcedDeferral == final # "auto_defer"
\* I9  A deferral tells the WA what was contested.
DeferralInformative == (final \in {"defer", "auto_defer"}) => package
\* I13 Stubs only where content is withheld: non-ablated stages get segments in full, never as stubs.
StubsOnlyAblated == \A j \in Judges \ Ablated : \A it \in Stubs : ~inputs[j][it]
\* (StubInformed withdrawn 2026-11-18: only signed rules count, and nothing structural marks a chat rule.)
Terminates == <>(pc = "done")
=============================================================================
