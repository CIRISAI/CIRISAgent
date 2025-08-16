"""
Tests for safe domain capabilities in WiseBus.

These tests ensure that non-medical capabilities work correctly
and demonstrate proper usage of the wisdom extension system.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.buses.wise_bus import WiseBus
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority_core import GuidanceRequest, GuidanceResponse, WisdomAdvice


class TestSafeDomainCapabilities:
    """Test that safe domain capabilities work correctly."""

    @pytest.fixture
    def wise_bus(self):
        """Create a WiseBus instance for testing."""
        registry_mock = MagicMock()
        registry_mock.get_services_by_type.return_value = []
        time_service_mock = MagicMock()
        time_service_mock.now.return_value = datetime.now()
        return WiseBus(registry_mock, time_service_mock)

    @pytest.mark.asyncio
    async def test_navigation_capability(self, wise_bus):
        """Test navigation domain capability."""
        # Create a mock navigation service
        nav_service = AsyncMock()
        nav_service.get_capabilities = MagicMock()
        nav_service.get_capabilities.return_value = MagicMock(capabilities=["domain:navigation", "modality:geo:route"])
        nav_service.get_guidance = AsyncMock(
            return_value=GuidanceResponse(
                selected_option="Route via Highway",
                reasoning="Fastest route with current traffic",
                wa_id="geo_wisdom",
                signature="geo_sig",
                advice=[
                    WisdomAdvice(
                        capability="domain:navigation",
                        provider_type="geo",
                        provider_name="GeoWisdomAdapter",
                        confidence=0.85,
                        explanation="Highway route is 15 minutes faster",
                        data={"distance": "25km", "duration": "30min", "via": "Highway 101"},
                        disclaimer="For informational purposes only. Follow all traffic laws.",
                        requires_professional=False,
                    )
                ],
            )
        )

        # Mock both get_services and get_services_by_type
        wise_bus.service_registry.get_services = AsyncMock(return_value=[nav_service])
        wise_bus.service_registry.get_services_by_type.return_value = [nav_service]

        # Create navigation request
        request = GuidanceRequest(
            context="Navigate from San Francisco to San Jose",
            options=["Route via Highway", "Route via Local Roads"],
            capability="domain:navigation",
            provider_type="geo",
            inputs={"start": "San Francisco", "end": "San Jose"},
        )

        # Execute request
        response = await wise_bus.request_guidance(request)

        # Verify response
        assert response is not None
        assert response.selected_option == "Route via Highway"
        assert response.reasoning == "Fastest route with current traffic"
        assert response.advice is not None
        assert len(response.advice) == 1
        assert response.advice[0].capability == "domain:navigation"
        assert response.advice[0].confidence == 0.85
        assert response.advice[0].disclaimer == "For informational purposes only. Follow all traffic laws."
        assert response.advice[0].requires_professional is False

    @pytest.mark.asyncio
    async def test_weather_capability(self, wise_bus):
        """Test weather domain capability."""
        # Create a mock weather service
        weather_service = AsyncMock()
        weather_service.get_capabilities = MagicMock()
        weather_service.get_capabilities.return_value = MagicMock(
            capabilities=["domain:weather", "modality:sensor:atmospheric"]
        )
        weather_service.get_guidance = AsyncMock(
            return_value=GuidanceResponse(
                selected_option="Postpone outdoor activity",
                reasoning="Severe weather warning in effect",
                wa_id="weather_wisdom",
                signature="weather_sig",
                advice=[
                    WisdomAdvice(
                        capability="domain:weather",
                        provider_type="weather",
                        provider_name="WeatherWisdomAdapter",
                        confidence=0.92,
                        risk="high",
                        explanation="Thunderstorm with high winds expected",
                        data={"temp": "18C", "wind": "45km/h", "precipitation": "heavy"},
                        disclaimer="Weather conditions can change rapidly. Check official sources.",
                        requires_professional=False,
                    )
                ],
            )
        )

        # Mock both get_services and get_services_by_type
        wise_bus.service_registry.get_services = AsyncMock(return_value=[weather_service])
        wise_bus.service_registry.get_services_by_type.return_value = [weather_service]

        # Create weather request
        request = GuidanceRequest(
            context="Should we proceed with outdoor event?",
            options=["Proceed as planned", "Postpone outdoor activity"],
            capability="domain:weather",
            urgency="high",
        )

        # Execute request
        response = await wise_bus.request_guidance(request)

        # Verify response
        assert response is not None
        assert response.selected_option == "Postpone outdoor activity"
        assert response.advice[0].risk == "high"
        assert response.advice[0].confidence == 0.92

    @pytest.mark.asyncio
    async def test_audio_transcription_capability(self, wise_bus):
        """Test audio transcription capability (non-medical)."""
        # Create a mock audio service
        audio_service = AsyncMock()
        audio_service.get_capabilities = MagicMock()
        audio_service.get_capabilities.return_value = MagicMock(capabilities=["modality:audio:transcription"])
        audio_service.get_guidance = AsyncMock(
            return_value=GuidanceResponse(
                custom_guidance="Meeting transcript: Discussed Q4 targets...",
                reasoning="Audio successfully transcribed",
                wa_id="audio_wisdom",
                signature="audio_sig",
                advice=[
                    WisdomAdvice(
                        capability="modality:audio:transcription",
                        provider_type="audio",
                        provider_name="AudioTranscriptionAdapter",
                        confidence=0.88,
                        explanation="Clear audio with minimal background noise",
                        data={"duration": "5:30", "language": "en-US", "quality": "high"},
                        disclaimer="Automated transcription may contain errors.",
                        requires_professional=False,
                    )
                ],
            )
        )

        # Mock both get_services and get_services_by_type
        wise_bus.service_registry.get_services = AsyncMock(return_value=[audio_service])
        wise_bus.service_registry.get_services_by_type.return_value = [audio_service]

        # Create audio request
        request = GuidanceRequest(
            context="Transcribe meeting recording",
            options=[],
            capability="modality:audio:transcription",
            inputs={"audio_url": "s3://bucket/meeting.wav"},
        )

        # Execute request
        response = await wise_bus.request_guidance(request)

        # Verify response
        assert response is not None
        assert "Meeting transcript" in response.custom_guidance
        assert response.advice[0].capability == "modality:audio:transcription"

    @pytest.mark.asyncio
    async def test_sensor_data_capability(self, wise_bus):
        """Test IoT sensor data interpretation (non-medical)."""
        # Create a mock sensor service
        sensor_service = AsyncMock()
        sensor_service.get_capabilities = MagicMock()
        sensor_service.get_capabilities.return_value = MagicMock(capabilities=["modality:sensor:environmental"])
        sensor_service.get_guidance = AsyncMock(
            return_value=GuidanceResponse(
                selected_option="Activate ventilation",
                reasoning="CO2 levels above recommended threshold",
                wa_id="sensor_wisdom",
                signature="sensor_sig",
                advice=[
                    WisdomAdvice(
                        capability="modality:sensor:environmental",
                        provider_type="sensor",
                        provider_name="EnvironmentalSensorAdapter",
                        confidence=0.95,
                        explanation="CO2 at 1200ppm, above 1000ppm threshold",
                        data={"co2": "1200ppm", "temp": "23C", "humidity": "45%"},
                        disclaimer="Sensor readings for informational purposes.",
                        requires_professional=False,
                    )
                ],
            )
        )

        # Mock both get_services and get_services_by_type
        wise_bus.service_registry.get_services = AsyncMock(return_value=[sensor_service])
        wise_bus.service_registry.get_services_by_type.return_value = [sensor_service]

        # Create sensor request
        request = GuidanceRequest(
            context="Room air quality check",
            options=["Maintain current settings", "Activate ventilation"],
            capability="modality:sensor:environmental",
        )

        # Execute request
        response = await wise_bus.request_guidance(request)

        # Verify response
        assert response is not None
        assert response.selected_option == "Activate ventilation"
        assert response.advice[0].data["co2"] == "1200ppm"

    @pytest.mark.asyncio
    async def test_policy_compliance_capability(self, wise_bus):
        """Test policy compliance checking (non-medical)."""
        # Create a mock policy service
        policy_service = AsyncMock()
        policy_service.get_capabilities = MagicMock()
        policy_service.get_capabilities.return_value = MagicMock(capabilities=["policy:compliance:gdpr"])
        policy_service.get_guidance = AsyncMock(
            return_value=GuidanceResponse(
                selected_option="Require explicit consent",
                reasoning="GDPR requires explicit consent for data processing",
                wa_id="policy_wisdom",
                signature="policy_sig",
                advice=[
                    WisdomAdvice(
                        capability="policy:compliance:gdpr",
                        provider_type="policy",
                        provider_name="GDPRComplianceAdapter",
                        confidence=0.98,
                        explanation="Article 6 requires lawful basis for processing",
                        data={"regulation": "GDPR", "article": "6", "requirement": "consent"},
                        disclaimer="Not legal advice. Consult legal counsel.",
                        requires_professional=True,  # Legal matters may need professional
                    )
                ],
            )
        )

        # Mock both get_services and get_services_by_type
        wise_bus.service_registry.get_services = AsyncMock(return_value=[policy_service])
        wise_bus.service_registry.get_services_by_type.return_value = [policy_service]

        # Create policy request
        request = GuidanceRequest(
            context="User data collection for analytics",
            options=["Proceed with implied consent", "Require explicit consent"],
            capability="policy:compliance:gdpr",
        )

        # Execute request
        response = await wise_bus.request_guidance(request)

        # Verify response
        assert response is not None
        assert response.selected_option == "Require explicit consent"
        assert response.advice[0].requires_professional is True
        assert "Not legal advice" in response.advice[0].disclaimer


class TestMultiProviderScenarios:
    """Test scenarios with multiple wisdom providers."""

    @pytest.fixture
    def wise_bus(self):
        """Create a WiseBus instance for testing."""
        registry_mock = MagicMock()
        registry_mock.get_services_by_type.return_value = []
        registry_mock.get_services = AsyncMock(return_value=[])
        time_service_mock = MagicMock()
        time_service_mock.now.return_value = datetime.now()
        return WiseBus(registry_mock, time_service_mock)

    @pytest.mark.asyncio
    async def test_multiple_providers_same_capability(self, wise_bus):
        """Test multiple providers offering the same capability."""
        # Create two navigation providers
        nav_service1 = AsyncMock()
        nav_service1.get_capabilities = MagicMock()
        nav_service1.get_capabilities.return_value = MagicMock(capabilities=["domain:navigation"])
        nav_service1.get_guidance = AsyncMock(
            return_value=GuidanceResponse(
                selected_option="Route A", reasoning="Provider 1 recommendation", wa_id="nav1", signature="sig1"
            )
        )

        nav_service2 = AsyncMock()
        nav_service2.get_capabilities = MagicMock()
        nav_service2.get_capabilities.return_value = MagicMock(capabilities=["domain:navigation"])
        nav_service2.get_guidance = AsyncMock(
            return_value=GuidanceResponse(
                selected_option="Route B", reasoning="Provider 2 recommendation", wa_id="nav2", signature="sig2"
            )
        )

        # Mock both get_services and get_services_by_type
        wise_bus.service_registry.get_services = AsyncMock(return_value=[nav_service1, nav_service2])
        wise_bus.service_registry.get_services_by_type.return_value = [nav_service1, nav_service2]

        # Create request
        request = GuidanceRequest(
            context="Navigate to destination", options=["Route A", "Route B"], capability="domain:navigation"
        )

        # Execute request
        response = await wise_bus.request_guidance(request)

        # Verify response (should get first provider's response with note about multiple)
        assert response is not None
        assert "from 2 providers" in response.reasoning

    @pytest.mark.asyncio
    async def test_provider_timeout_handling(self, wise_bus):
        """Test handling of provider timeouts."""
        # Create slow and fast providers
        slow_service = AsyncMock()
        slow_service.get_capabilities = MagicMock()
        slow_service.get_capabilities.return_value = MagicMock(capabilities=["domain:navigation"])

        async def slow_response(request):
            await asyncio.sleep(10)  # Longer than timeout
            return GuidanceResponse(reasoning="Slow response", wa_id="slow", signature="slow_sig")

        slow_service.get_guidance = slow_response

        fast_service = AsyncMock()
        fast_service.get_capabilities = MagicMock()
        fast_service.get_capabilities.return_value = MagicMock(capabilities=["domain:navigation"])
        fast_service.get_guidance = AsyncMock(
            return_value=GuidanceResponse(reasoning="Fast response", wa_id="fast", signature="fast_sig")
        )

        # Mock both get_services and get_services_by_type
        wise_bus.service_registry.get_services = AsyncMock(return_value=[slow_service, fast_service])
        wise_bus.service_registry.get_services_by_type.return_value = [slow_service, fast_service]

        # Create request with short timeout
        request = GuidanceRequest(context="Navigate quickly", options=["A", "B"], capability="domain:navigation")

        # Execute request with 1 second timeout
        response = await wise_bus.request_guidance(request, timeout=1.0)

        # Should get fast provider's response
        assert response is not None
        assert response.wa_id == "fast"

    @pytest.mark.asyncio
    async def test_mixed_capability_providers(self, wise_bus):
        """Test providers with different capabilities."""
        # Create providers with different capabilities
        nav_service = AsyncMock()
        nav_service.get_capabilities = MagicMock()
        nav_service.get_capabilities.return_value = MagicMock(capabilities=["domain:navigation"])
        nav_service.get_guidance = AsyncMock(
            return_value=GuidanceResponse(reasoning="Navigation response", wa_id="nav", signature="nav_sig")
        )

        weather_service = AsyncMock()
        weather_service.get_capabilities = MagicMock()
        weather_service.get_capabilities.return_value = MagicMock(capabilities=["domain:weather"])
        weather_service.get_guidance = AsyncMock()  # Set up the mock before using

        # Mock both get_services and get_services_by_type
        wise_bus.service_registry.get_services = AsyncMock(return_value=[nav_service])
        wise_bus.service_registry.get_services_by_type.return_value = [nav_service, weather_service]

        # Request navigation - should only use nav_service
        request = GuidanceRequest(context="Navigate", options=["A", "B"], capability="domain:navigation")

        response = await wise_bus.request_guidance(request)

        # Verify only navigation service was called
        nav_service.get_guidance.assert_called_once()
        weather_service.get_guidance.assert_not_called()


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    @pytest.fixture
    def wise_bus(self):
        """Create a WiseBus instance for testing."""
        registry_mock = MagicMock()
        registry_mock.get_services_by_type.return_value = []
        registry_mock.get_services = AsyncMock(return_value=[])
        time_service_mock = MagicMock()
        time_service_mock.now.return_value = datetime.now()
        return WiseBus(registry_mock, time_service_mock)

    @pytest.mark.asyncio
    async def test_request_without_capability_fields(self, wise_bus):
        """Test that requests without new fields still work."""
        # Create a legacy service with only fetch_guidance method
        legacy_service = AsyncMock()
        legacy_service.fetch_guidance = AsyncMock(return_value="Legacy guidance response")
        # Remove get_guidance attribute to simulate legacy service
        if hasattr(legacy_service, "get_guidance"):
            delattr(legacy_service, "get_guidance")

        # Mock get_service for fallback and ensure get_services returns empty
        wise_bus.get_service = AsyncMock(return_value=legacy_service)
        wise_bus.service_registry.get_services = AsyncMock(return_value=[])

        # Create legacy request (no capability fields)
        request = GuidanceRequest(context="Legacy request", options=["Option 1", "Option 2"], urgency="normal")

        # Should work via compatibility layer
        response = await wise_bus.request_guidance(request)

        assert response is not None
        assert response.custom_guidance == "Legacy guidance response"

    @pytest.mark.asyncio
    async def test_response_without_advice_field(self, wise_bus):
        """Test that responses without advice field still work."""
        # Create service returning legacy response
        service = AsyncMock()
        service.get_guidance = AsyncMock(
            return_value=GuidanceResponse(
                selected_option="Option 1",
                reasoning="Simple reasoning",
                wa_id="legacy",
                signature="legacy_sig",
                # No advice field
            )
        )

        # Mock both get_services and get_services_by_type
        wise_bus.service_registry.get_services = AsyncMock(return_value=[service])
        wise_bus.service_registry.get_services_by_type.return_value = [service]

        request = GuidanceRequest(context="Test", options=["Option 1", "Option 2"])

        response = await wise_bus.request_guidance(request)

        assert response is not None
        assert response.selected_option == "Option 1"
        assert response.advice is None  # Old responses don't have advice


# Run with: pytest tests/logic/buses/test_wise_bus_safe_domains.py -v
