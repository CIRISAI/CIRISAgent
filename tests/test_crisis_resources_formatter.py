"""
Test suite for crisis resource formatter functions.

This test suite ensures the formatter functions in ciris_engine.logic.formatters.crisis_resources
work correctly and provide appropriate output for templates.
"""

import pytest

from ciris_engine.logic.formatters.crisis_resources import format_crisis_resources_block, get_crisis_resources_guidance
from ciris_engine.schemas.resources.crisis import DEFAULT_CRISIS_RESOURCES, ResourceAvailability


class TestCrisisResourcesFormatter:
    """Test suite for crisis resources formatter functions."""

    def test_format_with_full_disclaimer(self):
        """Test formatting with full disclaimer (default)."""
        result = format_crisis_resources_block()

        # Should include the full disclaimer text
        assert "DISCLAIMER" in result
        assert "not a healthcare provider" in result
        assert "General Crisis Resources" in result
        assert "911 or local emergency services" in result
        assert "[DEFER TO HUMAN MODERATOR]" in result

        # Should include some resources
        assert "Find a Helpline" in result or "Crisis" in result

    def test_format_without_disclaimer(self):
        """Test simplified format without full disclaimer."""
        result = format_crisis_resources_block(include_full_disclaimer=False)

        # Should have simplified header
        assert "=== Crisis Resources ===" in result

        # Should not have full disclaimer
        assert "DISCLAIMER" not in result
        assert "[DEFER TO HUMAN MODERATOR]" not in result

        # Should still have emergency services
        assert "911 or local emergency services" in result

        # Should have some resources (limited to 3)
        lines = result.split("\n")
        resource_lines = [l for l in lines if l.startswith("• ") and "911" not in l]
        assert len(resource_lines) <= 3

    def test_format_with_specific_resource_ids(self):
        """Test formatting with specific resource IDs."""
        # Test with specific resources
        resource_ids = ["findahelpline", "988_lifeline"]
        result = format_crisis_resources_block(resource_ids=resource_ids, include_full_disclaimer=False)

        # Should include the specified resources
        assert "Find a Helpline" in result
        assert "988 Suicide & Crisis Lifeline" in result

        # Should not include others not specified
        assert "Samaritans" not in result  # UK resource not requested

    def test_format_with_regional_filtering(self):
        """Test formatting with regional filtering."""
        # Test US-only resources
        result = format_crisis_resources_block(regions=[ResourceAvailability.US], include_full_disclaimer=False)

        # Should include US resources
        assert any(res in result for res in ["988 Suicide & Crisis Lifeline", "Crisis Text Line", "emergency"])

        # Test UK-only resources
        result_uk = format_crisis_resources_block(regions=[ResourceAvailability.UK], include_full_disclaimer=False)

        # Should include UK resources
        assert "Samaritans" in result_uk or "Crisis Text Line" in result_uk

    def test_format_with_global_resources(self):
        """Test that global resources are included by default."""
        result = format_crisis_resources_block(include_full_disclaimer=False)

        # Should include global resources
        assert any(res in result for res in ["Find a Helpline", "IASP", "crisis", "Local Crisis Services"])

    def test_format_with_nonexistent_resource_ids(self):
        """Test handling of nonexistent resource IDs."""
        # Mix of valid and invalid IDs
        resource_ids = ["findahelpline", "nonexistent_resource", "988_lifeline"]
        result = format_crisis_resources_block(resource_ids=resource_ids, include_full_disclaimer=False)

        # Should include valid resources
        assert "Find a Helpline" in result
        assert "988 Suicide & Crisis Lifeline" in result

        # Should gracefully skip invalid ones (no error)
        assert "nonexistent" not in result.lower()

    def test_format_with_multiple_regions(self):
        """Test formatting with multiple regions."""
        result = format_crisis_resources_block(
            regions=[ResourceAvailability.US, ResourceAvailability.UK], include_full_disclaimer=False
        )

        # Should include resources from both regions
        # At least one resource should be present
        assert any(res in result for res in ["988", "Samaritans", "Crisis Text Line", "Find a Helpline"])

    def test_get_crisis_resources_guidance(self):
        """Test the guidance text function."""
        guidance = get_crisis_resources_guidance()

        # Check key guidance points
        assert "Crisis Resource Guidance" in guidance
        assert "DO NOT attempt to provide therapy" in guidance
        assert "DO share crisis resources" in guidance
        assert "DO defer to human moderators" in guidance
        assert "DO encourage seeking professional help" in guidance

        # Check role clarification
        assert "AI moderator, not a healthcare provider" in guidance
        assert "Share publicly available crisis resources" in guidance
        assert "Provide general information only" in guidance
        assert "Include clear disclaimers" in guidance
        assert "Defer complex situations" in guidance

        # Check maximum intervention
        assert "Maximum intervention" in guidance

    def test_format_with_empty_resource_ids(self):
        """Test formatting with empty resource IDs list."""
        result = format_crisis_resources_block(resource_ids=[], include_full_disclaimer=False)

        # Should fall back to global resources
        assert "=== Crisis Resources ===" in result
        assert "911 or local emergency services" in result

    def test_format_resource_limit(self):
        """Test that simplified format limits to 3 resources."""
        result = format_crisis_resources_block(include_full_disclaimer=False)

        lines = result.split("\n")
        # Count resource lines (those starting with bullet point, excluding emergency line)
        resource_lines = [l for l in lines if l.startswith("• ") and "911" not in l and "emergency" not in l.lower()]

        # Should be limited to 3 resources
        assert len(resource_lines) <= 3

    def test_format_consistency(self):
        """Test that formatter output is consistent."""
        # Multiple calls should produce same result
        result1 = format_crisis_resources_block()
        result2 = format_crisis_resources_block()

        assert result1 == result2

        # With same parameters
        result3 = format_crisis_resources_block(regions=[ResourceAvailability.US], include_full_disclaimer=False)
        result4 = format_crisis_resources_block(regions=[ResourceAvailability.US], include_full_disclaimer=False)

        assert result3 == result4

    def test_guidance_consistency(self):
        """Test that guidance is always the same."""
        guidance1 = get_crisis_resources_guidance()
        guidance2 = get_crisis_resources_guidance()

        assert guidance1 == guidance2
        assert len(guidance1) > 100  # Should have substantial content

    def test_format_with_all_parameters(self):
        """Test with all parameters specified."""
        result = format_crisis_resources_block(
            regions=[ResourceAvailability.GLOBAL], resource_ids=["findahelpline"], include_full_disclaimer=True
        )

        # With full disclaimer, resource_ids should be used
        assert "Find a Helpline" in result
        assert "DISCLAIMER" in result

    def test_format_structure_without_disclaimer(self):
        """Test the structure of simplified format."""
        result = format_crisis_resources_block(include_full_disclaimer=False)
        lines = result.split("\n")

        # First line should be header
        assert lines[0] == "=== Crisis Resources ==="

        # Should have bullet points
        bullet_lines = [l for l in lines if l.startswith("• ")]
        assert len(bullet_lines) >= 1  # At least emergency services

        # Last bullet should be emergency services
        assert "911" in bullet_lines[-1] or "emergency" in bullet_lines[-1].lower()
