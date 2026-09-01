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


def test_the_trace_gate_still_runs_and_still_asks_for_replication(raw: str) -> None:
    """Reaching Interact is half the gate; traces leaving is the other half.

    Enforcement is currently OFF: the `replication` rung sits on the
    KEX/replication path upstream is rebuilding, so it cannot pass for reasons
    no change here can fix, and holding five platforms red on someone else's
    in-flight work trains everyone to ignore the colour.

    What must NOT drift while it is off:
      * it still runs (a check nobody executes rots silently)
      * it still asks for `replication`, never `ship` — 'ship' keys on
        envelopes_sent_total, which is blind to the replication plane
        (CIRISEdge#434); softening the RUNG rather than the ENFORCEMENT would
        quietly redefine what "delivered" means
      * the run still SAYS so — an unenforced check that is also invisible is a
        vacuous pass with extra steps
    """
    assert "assert_traces_reached_canonical.py" in raw
    assert "--require replication" in raw
    assert "--require ship" not in raw, (
        "'ship' keys on envelopes_sent_total, which is blind to the replication "
        "plane (CIRISEdge#434) — the gate must require 'replication'"
    )
    trace_branch = raw.split("python tools/dev/assert_traces_reached_canonical.py")[1][:600]
    assert "::warning::" in trace_branch, "the non-enforced result is not surfaced at all"
    assert "NOT enforced" in trace_branch, "the log does not say enforcement is off"


def test_the_interact_gate_is_still_fatal(raw: str) -> None:
    """Whatever happens to the trace rung, silence on screen must stay fatal.

    This is the half of the gate that is entirely ours, so it has no excuse to
    be downgraded alongside the half that is not.
    """
    chat = raw.split("web_ui desktop-chat")[1][:700]
    assert "overall=1" in chat and "interact failed" in chat


def test_chat_authenticates_for_the_history_assertion(raw: str) -> None:
    """desktop-chat reads /v1/agent/history, so it needs credentials.

    Without them the command defaults to `admin`, which this workflow never
    creates, and every platform fails with 401 raised by the GATE rather than by
    the product — a red run that says nothing about the app.
    """
    chat = raw.split("web_ui desktop-chat")[1][:700]
    assert "--username" in chat and "--password" in chat


def test_headless_is_not_passed_to_mobile_targets(raw: str) -> None:
    """--headless controls a desktop window; an emulator has its own display."""
    assert '[ "$target" = "desktop" ] && extra="--headless"' in raw


def test_log_collection_cannot_outlive_the_job(raw: str) -> None:
    """A collect step must never hang.

    `command -v adb` succeeds on GitHub's macOS runners — they ship the Android
    SDK — and with no device attached adb blocks starting its server. That hung
    the macos-ios collect step for over an hour, burned the job timeout, and
    blocked upload-artifact behind it, so the failure it was collecting for could
    not be diagnosed at all.

    Two independent guards, because either alone is thin: only run it on the
    runner that actually owns Android, and cap it regardless.
    """
    assert "MATRIX_PLATFORMS" in raw, "logcat is not gated on the runner owning android"
    logcat = [ln for ln in raw.splitlines() if "adb logcat" in ln]
    assert logcat, "no logcat collection at all"
    for line in logcat:
        assert "timeout " in line, f"adb logcat is not time-capped: {line.strip()}"


def test_each_platform_starts_from_a_clean_host(raw: str) -> None:
    """One runner walks two platforms; the second must not inherit the first.

    macos-ios runs macOS then iOS on one host. With macOS's backend still on
    :8080 and its test server on :9091, the iOS app cannot bind and every probe
    lands on the still-running macOS stack — scoring a second desktop
    interaction as the iOS result. A false green on the platform least likely to
    be checked by eye.
    """
    assert "teardown: killing" in raw, "no per-platform teardown"
    teardown = raw.split("TEAR DOWN THE PREVIOUS PLATFORM FIRST")[1][:700]
    for port in ("8080", "9091"):
        assert port in teardown, f"teardown does not clear :{port}"


def test_the_trace_rung_has_three_outcomes(raw: str) -> None:
    """Unknown must not be recorded as delivered.

    Exit 3 (CIRISServer#518: no replication counter on this substrate) once ran
    the success branch, so chat-*.json said "traces": true and the gallery
    claimed delivery for a run whose own output said NOT COVERED.
    """
    assert "trace_status" in raw
    assert "traces_json=null" in raw, "the unobservable case is not recorded distinctly"
    assert "traces_json=true" in raw and "traces_json=false" in raw


def test_android_provisioning_asserts_the_avd_exists(raw: str) -> None:
    """Installing the emulator is not the same as having an AVD.

    The first version checked `test -x emulator`, then ran `-list-avds` without
    reading the result — so an empty list passed as success and reappeared two
    steps later as "no AVDs configured", a message about bring-up for a fault in
    provisioning. A check whose output nobody reads is not a check.
    """
    step = raw.split("Install the Android emulator")[1][:2000]
    assert 'grep -qx "ciris_qa"' in step, "the AVD list is not actually asserted"
    assert "ANDROID_AVD_HOME" in step, "the AVD home is left to inference"


def test_both_steps_agree_on_the_avd_home(raw: str) -> None:
    """avdmanager and the emulator resolve the AVD list independently.

    They agreed only by luck before, and stopped agreeing on the runner: the AVD
    was created somewhere the emulator did not look.
    """
    assert raw.count('export ANDROID_AVD_HOME="$HOME/.android/avd"') == 2
