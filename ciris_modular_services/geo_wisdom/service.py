"""
Geographic wisdom adapter using OpenStreetMap Nominatim API.

This adapter provides navigation and geographic guidance capabilities
WITHOUT any medical/health functionality.

LIABILITY: This is informational only, not professional navigation advice.
"""

import asyncio
import json
import logging
import os
from types import SimpleNamespace
from typing import Any, Dict, Optional
from urllib.parse import quote

import aiohttp

from ciris_engine.protocols.services import WiseAuthorityService
from ciris_engine.schemas.services.authority_core import (
    DeferralRequest,
    DeferralResponse,
    GuidanceRequest,
    GuidanceResponse,
    WisdomAdvice,
)
from ciris_engine.schemas.services.context import GuidanceContext
from ciris_engine.schemas.services.core import ServiceCapabilities

logger = logging.getLogger(__name__)


class GeoWisdomAdapter(WiseAuthorityService):
    """
    Geographic routing wisdom provider using OpenStreetMap.

    SAFE DOMAIN: Navigation and geographic information only.
    NO medical/health capabilities.
    """

    def __init__(self) -> None:
        """Initialize the geo wisdom adapter."""
        # OpenStreetMap Nominatim doesn't require API key but has usage limits
        # We should respect their usage policy: max 1 request per second
        self.base_url = "https://nominatim.openstreetmap.org"
        self.routing_url = "https://router.project-osrm.org"  # OSRM for routing

        # User agent is required by OSM policy
        self.user_agent = os.getenv("CIRIS_OSM_USER_AGENT", "CIRIS/1.0 (contact@ciris.ai)")

        # Rate limiting
        self._last_request_time: float = 0.0
        self._min_request_interval = 1.0  # 1 second between requests

        logger.info(f"GeoWisdomAdapter initialized with user agent: {self.user_agent}")

    def get_capabilities(self) -> ServiceCapabilities:
        """Return adapter capabilities."""
        return ServiceCapabilities(
            service_name="geo_wisdom",
            actions=["get_guidance", "fetch_guidance"],
            version="1.0.0",
            dependencies=[],
            metadata={"capabilities": ["domain:navigation", "modality:geo:route", "modality:geo:geocode"]}
        )

    async def _rate_limit(self) -> None:
        """Enforce rate limiting for OSM API."""
        import time

        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    async def _geocode(self, location: str) -> Optional[Dict[str, Any]]:
        """Convert location name to coordinates."""
        await self._rate_limit()

        headers = {"User-Agent": self.user_agent}
        params: Dict[str, str | int] = {"q": location, "format": "json", "limit": 1}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/search", headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data:
                            return {
                                "lat": float(data[0]["lat"]),
                                "lon": float(data[0]["lon"]),
                                "display_name": data[0]["display_name"],
                            }
        except Exception as e:
            logger.warning(f"Geocoding failed for {location}: {e}")

        return None

    async def _get_route(self, start_coords: Dict[str, Any], end_coords: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get route between two coordinates using OSRM."""
        # OSRM doesn't require rate limiting as aggressively

        url = (
            f"{self.routing_url}/route/v1/driving/"
            f"{start_coords['lon']},{start_coords['lat']};"
            f"{end_coords['lon']},{end_coords['lat']}"
            f"?overview=false&steps=false"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers={"User-Agent": self.user_agent}, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == "Ok" and data.get("routes"):
                            route = data["routes"][0]
                            return {
                                "distance_km": round(route["distance"] / 1000, 1),
                                "duration_min": round(route["duration"] / 60, 0),
                                "via": "OpenStreetMap routing",
                            }
        except Exception as e:
            logger.warning(f"Routing failed: {e}")

        return None

    async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse:
        """
        Get geographic guidance for navigation requests.

        CRITICAL: Rejects any medical/health related requests.
        """
        # Validate this is a navigation request
        if not request.capability or "navigation" not in request.capability.lower():
            return GuidanceResponse(
                reasoning="GeoWisdomAdapter only handles navigation requests", wa_id="geo_wisdom", signature="geo_sig"
            )

        # Extract locations from inputs
        inputs = request.inputs or {}
        start = inputs.get("start")
        end = inputs.get("end")

        if not start or not end:
            return GuidanceResponse(
                custom_guidance="Please provide start and end locations",
                reasoning="Missing location information",
                wa_id="geo_wisdom",
                signature="geo_sig",
            )

        try:
            # Geocode locations
            start_coords = await self._geocode(start)
            if not start_coords:
                return GuidanceResponse(
                    custom_guidance=f"Could not find location: {start}",
                    reasoning="Geocoding failed for start location",
                    wa_id="geo_wisdom",
                    signature="geo_sig",
                )

            end_coords = await self._geocode(end)
            if not end_coords:
                return GuidanceResponse(
                    custom_guidance=f"Could not find location: {end}",
                    reasoning="Geocoding failed for end location",
                    wa_id="geo_wisdom",
                    signature="geo_sig",
                )

            # Get route
            route_info = await self._get_route(start_coords, end_coords)

            if route_info:
                # Select best option if provided
                selected = None
                if request.options:
                    # Simple heuristic: prefer faster routes
                    if "highway" in request.options[0].lower() or "fast" in request.options[0].lower():
                        selected = request.options[0]
                    else:
                        selected = request.options[0]

                explanation = (
                    f"Route from {start_coords['display_name'][:50]}... "
                    f"to {end_coords['display_name'][:50]}... "
                    f"Distance: {route_info['distance_km']}km, "
                    f"Duration: {route_info['duration_min']} minutes"
                )

                return GuidanceResponse(
                    selected_option=selected,
                    custom_guidance=explanation,
                    reasoning=f"Route calculated via OpenStreetMap",
                    wa_id="geo_wisdom",
                    signature="geo_sig",
                    advice=[
                        WisdomAdvice(
                            capability="domain:navigation",
                            provider_type="geo",
                            provider_name="GeoWisdomAdapter",
                            confidence=0.85,
                            explanation=explanation,
                            data={
                                "distance": f"{route_info['distance_km']}km",
                                "duration": f"{route_info['duration_min']}min",
                                "via": route_info["via"],
                                "start_lat": str(start_coords["lat"]),
                                "start_lon": str(start_coords["lon"]),
                                "end_lat": str(end_coords["lat"]),
                                "end_lon": str(end_coords["lon"]),
                            },
                            disclaimer=(
                                "This is informational routing only. "
                                "Always follow traffic laws and road conditions. "
                                "Not responsible for navigation errors."
                            ),
                            requires_professional=False,
                        )
                    ],
                )
            else:
                return GuidanceResponse(
                    custom_guidance="Could not calculate route",
                    reasoning="Routing service unavailable",
                    wa_id="geo_wisdom",
                    signature="geo_sig",
                )

        except Exception as e:
            logger.error(f"GeoWisdomAdapter error: {e}", exc_info=True)
            return GuidanceResponse(
                custom_guidance="Geographic service error",
                reasoning=f"Error: {str(e)}",
                wa_id="geo_wisdom",
                signature="geo_sig",
            )

    async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]:
        """Legacy compatibility method."""
        request = GuidanceRequest(context=context.question, options={}, urgency="normal")

        response = await self.get_guidance(request)
        return response.custom_guidance or response.reasoning

    async def send_deferral(self, request: DeferralRequest) -> str:
        """Geographic services don't handle deferrals."""
        # Protocol expects str return type
        return "geo_wisdom_not_supported"


# Example usage:
# adapter = GeoWisdomAdapter()
# request = GuidanceRequest(
#     context="Navigate to work",
#     options=["Fastest route", "Scenic route"],
#     capability="domain:navigation",
#     inputs={"start": "San Francisco City Hall", "end": "Golden Gate Bridge"}
# )
# response = await adapter.get_guidance(request)
