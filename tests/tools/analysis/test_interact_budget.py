"""The interact-budget toys: extraction is exact, the models behave as documented."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.analysis.interact_budget import explore
from tools.analysis.interact_budget.extract_latency import extract, unique_logs
from tools.analysis.interact_budget.local_provider import conscience_stage
from tools.analysis.interact_budget.pipeline import SHARDS, Config, Sampler, ceiling, simulate, solve_deadline

SNAPSHOT = Path("tools/analysis/interact_budget/latency.2026-09-23.json")

LOG = """\
2026-09-23 13:23:33.577 - x - INFO - [OBSERVER] PASSIVE TASK CREATED: eebd5df8-e45a for message m
2026-09-23 13:23:39.696 - x - INFO - [LLM-TIMING] BaseDSDMA th_seed_eebd5df8_397e: 2225ms via p
2026-09-23 13:23:49.142 - x - INFO - [LLM-TIMING] CSDMAEvaluator th_seed_eebd5df8_397e: 11977ms via p
2026-09-23 13:23:50.384 - x - INFO - [LLM-TIMING] EthicalPDMAEvaluator th_seed_eebd5df8_397e: 13280ms via p
2026-09-23 13:24:04.200 - x - INFO - [LLM-TIMING] IDMAEvaluator th_seed_eebd5df8_397e: 13416ms via p
2026-09-23 13:24:33.324 - x - INFO - [LLM-TIMING] ActionSelectionPDMAEvaluator th_seed_eebd5df8_397e: 27393ms via p
2026-09-23 13:24:38.830 - x - INFO - [LLM-TIMING] epistemic_humility_conscience th_seed_eebd5df8_397e: 5055ms via p
2026-09-23 13:24:57.030 - x - INFO - [LLM-TIMING] entropy_conscience th_seed_eebd5df8_397e: 23381ms via p
2026-09-23 13:25:07.714 - x - INFO - [LLM-TIMING] optimization_veto_conscience th_seed_eebd5df8_397e: 33908ms via p
2026-09-23 13:25:18.545 - x - WARNING - [CONSCIENCE] coherence_conscience: no answer within the facility budget (45s) on attempt 1/2 -- retrying with a fresh call
2026-09-23 13:26:03.549 - x - WARNING - [CONSCIENCE] coherence_conscience: no answer within the facility budget (45s) on attempt 2/2 -- giving up
2026-09-23 13:26:03.551 - x - ERROR - CoherenceConscience: transport failure (TIMEOUT), check did not run: x
2026-09-23 13:26:03.607 - x - INFO - ThoughtProcessor: conscience result for th_seed_eebd5df8_397e: final_action=ponder
2026-09-23 13:26:10.000 - x - INFO - [LLM_REQUEST] model=qwen/q, base_url=https://openrouter.ai/api/v1/, timeout=60, response_model=X
"""


def test_extract_reads_the_real_log_shapes(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "ciris_agent_1.log").write_text(LOG)
    (tmp_path / "b" / "latest.log").write_text(LOG)  # the gate ships the same file twice
    paths = unique_logs([tmp_path])
    assert len(paths) == 1, "identical logs under two paths must count once"
    d = extract(paths)
    assert d["body"]["ActionSelectionPDMAEvaluator"] == [27.393]
    assert d["timeouts"] == {"coherence_conscience": 2}
    assert d["attempts"] == {"1": 1, "2": 1}
    assert d["gave_up"] == {"Coherence": 1}
    assert d["end_to_end"] == [pytest.approx(150.03, abs=0.01)]
    assert d["meta"]["budgets_seen"]["http_timeout=60s"] == 1
    assert d["overhead"] == [], "coherence never answered, so this thought cannot be decomposed"


def _synthetic(p_timeout: float, n: int = 400) -> dict:
    body = {s: [5.0] * n for s in SHARDS}
    for k in ("EthicalPDMAEvaluator", "CSDMAEvaluator", "BaseDSDMA", "IDMAEvaluator", "ActionSelectionPDMAEvaluator"):
        body[k] = [5.0] * n
    to = round(n * p_timeout / (1 - p_timeout))
    return {"body": body, "timeouts": {s: to for s in SHARDS}, "overhead": [0.0]}


def test_ceiling_matches_the_closed_form() -> None:
    p = 0.10
    data = _synthetic(p)
    # 5000 runs keeps this a unit test (3x40000 took ~100s under CI coverage and
    # the runner killed the xdist worker). Binomial sd at the widest point
    # (1 attempt, ~0.66) is ~0.007, so 0.025 is ~3.7 sd — and still far tighter
    # than the gaps between attempt counts (0.66 / 0.96 / 0.996).
    for attempts in (1, 2, 3):
        expected = (1 - p**attempts) ** 4
        got = ceiling(Config(consc_attempts=attempts, overhead=False), Sampler(data, seed=3), 5000)
        assert got == pytest.approx(expected, abs=0.025)


def test_a_ceiling_below_target_is_unreachable_not_a_big_number() -> None:
    data = _synthetic(0.10)
    assert solve_deadline(Config(consc_attempts=1), Sampler(data, seed=3), 0.99, 5000) is None


def test_a_longer_deadline_never_lowers_success() -> None:
    d = json.loads(SNAPSHOT.read_text())
    lo = simulate(Config(consc_attempts=4, deadline=110), Sampler(d, seed=5), 5000)["success"]
    hi = simulate(Config(consc_attempts=4, deadline=200), Sampler(d, seed=5), 5000)["success"]
    assert hi >= lo


def test_on_a_bound_box_zombies_cost_more_than_freed_slots() -> None:
    d = json.loads(SNAPSHOT.read_text())
    freed = conscience_stage(Sampler(d, seed=2), 1, 45.0, 2, True, 30.0, 2.0, 2000)
    zombie = conscience_stage(Sampler(d, seed=2), 1, 45.0, 2, False, 30.0, 2.0, 2000)
    assert zombie[4] > freed[4], "an abandoned generation that keeps its slot must cost more"
    assert zombie[2] >= freed[2]


def test_the_snapshot_and_cli_run(capsys: pytest.CaptureFixture) -> None:
    assert explore.main(["ceiling", "--latency", str(SNAPSHOT)]) == 0
    assert "ceiling" in capsys.readouterr().out
