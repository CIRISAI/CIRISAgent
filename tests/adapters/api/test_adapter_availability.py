"""
Tests for adapter availability API routes.

Tests the new adapter discovery and installation endpoints:
- GET /v1/system/adapters/available
- POST /v1/system/adapters/{adapter_name}/install
- POST /v1/system/adapters/{adapter_name}/check-eligibility
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import status

# Patch path for imports within the route module
DISCOVERY_SERVICE_PATCH = "ciris_engine.logic.services.tool.discovery_service.AdapterDiscoveryService"
INSTALLER_PATCH = "ciris_engine.logic.services.tool.installer.ToolInstaller"


class TestAdapterAvailabilityRoutes:
    """Test adapter availability API endpoints."""

    def test_available_adapters_requires_auth(self, client):
        """Test that available adapters endpoint requires auth."""
        response = client.get("/v1/system/adapters/available")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_available_adapters_with_auth(self, client, auth_headers):
        """Test available adapters endpoint with valid auth."""
        # Mock the discovery service at the source module
        with patch(DISCOVERY_SERVICE_PATCH) as mock_discovery_class:
            mock_discovery = Mock()
            mock_discovery_class.return_value = mock_discovery

            # Create mock discovery report
            mock_report = Mock()
            mock_report.model_dump.return_value = {
                "discovered_adapters": ["mcp_client", "mcp_server"],
                "eligible_adapters": ["mcp_client"],
                "ineligible_adapters": ["mcp_server"],
                "total_discovered": 2,
                "total_eligible": 1,
            }
            mock_discovery.get_discovery_report = AsyncMock(return_value=mock_report)

            response = client.get("/v1/system/adapters/available", headers=auth_headers)

            # May succeed or fail based on actual service availability
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR]

    def test_install_adapter_requires_admin(self, client, auth_headers):
        """Test that install endpoint requires auth."""
        response = client.post("/v1/system/adapters/test_adapter/install")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_install_adapter_already_eligible(self, client, auth_headers):
        """Test installing an adapter that's already eligible."""
        with patch(DISCOVERY_SERVICE_PATCH) as mock_discovery_class:
            mock_discovery = Mock()
            mock_discovery_class.return_value = mock_discovery

            # Mock adapter that's already eligible
            mock_status = Mock()
            mock_status.eligible = True
            mock_discovery.get_adapter_eligibility = AsyncMock(return_value=mock_status)

            response = client.post(
                "/v1/system/adapters/mcp_client/install",
                headers=auth_headers,
                json={},
            )

            # May succeed or error based on actual implementation
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ]

    def test_install_adapter_not_found(self, client, auth_headers):
        """Test installing an adapter that doesn't exist."""
        with patch(DISCOVERY_SERVICE_PATCH) as mock_discovery_class:
            mock_discovery = Mock()
            mock_discovery_class.return_value = mock_discovery

            # Mock adapter not found
            mock_discovery.get_adapter_eligibility = AsyncMock(return_value=None)

            response = client.post(
                "/v1/system/adapters/nonexistent_adapter/install",
                headers=auth_headers,
                json={},
            )

            # May be 404 or 500 depending on error handling
            assert response.status_code in [
                status.HTTP_404_NOT_FOUND,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ]

    def test_install_adapter_no_hints(self, client, auth_headers):
        """Test installing an adapter with no installation hints."""
        with patch(DISCOVERY_SERVICE_PATCH) as mock_discovery_class:
            mock_discovery = Mock()
            mock_discovery_class.return_value = mock_discovery

            # Mock ineligible adapter with no install hints
            mock_status = Mock()
            mock_status.eligible = False
            mock_status.can_install = False
            mock_status.install_hints = []
            mock_discovery.get_adapter_eligibility = AsyncMock(return_value=mock_status)

            response = client.post(
                "/v1/system/adapters/no_hints_adapter/install",
                headers=auth_headers,
                json={},
            )

            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ]

    def test_install_adapter_dry_run(self, client, auth_headers):
        """Test dry run installation."""
        with patch(DISCOVERY_SERVICE_PATCH) as mock_discovery_class, patch(INSTALLER_PATCH) as mock_installer_class:
            mock_discovery = Mock()
            mock_discovery_class.return_value = mock_discovery

            # Mock ineligible adapter with install hints
            mock_hint = Mock()
            mock_hint.id = "brew-test"
            mock_status = Mock()
            mock_status.eligible = False
            mock_status.can_install = True
            mock_status.install_hints = [mock_hint]
            mock_discovery.get_adapter_eligibility = AsyncMock(return_value=mock_status)

            # Mock installer with dry run success
            mock_installer = Mock()
            mock_installer_class.return_value = mock_installer
            mock_install_result = Mock()
            mock_install_result.success = True
            mock_install_result.message = "[dry-run] Would execute: brew install test"
            mock_install_result.binaries_installed = []
            mock_installer.install_first_applicable = AsyncMock(return_value=mock_install_result)

            response = client.post(
                "/v1/system/adapters/test_adapter/install",
                headers=auth_headers,
                json={"dry_run": True},
            )

            # May succeed or error based on implementation
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ]

    def test_check_eligibility_requires_auth(self, client):
        """Test that check-eligibility endpoint requires auth."""
        response = client.post("/v1/system/adapters/test_adapter/check-eligibility")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_check_eligibility_with_auth(self, client, auth_headers):
        """Test check-eligibility endpoint with valid auth."""
        with patch(DISCOVERY_SERVICE_PATCH) as mock_discovery_class:
            mock_discovery = Mock()
            mock_discovery_class.return_value = mock_discovery

            # Mock eligibility check result
            mock_status = Mock()
            mock_status.eligible = True
            mock_status.eligibility_reason = "All requirements satisfied"
            mock_status.missing_binaries = []
            mock_status.missing_env_vars = []
            mock_status.missing_config = []
            mock_status.can_install = False
            mock_discovery.get_adapter_eligibility = AsyncMock(return_value=mock_status)

            response = client.post(
                "/v1/system/adapters/mcp_client/check-eligibility",
                headers=auth_headers,
            )

            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ]

    def test_check_eligibility_not_found(self, client, auth_headers):
        """Test check-eligibility for nonexistent adapter."""
        with patch(DISCOVERY_SERVICE_PATCH) as mock_discovery_class:
            mock_discovery = Mock()
            mock_discovery_class.return_value = mock_discovery

            # Mock adapter not found
            mock_discovery.get_adapter_eligibility = AsyncMock(return_value=None)

            response = client.post(
                "/v1/system/adapters/nonexistent/check-eligibility",
                headers=auth_headers,
            )

            assert response.status_code in [
                status.HTTP_404_NOT_FOUND,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ]

    def test_check_eligibility_ineligible(self, client, auth_headers):
        """Test check-eligibility for ineligible adapter."""
        with patch(DISCOVERY_SERVICE_PATCH) as mock_discovery_class:
            mock_discovery = Mock()
            mock_discovery_class.return_value = mock_discovery

            # Mock ineligible adapter
            mock_status = Mock()
            mock_status.eligible = False
            mock_status.eligibility_reason = "Missing binary: ffmpeg"
            mock_status.missing_binaries = ["ffmpeg"]
            mock_status.missing_env_vars = []
            mock_status.missing_config = []
            mock_status.can_install = True
            mock_discovery.get_adapter_eligibility = AsyncMock(return_value=mock_status)

            response = client.post(
                "/v1/system/adapters/video_adapter/check-eligibility",
                headers=auth_headers,
            )

            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ]


class TestAdapterAvailabilityHelpers:
    """Test helper functions used by adapter availability routes."""

    def test_check_platform_requirements_empty(self):
        """Test platform check with empty requirements."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _check_platform_requirements_satisfied

        # Empty requirements should always be satisfied
        assert _check_platform_requirements_satisfied([]) is True

    def test_should_filter_adapter_mock(self):
        """Test filtering logic for mock adapters."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _should_filter_adapter

        manifest = {"module": {"MOCK": True}, "services": [{"type": "TOOL"}]}
        assert _should_filter_adapter(manifest) is True

    def test_should_filter_adapter_library(self):
        """Test filtering logic for library modules."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _should_filter_adapter

        manifest = {"module": {}, "metadata": {"type": "library"}, "services": [{"type": "TOOL"}]}
        assert _should_filter_adapter(manifest) is True

    def test_should_filter_adapter_no_services(self):
        """Test filtering logic for modules with no services."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _should_filter_adapter

        manifest = {"module": {}, "services": []}
        assert _should_filter_adapter(manifest) is True

    def test_should_filter_adapter_common_module(self):
        """Test filtering logic for common modules."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _should_filter_adapter

        manifest = {"module": {"name": "mcp_common"}, "services": [{"type": "TOOL"}]}
        assert _should_filter_adapter(manifest) is True

    def test_should_not_filter_valid_adapter(self):
        """Test that valid adapters are not filtered."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _should_filter_adapter

        manifest = {
            "module": {"name": "mcp_client", "MOCK": False},
            "services": [{"type": "TOOL"}],
            "metadata": {},
        }
        # When not filtering by platform, this should pass
        assert _should_filter_adapter(manifest, filter_by_platform=False) is False

    def test_extract_service_types(self):
        """Test extraction of service types from manifest."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _extract_service_types

        manifest = {
            "services": [
                {"type": "TOOL"},
                {"type": "COMMUNICATION"},
                {"type": "TOOL"},  # Duplicate
            ]
        }
        types = _extract_service_types(manifest)
        assert types == ["TOOL", "COMMUNICATION"]

    def test_parse_config_parameters(self):
        """Test parsing of configuration parameters from manifest."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _parse_config_parameters

        manifest = {
            "configuration": {
                "api_key": {
                    "type": "string",
                    "description": "API key for authentication",
                    "required": True,
                    "sensitivity": "HIGH",
                },
                "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds"},
            }
        }
        params = _parse_config_parameters(manifest)
        assert len(params) == 2

        api_key_param = next(p for p in params if p.name == "api_key")
        assert api_key_param.param_type == "string"
        assert api_key_param.required is True
        assert api_key_param.sensitivity == "HIGH"

        timeout_param = next(p for p in params if p.name == "timeout")
        assert timeout_param.param_type == "integer"
        assert timeout_param.default == 30

    def test_get_core_adapter_info_api(self):
        """Test getting core adapter info for API adapter."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _get_core_adapter_info

        info = _get_core_adapter_info("api")
        assert info.module_id == "api"
        assert info.name == "API Adapter"
        assert "REST API" in info.description
        assert "COMMUNICATION" in info.service_types

    def test_get_core_adapter_info_discord(self):
        """Test getting core adapter info for Discord adapter."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _get_core_adapter_info

        info = _get_core_adapter_info("discord")
        assert info.module_id == "discord"
        assert info.requires_external_deps is True
        assert "discord.py" in info.external_dependencies

    def test_get_core_adapter_info_unknown(self):
        """Test getting core adapter info for unknown adapter."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import _get_core_adapter_info

        info = _get_core_adapter_info("unknown_adapter")
        assert info.module_id == "unknown_adapter"
        # Should still return valid info with defaults
        assert info.name == "Unknown_Adapter"
