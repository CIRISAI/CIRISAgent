"""Publishing happens only from a pushed release tag, never from a main push.

WHY THIS EXISTS

build.yml used to publish on every push to main whenever the version was not
yet on PyPI. Commit 18c59a93 landed mid-release, and that alone published
`ciris-agent 2.16.0` plus the `v2.16.0-stable` GitHub release from an
incomplete tree. PyPI is immutable, so the real release had to ship as 2.16.1.

The rule (user ruling, 2026-10-15) is that every publishing job runs ONLY on a
pushed `refs/tags/v*-stable` and refuses unless the tag == "v" + CIRIS_VERSION.
This test enforces it across every workflow, not just build.yml. A new
publishing job gated on main, or one with no gate at all, fails here on the PR
that adds it, before it can publish anything.

A job counts as publishing if any step does one of these:
  - uploads to PyPI (twine / pypa publish action);
  - creates or uploads to a GitHub release;
  - uploads to a store (Play / TestFlight / altool / fastlane);
  - registers a build with CIRISRegistry;
  - notifies CIRISManager to deploy.

The checker is a plain function, so the negative fixtures below can show it
FAILS on a main-gated publish job. A gate that has never been seen to fail is
not trusted yet.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any, Dict, List, Union, cast

import pytest

yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
BUILD = WORKFLOWS / "build.yml"

# Text that marks a step as publishing something outside this repository's CI.
PUBLISH_MARKERS = (
    re.compile(r"twine\s+upload"),
    re.compile(r"pypa/gh-action-pypi-publish"),
    re.compile(r"softprops/action-gh-release"),
    re.compile(r"gh\s+release\s+(create|upload|edit)"),
    re.compile(r"upload-google-play|r0adkll/"),
    re.compile(r"testflight|altool|fastlane\s+(pilot|supply|deliver)", re.I),
    re.compile(r"ciris-build-sign\s+register"),
    re.compile(r"manager/v1/updates/notify"),
)

TAG_REF_CLAUSES = (
    "startsWith(github.ref, 'refs/tags/v')",
    "endsWith(github.ref, '-stable')",
)

# The jobs that exist today. If one is renamed this list goes stale and the
# test says so, rather than silently checking nothing.
KNOWN_PUBLISHERS = {"publish-wheels", "register-build", "deploy", "android-release"}


def _load(text: str) -> Dict[str, Any]:
    raw: Any = yaml.safe_load(text)
    return cast(Dict[str, Any], raw)


def _step_text(step: Dict[str, Any]) -> str:
    parts: List[str] = [str(step.get("uses", "")), str(step.get("run", ""))]
    with_ = step.get("with") or {}
    if isinstance(with_, dict):
        parts.extend(str(v) for v in with_.values())
    return "\n".join(parts)


def publishing_jobs(workflow: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for job_id, job in (workflow.get("jobs") or {}).items():
        steps = (job or {}).get("steps") or []
        if any(m.search(_step_text(s)) for s in steps for m in PUBLISH_MARKERS):
            out.append(job_id)
    return out


def _is_tag_gated(cond: Union[str, bool, None]) -> bool:
    if not isinstance(cond, str):
        return False
    c = cond.replace("${{", "").replace("}}", "")
    return all(clause in c for clause in TAG_REF_CLAUSES) and "github.event_name == 'push'" in c


def gate_violations(workflow: Dict[str, Any]) -> List[str]:
    """Every reason this workflow could publish from somewhere other than a release tag."""
    problems: List[str] = []
    jobs: Dict[str, Any] = workflow.get("jobs") or {}
    for job_id in publishing_jobs(workflow):
        job = jobs[job_id] or {}
        cond = job.get("if")
        if not _is_tag_gated(cond):
            problems.append(f"{job_id}: job-level `if:` is not gated on a pushed v*-stable tag (if={cond!r})")
        if "refs/heads/main" in str(cond):
            problems.append(f"{job_id}: job-level `if:` mentions refs/heads/main")
        for step in job.get("steps") or []:
            if "refs/heads/main" in str(step.get("if", "")):
                problems.append(f"{job_id}: step {step.get('name')!r} is gated on refs/heads/main")
        needs = job.get("needs") or []
        needs_list = [needs] if isinstance(needs, str) else list(needs)
        if "release-gate" not in needs_list:
            problems.append(f"{job_id}: does not need `release-gate` (tag == CIRIS_VERSION check)")
    return problems


# --------------------------------------------------------------------------- #
# The real workflows
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.y*ml")), ids=lambda p: p.name)
def test_no_workflow_publishes_outside_a_release_tag(path: pathlib.Path) -> None:
    workflow = _load(path.read_text(encoding="utf-8"))
    problems = gate_violations(workflow)
    assert not problems, f"{path.name} can publish without a release tag:\n  " + "\n  ".join(problems)


def test_the_known_publishers_are_still_detected() -> None:
    """The marker scan must still see the jobs that publish today. If it does
    not, the scan has gone blind and every other assertion here passes vacuously."""
    found = set(publishing_jobs(_load(BUILD.read_text(encoding="utf-8"))))
    assert KNOWN_PUBLISHERS <= found, f"publishing jobs no longer detected: {KNOWN_PUBLISHERS - found}"


def test_build_yml_runs_on_release_tags() -> None:
    """If the tag push did not trigger build.yml, the gated jobs would never run
    and nothing would be released at all."""
    workflow = _load(BUILD.read_text(encoding="utf-8"))
    raw: Any = workflow
    on = raw.get("on", raw.get(True))  # PyYAML reads bare `on` as True
    tags = ((on or {}).get("push") or {}).get("tags") or []
    assert "v*-stable" in tags, f"build.yml push.tags is {tags!r}; release tags would not trigger a build"


def test_release_gate_refuses_a_tag_that_disagrees_with_the_code() -> None:
    workflow = _load(BUILD.read_text(encoding="utf-8"))
    gate = workflow["jobs"]["release-gate"]
    assert _is_tag_gated(gate.get("if"))
    body = "\n".join(str(s.get("run", "")) for s in gate.get("steps") or [])
    assert "CIRIS_VERSION" in body and '"v$VERSION"' in body, "release-gate no longer compares the tag to CIRIS_VERSION"
    assert "exit 1" in body
    assert "merge-base --is-ancestor" in body, "release-gate no longer requires the tagged commit to be on main"


def test_release_attaches_to_the_pushed_tag() -> None:
    """The GitHub release must use the tag that triggered the run, not mint a new
    one from the version string on whatever commit happens to be building."""
    job = _load(BUILD.read_text(encoding="utf-8"))["jobs"]["android-release"]
    step = next(s for s in job["steps"] if "action-gh-release" in str(s.get("uses", "")))
    assert step["with"]["tag_name"] == "${{ github.ref_name }}"


def test_release_docker_tags_only_from_a_release_tag() -> None:
    """`:latest` is what CIRISManager deploys and `:<version>` names a release, so
    a main push must not move either one."""
    build = _load(BUILD.read_text(encoding="utf-8"))["jobs"]["build"]
    metas = [s for s in build["steps"] if "docker/metadata-action" in str(s.get("uses", ""))]
    assert metas, "no docker metadata step found in the build job"
    for step in metas:
        tags = str(step["with"]["tags"])
        assert "is_default_branch" not in tags, f"{step['name']}: release image tags still follow the default branch"
        for line in tags.splitlines():
            if "value=latest" in line or "outputs.version }}" in line:
                assert "steps.version.outputs.release == 'true'" in line, f"{step['name']}: {line.strip()}"


def test_no_matrix_in_job_level_if() -> None:
    """`matrix` is not available in a job-level `if`, and using it invalidates the file."""
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for job_id, job in (_load(path.read_text(encoding="utf-8")).get("jobs") or {}).items():
            assert "matrix." not in str((job or {}).get("if", "")), f"{path.name}:{job_id}"


# --------------------------------------------------------------------------- #
# Negative fixtures: the checker must FAIL on what it exists to forbid
# --------------------------------------------------------------------------- #

MAIN_GATED_PUBLISH = """
on:
  push:
    branches: [main]
jobs:
  release-gate:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v') && endsWith(github.ref, '-stable')
    runs-on: ubuntu-latest
    steps:
      - run: true
  publish:
    needs: [release-gate]
    if: github.ref == 'refs/heads/main' && github.repository == 'CIRISAI/CIRISAgent'
    runs-on: ubuntu-latest
    steps:
      - run: python -m twine upload dist/*.whl --skip-existing
"""

UNGATED_RELEASE = """
on: push
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: softprops/action-gh-release@v1
        with:
          tag_name: v1.0.0
"""

STEP_GATED_ON_MAIN = """
on: push
jobs:
  publish:
    needs: [release-gate]
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v') && endsWith(github.ref, '-stable')
    runs-on: ubuntu-latest
    steps:
      - name: notify
        if: github.ref == 'refs/heads/main'
        run: curl -X POST https://agents.ciris.ai/manager/v1/updates/notify
"""

TAG_GATED_BUT_NO_VERSION_CHECK = """
on: push
jobs:
  register:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v') && endsWith(github.ref, '-stable')
    runs-on: ubuntu-latest
    steps:
      - run: ciris-build-sign register --project ciris-agent
"""

PROPERLY_GATED = """
on: push
jobs:
  publish:
    needs: [release-gate, build]
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v') && endsWith(github.ref, '-stable')
    runs-on: ubuntu-latest
    steps:
      - run: python -m twine upload dist/*.whl
"""


def test_negative_main_gated_publish_job_fails() -> None:
    problems = gate_violations(_load(MAIN_GATED_PUBLISH))
    assert any("not gated on a pushed v*-stable tag" in p for p in problems), problems
    assert any("refs/heads/main" in p for p in problems), problems


def test_negative_ungated_release_job_fails() -> None:
    problems = gate_violations(_load(UNGATED_RELEASE))
    assert any(p.startswith("release:") and "not gated" in p for p in problems), problems


def test_negative_step_gated_on_main_fails() -> None:
    problems = gate_violations(_load(STEP_GATED_ON_MAIN))
    assert problems == ["publish: step 'notify' is gated on refs/heads/main"], problems


def test_negative_missing_release_gate_dependency_fails() -> None:
    problems = gate_violations(_load(TAG_GATED_BUT_NO_VERSION_CHECK))
    assert problems == ["register: does not need `release-gate` (tag == CIRIS_VERSION check)"], problems


def test_properly_gated_fixture_passes() -> None:
    assert gate_violations(_load(PROPERLY_GATED)) == []
