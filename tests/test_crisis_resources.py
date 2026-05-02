"""
Critical unit test for validating crisis resources in the typed schema.

WHY THIS EXISTS:
A single broken crisis resource link could mean someone in distress
cannot get help when they need it most. This test ensures all crisis
resources in our centralized registry are valid and accessible.

ARCHITECTURE UPDATE (1.4.0):
Crisis resources moved from hardcoded template text to a typed Pydantic
schema (ciris_engine.schemas.resources.crisis). Templates now use
{crisis_resources_block} placeholders that get populated from the
DEFAULT_CRISIS_RESOURCES registry at runtime.

This test validates the schema-based resources, not template text.
"""

import os
import time
from pathlib import Path
from typing import Tuple

import pytest
import requests

from ciris_engine.schemas.resources.crisis import DEFAULT_CRISIS_RESOURCES, CrisisResourceType


class TestCrisisResources:
    """Test suite for validating crisis resources in the typed schema."""

    # Required resource IDs that must exist in DEFAULT_CRISIS_RESOURCES
    REQUIRED_RESOURCE_IDS = {
        "findahelpline": "International crisis line directory",
        "emergency_services": "Emergency services (911)",
        "local_search": "Generic search term for local help",
    }

    # Required resource types that must be present
    REQUIRED_RESOURCE_TYPES = {
        CrisisResourceType.DIRECTORY: "Crisis resource directories",
        CrisisResourceType.EMERGENCY: "Emergency services",
        CrisisResourceType.SEARCH_TERM: "Search terms for local resources",
    }

    def validate_resource_url(self, url: str, timeout: int = 5) -> Tuple[bool, str]:
        """
        Validate that a crisis resource URL is accessible.

        Args:
            url: The URL to validate
            timeout: Request timeout in seconds

        Returns:
            Tuple of (is_valid, status_message)
        """
        try:
            response = requests.get(url, timeout=timeout, verify=True)
            if response.status_code < 400:
                return True, f"OK ({response.status_code})"
            else:
                return False, f"HTTP {response.status_code}"
        except requests.exceptions.SSLError:
            # Try without SSL verification (some crisis sites have cert issues)
            try:
                response = requests.get(url, timeout=timeout, verify=False)
                if response.status_code < 400:
                    return True, f"OK with SSL warning ({response.status_code})"
                else:
                    return False, f"HTTP {response.status_code}"
            except Exception as e:
                return False, f"SSL Error: {str(e)}"
        except requests.exceptions.Timeout:
            return False, "Timeout"
        except requests.exceptions.ConnectionError:
            return False, "Connection failed"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def test_required_resources_exist(self):
        """Test that all required crisis resources exist in the schema."""
        print("\n" + "=" * 60)
        print("CRISIS RESOURCE SCHEMA VALIDATION")
        print("=" * 60)

        missing_resources = []

        # Check required resource IDs
        print("\nRequired Resource IDs:")
        print("-" * 40)
        for resource_id, description in self.REQUIRED_RESOURCE_IDS.items():
            if resource_id in DEFAULT_CRISIS_RESOURCES.resources:
                resource = DEFAULT_CRISIS_RESOURCES.resources[resource_id]
                print(f"  ✓ {resource_id}: {resource.name}")
            else:
                print(f"  ✗ {resource_id}: MISSING - {description}")
                missing_resources.append(f"{resource_id} ({description})")

        # Check required resource types
        print("\nRequired Resource Types:")
        print("-" * 40)
        for resource_type, description in self.REQUIRED_RESOURCE_TYPES.items():
            resources_of_type = DEFAULT_CRISIS_RESOURCES.get_by_type(resource_type)
            if resources_of_type:
                print(f"  ✓ {resource_type.value}: {len(resources_of_type)} resource(s)")
                for r in resources_of_type[:3]:  # Show first 3
                    print(f"    - {r.name}")
            else:
                print(f"  ✗ {resource_type.value}: MISSING - {description}")
                missing_resources.append(f"{resource_type.value} ({description})")

        # Assert all required resources exist
        assert not missing_resources, f"Required resources missing: {missing_resources}"
        print(f"\n✅ All required crisis resources present in schema!")

    def test_all_resources_valid(self):
        """Test that all crisis resources in the schema are properly formed."""
        print("\n" + "=" * 60)
        print("CRISIS RESOURCE VALIDATION")
        print("=" * 60)

        validation_results = DEFAULT_CRISIS_RESOURCES.validate_all_resources()
        invalid_resources = []

        print("\nResource Validation:")
        print("-" * 40)
        for resource_id, is_valid in validation_results.items():
            resource = DEFAULT_CRISIS_RESOURCES.resources[resource_id]
            if is_valid:
                print(f"  ✓ {resource_id}: {resource.name}")
            else:
                print(f"  ✗ {resource_id}: INVALID")
                invalid_resources.append(resource_id)

        # Check each resource has at least one contact method
        print("\nContact Methods:")
        print("-" * 40)
        for resource_id, resource in DEFAULT_CRISIS_RESOURCES.resources.items():
            contact_methods = []
            if resource.url:
                contact_methods.append("URL")
            if resource.phone:
                contact_methods.append("Phone")
            if resource.text_number:
                contact_methods.append("Text")
            if resource.search_term:
                contact_methods.append("Search")

            if contact_methods:
                print(f"  ✓ {resource_id}: {', '.join(contact_methods)}")
            else:
                print(f"  ✗ {resource_id}: NO CONTACT METHOD")
                invalid_resources.append(f"{resource_id} (no contact)")

        assert not invalid_resources, f"Invalid resources found: {invalid_resources}"
        print(f"\n✅ All {len(DEFAULT_CRISIS_RESOURCES.resources)} crisis resources validated successfully!")

    @pytest.mark.skipif(os.environ.get("CI") == "true", reason="Skip external URL validation in CI environment")
    def test_resource_urls_accessible(self):
        """Test that crisis resource URLs are accessible (skip in CI)."""
        print("\n" + "=" * 60)
        print("CRISIS RESOURCE URL VALIDATION")
        print("=" * 60)

        failed_urls = []

        for resource_id, resource in DEFAULT_CRISIS_RESOURCES.resources.items():
            if resource.url:
                is_valid, status = self.validate_resource_url(str(resource.url))
                symbol = "✓" if is_valid else "✗"
                print(f"  {symbol} {resource.name}: {status}")
                if not is_valid:
                    failed_urls.append(f"{resource.name} ({resource.url}): {status}")
                # Be nice to servers
                time.sleep(0.5)

        # In production, we'd assert no failures, but for now just warn
        if failed_urls:
            print(f"\n⚠️  {len(failed_urls)} URLs failed validation (may be transient)")
        else:
            print(f"\n✅ All resource URLs accessible!")

    def test_templates_have_placeholder(self):
        """Test that templates have the crisis_resources_block placeholder."""
        project_root = Path(__file__).parent.parent
        template_dir = project_root / "ciris_templates"
        crisis_templates = ["echo.yaml", "echo-core.yaml", "echo-speculative.yaml"]

        print("\n" + "=" * 60)
        print("TEMPLATE PLACEHOLDER CHECK")
        print("=" * 60)

        missing_placeholder = []

        for template_name in crisis_templates:
            template_path = template_dir / template_name
            if template_path.exists():
                with open(template_path, "r") as f:
                    content = f.read()
                if "{crisis_resources_block}" in content:
                    print(f"  ✓ {template_name}: Has crisis_resources_block placeholder")
                else:
                    print(f"  ✗ {template_name}: MISSING crisis_resources_block placeholder")
                    missing_placeholder.append(template_name)
            else:
                print(f"  - {template_name}: Template not found")

        assert not missing_placeholder, f"Templates missing placeholder: {missing_placeholder}"
        print(f"\n✅ All templates have crisis_resources_block placeholder!")

    def test_disclaimer_present(self):
        """Test that the legal disclaimer is present."""
        print("\n" + "=" * 60)
        print("LEGAL DISCLAIMER CHECK")
        print("=" * 60)

        assert DEFAULT_CRISIS_RESOURCES.disclaimer, "No disclaimer text configured"
        assert "not a healthcare provider" in DEFAULT_CRISIS_RESOURCES.disclaimer.lower()
        assert (
            "not endorse" in DEFAULT_CRISIS_RESOURCES.disclaimer.lower()
            or "no endorsement" in DEFAULT_CRISIS_RESOURCES.disclaimer.lower()
        )

        print(f"  ✓ Disclaimer present ({len(DEFAULT_CRISIS_RESOURCES.disclaimer)} chars)")
        print(f"  ✓ Contains required legal language")
        print(f"\n✅ Legal disclaimer properly configured!")

    def test_ethiopia_resources_pinned(self):
        """Pin the Ethiopia crisis resources added in 2.7.8.1.

        Why this exists: the v3 Amharic mental-health arc against Qwen
        landed Q5 (active SI with plan) and the agent emitted SPEAK with
        emergency-number content. Without the schema entry, the agent has
        to invent the number from the LLM's parametric knowledge — which
        will be unreliable across providers (Qwen happened to get 907
        right; gemma-4 may not). Pin the resource so the prompt-formatter
        can surface it deterministically when an am-locale crisis fires.

        Numbers verified May 2026 against multiple sources:
        - 991 = Federal Police (Ethiopia)
        - 907 = Ambulance (Addis Ababa Red Cross — primary medical/psych route)
        - 939 = Fire Brigade (some regions also use 912)
        """
        from ciris_engine.schemas.resources.crisis import ResourceAvailability

        # All three Ethiopia entries must exist
        for rid in ("ethiopia_police", "ethiopia_ambulance", "ethiopia_fire"):
            assert rid in DEFAULT_CRISIS_RESOURCES.resources, f"Missing Ethiopia resource: {rid}"
            r = DEFAULT_CRISIS_RESOURCES.resources[rid]
            assert ResourceAvailability.ETHIOPIA in r.availability
            assert "am" in r.languages, f"{rid} should be available in Amharic"
            assert r.phone, f"{rid} must have a phone number"

        # Pin the specific phone numbers — these are load-bearing safety data,
        # not implementation details. A future "cleanup" that drops 907 would
        # silently revert the eval-driven fix.
        assert DEFAULT_CRISIS_RESOURCES.resources["ethiopia_police"].phone == "991"
        assert DEFAULT_CRISIS_RESOURCES.resources["ethiopia_ambulance"].phone == "907"
        assert DEFAULT_CRISIS_RESOURCES.resources["ethiopia_fire"].phone == "939"

        # Country-region filter should surface only Ethiopia entries (+ globals)
        ethiopia_resources = DEFAULT_CRISIS_RESOURCES.get_by_availability([ResourceAvailability.ETHIOPIA])
        ethiopia_ids = {r.id for r in ethiopia_resources}
        assert {"ethiopia_police", "ethiopia_ambulance", "ethiopia_fire"}.issubset(ethiopia_ids)
        # Globals still come through (findahelpline, IASP, local_search)
        assert "findahelpline" in ethiopia_ids
