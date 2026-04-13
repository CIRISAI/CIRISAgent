"""
Weather tool service using NOAA National Weather Service API.

This adapter provides weather data tool capabilities.

LIABILITY: This is informational only, not professional meteorological advice.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiohttp

from ciris_engine.logic.utils.location_utils import get_user_location
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
from ciris_engine.schemas.services.core import ServiceCapabilities

logger = logging.getLogger(__name__)


class WeatherToolService:
    """
    Weather tool service using NOAA National Weather Service API.

    Provides tools for:
    - Current weather conditions
    - Weather forecast
    - Weather alerts

    SAFE DOMAIN: Weather and atmospheric conditions only.
    NO medical/health capabilities.
    """

    def __init__(self) -> None:
        """Initialize the weather tool service."""
        # NOAA API is free but requires a User-Agent
        self.base_url = "https://api.weather.gov"

        # User agent is required by NOAA
        # Use PUBLIC_API_CONTACT_EMAIL from wizard, fall back to legacy env var
        contact_email = os.getenv("PUBLIC_API_CONTACT_EMAIL", "")
        if contact_email:
            self.user_agent = f"CIRIS/2.3 ({contact_email})"
        else:
            self.user_agent = os.getenv("CIRIS_NOAA_USER_AGENT", "CIRIS/1.0 (contact@ciris.ai)")

        # Optional: OpenWeatherMap as backup (requires API key)
        self.owm_api_key = os.getenv("CIRIS_OPENWEATHERMAP_API_KEY")
        self.owm_base_url = "https://api.openweathermap.org/data/2.5"

        # Cache for grid points (NOAA uses a grid system)
        self._grid_cache: Dict[tuple[float, float], Dict[str, Any]] = {}

        # Default location: try user location first, fall back to config
        self._default_lat: Optional[float] = None
        self._default_lon: Optional[float] = None
        self._default_location_string: Optional[str] = None
        self._location_source: Optional[str] = None

        # Try user location from setup wizard first
        user_location = get_user_location()
        if user_location.has_coordinates():
            self._default_lat = user_location.latitude
            self._default_lon = user_location.longitude
            self._default_location_string = user_location.location_string
            self._location_source = "user_setup"
            logger.info(
                f"Using user location from setup: {user_location.location_string} "
                f"({self._default_lat}, {self._default_lon})"
            )
        else:
            # Fall back to configured default location
            self._default_location = os.getenv("CIRIS_WEATHER_DEFAULT_LOCATION")
            if self._default_location:
                self._parse_default_location()
                if self._default_lat is not None:
                    self._location_source = "config"

        # Tool definitions
        self._tools: Dict[str, ToolInfo] = self._define_tools()

        logger.info("WeatherToolService initialized with NOAA API")
        if self._default_lat is not None:
            logger.info(f"Default location ({self._location_source}): {self._default_lat}, {self._default_lon}")
        if self.owm_api_key:
            logger.info("OpenWeatherMap backup available")

    def _parse_default_location(self) -> None:
        """Parse default location from env var (format: 'lat,lon' or city name)."""
        if not self._default_location:
            return

        # Try to parse as "lat,lon" format
        if "," in self._default_location:
            try:
                parts = self._default_location.split(",")
                if len(parts) == 2:
                    self._default_lat = float(parts[0].strip())
                    self._default_lon = float(parts[1].strip())
                    logger.info(f"Parsed default location: lat={self._default_lat}, lon={self._default_lon}")
                    return
            except ValueError:
                pass

        logger.warning(f"Could not parse default location '{self._default_location}' - expected 'lat,lon' format")

    def _get_coordinates_with_defaults(
        self, parameters: Dict[str, Any]
    ) -> tuple[Optional[float], Optional[float], bool]:
        """
        Get coordinates from parameters, falling back to configured defaults.

        Returns:
            (latitude, longitude, used_defaults) - used_defaults is True if defaults were applied
        """
        lat = parameters.get("latitude")
        lon = parameters.get("longitude")
        used_defaults = False

        # If coordinates not provided, use defaults
        if lat is None and lon is None and self._default_lat is not None:
            lat = self._default_lat
            lon = self._default_lon
            used_defaults = True
            logger.info(f"Using configured default location: {lat}, {lon}")

        return lat, lon, used_defaults

    def _define_tools(self) -> Dict[str, ToolInfo]:
        """Define available tools."""
        # Build dynamic description with default location info
        default_info = ""
        lat_desc = "Latitude coordinate of the location"
        lon_desc = "Longitude coordinate of the location"

        if self._default_lat is not None and self._default_lon is not None:
            location_desc = self._default_location_string or f"{self._default_lat}, {self._default_lon}"
            source_desc = "from setup" if self._location_source == "user_setup" else "configured"
            default_info = (
                f" User's location ({source_desc}): {location_desc}. "
                f"If no specific location is mentioned, use empty parameters {{}} to use this default."
            )
            lat_desc = f"Latitude coordinate (default: {self._default_lat} if omitted)"
            lon_desc = f"Longitude coordinate (default: {self._default_lon} if omitted)"

        tools: Dict[str, ToolInfo] = {
            "weather:current": ToolInfo(
                name="weather:current",
                description=f"Get current weather conditions for a location (temperature, wind, conditions).{default_info}",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "latitude": {
                            "type": "number",
                            "description": lat_desc,
                        },
                        "longitude": {
                            "type": "number",
                            "description": lon_desc,
                        },
                    },
                    required=[] if self._default_lat else ["latitude", "longitude"],
                ),
                category="weather",
                cost=0.0,
                when_to_use="When you need current weather conditions at a specific location",
                documentation=ToolDocumentation(
                    quick_start="Provide latitude and longitude coordinates to get current weather. "
                    "Uses NOAA (US) with OpenWeatherMap fallback for international locations.",
                    detailed_instructions="""
## Coordinate Format

- Latitude: decimal degrees (e.g., 40.7128 for NYC)
- Longitude: decimal degrees, negative for West (e.g., -74.0060 for NYC)

## Data Sources

1. **NOAA** (primary): US National Weather Service - most accurate for US locations
2. **OpenWeatherMap** (fallback): Global coverage, requires API key

## Response Fields

- temperature: Current temperature
- wind_speed/wind_direction: Wind conditions
- conditions: Short description (e.g., "Partly Cloudy")
- detailed: Full forecast description
- precipitation_chance: Percentage chance of precipitation
""",
                    examples=[
                        UsageExample(
                            title="New York City weather",
                            code='{"latitude": 40.7128, "longitude": -74.0060}',
                        ),
                        UsageExample(
                            title="Los Angeles weather",
                            code='{"latitude": 34.0522, "longitude": -118.2437}',
                        ),
                    ],
                    gotchas=[
                        ToolGotcha(
                            title="US-only for NOAA",
                            description="NOAA only covers US locations. International locations "
                            "require OpenWeatherMap API key (CIRIS_OPENWEATHERMAP_API_KEY).",
                            severity="info",
                        ),
                        ToolGotcha(
                            title="Coordinates required",
                            description="You must provide coordinates, not city names. "
                            "Use navigation:geocode to convert addresses to coordinates first.",
                            severity="warning",
                        ),
                    ],
                ),
                dma_guidance=ToolDMAGuidance(
                    when_not_to_use="Don't use for medical decisions based on weather. "
                    "Weather data is informational, not for life-safety decisions.",
                    prerequisite_actions=["navigation:geocode if you only have an address"],
                ),
            ),
            "weather:forecast": ToolInfo(
                name="weather:forecast",
                description=f"Get weather forecast for a location (upcoming conditions).{default_info}",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "latitude": {
                            "type": "number",
                            "description": lat_desc,
                        },
                        "longitude": {
                            "type": "number",
                            "description": lon_desc,
                        },
                    },
                    required=[] if self._default_lat else ["latitude", "longitude"],
                ),
                category="weather",
                cost=0.0,
                when_to_use="When you need weather forecast for planning ahead",
            ),
            "weather:alerts": ToolInfo(
                name="weather:alerts",
                description=f"Get active weather alerts for a location (warnings, watches, advisories).{default_info}",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "latitude": {
                            "type": "number",
                            "description": lat_desc,
                        },
                        "longitude": {
                            "type": "number",
                            "description": lon_desc,
                        },
                    },
                    required=[] if self._default_lat else ["latitude", "longitude"],
                ),
                category="weather",
                cost=0.0,
                when_to_use="When you need to check for severe weather warnings or alerts",
            ),
        }

        # Add context enrichment tool if user location is available (from any source)
        if self._default_lat is not None:
            tools["weather:my_location"] = ToolInfo(
                name="weather:my_location",
                description=(
                    f"Get current weather at user's location ({self._default_location_string}). "
                    "This tool automatically uses the user's configured location from setup."
                ),
                parameters=ToolParameterSchema(
                    type="object",
                    properties={},
                    required=[],
                ),
                category="weather",
                cost=0.0,
                when_to_use="When you need weather for the user's location without asking for coordinates",
                context_enrichment=True,
                context_enrichment_params={"_cache_ttl": 300.0},  # Cache for 5 minutes
            )

        return tools

    def get_capabilities(self) -> ServiceCapabilities:
        """Return service capabilities."""
        return ServiceCapabilities(
            service_name="weather",
            actions=list(self._tools.keys()),
            version="1.0.0",
            dependencies=[],
            metadata={
                "capabilities": [
                    "weather:current",
                    "weather:forecast",
                    "weather:alerts",
                    "domain:weather",
                ]
            },
        )

    async def start(self) -> None:
        """Start the service."""
        logger.info("WeatherToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("WeatherToolService stopped")

    def refresh_location(self) -> bool:
        """Refresh location from environment variables.

        Call this after user location is updated to pick up new coordinates.
        Re-reads location from env vars and re-registers tools.

        Returns:
            True if location was updated, False if unchanged or unavailable.
        """
        user_location = get_user_location()

        # Check if location changed
        old_lat = self._default_lat
        old_lon = self._default_lon

        if user_location.has_coordinates():
            self._default_lat = user_location.latitude
            self._default_lon = user_location.longitude
            self._default_location_string = user_location.location_string
            self._location_source = "user_setup"
            logger.info(
                f"Location refreshed: {user_location.location_string} "
                f"({self._default_lat}, {self._default_lon})"
            )
        else:
            # No coordinates available
            self._default_lat = None
            self._default_lon = None
            self._default_location_string = None
            self._location_source = None
            logger.info("Location cleared (no coordinates available)")

        # Check if anything changed
        changed = (old_lat != self._default_lat) or (old_lon != self._default_lon)

        if changed:
            # Re-register tools with updated location info
            self._tools = self._define_tools()
            logger.info(f"Tools re-registered: {list(self._tools.keys())}")

        return changed

    # ========== Tool Service Protocol Methods ==========

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolExecutionResult:
        """Execute a weather tool."""
        correlation_id = str(uuid4())

        if tool_name not in self._tools:
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                error=f"Unknown tool: {tool_name}",
                correlation_id=correlation_id,
            )

        try:
            if tool_name == "weather:current":
                return await self._execute_current(parameters, correlation_id)
            elif tool_name == "weather:forecast":
                return await self._execute_forecast(parameters, correlation_id)
            elif tool_name == "weather:alerts":
                return await self._execute_alerts(parameters, correlation_id)
            elif tool_name == "weather:my_location":
                return await self._execute_my_location(correlation_id)
            else:
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.NOT_FOUND,
                    success=False,
                    error=f"Tool not implemented: {tool_name}",
                    correlation_id=correlation_id,
                )
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def list_tools(self) -> List[str]:
        """List available tools."""
        return list(self._tools.keys())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a tool."""
        tool = self._tools.get(tool_name)
        return tool.parameters if tool else None

    async def get_available_tools(self) -> List[str]:
        """Get list of available tools."""
        return list(self._tools.keys())

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed tool information."""
        return self._tools.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get info for all tools."""
        return list(self._tools.values())

    async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate parameters for a tool."""
        tool = self._tools.get(tool_name)
        if not tool:
            return False

        # Check required parameters
        for required in tool.parameters.required:
            if required not in parameters:
                return False
        return True

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result by correlation ID (tools execute synchronously so this returns None)."""
        return None

    def get_service_metadata(self) -> Dict[str, Any]:
        """Get service metadata."""
        return {
            "data_source": True,
            "data_source_type": "rest",
            "contains_pii": False,
            "gdpr_applicable": False,
            "connector_id": "noaa_weather",
        }

    # ========== Internal Methods ==========

    async def _get_grid_point(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get NOAA grid point for coordinates."""
        cache_key = (round(lat, 4), round(lon, 4))
        if cache_key in self._grid_cache:
            return self._grid_cache[cache_key]

        headers = {"User-Agent": self.user_agent}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/points/{lat},{lon}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        grid_data = {
                            "gridId": data["properties"]["gridId"],
                            "gridX": data["properties"]["gridX"],
                            "gridY": data["properties"]["gridY"],
                            "forecast_url": data["properties"]["forecast"],
                            "forecast_hourly_url": data["properties"]["forecastHourly"],
                            "city": data["properties"]
                            .get("relativeLocation", {})
                            .get("properties", {})
                            .get("city", ""),
                            "state": data["properties"]
                            .get("relativeLocation", {})
                            .get("properties", {})
                            .get("state", ""),
                        }
                        self._grid_cache[cache_key] = grid_data
                        return grid_data
        except Exception as e:
            logger.warning(f"Failed to get NOAA grid point: {e}")

        return None

    async def _get_noaa_forecast(self, grid_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get forecast from NOAA."""
        headers = {"User-Agent": self.user_agent}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    grid_data["forecast_url"],
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        periods = data["properties"]["periods"]
                        if periods:
                            current = periods[0]
                            return {
                                "temperature": current["temperature"],
                                "temperature_unit": current["temperatureUnit"],
                                "wind_speed": current["windSpeed"],
                                "wind_direction": current["windDirection"],
                                "short_forecast": current["shortForecast"],
                                "detailed_forecast": current["detailedForecast"],
                                "precipitation_chance": self._extract_precipitation_chance(current["detailedForecast"]),
                                "periods": periods[:5],  # Include next 5 periods for forecast
                            }
        except Exception as e:
            logger.warning(f"Failed to get NOAA forecast: {e}")

        return None

    async def _get_noaa_alerts(self, lat: float, lon: float) -> List[Dict[str, Any]]:
        """Get weather alerts for a location."""
        headers = {"User-Agent": self.user_agent}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/alerts/active",
                    headers=headers,
                    params={"point": f"{lat},{lon}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        alerts = []
                        for feature in data.get("features", []):
                            props = feature["properties"]
                            alerts.append(
                                {
                                    "event": props.get("event"),
                                    "severity": props.get("severity"),
                                    "urgency": props.get("urgency"),
                                    "headline": props.get("headline"),
                                    "description": props.get("description", "")[:500],
                                    "effective": props.get("effective"),
                                    "expires": props.get("expires"),
                                }
                            )
                        return alerts
        except Exception as e:
            logger.warning(f"Failed to get NOAA alerts: {e}")

        return []

    async def _get_owm_weather(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get weather from OpenWeatherMap as fallback."""
        if not self.owm_api_key:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.owm_base_url}/weather",
                    params={"lat": lat, "lon": lon, "appid": self.owm_api_key, "units": "imperial"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "temperature": round(data["main"]["temp"]),
                            "temperature_unit": "F",
                            "wind_speed": f"{round(data['wind']['speed'])} mph",
                            "wind_direction": self._degrees_to_cardinal(data["wind"].get("deg", 0)),
                            "short_forecast": data["weather"][0]["main"],
                            "detailed_forecast": data["weather"][0]["description"],
                            "precipitation_chance": 0,
                            "humidity": data["main"].get("humidity", 0),
                            "feels_like": round(data["main"].get("feels_like", data["main"]["temp"])),
                        }
        except Exception as e:
            logger.warning(f"OpenWeatherMap fallback failed: {e}")

        return None

    def _extract_precipitation_chance(self, text: str) -> int:
        """Extract precipitation percentage from forecast text."""
        match = re.search(r"(\d+)\s*percent chance", text.lower())
        if match:
            return int(match.group(1))
        return 0

    def _degrees_to_cardinal(self, degrees: float) -> str:
        """Convert degrees to cardinal direction."""
        directions = [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ]
        index = round(degrees / 22.5) % 16
        return directions[index]

    # ========== Tool Implementations ==========

    async def _execute_my_location(self, correlation_id: str) -> ToolExecutionResult:
        """Execute weather for user's configured location (context enrichment tool)."""
        if self._default_lat is None or self._default_lon is None:
            return ToolExecutionResult(
                tool_name="weather:my_location",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="No user location available. Set location during setup to use this feature.",
                correlation_id=correlation_id,
            )

        # Delegate to current weather with user's coordinates
        result = await self._execute_current(
            {"latitude": self._default_lat, "longitude": self._default_lon},
            correlation_id,
        )

        # Update tool name and add location context
        result.tool_name = "weather:my_location"
        if result.data:
            result.data["user_location"] = self._default_location_string
            result.data["location_source"] = self._location_source

        return result

    async def _execute_current(self, parameters: Dict[str, Any], correlation_id: str) -> ToolExecutionResult:
        """Execute current weather tool."""
        lat, lon, used_defaults = self._get_coordinates_with_defaults(parameters)

        if lat is None or lon is None:
            default_hint = ""
            if self._default_location:
                default_hint = f" (configured default '{self._default_location}' could not be parsed)"
            else:
                default_hint = " (no default location configured - set via adapter wizard)"
            return ToolExecutionResult(
                tool_name="weather:current",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error=f"Missing required parameters: latitude and longitude{default_hint}",
                correlation_id=correlation_id,
            )

        try:
            lat_float = float(lat)
            lon_float = float(lon)
        except (ValueError, TypeError):
            return ToolExecutionResult(
                tool_name="weather:current",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Invalid coordinate values",
                correlation_id=correlation_id,
            )

        # Try NOAA first (US only)
        weather_data = None
        source = "NOAA"
        location_info = {}

        grid_data = await self._get_grid_point(lat_float, lon_float)
        if grid_data:
            weather_data = await self._get_noaa_forecast(grid_data)
            location_info = {
                "city": grid_data.get("city", ""),
                "state": grid_data.get("state", ""),
            }

        # Fallback to OpenWeatherMap if NOAA fails
        if not weather_data:
            weather_data = await self._get_owm_weather(lat_float, lon_float)
            source = "OpenWeatherMap"

        if not weather_data:
            return ToolExecutionResult(
                tool_name="weather:current",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Weather data unavailable for this location",
                correlation_id=correlation_id,
            )

        return ToolExecutionResult(
            tool_name="weather:current",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={
                "latitude": lat_float,
                "longitude": lon_float,
                "location": location_info,
                "temperature": weather_data["temperature"],
                "temperature_unit": weather_data["temperature_unit"],
                "wind_speed": weather_data["wind_speed"],
                "wind_direction": weather_data["wind_direction"],
                "conditions": weather_data["short_forecast"],
                "detailed": weather_data["detailed_forecast"],
                "precipitation_chance": weather_data.get("precipitation_chance", 0),
                "source": source,
                "disclaimer": "Weather conditions can change rapidly. Check official sources for critical decisions.",
            },
            correlation_id=correlation_id,
        )

    async def _execute_forecast(self, parameters: Dict[str, Any], correlation_id: str) -> ToolExecutionResult:
        """Execute weather forecast tool."""
        lat, lon, used_defaults = self._get_coordinates_with_defaults(parameters)

        if lat is None or lon is None:
            default_hint = ""
            if self._default_location:
                default_hint = f" (configured default '{self._default_location}' could not be parsed)"
            else:
                default_hint = " (no default location configured - set via adapter wizard)"
            return ToolExecutionResult(
                tool_name="weather:forecast",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error=f"Missing required parameters: latitude and longitude{default_hint}",
                correlation_id=correlation_id,
            )

        try:
            lat_float = float(lat)
            lon_float = float(lon)
        except (ValueError, TypeError):
            return ToolExecutionResult(
                tool_name="weather:forecast",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Invalid coordinate values",
                correlation_id=correlation_id,
            )

        grid_data = await self._get_grid_point(lat_float, lon_float)
        if not grid_data:
            return ToolExecutionResult(
                tool_name="weather:forecast",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Could not get forecast data for this location (NOAA US-only)",
                correlation_id=correlation_id,
            )

        weather_data = await self._get_noaa_forecast(grid_data)
        if not weather_data or "periods" not in weather_data:
            return ToolExecutionResult(
                tool_name="weather:forecast",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Forecast data unavailable",
                correlation_id=correlation_id,
            )

        # Format forecast periods
        forecast_periods = []
        for period in weather_data.get("periods", []):
            forecast_periods.append(
                {
                    "name": period.get("name", ""),
                    "temperature": period.get("temperature"),
                    "temperature_unit": period.get("temperatureUnit", "F"),
                    "wind_speed": period.get("windSpeed", ""),
                    "wind_direction": period.get("windDirection", ""),
                    "conditions": period.get("shortForecast", ""),
                    "detailed": period.get("detailedForecast", ""),
                }
            )

        return ToolExecutionResult(
            tool_name="weather:forecast",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={
                "latitude": lat_float,
                "longitude": lon_float,
                "location": {
                    "city": grid_data.get("city", ""),
                    "state": grid_data.get("state", ""),
                },
                "forecast": forecast_periods,
                "source": "NOAA",
                "disclaimer": "Forecasts are predictions and may change. Check official sources for critical decisions.",
            },
            correlation_id=correlation_id,
        )

    async def _execute_alerts(self, parameters: Dict[str, Any], correlation_id: str) -> ToolExecutionResult:
        """Execute weather alerts tool."""
        lat, lon, used_defaults = self._get_coordinates_with_defaults(parameters)

        if lat is None or lon is None:
            default_hint = ""
            if self._default_location:
                default_hint = f" (configured default '{self._default_location}' could not be parsed)"
            else:
                default_hint = " (no default location configured - set via adapter wizard)"
            return ToolExecutionResult(
                tool_name="weather:alerts",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error=f"Missing required parameters: latitude and longitude{default_hint}",
                correlation_id=correlation_id,
            )

        try:
            lat_float = float(lat)
            lon_float = float(lon)
        except (ValueError, TypeError):
            return ToolExecutionResult(
                tool_name="weather:alerts",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Invalid coordinate values",
                correlation_id=correlation_id,
            )

        alerts = await self._get_noaa_alerts(lat_float, lon_float)

        return ToolExecutionResult(
            tool_name="weather:alerts",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={
                "latitude": lat_float,
                "longitude": lon_float,
                "alert_count": len(alerts),
                "alerts": alerts,
                "source": "NOAA",
                "disclaimer": "Always take weather alerts seriously. Check official sources and local authorities.",
            },
            correlation_id=correlation_id,
        )
