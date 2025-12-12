"""
Home Assistant Tool Service.

Provides TOOL capabilities for Home Assistant:
- Device control (lights, switches, thermostats)
- Automation triggering
- Sensor data queries
- Notification sending

This is separate from HACommunicationService which handles
bidirectional messaging/events.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema

from .schemas import HANotification
from .service import HAIntegrationService

logger = logging.getLogger(__name__)


class HAToolService:
    """
    Tool service for Home Assistant operations.

    Provides execute_tool interface for:
    - ha_device_control: Control HA devices (turn_on, turn_off, toggle)
    - ha_automation_trigger: Trigger HA automations
    - ha_sensor_query: Query sensor/entity states
    - ha_notification: Send notifications via HA
    - ha_camera_snapshot: Get camera frame analysis
    """

    TOOL_DEFINITIONS: Dict[str, ToolInfo] = {
        "ha_device_control": ToolInfo(
            name="ha_device_control",
            description="Control a Home Assistant device (light, switch, cover, etc.)",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "entity_id": {
                        "type": "string",
                        "description": "Home Assistant entity ID (e.g., light.living_room, switch.garage)",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["turn_on", "turn_off", "toggle"],
                        "description": "Action to perform",
                    },
                    "brightness": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255,
                        "description": "Brightness level for lights (optional)",
                    },
                    "color_temp": {"type": "integer", "description": "Color temperature in mireds (optional)"},
                },
                required=["entity_id", "action"],
            ),
        ),
        "ha_automation_trigger": ToolInfo(
            name="ha_automation_trigger",
            description="Trigger a Home Assistant automation",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "automation_id": {
                        "type": "string",
                        "description": "Automation entity ID (e.g., automation.good_morning)",
                    },
                },
                required=["automation_id"],
            ),
        ),
        "ha_sensor_query": ToolInfo(
            name="ha_sensor_query",
            description="Query the state of a Home Assistant entity or sensor",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "entity_id": {
                        "type": "string",
                        "description": "Entity ID to query (e.g., sensor.temperature, binary_sensor.door)",
                    },
                },
                required=["entity_id"],
            ),
        ),
        "ha_list_entities": ToolInfo(
            name="ha_list_entities",
            description="List all Home Assistant entities, optionally filtered by domain",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "domain": {
                        "type": "string",
                        "description": "Filter by domain (light, switch, sensor, etc.). Leave empty for all.",
                    },
                },
                required=[],
            ),
            # Context enrichment: run this tool automatically during context gathering
            # to provide available entities to the ASPDMA for action selection
            context_enrichment=True,
            context_enrichment_params={},  # Empty params = list all entities
        ),
        "ha_notification": ToolInfo(
            name="ha_notification",
            description="Send a notification via Home Assistant",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "title": {"type": "string", "description": "Notification title"},
                    "message": {"type": "string", "description": "Notification message"},
                    "target": {"type": "string", "description": "Target service (e.g., mobile_app_phone). Optional."},
                },
                required=["title", "message"],
            ),
        ),
        "ha_camera_analyze": ToolInfo(
            name="ha_camera_analyze",
            description="Analyze a camera feed for motion detection",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "camera_name": {"type": "string", "description": "Name of the camera to analyze"},
                    "duration_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 60,
                        "description": "How long to analyze (default: 10)",
                    },
                },
                required=["camera_name"],
            ),
        ),
    }

    def __init__(self, ha_service: HAIntegrationService) -> None:
        """Initialize with underlying HA integration service."""
        self.ha_service = ha_service
        self._started = False
        logger.info("HAToolService initialized")

    async def start(self) -> None:
        """Start the tool service."""
        self._started = True
        logger.info("HAToolService started")

    async def stop(self) -> None:
        """Stop the tool service."""
        self._started = False
        logger.info("HAToolService stopped")

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================
    # The protocol requires these methods for tool discovery:
    # - get_available_tools() -> List[str]  : Used by system snapshot
    # - get_tool_info(name) -> ToolInfo     : Used by system snapshot per-tool
    # - get_all_tool_info() -> List[ToolInfo]: Used by /tools API endpoint
    # - list_tools() -> List[str]           : Legacy alias for get_available_tools
    # - get_tool_schema(name) -> schema     : Get parameter schema
    # - validate_parameters(name, params)   : Validate without executing
    # - get_tool_result(correlation_id)     : Get async result (not used here)
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names. Used by system snapshot tool collection."""
        return list(self.TOOL_DEFINITIONS.keys())

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool. Used by system snapshot."""
        return self.TOOL_DEFINITIONS.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get info for all tools. Used by /tools API endpoint."""
        return list(self.TOOL_DEFINITIONS.values())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a tool."""
        tool_info = self.TOOL_DEFINITIONS.get(tool_name)
        return tool_info.parameters if tool_info else None

    async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate parameters for a tool without executing it."""
        if tool_name not in self.TOOL_DEFINITIONS:
            return False
        tool_info = self.TOOL_DEFINITIONS[tool_name]
        if not tool_info.parameters:
            return True
        # Basic validation: check required fields are present
        required = tool_info.parameters.required or []
        return all(param in parameters for param in required)

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of previously executed tool. Not implemented for sync HA tools."""
        return None

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """Execute a Home Assistant tool."""
        start_time = datetime.now(timezone.utc)
        correlation_id = str(uuid.uuid4())

        logger.info("=" * 60)
        logger.info(f"[HA TOOL EXECUTE] Tool: {tool_name}")
        logger.info(f"[HA TOOL EXECUTE] Parameters: {parameters}")
        logger.info(f"[HA TOOL EXECUTE] Context: {context}")
        logger.info(f"[HA TOOL EXECUTE] Correlation ID: {correlation_id}")

        if tool_name not in self.TOOL_DEFINITIONS:
            logger.error(f"[HA TOOL EXECUTE] Unknown tool: {tool_name}")
            logger.info("=" * 60)
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}",
                correlation_id=correlation_id,
            )

        try:
            if tool_name == "ha_device_control":
                logger.info("[HA TOOL EXECUTE] Dispatching to _execute_device_control")
                result = await self._execute_device_control(parameters)
            elif tool_name == "ha_automation_trigger":
                result = await self._execute_automation_trigger(parameters)
            elif tool_name == "ha_sensor_query":
                result = await self._execute_sensor_query(parameters)
            elif tool_name == "ha_list_entities":
                result = await self._execute_list_entities(parameters)
            elif tool_name == "ha_notification":
                result = await self._execute_notification(parameters)
            elif tool_name == "ha_camera_analyze":
                result = await self._execute_camera_analyze(parameters)
            else:
                result = ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data=None,
                    error=f"Tool not implemented: {tool_name}",
                    correlation_id=correlation_id,
                )

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"[HA TOOL EXECUTE] Result: success={result.success}, status={result.status}")
            logger.info(f"[HA TOOL EXECUTE] Result data: {result.data}")
            if result.error:
                logger.error(f"[HA TOOL EXECUTE] Error: {result.error}")
            logger.info(f"[HA TOOL EXECUTE] Elapsed: {elapsed:.3f}s")
            logger.info("=" * 60)
            return result

        except Exception as e:
            logger.error(f"[HA TOOL EXECUTE] Exception executing tool {tool_name}: {e}")
            import traceback

            logger.error(f"[HA TOOL EXECUTE] Traceback: {traceback.format_exc()}")
            logger.info("=" * 60)
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def _execute_device_control(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute device control."""
        entity_id = params.get("entity_id", "")
        action = params.get("action", "")

        # Extract optional parameters
        kwargs: Dict[str, Any] = {}
        if "brightness" in params:
            kwargs["brightness"] = params["brightness"]
        if "color_temp" in params:
            kwargs["color_temp"] = params["color_temp"]

        result = await self.ha_service.control_device(entity_id, action, **kwargs)

        return ToolExecutionResult(
            tool_name="ha_device_control",
            status=ToolExecutionStatus.COMPLETED if result.success else ToolExecutionStatus.FAILED,
            success=result.success,
            data={
                "entity_id": result.entity_id,
                "action": result.action,
                "success": result.success,
                "error": result.error,
            },
            error=result.error,
            correlation_id=str(uuid.uuid4()),
        )

    async def _execute_automation_trigger(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute automation trigger."""
        automation_id = params.get("automation_id", "")
        result = await self.ha_service.trigger_automation(automation_id)

        return ToolExecutionResult(
            tool_name="ha_automation_trigger",
            status=ToolExecutionStatus.COMPLETED if result.success else ToolExecutionStatus.FAILED,
            success=result.success,
            data={
                "automation_id": result.entity_id,
                "success": result.success,
                "error": result.error,
            },
            error=result.error,
            correlation_id=str(uuid.uuid4()),
        )

    async def _execute_sensor_query(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute sensor query."""
        entity_id = params.get("entity_id", "")
        state = await self.ha_service.get_device_state(entity_id)

        if state:
            return ToolExecutionResult(
                tool_name="ha_sensor_query",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={
                    "entity_id": state.entity_id,
                    "state": state.state,
                    "friendly_name": state.friendly_name,
                    "domain": state.domain,
                    "attributes": state.attributes,
                    "last_changed": state.last_changed.isoformat() if state.last_changed else None,
                },
                error=None,
                correlation_id=str(uuid.uuid4()),
            )
        else:
            return ToolExecutionResult(
                tool_name="ha_sensor_query",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=f"Entity not found: {entity_id}",
                correlation_id=str(uuid.uuid4()),
            )

    async def _execute_list_entities(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute list entities."""
        domain = params.get("domain")

        if domain:
            entities = await self.ha_service.get_sensors_by_domain(domain)
        else:
            entities = await self.ha_service.get_all_entities()

        return ToolExecutionResult(
            tool_name="ha_list_entities",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={
                "count": len(entities),
                "entities": [
                    {
                        "entity_id": e.entity_id,
                        "state": e.state,
                        "friendly_name": e.friendly_name,
                        "domain": e.domain,
                    }
                    for e in entities[:50]  # Limit to 50 for response size
                ],
                "truncated": len(entities) > 50,
            },
            error=None,
            correlation_id=str(uuid.uuid4()),
        )

    async def _execute_notification(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute notification send."""
        notification = HANotification(
            title=params.get("title", ""),
            message=params.get("message", ""),
            target=params.get("target"),
        )

        success = await self.ha_service.send_notification(notification)

        return ToolExecutionResult(
            tool_name="ha_notification",
            status=ToolExecutionStatus.COMPLETED if success else ToolExecutionStatus.FAILED,
            success=success,
            data={"sent": success},
            error=None if success else "Failed to send notification",
            correlation_id=str(uuid.uuid4()),
        )

    async def _execute_camera_analyze(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute camera analysis."""
        camera_name = params.get("camera_name", "")
        duration = params.get("duration_seconds", 10)

        result = await self.ha_service.analyze_camera_feed(camera_name, duration)

        if result.error:
            return ToolExecutionResult(
                tool_name="ha_camera_analyze",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=result.error,
                correlation_id=str(uuid.uuid4()),
            )

        return ToolExecutionResult(
            tool_name="ha_camera_analyze",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={
                "camera_name": result.camera_name,
                "duration_seconds": result.duration_seconds,
                "frames_analyzed": result.frames_analyzed,
                "motion_detected": result.motion_detected,
                "average_brightness": result.average_brightness,
            },
            error=None,
            correlation_id=str(uuid.uuid4()),
        )
