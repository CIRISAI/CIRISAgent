# SECTION2 Baseline — Known bugs to verify and propose fixes

Phase: A

## Probe Results

- `accord_timestamp`: ACCORD timestamp window mismatch references | hits=3291 | exit=0 | evidence=`reports/investigation/baseline_remaining_phases_20260422_161838/evidence/section2_accord_timestamp.txt`
- `security_batch`: v2.6.2 security-fix references | hits=4 | exit=0 | evidence=`reports/investigation/baseline_remaining_phases_20260422_161838/evidence/section2_security_batch.txt`
- `broken_nav`: Known broken pages references | hits=142 | exit=0 | evidence=`reports/investigation/baseline_remaining_phases_20260422_161838/evidence/section2_broken_nav.txt`

## Baseline Interpretation

- This is a discovery baseline only (signal inventory), not a claim-level verification.
- Use the evidence files above to drive deep, line-by-line validation in follow-up passes.

## Priority

- Ship-before-June-1: convert high-hit probes into fully validated findings with file/line references.
- Ship-this-quarter: add automation to compute stable metrics and drift alerts.
