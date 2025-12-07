"""
Navigation tool service using OpenStreetMap Nominatim and OSRM APIs.

This adapter provides navigation and geographic tool capabilities.

LIABILITY: This is informational only, not professional navigation advice.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiohttp

from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.services.core import ServiceCapabilities

logger = logging.getLogger(__name__)


class NavigationToolService:
    """
    Navigation tool service using OpenStreetMap.

    Provides tools for:
    - Geocoding (address to coordinates)
    - Reverse geocoding (coordinates to address)
    - Route calculation (point A to B)

    SAFE DOMAIN: Navigation and geographic information only.
    """

    def __init__(self) -> None:
        """Initialize the navigation tool service."""
        # OpenStreetMap Nominatim doesn't require API key but has usage limits
        # We should respect their usage policy: max 1 request per second
        self.base_url = "https://nominatim.openstreetmap.org"
        self.routing_url = "https://router.project-osrm.org"  # OSRM for routing

        # User agent is required by OSM policy
        self.user_agent = os.getenv("CIRIS_OSM_USER_AGENT", "CIRIS/1.0 (contact@ciris.ai)")

        # Rate limiting
        self._last_request_time: float = 0.0
        self._min_request_interval = 1.0  # 1 second between requests

        # Tool definitions
        self._tools: Dict[str, ToolInfo] = self._define_tools()

        logger.info(f"NavigationToolService initialized with user agent: {self.user_agent}")

    def _define_tools(self) -> Dict[str, ToolInfo]:
        """Define available tools."""
        return {
            "navigation:geocode": ToolInfo(
                name="navigation:geocode",
                description="Convert an address or place name to geographic coordinates (latitude/longitude)",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "location": {
                            "type": "string",
                            "description": "Address or place name to geocode (e.g., 'San Francisco City Hall')",
                        }
                    },
                    required=["location"],
                ),
                category="navigation",
                cost=0.0,
                when_to_use="When you need to find the coordinates of a location by name or address",
            ),
            "navigation:reverse_geocode": ToolInfo(
                name="navigation:reverse_geocode",
                description="Convert geographic coordinates to an address or place name",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "latitude": {
                            "type": "number",
                            "description": "Latitude coordinate",
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Longitude coordinate",
                        },
                    },
                    required=["latitude", "longitude"],
                ),
                category="navigation",
                cost=0.0,
                when_to_use="When you have coordinates and need to find the address or place name",
            ),
            "navigation:route": ToolInfo(
                name="navigation:route",
                description="Calculate driving route between two locations with distance and duration",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "start": {
                            "type": "string",
                            "description": "Starting location (address or place name)",
                        },
                        "end": {
                            "type": "string",
                            "description": "Destination location (address or place name)",
                        },
                    },
                    required=["start", "end"],
                ),
                category="navigation",
                cost=0.0,
                when_to_use="When you need to calculate distance and travel time between two locations",
            ),
        }

    def get_capabilities(self) -> ServiceCapabilities:
        """Return service capabilities."""
        return ServiceCapabilities(
            service_name="navigation",
            actions=list(self._tools.keys()),
            version="1.0.0",
            dependencies=[],
            metadata={
                "capabilities": [
                    "navigation:geocode",
                    "navigation:reverse_geocode",
                    "navigation:route",
                    "domain:navigation",
                ]
            },
        )

    async def start(self) -> None:
        """Start the service."""
        logger.info("NavigationToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("NavigationToolService stopped")

    # ========== Tool Service Protocol Methods ==========

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolExecutionResult:
        """Execute a navigation tool."""
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
            if tool_name == "navigation:geocode":
                return await self._execute_geocode(parameters, correlation_id)
            elif tool_name == "navigation:reverse_geocode":
                return await self._execute_reverse_geocode(parameters, correlation_id)
            elif tool_name == "navigation:route":
                return await self._execute_route(parameters, correlation_id)
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
            "connector_id": "openstreetmap",
        }

    # ========== Internal Methods ==========

    async def _rate_limit(self) -> None:
        """Enforce rate limiting for OSM API."""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    async def _geocode(self, location: str) -> Optional[Dict[str, Any]]:
        """Convert location name to coordinates."""
        await self._rate_limit()

        headers = {"User-Agent": self.user_agent}
        params: Dict[str, Any] = {"q": location, "format": "json", "limit": 1}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/search",
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data:
                            return {
                                "latitude": float(data[0]["lat"]),
                                "longitude": float(data[0]["lon"]),
                                "display_name": data[0]["display_name"],
                                "type": data[0].get("type", "unknown"),
                            }
        except Exception as e:
            logger.warning(f"Geocoding failed for {location}: {e}")

        return None

    async def _reverse_geocode(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Convert coordinates to address."""
        await self._rate_limit()

        headers = {"User-Agent": self.user_agent}
        params: Dict[str, Any] = {"lat": lat, "lon": lon, "format": "json"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/reverse",
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "display_name": data.get("display_name", "Unknown"),
                            "address": data.get("address", {}),
                            "type": data.get("type", "unknown"),
                        }
        except Exception as e:
            logger.warning(f"Reverse geocoding failed for {lat}, {lon}: {e}")

        return None

    async def _get_route(self, start_coords: Dict[str, Any], end_coords: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get route between two coordinates using OSRM."""
        url = (
            f"{self.routing_url}/route/v1/driving/"
            f"{start_coords['longitude']},{start_coords['latitude']};"
            f"{end_coords['longitude']},{end_coords['latitude']}"
            f"?overview=false&steps=false"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == "Ok" and data.get("routes"):
                            route = data["routes"][0]
                            return {
                                "distance_km": round(route["distance"] / 1000, 1),
                                "distance_miles": round(route["distance"] / 1609.34, 1),
                                "duration_minutes": round(route["duration"] / 60, 0),
                                "duration_hours": round(route["duration"] / 3600, 2),
                            }
        except Exception as e:
            logger.warning(f"Routing failed: {e}")

        return None

    # ========== Tool Implementations ==========

    async def _execute_geocode(self, parameters: Dict[str, Any], correlation_id: str) -> ToolExecutionResult:
        """Execute geocode tool."""
        location = parameters.get("location")
        if not location:
            return ToolExecutionResult(
                tool_name="navigation:geocode",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Missing required parameter: location",
                correlation_id=correlation_id,
            )

        result = await self._geocode(location)
        if result:
            return ToolExecutionResult(
                tool_name="navigation:geocode",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={
                    "location": location,
                    "latitude": result["latitude"],
                    "longitude": result["longitude"],
                    "display_name": result["display_name"],
                    "type": result["type"],
                },
                correlation_id=correlation_id,
            )
        else:
            return ToolExecutionResult(
                tool_name="navigation:geocode",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error=f"Could not find location: {location}",
                correlation_id=correlation_id,
            )

    async def _execute_reverse_geocode(self, parameters: Dict[str, Any], correlation_id: str) -> ToolExecutionResult:
        """Execute reverse geocode tool."""
        lat = parameters.get("latitude")
        lon = parameters.get("longitude")

        if lat is None or lon is None:
            return ToolExecutionResult(
                tool_name="navigation:reverse_geocode",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Missing required parameters: latitude and longitude",
                correlation_id=correlation_id,
            )

        try:
            lat_float = float(lat)
            lon_float = float(lon)
        except (ValueError, TypeError):
            return ToolExecutionResult(
                tool_name="navigation:reverse_geocode",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Invalid coordinate values",
                correlation_id=correlation_id,
            )

        result = await self._reverse_geocode(lat_float, lon_float)
        if result:
            return ToolExecutionResult(
                tool_name="navigation:reverse_geocode",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={
                    "latitude": lat_float,
                    "longitude": lon_float,
                    "display_name": result["display_name"],
                    "address": result["address"],
                    "type": result["type"],
                },
                correlation_id=correlation_id,
            )
        else:
            return ToolExecutionResult(
                tool_name="navigation:reverse_geocode",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error=f"Could not reverse geocode coordinates: {lat}, {lon}",
                correlation_id=correlation_id,
            )

    async def _execute_route(self, parameters: Dict[str, Any], correlation_id: str) -> ToolExecutionResult:
        """Execute route calculation tool."""
        start = parameters.get("start")
        end = parameters.get("end")

        if not start or not end:
            return ToolExecutionResult(
                tool_name="navigation:route",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Missing required parameters: start and end",
                correlation_id=correlation_id,
            )

        # Geocode both locations
        start_coords = await self._geocode(start)
        if not start_coords:
            return ToolExecutionResult(
                tool_name="navigation:route",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error=f"Could not find start location: {start}",
                correlation_id=correlation_id,
            )

        end_coords = await self._geocode(end)
        if not end_coords:
            return ToolExecutionResult(
                tool_name="navigation:route",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error=f"Could not find end location: {end}",
                correlation_id=correlation_id,
            )

        # Calculate route
        route = await self._get_route(start_coords, end_coords)
        if route:
            return ToolExecutionResult(
                tool_name="navigation:route",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={
                    "start": {
                        "query": start,
                        "resolved": start_coords["display_name"],
                        "latitude": start_coords["latitude"],
                        "longitude": start_coords["longitude"],
                    },
                    "end": {
                        "query": end,
                        "resolved": end_coords["display_name"],
                        "latitude": end_coords["latitude"],
                        "longitude": end_coords["longitude"],
                    },
                    "distance_km": route["distance_km"],
                    "distance_miles": route["distance_miles"],
                    "duration_minutes": route["duration_minutes"],
                    "duration_hours": route["duration_hours"],
                    "source": "OpenStreetMap/OSRM",
                    "disclaimer": "Travel times are estimates. Always follow traffic laws and check current conditions.",
                },
                correlation_id=correlation_id,
            )
        else:
            return ToolExecutionResult(
                tool_name="navigation:route",
                status=ToolExecutionStatus.FAILED,
                success=False,
                error="Could not calculate route between locations",
                correlation_id=correlation_id,
            )
