import pytest

from ciris_engine.schemas.conscience.core import (
    CoherenceCheckResult,
    EntropyCheckResult,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult
from tests.adapters.mock_llm import MockLLMClient


@pytest.mark.asyncio
async def test_mock_llm_structured_outputs():
    client = MockLLMClient()
    assert isinstance(await client._create(response_model=EthicalDMAResult), EthicalDMAResult)
    assert isinstance(await client._create(response_model=CSDMAResult), CSDMAResult)
    # DSDMA now uses DSDMAResult directly as the instructor response_model
    # (the legacy BaseDSDMA.LLMOutputForDSDMA shim was removed in 2.7.4 — it
    # asked for `score` while the prompt asked for `domain_alignment`,
    # causing schema-mismatch retries that opened the LLM circuit breaker).
    dsdma = await client._create(response_model=DSDMAResult)
    assert isinstance(dsdma, DSDMAResult)
    assert hasattr(dsdma, "finish_reason")
    assert isinstance(await client._create(response_model=ActionSelectionDMAResult), ActionSelectionDMAResult)
    assert isinstance(await client._create(response_model=OptimizationVetoResult), OptimizationVetoResult)
    assert isinstance(await client._create(response_model=EpistemicHumilityResult), EpistemicHumilityResult)
    assert isinstance(await client._create(response_model=EntropyCheckResult), EntropyCheckResult)
    assert isinstance(await client._create(response_model=CoherenceCheckResult), CoherenceCheckResult)
