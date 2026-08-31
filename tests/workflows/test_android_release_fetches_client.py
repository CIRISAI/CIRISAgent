"""The APK job must fetch the CIRISClient AAR before Gradle runs.

WHY THIS EXISTS AS A TEST RATHER THAN A COMMENT

`apps/android/libs/*.aar` is gitignored on purpose: it is a ~15 MB pre-built
binary of another repository's source, which the repo-size rule excludes
("distribute via GitHub Releases and fetch on install"). A clean CI checkout
therefore has NO AAR, and Gradle cannot resolve it:

    Execution failed for task ':android:checkDebugAarMetadata'.
    > Could not find :ciris-client-0.5.194:.
      Searched in: apps/android/libs/ciris-client-0.5.194.aar

That is exactly what happened to v2.9.42: the tag published no Android APK at
all. The reason it went unnoticed is the part worth guarding — the APK is built
ONLY in the release job, so no pull-request check exercises it. A missing
artifact looks identical to a release that never had one, and the next person to
notice is whoever goes looking for the APK.

So the ordering is asserted here, where a PR does run it.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Mapping, TypedDict, cast

import pytest

yaml = pytest.importorskip("yaml")


class WorkflowStep(TypedDict, total=False):
    """One step of a GitHub Actions job — only the keys this guard reads.

    `total=False` because every key here is genuinely optional in the Actions
    schema: a step may be a `uses:` with no `run:`, and most steps carry no
    `env:`. Typing the boundary is the repo rule (no untyped dicts), and it earns
    its keep here — `yaml.safe_load` hands back `Any`, so without these a typo
    like `step["evn"]` is invisible to mypy in a file whose whole job is
    catching a mistake nobody else catches.
    """

    name: str
    run: str
    env: Dict[str, str]
    uses: str


class WorkflowJob(TypedDict, total=False):
    name: str
    steps: List[WorkflowStep]


class Workflow(TypedDict):
    jobs: Dict[str, WorkflowJob]

WORKFLOW = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "build.yml"


def _apk_job() -> WorkflowJob:
    raw: Any = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    spec = cast(Workflow, raw)
    for job in spec["jobs"].values():
        for step in job.get("steps") or []:
            if "assembleDebug" in str(step.get("run", "")):
                return job
    pytest.fail("no job in build.yml builds the Android APK — did the job move?")


def _step_index(job: WorkflowJob, needle: str) -> int:
    for i, step in enumerate(job.get("steps") or []):
        if needle in str(step.get("run", "")):
            return i
    return -1


def test_the_aar_is_fetched_before_gradle_builds() -> None:
    """Order matters: fetching after the build is the same as not fetching."""
    job = _apk_job()
    fetch = _step_index(job, "fetch_client_artifacts.py")
    build = _step_index(job, "assembleDebug")

    assert fetch != -1, (
        "the APK job never fetches the CIRISClient AAR. apps/android/libs/*.aar is "
        "gitignored, so Gradle will fail on ':android:checkDebugAarMetadata' and the "
        "release will publish no APK — silently, because only the release job builds it."
    )
    assert fetch < build, "the AAR must be fetched BEFORE assembleDebug, not after"


def test_the_fetch_step_can_authenticate() -> None:
    """The fetcher resolves the asset URL with `gh release view`, which needs a
    token on a runner even for a public repo. Without it the step fails auth and
    the build fails one step later anyway — a different error, same missing APK."""
    job = _apk_job()
    idx = _step_index(job, "fetch_client_artifacts.py")
    # NOT steps[idx] directly. _step_index returns -1 when absent, and steps[-1]
    # is the LAST step — so with no fetch step at all this asserted against an
    # unrelated step's env and passed. Caught by running it against the
    # pre-fix workflow, where it went green for entirely the wrong reason.
    assert idx != -1, "no AAR fetch step to check for a token (see the ordering test)"
    step: WorkflowStep = (job.get("steps") or [])[idx]
    env_map: Mapping[str, str] = step.get("env") or {}
    env = {k.upper() for k in env_map}

    assert env & {"GH_TOKEN", "GITHUB_TOKEN"}, (
        "the AAR fetch step passes no token; `gh release view` will fail to authenticate"
    )
