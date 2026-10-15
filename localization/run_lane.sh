#!/usr/bin/env bash
# Run one lane of the localization pipeline for the i18n workflows.
#
# AGENT-OWNED (not vendored). Builds the command from environment variables so
# workflow inputs never get interpolated into a script body, then appends "$@"
# (e.g. --dry-run, --mode batch, --report i18n-report.json).
#
#   TARGET          accord | ui
#   LANE            translate | evaluate | repair
#   ACCORD_VERSION  accord version (TARGET=accord)
#   TM_VERSION      previous accord used as translation memory (TARGET=accord)
#   STEM            target filename stem: accord | constitution_ethics (default accord)
#   TM_STEM         filename stem of the translation-memory edition (default accord)
#   SEED_EXACT_TM   true = lines whose English is unchanged from the TM edition take
#                   its shipped translation instead of a fresh draft (default false)
#   EXTRA_TM        space-separated corpus roots (a ciris-website, CIRISClient or
#                   CIRISAgent checkout) whose translated strings become extra
#                   terminology anchors, never values (TARGET=accord; default none)
#   UNITS           space-separated accord units; empty = every unit, one at a time
#   KEYS            space-separated fnmatch patterns over flat dotted keys
#   LANGS           space-separated locale codes; empty = all 28
#   MAX_KEYS        refuse runs larger than this many key-values (accord: per unit)
set -euo pipefail
cd "$(dirname "$0")/.."
set -f  # KEYS patterns like accord.v9.* are fnmatch patterns, not shell globs

case "${TARGET:-accord}" in
  accord)
    cmd=(python3 localization/accord_localize.py
         --version "${ACCORD_VERSION:?ACCORD_VERSION is required for TARGET=accord}"
         --tm-version "${TM_VERSION:-1.2b}"
         --stem "${STEM:-accord}"
         --tm-stem "${TM_STEM:-accord}"
         --units "${UNITS:-}")
    if [ "${SEED_EXACT_TM:-false}" = "true" ]; then cmd+=(--seed-exact-tm); fi
    for d in ${EXTRA_TM:-}; do cmd+=(--extra-tm "$d"); done
    ;;
  ui)
    export LOCALIZE_TARGET=ui
    # localize.py's own CLI, with provider backoff installed (lane_backoff.py).
    cmd=(python3 localization/lane_backoff.py)
    ;;
  *)
    echo "TARGET must be accord or ui, got '${TARGET}'" >&2
    exit 2
    ;;
esac

# --mode batch appends ":batch" to rung 0, and OpenRouter serves :batch slugs
# only through its async batch API: /chat/completions answers 404, rung 0 is
# lost, and the spend report still halves every line. Refused for both targets
# (accord_localize.py refuses it too, for direct runs).
prev=""
for a in "$@"; do
  if [ "$a" = "--mode=batch" ] || { [ "$prev" = "--mode" ] && [ "$a" = "batch" ]; }; then
    echo "[refuse] --mode batch: OpenRouter :batch slugs 404 on /chat/completions. Use --mode fast." >&2
    exit 2
  fi
  prev="$a"
done

cmd+=(--lane "${LANE:?LANE is required}" --max-keys "${MAX_KEYS:-400}")
for p in ${KEYS:-}; do cmd+=(--keys "$p"); done
for l in ${LANGS:-}; do cmd+=(--lang "$l"); done

exec "${cmd[@]}" "$@"
