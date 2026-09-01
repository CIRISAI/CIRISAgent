"""Reproductions of field failures, each pinned to the log line it reproduces.

Every test here is `xfail(strict=True)` while the defect is live. That gives us
three things at once:

  * the failure is RECORDED, in executable form, from the receipts — not from a
    description of the receipts
  * CI stays green while the fix is designed, so the repro can land immediately
    instead of waiting on the cure
  * the moment the defect is fixed the test XPASSes, and `strict=True` turns that
    into a FAILURE — so a fix cannot land without deleting the marker, and the
    repro cannot rot into a test that passes for the wrong reason

Remove the marker in the same commit as the fix. If a test here ever passes with
its marker still on, the fix is real and undocumented; if it fails after the
marker is removed, the fix regressed.
"""
