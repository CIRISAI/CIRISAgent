"""
Unit test to validate and document the single-step hang bug.

This test demonstrates the deadlock that occurs when single_step() calls
_process_single_thought() while the processor is paused, causing infinite hang.

PRINCIPLE: FAIL FAST AND LOUD NO FALLBACKS NO FALSE DATA EVER!
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.persistence.models import Thought, ThoughtStatus, ThoughtType
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.providers.service_registry import ServiceRegistry


class TestSingleStepHangValidation:
    """Test to validate and document the single-step hang bug."""

    @pytest.fixture
    def mock_time_service(self):
        """Mock time service."""
        current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_service = Mock()
        mock_service.now.return_value = current_time
        mock_service.now_iso.return_value = current_time.isoformat()
        return mock_service

    @pytest.fixture
    def mock_services(self, mock_time_service):
        """Mock all required services."""
        return {
            "time_service": mock_time_service,
            "telemetry_service": Mock(memorize_metric=AsyncMock()),
            "memory_service": Mock(
                memorize=AsyncMock(),
                export_identity_context=AsyncMock(return_value="Test identity context")
            ),
            "identity_manager": Mock(get_identity=Mock(return_value={"name": "TestAgent"})),
            "resource_monitor": Mock(
                get_current_metrics=Mock(return_value={
                    "cpu_percent": 10.0,
                    "memory_percent": 20.0,
                    "disk_usage_percent": 30.0
                })
            ),
            "llm_service": Mock(),
            "audit_service": Mock(log_event=AsyncMock()),
        }

    @pytest.fixture 
    def mock_config(self):
        """Mock configuration."""
        config = Mock(spec=ConfigAccessor)
        config.get = Mock(side_effect=lambda key, default=None: {
            "agent.startup_state": "WORK",
            "agent.max_rounds": 100,
            "agent.round_timeout": 300,
            "agent.state_transition_delay": 0.1,  # Faster for tests
        }.get(key, default))
        return config

    @pytest.fixture
    def mock_state_processor(self):
        """Mock state processor that hangs when called."""
        processor = Mock()
        processor.get_supported_states = Mock(return_value=[AgentState.WORK])
        processor.can_process = Mock(return_value=True)
        processor.initialize = Mock(return_value=True)
        processor.cleanup = Mock(return_value=True)
        
        # This is the hanging method - simulate deadlock
        async def hanging_process_thought_item(*args, **kwargs):
            """Simulate the hanging behavior that causes deadlock."""
            # This would hang indefinitely in real scenario
            await asyncio.sleep(10)  # Long enough to timeout test
            return {"success": False, "error": "Should not reach here"}
        
        processor.process_thought_item = AsyncMock(side_effect=hanging_process_thought_item)
        return processor

    @pytest.fixture
    def sample_thought(self):
        """Sample thought for testing."""
        return Thought(
            thought_id="test_thought_001",
            content="Test thought content",
            thought_type=ThoughtType.TASK_EXECUTION,
            source_task_id="task_001",
            status=ThoughtStatus.PENDING,
            created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )

    @pytest.fixture
    def agent_processor(self, mock_config, mock_services, mock_state_processor, mock_time_service):
        """Create AgentProcessor with mocked dependencies."""
        # Mock required dependencies
        mock_app_config = Mock()
        mock_thought_processor = Mock(spec=ThoughtProcessor)
        mock_action_dispatcher = Mock()
        mock_service_registry = Mock(spec=ServiceRegistry)

        # Create the processor
        processor = AgentProcessor(
            config=mock_config,
            app_config=mock_app_config,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            service_registry=mock_service_registry,
            **mock_services
        )

        # Set up state processors
        processor.state_processors = {AgentState.WORK: mock_state_processor}
        processor.state_manager.current_state = AgentState.WORK

        return processor

    @pytest.mark.asyncio
    async def test_single_step_hangs_when_not_paused(self, agent_processor):
        """Test that single_step fails fast when processor not paused."""
        # ARRANGE: Processor is not paused
        assert not agent_processor.is_paused()
        
        # ACT: Call single_step
        result = await agent_processor.single_step()
        
        # ASSERT: Fails fast with clear error - NO HANG
        assert result["success"] is False
        assert "Cannot single-step unless paused" in result["error"]
        # Should return immediately, not hang

    @pytest.mark.asyncio 
    async def test_single_step_hangs_when_no_pipeline_controller(self, agent_processor):
        """Test that single_step fails fast when no pipeline controller."""
        # ARRANGE: Pause processor but don't set up pipeline controller
        agent_processor._is_paused = True
        agent_processor._pipeline_controller = None
        
        # ACT: Call single_step
        result = await agent_processor.single_step()
        
        # ASSERT: Fails fast with clear error - NO HANG
        assert result["success"] is False
        assert "Pipeline controller not initialized" in result["error"]

    @pytest.mark.asyncio
    async def test_single_step_deadlock_with_paused_processor(self, agent_processor, sample_thought):
        """
        CRITICAL TEST: Demonstrates the deadlock bug in single_step().
        
        This test validates that the current implementation hangs when:
        1. Processor is paused
        2. Pipeline controller exists  
        3. There are pending thoughts
        4. single_step() calls _process_single_thought()
        5. _process_single_thought() calls processor.process_thought_item()
        6. State processor tries to run full pipeline while paused -> DEADLOCK
        """
        # ARRANGE: Set up the deadlock scenario
        await agent_processor.pause_processing()
        assert agent_processor.is_paused()
        assert agent_processor._pipeline_controller is not None
        
        # Mock persistence to return pending thought
        with patch('ciris_engine.logic.persistence.get_thoughts_by_status') as mock_get_thoughts:
            mock_get_thoughts.return_value = [sample_thought]
            
            # Mock pipeline controller methods
            agent_processor._pipeline_controller.drain_pipeline_step = Mock(return_value=None)
            agent_processor._pipeline_controller.get_pipeline_state = Mock(return_value=Mock(
                thoughts_by_step={}, dict=Mock(return_value={})
            ))
            
            # ACT: Call single_step with timeout to catch deadlock
            with pytest.raises(asyncio.TimeoutError):
                # This should hang indefinitely due to deadlock
                await asyncio.wait_for(agent_processor.single_step(), timeout=2.0)
            
            # ASSERT: The hang demonstrates the bug
            # If we reach here, the test proves the deadlock exists
            # The fix will make this test pass without timeout

    @pytest.mark.asyncio
    async def test_pause_processing_works_correctly(self, agent_processor):
        """Test that pause_processing works without hanging."""
        # ARRANGE: Processor not paused
        assert not agent_processor.is_paused()
        
        # ACT: Pause processing
        result = await agent_processor.pause_processing()
        
        # ASSERT: Pause succeeds
        assert result is True
        assert agent_processor.is_paused()
        assert agent_processor._pipeline_controller is not None
        assert agent_processor._pause_event is not None

    @pytest.mark.asyncio  
    async def test_resume_processing_works_correctly(self, agent_processor):
        """Test that resume_processing works correctly."""
        # ARRANGE: Pause first
        await agent_processor.pause_processing()
        assert agent_processor.is_paused()
        
        # ACT: Resume processing
        result = await agent_processor.resume_processing()
        
        # ASSERT: Resume succeeds
        assert result is True
        assert not agent_processor.is_paused()

    @pytest.mark.asyncio
    async def test_single_step_with_empty_pipeline(self, agent_processor):
        """Test single_step behavior with empty pipeline and no pending thoughts."""
        # ARRANGE: Paused processor with empty pipeline
        await agent_processor.pause_processing()
        
        # Mock empty pipeline and no pending thoughts
        agent_processor._pipeline_controller.drain_pipeline_step = Mock(return_value=None)
        
        with patch('ciris_engine.logic.persistence.get_thoughts_by_status') as mock_get_thoughts:
            mock_get_thoughts.return_value = []  # No pending thoughts
            
            # ACT: Call single_step
            result = await agent_processor.single_step()
            
            # ASSERT: Returns success with pipeline_empty flag
            assert result["success"] is True
            assert result["pipeline_empty"] is True
            assert "No thoughts to process" in result["message"]
            assert "processing_time_ms" in result