"""Type safety validation tests for ThoughtProcessor.

Note: This test will be enhanced after protocol definitions are merged.
Currently validates that mock objects can be created and passed to ThoughtProcessor.
"""

import pytest

from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
from tests.fixtures.processor_mocks import MockConscienceRegistry, MockContextBuilder, MockDMAOrchestrator


def test_thought_processor_accepts_mock_implementations():
    """Verify ThoughtProcessor accepts mock implementations."""
    # This test validates that our mock implementations can be passed to ThoughtProcessor
    # After Workstream 2 protocols are merged, mypy will validate protocol compliance
    processor = ThoughtProcessor(
        dma_orchestrator=MockDMAOrchestrator(),
        context_builder=MockContextBuilder(),
        conscience_registry=MockConscienceRegistry(),
        app_config=None,  # type: ignore[arg-type]
        dependencies=None,  # type: ignore[arg-type]
        time_service=None,  # type: ignore[arg-type]
    )
    assert processor is not None
    assert processor.dma_orchestrator is not None
    assert processor.context_builder is not None
    assert processor.conscience_registry is not None


# Note: Mypy will validate protocol compliance at CI time after merge
# The test itself just ensures the objects can be created
