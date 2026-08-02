"""CI gate for the CC evidence registry (CIRISAgent#911).

Runs tools/check_evidence.py so that every in-repo ``path#symbol`` in
``evidence/cc_impl.tsv`` must AST-resolve — a moved/renamed/deleted symbol is a
test failure (a spec-regression test), so a Constitution ``impl:CIRISAgent``
pointer can never silently rot.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_cc_impl_manifest_symbols_resolve() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_evidence.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "evidence/cc_impl.tsv has an unresolvable path#symbol:\n"
        + result.stdout
        + result.stderr
    )


def test_manifest_present_and_well_formed() -> None:
    manifest = ROOT / "evidence" / "cc_impl.tsv"
    assert manifest.exists(), "evidence/cc_impl.tsv is missing"
    lines = [ln for ln in manifest.read_text().splitlines() if ln and not ln.startswith("#")]
    header = lines[0].split("\t")
    assert header == ["decimal_id", "claim_id", "repo", "path#symbol", "status"]
    # Every data row has the right column count and a known status.
    #
    # The vocabulary is imported from the gate rather than restated here: this
    # test previously kept its own copy, so adding `open` to the gate left the
    # test rejecting manifests the gate accepted. Two lists that must agree are
    # one list waiting to disagree.
    sys.path.insert(0, str(ROOT / "tools"))
    from check_evidence import KNOWN_STATUSES  # noqa: PLC0415 — path set above

    for row in lines[1:]:
        cols = row.split("\t")
        assert len(cols) == 5, f"bad column count: {row!r}"
        assert cols[4] in KNOWN_STATUSES, f"unknown status {cols[4]!r} in {row!r}"
