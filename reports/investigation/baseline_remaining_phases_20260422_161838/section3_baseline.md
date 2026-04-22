# SECTION3 Baseline — Security surface for external audit / bounty scoping

Phase: B

## Probe Results

- `auth_surface`: Authentication and identity surface | hits=4273 | exit=0 | evidence=`reports/investigation/baseline_remaining_phases_20260422_161838/evidence/section3_auth_surface.txt`
- `pq_keys`: Ed25519 + ML-DSA-65 key handling | hits=226 | exit=0 | evidence=`reports/investigation/baseline_remaining_phases_20260422_161838/evidence/section3_pq_keys.txt`
- `kill_switch`: Kill switch paths | hits=60 | exit=0 | evidence=`reports/investigation/baseline_remaining_phases_20260422_161838/evidence/section3_kill_switch.txt`

## Baseline Interpretation

- This is a discovery baseline only (signal inventory), not a claim-level verification.
- Use the evidence files above to drive deep, line-by-line validation in follow-up passes.

## Priority

- Ship-before-June-1: convert high-hit probes into fully validated findings with file/line references.
- Ship-this-quarter: add automation to compute stable metrics and drift alerts.
