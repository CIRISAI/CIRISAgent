"""Measured context map: which context items each LLM call's prompt actually contained, by scenario and stage.

Reads raw episode logs (task ids, senders, messages, rules) and the reasoning streams (LLM_CALL prompts as sent).
Output: matrix.json + a printed table. Every cell is a fraction of calls (n shown), never inferred from code.
"""
import collections
import glob
import json
import os
import re
import sys

S = "/tmp/claude-1000/-home-emoore-RATCHET/4fdbd195-6bf1-45c9-8ffc-931540da4e4d/scratchpad"
OUT = os.path.join(S, "ctxmap", "matrix.json")

HANDLERS = ["CSDMAEvaluator", "BaseDSDMA", "EthicalPDMAEvaluator", "IDMAEvaluator", "ActionSelectionPDMAEvaluator",
            "TSASPDMA", "coherence_conscience", "entropy_conscience", "epistemic_humility_conscience",
            "optimization_veto_conscience"]
ITEMS = ["user_msg", "history", "sender_id", "sender_role", "display_name", "identity", "rule_any",
         "rule_in_identity", "wa_guidance", "actions_ran", "prior_attempt", "veto_feedback", "raw_ctx_via_record",
         "thought_as_user_msg"]


def rule_snippet(text):
    """A distinctive slice of the rule body (inside <<< >>> if present)."""
    if not text:
        return None
    m = re.search(r"<<<.*?:\s*(.*?)(>>>|$)", text, re.S)
    body = (m.group(1) if m else text).strip()
    body = re.sub(r"\s+", " ", body)
    return body[10:60] if len(body) > 70 else body[:40]


def norm(s):
    return re.sub(r"\s+", " ", s)


def load_raw(path):
    """task_id -> dict(scenario, message, sender_id, username, rule) from one raw episode log."""
    tasks, rule, prestep_rule, case = {}, None, None, None
    sends = {}
    events = [json.loads(l) for l in open(path) if l.strip()]
    for r in events:
        if r.get("event") == "start":
            case = r["case"]
            rule = rule_snippet(case.get("correction"))
        if r.get("event") == "verdict" and r.get("rule"):
            prestep_rule = rule_snippet(r.get("rule"))
    rule = prestep_rule or rule
    last_send = {}
    for r in events:
        ev = r.get("event")
        if ev == "send":
            last_send[r.get("label")] = r
        if ev == "reply" and r.get("task_id"):
            s = last_send.get(r.get("label"), {})
            tasks[r["task_id"]] = {"label": r.get("label"), "message": s.get("message") or "", "user": r.get("user")}
        if ev == "probe" and r.get("task_id") in tasks:
            tasks[r["task_id"]].update(sender_id=r.get("user_id"), username=r.get("username"),
                                       sender=r.get("sender"), phase=r.get("phase"))
        if ev == "deferral_answered" and (r.get("guidance") or {}).get("task_id"):
            g = r["guidance"]["task_id"]
            orig = tasks.get(r.get("original_task_id"), {})
            tasks[g] = {**orig, "label": (orig.get("label") or r.get("label")) + "+guidance", "guidance_task": True}
    return case, rule, tasks


def scenario_of(case, t, run_kind):
    lab = t.get("label") or ""
    if t.get("guidance_task"):
        return "S4 guidance task after WA answer"
    if run_kind == "prestep":
        if lab.startswith("default"):
            return "S1 default (no rule)"
        if lab.startswith("obey_inline"):
            return "S2 rule stated by user (same message)"
        if lab.startswith("obey_wa") and not lab.endswith("-rule"):
            return "S3 rule stated by WA (earlier message, same channel)"
        if lab.endswith("-rule"):
            return "S3r WA states the rule (the rule message itself)"
    if run_kind == "episode":
        ph = t.get("phase") or lab.split("-")[0]
        if case and case.get("kind") == "sham" and "impersonator" in lab and ph == "probe":
            return "S6 impersonator after genuine correction"
        if ph == "probe":
            return "S5 after amendment landed (other user)"
        if ph == "after_reset":
            return "S5r after amendment + restart"
        if ph == "baseline":
            return "S1 default (no rule)"
    return None


def detect(prompt_text, t, rule):
    p = norm(prompt_text)
    msgs = None
    try:
        msgs = json.loads(prompt_text)
    except ValueError:
        pass
    probe_text = norm(t.get("message") or "")
    # the probe question is the last paragraph of the sent message (obey_inline prefixes the rule)
    q = probe_text.split("--- ")[-1].strip()[:45] if probe_text else ""
    ident_msgs = [norm(m["content"]) for m in (msgs or []) if isinstance(m.get("content"), str)
                  and "CORE IDENTITY" in m["content"]]
    name = t.get("username") or ""
    sender = t.get("sender") or ""
    shown = sender[1:] if sender.startswith(("~", "@")) else name
    return {
        "user_msg": bool(q) and q in p,
        "history": "CONVERSATION HISTORY" in p,
        "sender_id": bool(t.get("sender_id")) and t["sender_id"] in p,
        "sender_role": bool(re.search(r"role: (OBSERVER|ADMIN|AUTHORITY|SYSTEM_ADMIN)", p)),
        "display_name": bool(shown) and ("@" + shown) in p,
        "identity": "CORE IDENTITY" in p,
        "rule_any": bool(rule) and norm(rule) in p,
        "rule_in_identity": bool(rule) and any(norm(rule) in m for m in ident_msgs),
        "wa_guidance": "Wise Authority: I confirm this instruction" in p or "Approved by the Wise Authority" in p,
        "actions_ran": "Actions that ran in this task:" in p,
        "prior_attempt": "I attempted to" in p,
        "veto_feedback": "CONSCIENCE OVERRIDE GUIDANCE" in p,
        "raw_ctx_via_record": "Actions that ran in this task:" in p and "PREVIOUS CONTEXT" in p,
        # CIRISAgent#1366 item 18: with ConscienceCheckContext.task None, coherence / epistemic humility label the
        # follow-up thought's text "User message"; a real observation there starts "You observed".
        "thought_as_user_msg": bool(re.search(r"User message:\s*(?!You observed)\S", p)),
    }


def stage_of(e, seen_aspdma):
    h = e.get("handler_name") or ""
    th = str(e.get("thought_id") or "")
    kind = "seed" if "_seed_" in th else "followup"
    if h == "ActionSelectionPDMAEvaluator":
        seen_aspdma[th] = seen_aspdma.get(th, 0) + 1
    retry = seen_aspdma.get(th, 0) >= 2
    hn = h
    if h == "ActionSelectionPDMAEvaluator" and str(e.get("response_model", "")).startswith("TSASPDMA"):
        hn = "TSASPDMA"
    if "TSASPDMA" in str(e.get("response_model", "")) or "ToolSelection" in str(e.get("response_model", "")):
        hn = "TSASPDMA"
    return hn, kind, retry


def main():
    sources = [
        ("prestep", f"{S}/m4_pre_44150719651"), ("prestep", f"{S}/m4_pre_44150738031"),
        ("prestep", f"{S}/m4_r_44208916740"), ("prestep", f"{S}/m4_r_44208929326"),
        ("prestep", f"{S}/m4_r_44219599913"), ("prestep", f"{S}/m4_r_44219609447"),
        ("episode", f"{S}/m4_tag4"), ("episode", f"{S}/m4_contam"), ("episode", f"{S}/m4_imp221"),
    ]
    cells = collections.defaultdict(lambda: collections.Counter())
    counts = collections.Counter()
    handlers_seen = collections.Counter()
    for kind, root in sources:
        for raw in glob.glob(f"{root}/m4-raw-*/*.jsonl"):
            cid = os.path.basename(raw)[:-6]
            streams = glob.glob(f"{root}/m4-agent-logs-{cid}/qa_reports/correction_episodes/*stream*/reasoning_stream.jsonl")
            if not streams:
                continue
            case, rule, tasks = load_raw(raw)
            seen = {}
            for line in open(streams[0]):
                if '"llm_call"' not in line:
                    continue
                e = json.loads(line)
                t = tasks.get(e.get("task_id"))
                if not t:
                    continue
                sc = scenario_of(case, t, kind)
                if not sc:
                    continue
                h, tk, retry = stage_of(e, seen)
                handlers_seen[(h, str(e.get("response_model")))] += 1
                if h not in HANDLERS:
                    continue
                key = (sc, tk + ("+retry" if retry else ""), h)
                counts[key] += 1
                for it, v in detect(str(e.get("prompt")), t, rule).items():
                    if v:
                        cells[key][it] += 1
    rows = []
    for key in sorted(counts):
        n = counts[key]
        rows.append({"scenario": key[0], "thought": key[1], "handler": key[2], "n": n,
                     **{it: round(cells[key][it] / n, 2) for it in ITEMS}})
    json.dump({"items": ITEMS, "rows": rows, "handlers_seen": {f"{a}|{b}": c for (a, b), c in handlers_seen.items()}},
              open(OUT, "w"), indent=1)
    print(len(rows), "rows;", sum(counts.values()), "calls")
    for (a, b), c in sorted(handlers_seen.items(), key=lambda x: -x[1])[:20]:
        print(f"  {a:34} {b:30} {c}")


if __name__ == "__main__":
    main()
