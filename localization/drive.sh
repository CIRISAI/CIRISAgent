#!/usr/bin/env bash
# Drive a localization lane to completion, banking work between attempts.
#
# The ladder itself is never bypassed or shortened: escalation to
# the top rungs is the design, not a cost bug. What this driver adds is what
# happens AROUND a run:
#   - retries with backoff, because the write path banks accepted values per
#     language, so a 402 (auto-top-up lag) or a killed process loses nothing;
#   - after the final attempt, anything still unresolved or judge-rejected is
#     collected into localization/hard-cases/<timestamp>.json for CLAUDE'S
#     JUDGMENT (a human or an agent reading the file). The playbook, in order:
#       1. Change the ENGLISH source to be less ambiguous or less idiomatic,
#          then re-run — most failures are the source's fault.
#       2. Hand-translate with real research (dictionaries, native corpora)
#          only when the source is already unambiguous.
#     Never resolve a hard case by weakening the reviewer or skipping rungs.
#
# Usage:
#   LANE=translate|evaluate [BUNDLE=dictionaries|chrome] [KEYS="pat.* pat2.*"] [LANGS="yo am"]
#   [MAX_KEYS=500] [ATTEMPTS=8] [BACKOFF=180] localization/drive.sh
set -u
cd "$(dirname "$0")/.."
LANE="${LANE:-translate}"
export LOCALIZE_BUNDLE="${BUNDLE:-dictionaries}"
MAX_KEYS="${MAX_KEYS:-500}"
ATTEMPTS="${ATTEMPTS:-8}"
BACKOFF="${BACKOFF:-180}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="localization/hard-cases"
mkdir -p "$OUT"

if [ -z "${OPENROUTER_API_KEY:-}" ] && [ -f "$HOME/.openrouter_key" ]; then
  export OPENROUTER_API_KEY="$(tr -d '\n\r\t ' < "$HOME/.openrouter_key")"
fi

keyargs=()
for p in ${KEYS:-}; do keyargs+=(--keys "$p"); done
for l in ${LANGS:-}; do keyargs+=(--lang "$l"); done

last_report=""
for attempt in $(seq 1 "$ATTEMPTS"); do
  if [ "$LANE" = "translate" ] && [ -z "${KEYS:-}" ]; then
    if python3 localization/localize.py --check 2>&1 | grep -q 'all languages at parity'; then
      echo "DONE after $((attempt-1)) attempt(s): all languages at parity"
      exit 0
    fi
  fi
  echo "=== attempt $attempt/$ATTEMPTS ($LANE lane, $LOCALIZE_BUNDLE bundle) ==="
  last_report="$OUT/run-$STAMP-a$attempt.json"
  python3 localization/localize.py --lane "$LANE" "${keyargs[@]}" \
    --max-keys "$MAX_KEYS" --report "$last_report" 2>&1 | tail -20
  # ${PIPESTATUS[0]}, NOT $?. In a pipeline `$?` is the LAST command's status,
  # so this read `tail`'s -- and tail exits 0 whatever it was fed. Every refusal,
  # every crash and every 402 therefore reported "lane clean", and the retry loop
  # underneath has never once fired.
  #
  # It was found the only way a silent false green ever is: by noticing the work
  # had not happened. `--keys 'chat.*'` refused with "616 > --max-keys 500",
  # translated nothing, and this said DONE.
  #
  # Same shape as the PyPI publish gate whose retries were dead code under
  # `bash -e` (packaging, 0.5.19x): a status that was never the one being tested.
  rc=${PIPESTATUS[0]}
  if [ "$rc" = "0" ]; then
    echo "DONE after $attempt attempt(s): lane clean"
    exit 0
  fi
  echo "--- lane exit $rc; backing off ${BACKOFF}s (402 lag, transient rungs) ---"
  sleep "$BACKOFF"
done

# The attempts are spent: distill what resisted into a hard-cases file.
python3 - "$last_report" "$OUT/hard-cases-$STAMP.json" <<'PY'
import json, sys
report, out = sys.argv[1], sys.argv[2]
try:
    r = json.load(open(report))
except Exception:
    r = {}
cases = []
for lang, d in sorted(r.items()):
    for k, why in (d.get("unresolved") or {}).items():
        cases.append({"lang": lang, "key": k, "kind": "ladder_exhausted", "why": why})
    for k, why in (d.get("rejected_unrepaired") or {}).items():
        cases.append({"lang": lang, "key": k, "kind": "judge_rejected", "why": why,
                      "findings": (d.get("findings") or {}).get(k, [])})
doc = {
    "instructions": (
        "Hard cases for Claude's judgment. Preferred fix: clarify the ENGLISH "
        "source (less ambiguous, less idiomatic) and re-run the lane. Second: "
        "hand-translate with real research. Never bypass the ladder or soften "
        "the reviewer."
    ),
    "cases": cases,
}
json.dump(doc, open(out, "w"), indent=2, ensure_ascii=False)
print(f"wrote {len(cases)} hard case(s) to {out}")
PY
echo "ATTEMPTS EXHAUSTED — hard cases filed for adjudication"
exit 1
