"""
CRITICAL: Tests for medical capability blocking in WiseBus.

These tests ensure that medical/health capabilities are completely blocked
at the bus level to prevent any medical functionality in the main repository.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.buses.wise_bus import PROHIBITED_CAPABILITIES, WiseBus
from ciris_engine.schemas.services.authority_core import GuidanceRequest, GuidanceResponse


class TestMedicalCapabilityBlocking:
    """Test that medical capabilities are absolutely blocked."""

    @pytest.fixture
    def wise_bus(self):
        """Create a WiseBus instance for testing."""
        registry_mock = MagicMock()
        registry_mock.get_services_by_type.return_value = []
        time_service_mock = MagicMock()
        return WiseBus(registry_mock, time_service_mock)

    def test_prohibited_capabilities_comprehensive(self):
        """Ensure PROHIBITED_CAPABILITIES includes all medical terms."""
        # Core medical terms that must be blocked
        required_blocks = [
            "medical",
            "health",
            "clinical",
            "patient",
            "diagnosis",
            "treatment",
            "prescription",
            "symptom",
            "disease",
            "medication",
            "therapy",
            "triage",
            "condition",
            "disorder",
        ]

        for term in required_blocks:
            assert term in PROHIBITED_CAPABILITIES, f"Missing critical block: {term}"

        # Domain-prefixed versions
        assert "domain:medical" in PROHIBITED_CAPABILITIES
        assert "domain:health" in PROHIBITED_CAPABILITIES
        assert "domain:clinical" in PROHIBITED_CAPABILITIES
        assert "modality:medical" in PROHIBITED_CAPABILITIES
        assert "provider:medical" in PROHIBITED_CAPABILITIES

    @pytest.mark.parametrize(
        "capability",
        [
            "domain:medical",
            "domain:health",
            "domain:triage",
            "domain:diagnosis",
            "domain:treatment",
            "domain:prescription",
            "domain:patient",
            "domain:clinical",
            "domain:symptom",
            "domain:disease",
            "domain:medication",
            "domain:therapy",
            "domain:condition",
            "domain:disorder",
            "modality:medical",
            "modality:medical:imaging",
            "provider:medical",
            "provider:clinical",
            # Mixed case variations
            "Domain:Medical",
            "DOMAIN:HEALTH",
            "DoMaIn:ClInIcAl",
            # Embedded terms
            "domain:medical_advice",
            "modality:health_monitoring",
            "provider:patient_care",
            "capability:diagnosis_system",
            "service:treatment_planning",
            "domain:symptom_checker",
            "modality:medication_reminder",
            "provider:therapy_guide",
        ],
    )
    def test_validate_capability_blocks_medical(self, wise_bus, capability):
        """Test that all medical-related capabilities are blocked."""
        with pytest.raises(ValueError) as exc_info:
            wise_bus._validate_capability(capability)

        error_msg = str(exc_info.value)
        assert "PROHIBITED" in error_msg
        assert "Medical/health capabilities blocked" in error_msg
        assert "CIRISMedical" in error_msg

    @pytest.mark.parametrize(
        "capability",
        [
            "domain:navigation",
            "domain:weather",
            "domain:translation",
            "domain:education",
            "domain:security",
            "modality:audio",
            "modality:geo",
            "modality:sensor",
            "modality:vision",
            "policy:compliance",
            "provider:geo",
            "provider:weather",
            "capability:routing",
            "service:transcription",
        ],
    )
    def test_validate_capability_allows_safe_domains(self, wise_bus, capability):
        """Test that safe domains are allowed."""
        # Should not raise
        wise_bus._validate_capability(capability)

    def test_validate_capability_none_allowed(self, wise_bus):
        """Test that None capability is allowed (backward compatibility)."""
        # Should not raise
        wise_bus._validate_capability(None)
        wise_bus._validate_capability("")

    @pytest.mark.asyncio
    async def test_request_guidance_blocks_medical_capability(self, wise_bus):
        """Test that request_guidance blocks medical capabilities."""
        medical_capabilities = [
            "domain:medical",
            "domain:health:triage",
            "modality:medical:imaging",
            "provider:clinical",
        ]

        for cap in medical_capabilities:
            request = GuidanceRequest(context="test context", options=["A", "B"], capability=cap)

            with pytest.raises(ValueError) as exc_info:
                await wise_bus.request_guidance(request)

            error_msg = str(exc_info.value)
            assert "PROHIBITED" in error_msg
            assert cap in error_msg

    @pytest.mark.asyncio
    async def test_request_guidance_allows_safe_capability(self, wise_bus):
        """Test that request_guidance allows safe capabilities."""
        # Mock a service
        mock_service = AsyncMock()
        mock_service.get_guidance = AsyncMock(
            return_value=GuidanceResponse(reasoning="Test response", wa_id="test", signature="test_sig")
        )

        wise_bus.service_registry.get_services_by_type.return_value = [mock_service]

        # Also need to mock the async get_service for fallback
        async def mock_get_service(*args, **kwargs):
            return mock_service

        wise_bus.service_registry.get_service = mock_get_service

        safe_capabilities = [
            "domain:navigation",
            "domain:weather",
            "modality:audio:transcription",
        ]

        for cap in safe_capabilities:
            request = GuidanceRequest(context="test context", options=["A", "B"], capability=cap)

            # Should not raise
            response = await wise_bus.request_guidance(request)
            assert response is not None
            assert response.reasoning is not None

    @pytest.mark.asyncio
    async def test_request_guidance_without_capability(self, wise_bus):
        """Test backward compatibility - request without capability field."""
        # Mock a service
        mock_service = AsyncMock()
        mock_service.fetch_guidance = AsyncMock(return_value="Test guidance")

        # Need to mock the async get_service method properly
        async def mock_get_service(*args, **kwargs):
            return mock_service

        wise_bus.get_service = mock_get_service

        request = GuidanceRequest(context="test context", options=["A", "B"], urgency="normal")

        # Should not raise and should work normally
        response = await wise_bus.request_guidance(request)
        assert response is not None

    def test_error_message_clarity(self, wise_bus):
        """Test that error messages are clear and actionable."""
        with pytest.raises(ValueError) as exc_info:
            wise_bus._validate_capability("domain:medical")

        error_msg = str(exc_info.value)
        # Check for key information
        assert "PROHIBITED" in error_msg
        assert "Medical/health capabilities blocked" in error_msg
        assert "domain:medical" in error_msg
        assert "medical" in error_msg
        assert "CIRISMedical" in error_msg
        assert "separate licensed system" in error_msg

    def test_partial_match_blocking(self, wise_bus):
        """Test that partial matches of medical terms are blocked."""
        blocked_variations = [
            "medical_anything",
            "health_monitoring",
            "patient_data",
            "clinical_trial",
            "diagnosis_tool",
            "treatment_plan",
            "prescription_manager",
            "symptom_tracker",
            "disease_detection",
            "medication_schedule",
            "therapy_session",
        ]

        for term in blocked_variations:
            capability = f"domain:{term}"
            with pytest.raises(ValueError) as exc_info:
                wise_bus._validate_capability(capability)
            assert "PROHIBITED" in str(exc_info.value)

    def test_case_insensitive_blocking(self, wise_bus):
        """Test that blocking is case-insensitive."""
        case_variations = [
            "DOMAIN:MEDICAL",
            "Domain:Medical",
            "domain:MEDICAL",
            "DoMaIn:MeDiCaL",
            "DOMAIN:health",
            "domain:HEALTH",
            "Domain:Health",
        ]

        for cap in case_variations:
            with pytest.raises(ValueError):
                wise_bus._validate_capability(cap)


class TestMedicalBlockingIntegration:
    """Integration tests for medical blocking in real scenarios."""

    @pytest.mark.asyncio
    async def test_full_request_flow_with_medical_block(self):
        """Test complete request flow with medical capability."""
        registry_mock = MagicMock()
        registry_mock.get_services_by_type.return_value = []
        time_service_mock = MagicMock()
        wise_bus = WiseBus(registry_mock, time_service_mock)

        # Create a medical request
        request = GuidanceRequest(
            context="Patient symptoms include fever and cough",
            options=["Prescribe antibiotics", "Recommend rest"],
            capability="domain:medical:diagnosis",
            urgency="high",
        )

        # Should be blocked immediately
        with pytest.raises(ValueError) as exc_info:
            await wise_bus.request_guidance(request)

        # Verify error message
        error = str(exc_info.value)
        assert "PROHIBITED" in error
        assert "domain:medical:diagnosis" in error
        assert "medical" in error
        assert "CIRISMedical" in error

    @pytest.mark.asyncio
    async def test_safe_navigation_request_flow(self):
        """Test complete request flow with safe navigation capability."""
        registry_mock = MagicMock()
        time_service_mock = MagicMock()
        wise_bus = WiseBus(registry_mock, time_service_mock)

        # Mock a navigation service
        mock_service = AsyncMock()
        mock_service.get_capabilities = MagicMock()
        mock_service.get_capabilities.return_value = MagicMock(capabilities=["domain:navigation"])
        mock_service.get_guidance = AsyncMock(
            return_value=GuidanceResponse(
                selected_option="Route A", reasoning="Shortest path", wa_id="geo", signature="geo_sig"
            )
        )

        # Mock both get_services (async) and get_service (async) for fallback
        registry_mock.get_services_by_type.return_value = [mock_service]
        registry_mock.get_services = AsyncMock(return_value=[mock_service])
        registry_mock.get_service = AsyncMock(return_value=mock_service)

        # Create a safe navigation request
        request = GuidanceRequest(
            context="Navigate from point A to point B",
            options=["Route A", "Route B"],
            capability="domain:navigation",
            urgency="normal",
        )

        # Should succeed
        response = await wise_bus.request_guidance(request)
        assert response is not None
        assert response.selected_option == "Route A"
        assert response.reasoning == "Shortest path"


# Run with: pytest tests/logic/buses/test_wise_bus_medical_blocking.py -v
