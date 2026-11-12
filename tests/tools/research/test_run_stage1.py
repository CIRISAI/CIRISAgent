"""The direct runner, against a fake model client: no network, no spend."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest

from ciris_engine.schemas.runtime.resources import ResourceUsage
from tests.ciris_engine.logic.dma import compose_golden as cg
from tools.research import render_stage1 as rs
from tools.research import run_stage1 as runner


class FakeClient:
    """Answers each evaluator with a valid result and a fixed cost."""

    def __init__(self, cost_cents: float = 1.0, fail_first: bool = False) -> None:
        self.cost_cents = cost_cents
        self.fail_first = fail_first
        self.calls: List[str] = []

    async def call_llm_structured(self, messages: Any, response_model: Any, **_: Any) -> Tuple[Any, ResourceUsage]:
        name = response_model.__name__
        self.calls.append(name)
        if self.fail_first and len(self.calls) == 1:
            raise TimeoutError("provider did not answer")
        usage = ResourceUsage(tokens_input=100, tokens_output=10, cost_cents=self.cost_cents)
        if "ASPDMA" in name or "ActionSelection" in name:
            from ciris_engine.schemas.dma.results import ASPDMALLMResult
            from ciris_engine.schemas.runtime.enums import HandlerActionType

            return ASPDMALLMResult(selected_action=HandlerActionType.DEFER, reasoning="fake"), usage
        if "Ethical" in name:
            return cg.make_ethical_result(), usage
        if "CSDMA" in name:
            return cg.make_csdma_result(), usage
        if "IDMA" in name:
            from ciris_engine.schemas.dma.results import IDMAResult

            return IDMAResult(k_eff=3.0, correlation_risk=0.2, phase="healthy", fragility_flag=False, reasoning="fake"), usage
        return cg.make_dsdma_result(), usage


def _args(tmp_path: Path, **over: Any) -> SimpleNamespace:
    base: Dict[str, Any] = dict(
        out=tmp_path / "out", key_file="unused", max_usd=1.0, reserve_usd=0.10, model="fake/model",
        base_url="https://example.invalid/v1", timeout=5, limit=None, shard=(0, 1), concurrency=2,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _items(tmp_path: Path, n: int) -> Path:
    src = tmp_path / "items.jsonl"
    src.write_text("".join(json.dumps({"id": f"i{k}", "task": f"TASK-{k}", "thought": f"THOUGHT-{k}"}) + "\n" for k in range(n)), encoding="utf-8")
    return src


@pytest.fixture(autouse=True)
def _en(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", "en")
    monkeypatch.delenv("CIRIS_LLM_CAPTURE_HANDLER", raising=False)
    monkeypatch.delenv("CIRIS_LLM_CAPTURE_FILE", raising=False)


def _rows(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_five_calls_per_item_and_the_summaries_reach_selection(tmp_path: Path) -> None:
    stack = rs.load_stack(rs.DEFAULT_TEMPLATE)
    client = FakeClient()
    manifest = asyncio.run(runner.run(_args(tmp_path), [("s", _items(tmp_path, 2))], stack, client=client))

    results = _rows(tmp_path / "out" / "s.results.jsonl")
    assert [r["status"] for r in results] == ["ok", "ok"] and all(r["calls"] == 5 for r in results)
    assert {r["selected_action"] for r in results} == {"defer"}
    calls = _rows(tmp_path / "out" / "s.llm_calls.jsonl")
    assert len(calls) == 10 and {c["thought_id"] for c in calls} == {"i0", "i1"}
    by_item = {r["id"]: r for r in results}
    for call in calls:
        if call["handler"] == "ActionSelectionPDMAEvaluator":
            row = by_item[call["thought_id"]]
            assert call["prompt_hash"] == row["selection_prompt_hash"]
            user = call["messages"][-1]["content"]
            # what the evaluators said is what selection read
            assert row["summaries"]["ethical"] in user and row["summaries"]["csdma"] in user
            assert row["summaries"]["dsdma"] in user and "Thought Depth: 0" in user
    assert manifest["spent_usd_reported"] == pytest.approx(0.10) and manifest["stopped"] is None


def test_the_ceiling_stops_the_run_before_it_is_crossed(tmp_path: Path) -> None:
    stack = rs.load_stack(rs.DEFAULT_TEMPLATE)
    # 5 cents an item, 10 cent reserve, 20 cent ceiling, one at a time: an item starts only while
    # spent + reserve <= ceiling, so three run (0.15 spent) and the fourth does not start.
    args = _args(tmp_path, max_usd=0.20, concurrency=1)
    client = FakeClient(cost_cents=1.0)
    manifest = asyncio.run(runner.run(args, [("s", _items(tmp_path, 6))], stack, client=client))
    assert manifest["stopped"] and manifest["spent_usd_reported"] <= 0.20
    assert manifest["counts"]["s"]["ok"] == 3 and manifest["counts"]["s"]["not_started"] == 3
    assert manifest["spent_usd_reported"] == pytest.approx(0.15)


def test_a_rerun_skips_what_is_done_and_counts_its_cost(tmp_path: Path) -> None:
    stack = rs.load_stack(rs.DEFAULT_TEMPLATE)
    src = _items(tmp_path, 3)
    asyncio.run(runner.run(_args(tmp_path, limit=2), [("s", src)], stack, client=FakeClient()))
    second = FakeClient()
    manifest = asyncio.run(runner.run(_args(tmp_path), [("s", src)], stack, client=second))
    assert len(second.calls) == 5 and manifest["counts"]["s"]["already_done"] == 2
    assert manifest["spent_usd_reported"] == pytest.approx(0.15)
    assert len(_rows(tmp_path / "out" / "s.results.jsonl")) == 3


def test_a_failed_call_is_recorded_and_retried_once(tmp_path: Path) -> None:
    stack = rs.load_stack(rs.DEFAULT_TEMPLATE)
    client = FakeClient(fail_first=True)
    asyncio.run(runner.run(_args(tmp_path, concurrency=1), [("s", _items(tmp_path, 1))], stack, client=client))
    result = _rows(tmp_path / "out" / "s.results.jsonl")[0]
    calls = _rows(tmp_path / "out" / "s.llm_calls.jsonl")
    assert result["status"] == "ok" and result["calls"] == 6
    assert [c["status"] for c in calls].count("error") == 1 and len(calls) == 6
