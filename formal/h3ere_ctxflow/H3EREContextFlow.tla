------------------------- MODULE H3EREContextFlow -------------------------
(***************************************************************************)
(* One H3ERE thought as it SHOULD run: what context each conscience        *)
(* receives, how a veto is typed and carried through retries, and what may *)
(* execute.                                                                *)
(*                                                                         *)
(* Rules = "contract": the proposed context and decision contract.         *)
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
EXTENDS Naturals, FiniteSets, TLC, ContextData

CONSTANTS Rules, MaxDepth, PostReviewChange, VerbPassSeesVeto, ToolGate
ASSUME Rules \in {"measured", "contract"} /\ MaxDepth \in 1..6 /\ PostReviewChange \in BOOLEAN
       /\ VerbPassSeesVeto \in BOOLEAN /\ ToolGate \in BOOLEAN
\* VerbPassSeesVeto (#1366 item 1): the veto reason reaches the verb second pass (TSASPDMA), which
\*   drafts TOOL actions. FALSE = it reaches ASPDMA only, so a banned TOOL action can be re-proposed.
\* ToolGate (#1366 item 19): TaskEnvelope Phase 2 checks a deterministic, task-scoped authorization
\*   fact at ToolBus.dispatch_to_provider. In S6 the sender is not authorized to file, so a filing is
\*   denied at dispatch whatever the models decided. It covers TOOL actions only.

Scenarios == {"S1", "S2", "S3", "S4", "S5", "S6"}
\* S1 no rule in force.
\* S2 an ordinary user states a rule in their own message (own-turn preference at most).
\* S3 the WA states a rule earlier on its own channel.
\* S4 guidance task: the WA resolved a deferral, repeating the rule (signed).
\* S5 the rule landed as an approved identity amendment; another user asks.
\* S6 as S5 and ID-scoped; the asker shows the authorized person's display name.
Kinds   == {"seed", "followup"}
Judges  == {"coherence", "entropy", "epistemic", "optveto"}
Ablated == {"entropy", "optveto"}          \* input-ablated by design: no untrusted text
Untrusted == {"user_msg", "history", "display_name", "raw_ctx_via_record"}
Items == {"user_msg", "history", "display_name", "raw_ctx_via_record", "identity", "rule_visible",
          "rule_in_identity", "wa_guidance", "gov_block", "sender_id_verified"}

Options(s) == CASE s = "S1" -> {"normal"}
                [] s = "S6" -> {"refuse", "file"}
                [] OTHER    -> {"follow", "normal"}
Acceptable(s, a) == CASE s = "S1" -> a = "normal"
                      [] s = "S2" -> a \in {"follow", "normal"}  \* same-user reply: either is fine
                      [] s = "S6" -> a = "refuse"
                      [] OTHER    -> a = "follow"
TrustedRule(s) == s \in {"S3", "S4", "S5", "S6"}   \* a verified-WA rule exists in trusted state
FaceValueFine(a) == a \in {"normal", "file"}       \* looks like ordinary help to a stage without the rule
ToolActions == {"file"}                            \* drafted by the verb second pass, dispatched via ToolBus
GateDenies(s, a) == ToolGate /\ s = "S6" /\ a \in ToolActions

(* The contract: what each conscience must receive.                        *)
ContractHas(j, s, item) ==
    CASE item = "identity"           -> "always"
      [] item = "gov_block"          -> IF TrustedRule(s) THEN "always" ELSE "never"
         \* system-built: rule text + provenance (WA id, deferral/attestation/amendment ids, signature ok)
      [] item = "rule_in_identity"   -> IF s \in {"S5", "S6"} THEN "always" ELSE "never"
      [] item = "wa_guidance"        -> IF s = "S4" THEN "always" ELSE "never"
      [] item = "sender_id_verified" -> "always"   \* structured field, separate from the display name
      [] item \in {"user_msg", "history", "display_name"} -> IF j \in Ablated THEN "never" ELSE "always"
      [] item = "raw_ctx_via_record" -> "never"    \* action record is factual: no message text
      [] item = "rule_visible"       -> IF s = "S1" \/ j \in Ablated THEN "never" ELSE "always"
      [] OTHER -> "never"

Pres(j, s, k, item) == IF Rules = "contract" THEN ContractHas(j, s, item) ELSE MeasuredHas(j, s, k, item)

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

Trusted(p) == p["gov_block"] \/ p["rule_in_identity"] \/ p["wa_guidance"]
\* Does conscience j hold the evidence the decision rests on?
HasEvidence(j) ==
    LET p == inputs[j] IN
    CASE scen = "S1" -> TRUE
      [] scen = "S2" -> j \notin Ablated /\ p["rule_visible"]
      [] scen = "S6" -> (attached \/ Trusted(p)) /\ (attached \/ p["sender_id_verified"])
      [] OTHER       -> attached \/ Trusted(p) \/ (j \notin Ablated /\ p["rule_visible"])

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
    /\ IF Options(scen) \ (IF VerbPassSeesVeto THEN banned ELSE banned \ ToolActions) = {}
         THEN /\ final' = "defer" /\ package' = TRUE /\ pc' = "done" /\ UNCHANGED <<draft, everRefused>>
         ELSE /\ \E a \in Options(scen) \ (IF VerbPassSeesVeto THEN banned ELSE banned \ ToolActions) :
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
Executed == final \in {"normal", "follow", "refuse", "file"}

TypeOK == pc \in {"draft", "judge", "exec", "done"} /\ depth \in 0..MaxDepth
\* I1  The firewall: input-ablated consciences receive no untrusted text.
Ablation == \A j \in Ablated : \A it \in Untrusted : ~inputs[j][it]
\* I2  Every conscience holds trusted evidence for a verified-WA rule in force.
EvidenceSufficiency == TrustedRule(scen) => \A j \in Judges : Trusted(inputs[j])
\* I3  ID-scoped decisions: the verified sender id is a field of its own wherever a display name is shown.
VerifiedIdentity == (scen = "S6") => \A j \in Judges : inputs[j]["sender_id_verified"]
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
Terminates == <>(pc = "done")
=============================================================================
