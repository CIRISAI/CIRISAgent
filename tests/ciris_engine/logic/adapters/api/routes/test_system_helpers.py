"""Unit tests for system route helper functions created during complexity refactoring."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, Request

from ciris_engine.logic.adapters.api.routes.system import RuntimeAction  # Also defined in the same file
from ciris_engine.logic.adapters.api.routes.system import RuntimeControlResponse  # Defined in the same file
from ciris_engine.logic.adapters.api.routes.system import ServiceMetrics  # Also defined in the same file
from ciris_engine.logic.adapters.api.routes.system import ServiceStatus  # Also defined in the same file
from ciris_engine.logic.adapters.api.routes.system import (
    _create_display_name,
    _create_final_response,
    _create_pause_response,
    _create_service_status,
    _execute_pause_action,
    _execute_resume_action,
    _execute_state_action,
    _extract_pipeline_state_info,
    _get_cognitive_state,
    _get_runtime_control_service,
    _get_service_category,
    _map_service_type_enum,
    _parse_direct_service_key,
    _parse_registry_service_key,
    _parse_service_key,
    _update_service_summary,
    _validate_runtime_action,
)
from ciris_engine.schemas.services.core.runtime import ProcessorStatus


class TestRuntimeControlHelpers:
    """Test cases for runtime control helper functions."""

    def test_get_runtime_control_service_main_service(self):
        """Test _get_runtime_control_service with main service available."""
        request = Mock(spec=Request)
        main_service = Mock()
        request.app.state.main_runtime_control_service = main_service
        request.app.state.runtime_control_service = Mock()  # Should not be used

        result = _get_runtime_control_service(request)

        assert result == main_service

    def test_get_runtime_control_service_fallback_service(self):
        """Test _get_runtime_control_service with fallback service."""
        request = Mock(spec=Request)
        request.app.state.main_runtime_control_service = None
        fallback_service = Mock()
        request.app.state.runtime_control_service = fallback_service

        result = _get_runtime_control_service(request)

        assert result == fallback_service

    def test_get_runtime_control_service_no_service(self):
        """Test _get_runtime_control_service with no service available."""
        request = Mock(spec=Request)
        request.app.state.main_runtime_control_service = None
        request.app.state.runtime_control_service = None

        with pytest.raises(HTTPException) as exc_info:
            _get_runtime_control_service(request)

        assert exc_info.value.status_code == 503

    def test_validate_runtime_action_valid(self):
        """Test _validate_runtime_action with valid actions."""
        for action in ["pause", "resume", "state"]:
            _validate_runtime_action(action)  # Should not raise

    def test_validate_runtime_action_invalid(self):
        """Test _validate_runtime_action with invalid action."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_runtime_action("invalid")

        assert exc_info.value.status_code == 400
        assert "Invalid action" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_pause_action_api_service(self):
        """Test _execute_pause_action with API runtime control service."""
        runtime_control = Mock()
        # Mock signature inspection to return API service (has parameters)
        with patch("inspect.signature") as mock_signature:
            mock_signature.return_value.parameters = {"reason": None}  # Has parameters
            runtime_control.pause_processing = AsyncMock(return_value=True)

            body = RuntimeAction(reason="Test reason")
            result = await _execute_pause_action(runtime_control, body)

        assert result is True
        runtime_control.pause_processing.assert_called_once_with("Test reason")

    @pytest.mark.asyncio
    async def test_execute_pause_action_main_service(self):
        """Test _execute_pause_action with main runtime control service."""
        runtime_control = Mock()
        # Mock signature inspection to return main service (no parameters)
        with patch("inspect.signature") as mock_signature:
            mock_signature.return_value.parameters = {}  # No parameters
            control_response = Mock()
            control_response.success = True
            runtime_control.pause_processing = AsyncMock(return_value=control_response)

            body = RuntimeAction(reason="Test reason")
            result = await _execute_pause_action(runtime_control, body)

        assert result is True
        runtime_control.pause_processing.assert_called_once_with()

    def test_extract_pipeline_state_info_no_runtime(self):
        """Test _extract_pipeline_state_info with no runtime available."""
        request = Mock(spec=Request)
        request.app.state.runtime = None

        current_step, current_step_schema, pipeline_state = _extract_pipeline_state_info(request)

        assert current_step is None
        assert current_step_schema is None
        assert pipeline_state is None

    def test_extract_pipeline_state_info_no_pipeline_controller(self):
        """Test _extract_pipeline_state_info with no pipeline controller."""
        request = Mock(spec=Request)
        runtime = Mock()
        agent_processor = Mock()
        agent_processor._pipeline_controller = None
        runtime.agent_processor = agent_processor
        request.app.state.runtime = runtime

        current_step, current_step_schema, pipeline_state = _extract_pipeline_state_info(request)

        assert current_step is None
        assert current_step_schema is None
        assert pipeline_state is None

    def test_extract_pipeline_state_info_with_current_step(self):
        """Test _extract_pipeline_state_info with current step available."""
        request = Mock(spec=Request)
        runtime = Mock()
        agent_processor = Mock()
        pipeline_controller = Mock()
        pipeline_state_obj = Mock()
        pipeline_state_obj.current_step = "BUILD_CONTEXT"
        pipeline_state_obj.pipeline_state = {"current_round": 1}

        pipeline_controller.get_current_state.return_value = pipeline_state_obj
        agent_processor._pipeline_controller = pipeline_controller
        runtime.agent_processor = agent_processor
        request.app.state.runtime = runtime

        current_step, current_step_schema, pipeline_state = _extract_pipeline_state_info(request)

        assert current_step == "BUILD_CONTEXT"
        assert current_step_schema is not None
        assert current_step_schema["step_point"] == "BUILD_CONTEXT"
        assert current_step_schema["can_single_step"] is True
        assert pipeline_state == {"current_round": 1}

    def test_extract_pipeline_state_info_controller_error(self):
        """Test _extract_pipeline_state_info with controller error."""
        request = Mock(spec=Request)
        runtime = Mock()
        agent_processor = Mock()
        pipeline_controller = Mock()
        pipeline_controller.get_current_state.side_effect = Exception("Controller error")
        agent_processor._pipeline_controller = pipeline_controller
        runtime.agent_processor = agent_processor
        request.app.state.runtime = runtime

        current_step, current_step_schema, pipeline_state = _extract_pipeline_state_info(request)

        assert current_step is None
        assert current_step_schema is None
        assert pipeline_state is None

    def test_create_pause_response_success(self):
        """Test _create_pause_response with successful pause."""
        result = _create_pause_response(True, "BUILD_CONTEXT", {"step_point": "BUILD_CONTEXT"}, {"state": "paused"})

        assert result.success is True
        assert "Processing paused at step: BUILD_CONTEXT" in result.message
        assert result.processor_state == "paused"
        assert result.current_step == "BUILD_CONTEXT"
        assert result.current_step_schema == {"step_point": "BUILD_CONTEXT"}
        assert result.pipeline_state == {"state": "paused"}

    def test_create_pause_response_already_paused(self):
        """Test _create_pause_response when already paused."""
        result = _create_pause_response(False, None, None, None)

        assert result.success is False
        assert result.message == "Already paused"
        assert result.processor_state == "unknown"
        assert result.current_step is None  # Field exists but is None

    @pytest.mark.asyncio
    async def test_execute_resume_action_main_service(self):
        """Test _execute_resume_action with main service response object."""
        runtime_control = Mock()
        resume_result = Mock()
        resume_result.success = True
        runtime_control.resume_processing = AsyncMock(return_value=resume_result)

        result = await _execute_resume_action(runtime_control)

        assert result.success is True
        assert result.message == "Processing resumed"
        assert result.processor_state == "active"

    @pytest.mark.asyncio
    async def test_execute_resume_action_api_service(self):
        """Test _execute_resume_action with API service boolean response."""
        runtime_control = Mock()
        runtime_control.resume_processing = AsyncMock(return_value=True)  # Boolean response

        result = await _execute_resume_action(runtime_control)

        assert result.success is True
        assert result.message == "Processing resumed"
        assert result.processor_state == "active"

    @pytest.mark.asyncio
    async def test_execute_resume_action_not_paused(self):
        """Test _execute_resume_action when not paused."""
        runtime_control = Mock()
        runtime_control.resume_processing = AsyncMock(return_value=False)  # Not paused

        result = await _execute_resume_action(runtime_control)

        assert result.success is False
        assert result.message == "Not paused"
        assert result.processor_state == "unknown"

    @pytest.mark.asyncio
    async def test_execute_state_action(self):
        """Test _execute_state_action."""
        runtime_control = Mock()
        status = Mock()
        status.processor_status = ProcessorStatus.PAUSED
        status.cognitive_state = "WORK"
        queue_status = Mock()
        queue_status.queue_size = 5

        runtime_control.get_runtime_status = AsyncMock(return_value=status)
        runtime_control.get_processor_queue_status = AsyncMock(return_value=queue_status)

        result = await _execute_state_action(runtime_control)

        assert result.success is True
        assert result.message == "Current runtime state retrieved"
        assert result.processor_state == "paused"
        assert result.cognitive_state == "WORK"
        assert result.queue_depth == 5

    @pytest.mark.asyncio
    async def test_execute_state_action_no_queue(self):
        """Test _execute_state_action with no queue status."""
        runtime_control = Mock()
        status = Mock()
        status.processor_status = ProcessorStatus.RUNNING  # Use correct enum value
        status.cognitive_state = None

        runtime_control.get_runtime_status = AsyncMock(return_value=status)
        runtime_control.get_processor_queue_status = AsyncMock(return_value=None)

        result = await _execute_state_action(runtime_control)

        assert result.success is True
        assert result.processor_state == "active"
        assert result.cognitive_state == "UNKNOWN"
        assert result.queue_depth == 0

    def test_get_cognitive_state_no_runtime(self):
        """Test _get_cognitive_state with no runtime."""
        request = Mock(spec=Request)
        request.app.state.runtime = None

        result = _get_cognitive_state(request)

        assert result is None

    def test_get_cognitive_state_no_agent_processor(self):
        """Test _get_cognitive_state with no agent processor."""
        request = Mock(spec=Request)
        runtime = Mock()
        runtime.agent_processor = None
        request.app.state.runtime = runtime

        result = _get_cognitive_state(request)

        assert result is None

    def test_get_cognitive_state_success(self):
        """Test _get_cognitive_state with successful retrieval."""
        request = Mock(spec=Request)
        runtime = Mock()
        agent_processor = Mock()
        agent_processor.get_current_state.return_value = "WORK"
        runtime.agent_processor = agent_processor
        request.app.state.runtime = runtime

        result = _get_cognitive_state(request)

        assert result == "WORK"

    def test_get_cognitive_state_error(self):
        """Test _get_cognitive_state with error during retrieval."""
        request = Mock(spec=Request)
        runtime = Mock()
        agent_processor = Mock()
        agent_processor.get_current_state.side_effect = Exception("State error")
        runtime.agent_processor = agent_processor
        request.app.state.runtime = runtime

        result = _get_cognitive_state(request)

        assert result is None

    def test_create_final_response_basic(self):
        """Test _create_final_response with basic response."""
        base_result = RuntimeControlResponse(
            success=True, message="Test message", processor_state="active", cognitive_state="UNKNOWN", queue_depth=3
        )

        result = _create_final_response(base_result, "WORK")

        assert result.success is True
        assert result.message == "Test message"
        assert result.processor_state == "active"
        assert result.cognitive_state == "WORK"
        assert result.queue_depth == 3

    def test_create_final_response_with_enhanced_fields(self):
        """Test _create_final_response with enhanced fields."""
        base_result = RuntimeControlResponse(
            success=True, message="Test message", processor_state="paused", cognitive_state="UNKNOWN", queue_depth=0
        )
        # Add enhanced fields
        base_result.current_step = "BUILD_CONTEXT"
        base_result.current_step_schema = {"step_point": "BUILD_CONTEXT"}
        base_result.pipeline_state = {"paused": True}

        result = _create_final_response(base_result, "WORK")

        assert result.success is True
        assert result.cognitive_state == "WORK"
        assert result.current_step == "BUILD_CONTEXT"
        assert result.current_step_schema == {"step_point": "BUILD_CONTEXT"}
        assert result.pipeline_state == {"paused": True}

    def test_create_final_response_cognitive_state_fallback(self):
        """Test _create_final_response with cognitive state fallback."""
        base_result = RuntimeControlResponse(
            success=True, message="Test message", processor_state="active", cognitive_state="DREAM", queue_depth=1
        )

        # Test fallback to base cognitive state when passed cognitive_state is None
        result = _create_final_response(base_result, None)

        assert result.cognitive_state == "DREAM"

        # Test fallback to UNKNOWN when both are None
        base_result.cognitive_state = None
        result = _create_final_response(base_result, None)

        assert result.cognitive_state == "UNKNOWN"


class TestServiceParsingHelpers:
    """Test cases for service parsing helper functions."""

    def test_parse_direct_service_key_valid(self):
        """Test _parse_direct_service_key with valid key."""
        service_type, display_name = _parse_direct_service_key("direct.graph.memory_service")

        assert service_type == "graph"
        assert display_name == "MemoryService"

    def test_parse_direct_service_key_complex_name(self):
        """Test _parse_direct_service_key with complex service name."""
        service_type, display_name = _parse_direct_service_key("direct.infrastructure.time_service_provider")

        assert service_type == "infrastructure"
        assert display_name == "TimeServiceProvider"

    def test_parse_direct_service_key_invalid(self):
        """Test _parse_direct_service_key with invalid key."""
        service_type, display_name = _parse_direct_service_key("invalid.key")

        assert service_type == "unknown"
        assert display_name == "invalid.key"

    def test_parse_registry_service_key_4_part(self):
        """Test _parse_registry_service_key with 4-part key."""
        service_type, display_name = _parse_registry_service_key("registry.ServiceType.TOOL.APIToolService_12345")

        assert service_type == "tool"
        assert display_name == "API-TOOL"

    def test_parse_registry_service_key_3_part(self):
        """Test _parse_registry_service_key with 3-part key."""
        service_type, display_name = _parse_registry_service_key("registry.ServiceType.COMMUNICATION")

        assert service_type == "unknown"  # Correct behavior - no adapter prefix
        assert display_name == "COMMUNICATION"

    def test_parse_registry_service_key_discord(self):
        """Test _parse_registry_service_key with Discord service."""
        service_type, display_name = _parse_registry_service_key(
            "registry.ServiceType.COMMUNICATION.DiscordCommunicationService_67890"
        )

        assert service_type == "adapter"
        assert display_name == "DISCORD-COMM"

    def test_map_service_type_enum_communication(self):
        """Test _map_service_type_enum with COMMUNICATION type."""
        service_type, display_name = _map_service_type_enum("ServiceType.COMMUNICATION", "TestService", "API")

        assert service_type == "adapter"
        assert display_name == "API-COMM"

    def test_map_service_type_enum_memory(self):
        """Test _map_service_type_enum with MEMORY type."""
        service_type, display_name = _map_service_type_enum("ServiceType.MEMORY", "MemoryService", "")

        assert service_type == "graph"
        assert display_name == "MemoryService"

    def test_map_service_type_enum_llm(self):
        """Test _map_service_type_enum with LLM type."""
        service_type, display_name = _map_service_type_enum("ServiceType.LLM", "LLMService", "")

        assert service_type == "runtime"
        assert display_name == "LLMService"

    def test_map_service_type_enum_time(self):
        """Test _map_service_type_enum with TIME type."""
        service_type, display_name = _map_service_type_enum("ServiceType.TIME", "TimeService", "")

        assert service_type == "infrastructure"
        assert display_name == "TimeService"

    def test_map_service_type_enum_tool(self):
        """Test _map_service_type_enum with TOOL type."""
        service_type, display_name = _map_service_type_enum("ServiceType.TOOL", "ToolService", "CLI")

        assert service_type == "tool"
        assert display_name == "CLI-TOOL"

    def test_map_service_type_enum_wise_authority(self):
        """Test _map_service_type_enum with WISE_AUTHORITY type."""
        service_type, display_name = _map_service_type_enum("ServiceType.WISE_AUTHORITY", "WiseService", "DISCORD")

        assert service_type == "governance"
        assert display_name == "DISCORD-WISE"

    def test_map_service_type_enum_runtime_control(self):
        """Test _map_service_type_enum with RUNTIME_CONTROL type."""
        service_type, display_name = _map_service_type_enum("ServiceType.RUNTIME_CONTROL", "RuntimeService", "API")

        assert service_type == "runtime"
        assert display_name == "API-RUNTIME"

    def test_map_service_type_enum_unknown(self):
        """Test _map_service_type_enum with unknown type."""
        service_type, display_name = _map_service_type_enum("ServiceType.UNKNOWN", "UnknownService", "")

        assert service_type == "unknown"
        assert display_name == "UnknownService"

    def test_parse_service_key_direct(self):
        """Test _parse_service_key with direct service."""
        service_type, display_name = _parse_service_key("direct.graph.memory_service")

        assert service_type == "graph"
        assert display_name == "MemoryService"

    def test_parse_service_key_registry(self):
        """Test _parse_service_key with registry service."""
        service_type, display_name = _parse_service_key("registry.ServiceType.TOOL.APIToolService_12345")

        assert service_type == "tool"
        assert display_name == "API-TOOL"

    def test_parse_service_key_unknown(self):
        """Test _parse_service_key with unknown format."""
        service_type, display_name = _parse_service_key("unknown.format")

        assert service_type == "unknown"
        assert display_name == "unknown.format"

    def test_create_service_status(self):
        """Test _create_service_status."""
        details = {"healthy": True, "extra": "ignored"}

        status = _create_service_status("direct.graph.memory_service", details)

        assert status.name == "MemoryService"
        assert status.type == "graph"
        assert status.healthy is True
        assert status.available is True
        assert status.uptime_seconds is None
        assert isinstance(status.metrics, ServiceMetrics)

    def test_create_service_status_unhealthy(self):
        """Test _create_service_status with unhealthy service."""
        details = {"healthy": False}

        status = _create_service_status("registry.ServiceType.COMMUNICATION.DiscordCommunicationService_123", details)

        assert status.name == "DISCORD-COMM"
        assert status.type == "adapter"
        assert status.healthy is False
        assert status.available is False

    def test_create_service_status_missing_healthy(self):
        """Test _create_service_status with missing healthy field."""
        details = {}

        status = _create_service_status("direct.infrastructure.time_service", details)

        assert status.name == "TimeService"
        assert status.type == "infrastructure"
        assert status.healthy is False
        assert status.available is False

    def test_update_service_summary_new_type(self):
        """Test _update_service_summary with new service type."""
        service_summary = {}

        _update_service_summary(service_summary, "graph", True)

        assert service_summary == {"graph": {"total": 1, "healthy": 1}}

    def test_update_service_summary_existing_type(self):
        """Test _update_service_summary with existing service type."""
        service_summary = {"graph": {"total": 2, "healthy": 1}}

        _update_service_summary(service_summary, "graph", False)

        assert service_summary == {"graph": {"total": 3, "healthy": 1}}

    def test_update_service_summary_healthy_increment(self):
        """Test _update_service_summary with healthy service increment."""
        service_summary = {"runtime": {"total": 0, "healthy": 0}}

        _update_service_summary(service_summary, "runtime", True)

        assert service_summary == {"runtime": {"total": 1, "healthy": 1}}


class TestServiceCategoryHelpers:
    """Test cases for new service category helper functions."""

    def test_get_service_category_communication(self):
        """Test _get_service_category with COMMUNICATION service type."""
        result = _get_service_category("ServiceType.COMMUNICATION")
        assert result == "adapter"

    def test_get_service_category_memory(self):
        """Test _get_service_category with MEMORY service type."""
        result = _get_service_category("ServiceType.MEMORY")
        assert result == "graph"

    def test_get_service_category_llm(self):
        """Test _get_service_category with LLM service type."""
        result = _get_service_category("ServiceType.LLM")
        assert result == "runtime"

    def test_get_service_category_time(self):
        """Test _get_service_category with TIME service type."""
        result = _get_service_category("ServiceType.TIME")
        assert result == "infrastructure"

    def test_get_service_category_wise_authority(self):
        """Test _get_service_category with WISE_AUTHORITY service type."""
        result = _get_service_category("ServiceType.WISE_AUTHORITY")
        assert result == "governance"

    def test_get_service_category_runtime_control(self):
        """Test _get_service_category with RUNTIME_CONTROL service type."""
        result = _get_service_category("ServiceType.RUNTIME_CONTROL")
        assert result == "runtime"

    def test_get_service_category_tool(self):
        """Test _get_service_category with TOOL service type."""
        result = _get_service_category("ServiceType.TOOL")
        assert result == "tool"

    def test_get_service_category_secrets_tool(self):
        """Test _get_service_category with SECRETS_TOOL service type."""
        result = _get_service_category("ServiceType.SECRETS_TOOL")
        assert result == "tool"

    def test_get_service_category_infrastructure_services(self):
        """Test _get_service_category with all infrastructure services."""
        services = [
            "ServiceType.SECRETS",
            "ServiceType.AUTHENTICATION",
            "ServiceType.RESOURCE_MONITOR",
            "ServiceType.DATABASE_MAINTENANCE",
            "ServiceType.INITIALIZATION",
            "ServiceType.SHUTDOWN",
        ]
        for service_type in services:
            result = _get_service_category(service_type)
            assert result == "infrastructure", f"Expected 'infrastructure' for {service_type}, got '{result}'"

    def test_get_service_category_graph_services(self):
        """Test _get_service_category with all graph services."""
        services = [
            "ServiceType.CONFIG",
            "ServiceType.TELEMETRY",
            "ServiceType.AUDIT",
            "ServiceType.INCIDENT_MANAGEMENT",
            "ServiceType.TSDB_CONSOLIDATION",
        ]
        for service_type in services:
            result = _get_service_category(service_type)
            assert result == "graph", f"Expected 'graph' for {service_type}, got '{result}'"

    def test_get_service_category_governance_services(self):
        """Test _get_service_category with all governance services."""
        services = ["ServiceType.ADAPTIVE_FILTER", "ServiceType.VISIBILITY", "ServiceType.SELF_OBSERVATION"]
        for service_type in services:
            result = _get_service_category(service_type)
            assert result == "governance", f"Expected 'governance' for {service_type}, got '{result}'"

    def test_get_service_category_runtime_services(self):
        """Test _get_service_category with all runtime services."""
        services = ["ServiceType.TASK_SCHEDULER"]
        for service_type in services:
            result = _get_service_category(service_type)
            assert result == "runtime", f"Expected 'runtime' for {service_type}, got '{result}'"

    def test_get_service_category_unknown(self):
        """Test _get_service_category with unknown service type."""
        result = _get_service_category("ServiceType.UNKNOWN")
        assert result == "unknown"

    def test_get_service_category_malformed(self):
        """Test _get_service_category with malformed service type."""
        result = _get_service_category("NotAServiceType")
        assert result == "unknown"

    def test_create_display_name_communication_with_adapter(self):
        """Test _create_display_name with COMMUNICATION and adapter prefix."""
        result = _create_display_name("ServiceType.COMMUNICATION", "TestService", "API")
        assert result == "API-COMM"

    def test_create_display_name_communication_with_discord(self):
        """Test _create_display_name with COMMUNICATION and Discord prefix."""
        result = _create_display_name("ServiceType.COMMUNICATION", "DiscordService", "DISCORD")
        assert result == "DISCORD-COMM"

    def test_create_display_name_communication_no_adapter(self):
        """Test _create_display_name with COMMUNICATION but no adapter prefix."""
        result = _create_display_name("ServiceType.COMMUNICATION", "CommunicationService", "")
        assert result == "CommunicationService"

    def test_create_display_name_tool_with_adapter(self):
        """Test _create_display_name with TOOL and adapter prefix."""
        result = _create_display_name("ServiceType.TOOL", "ToolService", "CLI")
        assert result == "CLI-TOOL"

    def test_create_display_name_tool_no_adapter(self):
        """Test _create_display_name with TOOL but no adapter prefix."""
        result = _create_display_name("ServiceType.TOOL", "ToolService", "")
        assert result == "ToolService"

    def test_create_display_name_wise_authority_with_adapter(self):
        """Test _create_display_name with WISE_AUTHORITY and adapter prefix."""
        result = _create_display_name("ServiceType.WISE_AUTHORITY", "WiseService", "DISCORD")
        assert result == "DISCORD-WISE"

    def test_create_display_name_wise_authority_no_adapter(self):
        """Test _create_display_name with WISE_AUTHORITY but no adapter prefix."""
        result = _create_display_name("ServiceType.WISE_AUTHORITY", "WiseService", "")
        assert result == "WiseService"

    def test_create_display_name_runtime_control_with_adapter(self):
        """Test _create_display_name with RUNTIME_CONTROL and adapter prefix."""
        result = _create_display_name("ServiceType.RUNTIME_CONTROL", "RuntimeService", "API")
        assert result == "API-RUNTIME"

    def test_create_display_name_runtime_control_no_adapter(self):
        """Test _create_display_name with RUNTIME_CONTROL but no adapter prefix."""
        result = _create_display_name("ServiceType.RUNTIME_CONTROL", "RuntimeService", "")
        assert result == "RuntimeService"

    def test_create_display_name_other_service_with_adapter(self):
        """Test _create_display_name with other service types ignores adapter prefix."""
        result = _create_display_name("ServiceType.MEMORY", "MemoryService", "IGNORED")
        assert result == "MemoryService"

    def test_create_display_name_other_service_no_adapter(self):
        """Test _create_display_name with other service types and no adapter prefix."""
        result = _create_display_name("ServiceType.LLM", "LLMService", "")
        assert result == "LLMService"

    def test_create_display_name_unknown_service(self):
        """Test _create_display_name with unknown service type."""
        result = _create_display_name("ServiceType.UNKNOWN", "UnknownService", "PREFIX")
        assert result == "UnknownService"
