"""
Weather wisdom adapter using NOAA National Weather Service API.

This adapter provides weather and atmospheric guidance capabilities
WITHOUT any medical/health functionality.

LIABILITY: This is informational only, not professional meteorological advice.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

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


class WeatherWisdomAdapter(WiseAuthorityService):
    """
    Weather wisdom provider using NOAA National Weather Service API.

    SAFE DOMAIN: Weather and atmospheric conditions only.
    NO medical/health capabilities.

    Note: NOAA API is free and doesn't require an API key, but we should
    respect their usage guidelines.
    """

    def __init__(self) -> None:
        """Initialize the weather wisdom adapter."""
        # NOAA API is free but requires a User-Agent
        self.base_url = "https://api.weather.gov"

        # User agent is required by NOAA
        self.user_agent = os.getenv("CIRIS_NOAA_USER_AGENT", "CIRIS/1.0 (contact@ciris.ai)")

        # Optional: OpenWeatherMap as backup (requires API key)
        self.owm_api_key = os.getenv("CIRIS_OPENWEATHERMAP_API_KEY")
        self.owm_base_url = "https://api.openweathermap.org/data/2.5"

        # Cache for grid points (NOAA uses a grid system)
        self._grid_cache: Dict[tuple[float, float], Dict[str, Any]] = {}

        logger.info(f"WeatherWisdomAdapter initialized with NOAA API")
        if self.owm_api_key:
            logger.info("OpenWeatherMap backup available")

    def get_capabilities(self) -> ServiceCapabilities:
        """Return adapter capabilities."""
        return ServiceCapabilities(
            service_name="weather_wisdom",
            actions=["get_guidance", "fetch_guidance"],
            version="1.0.0",
            dependencies=[],
            metadata={
                "domain": "weather",
                "modality": "sensor:atmospheric",
                "capabilities": ["forecast", "alerts"]
            }
        )

    async def _get_grid_point(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get NOAA grid point for coordinates."""
        cache_key = (round(lat, 4), round(lon, 4))
        if cache_key in self._grid_cache:
            return self._grid_cache[cache_key]

        headers = {"User-Agent": self.user_agent}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/points/{lat},{lon}", headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        grid_data = {
                            "gridId": data["properties"]["gridId"],
                            "gridX": data["properties"]["gridX"],
                            "gridY": data["properties"]["gridY"],
                            "forecast_url": data["properties"]["forecast"],
                            "forecast_hourly_url": data["properties"]["forecastHourly"],
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
                    grid_data["forecast_url"], headers=headers, timeout=aiohttp.ClientTimeout(total=10)
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
                                    "description": props.get("description", "")[:200],
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
                            "precipitation_chance": 0,  # OWM doesn't provide this in basic API
                        }
        except Exception as e:
            logger.warning(f"OpenWeatherMap fallback failed: {e}")

        return None

    def _extract_precipitation_chance(self, text: str) -> int:
        """Extract precipitation percentage from forecast text."""
        import re

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

    def _assess_weather_safety(self, weather_data: Dict[str, Any], alerts: List[Dict[str, Any]]) -> tuple[str, float, str]:
        """Assess safety of weather conditions."""
        risk_level = "low"
        confidence = 0.85

        # Check alerts first
        if alerts:
            for alert in alerts:
                if alert.get("severity") in ["Extreme", "Severe"]:
                    risk_level = "high"
                    confidence = 0.95
                    break
                elif alert.get("severity") == "Moderate":
                    risk_level = "medium"
                    confidence = 0.90

        # Check weather conditions
        if weather_data:
            # Extract wind speed number
            wind_str = weather_data.get("wind_speed", "0")
            try:
                wind_mph = int(wind_str.split()[0]) if wind_str else 0
            except:
                wind_mph = 0

            # High winds
            if wind_mph > 40:
                risk_level = "high"
            elif wind_mph > 25 and risk_level == "low":
                risk_level = "medium"

            # Severe weather keywords
            forecast = weather_data.get("detailed_forecast", "").lower()
            severe_keywords = ["tornado", "hurricane", "blizzard", "ice storm", "severe thunderstorm"]
            if any(keyword in forecast for keyword in severe_keywords):
                risk_level = "high"
                confidence = 0.95

        return risk_level, confidence, "Weather assessment based on current conditions and alerts"

    async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse:
        """
        Get weather guidance for outdoor activity decisions.

        CRITICAL: Rejects any medical/health related requests.
        """
        # Validate this is a weather request
        if request.capability and "weather" not in request.capability.lower():
            return GuidanceResponse(
                reasoning="WeatherWisdomAdapter only handles weather requests",
                wa_id="weather_wisdom",
                signature="weather_sig",
            )

        # Extract location from inputs
        inputs = request.inputs or {}
        lat_str = inputs.get("latitude")
        lon_str = inputs.get("longitude")
        location = inputs.get("location")

        # If we have a location name but no coordinates, we'd need geocoding
        # For now, require coordinates or use a default
        lat: float
        lon: float

        if not lat_str or not lon_str:
            if location:
                # In production, we'd geocode this location
                # For demo, use a default location (San Francisco)
                lat, lon = 37.7749, -122.4194
                logger.info(f"Using default coordinates for demo: {lat}, {lon}")
            else:
                return GuidanceResponse(
                    custom_guidance="Please provide location coordinates",
                    reasoning="Missing location information",
                    wa_id="weather_wisdom",
                    signature="weather_sig",
                )
        else:
            try:
                lat = float(lat_str)
                lon = float(lon_str)
            except (ValueError, TypeError) as e:
                return GuidanceResponse(
                    custom_guidance=f"Invalid coordinates: {e}",
                    reasoning="Coordinate conversion error",
                    wa_id="weather_wisdom",
                    signature="weather_sig",
                )

        try:
            # Try NOAA first (US only)
            weather_data = None
            alerts = []
            source = "NOAA"

            grid_data = await self._get_grid_point(lat, lon)
            if grid_data:
                weather_data = await self._get_noaa_forecast(grid_data)
                alerts = await self._get_noaa_alerts(lat, lon)

            # Fallback to OpenWeatherMap if NOAA fails
            if not weather_data:
                weather_data = await self._get_owm_weather(lat, lon)
                source = "OpenWeatherMap"

            if not weather_data:
                return GuidanceResponse(
                    custom_guidance="Weather data unavailable",
                    reasoning="Could not retrieve weather information",
                    wa_id="weather_wisdom",
                    signature="weather_sig",
                )

            # Assess weather safety
            risk_level, confidence, assessment = self._assess_weather_safety(weather_data, alerts)

            # Make recommendation based on context
            selected_option = None
            if request.options:
                # Analyze options for weather-related decisions
                for option in request.options:
                    option_lower = option.lower()
                    if any(word in option_lower for word in ["postpone", "cancel", "delay", "indoor"]):
                        if risk_level in ["high", "medium"]:
                            selected_option = option
                            break
                    elif any(word in option_lower for word in ["proceed", "continue", "outdoor"]):
                        if risk_level == "low":
                            selected_option = option
                            break

                if not selected_option:
                    selected_option = request.options[0]

            # Build explanation
            explanation = (
                f"Current: {weather_data['temperature']}°{weather_data['temperature_unit']}, "
                f"{weather_data['short_forecast']}. "
                f"Wind: {weather_data['wind_speed']} {weather_data['wind_direction']}. "
            )

            if alerts:
                explanation += f"ALERTS: {alerts[0]['event']}. "

            explanation += f"Risk level: {risk_level}."

            return GuidanceResponse(
                selected_option=selected_option,
                custom_guidance=explanation,
                reasoning=f"{assessment} (Source: {source})",
                wa_id="weather_wisdom",
                signature="weather_sig",
                advice=[
                    WisdomAdvice(
                        capability="domain:weather",
                        provider_type="weather",
                        provider_name="WeatherWisdomAdapter",
                        confidence=confidence,
                        risk=risk_level,
                        explanation=explanation,
                        data={
                            "temperature": f"{weather_data['temperature']}°{weather_data['temperature_unit']}",
                            "wind": weather_data["wind_speed"],
                            "conditions": weather_data["short_forecast"],
                            "precipitation_chance": str(weather_data.get("precipitation_chance", 0)),
                            "alerts": str(len(alerts)),
                            "source": source,
                        },
                        disclaimer=(
                            "Weather conditions can change rapidly. "
                            "This is informational only. "
                            "Check official weather services for critical decisions."
                        ),
                        requires_professional=False,
                    )
                ],
            )

        except Exception as e:
            logger.error(f"WeatherWisdomAdapter error: {e}", exc_info=True)
            return GuidanceResponse(
                custom_guidance="Weather service error",
                reasoning=f"Error: {str(e)}",
                wa_id="weather_wisdom",
                signature="weather_sig",
            )

    async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]:
        """Legacy compatibility method."""
        request = GuidanceRequest(context=context.question, options={}, urgency="normal")

        response = await self.get_guidance(request)
        return response.custom_guidance or response.reasoning

    async def send_deferral(self, request: DeferralRequest) -> str:
        """Weather services don't handle deferrals."""
        # Protocol expects str return type
        return "weather_wisdom_not_supported"


# Example usage:
# adapter = WeatherWisdomAdapter()
# request = GuidanceRequest(
#     context="Should we have the outdoor event?",
#     options=["Proceed as planned", "Move indoors", "Postpone"],
#     capability="domain:weather",
#     inputs={"latitude": "37.7749", "longitude": "-122.4194"}
# )
# response = await adapter.get_guidance(request)
