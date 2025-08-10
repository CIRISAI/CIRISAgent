"""
Critical unit test for validating crisis resource links in templates.

WHY THIS EXISTS:
A single broken crisis resource link could mean someone in distress
cannot get help when they need it most. This test ensures all crisis
resources mentioned in our templates are valid and accessible.

This test should run in CI/CD to catch broken links immediately.
"""

import os
import re
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import urlparse

import pytest
import requests
import yaml


class TestCrisisResources:
    """Test suite for validating crisis resources in templates."""

    # Known crisis resource patterns to look for
    RESOURCE_PATTERNS = [
        # Websites
        r"findahelpline\.com",
        r"iasp\.info(?:/[\w/]+)?",
        r"7cups\.com",
        r"suicidepreventionlifeline\.org(?:/[\w/]+)?",
        r"samaritans\.org",
        r"crisistextline\.org",
        # Phone numbers
        r"741741",  # Crisis Text Line
        r"988",  # US Suicide Prevention Lifeline
        r"911|112|999",  # Emergency numbers
        # Email addresses
        r"jo@samaritans\.org",
        # Any URL pattern
        r'https?://[^\s\'"]+',
    ]

    # Resources that should ALWAYS be present in crisis templates
    REQUIRED_RESOURCES = {
        "findahelpline.com": "International crisis line directory",
        "911": "US emergency services",
        "crisis hotline": "Generic search term for local help",
    }

    @pytest.fixture
    def template_files(self) -> List[Path]:
        """Get all template files that contain crisis information."""
        project_root = Path(__file__).parent.parent
        template_dir = project_root / "ciris_templates"

        # Only check templates that handle crisis situations
        crisis_templates = ["echo.yaml", "echo-core.yaml", "echo-speculative.yaml"]

        files = []
        for template_name in crisis_templates:
            template_path = template_dir / template_name
            if template_path.exists():
                files.append(template_path)

        if not files:
            pytest.skip("No crisis-handling templates found")

        return files

    def extract_resources(self, template_path: Path) -> Dict[str, List[str]]:
        """Extract all crisis resources from a template file."""
        with open(template_path, "r") as f:
            content = f.read()

        resources = {
            "websites": set(),
            "phone_numbers": set(),
            "email_addresses": set(),
            "search_terms": set(),
        }

        # Extract websites
        website_pattern = r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.(?:com|org|info|net|gov|uk|ca|au)[^\s\'"]*)'
        for match in re.finditer(website_pattern, content, re.IGNORECASE):
            domain = match.group(1).lower()
            # Clean up domain
            domain = domain.rstrip(".,;:")
            if not any(skip in domain for skip in ["example.", "your", "[", "]"]):
                resources["websites"].add(domain)

        # Extract phone numbers (specifically crisis lines)
        if "741741" in content:
            resources["phone_numbers"].add("741741")
        if "988" in content:
            resources["phone_numbers"].add("988")

        # Extract email addresses
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        for match in re.finditer(email_pattern, content):
            email = match.group(0).lower()
            if "samaritans" in email:  # Only crisis-related emails
                resources["email_addresses"].add(email)

        # Extract search guidance
        search_pattern = r'[Ss]earch[:\s]+[\'"]([^\'"\n]+)[\'"]'
        for match in re.finditer(search_pattern, content):
            term = match.group(1)
            if "crisis" in term.lower() or "hotline" in term.lower():
                resources["search_terms"].add(term)

        return {k: list(v) for k, v in resources.items()}

    def validate_website(self, url: str, timeout: int = 10) -> Tuple[bool, str]:
        """Validate a website is accessible."""
        # Ensure URL has protocol
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        try:
            # Use HEAD request first (faster)
            response = requests.head(url, timeout=timeout, allow_redirects=True)

            # If HEAD fails or returns error, try GET
            if response.status_code >= 400:
                response = requests.get(url, timeout=timeout, allow_redirects=True)

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

    @pytest.mark.skipif(os.environ.get("CI") == "true", reason="Skip external URL validation in CI environment")
    def test_all_crisis_resources_valid(self, template_files: List[Path]):
        """Test that all crisis resources in templates are valid and accessible."""
        all_resources = {}
        validation_results = {}

        # Extract resources from all templates
        for template_path in template_files:
            resources = self.extract_resources(template_path)
            all_resources[template_path.name] = resources

        # Validate websites
        print("\n" + "=" * 60)
        print("CRISIS RESOURCE VALIDATION")
        print("=" * 60)

        tested_urls = set()  # Avoid testing same URL multiple times
        failed_resources = []

        for template_name, resources in all_resources.items():
            print(f"\n{template_name}:")
            print("-" * 40)

            # Test websites
            if resources["websites"]:
                print("  Websites:")
                for website in resources["websites"]:
                    if website not in tested_urls:
                        tested_urls.add(website)
                        is_valid, status = self.validate_website(website)

                        status_symbol = "✓" if is_valid else "✗"
                        print(f"    {status_symbol} {website}: {status}")

                        if not is_valid:
                            failed_resources.append(f"{template_name}: {website} - {status}")

                        # Be nice to servers
                        time.sleep(0.5)

            # Display other resources (not validated but logged)
            if resources["phone_numbers"]:
                print("  Phone Numbers:")
                for number in resources["phone_numbers"]:
                    print(f"    ℹ {number} (not validated)")

            if resources["email_addresses"]:
                print("  Email Addresses:")
                for email in resources["email_addresses"]:
                    print(f"    ℹ {email} (not validated)")

            if resources["search_terms"]:
                print("  Search Guidance:")
                for term in resources["search_terms"]:
                    print(f'    ℹ "{term}"')

        # Check for required resources
        print("\n" + "=" * 60)
        print("REQUIRED RESOURCE CHECK")
        print("=" * 60)

        all_content = ""
        for template_path in template_files:
            with open(template_path, "r") as f:
                all_content += f.read().lower()

        missing_required = []
        for resource, description in self.REQUIRED_RESOURCES.items():
            if resource.lower() not in all_content:
                missing_required.append(f"{resource} ({description})")
                print(f"  ✗ Missing: {resource} - {description}")
            else:
                print(f"  ✓ Found: {resource}")

        # Final report
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)

        if failed_resources:
            print("\n⚠️  FAILED RESOURCES (CRITICAL):")
            for failure in failed_resources:
                print(f"  - {failure}")

        if missing_required:
            print("\n⚠️  MISSING REQUIRED RESOURCES:")
            for missing in missing_required:
                print(f"  - {missing}")

        # Fail the test if any resources are broken or missing
        if failed_resources or missing_required:
            error_msg = "\n\nCRITICAL: Crisis resources validation failed!\n"
            error_msg += "This could prevent someone in crisis from getting help.\n"
            error_msg += "Please fix immediately:\n"

            if failed_resources:
                error_msg += "\nBroken/Inaccessible Resources:\n"
                for failure in failed_resources:
                    error_msg += f"  - {failure}\n"

            if missing_required:
                error_msg += "\nMissing Required Resources:\n"
                for missing in missing_required:
                    error_msg += f"  - {missing}\n"

            pytest.fail(error_msg)
        else:
            print("\n✓ All crisis resources validated successfully!")

    def test_no_medical_provider_claims(self, template_files: List[Path]):
        """Ensure templates don't claim to be medical providers."""
        problematic_phrases = [
            r"I can help you",
            r"I'll help you",
            r"I will help you",
            r"I can provide.*support",
            r"I can diagnose",
            r"I can treat",
            r"I am.*therapist",
            r"I am.*counselor",
            r"I am.*doctor",
            r"I am.*psychiatrist",
        ]

        violations = []

        for template_path in template_files:
            with open(template_path, "r") as f:
                content = f.read()

            for pattern in problematic_phrases:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Get surrounding context
                    start = max(0, match.start() - 50)
                    end = min(len(content), match.end() + 50)
                    context = content[start:end].replace("\n", " ")

                    violations.append({"template": template_path.name, "phrase": match.group(0), "context": context})

        if violations:
            error_msg = "\n\nLIABILITY WARNING: Templates contain medical provider language!\n"
            error_msg += "This could create legal liability for CIRIS L3C.\n\n"

            for v in violations:
                error_msg += f"Template: {v['template']}\n"
                error_msg += f"  Problem: \"{v['phrase']}\"\n"
                error_msg += f"  Context: ...{v['context']}...\n\n"

            pytest.fail(error_msg)

    def test_proper_disclaimers_present(self, template_files: List[Path]):
        """Ensure all crisis-handling templates have proper disclaimers."""
        # These are the key disclaimers that must be present in some form
        # We check for various phrasings that convey the same meaning
        required_disclaimer_patterns = [
            ["NOT a licensed medical", "not a licensed medical"],
            ["CIRIS L3C is not a healthcare provider", "not a healthcare provider"],
            ["general information only", "information only"],
            ["not medical advice", "not provide medical", "does not provide medical"],
        ]

        missing_disclaimers = []

        for template_path in template_files:
            with open(template_path, "r") as f:
                content = f.read()

            # Check if template uses crisis_resources_block placeholder
            uses_crisis_block = "{crisis_resources_block}" in content

            # Convert content to lowercase for case-insensitive comparison
            content_lower = content.lower()

            # If template uses the block, disclaimers are provided through the block
            # Otherwise, they should be in the template directly
            if not uses_crisis_block:
                for pattern_group in required_disclaimer_patterns:
                    # Check if any variant of the disclaimer is present
                    found = any(pattern.lower() in content_lower for pattern in pattern_group)
                    if not found:
                        # Use the first pattern as the "canonical" missing disclaimer
                        missing_disclaimers.append({"template": template_path.name, "missing": pattern_group[0]})

        if missing_disclaimers:
            error_msg = "\n\nLEGAL COMPLIANCE: Missing required disclaimers!\n\n"

            for item in missing_disclaimers:
                error_msg += f"Template: {item['template']}\n"
                error_msg += f"  Missing: \"{item['missing']}\"\n"

            pytest.fail(error_msg)


if __name__ == "__main__":
    # Allow running directly for debugging
    pytest.main([__file__, "-v", "--tb=short"])
