"""Shared fixtures for processor support tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
from ciris_engine.logic.dma.csdma import CSDMAEvaluator
from ciris_engine.logic.dma.dsdma_base import BaseDSDMA
from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator
from ciris_engine.logic.processors.support.dma_orchestrator import DMAOrchestrator
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.runtime.enums import ThoughtType


@pytest.fixture
def mock_time_service():
    """Mock time service that returns consistent UTC time."""
    time_service = MagicMock()
    time_service.now.return_value = datetime(2025, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    return time_service


@pytest.fixture
def mock_ethical_pdma():
    """Mock Ethical PDMA evaluator."""
    evaluator = MagicMock(spec=EthicalPDMAEvaluator)
    return evaluator


@pytest.fixture
def mock_csdma():
    """Mock Common Sense DMA evaluator."""
    evaluator = MagicMock(spec=CSDMAEvaluator)
    return evaluator


@pytest.fixture
def mock_dsdma():
    """Mock Domain-Specific DMA evaluator."""
    evaluator = MagicMock(spec=BaseDSDMA)
    return evaluator


@pytest.fixture
def mock_action_selection_pdma():
    """Mock Action Selection PDMA evaluator."""
    evaluator = MagicMock(spec=ActionSelectionPDMAEvaluator)
    return evaluator


@pytest.fixture
def mock_app_config():
    """Mock application configuration."""
    config = MagicMock()
    config.workflow.DMA_RETRY_LIMIT = 3
    config.workflow.DMA_TIMEOUT_SECONDS = 30.0
    config.workflow.max_rounds = 5
    return config


@pytest.fixture
def dma_orchestrator(
    mock_ethical_pdma,
    mock_csdma,
    mock_dsdma,
    mock_action_selection_pdma,
    mock_time_service,
    mock_app_config,
):
    """Create DMAOrchestrator with all mock dependencies."""
    return DMAOrchestrator(
        ethical_pdma_evaluator=mock_ethical_pdma,
        csdma_evaluator=mock_csdma,
        dsdma=mock_dsdma,
        action_selection_pdma_evaluator=mock_action_selection_pdma,
        time_service=mock_time_service,
        app_config=mock_app_config,
    )


@pytest.fixture
def sample_thought_item():
    """Create a sample processing queue item.

    Reuses the standard pattern from tests/ciris_engine/logic/processors/core/conftest.py
    """
    content = ThoughtContent(text="Test thought content")
    return ProcessingQueueItem(
        thought_id="thought_123",
        source_task_id="task_123",
        thought_type=ThoughtType.STANDARD,
        content=content,
        thought_depth=0,
    )


@pytest.fixture
def sample_processing_context():
    """Create a sample processing context."""
    context = MagicMock()
    context.system_snapshot = MagicMock()
    context.system_snapshot.channel_context = "test_channel"
    context.initial_task_context = None
    context.is_conscience_retry = False
    return context


# DMA Result Helpers


@pytest.fixture
def sample_ethical_result():
    """Create a valid Ethical PDMA result."""
    from ciris_engine.schemas.dma.results import EthicalDMAResult

    return EthicalDMAResult(
        stakeholders="user, system, community",
        conflicts="none",
        reasoning="Ethically sound action with no conflicts",
        alignment_check="Aligns with all CIRIS principles",
    )


@pytest.fixture
def sample_csdma_result():
    """Create a valid CSDMA result."""
    from ciris_engine.schemas.dma.results import CSDMAResult

    return CSDMAResult(
        plausibility_score=0.85,
        flags=[],
        reasoning="Common sense check passed",
    )


@pytest.fixture
def sample_dsdma_result():
    """Create a valid DSDMA result."""
    from ciris_engine.schemas.dma.results import DSDMAResult

    return DSDMAResult(
        domain="general",
        domain_alignment=0.8,
        flags=[],
        reasoning="Within domain expertise",
    )


@pytest.fixture
def sample_action_selection_result():
    """Create a valid Action Selection result."""
    from ciris_engine.schemas.actions import SpeakParams
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="Test response"),
        rationale="Best action based on DMA results",
        reasoning="Detailed reasoning process",
    )


@pytest.fixture
def sample_initial_dma_results(sample_ethical_result, sample_csdma_result, sample_dsdma_result):
    """Create complete initial DMA results."""
    from ciris_engine.schemas.processors.dma import InitialDMAResults

    return InitialDMAResults(
        ethical_pdma=sample_ethical_result,
        csdma=sample_csdma_result,
        dsdma=sample_dsdma_result,
    )
