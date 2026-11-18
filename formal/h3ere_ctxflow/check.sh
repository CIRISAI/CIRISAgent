#!/usr/bin/env bash
# Check every invariant separately under each configuration. Needs TLA2TOOLS=/path/to/tla2tools.jar (Java 11+).
set -u
cd "$(dirname "$0")"
: "${TLA2TOOLS:?set TLA2TOOLS to tla2tools.jar}"
INVS="TypeOK Ablation EvidenceSufficiency VerifiedIdentity NoWrongExecution ReviewIntegrity VetoContinuity AuthMonotone NoForcedDeferral DeferralInformative"
for cfg in ${CFGS:-contract measured contract_postreview contract_noverbveto contract_postreview_gate measured_gate}; do
  for inv in $INVS Terminates; do
    W=$(mktemp -d); cp H3EREContextFlow.tla ContextData.tla "$W/"; cp "$cfg.cfg" "$W/c.cfg"
    if [ "$inv" = Terminates ]; then echo "PROPERTY Terminates" >> "$W/c.cfg"; else echo "INVARIANT $inv" >> "$W/c.cfg"; fi
    out=$(cd "$W" && java -XX:+UseParallelGC -cp "$TLA2TOOLS" tlc2.TLC -config c.cfg -workers 2 H3EREContextFlow.tla 2>&1)
    if echo "$out" | grep -q "No error has been found"; then r=holds
    elif echo "$out" | grep -q "is violated\|Temporal properties were violated"; then r=VIOLATED
    else r="ERROR"; echo "$out" | tail -15; fi
    n=$(echo "$out" | grep -o '[0-9]* distinct states found' | tail -1)
    printf '%-20s %-22s %-9s %s\n' "$cfg" "$inv" "$r" "$n"
    [ "${VERBOSE:-0}" = 1 ] && [ "$r" = VIOLATED ] && echo "$out" | sed -n '/is violated/,/distinct states/p' | head -60
    rm -rf "$W"
  done
done
