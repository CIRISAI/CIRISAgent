#!/usr/bin/env python3
"""Say which layer broke when a five-platform leg fails, and why.

WHY THIS EXISTS. On 2026-09-04 a gate run failed on three legs and the logs
said, in full: "windows interact failed", "ios: no [DELIVERY-PROBE] lines",
"none of the given log paths exist". Reconstructing what actually happened took
a dozen queries and produced two WRONG conclusions on the way -- first that the
release's targetSdk bump had broken Android, then that the client bump had. The
truth needed a control run.

Every fact needed to tell those apart was already on the runner. A gate that
knows a thing and does not say it is making its user guess, and the guess is
what costs the hours. So: on any leg failure, classify the layer, name the
evidence, and put a row in the job summary.

THE LAYERS, in the order they can break:

  INFRA    the app or server never came up; there are no logs to read
  CLIENT   the UI did not reach the state the driver waited for
  WIRE     the LLM provider refused: no credit, bad key, rate limit, no model
  AGENT    the agent ran and errored: DMA failure, conscience, traceback
  SILENT   the agent ran, did not error, and produced no reply anyway
  DELIVERY traces did not reach the rung the run required

WIRE vs AGENT vs SILENT is the distinction that matters most and the one the
gate never drew. "The agent did not answer" is the same sentence whether the
provider is out of credit or a DMA threw, and those have opposite owners.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

# (layer, regex, what it means). First match wins, so order is significance,
# not alphabet: a provider refusal explains a silent agent, never the reverse.
# THE HARNESS TALKS TOO. The driver prints advice ("check the agent log for DMA
# errors") and the workflow echoes its own commented source; both contain the
# words we match on. Classifying those produced a confident, wrong AGENT verdict
# on the very first test -- the same mistake a human makes reading the raw log.
# Strip the harness's own voice before looking for the product's.
# THE PRODUCT HAS ITS OWN VOCABULARY, and it collides with ours. The wallet
# adapter's provider is literally named "x402" and speaks the x402 payment
# protocol, so its perfectly healthy INIT lines contain "402" and "payment
# required" -- which the first live run classified as the LLM provider refusing
# to serve us, while the budget probe in the same breath reported $88 available.
# A line about the wallet is never evidence about the model wire.
NOT_THE_LLM = re.compile(r"wallet|x402|WALLET_INIT|credit_gate|agent_credits", re.IGNORECASE)

ADVICE = re.compile(
    r"check the (llm|agent)|see the agent log|a gate that cannot find|"
    r"must fail, not pass quietly|#\s|echo \"|::(group|endgroup|warning)::",
    re.IGNORECASE,
)


def strip_advice(blob: str) -> str:
    """Remove the harness's own voice AND the product's payment vocabulary.

    Both produced confident wrong verdicts on their first contact with a real
    run, for the same reason: the words we match on appear in text that is not
    about what we are diagnosing.
    """
    return "\n".join(
        l for l in blob.splitlines() if not ADVICE.search(l) and not NOT_THE_LLM.search(l)
    )


SIGNATURES: list[tuple[str, str, str]] = [
    ("WIRE", r"Key limit exceeded|insufficient[_ ]credits|quota exceeded", "provider refused: account limit or credit exhausted"),
    ("WIRE", r"\b402\b|payment required", "provider refused: payment required"),
    ("WIRE", r"\b429\b|rate.?limit", "provider refused: rate limited"),
    ("WIRE", r"\b401\b.*(openrouter|provider|llm)|invalid[_ ]api[_ ]key|unauthorized.*llm", "provider refused: key rejected"),
    ("WIRE", r"model_not_available|model not found|\b404\b.*model", "provider refused: model name not served"),
    ("WIRE", r"(connection|read) timed out.*(openrouter|api\.|llm)|provider.*unreachable", "provider unreachable"),
    ("AGENT", r"(ERROR|CRITICAL)\b[^\n]*\bDMA\b|\b\w*DMA\w*(Evaluator)?\b[^\n]*\b(raised|failed:|exception|ValidationError)", "a DMA errored"),
    ("AGENT", r"(ERROR|CRITICAL)\b[^\n]*conscience|conscience[^\n]*(raised|failed:|exception)", "a conscience errored"),
    ("AGENT", r"Traceback \(most recent call last\)", "unhandled exception in the agent"),
    ("INFRA", r"none of the given log paths exist", "no logs were produced: the app or server never started"),
    ("INFRA", r"Address already in use|EADDRINUSE", "port already held"),
    ("INFRA", r"no simulator \.app was built", "the iOS app was never built"),
    ("CLIENT", r"element .*not found|no element with testTag|wait_for.*timed out|tagged but not dr", "the UI never reached the awaited state"),
    ("DELIVERY", r"no \[DELIVERY-PROBE\] lines|highest rung reached", "traces did not reach the required rung"),
    ("SILENT", r"message_type=='agent' row|agent did not answer|no reply", "the agent produced no reply and logged no error"),
]

PHASE_DEFAULT = {
    "setup": ("CLIENT", "the setup wizard did not complete"),
    "login": ("CLIENT", "login did not complete"),
    "interact": ("SILENT", "no reply was rendered"),
    "delivery": ("DELIVERY", "trace delivery did not reach the required rung"),
    "identity": ("AGENT", "the one-holder-per-identity invariant broke"),
}


def read_logs(paths: list[str], cap: int = 400_000) -> str:
    """Whatever exists, tail-biased: failures are at the end."""
    out: list[str] = []
    for p in paths:
        path = pathlib.Path(p)
        for f in ([path] if path.is_file() else sorted(path.rglob("*.log")) + sorted(path.rglob("*.txt")) if path.is_dir() else []):
            try:
                out.append(f"--- {f} ---\n" + f.read_text(errors="replace")[-cap:])
            except OSError:
                continue
    return "\n".join(out)


def probe_provider() -> tuple[str, str] | None:
    """Ask the provider what it thinks of our key. NEVER prints the key.

    This is the single most valuable fact when a run goes silent, and it is one
    HTTP call: an exhausted budget and a broken DMA look identical from the
    agent's side, and they have different owners.
    """
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return ("WIRE?", "no OPENROUTER_API_KEY in this job -- cannot check the budget")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r).get("data", {})
    except urllib.error.HTTPError as e:
        return ("WIRE", f"provider rejected the key check: HTTP {e.code}")
    except Exception as e:  # noqa: BLE001 - a probe must never mask the real failure
        return ("WIRE?", f"could not reach the provider to check the budget: {type(e).__name__}")
    rem, lim, use = d.get("limit_remaining"), d.get("limit"), d.get("usage")
    if rem is not None and isinstance(rem, (int, float)) and rem <= 0:
        return ("WIRE", f"BUDGET EXHAUSTED: limit_remaining={rem} of limit={lim} (usage={use})")
    return (None, f"provider budget OK: limit_remaining={rem} of limit={lim} (usage={use})")


def classify(blob: str, phase: str) -> tuple[str, str, str]:
    for layer, pat, meaning in SIGNATURES:
        m = re.search(pat, blob, re.IGNORECASE)
        if m:
            line = next((l.strip() for l in blob.splitlines() if m.group(0).lower() in l.lower()), m.group(0))
            return layer, meaning, line[:300]
    layer, meaning = PHASE_DEFAULT.get(phase, ("UNKNOWN", "no known signature matched"))
    return layer, meaning, "(no matching line in the collected logs)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True)
    ap.add_argument("--phase", required=True)
    ap.add_argument("--logs", nargs="*", default=[])
    ap.add_argument("--summary", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    ap.add_argument("--probe-provider", action="store_true", help="ask the LLM provider about our budget")
    a = ap.parse_args()

    blob = strip_advice(read_logs(a.logs))
    layer, meaning, evidence = classify(blob, a.phase)

    probe_note = ""
    if a.probe_provider and layer in ("SILENT", "AGENT", "UNKNOWN", "DELIVERY"):
        # Only when the agent's own behaviour is in question. A CLIENT or INFRA
        # failure is not the provider's fault and the call would be noise.
        p = probe_provider()
        if p:
            override, probe_note = p
            if override:
                layer, meaning = override, probe_note

    # THE PROBE VETOES A CREDIT VERDICT. If some line made this look like a
    # billing refusal but the provider says the budget is intact, the line was
    # not about the model wire -- report the doubt rather than a false cause.
    if layer == "WIRE" and ("credit" in meaning or "payment" in meaning):
        v = probe_provider()
        if v and v[0] is None:
            layer = "UNKNOWN"
            meaning = f"a payment-shaped line matched, but {v[1]} -- not a billing refusal"
            probe_note = v[1]

    head = f"{a.platform}/{a.phase}: {layer} -- {meaning}"
    print(f"::error::{head}")
    print(f"::group::DIAGNOSIS {a.platform}/{a.phase}")
    print(f"  layer:    {layer}")
    print(f"  meaning:  {meaning}")
    print(f"  evidence: {evidence}")
    if probe_note:
        print(f"  provider: {probe_note}")
    print(f"  logs read: {len(blob)} bytes from {len(a.logs)} path(s)")
    if not blob:
        print("  NOTE: no logs were readable at all -- that is itself the finding (see INFRA).")
    print("::endgroup::")

    if a.summary:
        try:
            with open(a.summary, "a", encoding="utf-8") as fh:
                fh.write(f"| {a.platform} | {a.phase} | **{layer}** | {meaning} | `{evidence[:120]}` |\n")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
