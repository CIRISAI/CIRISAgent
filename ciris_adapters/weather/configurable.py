"""
Weather ConfigurableAdapterProtocol implementation.

Provides interactive configuration workflow for Weather service:
1. API Key - Optional OpenWeatherMap API key for international coverage
2. Default Location - Optional default location for weather queries
3. Units - Select temperature units (metric, imperial, kelvin)
4. User Agent - NOAA requires a user agent
5. Confirm - Review and apply configuration

The weather adapter uses:
- NOAA National Weather Service API (free, US-only, requires user agent)
- OpenWeatherMap API (requires key, international coverage)
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)


class WeatherConfigurableAdapter:
    """Weather configurable adapter.

    Implements ConfigurableAdapterProtocol for Weather service.

    Configuration fields:
    - user_agent: User agent for NOAA API (required by NOAA)
    - owm_api_key: Optional OpenWeatherMap API key for international coverage
    - default_location: Optional default location (lat,lon or city name)
    - units: Temperature units (metric, imperial, kelvin)
    - update_interval: How often to refresh cached data (seconds)
    """

    # Available units for weather data
    UNIT_OPTIONS = {
        "imperial": {
            "label": "Imperial (°F, mph)",
            "description": "Fahrenheit for temperature, miles per hour for wind",
            "default": True,
        },
        "metric": {
            "label": "Metric (°C, m/s)",
            "description": "Celsius for temperature, meters per second for wind",
            "default": False,
        },
        "kelvin": {
            "label": "Kelvin (K, m/s)",
            "description": "Kelvin for temperature (scientific standard)",
            "default": False,
        },
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the Weather configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None

        logger.info("WeatherConfigurableAdapter initialized")

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get options for a selection step.

        Args:
            step_id: ID of the configuration step
            context: Current configuration context

        Returns:
            List of available options
        """
        logger.info(f"Getting config options for step: {step_id}")

        if step_id == "select_units":
            # Return available unit options
            return [
                {
                    "id": unit_id,
                    "label": unit["label"],
                    "description": unit["description"],
                    "metadata": {"default": unit["default"]},
                }
                for unit_id, unit in self.UNIT_OPTIONS.items()
            ]

        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate Weather configuration before applying.

        Performs:
        - Required field validation
        - User agent format validation
        - Optional: API key validation with OpenWeatherMap
        - Optional: Default location validation

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating Weather configuration")

        if not config:
            return False, "Configuration is empty"

        # Check required field: user_agent
        user_agent = config.get("user_agent")
        if not user_agent or not isinstance(user_agent, str) or len(user_agent.strip()) < 3:
            return False, "user_agent is required and must be at least 3 characters (required by NOAA)"

        # Validate units if provided
        units = config.get("units")
        if units and units not in self.UNIT_OPTIONS:
            return False, f"Invalid units: {units} (must be one of: {', '.join(self.UNIT_OPTIONS.keys())})"

        # Validate update_interval if provided
        update_interval = config.get("update_interval")
        if update_interval is not None:
            try:
                interval_int = int(update_interval)
                if interval_int < 60:
                    return False, "update_interval must be at least 60 seconds (API rate limiting)"
                if interval_int > 86400:
                    return False, "update_interval must not exceed 86400 seconds (24 hours)"
            except (ValueError, TypeError):
                return False, "update_interval must be a valid integer"

        # Validate OpenWeatherMap API key if provided
        owm_api_key = config.get("owm_api_key")
        if owm_api_key:
            # Test the API key with a simple request
            is_valid, error = await self._validate_owm_api_key(owm_api_key)
            if not is_valid:
                return False, f"OpenWeatherMap API key validation failed: {error}"

        # Validate default_location if provided
        default_location = config.get("default_location")
        if default_location:
            # Check if it's lat,lon format
            if "," in default_location:
                parts = default_location.split(",")
                if len(parts) != 2:
                    return False, "default_location must be 'lat,lon' or a city name"
                try:
                    lat = float(parts[0].strip())
                    lon = float(parts[1].strip())
                    if not (-90 <= lat <= 90):
                        return False, "Latitude must be between -90 and 90"
                    if not (-180 <= lon <= 180):
                        return False, "Longitude must be between -180 and 180"
                except ValueError:
                    return False, "Invalid lat,lon format - coordinates must be valid numbers"

        logger.info("Weather configuration validated successfully")
        return True, None

    async def _validate_owm_api_key(self, api_key: str) -> Tuple[bool, Optional[str]]:
        """Validate OpenWeatherMap API key by making a test request.

        Args:
            api_key: API key to validate

        Returns:
            (is_valid, error_message) tuple
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Test with a simple request for New York City
                async with session.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"lat": 40.7128, "lon": -74.0060, "appid": api_key},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 401:
                        return False, "API key is invalid"
                    elif response.status == 429:
                        return False, "API key has exceeded rate limit"
                    elif response.status != 200:
                        return False, f"API validation failed with HTTP {response.status}"

                    # Key is valid
                    return True, None

        except aiohttp.ClientError as e:
            return False, f"Network error during validation: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration.

        Stores configuration and sets up environment for the service.

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying Weather configuration")

        self._applied_config = config.copy()

        # Set environment variables for the Weather service
        if config.get("user_agent"):
            os.environ["CIRIS_NOAA_USER_AGENT"] = config["user_agent"]

        if config.get("owm_api_key"):
            os.environ["CIRIS_OPENWEATHERMAP_API_KEY"] = config["owm_api_key"]

        if config.get("units"):
            os.environ["CIRIS_WEATHER_UNITS"] = config["units"]

        if config.get("default_location"):
            os.environ["CIRIS_WEATHER_DEFAULT_LOCATION"] = config["default_location"]

        if config.get("update_interval"):
            os.environ["CIRIS_WEATHER_UPDATE_INTERVAL"] = str(config["update_interval"])

        # Log sanitized config
        safe_config = {k: ("***" if "api_key" in k.lower() or "token" in k.lower() else v) for k, v in config.items()}
        logger.info(f"Weather configuration applied: {safe_config}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config
