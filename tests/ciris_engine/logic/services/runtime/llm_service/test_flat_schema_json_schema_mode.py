"""Unit tests for scoped JSON_SCHEMA routing on flat DMA/conscience schemas (CIRISAgent#895)."""

from __future__ import annotations

from unittest import mock

import instructor
import pytest

from ciris_engine.logic.services.runtime.llm_service.service import (
    FLAT_JSON_SCHEMA_MODELS,
    OpenAICompatibleClient,
    OpenAIConfig,
)
from ciris_engine.schemas.conscience.core import (
    CoherenceResult,
    EntropyResult,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)
from ciris_engine.schemas.dma.results import ASPDMALLMResult, CSDMAResult, DSDMAResult, EthicalDMAResult, IDMAResult


def _make_client(instructor_mode: str = "JSON") -> OpenAICompatibleClient:
    cfg = OpenAIConfig(
        api_key="test-key",
        base_url="http://127.0.0.1:11434/v1",
        model_name="gemma4",
        instructor_mode=instructor_mode,
    )
    return OpenAICompatibleClient(config=cfg)


class TestFlatSchemaJSONSchemaRouting:
    def test_flat_schema_set_matches_six_documented_models(self) -> None:
        assert FLAT_JSON_SCHEMA_MODELS == frozenset(
            {
                "CSDMAResult",
                "DSDMAResult",
                "EntropyResult",
                "CoherenceResult",
                "OptimizationVetoResult",
                "EpistemicHumilityResult",
            }
        )

    @pytest.mark.parametrize(
        "model_cls",
        [
            CSDMAResult,
            DSDMAResult,
            EntropyResult,
            CoherenceResult,
            OptimizationVetoResult,
            EpistemicHumilityResult,
        ],
    )
    def test_flat_schemas_route_to_json_schema_client(self, model_cls: type) -> None:
        svc = _make_client("JSON")
        selected = svc._select_instruct_client(model_cls)
        assert selected is svc._json_schema_instruct_client
        assert selected is not svc.instruct_client
        assert selected.mode == instructor.Mode.JSON_SCHEMA
        assert selected.client is svc.client

    @pytest.mark.parametrize(
        "model_cls",
        [
            ASPDMALLMResult,
            IDMAResult,
            EthicalDMAResult,
        ],
    )
    def test_union_and_crux_schemas_stay_on_default_json_client(self, model_cls: type) -> None:
        svc = _make_client("JSON")
        selected = svc._select_instruct_client(model_cls)
        assert selected is svc.instruct_client
        assert selected.mode == instructor.Mode.JSON

    def test_explicit_tools_mode_does_not_override_to_json_schema(self) -> None:
        svc = _make_client("TOOLS")
        assert svc._json_schema_instruct_client is None
        assert svc._select_instruct_client(CSDMAResult) is svc.instruct_client
        assert svc.instruct_client.mode == instructor.Mode.TOOLS

    def test_explicit_json_schema_mode_is_supported_in_mode_map(self) -> None:
        svc = _make_client("JSON_SCHEMA")
        assert svc.instruct_client.mode == instructor.Mode.JSON_SCHEMA

    def test_replaced_instruct_client_is_respected(self) -> None:
        svc = _make_client("JSON")
        custom_double = mock.MagicMock()
        svc.instruct_client = custom_double
        assert svc._select_instruct_client(CSDMAResult) is custom_double
