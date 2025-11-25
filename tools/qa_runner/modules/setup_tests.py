"""
Setup wizard test module.

Tests the first-run setup wizard API endpoints.
"""

import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from ..config import QAModule, QATestCase


def _validate_templates_response(response: Dict[str, Any]) -> bool:
    """Validate that templates response contains required templates.

    Args:
        response: The JSON response from /v1/setup/templates

    Returns:
        True if valid, raises AssertionError if not
    """
    data = response.get("data", [])
    assert data, "No templates returned in response"

    # Extract template IDs
    template_ids = [t.get("id") for t in data]

    # Required templates that must be present
    required_templates = ["default", "ally"]  # default.yaml=Datum, ally.yaml=Ally

    missing = [t for t in required_templates if t not in template_ids]
    assert not missing, f"Missing required templates: {missing}. Found: {template_ids}"

    # Verify default template has name "Datum"
    default_template = next((t for t in data if t.get("id") == "default"), None)
    assert default_template, "Default template not found in response"
    assert default_template.get("name") == "Datum", f"Default template should have name 'Datum', got: {default_template.get('name')}"

    # Verify ally template has name "Ally"
    ally_template = next((t for t in data if t.get("id") == "ally"), None)
    assert ally_template, "Ally template not found in response"
    assert ally_template.get("name") == "Ally", f"Ally template should have name 'Ally', got: {ally_template.get('name')}"

    # Verify minimum expected templates
    expected_min_count = 5  # default, sage, scout, echo, ally at minimum
    assert len(data) >= expected_min_count, f"Expected at least {expected_min_count} templates, got {len(data)}: {template_ids}"

    return True


class SetupTestModule:
    """Test module for setup wizard endpoints."""

    @staticmethod
    def get_setup_tests() -> List[QATestCase]:
        """Get setup wizard test cases.

        These tests verify the first-run setup wizard functionality.
        All tests run without authentication during first-run mode.
        """
        return [
            # GET /v1/setup/status - Check setup status
            QATestCase(
                name="Get setup status",
                module=QAModule.SETUP,
                endpoint="/v1/setup/status",
                method="GET",
                expected_status=200,
                requires_auth=False,
                description="Check if setup is required (first-run detection)",
            ),
            # GET /v1/setup/providers - List LLM providers
            QATestCase(
                name="List LLM providers",
                module=QAModule.SETUP,
                endpoint="/v1/setup/providers",
                method="GET",
                expected_status=200,
                requires_auth=False,
                description="Get list of supported LLM providers (OpenAI, local, other)",
            ),
            # GET /v1/setup/templates - List agent templates
            QATestCase(
                name="List agent templates",
                module=QAModule.SETUP,
                endpoint="/v1/setup/templates",
                method="GET",
                expected_status=200,
                requires_auth=False,
                description="Get list of agent identity templates - must include default (Datum) and ally",
                custom_validation=_validate_templates_response,
            ),
            # GET /v1/setup/adapters - List available adapters
            QATestCase(
                name="List available adapters",
                module=QAModule.SETUP,
                endpoint="/v1/setup/adapters",
                method="GET",
                expected_status=200,
                requires_auth=False,
                description="Get list of communication adapters (api, cli, discord, reddit)",
            ),
            # POST /v1/setup/validate-llm - Validate LLM configuration (success)
            QATestCase(
                name="Validate LLM configuration (mock)",
                module=QAModule.SETUP,
                endpoint="/v1/setup/validate-llm",
                method="POST",
                payload={
                    "provider": "local",
                    "api_key": "mock_key",
                    "base_url": "http://localhost:11434",
                    "model": "llama3",
                },
                expected_status=200,
                requires_auth=False,
                description="Test LLM connection validation (mock mode - expected to fail gracefully)",
            ),
            # POST /v1/setup/validate-llm - Invalid OpenAI key
            QATestCase(
                name="Validate LLM with invalid OpenAI key",
                module=QAModule.SETUP,
                endpoint="/v1/setup/validate-llm",
                method="POST",
                payload={
                    "provider": "openai",
                    "api_key": "",
                    "base_url": None,
                    "model": None,
                },
                expected_status=200,  # Endpoint returns 200 with valid: false
                requires_auth=False,
                description="Test LLM validation with invalid OpenAI key (returns valid: false)",
            ),
            # NOTE: GET /v1/setup/config test removed - requires actual first-run state
            # which QA runner cannot easily simulate. This endpoint is tested in unit tests.
            # POST /v1/setup/complete - Complete setup (minimal config)
            QATestCase(
                name="Complete setup (minimal config)",
                module=QAModule.SETUP,
                endpoint="/v1/setup/complete",
                method="POST",
                payload={
                    "llm_provider": "openai",
                    "llm_api_key": "sk-test_qa_key_12345",
                    "llm_base_url": None,
                    "llm_model": None,
                    "template_id": "general",
                    "enabled_adapters": ["api"],
                    "adapter_config": {},
                    "admin_username": "qa_test_user",
                    "admin_password": "qa_test_password_12345",
                    "system_admin_password": "new_admin_password_12345",
                    "agent_port": 8080,
                },
                expected_status=200,
                requires_auth=False,
                description="Complete initial setup with minimal configuration",
            ),
            # POST /v1/auth/login - Verify user creation after setup
            QATestCase(
                name="Login as created setup user",
                module=QAModule.SETUP,
                endpoint="/v1/auth/login",
                method="POST",
                payload={
                    "username": "qa_test_user",
                    "password": "qa_test_password_12345",
                },
                expected_status=200,
                requires_auth=False,
                description="Verify that the user created during setup can log in successfully",
            ),
        ]

    @staticmethod
    def get_all_tests() -> List[QATestCase]:
        """Get all setup tests."""
        return SetupTestModule.get_setup_tests()
