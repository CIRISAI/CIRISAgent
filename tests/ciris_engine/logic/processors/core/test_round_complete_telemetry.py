"""
Unit tests for round_complete telemetry functionality.

Tests the telemetry validation fix where tag values must be strings.
"""

import pytest


class TestRoundCompleteTelemetry:
    """Test telemetry functionality in round complete phase."""

    @pytest.mark.asyncio
    async def test_round_complete_records_telemetry_with_string_tags(
        self, thought_processor_phase_with_telemetry, mock_telemetry_service, sample_processing_queue_item, sample_final_result
    ):
        """Test that telemetry is recorded with all tag values as strings."""
        # Setup
        thought_processor_phase_with_telemetry.current_round_number = 5
        
        # Execute
        result = await thought_processor_phase_with_telemetry._round_complete_step(sample_processing_queue_item, sample_final_result)
        
        # Verify telemetry was called
        mock_telemetry_service.record_metric.assert_called_once()
        
        # Get the call arguments
        call_args = mock_telemetry_service.record_metric.call_args
        metric_name = call_args[0][0]
        value = call_args[1]["value"] 
        tags = call_args[1]["tags"]
        
        # Verify metric details
        assert metric_name == "round_completed"
        assert value == 1.0
        
        # Critical test: Verify all tag values are strings
        assert isinstance(tags["thought_id"], str)
        assert isinstance(tags["round_number"], str)
        assert isinstance(tags["final_action"], str)
        
        # Verify tag content
        assert tags["thought_id"] == "test_thought_123"
        assert tags["round_number"] == "5"  # This is the key fix - must be string
        assert tags["final_action"] == "SPEAK"
        
        # Verify result is returned unchanged
        assert result is sample_final_result

    @pytest.mark.asyncio
    async def test_round_complete_handles_zero_round_number(
        self, thought_processor_phase_with_telemetry, mock_telemetry_service, sample_processing_queue_item, sample_final_result
    ):
        """Test round_number conversion when it's 0 (default value)."""
        # Setup - set to 0 explicitly
        thought_processor_phase_with_telemetry.current_round_number = 0
        
        # Execute
        await thought_processor_phase_with_telemetry._round_complete_step(sample_processing_queue_item, sample_final_result)
        
        # Verify
        call_args = mock_telemetry_service.record_metric.call_args
        tags = call_args[1]["tags"]
        
        # Verify zero is converted to string "0"
        assert tags["round_number"] == "0"
        assert isinstance(tags["round_number"], str)

    @pytest.mark.asyncio
    async def test_round_complete_handles_none_final_result(
        self, thought_processor_phase_with_telemetry, mock_telemetry_service, sample_processing_queue_item
    ):
        """Test telemetry when final_result is None."""
        # Execute with None final result
        result = await thought_processor_phase_with_telemetry._round_complete_step(sample_processing_queue_item, None)
        
        # Verify
        call_args = mock_telemetry_service.record_metric.call_args
        tags = call_args[1]["tags"]
        
        # Should default to "none" when final_result is None
        assert tags["final_action"] == "none"
        assert isinstance(tags["final_action"], str)
        
        # Result should be None (unchanged)
        assert result is None

    @pytest.mark.asyncio
    async def test_round_complete_handles_missing_telemetry_service(
        self, sample_processing_queue_item, sample_final_result
    ):
        """Test that round complete works without telemetry service."""
        from datetime import datetime, timezone
        from unittest.mock import Mock
        from ciris_engine.logic.processors.core.thought_processor.round_complete import RoundCompletePhase
        
        # Create phase without telemetry service
        phase = RoundCompletePhase()
        
        # Add required time service
        mock_time_service = Mock()
        mock_time_service.now.return_value = datetime.now(timezone.utc)
        phase._time_service = mock_time_service
        
        # Execute - should not raise error
        result = await phase._round_complete_step(sample_processing_queue_item, sample_final_result)
        
        # Should return result unchanged
        assert result is sample_final_result

    @pytest.mark.asyncio
    async def test_round_complete_handles_telemetry_service_none(
        self, sample_processing_queue_item, sample_final_result
    ):
        """Test that round complete works when telemetry_service is None."""
        from datetime import datetime, timezone
        from unittest.mock import Mock
        from ciris_engine.logic.processors.core.thought_processor.round_complete import RoundCompletePhase
        
        # Create phase with None telemetry service
        phase = RoundCompletePhase()
        phase.telemetry_service = None
        
        # Add required time service
        mock_time_service = Mock()
        mock_time_service.now.return_value = datetime.now(timezone.utc)
        phase._time_service = mock_time_service
        
        # Execute - should not raise error
        result = await phase._round_complete_step(sample_processing_queue_item, sample_final_result)
        
        # Should return result unchanged
        assert result is sample_final_result

    @pytest.mark.asyncio
    async def test_round_complete_with_various_round_numbers(
        self, thought_processor_phase_with_telemetry, mock_telemetry_service, sample_processing_queue_item, sample_final_result
    ):
        """Test telemetry with different round number values."""
        test_cases = [0, 1, 10, 100, 999]
        
        for round_num in test_cases:
            # Reset mock
            mock_telemetry_service.record_metric.reset_mock()
            
            # Setup
            thought_processor_phase_with_telemetry.current_round_number = round_num
            
            # Execute
            await thought_processor_phase_with_telemetry._round_complete_step(sample_processing_queue_item, sample_final_result)
            
            # Verify
            call_args = mock_telemetry_service.record_metric.call_args
            tags = call_args[1]["tags"]
            
            assert tags["round_number"] == str(round_num)
            assert isinstance(tags["round_number"], str)

    @pytest.mark.asyncio
    async def test_round_complete_telemetry_exception_handling(
        self, thought_processor_phase_with_telemetry, mock_telemetry_service, sample_processing_queue_item, sample_final_result, caplog
    ):
        """Test that telemetry exceptions don't break round completion."""
        import logging
        
        # Setup telemetry to raise exception
        mock_telemetry_service.record_metric.side_effect = Exception("Telemetry error")
        
        # Execute - should not raise exception
        with caplog.at_level(logging.ERROR):
            result = await thought_processor_phase_with_telemetry._round_complete_step(sample_processing_queue_item, sample_final_result)
        
        # Should still return result unchanged
        assert result is sample_final_result
        
        # Should have logged the error
        assert "Error recording round completion metric: Telemetry error" in caplog.text

    @pytest.mark.asyncio 
    async def test_telemetry_tag_validation_schema_compliance(
        self, thought_processor_phase_with_telemetry, mock_telemetry_service, sample_processing_queue_item, sample_final_result
    ):
        """Test that telemetry tags comply with TelemetryNodeAttributes schema requirements."""
        # Setup
        thought_processor_phase_with_telemetry.current_round_number = 42
        
        # Execute
        await thought_processor_phase_with_telemetry._round_complete_step(sample_processing_queue_item, sample_final_result)
        
        # Get call arguments
        call_args = mock_telemetry_service.record_metric.call_args
        tags = call_args[1]["tags"]
        
        # Verify schema compliance: Dict[str, str] as required by TelemetryNodeAttributes.labels
        assert isinstance(tags, dict)
        for key, value in tags.items():
            assert isinstance(key, str), f"Tag key {key} should be string"
            assert isinstance(value, str), f"Tag value {value} should be string" 
            
        # Verify no integer values (the original bug)
        for value in tags.values():
            assert not isinstance(value, int), "Tag values must not be integers"