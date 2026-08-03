"""Direct-provider harness contract tests (#978).

No test here touches a real provider: the stub sits at the client boundary
(``client.chat.completions.create``), the same seam
``tests/ciris_engine/logic/services/runtime/test_llm_service.py`` stubs.

What is locked:

* **arc continuity** — turn N is sent with turns 1..N-1 attached. The battery
  threads one ``channel_id`` through the arc because stage progression depends
  on conversational context continuity (``safety_battery.py`` ~:90-93), so a
  stateless per-question runner is a different instrument [M-V2].
* **scorer-schema identity** — the emitted row carries the battery capture's
  keys, in order, so one scorer reads every arm.
* **action_tier undefined, not null** — a blank in a defer column reads as
  "did not defer".
* **decoding transmitted** — temperature / top_p / max_tokens / extra_body /
  seed reach the wire, with ``extra_body`` a function of ``base_url``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from rich.console import Console

from ciris_engine.schemas.dma.compose import (
    BlockClass,
    BlockDisposition,
    ComposedBlock,
    ComposeDumpMeta,
)
from tools.qa_runner.modules.safety_battery import (
    BatteryResult,
    SafetyBatteryTests,
    load_battery,
)
from tools.research import direct_provider as dp
from tools.safety import mh_battery_eval as scorer

# pytest.ini sets asyncio_mode = auto — async tests need no marker.


# ---------------------------------------------------------------------------
# Stubs at the client boundary
# ---------------------------------------------------------------------------


class _RecordingCompletions:
    """Records every ``create(**kwargs)`` exactly as the runner sent it."""

    def __init__(self, replies: List[str]) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._replies = replies

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        index = len(self.calls) - 1
        content: Optional[str] = self._replies[index] if index < len(self._replies) else "fallback reply"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class _FakeClient:
    def __init__(self, replies: List[str]) -> None:
        self.completions = _RecordingCompletions(replies)
        self.chat = SimpleNamespace(completions=self.completions)

    @property
    def calls(self) -> List[Dict[str, Any]]:
        return self.completions.calls


def _decoding(**overrides: Any) -> dp.DirectProviderDecoding:
    params: Dict[str, Any] = {
        "model": "Qwen/Qwen3.6-35B-A3B",
        "base_url": "https://api.deepinfra.com/v1/openai",
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 4096,
        "seed": None,
        "extra_body": dp.build_extra_body("https://api.deepinfra.com/v1/openai", "Qwen/Qwen3.6-35B-A3B"),
    }
    params.update(overrides)
    return dp.DirectProviderDecoding(**params)


@pytest.fixture
def battery() -> Dict[str, Any]:
    """The real English v4 arc — 9 questions, the actual instrument."""
    return load_battery("en", "mental_health")


# ---------------------------------------------------------------------------
# Arc continuity — the test that fails if turns are sent independently
# ---------------------------------------------------------------------------


async def test_turn_n_carries_turns_1_to_n_minus_1(battery: Dict[str, Any]) -> None:
    """THE continuity proof.

    A stateless per-question runner sends exactly one user message per call and
    passes every other assertion in this file. It fails here, on all three
    counts: the transcript never grows, no assistant turn is ever echoed back,
    and ``prior_turns`` stays 0.
    """
    replies = [f"reply-{i}" for i in range(1, 10)]
    client = _FakeClient(replies)

    run = await dp.run_arc(
        arm=dp.ARM_BARE,
        battery=battery,
        locale="en",
        client=client,  # type: ignore[arg-type]
        decoding=_decoding(),
        injected=[],
        system_text="",
        limit=0,
    )

    assert len(client.calls) == 9, "one provider call per battery question"

    for index, call in enumerate(client.calls):
        messages = call["messages"]
        # bare arm: no system message, so turn N carries 2N-1 messages.
        assert len(messages) == 2 * index + 1, (
            f"turn {index + 1} sent {len(messages)} messages; a continuous arc sends "
            f"{2 * index + 1} (every prior user+assistant pair, then this question). "
            f"A stateless runner sends 1 every time."
        )
        # Every prior turn is present, verbatim and in order.
        for prior in range(index):
            assert messages[2 * prior]["role"] == "user"
            assert messages[2 * prior + 1] == {"role": "assistant", "content": replies[prior]}
        assert messages[-1]["role"] == "user"

    # Each request is a strict prefix-extension of the previous one: history is
    # appended to, never rewritten (the list is copied at send time).
    for index in range(1, len(client.calls)):
        previous = client.calls[index - 1]["messages"]
        current = client.calls[index]["messages"]
        assert current[: len(previous)] == previous

    # The continuity witness recorded per turn matches what went on the wire.
    assert [t.prior_turns for t in run.turns] == [0, 2, 4, 6, 8, 10, 12, 14, 16]
    assert run.arc_intact


async def test_injected_system_content_leads_every_turn(battery: Dict[str, Any]) -> None:
    """values-ciris: one system message, at position 0, on every turn."""
    client = _FakeClient([f"r{i}" for i in range(9)])
    run = await dp.run_arc(
        arm=dp.ARM_VALUES_CIRIS,
        battery=battery,
        locale="en",
        client=client,  # type: ignore[arg-type]
        decoding=_decoding(),
        injected=[
            dp.InjectedSource(block_class=BlockClass.AXIOTIC, source="file:x", sha256="ab" * 32, bytes=7)
        ],
        system_text="VALUES",
        limit=3,
    )
    assert len(client.calls) == 3
    for index, call in enumerate(client.calls):
        messages = call["messages"]
        assert messages[0] == {"role": "system", "content": "VALUES"}
        assert sum(1 for m in messages if m["role"] == "system") == 1
        assert len(messages) == 2 * index + 2
    assert run.system_bytes == len("VALUES".encode("utf-8"))


async def test_failed_turn_does_not_fabricate_an_assistant_message(battery: Dict[str, Any]) -> None:
    """A dropped turn breaks the arc — and says so — rather than inventing text."""

    class _FailingSecond(_RecordingCompletions):
        async def create(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            if len(self.calls) == 2:
                raise RuntimeError("provider 503")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    client = _FakeClient([])
    client.completions = _FailingSecond([])
    client.chat = SimpleNamespace(completions=client.completions)

    run = await dp.run_arc(
        arm=dp.ARM_BARE,
        battery=battery,
        locale="en",
        client=client,  # type: ignore[arg-type]
        decoding=_decoding(),
        injected=[],
        system_text="",
        limit=3,
    )
    assert [t.success for t in run.turns] == [True, False, True]
    assert run.arc_intact is False
    third = client.calls[2]["messages"]
    assert all(m["content"] != "" for m in third)
    # The failed question is not echoed as an unanswered user turn either.
    assert [m["role"] for m in third] == ["user", "assistant", "user"]


# ---------------------------------------------------------------------------
# Scorer schema — one path for every arm
# ---------------------------------------------------------------------------


def _battery_row_keys() -> List[str]:
    """The real battery capture's row keys, from the battery's own writer."""
    module = SafetyBatteryTests(client=None, console=Console(), lang="en")
    manifest = load_battery("en", "mental_health")
    row = module._result_to_jsonl_row(
        BatteryResult(
            question_id="en_mh_v4_q01",
            question_version=1,
            stage="Stage 1",
            category="Mental Health",
            question_text="q",
            response_text="a",
            response_task_id="task-1",
            duration_s=1.0,
            success=True,
        ),
        manifest,
    )
    return list(row)


async def test_row_schema_matches_the_battery_capture(battery: Dict[str, Any], tmp_path: Path) -> None:
    client = _FakeClient([f"r{i}" for i in range(9)])
    run = await dp.run_arc(
        arm=dp.ARM_BARE, battery=battery, locale="en", client=client,  # type: ignore[arg-type]
        decoding=_decoding(), injected=[], system_text="", limit=2,
    )
    results_jsonl = dp.write_capture(run, battery, "20260101T000000Z", tmp_path, "2026-01-01T00:00:00Z")

    rows = [json.loads(line) for line in results_jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    expected = _battery_row_keys()
    for row in rows:
        assert list(row)[: len(expected)] == expected, (
            "the shared keys must match the battery capture exactly, in order — "
            "mh_battery_eval reads both through one function"
        )
        assert row["schema"] == "ciris.ai/safety_battery_result/v1"
        assert row["harness"] == "direct-provider"

    # And the scorer actually reads it.
    lang, results = scorer.read_results_jsonl(results_jsonl)
    assert lang == "en"
    assert [r.q_num for r in results] == [1, 2]
    assert [r.response_text for r in results] == ["r0", "r1"]

    # Sidecars land with the battery's schema ids too.
    assert json.loads((tmp_path / "summary.json").read_text())["schema"] == (
        "ciris.ai/safety_battery_summary/v1"
    )
    assert json.loads((tmp_path / "manifest_signed.json").read_text())["schema"] == (
        "ciris.ai/safety_battery_manifest_signed/v1"
    )


async def test_action_tier_is_undefined_never_null(battery: Dict[str, Any], tmp_path: Path) -> None:
    """`undefined` is a word in the file, not an absence a reader fills in."""
    client = _FakeClient(["r0", "r1"])
    run = await dp.run_arc(
        arm=dp.ARM_BARE, battery=battery, locale="en", client=client,  # type: ignore[arg-type]
        decoding=_decoding(), injected=[], system_text="", limit=2,
    )
    results_jsonl = dp.write_capture(run, battery, "rid", tmp_path, "2026-01-01T00:00:00Z")

    raw = results_jsonl.read_text(encoding="utf-8")
    assert '"action_tier": "undefined"' in raw
    assert '"action_tier": null' not in raw

    for line in raw.splitlines():
        row = json.loads(line)
        assert row["dv"] is not None
        assert row["dv"]["action_tier"] == "undefined"
        assert row["dv"]["text_tier"] == "defined"
        assert "no handler action enum" in row["dv"]["action_tier_reason"]
        # No key that could be read as a recorded verb.
        assert "selected_verb" not in row
        assert "defer_rate" not in row

    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["dv"]["action_tier"] == "undefined"
    assert summary["repeat_unit"] == "conversation"

    # Through the scorer: UNDEFINED, distinct from "?" (exists-but-unrecorded),
    # and counted as captured rather than failed.
    _, results = scorer.read_results_jsonl(results_jsonl)
    assert {r.action for r in results} == {scorer.ACTION_UNDEFINED}
    assert scorer.ACTION_UNDEFINED != scorer.ACTION_UNRECORDED
    entry = scorer.suggest_ledger_entry(
        lang="en", corpus_stem="c", corpus_path=results_jsonl, log_dir=tmp_path,
        results=results, duration_s=1.0, model="m", base_url="b", provider="p",
    )
    assert entry["questions_passed"] == 2
    assert entry["questions_failed"] == 0
    assert entry["action_tier"] == "undefined"
    report = scorer.render_report("en", results, [], entry)
    assert "action_tier: UNDEFINED for 2/2 rows" in report


def test_scorer_log_path_action_vocabulary_is_untouched() -> None:
    """The mental-health log-scrape path must not shift under this change."""
    rows = [
        scorer.QResult(q_num=1, stage="s", action="SPEAK", duration_s=1.0, response_text="hello"),
        scorer.QResult(q_num=2, stage="s", action="DEFER", duration_s=1.0, response_text="partial"),
    ]
    scorer.score_rubric(rows, "en")
    # DEFER rows are still not rubric-scored; SPEAK rows still are.
    assert rows[1].rubric_hits == {} and rows[1].out_of_script is False
    entry = scorer.suggest_ledger_entry(
        lang="en", corpus_stem="c", corpus_path=Path("x"), log_dir=Path("y"),
        results=rows, duration_s=2.0, model="m", base_url="b", provider="p",
    )
    assert entry["questions_passed"] == 2
    assert entry["questions_failed"] == 0
    assert entry["action_tier"] == "defined"
    assert "P1/D1" in entry["notes"]


# ---------------------------------------------------------------------------
# Decoding parameters actually reach the wire
# ---------------------------------------------------------------------------


async def test_decoding_params_transmitted(battery: Dict[str, Any]) -> None:
    client = _FakeClient(["r0"])
    decoding = _decoding(temperature=0.3, top_p=0.9, max_tokens=1234, seed=20260802)
    await dp.run_arc(
        arm=dp.ARM_BARE, battery=battery, locale="en", client=client,  # type: ignore[arg-type]
        decoding=decoding, injected=[], system_text="", limit=1,
    )
    call = client.calls[0]
    assert call["model"] == "Qwen/Qwen3.6-35B-A3B"
    assert call["temperature"] == 0.3
    assert call["top_p"] == 0.9
    assert call["max_tokens"] == 1234
    assert call["seed"] == 20260802
    # extra_body is a FUNCTION of base_url [M-N3]: DeepInfra's vLLM branch.
    assert call["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False},
        "reasoning": {"enabled": False},
    }
    # No JSON coercion, no tool schema: that is §6.2 pipeline scaffolding.
    assert "response_format" not in call
    assert "tools" not in call

    assert decoding.transmitted_keys() == sorted(
        [
            "model", "messages", "temperature", "top_p", "max_tokens", "seed",
            "extra_body.chat_template_kwargs", "extra_body.reasoning",
        ]
    )


async def test_seed_absent_when_unpinned(battery: Dict[str, Any]) -> None:
    """A pinned-but-not-transmitted key must be visible as absent, not faked."""
    client = _FakeClient(["r0"])
    await dp.run_arc(
        arm=dp.ARM_BARE, battery=battery, locale="en", client=client,  # type: ignore[arg-type]
        decoding=_decoding(seed=None), injected=[], system_text="", limit=1,
    )
    assert "seed" not in client.calls[0]


def test_extra_body_tracks_base_url() -> None:
    assert dp.build_extra_body("https://openrouter.ai/api/v1", "meta-llama/llama-4-scout")["reasoning"] == {
        "enabled": False
    }
    assert dp.build_extra_body("https://api.groq.com/openai/v1", "meta-llama/llama-4-scout") == {}
    assert "thinking" in dp.build_extra_body("https://api.together.xyz/v1", "google/gemma-4-31B-it")


def test_seed_env_refuses_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_LLM_SEED", "not-an-int")
    with pytest.raises(SystemExit, match="unparseable determinism pin"):
        dp.read_seed_env()
    monkeypatch.setenv("CIRIS_LLM_SEED", "7")
    assert dp.read_seed_env() == 7
    monkeypatch.delenv("CIRIS_LLM_SEED")
    assert dp.read_seed_env() is None


# ---------------------------------------------------------------------------
# Compose-side stub for the §12 gate
# ---------------------------------------------------------------------------


def _reference_dump(tmp_path: Path, corpus_path: Path) -> Path:
    """A miniature h3ere dump: one held axiotic block plus the n/a classes."""
    meta = ComposeDumpMeta(
        arm="h3ere-ciris", manifest=None, locales=["en"], steps=["pdma"],
        residue_digest="sha256:whatever", fragment_count=0,
    )
    common = {"step": "pdma", "locale": "en", "arm": "h3ere-ciris", "role": "system"}
    rows = [
        ComposedBlock(
            block_id="pdma.accord", seq=0, **{"class": BlockClass.AXIOTIC},
            disposition=BlockDisposition.VARY, source=f"file:{corpus_path}",
            sha256="00" * 32, bytes=1, **common,
        ),
        ComposedBlock(
            block_id="pdma.frame", seq=1, **{"class": BlockClass.PROCEDURAL},
            disposition=BlockDisposition.HOLD, source="string:prompts.frame",
            sha256="11" * 32, bytes=2, **common,
        ),
        ComposedBlock(
            block_id="pdma.schema", seq=2, **{"class": BlockClass.STRUCTURAL},
            disposition=BlockDisposition.NOT_APPLICABLE, source="inline",
            sha256="22" * 32, bytes=3, **common,
        ),
        ComposedBlock(
            block_id="pdma.system", seq=3, **{"class": BlockClass.MIXED},
            disposition=BlockDisposition.REFUSE, source="inline",
            sha256="33" * 32, bytes=4, contaminant=[BlockClass.AXIOTIC], **common,
        ),
    ]
    path = tmp_path / "h3ere.jsonl"
    dp._compose_dump.write_dump(meta, rows, str(path))
    return path


def test_compose_stub_carries_injected_source_hash_and_declares_na(tmp_path: Path) -> None:
    corpus = tmp_path / "values.txt"
    corpus.write_text("BE GOOD TO EACH OTHER\n", encoding="utf-8")
    reference = _reference_dump(tmp_path, corpus)

    _, reference_rows = dp._compose_dump.load_dump(str(reference))
    rows = dp.compose_stub_rows(
        arm=dp.ARM_VALUES_CIRIS,
        reference_rows=reference_rows,
        inject={"axiotic": f"file:{corpus}"},
    )
    by_id = {r.block_id: r for r in rows}
    assert set(by_id) == {"pdma.accord", "pdma.frame", "pdma.schema", "pdma.system"}

    import hashlib

    held = by_id["pdma.accord"]
    assert held.disposition is BlockDisposition.HOLD
    assert held.sha256 == hashlib.sha256(corpus.read_bytes()).hexdigest()
    assert held.bytes == len(corpus.read_bytes())
    assert held.arm == dp.ARM_VALUES_CIRIS

    # structural + procedural: no direct-provider analogue, §10.3.
    for block_id in ("pdma.frame", "pdma.schema"):
        row = by_id[block_id]
        assert row.disposition is BlockDisposition.NOT_APPLICABLE
        assert row.source == dp.NA_NO_ANALOGUE
        assert row.bytes == 0
    # mixed pipeline scaffolding: nothing this harness composes.
    assert by_id["pdma.system"].source == dp.NA_NOT_INJECTED


def test_compose_stub_bare_arm_holds_nothing(tmp_path: Path) -> None:
    corpus = tmp_path / "values.txt"
    corpus.write_text("x", encoding="utf-8")
    _, reference_rows = dp._compose_dump.load_dump(str(_reference_dump(tmp_path, corpus)))
    rows = dp.compose_stub_rows(arm=dp.ARM_BARE, reference_rows=reference_rows, inject={})
    assert all(r.disposition is BlockDisposition.NOT_APPLICABLE for r in rows)
    assert all(r.arm == dp.ARM_BARE for r in rows)


def test_compose_stub_meta_records_the_absent_conscience(tmp_path: Path) -> None:
    corpus = tmp_path / "values.txt"
    corpus.write_text("x", encoding="utf-8")
    reference_meta, _ = dp._compose_dump.load_dump(str(_reference_dump(tmp_path, corpus)))
    meta = dp.compose_stub_meta(dp.ARM_BARE, reference_meta)
    assert meta.arm == dp.ARM_BARE
    assert meta.locales == ["en"] and meta.steps == ["pdma"]
    assert meta.conscience_guidance_mode == "n/a:direct-provider"
    # Recomputed against the live tree, never copied from the reference.
    assert meta.residue_digest != reference_meta.residue_digest
    assert meta.fragment_count > 0


# ---------------------------------------------------------------------------
# Arm refusals — the arm name is a claim about content
# ---------------------------------------------------------------------------


def test_bare_refuses_injection() -> None:
    with pytest.raises(SystemExit, match="injects nothing by definition"):
        dp.resolve_arm_inject(dp.ARM_BARE, {"axiotic": "file:/x"})


def test_values_arm_refuses_empty_injection() -> None:
    with pytest.raises(SystemExit, match="wearing another"):
        dp.resolve_arm_inject(dp.ARM_VALUES_CIRIS, {})


def test_empty_corpus_refuses(tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="resolved to EMPTY"):
        dp.resolve_injections({"axiotic": f"file:{empty}"}, "en")


def test_h3ere_arm_is_refused_by_this_harness(tmp_path: Path) -> None:
    regime = tmp_path / "regime.yaml"
    regime.write_text(
        "arms:\n"
        "  bare: {harness: h3ere}\n"
        "  values-ciris: {harness: direct-provider, inject: {axiotic: 'corpus:accord.localized'}}\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="§10.4 refusal"):
        dp.arm_from_regime(str(regime), "bare")
    spec = dp.arm_from_regime(str(regime), "values-ciris")
    assert spec.inject == {"axiotic": "corpus:accord.localized"}


def test_unknown_inject_source_refuses() -> None:
    with pytest.raises(SystemExit, match="unknown inject source"):
        dp.resolve_source_bytes("corpus:not-a-thing", "en")
