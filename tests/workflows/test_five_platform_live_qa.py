"""Structural guards for the five-platform live gate.

This workflow's whole purpose is to be the one job that cannot pass vacuously, so
the properties that make it non-vacuous deserve guarding at PR time — the job
itself is nightly and runs on hardware a PR check does not have.

Each assertion below corresponds to a way this gate has already been defeated, in
this repo, inside a green build:

  * artifacts uploaded unconditionally — a failure you cannot diagnose from the
    artifact costs a re-run to learn what the first run already knew
  * fail-fast disabled — killing the matrix on first red destroys the five-way
    comparison the gallery exists to show
  * the gallery job runs on failure — the red run is the one worth looking at
  * a platform that cannot run FAILS rather than being quietly absent — v2.9.42
    published no APK exactly that way
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, List

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "five-platform-live-qa.yml"


@pytest.fixture(scope="module")
def spec() -> Dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raw() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _steps(job: Dict[str, Any]) -> List[Dict[str, Any]]:
    return job.get("steps") or []


def test_three_runner_images_cover_five_platforms(spec: Dict[str, Any]) -> None:
    """macOS pairs with iOS, Linux with Android, Windows alone."""
    include = spec["jobs"]["live-qa"]["strategy"]["matrix"]["include"]
    assert {e["os"] for e in include} == {"ubuntu-latest", "macos-14", "windows-latest"}
    covered = " ".join(e["platforms"] for e in include).split()
    assert sorted(covered) == ["android", "ios", "linux", "macos", "windows"]


def test_fail_fast_is_disabled(spec: Dict[str, Any]) -> None:
    """One red platform must not cancel the other four."""
    assert spec["jobs"]["live-qa"]["strategy"]["fail-fast"] is False


def test_artifacts_upload_even_on_failure(spec: Dict[str, Any]) -> None:
    """The failing run is the one whose logs matter."""
    uploads = [s for s in _steps(spec["jobs"]["live-qa"]) if "upload-artifact" in str(s.get("uses", ""))]
    assert uploads, "the job uploads nothing — a CI failure would be undiagnosable"
    for step in uploads:
        assert step.get("if") == "always()", f"{step.get('name', step['uses'])} does not upload on failure"


def test_log_collection_runs_on_failure(spec: Dict[str, Any]) -> None:
    collect = [s for s in _steps(spec["jobs"]["live-qa"]) if "Collect artifacts" in str(s.get("name", ""))]
    assert collect and collect[0].get("if") == "always()"


def test_command_output_is_captured_to_an_uploaded_path(spec: Dict[str, Any], raw: str) -> None:
    """CIRIS_QA_LOG_DIR must point INSIDE the uploaded artifacts directory.

    Setting it somewhere else would faithfully record everything and then throw
    it away when the runner is destroyed.
    """
    env = spec["jobs"]["live-qa"]["env"]
    assert "CIRIS_QA_LOG_DIR" in env, "bring-up command output is not being captured"
    assert "artifacts" in env["CIRIS_QA_LOG_DIR"], "command logs land outside the uploaded path"


def test_the_gallery_renders_even_when_platforms_fail(spec: Dict[str, Any]) -> None:
    gallery = spec["jobs"]["gallery"]
    assert gallery.get("if") == "always()", "a gallery that only renders on success is useless when it matters"
    assert gallery.get("needs") == "live-qa"


def test_a_platform_that_cannot_run_fails_rather_than_vanishing(raw: str) -> None:
    """THE VACUOUS-PASS GUARD.

    If the iOS app does not build, the run must go red — not skip silently and
    leave four tiles that read as five. This is the exact shape of v2.9.42
    shipping with no APK: not a red tick, an absent artifact.
    """
    assert "no simulator .app was built" in raw
    # `overall=1` on that branch is what makes the job red.
    ios_skip = raw.split("no simulator .app was built")[1][:200]
    assert "overall=1" in ios_skip, "iOS skips without failing the job"


def test_the_trace_gate_is_invoked_and_is_fatal(raw: str) -> None:
    """Reaching Interact is half the gate; traces leaving is the other half."""
    assert "assert_traces_reached_canonical.py" in raw
    assert "--require ship" not in raw, (
        "'ship' keys on envelopes_sent_total, which is blind to the replication "
        "plane (CIRISEdge#434) — the gate must require 'replication'"
    )


def test_headless_is_not_passed_to_mobile_targets(raw: str) -> None:
    """--headless controls a desktop window; an emulator has its own display."""
    assert '[ "$target" = "desktop" ] && extra="--headless"' in raw
