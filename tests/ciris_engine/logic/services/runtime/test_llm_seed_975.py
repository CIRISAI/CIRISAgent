"""#975 seed plumbing: transmitted iff configured, OpenAI path only [M-N1].

Lives in this directory for the `llm_service` fixture (conftest.py:188).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Seed plumbing — transmitted iff configured, OpenAI path only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_transmitted_only_when_configured(llm_service, monkeypatch) -> None:
    from ciris_engine.schemas.actions.parameters import SpeakParams
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    mock_result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="ok"),
        rationale="r",
        reasoning="r",
        evaluation_time_ms=1,
    )
    mock_completion = MagicMock()
    mock_completion.usage = MagicMock(prompt_tokens=1, completion_tokens=1)
    captured: dict = {}

    async def _capture(**kwargs):
        captured.clear()
        captured.update(kwargs)
        return (mock_result, mock_completion)

    with patch.object(
        llm_service.instruct_client.chat.completions,
        "create_with_completion",
        AsyncMock(side_effect=_capture),
    ):
        # unset -> absent. Absence is load-bearing: an unconditional seed would
        # 400 on providers that reject unknown params.
        monkeypatch.delenv("CIRIS_LLM_SEED", raising=False)
        await llm_service.call_llm_structured(
            messages=[{"role": "user", "content": "x"}],
            response_model=ActionSelectionDMAResult,
            max_tokens=64,
            temperature=0.0,
        )
        assert "seed" not in captured, "seed transmitted without configuration"

        # set -> transmitted as int
        monkeypatch.setenv("CIRIS_LLM_SEED", "20260802")
        await llm_service.call_llm_structured(
            messages=[{"role": "user", "content": "x"}],
            response_model=ActionSelectionDMAResult,
            max_tokens=64,
            temperature=0.0,
        )
        assert captured.get("seed") == 20260802, "pinned seed was not transmitted [M-N1]"


@pytest.mark.asyncio
async def test_unparseable_seed_refuses_loudly(llm_service, monkeypatch) -> None:
    """A determinism pin that cannot be parsed must stop the run, not be
    silently dropped — a campaign that believes it is seeded and is not
    produces confident wrong numbers."""
    monkeypatch.setenv("CIRIS_LLM_SEED", "not-an-int")
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult

    with pytest.raises(Exception, match="CIRIS_LLM_SEED"):
        await llm_service.call_llm_structured(
            messages=[{"role": "user", "content": "x"}],
            response_model=ActionSelectionDMAResult,
            max_tokens=64,
            temperature=0.0,
        )
