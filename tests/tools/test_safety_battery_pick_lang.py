"""safety-battery pick-lang pre-flight (CIRISAgent#1233).

The scheduled battery died before any capture because one truncated page of the
repo-wide artifact list killed a 35-page ``gh api --paginate``. These tests pin
the retry (including the exact truncated-body failure), the give-up path, and the
"untested first, then oldest" pick semantics carried over from the YAML.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import pytest

_PATH = Path(__file__).resolve().parents[2] / "tools" / "safety_battery_pick_lang.py"
_spec = importlib.util.spec_from_file_location("safety_battery_pick_lang", _PATH)
assert _spec and _spec.loader
spl = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = spl  # dataclasses resolve their module via sys.modules
_spec.loader.exec_module(spl)

NOW = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _art(i: int, name: str, days_ago: float, expired: bool = False) -> Dict[str, object]:
    return {"id": i, "name": name, "created_at": _iso(days_ago), "expired": expired}


def _cap(lang: str, tail: str = "mental_health-v4-qwen-2.15.0-default") -> str:
    return f"safety-battery-capture-{lang}-{tail}"


def _pages(artifacts: List[Dict[str, object]], per_page: int = spl.PER_PAGE) -> List[str]:
    chunks = [artifacts[i : i + per_page] for i in range(0, len(artifacts), per_page)] or [[]]
    if len(chunks[-1]) == per_page:
        chunks.append([])
    return [json.dumps({"total_count": len(artifacts), "artifacts": c}) for c in chunks]


class _Fetcher:
    """Serves pages; ``faults[page]`` is a list of bad responses served before the good one."""

    def __init__(self, pages: List[str], faults: Dict[int, List[object]] | None = None):
        self.pages = pages
        self.faults = {k: list(v) for k, v in (faults or {}).items()}
        self.calls: List[int] = []

    def __call__(self, page: int) -> str:
        self.calls.append(page)
        pending = self.faults.get(page)
        if pending:
            bad = pending.pop(0)
            if isinstance(bad, BaseException):
                raise bad
            return str(bad)
        return self.pages[page - 1]


def _quiet(**kw):
    return {"sleep": lambda s: None, "log": lambda m: None, **kw}


# ── retry ───────────────────────────────────────────────────────────────


def test_truncated_page_is_retried_and_scan_completes():
    arts = [_art(i, _cap(spl.ROSTER[i % len(spl.ROSTER)]), 3) for i in range(250)]
    pages = _pages(arts)
    good = pages[1]
    truncated = good[: len(good) // 2]  # "unexpected end of JSON input"
    f = _Fetcher(pages, faults={2: [truncated, truncated]})
    sleeps: List[float] = []
    out = spl.list_capture_artifacts(f, sleep=sleeps.append, log=lambda m: None)
    assert len(out) == 250
    assert f.calls == [1, 2, 2, 2, 3]
    assert sleeps == [2.0, 4.0]  # bounded exponential backoff


def test_failed_gh_call_and_missing_artifacts_key_are_retried():
    pages = _pages([_art(1, _cap("am"), 1)])
    f = _Fetcher(pages, faults={1: [RuntimeError("gh api exited 1: HTTP 502"), '{"message": "oops"}']})
    out = spl.list_capture_artifacts(f, **_quiet())
    assert [a.name for a in out] == [_cap("am")]


def test_page_failing_every_attempt_raises_not_a_partial_pick():
    pages = _pages([_art(i, _cap("am"), 1) for i in range(150)])
    f = _Fetcher(pages, faults={2: ["{trunc"] * 10})
    with pytest.raises(spl.PageFetchError, match="page 2 failed after 5 attempts"):
        spl.list_capture_artifacts(f, **_quiet())
    assert f.calls.count(2) == 5


def test_main_returns_nonzero_when_scan_fails(monkeypatch, capsys):
    monkeypatch.setattr(spl, "gh_fetch_raw", lambda repo: _Fetcher([], faults={1: ["{"] * 10}))
    monkeypatch.setattr(spl.time, "sleep", lambda s: None)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert spl.main(["--repo", "o/r"]) == 1
    assert "lang=" not in capsys.readouterr().out


def test_exact_multiple_of_per_page_reads_the_empty_terminal_page():
    arts = [_art(i, _cap("am"), 1) for i in range(spl.PER_PAGE)]
    f = _Fetcher(_pages(arts))
    assert len(spl.list_capture_artifacts(f, **_quiet())) == spl.PER_PAGE
    assert f.calls == [1, 2]


def test_filters_expired_noncapture_and_research_arm_artifacts():
    arts = [
        _art(1, _cap("am"), 1),
        _art(2, _cap("ar"), 1, expired=True),
        _art(3, "safety-battery-interpret-bn-x", 1),
        _art(4, _cap("my") + "-arm-0123456789ab", 1),
        _art(1, _cap("am"), 1),  # duplicate id across pages
    ]
    out = spl.list_capture_artifacts(_Fetcher(_pages(arts)), **_quiet())
    assert [a.name for a in out] == [_cap("am")]


# ── pick semantics ──────────────────────────────────────────────────────


def _arts(ages: Dict[str, float]) -> List[spl.Artifact]:
    return [spl.Artifact(_cap(lang), NOW - timedelta(days=d)) for lang, d in ages.items()]


def test_untested_cell_wins_in_roster_order():
    ages = {lang: 1 for lang in spl.ROSTER}
    del ages["hi"], ages["tr"]
    assert spl.pick_lang(_arts(ages), NOW) == spl.Pick("hi", "untested (no prior capture artifact)")


def test_oldest_newest_capture_wins():
    ages = {lang: 2 for lang in spl.ROSTER}
    ages["ja"] = 30
    arts = _arts(ages) + [spl.Artifact(_cap("ko"), NOW - timedelta(days=90))]  # ko also has a 2d capture
    assert spl.pick_lang(arts, NOW) == spl.Pick("ja", "oldest capture (30d old)")


def test_ties_in_whole_days_go_to_earlier_roster_entry():
    ages = {lang: 5.2 for lang in spl.ROSTER}
    ages["de"] = 5.9  # same whole-day age as everyone else
    assert spl.pick_lang(_arts(ages), NOW).lang == spl.ROSTER[0]


def test_prefix_does_not_bleed_between_langs():
    # 'am' must not be satisfied by an artifact for a lang whose code starts with 'am'.
    arts = [spl.Artifact("safety-battery-capture-amx-foo", NOW)]
    assert spl.pick_lang(arts, NOW).lang == "am"


def test_explicit_lang_skips_scan(monkeypatch, tmp_path):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(spl, "gh_fetch_raw", lambda repo: pytest.fail("must not scan"))
    assert spl.main(["--repo", "o/r", "--explicit-lang", "yo"]) == 0
    assert out.read_text() == "lang=yo\nreason=workflow_dispatch input\n"


def test_main_writes_pick_to_github_output(monkeypatch, tmp_path):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    pages = _pages([_art(1, _cap("am"), 1)])
    monkeypatch.setattr(spl, "gh_fetch_raw", lambda repo: _Fetcher(pages))
    assert spl.main(["--repo", "o/r"]) == 0
    assert out.read_text() == "lang=ar\nreason=untested (no prior capture artifact)\n"
