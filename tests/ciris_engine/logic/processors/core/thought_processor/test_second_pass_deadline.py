"""The tool/verb second-pass DMAs spend from the thought deadline (#1186).

TSASPDMA, DSASPDMA and MSASPDMA call their evaluators directly instead of
through run_dma_with_retries, so they were the one LLM path the thought
budget did not bound.
"""

from __future__ import annotations

import asyncio

import pytest

from ciris_engine.logic.config import llm_budget
from ciris_engine.logic.config.llm_budget import Deadline
from ciris_engine.logic.processors.core.thought_processor import main as tp_main
from ciris_engine.logic.processors.core.thought_processor.main import _within_thought_deadline


class _Item:
    def __init__(self, deadline):
        self.deadline = deadline


@pytest.fixture(autouse=True)
def _remote_budget(monkeypatch):
    monkeypatch.setattr(llm_budget, "get_env_var", lambda name, default=None: default)


async def test_no_deadline_runs_the_call_once():
    calls = []

    async def call():
        calls.append(1)
        return "refined"

    assert await _within_thought_deadline(_Item(None), call()) == "refined"
    assert calls == [1]


async def test_a_spent_deadline_never_starts_the_llm_call():
    now = [0.0]
    spent = Deadline(5.0, clock=lambda: now[0])
    now[0] = 100.0
    started = []

    async def call():
        started.append(1)

    with pytest.raises(TimeoutError, match="LLM API timeout"):
        await _within_thought_deadline(_Item(spent), call())
    assert started == [], "no provider request may be sent once the thought's time is gone"


async def test_the_attempt_is_clamped_to_what_is_left(monkeypatch):
    seen = {}

    async def fake_wait_for(coro, timeout):
        seen["timeout"] = timeout
        coro.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(tp_main.asyncio, "wait_for", fake_wait_for)
    now = [0.0]
    deadline = Deadline(30.0, clock=lambda: now[0])

    async def call():
        return None

    with pytest.raises(asyncio.TimeoutError):
        await _within_thought_deadline(_Item(deadline), call())
    assert seen["timeout"] == 30.0, "90s DMA per-try must be clamped to the 30s remainder"


async def test_a_mock_deadline_is_treated_as_none():
    """Tests pass MagicMock thought items; a mock attribute is not a deadline."""
    from unittest.mock import MagicMock

    async def call():
        return "ok"

    assert await _within_thought_deadline(MagicMock(), call()) == "ok"


def test_every_second_pass_call_site_is_bounded():
    """A new second-pass call added without the wrapper would silently escape the budget."""
    import inspect

    src = inspect.getsource(tp_main)
    for fn in ("run_tsaspdma_correction", "run_tsaspdma", "run_dsaspdma", "run_msaspdma"):
        calls = [
            i
            for i in range(len(src))
            if src.startswith(f"{fn}(", i) and not (src[i - 1].isalnum() or src[i - 1] == "_")
        ]
        assert calls, f"{fn} is no longer called -- update this guard"
        for i in calls:
            preceding = src[max(0, i - 80) : i]
            assert "_within_thought_deadline(" in preceding, f"{fn} is called outside _within_thought_deadline"
