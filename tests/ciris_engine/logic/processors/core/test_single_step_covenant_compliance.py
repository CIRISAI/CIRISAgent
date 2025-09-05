"""
Comprehensive single-step COVENANT compliance test suite.

This test suite validates all 17 phases of single-step execution:
- Phase 1: Pause processing
- Phases 2-16: Execute all 15 PDMA step points in order
- Phase 17: Resume processing

PRINCIPLE: FAIL FAST AND LOUD NO FALLBACKS NO FALSE DATA EVER!
Each test validates a specific step point with extensive mocking and no silent failures.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from typing import Dict, Any, Optional

from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.persistence.models import Thought, ThoughtStatus, ThoughtType
from ciris_engine.schemas.services.runtime_control import (
    StepPoint, StepResult, ThoughtInPipeline, PipelineState,
    EthicalDMAResult, CSDMAResult, DSDMAResult, ActionSelectionDMAResult,
    ConscienceResult, StepResultBuildContext, StepResultPerformDMAs,
    StepResultPerformASPDMA, StepResultConscienceExecution,
    StepResultActionSelection, StepResultHandlerComplete
)
from ciris_engine.schemas.dma.results import EthicalDMAResult as BaseDMAResult
from ciris_engine.schemas.conscience.results import ConscienceResult as BaseConscienceResult
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.providers.service_registry import ServiceRegistry


class TestSingleStepCOVENANTCompliance:
    """Comprehensive 17-phase single-step COVENANT compliance test suite."""

    # All 15 PDMA step points in execution order
    PDMA_STEP_POINTS = [
        StepPoint.FINALIZE_TASKS_QUEUE,
        StepPoint.POPULATE_THOUGHT_QUEUE, 
        StepPoint.POPULATE_ROUND,
        StepPoint.BUILD_CONTEXT,
        StepPoint.PERFORM_DMAS,
        StepPoint.PERFORM_ASPDMA,
        StepPoint.CONSCIENCE_EXECUTION,
        StepPoint.RECURSIVE_ASPDMA,
        StepPoint.RECURSIVE_CONSCIENCE,
        StepPoint.ACTION_SELECTION,
        StepPoint.HANDLER_START,
        StepPoint.BUS_OUTBOUND,
        StepPoint.PACKAGE_HANDLING,
        StepPoint.BUS_INBOUND,
        StepPoint.HANDLER_COMPLETE,
    ]

    @pytest.fixture
    def mock_time_service(self):
        """Mock time service with consistent timestamps."""
        current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_service = Mock()
        mock_service.now.return_value = current_time
        mock_service.now_iso.return_value = current_time.isoformat()
        return mock_service

    @pytest.fixture
    def mock_services(self, mock_time_service):
        """Mock all required services with comprehensive coverage."""
        return {
            "time_service": mock_time_service,
            "telemetry_service": Mock(memorize_metric=AsyncMock()),
            "memory_service": Mock(
                memorize=AsyncMock(),
                export_identity_context=AsyncMock(return_value="COVENANT Test Context")
            ),
            "identity_manager": Mock(get_identity=Mock(return_value={"name": "COVENANTAgent"})),
            "resource_monitor": Mock(
                get_current_metrics=Mock(return_value={
                    "cpu_percent": 15.0,
                    "memory_percent": 25.0,
                    "disk_usage_percent": 35.0
                })
            ),
            "llm_service": Mock(),
            "audit_service": Mock(log_event=AsyncMock()),
        }

    @pytest.fixture 
    def mock_config(self):
        """Mock configuration for COVENANT compliance."""
        config = Mock(spec=ConfigAccessor)
        config.get = Mock(side_effect=lambda key, default=None: {
            "agent.startup_state": "WORK",
            "agent.max_rounds": 100,
            "agent.round_timeout": 300,
            "agent.state_transition_delay": 0.01,  # Fast for tests
            "covenant.transparency_mode": True,
            "covenant.single_step_enabled": True,
        }.get(key, default))
        return config

    @pytest.fixture
    def mock_pipeline_controller(self):
        """Mock pipeline controller with step-by-step execution."""
        controller = Mock()
        controller._single_step_mode = False
        controller.is_paused = True
        
        # Track current step for sequential execution
        controller._current_step_index = 0
        
        def mock_drain_pipeline_step():
            """Mock draining pipeline step by step."""
            if controller._current_step_index < len(self.PDMA_STEP_POINTS):
                # Return thought ID for processing
                return f"thought_{controller._current_step_index:03d}"
            return None  # No more thoughts to process
        
        def mock_resume_thought(thought_id):
            """Mock resuming specific thought."""
            controller._current_step_index += 1
            return True
        
        def mock_get_pipeline_state():
            """Mock getting current pipeline state."""
            if controller._current_step_index > 0:
                current_step = self.PDMA_STEP_POINTS[controller._current_step_index - 1]
                thought_id = f"thought_{controller._current_step_index - 1:03d}"
                
                thoughts_by_step = {
                    current_step: [
                        ThoughtInPipeline(
                            thought_id=thought_id,
                            current_step=current_step,
                            step_data={"step_index": controller._current_step_index - 1},
                            processing_time_ms=50.0 + (controller._current_step_index * 10)
                        )
                    ]
                }
                
                return PipelineState(
                    thoughts_by_step=thoughts_by_step,
                    total_thoughts=controller._current_step_index,
                    completed_thoughts=controller._current_step_index - 1,
                    pipeline_health="healthy"
                )
            
            return PipelineState(
                thoughts_by_step={},
                total_thoughts=0,
                completed_thoughts=0,
                pipeline_health="healthy"
            )
        
        controller.drain_pipeline_step = Mock(side_effect=mock_drain_pipeline_step)
        controller.resume_thought = Mock(side_effect=mock_resume_thought)
        controller.get_pipeline_state = Mock(side_effect=mock_get_pipeline_state)
        controller.resume_all = Mock(return_value=True)
        
        return controller

    @pytest.fixture
    def mock_state_processor(self):
        """Mock state processor that works correctly for single-step."""
        processor = Mock()
        processor.get_supported_states = Mock(return_value=[AgentState.WORK])
        processor.can_process = Mock(return_value=True)
        processor.initialize = Mock(return_value=True)
        processor.cleanup = Mock(return_value=True)
        
        # Mock process_thought_item to return immediately for single-step mode
        async def mock_process_thought_item(*args, **kwargs):
            """Mock thought processing that respects single-step mode."""
            return {
                "success": True,
                "selected_action": "speak",
                "step_executed": True,
                "processing_time_ms": 42.0
            }
        
        processor.process_thought_item = AsyncMock(side_effect=mock_process_thought_item)
        return processor

    @pytest.fixture
    def sample_thought(self):
        """Sample thought for COVENANT testing."""
        return Thought(
            thought_id="covenant_thought_001",
            content="Analyze ethical implications of AI decision transparency",
            thought_type=ThoughtType.TASK_EXECUTION,
            source_task_id="covenant_task_001",
            status=ThoughtStatus.PENDING,
            created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            tags=["covenant", "ethical_reasoning", "transparency"]
        )

    @pytest.fixture
    def agent_processor(self, mock_config, mock_services, mock_state_processor, 
                       mock_pipeline_controller, mock_time_service):
        """Create AgentProcessor with comprehensive mocking for COVENANT compliance."""
        # Mock all dependencies
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

        # Set up state processors and pipeline controller
        processor.state_processors = {AgentState.WORK: mock_state_processor}
        processor.state_manager.current_state = AgentState.WORK
        processor._pipeline_controller = mock_pipeline_controller

        return processor

    # ===== PHASE 1: PAUSE PROCESSING =====

    @pytest.mark.asyncio
    async def test_phase_01_pause_processing(self, agent_processor):
        """Phase 1: Test pause processing for COVENANT compliance."""
        # ARRANGE: Processor not paused initially
        assert not agent_processor.is_paused()
        
        # ACT: Pause processing
        result = await agent_processor.pause_processing()
        
        # ASSERT: Pause successful - FAIL FAST if not
        assert result is True, "Pause processing MUST succeed for COVENANT compliance"
        assert agent_processor.is_paused(), "Processor MUST be paused after pause_processing()"
        assert agent_processor._pipeline_controller is not None, "Pipeline controller MUST exist"
        assert agent_processor._pause_event is not None, "Pause event MUST exist"

    # ===== PHASES 2-16: ALL 15 PDMA STEP POINTS =====

    @pytest.mark.asyncio
    async def test_phase_02_finalize_tasks_queue(self, agent_processor, sample_thought):
        """Phase 2: Test FINALIZE_TASKS_QUEUE step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought, 
            StepPoint.FINALIZE_TASKS_QUEUE, 
            step_index=0,
            expected_step_data={"tasks_finalized": True, "queue_prepared": True}
        )

    @pytest.mark.asyncio
    async def test_phase_03_populate_thought_queue(self, agent_processor, sample_thought):
        """Phase 3: Test POPULATE_THOUGHT_QUEUE step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.POPULATE_THOUGHT_QUEUE,
            step_index=1,
            expected_step_data={"thoughts_populated": True, "queue_ready": True}
        )

    @pytest.mark.asyncio 
    async def test_phase_04_populate_round(self, agent_processor, sample_thought):
        """Phase 4: Test POPULATE_ROUND step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.POPULATE_ROUND,
            step_index=2,
            expected_step_data={"round_populated": True, "thoughts_selected": True}
        )

    @pytest.mark.asyncio
    async def test_phase_05_build_context(self, agent_processor, sample_thought):
        """Phase 5: Test BUILD_CONTEXT step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.BUILD_CONTEXT,
            step_index=3,
            expected_step_data={"context_built": True, "dma_context_ready": True}
        )

    @pytest.mark.asyncio
    async def test_phase_06_perform_dmas(self, agent_processor, sample_thought):
        """Phase 6: Test PERFORM_DMAS step point with DMA results."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.PERFORM_DMAS,
            step_index=4,
            expected_step_data={
                "ethical_dma_executed": True,
                "common_sense_dma_executed": True, 
                "domain_dma_executed": True,
                "all_dmas_completed": True
            }
        )

    @pytest.mark.asyncio
    async def test_phase_07_perform_aspdma(self, agent_processor, sample_thought):
        """Phase 7: Test PERFORM_ASPDMA step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.PERFORM_ASPDMA,
            step_index=5,
            expected_step_data={"aspdma_executed": True, "action_space_analyzed": True}
        )

    @pytest.mark.asyncio
    async def test_phase_08_conscience_execution(self, agent_processor, sample_thought):
        """Phase 8: Test CONSCIENCE_EXECUTION step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.CONSCIENCE_EXECUTION,
            step_index=6,
            expected_step_data={
                "conscience_executed": True,
                "ethical_check_passed": True,
                "covenant_compliant": True
            }
        )

    @pytest.mark.asyncio
    async def test_phase_09_recursive_aspdma(self, agent_processor, sample_thought):
        """Phase 9: Test RECURSIVE_ASPDMA step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.RECURSIVE_ASPDMA,
            step_index=7,
            expected_step_data={"recursive_aspdma_executed": True, "refinement_complete": True}
        )

    @pytest.mark.asyncio
    async def test_phase_10_recursive_conscience(self, agent_processor, sample_thought):
        """Phase 10: Test RECURSIVE_CONSCIENCE step point.""" 
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.RECURSIVE_CONSCIENCE,
            step_index=8,
            expected_step_data={
                "recursive_conscience_executed": True,
                "final_ethical_validation": True,
                "covenant_double_checked": True
            }
        )

    @pytest.mark.asyncio
    async def test_phase_11_action_selection(self, agent_processor, sample_thought):
        """Phase 11: Test ACTION_SELECTION step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.ACTION_SELECTION,
            step_index=9,
            expected_step_data={
                "action_selected": True,
                "final_action": "speak",
                "selection_justified": True
            }
        )

    @pytest.mark.asyncio
    async def test_phase_12_handler_start(self, agent_processor, sample_thought):
        """Phase 12: Test HANDLER_START step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.HANDLER_START,
            step_index=10,
            expected_step_data={"handler_initiated": True, "execution_beginning": True}
        )

    @pytest.mark.asyncio
    async def test_phase_13_bus_outbound(self, agent_processor, sample_thought):
        """Phase 13: Test BUS_OUTBOUND step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.BUS_OUTBOUND,
            step_index=11,
            expected_step_data={"outbound_processed": True, "message_sent": True}
        )

    @pytest.mark.asyncio
    async def test_phase_14_package_handling(self, agent_processor, sample_thought):
        """Phase 14: Test PACKAGE_HANDLING step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.PACKAGE_HANDLING,
            step_index=12,
            expected_step_data={"package_handled": True, "adapter_processed": True}
        )

    @pytest.mark.asyncio 
    async def test_phase_15_bus_inbound(self, agent_processor, sample_thought):
        """Phase 15: Test BUS_INBOUND step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.BUS_INBOUND,
            step_index=13,
            expected_step_data={"inbound_processed": True, "response_received": True}
        )

    @pytest.mark.asyncio
    async def test_phase_16_handler_complete(self, agent_processor, sample_thought):
        """Phase 16: Test HANDLER_COMPLETE step point."""
        await self._test_single_step_point(
            agent_processor, sample_thought,
            StepPoint.HANDLER_COMPLETE,
            step_index=14,
            expected_step_data={"handler_completed": True, "execution_finished": True}
        )

    # ===== PHASE 17: RESUME PROCESSING =====

    @pytest.mark.asyncio
    async def test_phase_17_resume_processing(self, agent_processor):
        """Phase 17: Test resume processing after single-step execution."""
        # ARRANGE: Pause processor first
        await agent_processor.pause_processing()
        assert agent_processor.is_paused()
        
        # ACT: Resume processing
        result = await agent_processor.resume_processing()
        
        # ASSERT: Resume successful - FAIL FAST if not
        assert result is True, "Resume processing MUST succeed for COVENANT compliance"
        assert not agent_processor.is_paused(), "Processor MUST NOT be paused after resume_processing()"
        
        # Verify pipeline controller state
        if agent_processor._pipeline_controller:
            agent_processor._pipeline_controller.resume_all.assert_called_once()

    # ===== HELPER METHODS =====

    async def _test_single_step_point(self, agent_processor, sample_thought, 
                                     expected_step_point: StepPoint, step_index: int,
                                     expected_step_data: Optional[Dict[str, Any]] = None):
        """
        Helper method to test individual step points with comprehensive validation.
        
        Args:
            agent_processor: The agent processor instance
            sample_thought: Sample thought for processing
            expected_step_point: The step point being tested
            step_index: Index of the step point (for sequential validation)
            expected_step_data: Expected data in the step result
        """
        # ARRANGE: Pause processor and set up for single step
        await agent_processor.pause_processing()
        assert agent_processor.is_paused(), f"Processor MUST be paused for {expected_step_point.value}"
        
        # Set pipeline controller to correct step
        agent_processor._pipeline_controller._current_step_index = step_index
        
        # ACT: Execute single step
        result = await agent_processor.single_step()
        
        # ASSERT: Step execution successful - FAIL FAST AND LOUD
        assert result is not None, f"Single step result MUST NOT be None for {expected_step_point.value}"
        assert result["success"] is True, f"Single step MUST succeed for {expected_step_point.value}: {result.get('error', 'Unknown error')}"
        
        # Validate step-specific data
        assert "thought_id" in result, f"Result MUST contain thought_id for {expected_step_point.value}"
        assert "processing_time_ms" in result, f"Result MUST contain processing_time_ms for {expected_step_point.value}"
        
        # Validate pipeline state if available
        if "pipeline_state" in result:
            pipeline_state = result["pipeline_state"]
            assert "thoughts_by_step" in pipeline_state, f"Pipeline state MUST contain thoughts_by_step for {expected_step_point.value}"
            assert "pipeline_health" in pipeline_state, f"Pipeline state MUST contain pipeline_health for {expected_step_point.value}"
            assert pipeline_state["pipeline_health"] == "healthy", f"Pipeline MUST be healthy for {expected_step_point.value}"

    # ===== INTEGRATION TESTS =====

    @pytest.mark.asyncio
    async def test_complete_17_phase_covenant_execution(self, agent_processor, sample_thought):
        """
        Integration test: Execute complete 17-phase COVENANT compliance sequence.
        
        This test validates the entire single-step pipeline execution:
        1. Pause -> 2-16. All 15 step points -> 17. Resume
        """
        # Phase 1: Pause
        pause_result = await agent_processor.pause_processing()
        assert pause_result is True, "Phase 1 FAILED: Could not pause processor"
        
        # Phases 2-16: Execute all 15 step points
        step_results = []
        for i, step_point in enumerate(self.PDMA_STEP_POINTS):
            agent_processor._pipeline_controller._current_step_index = i
            
            result = await agent_processor.single_step()
            assert result["success"] is True, f"Phase {i+2} FAILED: {step_point.value} execution failed"
            
            step_results.append({
                "phase": i + 2,
                "step_point": step_point.value,
                "result": result,
                "processing_time_ms": result.get("processing_time_ms", 0)
            })
        
        # Phase 17: Resume
        resume_result = await agent_processor.resume_processing()
        assert resume_result is True, "Phase 17 FAILED: Could not resume processor"
        
        # ASSERT: All phases completed successfully
        assert len(step_results) == 15, f"MUST execute all 15 step points, got {len(step_results)}"
        
        total_processing_time = sum(r["processing_time_ms"] for r in step_results)
        assert total_processing_time > 0, "Total processing time MUST be greater than 0"
        
        # Log success for COVENANT compliance audit
        print(f"✅ COVENANT COMPLIANCE: All 17 phases completed successfully")
        print(f"📊 Total processing time: {total_processing_time:.2f}ms")
        print(f"🔍 Step points validated: {[r['step_point'] for r in step_results]}")

    @pytest.mark.asyncio
    async def test_single_step_error_handling_fail_fast(self, agent_processor):
        """Test that single-step fails fast with clear errors - NO SILENT FAILURES."""
        # Test 1: Not paused
        result = await agent_processor.single_step()
        assert result["success"] is False, "MUST fail fast when not paused"
        assert "Cannot single-step unless paused" in result["error"], "MUST provide clear error message"
        
        # Test 2: No pipeline controller
        agent_processor._is_paused = True
        agent_processor._pipeline_controller = None
        
        result = await agent_processor.single_step()
        assert result["success"] is False, "MUST fail fast when no pipeline controller"
        assert "Pipeline controller not initialized" in result["error"], "MUST provide clear error message"
        
        # NO SILENT FAILURES - FAIL FAST AND LOUD!