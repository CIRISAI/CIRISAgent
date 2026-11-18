"""Compile context_policy.yaml into ContractPolicy.tla (FSD_PROMPT_CONTEXT_PROVENANCE.md §5, §5a, §11).

A closed-vocabulary compiler, not a language: every kind, provenance, trust level, lifecycle and predicate must
be one of the enums below. Before generating anything it runs the static checks of §5a and refuses on failure:
  - vocabulary: unknown names are errors;
  - firewall: an ablated stage allows no untrusted kind (except kinds marked residual) and no untrusted rule
    provenance;
  - no laundering by declaration: action_record is system trust and factual;
  - identity layout: display_name renders labelled; sender_identity carries authn;
  - only signed rules are verified provenances (decision 2026-11-18): user_chat and wa_chat must be untrusted;
  - evidence sufficiency: whenever a trusted (signed) rule is in force, every judge receives a verified rule provenance,
    an amendment or signed guidance under a predicate at least as broad;
  - completeness: every stage the model consumes is present.

Output: ContractHas(stage, scenario, kind, atom) over the model's atoms. Atoms are the (kind, provenance,
rendering) combinations the TLA+ model reasons about; kinds the model does not consume are checked but not
emitted. Usage: python3 gen_contract_policy.py context_policy.yaml ContractPolicy.tla
"""
import sys

import yaml

TRUST = {"untrusted", "verified", "system"}
LIFECYCLE = {"standing", "per-task", "per-message", "per-thought", "retry-only", "per-call"}
PREDICATES = {"always", "never", "trusted_rule_in_force", "id_scoped", "signed_guidance_in_force",
              "amendment_in_force", "advisory_rule", "retry"}
PROVENANCES = {"user_chat", "wa_chat", "signed_guidance", "amendment"}
KINDS = {"stage_instruction", "schema_instruction", "accord", "identity_base", "amendment", "rule", "wa_guidance",
         "request", "history", "sender_identity", "display_name", "action_record", "draft", "dma_output",
         "conscience_feedback", "tool_output", "pipeline_position"}
JUDGES = ["coherence", "entropy", "epistemic", "optveto"]
MODEL_STAGES = JUDGES + ["aspdma", "tsaspdma"]
# Scenario sets each predicate holds in (the model's S1..S6; FSD and README scenario table).
PRED_TLA = {
    "always": "TRUE", "never": "FALSE",
    "trusted_rule_in_force": 's \\in {"S4", "S5", "S6"}',
    "id_scoped": 's = "S6"',
    "signed_guidance_in_force": 's = "S4"',
    "amendment_in_force": 's \\in {"S5", "S6"}',
    "advisory_rule": 's \\in {"S2", "S3"}',
    "retry": "FALSE",   # retry-only kinds are not among the judges' atoms; drafters' feedback is modelled in Retry
}
PRED_SCEN = {"always": {"S1", "S2", "S3", "S4", "S5", "S6"}, "never": set(),
             "trusted_rule_in_force": {"S4", "S5", "S6"}, "id_scoped": {"S6"},
             "signed_guidance_in_force": {"S4"}, "amendment_in_force": {"S5", "S6"}, "advisory_rule": {"S2", "S3"},
             "retry": set()}


def fail(msg):
    sys.exit(f"context policy rejected: {msg}")


def main(src, out):
    P = yaml.safe_load(open(src))
    kinds, prov, stages = P["kinds"], P["rule_provenance"], P["stages"]
    ablated = set(P["ablated_stages"])
    # vocabulary
    for k, a in kinds.items():
        if k not in KINDS:
            fail(f"unknown kind {k!r}")
        if "trust" in a and a["trust"] not in TRUST:
            fail(f"{k}: unknown trust {a['trust']!r}")
        if a.get("lifecycle") not in LIFECYCLE:
            fail(f"{k}: unknown lifecycle {a.get('lifecycle')!r}")
    for pv, t in prov.items():
        if pv not in PROVENANCES or t not in TRUST:
            fail(f"rule provenance {pv!r}: {t!r}")
    for st, rows in stages.items():
        for key, pred in rows.items():
            kind, _, pv = key.partition(".")
            if kind not in kinds:
                fail(f"{st}.{key}: kind not declared")
            if pv and (kind != "rule" or pv not in prov):
                fail(f"{st}.{key}: provenance only on rule, and must be declared")
            if pred not in PREDICATES:
                fail(f"{st}.{key}: unknown predicate {pred!r}")
    # completeness
    for st in MODEL_STAGES:
        if st not in stages:
            fail(f"stage {st} missing")

    def trust_of(key):
        kind, _, pv = key.partition(".")
        return prov[pv] if pv else kinds[kind].get("trust")

    for pv in ("user_chat", "wa_chat"):
        if prov.get(pv) != "untrusted":
            fail(f"rule provenance {pv} must be untrusted: only signed rules are authoritative")
    # firewall
    for st in ablated:
        for key, pred in stages[st].items():
            if pred == "never":
                continue
            kind = key.split(".")[0]
            if trust_of(key) == "untrusted" and not kinds[kind].get("residual"):
                fail(f"firewall: ablated stage {st} allows untrusted {key}")
    # no laundering by declaration; identity layout
    if kinds["action_record"].get("trust") != "system":
        fail("action_record must be system trust (factual, no derived_from)")
    if kinds["display_name"].get("render") != "labelled":
        fail("display_name must render labelled")
    if kinds["sender_identity"].get("authn") != "required":
        fail("sender_identity must carry authn")
    # evidence sufficiency
    for st in JUDGES:
        covered = set()
        for key, pred in stages[st].items():
            if key in ("amendment", "wa_guidance") or (key.startswith("rule.") and trust_of(key) == "verified"):
                covered |= PRED_SCEN[pred]
        missing = PRED_SCEN["trusted_rule_in_force"] - covered
        if missing:
            fail(f"evidence sufficiency: judge {st} has no verified rule evidence in {sorted(missing)}")

    # atoms the model consumes
    def expr(st, keys):
        preds = [stages[st].get(k, "never") for k in keys]
        exprs = [PRED_TLA[p] for p in preds if p != "never"]
        return " \\/ ".join(f"({e})" for e in exprs) if exprs else "FALSE"

    atoms = {
        "request": ["request"], "history": ["history"], "identity_base": ["identity_base"],
        "amendment": ["amendment"], "wa_guidance": ["wa_guidance"], "sender_identity": ["sender_identity"],
        "action_record_factual": ["action_record"], "display_name_labelled": ["display_name"],
        "rule_user_chat": ["rule.user_chat"], "rule_wa_chat": ["rule.wa_chat"],
        "rule_verified": ["rule.signed_guidance", "rule.amendment"],
        # never produced under a valid policy: the checks above forbid them
        "action_record_tainted": [], "display_name_unlabelled": [],
    }
    lines = []
    for st in MODEL_STAGES:
        for atom, keys in atoms.items():
            lines.append(f'    [] <<"{st}", "{atom}">> = key -> IF {expr(st, keys)} THEN "always" ELSE "never"')
    body = "\n".join(lines).replace("    [] ", "    CASE ", 1)
    open(out, "w").write(f"""---------------------------- MODULE ContractPolicy ----------------------------
(* GENERATED by gen_contract_policy.py from {src} (policy version {P['version']}) -- do not edit.    *)
(* The policy passed the static checks: vocabulary, firewall, no laundering, identity layout,      *)
(* evidence sufficiency, completeness.                                                             *)

ContractHas(stage, s, k, atom) ==
  LET key == <<stage, atom>> IN
{body}
    [] OTHER -> "never"
=============================================================================
""")
    print(f"policy v{P['version']} passed static checks -> {out} ({len(lines)} entries)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
