"""The shard bookkeeping behind the sharded i18n lane, and its rate-limit backoff.

Offline: no model is called. Every refusal has a positive twin.
"""

from __future__ import annotations

import importlib
import io
import json
import random
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest

REPO = Path(__file__).resolve().parents[2]
LOCALIZATION = REPO / "localization"
sys.path.insert(0, str(LOCALIZATION))

import lane_backoff as LB  # noqa: E402
import lane_shards as LS  # noqa: E402

VERSION, STEM = "1.3", "constitution_ethics"


# ─────────────────────────────────────────────────────────────────────────────
# Assignment
# ─────────────────────────────────────────────────────────────────────────────


def test_assignment_is_deterministic_and_round_robin() -> None:
    known = ["am", "ar", "de", "es", "fr"]
    assert LS.assign([], 2, known=known) == [["am", "de", "fr"], ["ar", "es"]]
    first, again = LS.assign([], 2, known=known), LS.assign([], 2, known=known)
    assert first == again


def test_requested_langs_only_and_no_empty_shards() -> None:
    assert LS.assign(["yo", "am", "yo"], 7) == [["yo"], ["am"]]


def test_unknown_language_and_bad_shard_counts_are_refused() -> None:
    with pytest.raises(SystemExit, match="xx"):
        LS.assign(["xx"], 7)
    with pytest.raises(SystemExit, match="en"):
        LS.assign(["en"], 7)  # English is the source, never a target
    for bad in ("0", "29", "seven"):
        with pytest.raises(SystemExit):
            LS.parse_shards(bad)
    assert LS.parse_shards("") == LS.DEFAULT_SHARDS


def test_matrix_shape() -> None:
    m = LS.matrix([["am", "ha"], ["yo"]])
    assert m == {"include": [{"shard": "0", "langs": "am ha"}, {"shard": "1", "langs": "yo"}]}


def test_owned_files_are_a_closed_per_locale_list() -> None:
    assert LS.owned_files("ui", ["am"]) == ["ciris_engine/data/localized/am.json"]
    assert LS.owned_files("accord", ["am"], version=VERSION, stem=STEM) == [
        "localization/accord/constitution_ethics_1.3/am.json",
        "ciris_engine/data/localized/constitution_ethics_1.3_am.txt",
    ]
    assert LS.owned_files("accord", ["yo"], version="1.3", stem="accord") == [
        "localization/accord/1.3/yo.json",
        "ciris_engine/data/localized/accord_1.3_yo.txt",
    ]
    for bad in ("../x", "en", "AM"):
        with pytest.raises(SystemExit):
            LS.owned_files("ui", [bad])
    with pytest.raises(SystemExit):
        LS.owned_files("accord", ["am"], version="../1.3", stem=STEM)


# ─────────────────────────────────────────────────────────────────────────────
# Spend
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def localize_ui(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    for var in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "LOCALIZE_PROVIDER", "LOCALIZE_LADDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LOCALIZE_TARGET", "ui")
    for name in ("localize", "check_localization_sync", "glossary"):
        sys.modules.pop(name, None)
    yield importlib.import_module("localize")
    for name in ("localize", "check_localization_sync", "glossary"):
        sys.modules.pop(name, None)


def test_spend_is_parsed_from_the_vendored_report_format(localize_ui: Any) -> None:
    """Parses what ``Spend.report`` really prints, summed across units."""
    L = localize_ui
    spend = L.Spend()
    model = next(iter(L.PRICE))
    spend.add(model, L.Reply("x", 1_000_000, 100_000, 5_000))
    one = spend.report()
    log = f"=== unit a ===\nspend (estimate)\n{one}\n=== unit b ===\n{one}\n"
    got = LS.parse_spend(log)
    single = float(one.rsplit("$", 1)[1])
    assert single > 0
    assert got["total_usd"] == pytest.approx(2 * single)
    assert got["models"][model]["input_tokens"] == 2_000_000
    assert got["models"][model]["cache_read"] == 10_000
    assert got["models"][model]["output_tokens"] == 200_000


# ─────────────────────────────────────────────────────────────────────────────
# Pack and collect
# ─────────────────────────────────────────────────────────────────────────────

SPEND_LOG = "  m/x: 1,000 in (0 cache-read) / 10 out ~ $0.2500\n  total ~ $0.2500\n"


def _report(langs: List[str]) -> Dict[str, Any]:
    return {"section0": {lang: {"keys": 1, "rejected_unrepaired": {}} for lang in langs}}


def _make_shard(tmp: Path, shard: str, langs: List[str], rc: int = 0, *, extra: Dict[str, str] | None = None) -> Path:
    """A shard checkout that wrote its own files AND a neighbour's, then packed."""
    work = tmp / f"work{shard}"
    for rel in LS.owned_files("accord", langs, version=VERSION, stem=STEM):
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(f"shard {shard} {rel}\n", encoding="utf-8")
    # the stage seeds every locale, so a shard's tree touches files it does not own
    neighbour = work / "ciris_engine/data/localized/constitution_ethics_1.3_zz.txt"
    neighbour.parent.mkdir(parents=True, exist_ok=True)
    neighbour.write_text("not mine\n", encoding="utf-8")
    (work / "i18n-report.json").write_text(json.dumps(_report(langs)), encoding="utf-8")
    (work / "lane.log").write_text(SPEND_LOG, encoding="utf-8")
    out = tmp / "shards" / f"{LS.ARTIFACT_PREFIX}{shard}"
    meta = LS.pack(
        target="accord",
        version=VERSION,
        stem=STEM,
        shard=shard,
        langs=langs,
        rc=rc,
        out=out,
        root=work,
        report=work / "i18n-report.json",
        log=work / "lane.log",
    )
    assert "constitution_ethics_1.3_zz.txt" not in json.dumps(meta)
    for rel, text in (extra or {}).items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(text, encoding="utf-8")
    return out


def _collect(tmp: Path, layout: List[List[str]]) -> tuple[Dict[str, Any], List[str], Path]:
    root = tmp / "checkout"
    root.mkdir(exist_ok=True)
    report, failures = LS.collect(
        target="accord", version=VERSION, stem=STEM, layout=layout, source=tmp / "shards", root=root, log=lambda _: None
    )
    return report, failures, root


def test_pack_takes_only_the_shards_own_locales(tmp_path: Path) -> None:
    out = _make_shard(tmp_path, "0", ["am", "ha"])
    files = sorted(p.relative_to(out / LS.FILES_DIR).as_posix() for p in (out / LS.FILES_DIR).rglob("*") if p.is_file())
    assert files == sorted(LS.owned_files("accord", ["am", "ha"], version=VERSION, stem=STEM))
    assert json.loads((out / LS.SHARD_META).read_text())["rc"] == 0


def test_clean_shards_are_collected_merged_and_spend_summed(tmp_path: Path) -> None:
    layout = [["am", "ha"], ["yo"]]
    _make_shard(tmp_path, "0", layout[0])
    _make_shard(tmp_path, "1", layout[1])
    report, failures, root = _collect(tmp_path, layout)
    assert failures == []
    assert set(report["section0"]) == {"am", "ha", "yo"}
    assert report["_lane"]["spend"]["total_usd"] == pytest.approx(0.5)
    assert report["_lane"]["spend"]["models"]["m/x"]["input_tokens"] == 2000
    for rel in LS.owned_files("accord", ["am", "ha", "yo"], version=VERSION, stem=STEM):
        assert (root / rel).is_file()
    assert not (root / "ciris_engine/data/localized/constitution_ethics_1.3_zz.txt").exists()


def test_collect_refuses_a_shard_carrying_a_foreign_locale_file(tmp_path: Path) -> None:
    layout = [["am"], ["yo"]]
    _make_shard(tmp_path, "0", layout[0])
    # shard 1 smuggles shard 0's locale (and would overwrite it)
    foreign = LS.FILES_DIR + "/ciris_engine/data/localized/constitution_ethics_1.3_am.txt"
    _make_shard(tmp_path, "1", layout[1], extra={foreign: "overwrite am\n"})
    report, failures, root = _collect(tmp_path, layout)
    assert any("shard 1 REFUSED" in f and "constitution_ethics_1.3_am.txt" in f for f in failures), failures
    # refused WHOLE: none of shard 1's files land, not even its own
    assert not (root / "ciris_engine/data/localized/constitution_ethics_1.3_yo.txt").exists()
    assert "yo" not in report.get("section0", {})
    # the honest shard still lands, untouched by the smuggled copy
    am = root / "ciris_engine/data/localized/constitution_ethics_1.3_am.txt"
    assert am.read_text(encoding="utf-8").startswith("shard 0")
    assert [r["status"] for r in report["_lane"]["shards"]] == ["ok", "refused"]


def test_collect_refuses_files_outside_the_locale_tree(tmp_path: Path) -> None:
    layout = [["am"]]
    _make_shard(tmp_path, "0", layout[0], extra={LS.FILES_DIR + "/.github/workflows/x.yml": "on: push\n"})
    _, failures, root = _collect(tmp_path, layout)
    assert any("REFUSED" in f and "x.yml" in f for f in failures)
    assert not (root / ".github").exists()


def test_collect_refuses_unexpected_top_level_files_and_report_locales(tmp_path: Path) -> None:
    _make_shard(tmp_path, "0", ["am"], extra={"payload.sh": "rm -rf /\n"})
    _, failures, _ = _collect(tmp_path, [["am"]])
    assert any("payload.sh" in f for f in failures)

    tmp2 = tmp_path / "b"
    out = _make_shard(tmp2, "0", ["am"])
    (out / LS.SHARD_REPORT).write_text(json.dumps(_report(["am", "yo"])), encoding="utf-8")
    _, failures, _ = _collect(tmp2, [["am"]])
    assert any("REFUSED" in f and "'yo'" in f for f in failures)


def test_collect_refuses_a_shard_that_claims_other_locales(tmp_path: Path) -> None:
    _make_shard(tmp_path, "0", ["am", "yo"])  # the run's assignment says shard 0 is am only
    _, failures, root = _collect(tmp_path, [["am"], ["yo"]])
    assert any("shard 0 REFUSED" in f and "assignment" in f for f in failures)
    assert any("shard 1" in f and "no artifact" in f for f in failures)
    assert not any(root.rglob("*.txt"))


def test_collect_refuses_symlinks(tmp_path: Path) -> None:
    out = _make_shard(tmp_path, "0", ["am"])
    target = out / LS.FILES_DIR / "ciris_engine/data/localized/constitution_ethics_1.3_am.txt"
    target.unlink()
    target.symlink_to("/etc/passwd")
    _, failures, _ = _collect(tmp_path, [["am"]])
    assert any("symlink" in f for f in failures)


def test_a_failed_shard_is_banked_and_still_fails_the_run(tmp_path: Path) -> None:
    """Fail-closed, as the single-job lane: accepted values committed, run red."""
    layout = [["am"], ["yo"]]
    _make_shard(tmp_path, "0", layout[0], rc=1)
    _make_shard(tmp_path, "1", layout[1])
    report, failures, root = _collect(tmp_path, layout)
    assert len(failures) == 1
    assert "shard 0" in failures[0]
    assert "exited 1" in failures[0]
    assert (root / "ciris_engine/data/localized/constitution_ethics_1.3_am.txt").is_file()
    assert [r["status"] for r in report["_lane"]["shards"]] == ["failed", "ok"]


def test_a_shard_whose_lane_step_died_counts_as_failed(tmp_path: Path) -> None:
    assert LS.parse_rc("") == -1
    assert LS.parse_rc("0") == 0
    _make_shard(tmp_path, "0", ["am"], rc=LS.parse_rc(""))
    _, failures, _ = _collect(tmp_path, [["am"]])
    assert failures
    assert "exited -1" in failures[0]


def test_the_collect_cli_writes_the_report_and_exits_on_failure(tmp_path: Path) -> None:
    """No artifacts at all (every shard died): exit 1, report says missing, nothing copied."""
    out = tmp_path / "merged.json"
    before = sorted(REPO.glob("ciris_engine/data/localized/constitution_ethics_1.3_*.txt"))
    argv = ["collect", "--target", "accord", "--version", VERSION, "--stem", STEM, "--shards", "2"]
    argv += ["--langs", "am yo", "--from", str(tmp_path / "nowhere"), "--report", str(out)]
    assert LS.main(argv) == 1
    assert [r["status"] for r in json.loads(out.read_text())["_lane"]["shards"]] == ["missing", "missing"]
    assert sorted(REPO.glob("ciris_engine/data/localized/constitution_ethics_1.3_*.txt")) == before


# ─────────────────────────────────────────────────────────────────────────────
# Rate-limit backoff (adapter around the vendored call_model)
# ─────────────────────────────────────────────────────────────────────────────


def _http(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://openrouter.ai", code, "x", headers, io.BytesIO(b""))


class Flaky:
    def __init__(self, errors: List[BaseException]) -> None:
        self.errors = list(errors)
        self.calls = 0

    def __call__(self, model: str, *a: Any, **k: Any) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def _wrap(fn: Any, sleeps: List[float], **kw: Any) -> Any:
    return LB.with_backoff(fn, base=10, cap=100, sleep=sleeps.append, rng=random.Random(0), log=lambda _: None, **kw)


@pytest.mark.parametrize("code", [429, 402, 503, 529])
def test_transient_statuses_are_retried_in_place(code: int) -> None:
    sleeps: List[float] = []
    fn = Flaky([_http(code)])
    assert _wrap(fn, sleeps, attempts=6)("m") == "ok"
    assert fn.calls == 2
    assert len(sleeps) == 1
    assert 7.5 <= sleeps[0] <= 12.5


def test_backoff_grows_and_is_capped() -> None:
    sleeps: List[float] = []
    fn = Flaky([_http(429)] * 5)
    assert _wrap(fn, sleeps, attempts=6)("m") == "ok"
    assert sleeps[1] > sleeps[0]
    assert max(sleeps) <= 100


def test_retries_run_out_and_the_original_error_reaches_the_vendored_code() -> None:
    sleeps: List[float] = []
    err = _http(429)
    fn = Flaky([err] * 10)
    wrapped = _wrap(fn, sleeps, attempts=3)
    with pytest.raises(urllib.error.HTTPError) as caught:
        wrapped("m")
    assert caught.value is err
    assert fn.calls == 3


def test_402_gives_up_sooner_than_429() -> None:
    sleeps: List[float] = []
    fn = Flaky([_http(402)] * 10)
    wrapped = _wrap(fn, sleeps, attempts=6, attempts_402=3)
    with pytest.raises(urllib.error.HTTPError):
        wrapped("m")
    assert fn.calls == 3


@pytest.mark.parametrize("err", [_http(400), _http(401), ValueError("bad json"), RuntimeError("openrouter: boom")])
def test_other_failures_are_not_retried(err: BaseException) -> None:
    sleeps: List[float] = []
    fn = Flaky([err])
    wrapped = _wrap(fn, sleeps)
    with pytest.raises(type(err)):
        wrapped("m")
    assert fn.calls == 1
    assert sleeps == []


def test_openrouter_in_body_rate_limit_and_retry_after() -> None:
    assert LB.status_of(RuntimeError("openrouter: {'code': 429, 'message': 'Rate limit exceeded'}")) == 429
    assert LB.status_of(RuntimeError('openrouter: {"code": 402, "message": "Insufficient credits"}')) == 402
    sleeps: List[float] = []
    fn = Flaky([_http(429, retry_after="60")])
    assert _wrap(fn, sleeps)("m") == "ok"
    assert sleeps == [60.0]


def test_anthropic_style_status_code_attribute() -> None:
    class RateLimitError(Exception):
        status_code = 429

    assert LB.status_of(RateLimitError()) == 429


def test_install_wraps_the_vendored_call_model_once(localize_ui: Any) -> None:
    L = localize_ui
    original = L.call_model
    LB.install(L)
    LB.install(L)
    assert L.call_model is not original
    assert L.call_model.__wrapped__ is original  # wrapped exactly once


def test_both_entry_points_install_the_backoff() -> None:
    assert "lane_backoff.install(L)" in (LOCALIZATION / "accord_localize.py").read_text(encoding="utf-8")
    run_lane = (LOCALIZATION / "run_lane.sh").read_text(encoding="utf-8")
    assert "cmd=(python3 localization/lane_backoff.py)" in run_lane
    assert "cmd=(python3 localization/localize.py)" not in run_lane
