"""Shard coverage must be UNIONED, not concatenated.

CIRISAgent#1116: the combine step used to parse the 8 per-shard Cobertura XMLs
and append their ``<package>`` elements into one tree. That produced a
``coverage.xml`` holding 8 entries per file — one per shard, each with only that
shard's hits — and nothing ever OR'd the per-line counts. Sonar resolved the
duplicate keys to a single arbitrary shard, so lines covered by tests that
happened to land in a different shard were reported UNCOVERED.

Measured on run 32784489152: ``edge_runtime.py`` lines 314-316 and 330 were
covered by shards 1-6 and scored as uncovered, and the PR's ``new_coverage``
came out at 14.6% against an 80% gate.

The failure was silent — a wrong number looks exactly like a real one — so the
contract is pinned here rather than left to review.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "build.yml"


def _combine_step_script() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in workflow["jobs"].values():
        for step in job.get("steps") or []:
            if isinstance(step, dict) and step.get("name") == "Combine coverage reports":
                return step.get("run", "")
    pytest.fail("no 'Combine coverage reports' step found in build.yml")


def test_combine_uses_coverage_combine() -> None:
    """`coverage combine` is the only thing that unions line hits — and the
    only thing that can merge branch/arc data at all."""
    assert "coverage combine" in _combine_step_script()


def test_combine_does_not_concatenate_xml() -> None:
    """The exact defect: appending <package> elements instead of merging."""
    script = _combine_step_script()
    assert "findall('.//package')" not in script
    assert "append(pkg)" not in script


def test_shards_emit_raw_coverage_data() -> None:
    """`coverage combine` needs the raw data files; a per-shard XML report
    cannot be unioned after the fact."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "COVERAGE_FILE=coverage-data-shard-" in text
    assert "--cov-report=xml:coverage-shard-" not in text


def test_shard_data_files_are_not_hidden() -> None:
    """A dot-prefixed name would be silently skipped by upload-artifact unless
    include-hidden-files is set — losing the data the fix depends on."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "COVERAGE_FILE=.coverage" not in text


def test_a_missing_shard_is_reported() -> None:
    """A silently absent shard understates coverage exactly the way the old
    merge did, so it has to be said out loud."""
    script = _combine_step_script()
    assert "::warning" in script or "::error" in script
