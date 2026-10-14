"""Structural guards for the sharded i18n lane (.github/workflows/i18n-lane.yml).

The lane runs N locale shards in parallel and one collector. What keeps that
safe is structural, so it is guarded at PR time -- the lane itself is dispatch
only and spends tokens:

  * a shard NEVER commits or pushes: read-only token, no persisted
    credentials, no git write anywhere in its steps. collect is the one writer.
  * fail-fast is off: one fail-closed shard must not cancel the others' work.
  * collect runs on a failed shard (always()), and commits only once, only
    after the gate over the combined tree.
  * `matrix` never appears in a job-level `if` (it invalidates the file).
  * inputs reach shells through env: no ${{ }} inside a run body, and each body
    stays far below the 21000-character expression cap.
  * the callers keep the one-writer-per-ref concurrency group and stay under
    the 25-input dispatch cap.
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Any, Dict, List

import pytest

yaml = pytest.importorskip("yaml")

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
LANE = WORKFLOWS / "i18n-lane.yml"
CALLERS = [WORKFLOWS / f"i18n-{name}.yml" for name in ("translate", "evaluate", "repair")]

sys.path.insert(0, str(REPO / "localization"))

import lane_shards as LS  # noqa: E402

GIT_WRITE = re.compile(r"\bgit\s+(commit|push|add|tag|merge|rebase|pull)\b|\bgh\s+(pr|api|release)\b")


def _load(path: pathlib.Path) -> Dict[str, Any]:
    doc: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc


def _on(doc: Dict[str, Any]) -> Dict[str, Any]:
    on: Dict[str, Any] = doc.get("on", doc.get(True))  # PyYAML reads `on:` as True
    return on


def _steps(job: Dict[str, Any]) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = job.get("steps", [])
    return steps


@pytest.fixture(scope="module")
def lane() -> Dict[str, Any]:
    return _load(LANE)


def test_three_jobs_plan_shard_collect(lane: Dict[str, Any]) -> None:
    assert set(lane["jobs"]) == {"plan", "shard", "collect"}
    assert lane["jobs"]["shard"]["needs"] == "plan"
    assert set(lane["jobs"]["collect"]["needs"]) == {"plan", "shard"}


def test_the_shard_job_never_commits_or_pushes(lane: Dict[str, Any]) -> None:
    shard = lane["jobs"]["shard"]
    assert shard["permissions"] == {"contents": "read"}
    for step in _steps(shard):
        assert not GIT_WRITE.search(step.get("run", "")), step.get("name")
        if str(step.get("uses", "")).startswith("actions/checkout"):
            assert step["with"]["persist-credentials"] is False
    # and it never reaches for the push token by name
    assert "GITHUB_TOKEN" not in yaml.safe_dump(shard)


def test_the_plan_job_never_writes_either(lane: Dict[str, Any]) -> None:
    plan = lane["jobs"]["plan"]
    assert plan["permissions"] == {"contents": "read"}
    assert not any(GIT_WRITE.search(s.get("run", "")) for s in _steps(plan))


def test_collect_is_the_only_writer_and_commits_once(lane: Dict[str, Any]) -> None:
    writers = [
        (name, step.get("name"))
        for name, job in lane["jobs"].items()
        for step in _steps(job)
        if re.search(r"\bgit\s+(commit|push)\b", step.get("run", ""))
    ]
    assert writers == [("collect", "Commit")]
    collect = lane["jobs"]["collect"]
    assert collect["permissions"] == {"contents": "write"}
    commit = next(s for s in _steps(collect) if s.get("name") == "Commit")
    assert commit["run"].count("git commit") == 1
    # banks accepted work even when a shard failed, but never past a failed gate
    assert "always()" in commit["if"]
    assert "steps.gate.outcome == 'success'" in commit["if"]
    assert "inputs.commit" in commit["if"]


def test_collect_runs_when_a_shard_fails(lane: Dict[str, Any]) -> None:
    collect = lane["jobs"]["collect"]
    assert "always()" in collect["if"]
    assert "needs.plan.result == 'success'" in collect["if"]
    names = [s.get("name") for s in _steps(collect)]
    # collect (refusal) before the gate, the gate before the commit
    assert (
        names.index("Collect -- each shard's own locales, nothing else")
        < names.index("Gate -- the pipeline proposes, this decides")
        < names.index("Commit")
    )
    gate = next(s for s in _steps(collect) if s.get("id") == "gate")
    assert gate["if"] == "always()"
    assert "check_localize_vendoring.py" in gate["run"]
    assert "accord_localize.py" in gate["run"]
    assert "--verify" in gate["run"]
    run = next(s for s in _steps(collect) if s.get("id") == "collect")["run"]
    assert "lane_shards.py collect" in run


def test_shards_download_outside_the_checkout(lane: Dict[str, Any]) -> None:
    dl = next(s for s in _steps(lane["jobs"]["collect"]) if "download-artifact" in str(s.get("uses", "")))
    assert dl["with"]["pattern"] == f"{LS.ARTIFACT_PREFIX}*"
    assert dl["with"]["path"].startswith("${{ runner.temp }}")


def test_fail_fast_off_and_matrix_from_plan(lane: Dict[str, Any]) -> None:
    strategy = lane["jobs"]["shard"]["strategy"]
    assert strategy["fail-fast"] is False
    assert strategy["matrix"] == "${{ fromJSON(needs.plan.outputs.matrix) }}"
    assert lane["jobs"]["shard"]["env"]["LANGS"] == "${{ matrix.langs }}"


def test_each_shard_uploads_its_files_even_on_failure(lane: Dict[str, Any]) -> None:
    steps = _steps(lane["jobs"]["shard"])
    pack = next(s for s in steps if "lane_shards.py pack" in s.get("run", ""))
    upload = next(s for s in steps if "upload-artifact" in str(s.get("uses", "")))
    assert pack["if"] == "always()"
    assert upload["if"] == "always()"
    assert upload["with"]["name"] == LS.ARTIFACT_PREFIX + "${{ matrix.shard }}"


def test_matrix_never_in_a_job_level_if(lane: Dict[str, Any]) -> None:
    for name, job in lane["jobs"].items():
        assert "matrix" not in str(job.get("if", "")), name


@pytest.mark.parametrize("path", [LANE, *CALLERS], ids=lambda p: p.name)
def test_run_bodies_take_inputs_through_env(path: pathlib.Path) -> None:
    for job in _load(path).get("jobs", {}).values():
        for step in _steps(job):
            body = step.get("run", "")
            assert "${{" not in body, step.get("name")
            assert len(body) < 21000 // 2, step.get("name")


def test_the_lane_takes_a_shards_input_defaulting_to_seven() -> None:
    inputs = _on(_load(LANE))["workflow_call"]["inputs"]
    assert inputs["shards"]["default"] == str(LS.DEFAULT_SHARDS) == "7"


@pytest.mark.parametrize("path", CALLERS, ids=lambda p: p.name)
def test_callers_pass_shards_keep_the_writer_queue_and_input_cap(path: pathlib.Path) -> None:
    doc = _load(path)
    inputs = _on(doc)["workflow_dispatch"]["inputs"]
    assert "shards" in inputs
    assert inputs["shards"]["default"] == "7"
    assert len(inputs) <= 25 - 2, "leave headroom under GitHub's 25-input dispatch cap"
    assert doc["concurrency"] == {"group": "i18n-write-${{ github.ref }}", "cancel-in-progress": False}
    (job,) = doc["jobs"].values()
    assert job["uses"] == "./.github/workflows/i18n-lane.yml"
    assert job["with"]["shards"] == "${{ inputs.shards }}"


# ─────────────────────────────────────────────────────────────────────────────
# The assignment the workflow uses
# ─────────────────────────────────────────────────────────────────────────────


def test_default_layout_is_seven_disjoint_shards_of_four_covering_all_28() -> None:
    every = LS.lane_languages()
    assert len(every) == 28
    assert "en" not in every
    layout = LS.assign([], LS.DEFAULT_SHARDS)
    assert [len(s) for s in layout] == [4] * 7
    flat = [lang for s in layout for lang in s]
    assert len(flat) == len(set(flat)) == 28
    assert set(flat) == set(every)


@pytest.mark.parametrize("n", range(1, 29))
def test_any_shard_count_is_disjoint_and_complete(n: int) -> None:
    layout = LS.assign([], n)
    flat = [lang for s in layout for lang in s]
    assert len(flat) == len(set(flat)) == 28
    assert len(layout) == n
    assert max(map(len, layout)) - min(map(len, layout)) <= 1
    # owned files are disjoint too: no two shards may write the same path
    for target in ("ui", "accord"):
        owned = [p for s in layout for p in LS.owned_files(target, s, version="1.3", stem="constitution_ethics")]
        assert len(owned) == len(set(owned))


# ─────────────────────────────────────────────────────────────────────────────
# Extra translation memory (#1273): pinned once, identical in every shard
# ─────────────────────────────────────────────────────────────────────────────

EXTRA_TM_REPOS = {"CIRISAI/ciris-website": "extra_tm_website", "CIRISAI/CIRISClient": "extra_tm_client"}


def _extra_tm_checkouts(job: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        s["with"]["repository"]: s
        for s in _steps(job)
        if str(s.get("uses", "")).startswith("actions/checkout") and s.get("with", {}).get("repository")
    }


def test_plan_resolves_the_extra_tm_shas_once_and_exports_them(lane: Dict[str, Any]) -> None:
    plan = lane["jobs"]["plan"]
    resolve = next(s for s in _steps(plan) if s.get("id") == "extra_tm")
    assert "ls-remote" in resolve["run"]
    assert plan["outputs"]["extra_tm_website"] == "${{ steps.extra_tm.outputs.website }}"
    assert plan["outputs"]["extra_tm_client"] == "${{ steps.extra_tm.outputs.client }}"
    assert "extra_tm_provenance" in plan["outputs"]
    # the plan's own dry-run anchors on the same pins
    co = _extra_tm_checkouts(plan)
    assert co["CIRISAI/ciris-website"]["with"]["ref"] == "${{ steps.extra_tm.outputs.website }}"
    assert co["CIRISAI/CIRISClient"]["with"]["ref"] == "${{ steps.extra_tm.outputs.client }}"


def test_every_shard_checks_out_the_identical_extra_tm_shas(lane: Dict[str, Any]) -> None:
    """Shards never resolve a default branch themselves: the ref of every extra-TM
    checkout in the shard job is plan's output, one value for the whole matrix --
    not a matrix value, not an ls-remote of their own."""
    shard = lane["jobs"]["shard"]
    assert not any("ls-remote" in s.get("run", "") for s in _steps(shard))
    co = _extra_tm_checkouts(shard)
    assert set(co) == set(EXTRA_TM_REPOS)
    for repo, output in EXTRA_TM_REPOS.items():
        ref = co[repo]["with"]["ref"]
        assert ref == "${{ needs.plan.outputs." + output + " }}", ref
        assert co[repo]["with"]["persist-credentials"] is False
    verify = next(s for s in _steps(shard) if s.get("name") == "Extra translation memory -- verify the pin")
    assert verify["env"] == {
        "WEBSITE_SHA": "${{ needs.plan.outputs.extra_tm_website }}",
        "CLIENT_SHA": "${{ needs.plan.outputs.extra_tm_client }}",
    }
    assert "rev-parse HEAD" in verify["run"]
    assert "EXTRA_TM=" in verify["run"]
    names = [s.get("name") for s in _steps(shard)]
    assert names.index("Extra translation memory -- verify the pin") < names.index(
        "Run the lane (this shard's locales only)"
    )


def test_collect_records_the_extra_tm_provenance_in_the_commit(lane: Dict[str, Any]) -> None:
    commit = next(s for s in _steps(lane["jobs"]["collect"]) if s.get("name") == "Commit")
    assert commit["env"]["EXTRA_TM_PROVENANCE"] == "${{ needs.plan.outputs.extra_tm_provenance }}"
    assert "${EXTRA_TM_PROVENANCE:-none}" in commit["run"]
