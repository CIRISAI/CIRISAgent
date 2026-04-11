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
                quick_start="Control HA devices: use entity_id + action. For PLAYING NEW MUSIC, use Music Assistant tools (ma_search, ma_play) NOT this tool!",
                detailed_instructions="""
# Home Assistant Device Control

**IMPORTANT: To PLAY NEW MUSIC (e.g., "play Enya"), use Music Assistant tools:**
- **ma_search** - Search for artists/songs/albums
- **ma_play** - Play music on a player

This tool (ha_device_control) is for device control, NOT for starting new music!

## Action Reference by Domain

### media_player.* (Music, Speakers, TVs)
- **media_play** - RESUME paused playback ONLY (does NOT start new music!)
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
                        description="When user says 'resume', use media_play NOT turn_on. turn_on just powers on the device, it doesn't start playback.",
                    ),
                    ToolGotcha(
                        title="500 error on turn_off for media players",
                        description="If a media player returns 500 on turn_off, use media_stop instead. Some players (like Music Assistant) don't support turn_off.",
                    ),
                    ToolGotcha(
                        title="CRITICAL: media_play does NOT play new music",
                        description="media_play ONLY resumes paused content. To play NEW music (e.g., 'play Enya'), use Music Assistant tools: ma_search to find content, then ma_play to play it.",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Do not use to PLAY NEW MUSIC - use Music Assistant tools (ma_search, ma_play) instead. Do not use for querying state - use ha_sensor_query instead. Do not use for automations - use ha_automation_trigger.",
                ethical_considerations="Device control affects the physical environment. Verify user intent for irreversible actions like unlocking doors.",
            ),
        ),
        "ha_automation_trigger": ToolInfo(
            name="ha_automation_trigger",
            description="Trigger a Home Assistant automation immediately",
            when_to_use="Use to manually trigger an automation (e.g., 'run the good morning routine')",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "automation_id": {
                        "type": "string",
                        "description": "Automation entity ID (e.g., automation.good_morning, automation.bedtime_routine)",
                    },
                },
                required=["automation_id"],
            ),
            documentation=ToolDocumentation(
                quick_start="Trigger automations: ha_automation_trigger automation_id='automation.good_morning'",
                detailed_instructions="""
# Home Assistant Automation Trigger

Manually trigger any Home Assistant automation to run immediately, regardless of its normal triggers.

## When to Use
- User wants to manually run a routine ("run my morning routine")
- Testing automations
- User wants to trigger a scene-like automation

## Entity ID Format
Automations use the format: `automation.<snake_case_name>`
Examples:
- `automation.good_morning` - Morning routine
- `automation.turn_off_all_lights` - All lights off
- `automation.bedtime_routine` - Bedtime routine

## Important Notes
- Automation must be ENABLED to trigger (disabled automations won't run)
- This bypasses the automation's normal trigger conditions
- The automation runs with its configured actions and conditions

## Finding Automations
Use ha_list_entities with domain='automation' to see available automations.
""",
                examples=[
                    UsageExample(
                        title="Trigger morning routine",
                        description="Run the good morning automation",
                        code='{"automation_id": "automation.good_morning"}',
                    ),
                    UsageExample(
                        title="Trigger all lights off",
                        description="Run automation that turns off all lights",
                        code='{"automation_id": "automation.turn_off_all_lights"}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Disabled automations won't trigger",
                        description="If an automation is disabled (turned off), triggering it has no effect. Use ha_sensor_query to check the automation's state first if unsure.",
                        severity="warning",
                    ),
                    ToolGotcha(
                        title="Conditions still apply",
                        description="The automation's conditions are still evaluated when triggered manually. If conditions fail, actions won't run.",
                        severity="info",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use for direct device control - use ha_device_control instead. Don't use if you can achieve the goal with a single device command.",
                ethical_considerations="Automations may control multiple devices. Verify user intent for automations that affect security (locks, alarms) or major systems.",
            ),
        ),
        "ha_sensor_query": ToolInfo(
            name="ha_sensor_query",
            description="Query the current state and attributes of any Home Assistant entity",
            when_to_use="Use to check sensor values, device states, or entity attributes (e.g., 'what's the temperature?', 'is the door open?')",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "entity_id": {
                        "type": "string",
                        "description": "Entity ID to query (e.g., sensor.living_room_temperature, binary_sensor.front_door)",
                    },
                },
                required=["entity_id"],
            ),
            documentation=ToolDocumentation(
                quick_start="Query state: ha_sensor_query entity_id='sensor.temperature' - returns state + attributes",
                detailed_instructions="""
# Home Assistant Sensor Query

Query any Home Assistant entity to get its current state and attributes.

## What You Get
- **state**: The entity's current value (e.g., "72.5", "on", "open", "home")
- **attributes**: Additional data like unit_of_measurement, friendly_name, device_class
- **last_changed**: When the state last changed

## Common Entity Types

### Sensors (sensor.*)
- Temperature: `sensor.living_room_temperature` → "72.5" (°F)
- Humidity: `sensor.bathroom_humidity` → "65" (%)
- Power: `sensor.washing_machine_power` → "150" (W)
- Battery: `sensor.phone_battery_level` → "85" (%)

### Binary Sensors (binary_sensor.*)
- Door: `binary_sensor.front_door` → "on" (open) / "off" (closed)
- Motion: `binary_sensor.hallway_motion` → "on" (detected) / "off" (clear)
- Window: `binary_sensor.bedroom_window` → "on" (open) / "off" (closed)

### Other Entities
- Person: `person.john` → "home" / "away" / zone name
- Weather: `weather.home` → "sunny" / "cloudy" / "rainy"
- Device state: `light.bedroom` → "on" / "off" (with brightness in attributes)

## Attributes
Attributes contain extra info depending on entity type:
- **unit_of_measurement**: "°F", "%", "W", etc.
- **device_class**: "temperature", "humidity", "motion", etc.
- **friendly_name**: Human-readable name
- **brightness**: For lights (0-255)
- **media_title**: For media players (currently playing)
""",
                examples=[
                    UsageExample(
                        title="Check temperature",
                        description="Query a temperature sensor",
                        code='{"entity_id": "sensor.living_room_temperature"}',
                    ),
                    UsageExample(
                        title="Check if door is open",
                        description="Query a door sensor",
                        code='{"entity_id": "binary_sensor.front_door"}',
                    ),
                    UsageExample(
                        title="Check person location",
                        description="See if someone is home",
                        code='{"entity_id": "person.john"}',
                    ),
                    UsageExample(
                        title="Check light brightness",
                        description="Query a light to see its state and brightness attribute",
                        code='{"entity_id": "light.bedroom_lamp"}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Unavailable state",
                        description="If entity returns 'unavailable' or 'unknown', the device may be offline or not responding.",
                        severity="info",
                    ),
                    ToolGotcha(
                        title="Binary sensor on/off meaning",
                        description="For binary sensors, 'on' typically means triggered/open/detected, 'off' means normal/closed/clear. Check device_class attribute for exact meaning.",
                        severity="info",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use for controlling devices - use ha_device_control. Don't use to get lists of entities - use ha_list_entities.",
                ethical_considerations="Sensor data may reveal presence/absence patterns. Be mindful when querying person or motion sensors.",
            ),
        ),
        "ha_list_entities": ToolInfo(
            name="ha_list_entities",
            description="List all Home Assistant entities, optionally filtered by domain",
            when_to_use="Use to discover available devices and their entity IDs (e.g., 'what lights do I have?', 'list all sensors')",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "domain": {
                        "type": "string",
                        "description": "Filter by domain (light, switch, sensor, media_player, climate, etc.). Leave empty for all.",
                    },
                },
                required=[],
            ),
            # Context enrichment: run this tool automatically during context gathering
            # to provide available entities to the ASPDMA for action selection
            context_enrichment=True,
            context_enrichment_params={},  # Empty params = list all entities
            documentation=ToolDocumentation(
                quick_start="List entities: ha_list_entities (all) or ha_list_entities domain='light' (filtered)",
                detailed_instructions="""
# Home Assistant Entity List

Discover all available Home Assistant entities, optionally filtered by domain.

## Common Domains
- **light** - Lights, bulbs, LED strips
- **switch** - Smart plugs, switches
- **sensor** - Temperature, humidity, power, battery sensors
- **binary_sensor** - Door, motion, window sensors (on/off states)
- **media_player** - Speakers, TVs, streaming devices
- **climate** - Thermostats, AC units
- **cover** - Blinds, curtains, garage doors
- **lock** - Smart locks
- **fan** - Fans, ventilation
- **camera** - Security cameras
- **automation** - Automations (for triggering)
- **person** - People/presence tracking

## Response Format
Returns up to 50 entities, prioritized by usefulness:
1. Controllable devices (lights, switches, climate)
2. Media players, covers, fans, locks
3. Sensors
4. Other entities

Each entity includes:
- **entity_id**: Full ID for use with other tools
- **state**: Current state
- **friendly_name**: Human-readable name
- **domain**: Entity domain

## Finding Specific Entities
If you need a specific entity but don't know its ID:
1. Filter by domain first (e.g., domain='light')
2. Match by friendly_name in results
3. Use the entity_id with other tools
""",
                examples=[
                    UsageExample(
                        title="List all lights",
                        description="See all available lights",
                        code='{"domain": "light"}',
                    ),
                    UsageExample(
                        title="List all media players",
                        description="Find speakers and TVs",
                        code='{"domain": "media_player"}',
                    ),
                    UsageExample(
                        title="List all entities",
                        description="See everything (prioritized list)",
                        code="{}",
                    ),
                    UsageExample(
                        title="List all automations",
                        description="Find automations to trigger",
                        code='{"domain": "automation"}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Results limited to 50 entities",
                        description="Large installations may have more entities. Use domain filter to find specific types.",
                        severity="info",
                    ),
                    ToolGotcha(
                        title="Unavailable entities filtered out",
                        description="Entities in 'unavailable' or 'unknown' state are hidden by default to reduce noise.",
                        severity="info",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use repeatedly - results are often provided in context. Don't use to control devices - use ha_device_control.",
            ),
        ),
        "ha_notification": ToolInfo(
            name="ha_notification",
            description="Send a push notification via Home Assistant to phones or other notification services",
            when_to_use="Use to send alerts, reminders, or messages to user's phone (e.g., 'send me a reminder', 'alert me when...')",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "title": {"type": "string", "description": "Notification title (short, descriptive)"},
                    "message": {"type": "string", "description": "Notification message body"},
                    "target": {
                        "type": "string",
                        "description": "Target service name (e.g., mobile_app_johns_iphone). Optional - uses default if not specified.",
                    },
                },
                required=["title", "message"],
            ),
            documentation=ToolDocumentation(
                quick_start="Send notification: ha_notification title='Alert' message='Something happened'",
                detailed_instructions="""
# Home Assistant Notification

Send push notifications through Home Assistant's notification system.

## Target Services
Notifications can be sent to various targets:
- **Mobile apps**: `mobile_app_<device_name>` (e.g., mobile_app_johns_iphone)
- **Persistent notification**: `persistent_notification` (shows in HA dashboard)
- **Other services**: Telegram, Slack, email (if configured)

## Message Formatting
- Keep titles short (shown in notification header)
- Messages can be longer (shown in notification body)
- Some targets support markdown formatting

## Common Use Cases
- Reminders and alerts
- Status updates
- Security notifications
- Automation confirmations

## Finding Target Names
Mobile app targets follow the pattern: `mobile_app_<device_name>`
The device name is set when the HA Companion app is installed.
""",
                examples=[
                    UsageExample(
                        title="Simple notification",
                        description="Send a basic notification to default target",
                        code='{"title": "Reminder", "message": "Don\'t forget to take out the trash"}',
                    ),
                    UsageExample(
                        title="Notification to specific phone",
                        description="Send to a specific mobile device",
                        code='{"title": "Motion Detected", "message": "Motion detected at front door", "target": "mobile_app_johns_iphone"}',
                    ),
                    UsageExample(
                        title="Persistent notification",
                        description="Show notification in HA dashboard",
                        code='{"title": "System Update", "message": "Updates available", "target": "persistent_notification"}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Target name format",
                        description="Mobile app targets use underscores, not spaces: mobile_app_johns_iphone not mobile_app_john's iphone",
                        severity="warning",
                    ),
                    ToolGotcha(
                        title="App must be configured",
                        description="The HA Companion app must be installed and configured on the target device for mobile notifications to work.",
                        severity="info",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use for conversational responses - just respond directly. Don't use excessively - notifications should be meaningful.",
                ethical_considerations="Notifications interrupt users. Use sparingly and only when the user has requested alerts or reminders.",
            ),
        ),
        "ha_camera_analyze": ToolInfo(
            name="ha_camera_analyze",
            description="Analyze a camera feed for motion detection and brightness levels",
            when_to_use="Use to detect motion or analyze camera feeds (e.g., 'is there motion at the front door?', 'check the backyard camera')",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "camera_name": {
                        "type": "string",
                        "description": "Camera name or identifier (e.g., 'front_door', 'backyard')",
                    },
                    "duration_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 60,
                        "description": "Analysis duration in seconds (default: 10, max: 60)",
                    },
                },
                required=["camera_name"],
            ),
            documentation=ToolDocumentation(
                quick_start="Analyze camera: ha_camera_analyze camera_name='front_door' duration_seconds=10",
                detailed_instructions="""
# Home Assistant Camera Analysis

Analyze a WebRTC camera feed for motion detection and brightness levels.

## How It Works
1. Connects to the camera's WebRTC stream
2. Captures frames for the specified duration
3. Analyzes frames for motion between consecutive frames
4. Calculates average brightness level

## Results Include
- **frames_analyzed**: Number of frames captured
- **motion_detected**: Boolean - whether motion was detected
- **average_brightness**: 0-255 brightness level (0=black, 255=white)

## Camera Configuration
Cameras must be configured in the WEBRTC_CAMERA_URLS environment variable.
Format: `camera_name=rtsp://url;other_camera=rtsp://url2`

## Duration Guidelines
- **Short (1-5s)**: Quick motion check
- **Medium (10-15s)**: Typical analysis
- **Long (30-60s)**: Extended monitoring

## Motion Detection
Motion is detected by comparing pixel differences between frames.
Sensitivity is tuned for typical indoor/outdoor use.
""",
                examples=[
                    UsageExample(
                        title="Quick motion check",
                        description="Check for motion at front door",
                        code='{"camera_name": "front_door", "duration_seconds": 5}',
                    ),
                    UsageExample(
                        title="Extended analysis",
                        description="Monitor backyard for 30 seconds",
                        code='{"camera_name": "backyard", "duration_seconds": 30}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Requires OpenCV",
                        description="Camera analysis requires OpenCV (cv2) to be installed. Feature is disabled without it.",
                        severity="warning",
                    ),
                    ToolGotcha(
                        title="Camera must be configured",
                        description="Camera URLs must be set in WEBRTC_CAMERA_URLS environment variable.",
                        severity="warning",
                    ),
                    ToolGotcha(
                        title="Processing time",
                        description="Analysis takes approximately the duration_seconds plus a few seconds for processing.",
                        severity="info",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use for viewing camera feeds - this is for motion analysis only. Don't use for camera snapshots - use HA camera entity instead.",
                ethical_considerations="Camera analysis involves visual monitoring. Ensure user has legitimate reason to analyze camera feeds.",
            ),
        ),
        # =====================================================================
        # Music Assistant Tools (uses HA service calls - requires MA integration in HA)
        # =====================================================================
        "ma_search": ToolInfo(
            name="ma_search",
            description="Search Music Assistant library for tracks, albums, artists, or playlists across all providers",
            when_to_use="Use when user wants to find music before playing (e.g., 'find songs by Queen', 'search for classical music')",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "query": {
                        "type": "string",
                        "description": "Search query - song name, artist, album, or descriptive terms",
                    },
                    "media_types": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["artist", "album", "track", "playlist", "radio"]},
                        "description": "Filter by type. Default: all types. Use ['track'] for songs.",
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
                quick_start="Search for music: ma_search query='Bohemian Rhapsody Queen' media_types=['track']",
                detailed_instructions="""
# Music Assistant Search

Search across ALL configured music providers (Spotify, Apple Music, Tidal, YouTube Music, local library, etc.).

## Search Strategies

### For Specific Songs
Include both song name AND artist for best results:
- "Bohemian Rhapsody Queen" ✓
- "Never Gonna Give You Up Rick Astley" ✓
- "Bohemian Rhapsody" (may return covers) ⚠️

### For Albums
Include album name and optionally artist:
- "Abbey Road Beatles" ✓
- "Greatest Hits Queen" ✓

### For Artists
Just the artist name:
- "Taylor Swift"
- "The Beatles"

### For Genres/Moods (if supported by provider)
- "relaxing piano music"
- "workout playlist"

## Media Types
- **track**: Individual songs
- **album**: Full albums
- **artist**: Artists
- **playlist**: User or curated playlists
- **radio**: Radio stations

## Using Search Results
Results include a `media_id` for each item. Use this ID with ma_play:
1. Search: ma_search query="Enya" → results include media_id
2. Play: ma_play media_id="<id from results>"

Or just use the name directly with ma_play (it will search automatically).

## Provider Aggregation
Results come from ALL configured providers and are deduplicated.
The same song from Spotify and your local library will appear once.
""",
                examples=[
                    UsageExample(
                        title="Search for a specific song",
                        description="Find a track with artist name for accuracy",
                        code='{"query": "Bohemian Rhapsody Queen", "media_types": ["track"], "limit": 5}',
                    ),
                    UsageExample(
                        title="Search for an artist",
                        description="Find artist and their albums",
                        code='{"query": "Taylor Swift", "media_types": ["artist", "album"]}',
                    ),
                    UsageExample(
                        title="Search for playlists",
                        description="Find themed playlists",
                        code='{"query": "workout", "media_types": ["playlist"]}',
                    ),
                    UsageExample(
                        title="Broad search",
                        description="Search all types for a term",
                        code='{"query": "classical piano"}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Include artist for songs",
                        description="Searching just 'Yesterday' returns many covers. Use 'Yesterday Beatles' for the original.",
                        severity="warning",
                    ),
                    ToolGotcha(
                        title="Results are async",
                        description="Large searches may return progressively. Results show what's found so far.",
                        severity="info",
                    ),
                    ToolGotcha(
                        title="MA must be installed",
                        description="Returns 404 if Music Assistant integration is not installed in Home Assistant.",
                        severity="error",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use if user just wants to play something - ma_play can search by name directly. Don't use for browsing library categories - use ma_browse instead.",
                ethical_considerations="Search queries may reveal music preferences. Handle with appropriate privacy.",
            ),
        ),
        "ma_play": ToolInfo(
            name="ma_play",
            description="Play music via Music Assistant - USE THIS when user wants to play songs, albums, artists, or playlists!",
            when_to_use="Use to PLAY MUSIC - when user says 'play [song/artist/album]', 'put on some [genre]', use this tool!",
            # Context enrichment: include this tool's info prominently in ASPDMA context
            context_enrichment=True,
            context_enrichment_params={"_info_only": True},  # Just surface the tool info, don't execute
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "media_id": {
                        "type": "string",
                        "description": "What to play: song name ('Bohemian Rhapsody'), 'artist - song', URI, or ID from ma_search",
                    },
                    "player_id": {
                        "type": "string",
                        "description": "Target player (e.g., media_player.mass_living_room). Optional - uses default player.",
                    },
                    "media_type": {
                        "type": "string",
                        "enum": ["track", "album", "artist", "playlist", "radio"],
                        "description": "What kind of media: track (song), album, artist (all songs), playlist. Default: track",
                    },
                    "enqueue": {
                        "type": "string",
                        "enum": ["play", "next", "add", "replace"],
                        "description": "Queue behavior: play (now), next (after current), add (end of queue), replace (clear queue first)",
                    },
                },
                required=["media_id"],
            ),
            documentation=ToolDocumentation(
                quick_start="Play music: ma_play media_id='Bohemian Rhapsody Queen' media_type='track'",
                detailed_instructions="""
# Music Assistant Play

**THIS IS THE TOOL FOR PLAYING NEW MUSIC!**
When user says "play Enya", "put on some jazz", "play Beatles" - use this tool.

## How to Specify What to Play

### By Name (Recommended for simple requests)
```
media_id="Bohemian Rhapsody"           # Song name
media_id="Queen - Bohemian Rhapsody"   # Artist - Song (more accurate)
media_id="Abbey Road"                   # Album name
media_id="Taylor Swift"                 # Artist name (plays their music)
```

### By URI (From search results)
```
media_id="library://track/123"
media_id="spotify://track/abc123"
```

## Media Types
- **track**: Play a specific song (default)
- **album**: Play a full album
- **artist**: Play songs by an artist (shuffled or top tracks)
- **playlist**: Play a playlist
- **radio**: Play a radio station

## Queue Behavior (enqueue parameter)
- **play**: Start playing immediately, adds to queue (default)
- **replace**: Clear queue first, then play
- **next**: Insert after currently playing track
- **add**: Add to end of queue

## Player Selection
- If no player_id specified, plays on the default/active player
- Use ma_players to see available players
- Players are typically: media_player.mass_<room_name>

## Common Patterns

"Play Enya" →
  ma_play media_id="Enya" media_type="artist"

"Play Bohemian Rhapsody" →
  ma_play media_id="Bohemian Rhapsody Queen" media_type="track"

"Play the Abbey Road album" →
  ma_play media_id="Abbey Road Beatles" media_type="album"

"Play music in the kitchen" →
  ma_play media_id="<song>" player_id="media_player.mass_kitchen"

## Verification
After playing, the tool verifies playback actually started.
If verification fails, suggests using ma_search first to confirm the media exists.
""",
                examples=[
                    UsageExample(
                        title="Play a song by name",
                        description="Simple track playback",
                        code='{"media_id": "Bohemian Rhapsody Queen", "media_type": "track"}',
                    ),
                    UsageExample(
                        title="Play an artist",
                        description="Play music by a specific artist",
                        code='{"media_id": "Enya", "media_type": "artist"}',
                    ),
                    UsageExample(
                        title="Play album on specific speaker",
                        description="Play full album in a specific room",
                        code='{"media_id": "Abbey Road", "media_type": "album", "player_id": "media_player.mass_living_room"}',
                    ),
                    UsageExample(
                        title="Add song to queue",
                        description="Queue a song after the current one",
                        code='{"media_id": "Hey Jude Beatles", "media_type": "track", "enqueue": "next"}',
                    ),
                    UsageExample(
                        title="Clear queue and play",
                        description="Replace current queue with new content",
                        code='{"media_id": "relaxing piano", "media_type": "playlist", "enqueue": "replace"}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="HA returns success even if media not found!",
                        description="Home Assistant returns 200 success even if the track doesn't exist. We verify by checking player state after 2 seconds.",
                        severity="warning",
                    ),
                    ToolGotcha(
                        title="Include artist name for accuracy",
                        description="'Yesterday' might play a cover. Use 'Yesterday Beatles' for the original.",
                        severity="warning",
                    ),
                    ToolGotcha(
                        title="Don't use media-source:// URIs",
                        description="Only use MA URIs (library://, spotify://) or plain names. media-source:// causes issues.",
                        severity="error",
                    ),
                    ToolGotcha(
                        title="Player must be available",
                        description="If specified player is off or unavailable, playback fails. Check ma_players first if unsure.",
                        severity="info",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use for pause/stop/skip - use ha_device_control with media_pause/media_stop/media_next_track. Don't use to resume paused content - use ha_device_control with media_play.",
                ethical_considerations="Playing music affects everyone in the room. Consider if others might be disturbed.",
            ),
        ),
        "ma_browse": ToolInfo(
            name="ma_browse",
            description="Browse Music Assistant library categories (artists, albums, playlists)",
            when_to_use="Use to explore available music without a specific search query (e.g., 'what music do I have?', 'show me my playlists')",
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
                quick_start="Browse library: ma_browse media_type='artists' to see all artists",
                detailed_instructions="""
# Music Assistant Browse

Navigate the music library by category without a specific search query.

## When to Use
- User asks "what music do I have?"
- User wants to explore their library
- User asks "show me my playlists"
- Discovering available content before playing

## Media Types

### artists
Lists all artists in the library across all providers.
Returns: artist names, IDs, image URLs, provider info.

### albums
Lists all albums in the library.
Returns: album names, artists, year, track count, IDs.

### tracks
Lists all individual tracks.
Returns: track names, artists, albums, duration, IDs.

### playlists
Lists all playlists (user-created and provider playlists).
Returns: playlist names, track counts, owner, IDs.

## Response Format
Each item includes:
- **name**: Display name
- **media_id**: ID for use with ma_play
- **uri**: Full URI for playback
- **provider**: Which music service it's from
- **image_url**: Cover art (if available)

## Browsing vs Searching
- **ma_browse**: Explore without a query (library navigation)
- **ma_search**: Find specific content by name/keyword

## Usage Flow
1. ma_browse media_type='playlists' → see available playlists
2. Find interesting playlist in results
3. ma_play media_id='<playlist_id>' media_type='playlist'
""",
                examples=[
                    UsageExample(
                        title="List all artists",
                        description="See all artists in the library",
                        code='{"media_type": "artists", "limit": 50}',
                    ),
                    UsageExample(
                        title="Browse playlists",
                        description="See available playlists",
                        code='{"media_type": "playlists"}',
                    ),
                    UsageExample(
                        title="List albums",
                        description="Browse the album collection",
                        code='{"media_type": "albums", "limit": 25}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Results are from all providers",
                        description="Browse returns content from ALL configured providers (Spotify, local library, etc.) combined. Results may be deduplicated.",
                        severity="info",
                    ),
                    ToolGotcha(
                        title="Large libraries may be slow",
                        description="Libraries with thousands of items may take longer to browse. Use limit parameter to control response size.",
                        severity="info",
                    ),
                    ToolGotcha(
                        title="Use search for specific content",
                        description="If user wants something specific like 'Taylor Swift songs', use ma_search instead of browsing all tracks.",
                        severity="warning",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use when user wants specific content - use ma_search instead. Don't use just to see what's playing - use ma_players or ma_queue.",
                ethical_considerations="Library browsing reveals music collection and preferences. Handle with appropriate privacy.",
            ),
        ),
        "ma_queue": ToolInfo(
            name="ma_queue",
            description="View or manage the playback queue for a Music Assistant player",
            when_to_use="Use to see what's playing now, what's up next, or view the full queue (e.g., 'what's playing?', 'what's next?', 'show me the queue')",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "player_id": {
                        "type": "string",
                        "description": "Player entity ID to get queue for (e.g., media_player.mass_living_room)",
                    },
                },
                required=["player_id"],
            ),
            documentation=ToolDocumentation(
                quick_start="View queue: ma_queue player_id='media_player.mass_living_room'",
                detailed_instructions="""
# Music Assistant Queue

View the current playback queue for a Music Assistant player.

## When to Use
- User asks "what's playing?"
- User asks "what's up next?"
- User wants to see the queue
- User asks "what song is this?"
- Before modifying the queue with ma_play

## Response Format
The queue includes:
- **current_item**: Currently playing track with full metadata
- **queue_items**: List of upcoming tracks
- **current_index**: Position in queue (0-based)
- **repeat_mode**: off, one, all
- **shuffle_enabled**: true/false

### Track Metadata
Each track includes:
- **name**: Track title
- **artist**: Artist name
- **album**: Album name
- **duration**: Length in seconds
- **media_id**: ID for requeuing
- **image_url**: Album art

## Getting Player ID
Use ma_players first to see available players and their entity IDs.
MA players typically have IDs like: media_player.mass_<room_name>

## Queue Management
To modify the queue, use ma_play with the enqueue parameter:
- **enqueue='next'**: Insert after current track
- **enqueue='add'**: Add to end of queue
- **enqueue='replace'**: Clear and start fresh

## Playback Control
To control playback (pause, skip, stop), use ha_device_control:
- **media_pause**: Pause current track
- **media_play**: Resume playback
- **media_next_track**: Skip to next in queue
- **media_previous_track**: Go back
- **media_stop**: Stop playback entirely
""",
                examples=[
                    UsageExample(
                        title="View current queue",
                        description="See what's playing and what's coming up",
                        code='{"player_id": "media_player.mass_living_room"}',
                    ),
                    UsageExample(
                        title="Check bedroom queue",
                        description="View queue on a specific player",
                        code='{"player_id": "media_player.mass_bedroom"}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Player ID is required",
                        description="Unlike ma_play which has a default player, ma_queue requires a specific player_id. Use ma_players to find available players first.",
                        severity="warning",
                    ),
                    ToolGotcha(
                        title="MA players have mass_ prefix",
                        description="Music Assistant players typically have entity IDs like media_player.mass_<room>. Non-mass media players won't have MA queues.",
                        severity="info",
                    ),
                    ToolGotcha(
                        title="Empty queue if nothing playing",
                        description="If the player is idle, queue will be empty. This is normal - music hasn't been started yet.",
                        severity="info",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use for controlling playback (pause/skip/stop) - use ha_device_control. Don't use for adding to queue - use ma_play with enqueue parameter.",
                ethical_considerations="Queue contents reveal current listening activity and preferences.",
            ),
        ),
        "ma_players": ToolInfo(
            name="ma_players",
            description="List all Music Assistant players and their current state",
            when_to_use="Use to see available music players, what's currently playing on each, and their entity IDs for targeting playback",
            # Context enrichment: run this to show available music players in context
            context_enrichment=True,
            context_enrichment_params={},  # Empty = execute to get player list
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            ),
            documentation=ToolDocumentation(
                quick_start="List players: ma_players - shows all music players with their states and entity IDs",
                detailed_instructions="""
# Music Assistant Players

List all Music Assistant players with their current state and what's playing.

## When to Use
- User asks "where can I play music?"
- User asks "what speakers do I have?"
- Need to find the player_id for other tools (ma_play, ma_queue)
- User asks "what's playing in each room?"
- Before playing music to a specific room

## Response Format
Returns a list of players, each with:
- **entity_id**: The player ID (e.g., media_player.mass_living_room) - USE THIS with other tools!
- **name**: Friendly name (e.g., "Living Room Speaker")
- **state**: playing, paused, idle, off
- **current_media**: What's playing (if applicable)
  - track: Song name
  - artist: Artist name
  - album: Album name
  - duration: Track length
  - position: Current playback position
- **volume_level**: Current volume (0.0 - 1.0)
- **is_grouped**: Whether player is part of a group
- **group_members**: Other players in the group (if grouped)

## Player Types
Music Assistant can manage various player types:
- **Streaming speakers**: Sonos, Chromecast, AirPlay
- **Smart speakers**: Google Home, Echo
- **Network players**: Squeezebox, DLNA
- **Local playback**: On the MA server itself

## Using Results
The entity_id from this tool is used with:
- **ma_play**: `player_id='media_player.mass_bedroom'`
- **ma_queue**: `player_id='media_player.mass_bedroom'`
- **ha_device_control**: `entity_id='media_player.mass_bedroom'` for pause/stop/skip

## Player Entity ID Pattern
MA players use the pattern: `media_player.mass_<room_name>`
Examples:
- media_player.mass_living_room
- media_player.mass_bedroom
- media_player.mass_kitchen

## Grouped Playback
MA supports synchronized multi-room audio. If players are grouped:
- Commands to the group leader affect all members
- is_grouped=true and group_members shows the group
""",
                examples=[
                    UsageExample(
                        title="List all players",
                        description="Get all available players and their states",
                        code="{}",
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Players may be unavailable",
                        description="Powered-off speakers or offline devices show as 'unavailable'. They can't play music until powered on.",
                        severity="info",
                    ),
                    ToolGotcha(
                        title="mass_ prefix indicates MA control",
                        description="Only players with 'mass_' in their entity_id are controlled by Music Assistant. Other media_player entities are regular HA players.",
                        severity="warning",
                    ),
                    ToolGotcha(
                        title="Group commands apply to all",
                        description="When playing to a grouped player, all members play the same content. Check is_grouped before targeting specific rooms.",
                        severity="info",
                    ),
                    ToolGotcha(
                        title="Run this before playing to a room",
                        description="If user says 'play music in the kitchen', run ma_players first to find the correct player_id, then use ma_play.",
                        severity="warning",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use for playing music - use ma_play. Don't use for playback control - use ha_device_control. Don't use repeatedly - player list doesn't change often.",
                ethical_considerations="Player list reveals home audio setup and current listening activity in each room.",
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

    async def notify_ha_initialized(self) -> None:
        """Called after HA background initialization completes.

        This triggers Music Assistant detection now that entities are available.
        Without this, MA tools might not appear if tool discovery happened
        before HA finished loading entities.
        """
        logger.info("[HA TOOLS] HA initialized - checking for Music Assistant")
        ma_detected = await self._check_ma_available()
        if ma_detected:
            logger.info("[HA TOOLS] Music Assistant tools now available")
        else:
            logger.debug("[HA TOOLS] Music Assistant not detected after HA init")

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

        # Extract optional parameters for various domains
        kwargs: Dict[str, Any] = {}
        # Light parameters
        if "brightness" in params:
            kwargs["brightness"] = params["brightness"]
        if "color_temp" in params:
            kwargs["color_temp"] = params["color_temp"]
        # Media player parameters
        if "volume_level" in params:
            kwargs["volume_level"] = params["volume_level"]
        # Climate parameters
        if "temperature" in params:
            kwargs["temperature"] = params["temperature"]
        if "hvac_mode" in params:
            kwargs["hvac_mode"] = params["hvac_mode"]
        # Fan parameters
        if "percentage" in params:
            kwargs["percentage"] = params["percentage"]

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
