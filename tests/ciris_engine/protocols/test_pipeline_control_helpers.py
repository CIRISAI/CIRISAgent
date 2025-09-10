"""Unit tests for pipeline control helper functions.

Tests for functions extracted during complexity refactoring to improve maintainability
and test coverage of individual components.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pytest

from ciris_engine.protocols.pipeline_control import PipelineController
from ciris_engine.schemas.services.runtime_control import PipelineState


class TestPipelineControllerHelpers:
    """Test suite for pipeline controller helper functions."""
    
    @pytest.fixture
    def pipeline_controller(self):
        """Create a pipeline controller instance for testing."""
        main_processor = Mock()
        controller = PipelineController(is_paused=False, main_processor=main_processor)
        return controller

    def test_get_pipeline_state_dict_with_dict_method(self, pipeline_controller):
        """Test pipeline state dict extraction when object has dict method."""
        # Arrange
        pipeline_state = Mock()
        pipeline_state.dict.return_value = {"state": "active", "paused_count": 0}
        
        pipeline_controller.get_pipeline_state = Mock(return_value=pipeline_state)

        # Act
        result = pipeline_controller._get_pipeline_state_dict()

        # Assert
        assert result == {"state": "active", "paused_count": 0}
        pipeline_state.dict.assert_called_once()

    def test_get_pipeline_state_dict_without_dict_method(self, pipeline_controller):
        """Test pipeline state dict extraction when object lacks dict method."""
        # Arrange
        pipeline_state = "simple_state_object"  # No dict method
        pipeline_controller.get_pipeline_state = Mock(return_value=pipeline_state)

        # Act
        result = pipeline_controller._get_pipeline_state_dict()

        # Assert
        assert result == {}

    @patch('asyncio.get_event_loop')
    def test_calculate_processing_time(self, mock_get_loop, pipeline_controller):
        """Test processing time calculation in milliseconds."""
        # Arrange
        mock_loop = Mock()
        mock_loop.time.return_value = 1000.5  # Current time
        mock_get_loop.return_value = mock_loop
        
        start_time = 1000.0  # Start time

        # Act
        result = pipeline_controller._calculate_processing_time(start_time)

        # Assert
        assert result == 500.0  # (1000.5 - 1000.0) * 1000 = 500ms

    @pytest.mark.asyncio
    async def test_handle_paused_thoughts_success(self, pipeline_controller):
        """Test handling of paused thoughts when execution succeeds."""
        # Arrange
        start_time = 1000.0
        
        mock_result = {
            "success": True,
            "message": "Advanced 2 thoughts",
            "thoughts_advanced": 2
        }
        
        with patch('ciris_engine.logic.processors.core.step_decorators.execute_all_steps') as mock_execute:
            mock_execute.return_value = mock_result
            
            with patch.object(pipeline_controller, '_calculate_processing_time', return_value=250.0):
                with patch.object(pipeline_controller, '_get_pipeline_state_dict', return_value={"state": "active"}):
                    # Act
                    result = await pipeline_controller._handle_paused_thoughts(start_time)

        # Assert
        assert result["success"] is True
        assert result["step_point"] == "resume_paused_thoughts"
        assert result["message"] == "Advanced 2 thoughts"
        assert result["thoughts_advanced"] == 2
        assert result["step_results"] == [{"thoughts_advanced": 2, "message": "Advanced 2 thoughts"}]
        assert result["processing_time_ms"] == 250.0
        assert result["pipeline_state"] == {"state": "active"}

    @pytest.mark.asyncio
    async def test_handle_paused_thoughts_failure(self, pipeline_controller):
        """Test handling of paused thoughts when execution fails."""
        # Arrange
        start_time = 1000.0
        
        mock_result = {
            "success": False,
            "message": "Failed to advance thoughts",
            "thoughts_advanced": 0
        }
        
        with patch('ciris_engine.logic.processors.core.step_decorators.execute_all_steps') as mock_execute:
            mock_execute.return_value = mock_result
            
            with patch.object(pipeline_controller, '_calculate_processing_time', return_value=100.0):
                with patch.object(pipeline_controller, '_get_pipeline_state_dict', return_value={"state": "error"}):
                    # Act
                    result = await pipeline_controller._handle_paused_thoughts(start_time)

        # Assert
        assert result["success"] is False
        assert result["step_point"] == "resume_paused_thoughts"
        assert result["message"] == "Failed to advance thoughts"
        assert result["thoughts_advanced"] == 0
        assert result["processing_time_ms"] == 100.0
        assert result["pipeline_state"] == {"state": "error"}

    def test_handle_no_pending_thoughts(self, pipeline_controller):
        """Test handling when no pending thoughts are available."""
        # Arrange
        start_time = 1000.0
        
        with patch.object(pipeline_controller, '_calculate_processing_time', return_value=50.0):
            with patch.object(pipeline_controller, '_get_pipeline_state_dict', return_value={"state": "idle"}):
                # Act
                result = pipeline_controller._handle_no_pending_thoughts(start_time)

        # Assert
        assert result["success"] is True
        assert result["step_point"] == "no_work"
        assert result["message"] == "No pending thoughts to process"
        assert result["thoughts_advanced"] == 0
        assert result["step_results"] == []
        assert result["processing_time_ms"] == 50.0
        assert result["pipeline_state"] == {"state": "idle"}

    def test_handle_successful_initiation(self, pipeline_controller):
        """Test handling successful thought processing initiation."""
        # Arrange
        start_time = 1000.0
        thought = Mock()
        thought.thought_id = "thought-123"
        
        with patch.object(pipeline_controller, '_calculate_processing_time', return_value=150.0):
            with patch.object(pipeline_controller, '_get_pipeline_state_dict', return_value={"state": "processing"}):
                # Act
                result = pipeline_controller._handle_successful_initiation(thought, start_time)

        # Assert
        assert result["success"] is True
        assert result["step_point"] == "initiate_processing"
        assert result["message"] == "Initiated processing for thought thought-123 - will pause at first step"
        assert result["thought_id"] == "thought-123"
        assert result["step_results"] == [{"thought_id": "thought-123", "initiated": True}]
        assert result["processing_time_ms"] == 150.0
        assert result["pipeline_state"] == {"state": "processing"}

    def test_handle_initiation_error(self, pipeline_controller):
        """Test handling error during thought processing initiation."""
        # Arrange
        start_time = 1000.0
        error = Exception("Processing failed")
        
        with patch.object(pipeline_controller, '_calculate_processing_time', return_value=75.0):
            with patch.object(pipeline_controller, '_get_pipeline_state_dict', return_value={"state": "error"}):
                # Act
                result = pipeline_controller._handle_initiation_error(error, start_time)

        # Assert
        assert result["success"] is False
        assert result["step_point"] == "error"
        assert result["message"] == "Error initiating processing: Processing failed"
        assert result["step_results"] == []
        assert result["processing_time_ms"] == 75.0
        assert result["pipeline_state"] == {"state": "error"}

    def test_handle_no_processor(self, pipeline_controller):
        """Test handling when no thought processor is available."""
        # Arrange
        start_time = 1000.0
        
        with patch.object(pipeline_controller, '_calculate_processing_time', return_value=25.0):
            with patch.object(pipeline_controller, '_get_pipeline_state_dict', return_value={"state": "no_processor"}):
                # Act
                result = pipeline_controller._handle_no_processor(start_time)

        # Assert
        assert result["success"] is False
        assert result["step_point"] == "error"
        assert result["message"] == "No thought processor available"
        assert result["step_results"] == []
        assert result["processing_time_ms"] == 25.0
        assert result["pipeline_state"] == {"state": "no_processor"}

    @pytest.mark.asyncio
    async def test_initiate_thought_processing_with_processor(self, pipeline_controller):
        """Test thought processing initiation when processor is available."""
        # Arrange
        start_time = 1000.0
        thought = Mock()
        thought.thought_id = "thought-456"
        
        # Set up main processor with thought processor
        pipeline_controller.main_processor = Mock()
        pipeline_controller.main_processor.thought_processor = Mock()
        
        with patch.object(pipeline_controller, '_handle_successful_initiation') as mock_success:
            mock_success.return_value = {"success": True}
            
            # Act
            result = await pipeline_controller._initiate_thought_processing(thought, start_time)

        # Assert
        mock_success.assert_called_once_with(thought, start_time)
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_initiate_thought_processing_no_main_processor(self, pipeline_controller):
        """Test thought processing initiation when main processor is None."""
        # Arrange
        start_time = 1000.0
        thought = Mock()
        
        pipeline_controller.main_processor = None
        
        with patch.object(pipeline_controller, '_handle_no_processor') as mock_no_processor:
            mock_no_processor.return_value = {"success": False, "error": "no_processor"}
            
            # Act
            result = await pipeline_controller._initiate_thought_processing(thought, start_time)

        # Assert
        mock_no_processor.assert_called_once_with(start_time)
        assert result == {"success": False, "error": "no_processor"}

    @pytest.mark.asyncio
    async def test_initiate_thought_processing_no_thought_processor(self, pipeline_controller):
        """Test thought processing initiation when thought processor is None."""
        # Arrange
        start_time = 1000.0
        thought = Mock()
        
        pipeline_controller.main_processor = Mock()
        pipeline_controller.main_processor.thought_processor = None
        
        with patch.object(pipeline_controller, '_handle_no_processor') as mock_no_processor:
            mock_no_processor.return_value = {"success": False, "error": "no_thought_processor"}
            
            # Act
            result = await pipeline_controller._initiate_thought_processing(thought, start_time)

        # Assert
        mock_no_processor.assert_called_once_with(start_time)
        assert result == {"success": False, "error": "no_thought_processor"}

    @pytest.mark.asyncio
    async def test_initiate_thought_processing_with_exception(self, pipeline_controller):
        """Test thought processing initiation when an exception occurs."""
        # Arrange
        start_time = 1000.0
        thought = Mock()
        
        pipeline_controller.main_processor = Mock()
        pipeline_controller.main_processor.thought_processor = Mock()
        
        # Mock _handle_successful_initiation to raise an exception
        exception = RuntimeError("Unexpected error")
        
        with patch.object(pipeline_controller, '_handle_successful_initiation', side_effect=exception):
            with patch.object(pipeline_controller, '_handle_initiation_error') as mock_error:
                mock_error.return_value = {"success": False, "error": "runtime_error"}
                
                # Act
                result = await pipeline_controller._initiate_thought_processing(thought, start_time)

        # Assert
        mock_error.assert_called_once_with(exception, start_time)
        assert result == {"success": False, "error": "runtime_error"}

    @pytest.mark.asyncio
    async def test_execute_single_step_point_integration_with_paused_thoughts(self, pipeline_controller):
        """Test complete execute_single_step_point flow with paused thoughts."""
        # Arrange
        with patch('ciris_engine.logic.processors.core.step_decorators.enable_single_step_mode') as mock_enable:
            with patch('ciris_engine.logic.processors.core.step_decorators.get_paused_thoughts') as mock_get_paused:
                mock_get_paused.return_value = ["thought1", "thought2"]  # Has paused thoughts
                
                with patch.object(pipeline_controller, '_handle_paused_thoughts') as mock_handle_paused:
                    expected_result = {
                        "success": True,
                        "step_point": "resume_paused_thoughts",
                        "thoughts_advanced": 2
                    }
                    mock_handle_paused.return_value = expected_result
                    
                    # Act
                    result = await pipeline_controller.execute_single_step_point()

        # Assert
        mock_enable.assert_called_once()
        mock_get_paused.assert_called_once()
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_execute_single_step_point_integration_with_pending_thoughts(self, pipeline_controller):
        """Test complete execute_single_step_point flow with pending thoughts."""
        # Arrange
        pending_thought = Mock()
        
        with patch('ciris_engine.logic.processors.core.step_decorators.enable_single_step_mode'):
            with patch('ciris_engine.logic.processors.core.step_decorators.get_paused_thoughts', return_value=[]):
                with patch('ciris_engine.logic.persistence.get_thoughts_by_status') as mock_get_thoughts:
                    mock_get_thoughts.return_value = [pending_thought]
                    
                    with patch.object(pipeline_controller, '_initiate_thought_processing') as mock_initiate:
                        expected_result = {
                            "success": True,
                            "step_point": "initiate_processing",
                            "thought_id": "pending-123"
                        }
                        mock_initiate.return_value = expected_result
                        
                        # Act
                        result = await pipeline_controller.execute_single_step_point()

        # Assert
        assert result == expected_result

    @pytest.mark.asyncio 
    async def test_execute_single_step_point_integration_no_work(self, pipeline_controller):
        """Test complete execute_single_step_point flow with no work available."""
        # Arrange
        with patch('ciris_engine.logic.processors.core.step_decorators.enable_single_step_mode'):
            with patch('ciris_engine.logic.processors.core.step_decorators.get_paused_thoughts', return_value=[]):
                with patch('ciris_engine.logic.persistence.get_thoughts_by_status', return_value=[]):
                    with patch.object(pipeline_controller, '_handle_no_pending_thoughts') as mock_handle_none:
                        expected_result = {
                            "success": True,
                            "step_point": "no_work",
                            "message": "No pending thoughts to process"
                        }
                        mock_handle_none.return_value = expected_result
                        
                        # Act
                        result = await pipeline_controller.execute_single_step_point()

        # Assert
        assert result == expected_result