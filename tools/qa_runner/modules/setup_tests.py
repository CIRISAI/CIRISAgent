"""
Setup wizard test module.

Tests the first-run setup wizard API endpoints.
"""

from typing import List

from ..config import QAModule, QATestCase


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
                description="Get list of agent identity templates (general, moderator, researcher, etc.)",
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
            # GET /v1/setup/config - Get current config (during first-run)
            QATestCase(
                name="Get setup config (first-run)",
                module=QAModule.SETUP,
                endpoint="/v1/setup/config",
                method="GET",
                expected_status=200,
                requires_auth=False,
                description="Get current configuration during first-run (no auth required)",
            ),
            # POST /v1/setup/complete - Complete setup (minimal config)
            # NOTE: This test is intentionally commented out because it would actually
            # complete setup and break subsequent tests. Enable for manual testing only.
            # QATestCase(
            #     name="Complete setup (minimal config)",
            #     module=QAModule.SETUP,
            #     endpoint="/v1/setup/complete",
            #     method="POST",
            #     payload={
            #         "llm_provider": "openai",
            #         "llm_api_key": "sk-test_qa_key_12345",
            #         "llm_base_url": None,
            #         "llm_model": None,
            #         "template_id": "general",
            #         "enabled_adapters": ["api"],
            #         "adapter_config": {},
            #         "admin_username": "qa_test_user",
            #         "admin_password": "qa_test_password_12345",
            #         "system_admin_password": "new_admin_password_12345",
            #         "agent_port": 8080,
            #     },
            #     expected_status=200,
            #     requires_auth=False,
            #     description="Complete initial setup with minimal configuration",
            # ),
        ]

    @staticmethod
    def get_all_tests() -> List[QATestCase]:
        """Get all setup tests."""
        return SetupTestModule.get_setup_tests()
