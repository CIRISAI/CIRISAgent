"""Tests for the DSASPDMA (Deferral-Specific Action Selection PDMA) evaluator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.dma.dsaspdma import DSASPDMAEvaluator, DSASPDMALLMResult
from ciris_engine.logic.dma.prompt_loader import set_prompt_language
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.actions.parameters import DeferParams, SpeakParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType
from ciris_engine.schemas.services.agent_credits import DomainCategory
from ciris_engine.schemas.services.deferral_taxonomy import (
    DeferralNeedCategory,
    DeferralOperationalReason,
)


@pytest.fixture(autouse=True)
def reset_dma_prompt_language() -> None:
    """Reset DMA prompt language around each test to avoid cross-test bleed."""

    set_prompt_language("en")
    yield
    set_prompt_language("en")


@pytest.fixture
def mock_service_registry() -> MagicMock:
    """Create a mock service registry."""

    return MagicMock()


@pytest.fixture
def mock_sink() -> MagicMock:
    """Create a mock sink for evaluator construction."""

    return MagicMock()


@pytest.fixture
def sample_thought() -> ProcessingQueueItem:
    """Create a sample processing-queue thought."""

    return ProcessingQueueItem(
        thought_id="test-thought-123",
        thought_type=ThoughtType.STANDARD,
        content=ThoughtContent(text="Can you help me interpret a lease dispute?"),
        source_task_id="test-task-456",
        thought_depth=0,
    )


@pytest.fixture
def sample_defer_result() -> ActionSelectionDMAResult:
    """Create a provisional ASPDMA DEFER result."""

    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.DEFER,
        action_parameters=DeferParams(
            channel_id="qa-channel",
            reason="Human review is required before giving legal guidance.",
            context={"capability": "legal_advice", "requested_scope": "tenant rights"},
        ),
        rationale="ASPDMA deferred because the request appears to require legal review.",
    )


class TestDSASPDMALLMResult:
    """Tests for the structured DSASPDMA result model."""

    def test_model_creation(self) -> None:
        result = DSASPDMALLMResult(
            reason_summary="Licensed legal review is required.",
            operational_reason=DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED,
            primary_need_category=DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY,
            rights_basis=["fair_trial", "access_to_justice"],
            domain_hint=DomainCategory.LEGAL,
        )

        assert result.operational_reason == DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED
        assert result.primary_need_category == DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY
        assert result.domain_hint == DomainCategory.LEGAL


class TestDSASPDMAEvaluator:
    """Tests for DSASPDMAEvaluator behavior."""

    def test_convert_result_merges_taxonomy(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_defer_result: ActionSelectionDMAResult,
    ) -> None:
        evaluator = DSASPDMAEvaluator(service_registry=mock_service_registry, sink=mock_sink)

        llm_result = DSASPDMALLMResult(
            reason_summary="Licensed legal review is required before proceeding.",
            operational_reason=DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED,
            primary_need_category=DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY,
            secondary_need_categories=[DeferralNeedCategory.IDENTITY_AND_CIVIC_PARTICIPATION],
            rights_basis=["fair_trial", "access_to_justice", "legal_aid_and_effective_remedy"],
            domain_hint=DomainCategory.LEGAL,
        )

        result = evaluator._convert_result(llm_result, sample_defer_result.action_parameters)

        assert result.selected_action == HandlerActionType.DEFER
        assert isinstance(result.action_parameters, DeferParams)
        assert result.action_parameters.reason_code == DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED
        assert result.action_parameters.needs_category == DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY
        assert result.action_parameters.secondary_needs_categories == [
            DeferralNeedCategory.IDENTITY_AND_CIVIC_PARTICIPATION
        ]
        assert result.action_parameters.rights_basis == [
            "fair_trial",
            "access_to_justice",
            "legal_aid_and_effective_remedy",
        ]
        assert result.action_parameters.domain_hint == DomainCategory.LEGAL
        assert result.action_parameters.context is not None
        assert result.action_parameters.context["primary_need_category"] == "justice_and_legal_agency"
        assert result.action_parameters.context["domain_hint"] == "LEGAL"

    def test_create_messages_uses_localized_prompt_and_taxonomy(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_thought: ProcessingQueueItem,
        sample_defer_result: ActionSelectionDMAResult,
    ) -> None:
        evaluator = DSASPDMAEvaluator(service_registry=mock_service_registry, sink=mock_sink)
        context = {"system_snapshot": {"user_profiles": [{"preferred_language": "es"}]}}

        messages = evaluator._create_messages(sample_thought, sample_defer_result, context=context)

        assert len(messages) >= 2
        system_content = "\n".join(message["content"] for message in messages if message["role"] == "system")
        user_content = "\n".join(message["content"] for message in messages if message["role"] == "user")
        assert "SELECCIÓN DE ACCIÓN ESPECÍFICA DE DEFERENCIA" in system_content
        assert "TAXONOMÍA DE DERECHOS / NECESIDADES" in user_content
        assert "Fundamento de derechos" in user_content
        assert "justice_and_legal_agency" in user_content

    @pytest.mark.asyncio
    async def test_evaluate_deferral_action_enriches_defer_params(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_thought: ProcessingQueueItem,
        sample_defer_result: ActionSelectionDMAResult,
    ) -> None:
        evaluator = DSASPDMAEvaluator(service_registry=mock_service_registry, sink=mock_sink)
        evaluator.call_llm_structured = AsyncMock(
            return_value=(
                DSASPDMALLMResult(
                    reason_summary="Licensed legal review is required before proceeding.",
                    operational_reason=DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED,
                    primary_need_category=DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY,
                    secondary_need_categories=[DeferralNeedCategory.IDENTITY_AND_CIVIC_PARTICIPATION],
                    rights_basis=["fair_trial", "access_to_justice"],
                    domain_hint=DomainCategory.LEGAL,
                ),
                None,
            )
        )

        result = await evaluator.evaluate_deferral_action(
            aspdma_result=sample_defer_result,
            original_thought=sample_thought,
        )

        assert result.selected_action == HandlerActionType.DEFER
        assert isinstance(result.action_parameters, DeferParams)
        assert result.action_parameters.domain_hint == DomainCategory.LEGAL
        assert result.action_parameters.needs_category == DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY
        assert result.action_parameters.reason_code == DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED
        assert result.rationale.startswith("DSASPDMA:")

    @pytest.mark.asyncio
    async def test_evaluate_deferral_action_requires_defer(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_thought: ProcessingQueueItem,
    ) -> None:
        evaluator = DSASPDMAEvaluator(service_registry=mock_service_registry, sink=mock_sink)
        non_defer = ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="Need more detail"),
            rationale="Not a deferral",
        )

        with pytest.raises(ValueError, match="DSASPDMA requires DEFER action"):
            await evaluator.evaluate_deferral_action(non_defer, sample_thought)
