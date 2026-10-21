"""The slow-host override: DeepInfra gets a 90s HTTP timeout, nothing else changes."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ciris_engine.logic.config import llm_budget as lb
from ciris_engine.logic.config.llm_budget import resolve_budget
from ciris_engine.schemas.config.llm_budget import (
    LOCAL_PROFILE,
    REMOTE_PROFILE,
    SLOW_REMOTE_PROFILE,
    LLMBudgetProfile,
    ProviderClass,
)


@pytest.fixture
def env(monkeypatch):
    table: dict[str, str] = {}
    monkeypatch.setattr(lb, "get_env_var", lambda name, default=None: table.get(name, default))
    return table


def test_deepinfra_gets_the_90s_profile(env) -> None:
    b = resolve_budget(None, "https://api.deepinfra.com/v1/openai")
    assert b == SLOW_REMOTE_PROFILE
    assert b.llm_http_timeout_s == 90.0
    assert b.provider_class is ProviderClass.REMOTE
    # Still nests: the per-tries outlast the HTTP timeout, the thought fits the interact deadline.
    assert b.dma_per_try_s >= b.llm_http_timeout_s
    assert b.conscience_per_try_s >= b.llm_http_timeout_s
    assert b.thought_budget_s <= b.interact_deadline_s


@pytest.mark.parametrize(
    "url",
    [
        "https://api.together.xyz/v1",
        "https://openrouter.ai/api/v1",
        "https://api.groq.com/openai/v1",
        "https://api.openai.com/v1",
        None,
    ],
)
def test_other_remote_hosts_are_unchanged(env, url) -> None:
    assert resolve_budget(None, url) == REMOTE_PROFILE


def test_local_is_unchanged(env) -> None:
    assert resolve_budget(None, "http://localhost:11434/v1") == LOCAL_PROFILE


def test_ciris_llm_timeout_still_overrides_on_deepinfra(env) -> None:
    env["CIRIS_LLM_TIMEOUT"] = "60"
    assert resolve_budget(None, "https://api.deepinfra.com/v1/openai").llm_http_timeout_s == 60.0


def test_a_forced_profile_wins_over_the_host(env) -> None:
    env["CIRIS_LLM_BUDGET_PROFILE"] = "remote"
    assert resolve_budget(None, "https://api.deepinfra.com/v1/openai") == REMOTE_PROFILE


def test_the_nesting_validator_rejects_a_cap_below_the_floor() -> None:
    with pytest.raises(ValidationError, match="dma_attempt_cap"):
        LLMBudgetProfile(**{**SLOW_REMOTE_PROFILE.model_dump(), "dma_attempts": 3, "dma_attempt_cap": 2})


def test_explicit_dma_attempts_is_the_whole_answer(env) -> None:
    env["CIRIS_DMA_ATTEMPTS"] = "2"
    b = resolve_budget(None, "https://api.together.xyz/v1")
    assert (b.dma_attempts, b.dma_attempt_cap) == (2, 2)
