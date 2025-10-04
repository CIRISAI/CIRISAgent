"""
Sensor wisdom adapter for Home Assistant integration.

This adapter provides IoT sensor data interpretation capabilities
WITHOUT any medical/health functionality.

LIABILITY: This is informational only, not professional advice.
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


class SensorWisdomAdapter(WiseAuthorityService):
    """
    IoT sensor wisdom provider using Home Assistant API.

    SAFE DOMAIN: Environmental and home automation sensors only.
    NO medical/health/patient monitoring capabilities.

    Requires Home Assistant instance with Long-Lived Access Token.
    """

    # CRITICAL: Blocked sensor types that could be medical
    PROHIBITED_SENSOR_TYPES = {
        "heart_rate",
        "blood_pressure",
        "blood_glucose",
        "blood_oxygen",
        "body_temperature",
        "weight",
        "bmi",
        "spo2",
        "ecg",
        "pulse",
        "medical",
        "health",
        "patient",
        "vital",
        "symptom",
    }

    def __init__(self) -> None:
        """Initialize the sensor wisdom adapter."""
        # Home Assistant configuration from environment
        self.ha_url = os.getenv("CIRIS_HOMEASSISTANT_URL", "http://homeassistant.local:8123")
        self.ha_token = os.getenv("CIRIS_HOMEASSISTANT_TOKEN")

        if not self.ha_token:
            logger.warning("CIRIS_HOMEASSISTANT_TOKEN not set - Home Assistant integration disabled")

        # Remove trailing slash from URL
        self.ha_url = self.ha_url.rstrip("/")

        # Cache for entity states
        self._entity_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 30  # seconds

        logger.info(f"SensorWisdomAdapter initialized for {self.ha_url}")

    def get_capabilities(self) -> ServiceCapabilities:
        """Return adapter capabilities."""
        return ServiceCapabilities(
            service_name="sensor_wisdom",
            actions=["get_guidance", "fetch_guidance"],
            version="1.0.0",
            dependencies=[],
            metadata={
                "capabilities": [
                    "modality:sensor:environmental",
                    "modality:sensor:motion",
                    "modality:sensor:temperature",
                    "modality:sensor:humidity",
                    "modality:sensor:air_quality",
                    "modality:sensor:energy",
                    "domain:home_automation",
                ]
            },
        )

    def _is_medical_sensor(self, sensor_type: str, entity_id: str, attributes: Dict[str, Any]) -> bool:
        """Check if a sensor might be medical/health related."""
        # Check entity ID
        entity_lower = entity_id.lower()
        for prohibited in self.PROHIBITED_SENSOR_TYPES:
            if prohibited in entity_lower:
                return True

        # Check device class
        device_class = attributes.get("device_class", "").lower()
        for prohibited in self.PROHIBITED_SENSOR_TYPES:
            if prohibited in device_class:
                return True

        # Check friendly name
        friendly_name = attributes.get("friendly_name", "").lower()
        for prohibited in self.PROHIBITED_SENSOR_TYPES:
            if prohibited in friendly_name:
                return True

        return False

    async def _get_ha_entities(self) -> Optional[List[Dict[str, Any]]]:
        """Get all entities from Home Assistant."""
        if not self.ha_token:
            return None

        # Check cache
        if self._entity_cache and self._cache_timestamp:
            if (datetime.now() - self._cache_timestamp).seconds < self._cache_ttl:
                return list(self._entity_cache.values())

        headers = {"Authorization": f"Bearer {self.ha_token}", "Content-Type": "application/json"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ha_url}/api/states", headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        entities = await response.json()

                        # Filter out medical sensors
                        safe_entities = []
                        for entity in entities:
                            entity_id = entity.get("entity_id", "")
                            attributes = entity.get("attributes", {})

                            # Skip if medical
                            if self._is_medical_sensor(entity_id.split(".")[0], entity_id, attributes):
                                logger.warning(f"Skipping potential medical sensor: {entity_id}")
                                continue

                            safe_entities.append(entity)
                            self._entity_cache[entity_id] = entity

                        self._cache_timestamp = datetime.now()
                        return safe_entities
                    else:
                        logger.warning(f"Home Assistant API returned status {response.status}")
        except Exception as e:
            logger.warning(f"Failed to get Home Assistant entities: {e}")

        return None

    async def _get_sensor_data(self, sensor_type: Optional[str] = None) -> Dict[str, Any]:
        """Get sensor data by type."""
        entities = await self._get_ha_entities()
        if not entities:
            return {}

        sensor_data: Dict[str, Any] = {
            "temperature": [],
            "humidity": [],
            "motion": [],
            "air_quality": [],
            "energy": [],
            "light": [],
            "other": [],
        }

        for entity in entities:
            entity_id = entity.get("entity_id", "")
            state = entity.get("state", "unknown")
            attributes = entity.get("attributes", {})

            # Skip unavailable entities
            if state in ["unknown", "unavailable"]:
                continue

            # Categorize by domain and device class
            domain = entity_id.split(".")[0]
            device_class = attributes.get("device_class", "")

            sensor_info = {
                "entity_id": entity_id,
                "state": state,
                "unit": attributes.get("unit_of_measurement", ""),
                "friendly_name": attributes.get("friendly_name", entity_id),
            }

            # Categorize sensors
            if domain == "sensor":
                if device_class == "temperature" or "temp" in entity_id.lower():
                    sensor_data["temperature"].append(sensor_info)
                elif device_class == "humidity" or "humidity" in entity_id.lower():
                    sensor_data["humidity"].append(sensor_info)
                elif device_class in ["co2", "pm25", "pm10", "aqi"] or "air" in entity_id.lower():
                    sensor_data["air_quality"].append(sensor_info)
                elif device_class in ["power", "energy", "current", "voltage"]:
                    sensor_data["energy"].append(sensor_info)
                else:
                    sensor_data["other"].append(sensor_info)
            elif domain == "binary_sensor":
                if device_class == "motion" or "motion" in entity_id.lower():
                    sensor_data["motion"].append(sensor_info)
            elif domain == "light":
                sensor_data["light"].append(sensor_info)

        return sensor_data

    def _analyze_environment(self, sensor_data: Dict[str, Any]) -> tuple[str, Dict[str, str]]:
        """Analyze environmental conditions from sensors."""
        analysis = []
        metrics = {}

        # Temperature analysis
        if sensor_data["temperature"]:
            temps = []
            for sensor in sensor_data["temperature"]:
                try:
                    temp_str = sensor["state"]
                    # Handle both Celsius and Fahrenheit
                    temp_val = float(temp_str.replace("°C", "").replace("°F", "").strip())
                    unit = sensor.get("unit", "°C")

                    # Convert to Fahrenheit for consistency
                    if "C" in unit:
                        temp_val = temp_val * 9 / 5 + 32
                        unit = "°F"

                    temps.append(temp_val)
                    metrics[sensor["friendly_name"]] = f"{temp_val:.1f}{unit}"
                except:
                    continue

            if temps:
                avg_temp = sum(temps) / len(temps)
                if avg_temp < 60:
                    analysis.append("Temperature is cool")
                elif avg_temp > 78:
                    analysis.append("Temperature is warm")
                else:
                    analysis.append("Temperature is comfortable")
                metrics["avg_temperature"] = f"{avg_temp:.1f}°F"

        # Humidity analysis
        if sensor_data["humidity"]:
            humidities = []
            for sensor in sensor_data["humidity"]:
                try:
                    humidity = float(sensor["state"].replace("%", "").strip())
                    humidities.append(humidity)
                    metrics[sensor["friendly_name"]] = f"{humidity}%"
                except:
                    continue

            if humidities:
                avg_humidity = sum(humidities) / len(humidities)
                if avg_humidity < 30:
                    analysis.append("Air is dry")
                elif avg_humidity > 60:
                    analysis.append("Humidity is high")
                else:
                    analysis.append("Humidity is normal")
                metrics["avg_humidity"] = f"{avg_humidity:.1f}%"

        # Air quality analysis
        if sensor_data["air_quality"]:
            for sensor in sensor_data["air_quality"]:
                name = sensor["friendly_name"]
                value = sensor["state"]
                unit = sensor.get("unit", "")

                # CO2 levels
                if "co2" in name.lower():
                    try:
                        co2_ppm = float(value)
                        metrics[name] = f"{co2_ppm} ppm"
                        if co2_ppm > 1000:
                            analysis.append("CO2 levels elevated - consider ventilation")
                    except:
                        pass

        # Motion detection
        motion_detected = False
        for sensor in sensor_data["motion"]:
            if sensor["state"].lower() in ["on", "true", "detected"]:
                motion_detected = True
                metrics[sensor["friendly_name"]] = "detected"

        if motion_detected:
            analysis.append("Motion detected in area")

        # Energy usage
        if sensor_data["energy"]:
            for sensor in sensor_data["energy"]:
                metrics[sensor["friendly_name"]] = f"{sensor['state']} {sensor.get('unit', '')}"

        return ". ".join(analysis) if analysis else "Normal conditions", metrics

    async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse:
        """
        Get sensor-based guidance for home automation decisions.

        CRITICAL: Rejects any medical/health sensor requests.
        """
        # Validate this is a sensor/home automation request
        if request.capability:
            cap_lower = request.capability.lower()
            # Check for medical terms
            for prohibited in self.PROHIBITED_SENSOR_TYPES:
                if prohibited in cap_lower:
                    return GuidanceResponse(
                        reasoning="PROHIBITED: Medical/health sensors are not supported",
                        wa_id="sensor_wisdom",
                        signature="sensor_sig",
                    )

        if not self.ha_token:
            return GuidanceResponse(
                custom_guidance="Home Assistant not configured",
                reasoning="CIRIS_HOMEASSISTANT_TOKEN environment variable not set",
                wa_id="sensor_wisdom",
                signature="sensor_sig",
            )

        try:
            # Get sensor data
            sensor_data = await self._get_sensor_data()

            if not any(sensor_data.values()):
                return GuidanceResponse(
                    custom_guidance="No sensor data available",
                    reasoning="Could not retrieve sensor information from Home Assistant",
                    wa_id="sensor_wisdom",
                    signature="sensor_sig",
                )

            # Analyze environment
            analysis, metrics = self._analyze_environment(sensor_data)

            # Make recommendation based on context and sensor data
            selected_option = None
            confidence = 0.75
            risk = "low"

            if request.options:
                # Analyze options based on sensor data
                for option in request.options:
                    option_lower = option.lower()

                    # Ventilation decisions
                    if "ventilat" in option_lower or "air" in option_lower:
                        if "CO2 levels elevated" in analysis:
                            selected_option = option
                            confidence = 0.85
                            risk = "medium"
                            break

                    # Temperature decisions
                    elif "heat" in option_lower or "cool" in option_lower:
                        if "warm" in analysis and "cool" in option_lower:
                            selected_option = option
                            confidence = 0.80
                        elif "cool" in analysis and "heat" in option_lower:
                            selected_option = option
                            confidence = 0.80

                    # Humidity decisions
                    elif "dehumidif" in option_lower:
                        if "high" in analysis:
                            selected_option = option
                            confidence = 0.80

                    # Motion-based decisions
                    elif "light" in option_lower or "security" in option_lower:
                        if "Motion detected" in analysis:
                            selected_option = option
                            confidence = 0.90

                if not selected_option:
                    selected_option = request.options[0]

            # Build explanation
            sensor_count = sum(len(v) for v in sensor_data.values())
            explanation = f"Analysis from {sensor_count} sensors: {analysis}"

            # Add key metrics
            if "avg_temperature" in metrics:
                explanation += f" Avg temp: {metrics['avg_temperature']}."
            if "avg_humidity" in metrics:
                explanation += f" Avg humidity: {metrics['avg_humidity']}."

            return GuidanceResponse(
                selected_option=selected_option,
                custom_guidance=explanation,
                reasoning=f"Sensor analysis from Home Assistant ({len(metrics)} metrics)",
                wa_id="sensor_wisdom",
                signature="sensor_sig",
                advice=[
                    WisdomAdvice(
                        capability="modality:sensor:environmental",
                        provider_type="sensor",
                        provider_name="SensorWisdomAdapter",
                        confidence=confidence,
                        risk=risk,
                        explanation=explanation,
                        data=metrics,
                        disclaimer=(
                            "Sensor readings are for informational purposes only. "
                            "Not for critical safety decisions. "
                            "Verify important readings manually."
                        ),
                        requires_professional=False,
                    )
                ],
            )

        except Exception as e:
            logger.error(f"SensorWisdomAdapter error: {e}", exc_info=True)
            return GuidanceResponse(
                custom_guidance="Sensor service error",
                reasoning=f"Error: {str(e)}",
                wa_id="sensor_wisdom",
                signature="sensor_sig",
            )

    async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]:
        """Legacy compatibility method."""
        request = GuidanceRequest(context=context.question, options={}, urgency="normal")

        response = await self.get_guidance(request)
        return response.custom_guidance or response.reasoning

    async def send_deferral(self, request: DeferralRequest) -> str:
        """Sensor services don't handle deferrals."""
        # Protocol expects str return type
        return "sensor_wisdom_not_supported"

    async def trigger_automation(self, entity_id: str, action: str) -> bool:
        """
        Trigger a Home Assistant automation or script.

        NOTE: This requires careful permission management in Home Assistant.
        """
        if not self.ha_token:
            return False

        headers = {"Authorization": f"Bearer {self.ha_token}", "Content-Type": "application/json"}

        # Map actions to HA services
        service_map = {
            "turn_on": "homeassistant/turn_on",
            "turn_off": "homeassistant/turn_off",
            "toggle": "homeassistant/toggle",
            "trigger": "automation/trigger",
        }

        service = service_map.get(action)
        if not service:
            logger.warning(f"Unknown action: {action}")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ha_url}/api/services/{service}",
                    headers=headers,
                    json={"entity_id": entity_id},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Failed to trigger automation: {e}")
            return False


# Example usage:
# adapter = SensorWisdomAdapter()
# request = GuidanceRequest(
#     context="Room air quality check",
#     options=["Maintain current settings", "Activate ventilation", "Open windows"],
#     capability="modality:sensor:environmental"
# )
# response = await adapter.get_guidance(request)
