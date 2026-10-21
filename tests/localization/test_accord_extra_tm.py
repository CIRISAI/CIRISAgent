"""--extra-tm: the website and app corpora as terminology anchors, never values.

Offline. The model is faked and the network is blocked exactly as in
test_accord_pipeline.py; the end-to-end runs reuse test_accord_stems.py's
Constitution-ethics-1.3-shaped tree.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tests.localization.test_accord_pipeline import AL, FakeModel, _isolate_modules  # noqa: F401  (autouse fixture)
from tests.localization.test_accord_stems import ETHICS, tree  # noqa: F401  (fixture)

#: A term the shaped 1.3 source uses ("...like shy fireflies.", section0).
TERM_EN, TERM_YO = "Shy fireflies", "Àwọn kòkòrò-iná onítìjú"
CLIENT_YO = "Kòkòrò-iná onítìjú (app)"
_REAL_INSTALL = AL.install


def _write(path: Path, doc: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def website(tmp_path: Path) -> Path:
    root = tmp_path / "ciris-website"
    d = root / "src" / "i18n" / "dictionaries"
    en = {
        "_meta": {"locale": "en", "origin": "source", "status": "source"},
        "hero": {
            "fireflies": TERM_EN,
            "same": "Darkness kept",
            "long": "Stars " * 40,
            "list": ["Shy fireflies", "x"],
            "count": 3,
            "html": "<strong>Shy</strong> fireflies",
            "flagged": "Boiled seas",
        },
        "labels": {"next": "Next", "memories": "No Memories"},
    }
    yo = {
        "_meta": {"locale": "yo", "origin": "machine", "status": "draft"},
        "hero": {
            "fireflies": TERM_YO,
            "same": "Darkness kept",
            "long": "Ìràwọ̀ " * 40,
            "list": ["Àwọn kòkòrò-iná", "x"],
            "count": 3,
            "html": "<strong>Ìtìjú</strong> kòkòrò",
            "flagged": "Òkun tó hó (rejected)",
        },
        "labels": {"next": "Tókàn", "memories": "Kò Sí Ìrántí"},
    }
    _write(d / "en.json", en)
    _write(d / "yo.json", yo)
    _write(root / "src" / "i18n" / "chrome" / "en.json", {"_meta": {"origin": "source"}, "nav": {"seas": "Seas"}})
    # A file that says it never went through review is excluded whole.
    _write(
        root / "src" / "i18n" / "chrome" / "yo.json",
        {"_meta": {"origin": "machine", "status": "unreviewed"}, "nav": {"seas": "Òkun"}},
    )
    _write(
        root / "localization" / "hard-cases" / "hard-cases-20261014T000000Z.json",
        {"cases": [{"lang": "yo", "key": "hero.flagged", "kind": "judge_rejected", "why": "major/accuracy"}]},
    )
    return root


@pytest.fixture
def client(tmp_path: Path) -> Path:
    root = tmp_path / "CIRISClient"
    d = root / "client" / "shared" / "src" / "desktopMain" / "resources" / "localization"
    _write(d / "en.json", {"_meta": {"language": "en"}, "a": TERM_EN, "b": "Life flickered"})
    _write(d / "yo.json", {"_meta": {"language": "yo"}, "a": CLIENT_YO, "b": "Ìyè ń tàn"})
    return root


def _run(monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path], *extra: str) -> Dict[str, Any]:  # noqa: F811
    seen: Dict[str, Any] = {"requests": []}
    # The UNWRAPPED install: two runs in one test must not chain their wrappers.
    real_install = _REAL_INSTALL

    def install(L: Any, stage: Any, tms: Any) -> None:
        real_install(L, stage, tms)
        fake = FakeModel(L)

        def recording(model: str, system: str, messages: List[Dict[str, Any]], *, batch: bool = False) -> Any:
            seen["requests"].append("\n\n".join(part["text"] for m in messages for part in m["content"]))
            return fake(model, system, messages, batch=batch)

        L.call_model = recording
        seen["L"] = L
        # Snapshotted now: a later run in the same test re-imports and re-hooks.
        seen["prompts"] = {name: getattr(L, name) for name in AL.accord_prompts(L, stage.stem)}
        seen["plain_prompts"] = AL.accord_prompts(L, stage.stem)

    monkeypatch.setattr(AL, "install", install)
    seen["rc"] = AL.main(
        [*ETHICS, "--stage-dir", str(tree["stage"]), "--localized-dir", str(tree["loc"]), *extra]
    )  # fmt: skip
    return seen


def _extra_lines(request: str) -> List[str]:
    return [line for line in request.split("\n") if line.startswith(("  website:", "  client:", "  agent-ui:"))]


# ── loading: normalising and status handling ─────────────────────────────────


def test_corpora_are_normalised_and_status_respected(website: Path, client: Path) -> None:
    pool, report = AL.load_extra_tm([client, website], ["yo"])
    by_key = {a.key: a for a in pool["yo"]}
    # The website outranks the client, whatever order the flags came in, and
    # the same English is ONE anchor, from the higher-ranked corpus.
    assert [c.name for c, _ in report] == ["website", "client"]
    assert by_key["website:hero.fireflies"].text == TERM_YO
    assert "client:a" not in by_key
    assert "client:b" in by_key
    assert "website:hero.same" not in by_key, "a value equal to its English is not a translation"
    assert "website:hero.long" not in by_key
    assert not any(k.startswith("website:hero.list") for k in by_key), "arrays are skipped"
    assert "website:hero.count" not in by_key, "non-strings are skipped"
    assert "website:hero.html" not in by_key
    assert "website:hero.flagged" not in by_key, "a judge-rejected hard case is not an exemplar"
    assert "website:nav.seas" not in by_key, "a file whose status says unreviewed is excluded whole"
    assert "website:labels.next" not in by_key, "a short single word is not a term"
    stats = dict(report)
    website_stats = next(s for c, s in stats.items() if c.name == "website")["yo"]
    assert website_stats["review_flagged"] == 1
    assert website_stats["file_status"] == 1
    assert website_stats["same_as_english"] == 1


def test_an_unknown_root_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        AL.load_extra_tm([tmp_path], ["yo"])


# ── selection: bounds and ordering ───────────────────────────────────────────


def _anchor(rank: int, key: str, english: str, text: str = "t") -> Any:
    return AL.ExtraAnchor(rank, key, english, text, frozenset(AL._tokens(english)))


def _pool_and_lines(n: int) -> Any:
    # Line j uses a 3-word client term (the better match), a 2-word website
    # term, an agent-UI term and the word "memories".
    pool = [_anchor(2, f"client:c{j:02d}", f"Lantern{j} keeper vigil") for j in range(n)]
    pool += [_anchor(1, f"website:w{j:02d}", f"Beacon{j} keeper") for j in range(n)]
    pool += [_anchor(3, f"agent-ui:a{j:02d}", f"Harbor{j}") for j in range(n)]
    pool += [_anchor(1, "website:memories", "No Memories")]
    lines = {f"k{j:02d}": f"lantern{j} beacon{j} harbor{j} keeper vigil memories" for j in range(n)}
    return pool, lines


def _rank(key: str) -> int:
    return 1 if key.startswith("website:") else 2 if key.startswith("client:") else 3


def test_ordering_and_bounds_hold() -> None:
    pool, lines = _pool_and_lines(8)
    out = AL.extra_anchors(pool, list(lines), lines)
    keys = [k for k, _, _ in out]
    # Per key at most EXTRA_PER_KEY: each line's two best (client, then website);
    # its third-best (agent UI) never makes it.
    assert len(out) == 8 * AL.EXTRA_PER_KEY
    assert not any(k.startswith("agent-ui:") for k in keys)
    # Emitted grouped by corpus rank: website, then client, then agent UI.
    assert [_rank(k) for k in keys] == sorted(_rank(k) for k in keys)
    assert keys[0].startswith("website:") and keys[-1].startswith("client:")
    assert "website:memories" not in keys, "'No Memories' is not offered to a line about memories"
    # One line alone: exactly EXTRA_PER_KEY.
    assert len(AL.extra_anchors(pool, ["k00"], {"k00": lines["k00"]})) == AL.EXTRA_PER_KEY


def test_request_bounds_and_round_robin() -> None:
    pool, lines = _pool_and_lines(40)
    out = AL.extra_anchors(pool, list(lines), lines)
    assert len(out) == AL.EXTRA_ANCHOR_LIMIT
    assert sum(len(k) + len(e) + len(t) + 16 for k, e, t in out) <= AL.EXTRA_MAX_BLOCK_CHARS
    # Round-robin: every key's best comes before any key's second, so with more
    # keys than the limit the request carries the first keys' BEST terms only.
    assert {k for k, _, _ in out} == {f"client:c{j:02d}" for j in range(AL.EXTRA_ANCHOR_LIMIT)}


def test_the_char_budget_binds(monkeypatch: pytest.MonkeyPatch) -> None:
    pool, lines = _pool_and_lines(8)
    monkeypatch.setattr(AL, "EXTRA_MAX_BLOCK_CHARS", 200)
    out = AL.extra_anchors(pool, list(lines), lines)
    assert 0 < len(out) < 8 * AL.EXTRA_PER_KEY
    assert sum(len(k) + len(e) + len(t) + 16 for k, e, t in out) <= 200


# ── end to end on constitution_ethics ────────────────────────────────────────


def test_an_ethics_request_carries_a_website_anchor_for_a_shared_term(
    monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path], website: Path, client: Path  # noqa: F811
) -> None:
    out = _run(
        monkeypatch, tree, "--extra-tm", str(website), "--extra-tm", str(client),
        "--units", "section0", "--lane", "translate", "--lang", "yo", "--max-keys", "5000",
    )  # fmt: skip
    translate = [r for r in out["requests"] if "TRANSLATE THESE KEYS" in r]
    assert translate
    assert any(f'website:hero.fireflies: "{TERM_EN}"  ->  "{TERM_YO}"' in r for r in translate)
    assert any("  client:b:" in r for r in translate), "client terms come after the website's"
    for r in translate:
        lines = _extra_lines(r)
        assert len(lines) <= AL.EXTRA_ANCHOR_LIMIT
        assert lines == sorted(lines, key=lambda line: 0 if line.startswith("  website:") else 1)
    assert "ANCHORS FROM THE WEBSITE AND APPS" in out["prompts"]["SYSTEM_TRANSLATE"]
    assert "ANCHORS FROM THE WEBSITE AND APPS" in out["prompts"]["SYSTEM_REVIEW"]


def test_extra_corpora_never_become_values(
    monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path], website: Path, client: Path, tmp_path: Path  # noqa: F811
) -> None:
    plain = {"loc": tmp_path / "plain-loc", "stage": tmp_path / "plain-stage"}
    shutil.copytree(tree["loc"], plain["loc"])
    args = ("--seed-exact-tm", "--lane", "translate", "--lang", "yo", "--max-keys", "5000")
    with_extra = _run(monkeypatch, tree, "--extra-tm", str(website), "--extra-tm", str(client), *args)
    without = _run(monkeypatch, plain, *args)
    assert with_extra["rc"] == without["rc"] == 0
    name = "constitution_ethics_1.3_yo.txt"
    assert (tree["loc"] / name).read_bytes() == (plain["loc"] / name).read_bytes()
    stage_with = json.loads((tree["stage"] / "yo.json").read_text(encoding="utf-8"))
    stage_without = json.loads((plain["stage"] / "yo.json").read_text(encoding="utf-8"))
    assert stage_with == stage_without
    blob = (tree["loc"] / name).read_text(encoding="utf-8") + json.dumps(stage_with, ensure_ascii=False)
    for text in (TERM_YO, CLIENT_YO, "Ìyè ń tàn"):
        assert text not in blob


def test_without_extra_tm_requests_are_unchanged(
    monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path], website: Path, client: Path, tmp_path: Path  # noqa: F811
) -> None:
    """The negative: no flag, no extra anchors, no extra rule, and the requests
    a flagged run sends differ from an unflagged one ONLY by the extra lines."""
    plain = {"loc": tmp_path / "plain-loc", "stage": tmp_path / "plain-stage"}
    shutil.copytree(tree["loc"], plain["loc"])
    args = ("--units", "section0", "--lane", "translate", "--lang", "yo", "--max-keys", "5000")
    without = _run(monkeypatch, plain, *args)
    with_extra = _run(monkeypatch, tree, "--extra-tm", str(website), "--extra-tm", str(client), *args)
    assert all(not _extra_lines(r) for r in without["requests"])
    assert without["prompts"] == without["plain_prompts"], "a prompt gained text without --extra-tm"
    assert with_extra["prompts"] != with_extra["plain_prompts"]
    assert len(without["requests"]) == len(with_extra["requests"])
    for a, b in zip(without["requests"], with_extra["requests"]):
        stripped = "\n".join(line for line in b.split("\n") if line not in _extra_lines(b))
        assert stripped == a
    assert any(_extra_lines(r) for r in with_extra["requests"]), "precondition: the flag did add anchors"


def test_run_lane_passes_extra_tm_only_for_the_accord_target() -> None:
    script = (AL.REPO_ROOT / "localization" / "run_lane.sh").read_text(encoding="utf-8")
    accord_branch = script.split("accord)", 1)[1].split(";;", 1)[0]
    assert re.search(r"for d in \$\{EXTRA_TM:-\}; do cmd\+=\(--extra-tm \"\$d\"\); done", accord_branch)
