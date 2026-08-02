#!/usr/bin/env bash
# Capture signed CEG traces from a live model run.
#
#   PROVIDER=openrouter API_KEY=sk-... MODEL=meta-llama/llama-4-scout \
#     ./tools/research/capture_traces.sh
#
# Everything is an env var with a sane default; the only required one is API_KEY.
# Run it directly on a dev box, or via docker/docker-compose.research.yml to get
# an isolated database and port (recommended when sharing a machine).
#
# WHAT YOU GET, per sealed trace, at three detail levels:
#   $OUT_DIR/<backend>/default/ceg-seal-<trace_id>.json          generic
#   $OUT_DIR/<backend>/accord_detailed/ceg-seal-<trace_id>.json  + actionable lists
#   $OUT_DIR/<backend>/accord_full/ceg-seal-<trace_id>.json      + raw prompts/completions
#
# Each file is the CEG carrier AS IT WOULD SHIP: the full federation_attestations
# row, all 22 columns, including scrub_signature_classical / scrub_signature_pqc
# / original_content_hash. Byte columns are hex-encoded as {"__hex__": "..."}.
# Written on SEAL, so an unreachable canonical does not cost you the corpus.
set -euo pipefail

PROVIDER="${PROVIDER:-openrouter}"
MODEL="${MODEL:-meta-llama/llama-4-scout}"
LANGUAGES="${LANGUAGES:-en}"
CONCURRENCY="${CONCURRENCY:-1}"
QUESTIONS_FILE="${QUESTIONS_FILE:-}"
OUT_DIR="${OUT_DIR:-/out}"
BASE_URL="${BASE_URL:-}"
API_KEY="${API_KEY:-}"
API_KEY_FILE="${API_KEY_FILE:-}"
# Research-bound prompt overrides. Path to a manifest INSIDE the container
# (mount it read-only, e.g. -v ./manifests:/manifests:ro then
# OVERRIDES=/manifests/arm-b.json). Reaching the prompts any other way — bind-
# mounting over a YAML, editing the image — bypasses the audited facility, so
# the run carries no record of having been manipulated. That reproduces the
# condition-self-report problem in a new place, which is self-defeating when the
# thing you are testing IS the override path.
OVERRIDES="${OVERRIDES:-}"

# Provider -> default base URL. Override with BASE_URL for anything else.
case "$PROVIDER" in
  openrouter) BASE_URL="${BASE_URL:-https://openrouter.ai/api/v1}" ;;
  together)   BASE_URL="${BASE_URL:-https://api.together.xyz/v1}" ;;
  groq)       BASE_URL="${BASE_URL:-https://api.groq.com/openai/v1}" ;;
  openai)     BASE_URL="${BASE_URL:-https://api.openai.com/v1}" ;;
  deepinfra)  BASE_URL="${BASE_URL:-https://api.deepinfra.com/v1/openai}" ;;
  *)
    if [ -z "$BASE_URL" ]; then
      echo "ERROR: unknown PROVIDER='$PROVIDER' and no BASE_URL set." >&2
      echo "       known: openrouter together groq openai deepinfra" >&2
      exit 2
    fi ;;
esac

if [ -z "$API_KEY" ] && [ -n "$API_KEY_FILE" ] && [ -f "$API_KEY_FILE" ]; then
  API_KEY="$(tr -d '\n\r' < "$API_KEY_FILE")"
fi
if [ -z "$API_KEY" ]; then
  echo "ERROR: no API key. Set API_KEY=... or API_KEY_FILE=/path/to/key" >&2
  exit 2
fi

KEYFILE="$(mktemp)"; trap 'rm -f "$KEYFILE"' EXIT
printf '%s' "$API_KEY" > "$KEYFILE"

# OVERRIDES FIRST — before preflight, because this check is free and local
# while preflight spends a real provider call. A manifest the agent will refuse
# should never reach the provider's billing.
if [ -n "$OVERRIDES" ]; then
  if [ ! -f "$OVERRIDES" ]; then
    echo "ERROR: OVERRIDES=$OVERRIDES not found in the container." >&2
    echo "       Mount it read-only, e.g.  -v \$PWD/manifests:/manifests:ro" >&2
    exit 5
  fi
  # Two keys by design: one says WHAT to apply, the other says you are ALLOWED
  # to. A single key would let a stray line in a production .env swap the
  # covenant out of a live agent.
  export CIRIS_RESEARCH_PROMPT_OVERRIDES="$OVERRIDES"
  export CIRIS_TESTING_MODE=true
  echo "── overrides ─────────────────────────────────────────────"
  echo "  manifest : $OVERRIDES"
  # Validate with the loader the AGENT uses, not a JSON-parses check.
  #
  # The agent's refusal at startup is correct and is not softened here — this
  # asks the same question earlier, of the same loader, and stops on the same
  # answer. A JSON-valid manifest missing residue_digest, or a strict one
  # omitting keys, used to survive this point and die minutes later inside the
  # run, surfacing as "Server failed to start" with the cause in a console tail
  # (#962, #963). Failing here costs ~8s and the message names the remedy.
  if ! python3 -m ciris_engine.logic.utils.research_overrides validate "$OVERRIDES"; then
    echo "  -> manifest refused. The agent would not have started on it." >&2
    exit 5
  fi
fi

# PREFLIGHT — fail in seconds on a bad key/model rather than after a full run.
# A 401 and a 402 both present as "no output"; one is a bad key, the other a
# valid key on an unfunded account, and they need different fixes.
echo "── preflight ─────────────────────────────────────────────"
code=$(curl -s -o /tmp/pf.json -w '%{http_code}' --max-time 45 \
  -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' \
  -H 'User-Agent: ciris-research-capture/1.0' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":1}" \
  "$BASE_URL/chat/completions" || echo 000)
if [ "$code" != "200" ]; then
  echo "  FAIL: HTTP $code from $PROVIDER"
  echo "  base_url : $BASE_URL"
  echo "  model    : $MODEL"
  echo "  says     : $(head -c 300 /tmp/pf.json 2>/dev/null)"
  case "$code" in
    401) echo "  -> key invalid or revoked." ;;
    402) echo "  -> key VALID, account out of credit. Billing, not config." ;;
    403) echo "  -> access denied for this model (tier/enablement)." ;;
    404) echo "  -> model not found. Check CASE — provider ids are case-sensitive." ;;
    429) echo "  -> rate limited." ;;
    000) echo "  -> endpoint unreachable (DNS/TLS/network)." ;;
  esac
  exit 3
fi
echo "  OK: $PROVIDER / $MODEL"

mkdir -p "$OUT_DIR"
export CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR="$OUT_DIR"
# The ceg-seal-*.json carriers ARE the product of this script, and only this
# script asks for them. The tee reads the live persist DB through a second
# SQLite handle, which is unsafe alongside the Rust writer on a WAL database
# (it took the staged-QA sqlite leg down), so it is off by default and opted
# into here rather than riding along on LOCAL_COPY_DIR.
export CIRIS_ACCORD_METRICS_CEG_SEAL_TEE="true"

BEFORE=$(find "$OUT_DIR" -name 'ceg-seal-*.json' 2>/dev/null | wc -l)

ARGS=(model_eval --live --live-key-file "$KEYFILE" --live-model "$MODEL"
      --live-base-url "$BASE_URL" --live-provider openai
      --model-eval-languages "$LANGUAGES" --model-eval-concurrency "$CONCURRENCY" --verbose)
[ -n "$QUESTIONS_FILE" ] && ARGS+=(--model-eval-questions-file "$QUESTIONS_FILE")

echo "── run ───────────────────────────────────────────────────"
echo "  languages=$LANGUAGES concurrency=$CONCURRENCY out=$OUT_DIR"
set +e
python3 -u -m tools.qa_runner "${ARGS[@]}"
RC=$?
set -e

AFTER=$(find "$OUT_DIR" -name 'ceg-seal-*.json' 2>/dev/null | wc -l)
NEW=$((AFTER - BEFORE))
SIGNED=$(grep -l '"scrub_signature_pqc"' $(find "$OUT_DIR" -name 'ceg-seal-*.json' 2>/dev/null) 2>/dev/null | wc -l)

echo "── result ────────────────────────────────────────────────"
echo "  qa_runner exit : $RC"
echo "  new traces     : $NEW"
echo "  PQC-signed     : $SIGNED"

# HARD FAIL ON AN EMPTY CORPUS.
#
# A run that evaluates cleanly and captures nothing is the failure mode this
# harness exists to prevent: it reported "Success Rate 100.0%" while writing
# zero trace files, and anything downstream would then compute over an empty set
# and call it a clean result. A capture run with no captures is a failed run.
if [ "$NEW" -eq 0 ]; then
  echo "  FAIL: the run produced NO trace files."
  echo "        Check the adapter log for 'Local-copy' / 'CEG seal' lines — every"
  echo "        path logs its verdict, including why it wrote nothing."
  exit 4
fi
if [ "$SIGNED" -eq 0 ]; then
  echo "  WARN: no PQC signatures present — not mesh-importable as-is."
fi
echo "  traces in $OUT_DIR"
exit $RC
