# SECTION5 Baseline — Lean 4 formal verification

Phase: C

## Probe Results

- `lean_files`: Lean theorem files | hits=0 | exit=1 | evidence=`reports/investigation/baseline_remaining_phases_20260422_161838/evidence/section5_lean_files.txt`
- `consistent_lie`: CONSISTENT-LIE references | hits=5833 | exit=0 | evidence=`reports/investigation/baseline_remaining_phases_20260422_161838/evidence/section5_consistent_lie.txt`

## Baseline Interpretation

- This is a discovery baseline only (signal inventory), not a claim-level verification.
- Use the evidence files above to drive deep, line-by-line validation in follow-up passes.

## Priority

- Ship-before-June-1: convert high-hit probes into fully validated findings with file/line references.
- Ship-this-quarter: add automation to compute stable metrics and drift alerts.
