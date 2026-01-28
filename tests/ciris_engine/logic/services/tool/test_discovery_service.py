"""Tests for the AdapterDiscoveryService."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Type
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService
from ciris_engine.logic.services.tool.eligibility_checker import EligibilityResult, ToolEligibilityChecker
from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema, ToolRequirements


def make_tool_info(name: str, description: str, **kwargs) -> ToolInfo:
    """Helper to create ToolInfo with default parameters."""
    return ToolInfo(
        name=name,
        description=description,
        parameters=ToolParameterSchema(type="object", properties={}),
        **kwargs,
    )


from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.manifest import ModuleInfo, ServiceDeclaration, ServiceManifest


def create_mock_manifest(name: str, services: Optional[List[str]] = None) -> ServiceManifest:
    """Create a mock service manifest for testing."""
    service_defs = [
        ServiceDeclaration(type=ServiceType.TOOL, class_path=f"{name}.service.{s}Service")
        for s in (services or ["main"])
    ]
    return ServiceManifest(
        module=ModuleInfo(
            name=name,
            version="1.0.0",
            description=f"Test adapter {name}",
            author="test",
        ),
        services=service_defs,
    )


class TestAdapterDiscoveryService:
    """Tests for AdapterDiscoveryService."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        assert service.checker is not None
        assert isinstance(service.checker, ToolEligibilityChecker)
        assert service.extra_paths == []

    def test_init_with_custom_checker(self) -> None:
        """Test initialization with custom eligibility checker."""
        checker = ToolEligibilityChecker()
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService(eligibility_checker=checker)

        assert service.checker is checker

    def test_init_with_extra_paths(self) -> None:
        """Test initialization with extra paths."""
        extra = [Path("/custom/adapters")]
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService(extra_paths=extra)

        assert Path("/custom/adapters") in service.extra_paths

    def test_init_parses_env_var(self) -> None:
        """Test initialization parses CIRIS_EXTRA_ADAPTERS env var."""
        with patch.dict(os.environ, {"CIRIS_EXTRA_ADAPTERS": "/path1:/path2"}):
            with patch.object(Path, "exists", return_value=False):
                with patch.object(Path, "is_dir", return_value=False):
                    service = AdapterDiscoveryService()

        assert Path("/path1") in service.extra_paths
        assert Path("/path2") in service.extra_paths

    def test_get_all_paths(self) -> None:
        """Test _get_all_paths returns standard plus extra paths."""
        extra = [Path("/custom")]
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService(extra_paths=extra)

        paths = service._get_all_paths()

        # Should include standard paths + extra
        assert Path("ciris_adapters") in paths
        assert Path.home() / ".ciris" / "adapters" in paths
        assert Path(".ciris") / "adapters" in paths
        assert Path("/custom") in paths

    def test_discover_adapters_empty_when_no_loaders(self) -> None:
        """Test discover_adapters returns empty when no paths exist."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        manifests = service.discover_adapters()

        assert manifests == []

    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    def test_discover_adapters_finds_manifests(self, mock_loader_class) -> None:
        """Test discover_adapters finds manifests from loaders."""
        # Setup mock loader
        mock_loader = MagicMock()
        mock_loader.discover_services.return_value = [
            create_mock_manifest("adapter1"),
            create_mock_manifest("adapter2"),
        ]
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        manifests = service.discover_adapters()

        assert len(manifests) >= 2  # May have duplicates from multiple paths
        names = [m.module.name for m in manifests]
        assert "adapter1" in names
        assert "adapter2" in names

    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    def test_discover_adapters_deduplicates(self, mock_loader_class) -> None:
        """Test discover_adapters skips duplicate adapter names."""
        # Setup mock loaders that return duplicates
        mock_loader = MagicMock()
        mock_loader.discover_services.return_value = [
            create_mock_manifest("adapter1"),
            create_mock_manifest("adapter1"),  # Duplicate
        ]
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        manifests = service.discover_adapters()

        # Should deduplicate across all loaders
        names = [m.module.name for m in manifests]
        assert names.count("adapter1") == 1

    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    def test_get_eligible_adapters_excludes_disabled(self, mock_loader_class) -> None:
        """Test get_eligible_adapters excludes disabled adapters."""
        mock_loader = MagicMock()
        mock_loader.discover_services.return_value = [
            create_mock_manifest("enabled_adapter"),
            create_mock_manifest("disabled_adapter"),
        ]
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        eligible = service.get_eligible_adapters(disabled_adapters=["disabled_adapter"])

        names = [m.module.name for m in eligible]
        assert "enabled_adapter" in names
        assert "disabled_adapter" not in names

    def test_check_tool_eligibility_delegates(self) -> None:
        """Test check_tool_eligibility delegates to checker."""
        mock_checker = MagicMock(spec=ToolEligibilityChecker)
        mock_checker.check_eligibility.return_value = EligibilityResult(eligible=True)

        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService(eligibility_checker=mock_checker)

        tool = make_tool_info(name="test", description="test")
        result = service.check_tool_eligibility(tool)

        mock_checker.check_eligibility.assert_called_once_with(tool)
        assert result.eligible is True

    def test_filter_eligible_tools_delegates(self) -> None:
        """Test filter_eligible_tools delegates to checker."""
        mock_checker = MagicMock(spec=ToolEligibilityChecker)
        tools = [make_tool_info(name="test1", description="test1")]
        mock_checker.filter_eligible_tools.return_value = tools

        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService(eligibility_checker=mock_checker)

        result = service.filter_eligible_tools(tools)

        mock_checker.filter_eligible_tools.assert_called_once_with(tools)
        assert result == tools

    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    def test_load_service_class_uses_cached_loader(self, mock_loader_class) -> None:
        """Test load_service_class uses the cached loader for manifest."""
        mock_loader = MagicMock()
        manifest = create_mock_manifest("test_adapter")
        mock_loader.discover_services.return_value = [manifest]
        mock_loader.load_service_class.return_value = object
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        # First discover to populate cache
        service.discover_adapters()

        # Then load class
        cls = service.load_service_class(manifest, "test.path")

        mock_loader.load_service_class.assert_called_with(manifest, "test.path")

    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    def test_load_service_class_tries_all_loaders_if_not_cached(self, mock_loader_class) -> None:
        """Test load_service_class tries all loaders if manifest not in cache."""
        mock_loader = MagicMock()
        mock_loader.discover_services.return_value = []
        mock_loader.load_service_class.return_value = object
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        # Don't discover, just try to load
        manifest = create_mock_manifest("unknown_adapter")
        cls = service.load_service_class(manifest, "test.path")

        # Should have tried the loader
        assert mock_loader.load_service_class.called


class TestAdapterDiscoveryServiceAsync:
    """Async tests for AdapterDiscoveryService."""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    async def test_load_eligible_adapters_skips_disabled(self, mock_loader_class) -> None:
        """Test load_eligible_adapters skips disabled adapters."""
        mock_loader = MagicMock()
        mock_loader.discover_services.return_value = [
            create_mock_manifest("enabled"),
            create_mock_manifest("disabled"),
        ]
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        result = await service.load_eligible_adapters(disabled_adapters=["disabled"])

        # Disabled should not be in result
        assert "disabled" not in result

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    async def test_load_eligible_adapters_checks_eligibility(self, mock_loader_class) -> None:
        """Test load_eligible_adapters checks tool eligibility."""
        # Setup mock
        mock_loader = MagicMock()
        manifest = create_mock_manifest("tool_adapter")
        mock_loader.discover_services.return_value = [manifest]

        # Mock service class
        mock_service = MagicMock()
        mock_service.get_all_tool_info = AsyncMock(return_value=[make_tool_info(name="tool1", description="test")])
        mock_loader.load_service_class.return_value = lambda **kwargs: mock_service
        mock_loader_class.return_value = mock_loader

        # Mock eligibility checker to return eligible
        mock_checker = MagicMock()
        mock_checker.check_eligibility.return_value = EligibilityResult(eligible=True)

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService(eligibility_checker=mock_checker)

        result = await service.load_eligible_adapters()

        # Should have checked eligibility
        assert mock_checker.check_eligibility.called

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    async def test_load_eligible_adapters_excludes_ineligible(self, mock_loader_class) -> None:
        """Test load_eligible_adapters excludes ineligible tools."""
        mock_loader = MagicMock()
        manifest = create_mock_manifest("ineligible_adapter")
        mock_loader.discover_services.return_value = [manifest]

        # Mock service with tools
        mock_service = MagicMock()
        mock_service.get_all_tool_info = AsyncMock(return_value=[make_tool_info(name="tool1", description="test")])
        mock_loader.load_service_class.return_value = lambda **kwargs: mock_service
        mock_loader_class.return_value = mock_loader

        # Mock checker to return ineligible
        mock_checker = MagicMock()
        mock_checker.check_eligibility.return_value = EligibilityResult(eligible=False, reason="missing binary")

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService(eligibility_checker=mock_checker)

        result = await service.load_eligible_adapters()

        # Should not include ineligible adapter
        assert "ineligible_adapter" not in result

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    async def test_load_eligible_adapters_handles_no_tool_info(self, mock_loader_class) -> None:
        """Test load_eligible_adapters handles services without get_all_tool_info."""
        mock_loader = MagicMock()
        manifest = create_mock_manifest("non_tool_adapter")
        mock_loader.discover_services.return_value = [manifest]

        # Mock service without get_all_tool_info
        mock_service = MagicMock(spec=[])  # No methods
        mock_loader.load_service_class.return_value = lambda **kwargs: mock_service
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        result = await service.load_eligible_adapters()

        # Non-tool services are assumed eligible
        assert "non_tool_adapter" in result

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    async def test_load_eligible_adapters_handles_empty_tools(self, mock_loader_class) -> None:
        """Test load_eligible_adapters handles services with no tools."""
        mock_loader = MagicMock()
        manifest = create_mock_manifest("empty_adapter")
        mock_loader.discover_services.return_value = [manifest]

        # Mock service with empty tools
        mock_service = MagicMock()
        mock_service.get_all_tool_info = AsyncMock(return_value=[])
        mock_loader.load_service_class.return_value = lambda **kwargs: mock_service
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        result = await service.load_eligible_adapters()

        # Services with no tools are eligible
        assert "empty_adapter" in result

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    async def test_load_eligible_adapters_handles_instantiation_error(self, mock_loader_class) -> None:
        """Test load_eligible_adapters handles service instantiation errors."""
        mock_loader = MagicMock()
        manifest = create_mock_manifest("error_adapter")
        mock_loader.discover_services.return_value = [manifest]

        # Mock service class that raises on instantiation
        def raise_error(**kwargs):
            raise RuntimeError("Cannot instantiate")

        mock_loader.load_service_class.return_value = raise_error
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        result = await service.load_eligible_adapters()

        # Should gracefully exclude erroring adapter
        assert "error_adapter" not in result


class TestDiscoveryServiceHelpers:
    """Tests for the extracted helper methods in AdapterDiscoveryService."""

    def test_build_eligibility_reason_missing_binaries(self) -> None:
        """Test _build_eligibility_reason with missing binaries."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        result = EligibilityResult(
            eligible=False,
            missing_binaries=["ffmpeg", "ffprobe"],
        )
        reason = service._build_eligibility_reason(result)
        assert "missing binaries: ffmpeg, ffprobe" in reason or "missing binaries: ffprobe, ffmpeg" in reason

    def test_build_eligibility_reason_missing_env_vars(self) -> None:
        """Test _build_eligibility_reason with missing env vars."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        result = EligibilityResult(
            eligible=False,
            missing_env_vars=["API_KEY", "SECRET"],
        )
        reason = service._build_eligibility_reason(result)
        assert "missing env vars" in reason

    def test_build_eligibility_reason_platform_mismatch(self) -> None:
        """Test _build_eligibility_reason with platform mismatch."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        result = EligibilityResult(
            eligible=False,
            platform_mismatch=True,
        )
        reason = service._build_eligibility_reason(result)
        assert "platform not supported" in reason

    def test_build_eligibility_reason_multiple_issues(self) -> None:
        """Test _build_eligibility_reason with multiple issues."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        result = EligibilityResult(
            eligible=False,
            missing_binaries=["ffmpeg"],
            missing_config=["some_config"],
        )
        reason = service._build_eligibility_reason(result)
        assert "missing binaries" in reason
        assert "missing config" in reason

    def test_build_eligibility_reason_empty(self) -> None:
        """Test _build_eligibility_reason with no issues returns unknown."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        result = EligibilityResult(eligible=False)
        reason = service._build_eligibility_reason(result)
        assert reason == "unknown"

    def test_check_tools_eligibility_all_eligible(self) -> None:
        """Test _check_tools_eligibility when all tools are eligible."""
        mock_checker = MagicMock()
        mock_checker.check_eligibility.return_value = EligibilityResult(eligible=True)

        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService(eligibility_checker=mock_checker)

        tools = [make_tool_info("tool1", "test"), make_tool_info("tool2", "test")]
        result = service._check_tools_eligibility(tools)

        assert result.eligible is True
        assert result.missing_binaries == []

    def test_check_tools_eligibility_some_ineligible(self) -> None:
        """Test _check_tools_eligibility when some tools are ineligible."""
        mock_checker = MagicMock()
        mock_checker.check_eligibility.side_effect = [
            EligibilityResult(eligible=True),
            EligibilityResult(eligible=False, missing_binaries=["ffmpeg"]),
        ]

        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService(eligibility_checker=mock_checker)

        tools = [make_tool_info("tool1", "test"), make_tool_info("tool2", "test")]
        result = service._check_tools_eligibility(tools)

        assert result.eligible is False
        assert "ffmpeg" in result.missing_binaries

    def test_get_adapter_source_info_with_loader(self) -> None:
        """Test _get_adapter_source_info with cached loader."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        # Mock a cached loader
        mock_loader = MagicMock()
        mock_loader.services_dir = Path("/path/to/ciris_adapters/test")
        service._manifest_loaders["test_adapter"] = mock_loader

        source_path, is_builtin = service._get_adapter_source_info("test_adapter")

        assert source_path == "/path/to/ciris_adapters/test"
        assert is_builtin is True

    def test_get_adapter_source_info_no_loader(self) -> None:
        """Test _get_adapter_source_info without cached loader."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        source_path, is_builtin = service._get_adapter_source_info("unknown_adapter")

        assert source_path is None
        assert is_builtin is False

    @pytest.mark.asyncio
    async def test_get_service_tools_with_tool_info(self) -> None:
        """Test _get_service_tools with service that has tool info."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        mock_service = MagicMock()
        expected_tools = [make_tool_info("tool1", "test")]
        mock_service.get_all_tool_info = AsyncMock(return_value=expected_tools)

        tools = await service._get_service_tools(mock_service)

        assert tools == expected_tools

    @pytest.mark.asyncio
    async def test_get_service_tools_no_method(self) -> None:
        """Test _get_service_tools with service without get_all_tool_info."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        mock_service = MagicMock(spec=[])  # No methods

        tools = await service._get_service_tools(mock_service)

        assert tools == []

    @pytest.mark.asyncio
    async def test_get_service_tools_exception(self) -> None:
        """Test _get_service_tools handles exceptions gracefully."""
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "is_dir", return_value=False):
                service = AdapterDiscoveryService()

        mock_service = MagicMock()
        mock_service.get_all_tool_info = AsyncMock(side_effect=RuntimeError("Failed"))

        tools = await service._get_service_tools(mock_service)

        assert tools == []

    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    def test_find_manifest_by_name_found(self, mock_loader_class) -> None:
        """Test _find_manifest_by_name when manifest exists."""
        mock_loader = MagicMock()
        manifest = create_mock_manifest("test_adapter")
        mock_loader.discover_services.return_value = [manifest]
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        result = service._find_manifest_by_name("test_adapter")

        assert result == manifest

    @patch("ciris_engine.logic.services.tool.discovery_service.AdapterLoader")
    def test_find_manifest_by_name_not_found(self, mock_loader_class) -> None:
        """Test _find_manifest_by_name when manifest does not exist."""
        mock_loader = MagicMock()
        mock_loader.discover_services.return_value = [create_mock_manifest("other")]
        mock_loader_class.return_value = mock_loader

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "is_dir", return_value=True):
                service = AdapterDiscoveryService()

        result = service._find_manifest_by_name("nonexistent")

        assert result is None
