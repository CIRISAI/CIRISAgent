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
         --units "${UNITS:-}")
    ;;
  ui)
    export LOCALIZE_TARGET=ui
    cmd=(python3 localization/localize.py)
    ;;
  *)
    echo "TARGET must be accord or ui, got '${TARGET}'" >&2
    exit 2
    ;;
esac

cmd+=(--lane "${LANE:?LANE is required}" --max-keys "${MAX_KEYS:-400}")
for p in ${KEYS:-}; do cmd+=(--keys "$p"); done
for l in ${LANGS:-}; do cmd+=(--lang "$l"); done

exec "${cmd[@]}" "$@"
