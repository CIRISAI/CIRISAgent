"""
Comprehensive tests for the prohibition system in WiseBus.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.buses.prohibitions import (
    COMMUNITY_MODERATION_CAPABILITIES,
    LEGITIMATE_MODULE_CATEGORIES,
    PROHIBITED_CAPABILITIES,
    ProhibitionSeverity,
    get_capability_category,
    get_prohibition_severity,
)
from ciris_engine.logic.buses.wise_bus import WiseBus
from ciris_engine.schemas.services.authority_core import GuidanceRequest, GuidanceResponse


class TestProhibitionCategories:
    """Test prohibition category detection and classification."""

    def test_medical_capability_detection(self):
        """Test detection of medical capabilities."""
        assert get_capability_category("diagnosis") == "MEDICAL"
        assert get_capability_category("treatment") == "MEDICAL"
        assert get_capability_category("prescription") == "MEDICAL"
        assert get_capability_category("medical_advice") == "MEDICAL"

    def test_financial_capability_detection(self):
        """Test detection of financial capabilities."""
        assert get_capability_category("investment_advice") == "FINANCIAL"
        assert get_capability_category("trading_signals") == "FINANCIAL"
        assert get_capability_category("portfolio_management") == "FINANCIAL"

    def test_weapons_capability_detection(self):
        """Test detection of weapons capabilities."""
        assert get_capability_category("weapon_design") == "WEAPONS_HARMFUL"
        assert get_capability_category("explosive_synthesis") == "WEAPONS_HARMFUL"
        assert get_capability_category("chemical_weapons") == "WEAPONS_HARMFUL"

    def test_manipulation_capability_detection(self):
        """Test detection of manipulation capabilities."""
        assert get_capability_category("subliminal_messaging") == "MANIPULATION_COERCION"
        assert get_capability_category("gaslighting") == "MANIPULATION_COERCION"
        assert get_capability_category("brainwashing") == "MANIPULATION_COERCION"

    def test_community_moderation_detection(self):
        """Test detection of community moderation capabilities."""
        assert get_capability_category("notify_moderators") == "COMMUNITY_CRISIS_ESCALATION"
        assert get_capability_category("identify_harm_patterns") == "COMMUNITY_PATTERN_DETECTION"
        assert get_capability_category("connect_crisis_resources") == "COMMUNITY_PROTECTIVE_ROUTING"

    def test_unknown_capability(self):
        """Test that unknown capabilities return None."""
        assert get_capability_category("harmless_capability") is None
        assert get_capability_category("regular_task") is None


class TestProhibitionSeverity:
    """Test prohibition severity classification."""

    def test_separate_module_severity(self):
        """Test capabilities requiring separate modules."""
        assert get_prohibition_severity("MEDICAL") == ProhibitionSeverity.REQUIRES_SEPARATE_MODULE
        assert get_prohibition_severity("FINANCIAL") == ProhibitionSeverity.REQUIRES_SEPARATE_MODULE
        assert get_prohibition_severity("LEGAL") == ProhibitionSeverity.REQUIRES_SEPARATE_MODULE

    def test_never_allowed_severity(self):
        """Test absolutely prohibited capabilities."""
        assert get_prohibition_severity("WEAPONS_HARMFUL") == ProhibitionSeverity.NEVER_ALLOWED
        assert get_prohibition_severity("MANIPULATION_COERCION") == ProhibitionSeverity.NEVER_ALLOWED
        assert get_prohibition_severity("CYBER_OFFENSIVE") == ProhibitionSeverity.NEVER_ALLOWED

    def test_tier_restricted_severity(self):
        """Test tier-restricted capabilities."""
        assert get_prohibition_severity("COMMUNITY_CRISIS_ESCALATION") == ProhibitionSeverity.TIER_RESTRICTED
        assert get_prohibition_severity("COMMUNITY_PATTERN_DETECTION") == ProhibitionSeverity.TIER_RESTRICTED


class TestWiseBusProhibitions:
    """Test WiseBus prohibition enforcement."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock service registry."""
        registry = MagicMock()
        registry.get_services_by_type.return_value = []
        registry.get_service = AsyncMock(return_value=None)  # No service available
        return registry

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        time_service = MagicMock()
        time_service.now.return_value = "2024-01-01T00:00:00Z"
        return time_service

    @pytest.fixture
    def wise_bus(self, mock_registry, mock_time_service):
        """Create a WiseBus instance."""
        return WiseBus(mock_registry, mock_time_service)

    def test_medical_capability_blocked(self, wise_bus):
        """Test that medical capabilities are blocked."""
        with pytest.raises(ValueError, match="PROHIBITED.*MEDICAL.*capabilities blocked"):
            wise_bus._validate_capability("diagnosis", agent_tier=1)

        with pytest.raises(ValueError, match="PROHIBITED.*MEDICAL.*capabilities blocked"):
            wise_bus._validate_capability("treatment", agent_tier=3)

    def test_weapons_capability_blocked(self, wise_bus):
        """Test that weapons capabilities are absolutely blocked."""
        with pytest.raises(ValueError, match="ABSOLUTELY PROHIBITED.*WEAPONS_HARMFUL"):
            wise_bus._validate_capability("weapon_design", agent_tier=1)

        # Even tier 5 can't access weapons
        with pytest.raises(ValueError, match="ABSOLUTELY PROHIBITED.*WEAPONS_HARMFUL"):
            wise_bus._validate_capability("explosive_synthesis", agent_tier=5)

    def test_community_moderation_tier_1_blocked(self, wise_bus):
        """Test that tier 1 agents can't use community moderation."""
        with pytest.raises(ValueError, match="TIER RESTRICTED.*requires Tier 4-5"):
            wise_bus._validate_capability("notify_moderators", agent_tier=1)

        with pytest.raises(ValueError, match="TIER RESTRICTED.*requires Tier 4-5"):
            wise_bus._validate_capability("identify_harm_patterns", agent_tier=3)

    def test_community_moderation_tier_4_allowed(self, wise_bus):
        """Test that tier 4-5 agents can use community moderation."""
        # Should not raise
        wise_bus._validate_capability("notify_moderators", agent_tier=4)
        wise_bus._validate_capability("identify_harm_patterns", agent_tier=5)
        wise_bus._validate_capability("connect_crisis_resources", agent_tier=4)

    def test_harmless_capability_allowed(self, wise_bus):
        """Test that harmless capabilities are allowed."""
        # Should not raise for any tier
        wise_bus._validate_capability("general_conversation", agent_tier=1)
        wise_bus._validate_capability("information_lookup", agent_tier=3)
        wise_bus._validate_capability(None, agent_tier=1)

    @pytest.mark.asyncio
    async def test_request_guidance_validates_capability(self, wise_bus):
        """Test that request_guidance validates capabilities."""
        request = GuidanceRequest(
            context="Test request",
            capability="medical_diagnosis",
            options=["allow", "deny"],
        )

        with pytest.raises(ValueError, match="PROHIBITED.*MEDICAL"):
            await wise_bus.request_guidance(request, agent_tier=1)

    @pytest.mark.asyncio
    async def test_agent_tier_detection_default(self, wise_bus):
        """Test default agent tier detection."""
        tier = await wise_bus.get_agent_tier()
        assert tier == 1  # Default tier

    @pytest.mark.asyncio
    async def test_agent_tier_detection_from_config(self, wise_bus, mock_registry):
        """Test agent tier detection from config."""
        # Mock config service
        config_service = MagicMock()
        config_service.get_value = AsyncMock(return_value="4")
        mock_registry.get_services_by_type.return_value = [config_service]

        tier = await wise_bus.get_agent_tier()
        assert tier == 4

    @pytest.mark.asyncio
    async def test_agent_tier_caching(self, wise_bus):
        """Test that agent tier is cached after first detection."""
        # First call sets the cache
        tier1 = await wise_bus.get_agent_tier()
        assert tier1 == 1

        # Manually set to different value
        wise_bus._agent_tier = 5

        # Second call should use cache
        tier2 = await wise_bus.get_agent_tier()
        assert tier2 == 5  # Uses cached value


class TestProhibitionCompleteness:
    """Test that all categories are properly defined."""

    def test_all_prohibited_categories_have_severity(self):
        """Test that all prohibited categories have a defined severity."""
        for category in PROHIBITED_CAPABILITIES.keys():
            severity = get_prohibition_severity(category)
            assert severity is not None, f"Category {category} has no severity"

    def test_all_community_categories_are_tier_restricted(self):
        """Test that all community moderation categories are tier-restricted."""
        for category in COMMUNITY_MODERATION_CAPABILITIES.keys():
            full_category = f"COMMUNITY_{category}"
            severity = get_prohibition_severity(full_category)
            assert severity == ProhibitionSeverity.TIER_RESTRICTED

    def test_legitimate_modules_are_separate_module_severity(self):
        """Test that legitimate module categories have correct severity."""
        for category in LEGITIMATE_MODULE_CATEGORIES:
            severity = get_prohibition_severity(category)
            assert severity == ProhibitionSeverity.REQUIRES_SEPARATE_MODULE

    def test_no_overlapping_capabilities(self):
        """Test that no capability appears in multiple categories."""
        all_capabilities = set()

        # Collect all capabilities
        for capabilities in PROHIBITED_CAPABILITIES.values():
            for cap in capabilities:
                assert cap not in all_capabilities, f"Duplicate capability: {cap}"
                all_capabilities.add(cap)

        for capabilities in COMMUNITY_MODERATION_CAPABILITIES.values():
            for cap in capabilities:
                assert cap not in all_capabilities, f"Duplicate capability: {cap}"
                all_capabilities.add(cap)


class TestProhibitionTelemetry:
    """Test prohibition telemetry reporting."""

    @pytest.mark.asyncio
    async def test_telemetry_includes_prohibition_counts(self):
        """Test that telemetry includes prohibition category counts."""
        registry = MagicMock()
        registry.get_services_by_type.return_value = []
        time_service = MagicMock()

        wise_bus = WiseBus(registry, time_service)
        telemetry = await wise_bus.collect_telemetry()

        # Check that telemetry includes prohibition counts
        assert "prohibited_capabilities" in telemetry
        assert "total_prohibited" in telemetry
        assert "community_capabilities" in telemetry
        assert "total_community" in telemetry

        # Verify counts are correct
        assert telemetry["total_prohibited"] > 0
        assert telemetry["total_community"] > 0

        # Check specific categories
        assert "medical" in telemetry["prohibited_capabilities"]
        assert "weapons_harmful" in telemetry["prohibited_capabilities"]
        assert "crisis_escalation" in telemetry["community_capabilities"]
