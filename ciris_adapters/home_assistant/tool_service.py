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

from ciris_engine.schemas.adapters.tools import (
    ToolDMAGuidance,
    ToolDocumentation,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolGotcha,
    ToolInfo,
    ToolParameterSchema,
    UsageExample,
)

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
            description="Control a Home Assistant device (light, switch, media_player, cover, climate, fan, etc.)",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "entity_id": {
                        "type": "string",
                        "description": "Home Assistant entity ID (e.g., light.living_room, media_player.bedroom)",
                    },
                    "action": {
                        "type": "string",
                        "enum": [
                            # Universal actions
                            "turn_on",
                            "turn_off",
                            "toggle",
                            # Media player actions
                            "media_play",
                            "media_pause",
                            "media_stop",
                            "media_play_pause",
                            "media_next_track",
                            "media_previous_track",
                            "volume_up",
                            "volume_down",
                            "volume_mute",
                            # Cover actions
                            "open_cover",
                            "close_cover",
                            "stop_cover",
                            # Lock actions
                            "lock",
                            "unlock",
                            # Climate actions
                            "set_hvac_mode",
                            "set_temperature",
                            # Fan actions
                            "set_percentage",
                        ],
                        "description": "Action to perform. Use domain-specific actions for best results.",
                    },
                    "brightness": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255,
                        "description": "Brightness level 0-255 for lights. Use with action='turn_on'.",
                    },
                    "color_temp": {"type": "integer", "description": "Color temperature in mireds (optional)"},
                    "volume_level": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Volume level 0.0-1.0 for media players with volume_set.",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Target temperature for climate entities.",
                    },
                    "hvac_mode": {
                        "type": "string",
                        "description": "HVAC mode: heat, cool, heat_cool, auto, dry, fan_only, off.",
                    },
                    "percentage": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Fan speed percentage 0-100.",
                    },
                },
                required=["entity_id", "action"],
            ),
            documentation=ToolDocumentation(
                quick_start="Control HA devices: use entity_id + action. For media players use media_stop/media_play, not turn_off.",
                detailed_instructions="""
# Home Assistant Device Control

## Action Reference by Domain

### media_player.* (Music, Speakers, TVs)
- **media_play** - Start/resume playback
- **media_pause** - Pause playback
- **media_stop** - STOP playback (USE THIS to stop music!)
- **media_play_pause** - Toggle play/pause
- **media_next_track** - Skip to next
- **media_previous_track** - Go to previous
- **volume_up** / **volume_down** - Adjust volume
- **volume_mute** - Mute/unmute
- **turn_on** / **turn_off** - Power device on/off (NOT for stopping music!)

### light.*
- **turn_on** - Turn on (optionally with brightness, color_temp)
- **turn_off** - Turn off
- **toggle** - Toggle state

### switch.* / input_boolean.*
- **turn_on** / **turn_off** / **toggle**

### cover.* (Blinds, Garage Doors, Curtains)
- **open_cover** - Open
- **close_cover** - Close
- **stop_cover** - Stop movement
- **toggle** - Toggle open/closed

### lock.*
- **lock** - Lock
- **unlock** - Unlock

### climate.* (Thermostats, AC)
- **turn_on** / **turn_off** - Power
- **set_hvac_mode** - Set mode (requires hvac_mode parameter)
- **set_temperature** - Set target temp (requires temperature parameter)

### fan.*
- **turn_on** / **turn_off** / **toggle**
- **set_percentage** - Set speed (requires percentage parameter)

## Common Mistakes
- Using turn_off to stop music → Use media_stop instead!
- Using turn_on to resume music → Use media_play instead!
""",
                examples=[
                    UsageExample(
                        title="Stop music in bedroom",
                        description="Use media_stop to stop playback (NOT turn_off)",
                        code='{"entity_id": "media_player.bedroom", "action": "media_stop"}',
                    ),
                    UsageExample(
                        title="Pause music temporarily",
                        description="Use media_pause to pause, media_play to resume",
                        code='{"entity_id": "media_player.living_room", "action": "media_pause"}',
                    ),
                    UsageExample(
                        title="Turn off bedroom light",
                        description="Use turn_off for lights and switches",
                        code='{"entity_id": "light.bedroom_lamp", "action": "turn_off"}',
                    ),
                    UsageExample(
                        title="Set thermostat temperature",
                        description="Use set_temperature with temperature parameter",
                        code='{"entity_id": "climate.living_room", "action": "set_temperature", "temperature": 72}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Don't use turn_off to stop music",
                        description="When user says 'stop the music', use media_stop NOT turn_off. turn_off powers off the device entirely which may fail on some players.",
                    ),
                    ToolGotcha(
                        title="Don't use turn_on to play music",
                        description="When user says 'play music' or 'resume', use media_play NOT turn_on. turn_on just powers on the device, it doesn't start playback.",
                    ),
                    ToolGotcha(
                        title="500 error on turn_off for media players",
                        description="If a media player returns 500 on turn_off, use media_stop instead. Some players (like Music Assistant) don't support turn_off.",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Do not use for querying state - use ha_sensor_query instead. Do not use for automations - use ha_automation_trigger.",
                ethical_considerations="Device control affects the physical environment. Verify user intent for irreversible actions like unlocking doors.",
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
        # =====================================================================
        # Music Assistant Tools (uses HA service calls - requires MA integration in HA)
        # =====================================================================
        "ma_search": ToolInfo(
            name="ma_search",
            description="Search Music Assistant library for tracks, albums, artists, or playlists",
            when_to_use="Use when the user wants to find music, search for songs, artists, or albums",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "query": {
                        "type": "string",
                        "description": "Search query (song name, artist, album, etc.)",
                    },
                    "media_types": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["artist", "album", "track", "playlist", "radio"]},
                        "description": "Types to search. Default: all types.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Max results per type (default: 10)",
                    },
                },
                required=["query"],
            ),
            documentation=ToolDocumentation(
                quick_start="Search for music: ma_search query='song name' to find tracks, albums, artists",
                detailed_instructions="""
# Music Assistant Search

Search across all configured music providers (Spotify, Tidal, local library, etc.).
Requires Music Assistant integration to be installed in Home Assistant.

## Search Tips
- For specific songs: include artist name ("Never Gonna Give You Up Rick Astley")
- For albums: include album name and optionally artist
- For artists: just the artist name
- Filter by type with media_types parameter

## Results
Returns matches grouped by type (tracks, albums, artists, playlists).
Use the media_id from results with ma_play to start playback.
""",
                examples=[
                    UsageExample(
                        title="Search for a song",
                        description="Find a specific track",
                        code='{"query": "Bohemian Rhapsody Queen", "media_types": ["track"]}',
                    ),
                    UsageExample(
                        title="Search for an artist",
                        description="Find all content by an artist",
                        code='{"query": "Taylor Swift", "media_types": ["artist", "album", "track"]}',
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Do not use if Music Assistant integration is not installed in Home Assistant.",
            ),
        ),
        "ma_play": ToolInfo(
            name="ma_play",
            description="Play a track, album, or playlist on Music Assistant",
            when_to_use="Use after ma_search to play a specific item, or to play by name",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "media_id": {
                        "type": "string",
                        "description": "Media name, URI, or ID from search results",
                    },
                    "player_id": {
                        "type": "string",
                        "description": "Target player entity ID (e.g., media_player.mass_living_room)",
                    },
                    "media_type": {
                        "type": "string",
                        "enum": ["track", "album", "artist", "playlist", "radio"],
                        "description": "Type of media to play (default: track)",
                    },
                    "enqueue": {
                        "type": "string",
                        "enum": ["play", "next", "add", "replace"],
                        "description": "Queue behavior: play (now), next (after current), add (end), replace (clear queue)",
                    },
                },
                required=["media_id"],
            ),
            documentation=ToolDocumentation(
                quick_start="Play music: ma_play media_id='song name' or use ID from ma_search results",
                detailed_instructions="""
# Music Assistant Play

Play media via Music Assistant through Home Assistant.

## Queue Options
- **play**: Start playing immediately (default)
- **next**: Add after currently playing track
- **add**: Add to end of queue
- **replace**: Clear queue and play this item

## Player Selection
If player_id not specified, uses the default/active player.
Use ma_players to see available Music Assistant players.
""",
                examples=[
                    UsageExample(
                        title="Play a song by name",
                        description="Play a track immediately",
                        code='{"media_id": "Bohemian Rhapsody", "media_type": "track", "enqueue": "play"}',
                    ),
                    UsageExample(
                        title="Play on specific player",
                        description="Play on a specific speaker",
                        code='{"media_id": "Abbey Road", "media_type": "album", "player_id": "media_player.mass_living_room"}',
                    ),
                ],
            ),
        ),
        "ma_browse": ToolInfo(
            name="ma_browse",
            description="Browse Music Assistant library categories (artists, albums, playlists)",
            when_to_use="Use to explore available music without a specific search query",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "media_type": {
                        "type": "string",
                        "enum": ["artists", "albums", "tracks", "playlists"],
                        "description": "Category to browse (default: artists)",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "description": "Max results (default: 25)",
                    },
                },
                required=[],
            ),
            documentation=ToolDocumentation(
                quick_start="Browse library: ma_browse path='artists' to see all artists",
                detailed_instructions="""
# Music Assistant Browse

Navigate the music library by category.

## Available Paths
- **artists**: List all artists
- **albums**: List all albums
- **tracks**: List all tracks
- **playlists**: List all playlists
- (empty): Show root categories
""",
            ),
        ),
        "ma_queue": ToolInfo(
            name="ma_queue",
            description="View or manage the playback queue for a Music Assistant player",
            when_to_use="Use to see what's playing or coming up in the queue",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "player_id": {
                        "type": "string",
                        "description": "Player entity ID to get queue for",
                    },
                },
                required=["player_id"],
            ),
            documentation=ToolDocumentation(
                quick_start="View queue: ma_queue player_id='media_player.living_room'",
            ),
        ),
        "ma_players": ToolInfo(
            name="ma_players",
            description="List all Music Assistant players and their current state",
            when_to_use="Use to see available players and what's currently playing",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            ),
            documentation=ToolDocumentation(
                quick_start="List players: ma_players to see all available music players",
            ),
        ),
    }

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

    # MA tools are only available if Music Assistant is installed in HA
    MA_TOOL_NAMES = {"ma_search", "ma_play", "ma_browse", "ma_queue", "ma_players"}

    def __init__(self, ha_service: HAIntegrationService) -> None:
        """Initialize with underlying HA integration service."""
        self.ha_service = ha_service
        self._started = False
        self._ma_available: Optional[bool] = None  # Cached MA detection
        logger.info("HAToolService initialized")

    async def _check_ma_available(self) -> bool:
        """Check if Music Assistant is installed in Home Assistant.

        Detects MA by looking for:
        - media_player.mass_* entities (MA-managed players)
        - update.music_assistant_* entities (MA server update entity)
        - Any entity with mass_player_id attribute

        Note: Only caches positive detection (MA found). Transient HA errors
        will retry on next call rather than permanently disabling MA tools.
        """
        # Only use cache if MA was previously detected (positive cache)
        # Don't cache failures - allow retry on transient HA errors
        if self._ma_available is True:
            return True

        try:
            entities = await self.ha_service.get_all_entities()
            # Check for MA indicators:
            # 1. MA player entities (mass_* prefix)
            # 2. MA update entity (indicates MA server is installed)
            # 3. Any media_player with mass_player_id attribute
            ma_found = any(
                e.entity_id.startswith("media_player.mass_")
                or e.entity_id.startswith("update.music_assistant")
                or (e.domain == "media_player" and e.attributes.get("mass_player_id"))
                for e in entities
            )
            if ma_found:
                # Cache positive detection - MA is installed
                self._ma_available = True
                logger.info("[HA TOOLS] Music Assistant detected - MA tools enabled")
            else:
                # Don't cache negative - MA might be installed later or HA might be starting up
                logger.debug("[HA TOOLS] Music Assistant not detected in current entity list")
            return ma_found
        except Exception as e:
            # Don't cache failures - allow retry when HA recovers
            logger.warning(f"[HA TOOLS] Error checking for MA (will retry): {e}")
            return False

    def get_service_metadata(self) -> Dict[str, Any]:
        """Return service metadata for DSAR and data source discovery."""
        return {"data_source": False, "service_type": "device_control"}

    async def get_available_tools(self) -> List[str]:
        """Get available tool names. Used by system snapshot tool collection."""
        tools = list(self.TOOL_DEFINITIONS.keys())
        # Filter out MA tools if MA not available
        if not await self._check_ma_available():
            tools = [t for t in tools if t not in self.MA_TOOL_NAMES]
        return tools

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool. Used by system snapshot."""
        # Don't return MA tools if MA not available
        if tool_name in self.MA_TOOL_NAMES and not await self._check_ma_available():
            return None
        return self.TOOL_DEFINITIONS.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get info for all tools. Used by /tools API endpoint."""
        tools = list(self.TOOL_DEFINITIONS.values())
        # Filter out MA tools if MA not available
        if not await self._check_ma_available():
            tools = [t for t in tools if t.name not in self.MA_TOOL_NAMES]
        return tools

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
            # Music Assistant tools
            elif tool_name == "ma_search":
                result = await self._execute_ma_search(parameters)
            elif tool_name == "ma_play":
                result = await self._execute_ma_play(parameters)
            elif tool_name == "ma_browse":
                result = await self._execute_ma_browse(parameters)
            elif tool_name == "ma_queue":
                result = await self._execute_ma_queue(parameters)
            elif tool_name == "ma_players":
                result = await self._execute_ma_players(parameters)
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
        """Execute device control with parameter validation and friendly name resolution."""
        entity_id = params.get("entity_id", "")
        action = params.get("action", "")

        # Validate required parameters BEFORE calling HA
        missing_params = []
        if not entity_id:
            missing_params.append("entity_id")
        if not action:
            missing_params.append("action")

        if missing_params:
            error_msg = (
                f"Missing required parameter(s): {', '.join(missing_params)}. "
                f"ha_device_control requires: entity_id (e.g., 'light.bedroom_lamp'), "
                f"action ('turn_on', 'turn_off', or 'toggle'). "
                f"Received parameters: {params}"
            )
            logger.error(f"[HA TOOL] Parameter validation failed: {error_msg}")
            return ToolExecutionResult(
                tool_name="ha_device_control",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"received_params": params, "missing": missing_params},
                error=error_msg,
                correlation_id=str(uuid.uuid4()),
            )

        # Map common LLM action aliases to valid HA actions
        action_aliases = {
            # Light aliases
            "set_brightness": "turn_on",
            "set_level": "turn_on",
            "dim": "turn_on",
            "brighten": "turn_on",
            "set_color_temp": "turn_on",
            "set_color": "turn_on",
            # Media player aliases
            "play": "media_play",
            "pause": "media_pause",
            "stop": "media_stop",
            "resume": "media_play",
            "skip": "media_next_track",
            "next": "media_next_track",
            "previous": "media_previous_track",
            "mute": "volume_mute",
            # Cover aliases
            "open": "open_cover",
            "close": "close_cover",
        }
        if action in action_aliases:
            original_action = action
            action = action_aliases[action]
            params["action"] = action
            logger.info(f"[HA TOOL] Mapped action alias '{original_action}' -> '{action}'")

        # Validate action is one of the allowed values
        valid_actions = [
            # Universal
            "turn_on",
            "turn_off",
            "toggle",
            # Media player
            "media_play",
            "media_pause",
            "media_stop",
            "media_play_pause",
            "media_next_track",
            "media_previous_track",
            "volume_up",
            "volume_down",
            "volume_mute",
            "volume_set",
            # Cover
            "open_cover",
            "close_cover",
            "stop_cover",
            # Lock
            "lock",
            "unlock",
            # Climate
            "set_hvac_mode",
            "set_temperature",
            # Fan
            "set_percentage",
        ]
        if action not in valid_actions:
            error_msg = (
                f"Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}. "
                f"Received parameters: {params}"
            )
            logger.error(f"[HA TOOL] Action validation failed: {error_msg}")
            return ToolExecutionResult(
                tool_name="ha_device_control",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"received_params": params, "invalid_action": action},
                error=error_msg,
                correlation_id=str(uuid.uuid4()),
            )

        # Resolve entity by friendly name if needed (native HA feature support)
        original_entity_id = entity_id
        resolved_entity_id = await self.ha_service.resolve_entity_by_name(entity_id)

        if resolved_entity_id:
            if resolved_entity_id != entity_id:
                logger.info(f"[HA TOOL] Resolved '{entity_id}' -> '{resolved_entity_id}'")
            entity_id = resolved_entity_id
        else:
            # Entity not found - return helpful error with available entities hint
            error_msg = (
                f"Entity '{entity_id}' not found. "
                f"Could not resolve as entity_id or friendly name. "
                f"Use ha_list_entities to see available entities."
            )
            logger.error(f"[HA TOOL] Entity resolution failed: {error_msg}")
            return ToolExecutionResult(
                tool_name="ha_device_control",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={
                    "received_params": params,
                    "original_entity_id": original_entity_id,
                    "resolution_failed": True,
                },
                error=error_msg,
                correlation_id=str(uuid.uuid4()),
            )

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
        """Execute automation trigger with parameter validation."""
        automation_id = params.get("automation_id", "")

        # Validate required parameters
        if not automation_id:
            error_msg = (
                f"Missing required parameter: automation_id. "
                f"ha_automation_trigger requires: automation_id (e.g., 'automation.good_morning'). "
                f"Received parameters: {params}"
            )
            logger.error(f"[HA TOOL] Parameter validation failed: {error_msg}")
            return ToolExecutionResult(
                tool_name="ha_automation_trigger",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"received_params": params, "missing": ["automation_id"]},
                error=error_msg,
                correlation_id=str(uuid.uuid4()),
            )

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
        """Execute sensor query with parameter validation."""
        entity_id = params.get("entity_id", "")

        # Validate required parameters
        if not entity_id:
            error_msg = (
                f"Missing required parameter: entity_id. "
                f"ha_sensor_query requires: entity_id (e.g., 'sensor.temperature', 'binary_sensor.door'). "
                f"Received parameters: {params}"
            )
            logger.error(f"[HA TOOL] Parameter validation failed: {error_msg}")
            return ToolExecutionResult(
                tool_name="ha_sensor_query",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"received_params": params, "missing": ["entity_id"]},
                error=error_msg,
                correlation_id=str(uuid.uuid4()),
            )
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
        include_unavailable = params.get("include_unavailable", False)

        if domain:
            entities = await self.ha_service.get_sensors_by_domain(domain)
        else:
            entities = await self.ha_service.get_all_entities()

        # Filter out unavailable/unknown entities unless explicitly requested
        if not include_unavailable:
            active_entities = [e for e in entities if e.state not in ("unavailable", "unknown")]
            filtered_count = len(entities) - len(active_entities)
            logger.info(f"[HA ENTITY LIST] Filtered {filtered_count} unavailable/unknown entities")
            entities = active_entities

        # Prioritize controllable domains for context relevance
        # Higher priority = more useful for the agent to know about
        domain_priority = {
            "light": 1,
            "switch": 1,
            "climate": 1,
            "media_player": 2,
            "cover": 2,
            "fan": 2,
            "lock": 2,
            "vacuum": 2,
            "sensor": 3,
            "binary_sensor": 3,
            "person": 4,
            "device_tracker": 4,
            "weather": 4,
            "camera": 5,
            "automation": 6,
            "scene": 6,
            "script": 6,
            # Lower priority for system stuff
            "update": 10,
            "button": 10,
            "select": 10,
            "number": 10,
        }

        def get_priority(entity: Any) -> int:
            return domain_priority.get(entity.domain, 8)

        # Sort by priority (lower = more important)
        entities = sorted(entities, key=get_priority)

        # Log entity details at INFO level for context tuning
        logger.info(f"[HA ENTITY LIST] Retrieved {len(entities)} active entities (domain filter: {domain})")
        for e in entities[:50]:
            # Log each entity with its metadata for context builder tuning
            attrs_summary = {
                k: v
                for k, v in (e.attributes or {}).items()
                if k in ["friendly_name", "device_class", "unit_of_measurement", "icon", "supported_features"]
            }
            logger.info(
                f"[HA ENTITY] {e.entity_id} | state={e.state} | "
                f"name={e.friendly_name} | domain={e.domain} | attrs={attrs_summary}"
            )
        if len(entities) > 50:
            logger.info(f"[HA ENTITY LIST] ... and {len(entities) - 50} more entities (truncated)")

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
        """Execute notification send with parameter validation."""
        title = params.get("title", "")
        message = params.get("message", "")

        # Validate required parameters
        missing_params = []
        if not title:
            missing_params.append("title")
        if not message:
            missing_params.append("message")

        if missing_params:
            error_msg = (
                f"Missing required parameter(s): {', '.join(missing_params)}. "
                f"ha_notification requires: title (string), message (string). "
                f"Optional: target (e.g., 'mobile_app_phone'). "
                f"Received parameters: {params}"
            )
            logger.error(f"[HA TOOL] Parameter validation failed: {error_msg}")
            return ToolExecutionResult(
                tool_name="ha_notification",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"received_params": params, "missing": missing_params},
                error=error_msg,
                correlation_id=str(uuid.uuid4()),
            )

        notification = HANotification(
            title=title,
            message=message,
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

    # =========================================================================
    # Music Assistant Tool Execution
    # =========================================================================

    async def _execute_ma_search(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute Music Assistant search."""
        query = params.get("query", "")
        if not query:
            return ToolExecutionResult(
                tool_name="ma_search",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error="Missing required parameter: query",
                correlation_id=str(uuid.uuid4()),
            )

        media_types = params.get("media_types")
        limit = params.get("limit", 10)

        result = await self.ha_service.ma_search(query, media_types, limit)

        # Check both explicit success field and error presence
        if not result.get("success", False) or "error" in result:
            return ToolExecutionResult(
                tool_name="ma_search",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=result,  # Include full result for debugging
                error=result.get("error", "Search failed"),
                correlation_id=str(uuid.uuid4()),
            )

        return ToolExecutionResult(
            tool_name="ma_search",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=result,
            error=None,
            correlation_id=str(uuid.uuid4()),
        )

    async def _execute_ma_play(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute Music Assistant play."""
        media_id = params.get("media_id", "")
        if not media_id:
            return ToolExecutionResult(
                tool_name="ma_play",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error="Missing required parameter: media_id",
                correlation_id=str(uuid.uuid4()),
            )

        player_id = params.get("player_id")
        media_type = params.get("media_type", "track")
        enqueue = params.get("enqueue", "play")

        result = await self.ha_service.ma_play(media_id, player_id, media_type, enqueue)

        # Check both explicit success field and error presence
        if not result.get("success", False) or "error" in result:
            error_msg = result.get("error", "Playback verification failed")
            suggestion = result.get("suggestion", "")
            full_error = f"{error_msg}. {suggestion}".strip() if suggestion else error_msg
            return ToolExecutionResult(
                tool_name="ma_play",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=result,  # Include full result for debugging
                error=full_error,
                correlation_id=str(uuid.uuid4()),
            )

        return ToolExecutionResult(
            tool_name="ma_play",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=result,
            error=None,
            correlation_id=str(uuid.uuid4()),
        )

    async def _execute_ma_browse(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute Music Assistant browse."""
        media_type = params.get("media_type", "artists")
        limit = params.get("limit", 25)

        result = await self.ha_service.ma_browse(media_type, limit)

        if "error" in result:
            return ToolExecutionResult(
                tool_name="ma_browse",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=result["error"],
                correlation_id=str(uuid.uuid4()),
            )

        return ToolExecutionResult(
            tool_name="ma_browse",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=result,
            error=None,
            correlation_id=str(uuid.uuid4()),
        )

    async def _execute_ma_queue(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute Music Assistant queue query."""
        player_id = params.get("player_id", "")
        if not player_id:
            return ToolExecutionResult(
                tool_name="ma_queue",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error="Missing required parameter: player_id",
                correlation_id=str(uuid.uuid4()),
            )

        result = await self.ha_service.ma_get_queue(player_id)

        if "error" in result:
            return ToolExecutionResult(
                tool_name="ma_queue",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=result["error"],
                correlation_id=str(uuid.uuid4()),
            )

        return ToolExecutionResult(
            tool_name="ma_queue",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=result,
            error=None,
            correlation_id=str(uuid.uuid4()),
        )

    async def _execute_ma_players(self, params: Dict[str, Any]) -> ToolExecutionResult:
        """Execute Music Assistant players list."""
        result = await self.ha_service.ma_get_players()

        if "error" in result:
            return ToolExecutionResult(
                tool_name="ma_players",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=result["error"],
                correlation_id=str(uuid.uuid4()),
            )

        return ToolExecutionResult(
            tool_name="ma_players",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=result,
            error=None,
            correlation_id=str(uuid.uuid4()),
        )
