"""The safety evidence harvester must never read an unreadable listing as "nothing live".

The repo-wide /actions/artifacts listing began answering 200 with an empty body
once the repo held ~5,000 artifacts; the harvester read that as zero live
artifacts and the sync went green while delivering nothing. It now lists per
battery run and fails loudly when a listing cannot be read.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import harvest_safety_evidence as h  # noqa: E402


def _proc(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="boom" if returncode else "")


def _lines(*objs: dict) -> str:
    return "\n".join(json.dumps(o) for o in objs) + "\n"


def _fake_gh(responses: dict[str, subprocess.CompletedProcess]):
    def run(cmd, **_kw):
        path = cmd[2]
        for key, proc in responses.items():
            if key in path:
                return proc
        raise AssertionError(f"unexpected gh call: {path}")

    return run


def test_lists_artifacts_per_battery_run(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_gh({
        "/workflows/safety-battery.yml/runs": _proc(_lines({"id": 1}, {"id": 2})),
        "/runs/1/artifacts": _proc(_lines(
            {"id": 11, "name": "safety-battery-capture-am-x", "created_at": "t", "size": 1},
            {"id": 12, "name": "safety-battery-agent-logs-1-am", "created_at": "t", "size": 1},
        )),
        "/runs/2/artifacts": _proc(_lines(
            {"id": 21, "name": "safety-battery-interpret-am-x", "created_at": "t", "size": 1},
        )),
    }))
    assert [a["id"] for a in h.live_artifacts()] == [11, 21]


def test_never_uses_the_repo_wide_listing(monkeypatch):
    seen = []

    def run(cmd, **_kw):
        seen.append(cmd[2])
        if "/workflows/" in cmd[2]:
            return _proc(_lines({"id": 1}))
        return _proc("")

    monkeypatch.setattr(subprocess, "run", run)
    h.live_artifacts()
    assert not any(p.split("?")[0].endswith("/actions/artifacts") for p in seen)


@pytest.mark.parametrize("runs_proc", [
    _proc("", returncode=1),          # gh error ("unexpected end of JSON input")
    _proc("not json\n"),              # garbage body
    _proc(""),                        # empty body: zero runs in 95 days is a broken listing
])
def test_unreadable_run_listing_fails_the_sync(monkeypatch, tmp_path, runs_proc):
    monkeypatch.setattr(h, "DEST", tmp_path)
    monkeypatch.setattr(subprocess, "run", _fake_gh({"/workflows/safety-battery.yml/runs": runs_proc}))
    assert h.main() == 1


def test_unreadable_artifact_listing_fails_the_sync(monkeypatch, tmp_path):
    monkeypatch.setattr(h, "DEST", tmp_path)
    monkeypatch.setattr(subprocess, "run", _fake_gh({
        "/workflows/safety-battery.yml/runs": _proc(_lines({"id": 1})),
        "/runs/1/artifacts": _proc("", returncode=1),
    }))
    assert h.main() == 1


def test_runs_with_no_live_artifacts_is_a_clean_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(h, "DEST", tmp_path)
    monkeypatch.setattr(subprocess, "run", _fake_gh({
        "/workflows/safety-battery.yml/runs": _proc(_lines({"id": 1})),
        "/runs/1/artifacts": _proc(""),
    }))
    assert h.main() == 0
