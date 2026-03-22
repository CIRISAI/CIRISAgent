"""
Comprehensive tests for _adapter_discovery.py module.

Covers:
- check_platform_requirements_satisfied() - Platform requirement checks
- check_external_dependencies() - CLI dependency checks
- should_filter_adapter() - All filtering rules
- extract_service_types() - Service type extraction
- parse_config_parameters() - Configuration parsing
- parse_manifest_to_module_info() - Full manifest parsing
- get_core_adapter_info() - Core adapter info generation
- try_load_service_manifest() - Manifest loading
- read_manifest_async() - Async manifest reading
- discover_services_from_directory() - Directory-based discovery
- discover_services_via_entry_points() - Entry point discovery
- discover_adapters() - Main discovery function
- get_cli_dependency_status() - CLI status checking
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.routes._adapter_discovery import (
    ADAPTER_ENTRY_POINT_GROUP,
    CAP_COMM_FETCH_MESSAGES,
    CAP_COMM_SEND_MESSAGE,
    COMM_CAPABILITIES,
    MANIFEST_FILENAME,
    check_external_dependencies,
    check_platform_requirements_satisfied,
    discover_adapters,
    discover_services_from_directory,
    discover_services_via_entry_points,
    extract_service_types,
    get_cli_dependency_status,
    get_core_adapter_info,
    parse_config_parameters,
    parse_manifest_to_module_info,
    read_manifest_async,
    should_filter_adapter,
    try_load_service_manifest,
)
from ciris_engine.schemas.runtime.adapter_management import ModuleConfigParameter, ModuleTypeInfo


class TestConstants:
    """Test module-level constants."""

    def test_adapter_entry_point_group(self):
        assert ADAPTER_ENTRY_POINT_GROUP == "ciris.adapters"

    def test_manifest_filename(self):
        assert MANIFEST_FILENAME == "manifest.json"

    def test_communication_capabilities(self):
        assert CAP_COMM_SEND_MESSAGE == "communication:send_message"
        assert CAP_COMM_FETCH_MESSAGES == "communication:fetch_messages"
        assert COMM_CAPABILITIES == [CAP_COMM_SEND_MESSAGE, CAP_COMM_FETCH_MESSAGES]


class TestCheckPlatformRequirementsSatisfied:
    """Test check_platform_requirements_satisfied function."""

    def test_empty_requirements_returns_true(self):
        """No requirements means always satisfied."""
        assert check_platform_requirements_satisfied([]) is True

    def test_none_requirements_returns_true(self):
        """None/falsy requirements treated as empty."""
        assert check_platform_requirements_satisfied(None) is True  # type: ignore

    def test_satisfied_requirements(self):
        """Test when platform satisfies requirements."""
        with patch("ciris_engine.logic.utils.platform_detection.detect_platform_capabilities") as mock_detect:
            mock_caps = MagicMock()
            mock_caps.satisfies.return_value = True
            mock_detect.return_value = mock_caps

            result = check_platform_requirements_satisfied(["desktop_cli"])
            assert result is True

    def test_unsatisfied_requirements(self):
        """Test when platform doesn't satisfy requirements."""
        with patch("ciris_engine.logic.utils.platform_detection.detect_platform_capabilities") as mock_detect:
            mock_caps = MagicMock()
            mock_caps.satisfies.return_value = False
            mock_detect.return_value = mock_caps

            result = check_platform_requirements_satisfied(["android_play_integrity"])
            assert result is False

    def test_unknown_requirement_skipped(self):
        """Unknown requirements should be skipped, not cause failure."""
        with patch("ciris_engine.logic.utils.platform_detection.detect_platform_capabilities") as mock_detect:
            mock_caps = MagicMock()
            mock_caps.satisfies.return_value = True
            mock_detect.return_value = mock_caps

            # Unknown requirement should be skipped (ValueError caught)
            result = check_platform_requirements_satisfied(["unknown_requirement_xyz"])
            assert result is True

    def test_exception_returns_false(self):
        """Exceptions during detection should return False."""
        with patch("ciris_engine.logic.utils.platform_detection.detect_platform_capabilities") as mock_detect:
            mock_detect.side_effect = RuntimeError("Detection failed")

            result = check_platform_requirements_satisfied(["desktop_cli"])
            assert result is False


class TestCheckExternalDependencies:
    """Test check_external_dependencies function."""

    def test_no_dependencies(self):
        """Manifest with no external dependencies."""
        manifest = {"module": {"name": "test"}}
        deps, missing, available = check_external_dependencies(manifest)
        assert deps == []
        assert missing == []
        assert available is True

    def test_external_dependencies_list(self):
        """Test with explicit external_dependencies list."""
        manifest = {
            "module": {"name": "test"},
            "external_dependencies": ["git", "curl"],
        }
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: f"/usr/bin/{x}" if x in ["git", "curl"] else None
            deps, missing, available = check_external_dependencies(manifest)

        assert deps == ["git", "curl"]
        assert missing == []
        assert available is True

    def test_missing_dependencies(self):
        """Test when some dependencies are missing."""
        manifest = {
            "module": {"name": "test"},
            "external_dependencies": ["git", "nonexistent_tool"],
        }
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/git" if x == "git" else None
            deps, missing, available = check_external_dependencies(manifest)

        assert deps == ["git", "nonexistent_tool"]
        assert missing == ["nonexistent_tool"]
        assert available is False

    def test_requires_binaries_capability(self):
        """Test requires:binaries capability adds module name."""
        manifest = {
            "module": {"name": "memo"},
            "capabilities": ["requires:binaries"],
        }
        with patch("shutil.which", return_value=None):
            deps, missing, available = check_external_dependencies(manifest)

        assert "memo" in deps
        assert "memo" in missing
        assert available is False

    def test_requires_binaries_not_duplicate(self):
        """Doesn't duplicate if already in external_dependencies."""
        manifest = {
            "module": {"name": "memo"},
            "capabilities": ["requires:binaries"],
            "external_dependencies": ["memo"],
        }
        with patch("shutil.which", return_value="/usr/bin/memo"):
            deps, missing, available = check_external_dependencies(manifest)

        assert deps.count("memo") == 1

    def test_non_list_external_dependencies_ignored(self):
        """Non-list external_dependencies should be ignored."""
        manifest = {
            "module": {"name": "test"},
            "external_dependencies": "not_a_list",
        }
        deps, missing, available = check_external_dependencies(manifest)
        assert deps == []
        assert available is True


class TestShouldFilterAdapter:
    """Test should_filter_adapter function."""

    def test_basic_valid_adapter_not_filtered(self):
        """Basic valid adapter should not be filtered."""
        manifest = {
            "module": {"name": "my_adapter"},
            "services": [{"type": "TOOL"}],
        }
        assert should_filter_adapter(manifest, filter_by_platform=False) is False

    def test_explicit_skip_adapter(self):
        """Adapter in skip_adapters set should be filtered."""
        manifest = {
            "module": {"name": "skip_me"},
            "services": [{"type": "TOOL"}],
        }
        assert should_filter_adapter(manifest, skip_adapters={"skip_me"}) is True

    def test_mock_adapter_filtered(self):
        """Mock adapters should be filtered."""
        manifest = {
            "module": {"name": "test", "MOCK": True},
            "services": [{"type": "TOOL"}],
        }
        assert should_filter_adapter(manifest) is True

        manifest2 = {
            "module": {"name": "test", "is_mock": True},
            "services": [{"type": "TOOL"}],
        }
        assert should_filter_adapter(manifest2) is True

    def test_reference_qa_adapter_filtered(self):
        """Reference/QA adapters should be filtered."""
        manifest = {
            "module": {"name": "test", "reference": True},
            "services": [{"type": "TOOL"}],
        }
        assert should_filter_adapter(manifest) is True

        manifest2 = {
            "module": {"name": "test", "for_qa": True},
            "services": [{"type": "TOOL"}],
        }
        assert should_filter_adapter(manifest2) is True

    def test_library_module_filtered(self):
        """Library modules should be filtered."""
        manifest = {
            "module": {"name": "test"},
            "metadata": {"type": "library"},
            "services": [{"type": "TOOL"}],
        }
        assert should_filter_adapter(manifest) is True

    def test_no_services_filtered(self):
        """Modules with no services should be filtered."""
        manifest = {
            "module": {"name": "test"},
            "services": [],
        }
        assert should_filter_adapter(manifest) is True

    def test_common_module_patterns_filtered(self):
        """Common module name patterns should be filtered."""
        patterns = ["utils_common", "helpers_common_utils", "mycommon"]
        for name in patterns:
            manifest = {
                "module": {"name": name},
                "services": [{"type": "TOOL"}],
            }
            assert should_filter_adapter(manifest) is True, f"Pattern {name} should be filtered"

    def test_internal_only_filtered(self):
        """Internal-only adapters should be filtered."""
        manifest = {
            "module": {"name": "ciris_verify", "internal_only": True},
            "services": [{"type": "TOOL"}],
        }
        assert should_filter_adapter(manifest) is True

    @patch("ciris_engine.logic.adapters.api.routes._adapter_discovery.check_platform_requirements_satisfied")
    def test_platform_requirements_not_met_filtered(self, mock_check):
        """Adapters not meeting platform requirements should be filtered."""
        mock_check.return_value = False
        manifest = {
            "module": {"name": "test"},
            "services": [{"type": "TOOL"}],
            "platform_requirements": ["android_play_integrity"],
        }
        assert should_filter_adapter(manifest, filter_by_platform=True) is True
        mock_check.assert_called_with(["android_play_integrity"])

    def test_platform_filtering_disabled(self):
        """When filter_by_platform=False, platform requirements are ignored."""
        manifest = {
            "module": {"name": "test"},
            "services": [{"type": "TOOL"}],
            "platform_requirements": ["android_play_integrity"],
        }
        # With filter_by_platform=False, platform requirements are not checked
        with patch(
            "ciris_engine.logic.adapters.api.routes._adapter_discovery.check_platform_requirements_satisfied"
        ) as mock_check:
            result = should_filter_adapter(manifest, filter_by_platform=False)
            mock_check.assert_not_called()
            assert result is False


class TestExtractServiceTypes:
    """Test extract_service_types function."""

    def test_empty_services(self):
        """Empty services list returns empty result."""
        assert extract_service_types({"services": []}) == []
        assert extract_service_types({}) == []

    def test_single_service(self):
        """Single service extracts correctly."""
        manifest = {"services": [{"type": "TOOL"}]}
        assert extract_service_types(manifest) == ["TOOL"]

    def test_multiple_services(self):
        """Multiple services extract correctly."""
        manifest = {
            "services": [
                {"type": "COMMUNICATION"},
                {"type": "TOOL"},
                {"type": "RUNTIME_CONTROL"},
            ]
        }
        assert extract_service_types(manifest) == ["COMMUNICATION", "TOOL", "RUNTIME_CONTROL"]

    def test_duplicate_types_deduplicated(self):
        """Duplicate service types are not repeated."""
        manifest = {
            "services": [
                {"type": "TOOL"},
                {"type": "TOOL"},
                {"type": "COMMUNICATION"},
            ]
        }
        result = extract_service_types(manifest)
        assert result == ["TOOL", "COMMUNICATION"]

    def test_empty_type_skipped(self):
        """Services with empty type are skipped."""
        manifest = {
            "services": [
                {"type": ""},
                {"type": "TOOL"},
                {},
            ]
        }
        assert extract_service_types(manifest) == ["TOOL"]


class TestParseConfigParameters:
    """Test parse_config_parameters function."""

    def test_empty_configuration(self):
        """Empty configuration returns empty list."""
        assert parse_config_parameters({}) == []
        assert parse_config_parameters({"configuration": {}}) == []

    def test_basic_parameter(self):
        """Basic parameter parsing."""
        manifest = {
            "configuration": {
                "api_key": {
                    "type": "string",
                    "description": "API key",
                    "required": True,
                }
            }
        }
        params = parse_config_parameters(manifest)
        assert len(params) == 1
        assert params[0].name == "api_key"
        assert params[0].param_type == "string"
        assert params[0].description == "API key"
        assert params[0].required is True

    def test_full_parameter(self):
        """Parameter with all fields."""
        manifest = {
            "configuration": {
                "port": {
                    "type": "integer",
                    "default": 8080,
                    "description": "Server port",
                    "env": "MY_PORT",
                    "required": False,
                    "sensitivity": "LOW",
                }
            }
        }
        params = parse_config_parameters(manifest)
        assert len(params) == 1
        p = params[0]
        assert p.name == "port"
        assert p.param_type == "integer"
        assert p.default == 8080
        assert p.env_var == "MY_PORT"
        assert p.required is False
        assert p.sensitivity == "LOW"

    def test_multiple_parameters(self):
        """Multiple parameters parsed correctly."""
        manifest = {
            "configuration": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
            }
        }
        params = parse_config_parameters(manifest)
        assert len(params) == 2
        names = [p.name for p in params]
        assert "host" in names
        assert "port" in names

    def test_non_dict_parameter_skipped(self):
        """Non-dict parameter values are skipped."""
        manifest = {
            "configuration": {
                "valid": {"type": "string"},
                "invalid": "not_a_dict",
            }
        }
        params = parse_config_parameters(manifest)
        assert len(params) == 1
        assert params[0].name == "valid"


class TestParseManifestToModuleInfo:
    """Test parse_manifest_to_module_info function."""

    def test_minimal_manifest(self):
        """Minimal manifest with required fields."""
        manifest = {
            "module": {"name": "test_adapter"},
        }
        info = parse_manifest_to_module_info(manifest, "test_adapter")

        assert info.module_id == "test_adapter"
        assert info.name == "test_adapter"
        assert info.version == "1.0.0"
        assert info.module_source == "modular"
        assert info.is_mock is False

    def test_full_manifest(self):
        """Full manifest with all optional fields."""
        manifest = {
            "module": {
                "name": "full_adapter",
                "version": "2.0.0",
                "description": "A full adapter",
                "author": "Test Author",
            },
            "services": [{"type": "TOOL"}, {"type": "COMMUNICATION"}],
            "capabilities": ["tool:full", "requires:binaries"],
            "configuration": {"setting": {"type": "string", "default": "value"}},
            "dependencies": {"external": {"requests": ">=2.0"}},
            "cli_dependencies": ["curl"],
            "metadata": {"safe_domain": "test.com", "prohibited": ["medical"]},
            "platform_requirements": ["desktop_cli"],
            "platform_requirements_rationale": "Needs CLI tools",
        }
        info = parse_manifest_to_module_info(manifest, "full_adapter")

        assert info.module_id == "full_adapter"
        assert info.name == "full_adapter"
        assert info.version == "2.0.0"
        assert info.description == "A full adapter"
        assert info.author == "Test Author"
        assert info.service_types == ["TOOL", "COMMUNICATION"]
        assert "tool:full" in info.capabilities
        assert info.requires_external_deps is True
        assert info.cli_dependencies == ["curl"]
        assert info.safe_domain == "test.com"
        assert info.prohibited == ["medical"]
        assert info.platform_requirements == ["desktop_cli"]
        assert info.platform_requirements_rationale == "Needs CLI tools"

    def test_requires_binaries_adds_module_name(self):
        """requires:binaries adds module name to cli_dependencies if empty."""
        manifest = {
            "module": {"name": "memo"},
            "capabilities": ["requires:binaries"],
        }
        info = parse_manifest_to_module_info(manifest, "memo")
        assert "memo" in info.cli_dependencies

    def test_requires_binaries_no_duplicate(self):
        """requires:binaries doesn't duplicate existing cli_dependency."""
        manifest = {
            "module": {"name": "memo"},
            "capabilities": ["requires:binaries"],
            "cli_dependencies": ["memo"],
        }
        info = parse_manifest_to_module_info(manifest, "memo")
        assert info.cli_dependencies.count("memo") == 1

    def test_internal_only_flag(self):
        """internal_only flag is parsed correctly."""
        manifest = {
            "module": {"name": "internal", "internal_only": True},
        }
        info = parse_manifest_to_module_info(manifest, "internal")
        assert info.internal_only is True

    @patch("ciris_engine.logic.adapters.api.routes._adapter_discovery.check_platform_requirements_satisfied")
    def test_platform_available_checked(self, mock_check):
        """platform_available is set based on check_platform_requirements_satisfied."""
        mock_check.return_value = True
        manifest = {
            "module": {"name": "test"},
            "platform_requirements": ["desktop_cli"],
        }
        info = parse_manifest_to_module_info(manifest, "test")
        assert info.platform_available is True
        mock_check.assert_called_with(["desktop_cli"])


class TestGetCoreAdapterInfo:
    """Test get_core_adapter_info function."""

    def test_api_adapter(self):
        """API adapter info is correct."""
        info = get_core_adapter_info("api")

        assert info.module_id == "api"
        assert info.name == "API Adapter"
        assert info.module_source == "core"
        assert "COMMUNICATION" in info.service_types
        assert "TOOL" in info.service_types
        assert info.requires_external_deps is False
        assert len(info.configuration_schema) == 3  # host, port, debug

    def test_cli_adapter(self):
        """CLI adapter info is correct."""
        info = get_core_adapter_info("cli")

        assert info.module_id == "cli"
        assert info.name == "CLI Adapter"
        assert "COMMUNICATION" in info.service_types
        assert len(info.configuration_schema) == 1  # prompt

    def test_discord_adapter(self):
        """Discord adapter info is correct."""
        info = get_core_adapter_info("discord")

        assert info.module_id == "discord"
        assert info.name == "Discord Adapter"
        assert "COMMUNICATION" in info.service_types
        assert "TOOL" in info.service_types
        assert info.requires_external_deps is True
        assert "discord.py" in info.external_dependencies
        assert len(info.configuration_schema) == 3  # token, guild_id, channel_id

    def test_unknown_adapter(self):
        """Unknown adapter type returns default info."""
        info = get_core_adapter_info("unknown_type")

        assert info.module_id == "unknown_type"
        assert info.name == "Unknown_Type"  # Titlecased
        assert info.module_source == "core"
        assert info.service_types == []


class TestTryLoadServiceManifest:
    """Test try_load_service_manifest function."""

    def test_nonexistent_module_returns_none(self):
        """Non-existent module returns None."""
        result = try_load_service_manifest("nonexistent_module_xyz")
        assert result is None

    def test_module_without_path_returns_none(self):
        """Module without __path__ returns None."""
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            del mock_module.__path__  # Remove __path__ attribute
            mock_import.return_value = mock_module

            result = try_load_service_manifest("test_module")
            assert result is None

    def test_module_without_manifest_returns_none(self):
        """Module without manifest.json returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("importlib.import_module") as mock_import:
                mock_module = MagicMock()
                mock_module.__path__ = [tmpdir]
                mock_import.return_value = mock_module

                result = try_load_service_manifest("test_module")
                assert result is None

    def test_valid_manifest_loaded(self):
        """Valid manifest is loaded and parsed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_data = {
                "module": {"name": "test_module", "version": "1.0.0"},
                "services": [{"type": "TOOL"}],
            }
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

            with patch("importlib.import_module") as mock_import:
                mock_module = MagicMock()
                mock_module.__path__ = [tmpdir]
                mock_import.return_value = mock_module

                result = try_load_service_manifest("test_module", filter_by_platform=False)
                assert result is not None
                assert result.name == "test_module"

    def test_filtered_manifest_returns_none(self):
        """Manifest that should be filtered returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_data = {
                "module": {"name": "test_module", "MOCK": True},
                "services": [{"type": "TOOL"}],
            }
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

            with patch("importlib.import_module") as mock_import:
                mock_module = MagicMock()
                mock_module.__path__ = [tmpdir]
                mock_import.return_value = mock_module

                result = try_load_service_manifest("test_module", apply_filter=True)
                assert result is None

    def test_apply_filter_false_skips_filtering(self):
        """With apply_filter=False, filtering is skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_data = {
                "module": {"name": "mock_adapter", "MOCK": True},
                "services": [{"type": "TOOL"}],
            }
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

            with patch("importlib.import_module") as mock_import:
                mock_module = MagicMock()
                mock_module.__path__ = [tmpdir]
                mock_import.return_value = mock_module

                result = try_load_service_manifest("mock_adapter", apply_filter=False)
                assert result is not None
                assert result.is_mock is True


class TestReadManifestAsync:
    """Test read_manifest_async function."""

    @pytest.mark.asyncio
    async def test_valid_manifest(self):
        """Valid manifest file is read and parsed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_data = {"module": {"name": "test"}, "version": "1.0.0"}
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

            result = await read_manifest_async(manifest_path)
            assert result is not None
            assert result["module"]["name"] == "test"

    @pytest.mark.asyncio
    async def test_nonexistent_file(self):
        """Non-existent file returns None."""
        result = await read_manifest_async(Path("/nonexistent/path/manifest.json"))
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        """Invalid JSON returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_path.write_text("not valid json {{{")

            result = await read_manifest_async(manifest_path)
            assert result is None


class TestDiscoverServicesFromDirectory:
    """Test discover_services_from_directory function."""

    @pytest.mark.asyncio
    async def test_empty_directory(self):
        """Empty directory returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await discover_services_from_directory(Path(tmpdir))
            assert result == []

    @pytest.mark.asyncio
    async def test_skips_underscore_dirs(self):
        """Directories starting with _ are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create _private directory
            private_dir = Path(tmpdir) / "_private"
            private_dir.mkdir()
            (private_dir / "manifest.json").write_text(
                json.dumps({"module": {"name": "_private"}, "services": [{"type": "TOOL"}]})
            )

            result = await discover_services_from_directory(Path(tmpdir))
            assert result == []

    @pytest.mark.asyncio
    async def test_skips_files(self):
        """Files (not directories) are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file instead of directory
            (Path(tmpdir) / "not_a_dir.txt").write_text("content")

            result = await discover_services_from_directory(Path(tmpdir))
            assert result == []


class TestDiscoverServicesViaEntryPoints:
    """Test discover_services_via_entry_points function."""

    @pytest.mark.asyncio
    async def test_no_entry_points(self):
        """No entry points returns empty list."""
        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = MagicMock(select=MagicMock(return_value=[]))
            result = await discover_services_via_entry_points()
            assert result == []

    @pytest.mark.asyncio
    async def test_entry_point_discovery(self):
        """Entry points are discovered and loaded."""
        mock_ep = MagicMock()
        mock_ep.name = "test_adapter"

        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_result = MagicMock()
            mock_result.select.return_value = [mock_ep]
            mock_eps.return_value = mock_result

            with patch(
                "ciris_engine.logic.adapters.api.routes._adapter_discovery.try_load_service_manifest"
            ) as mock_load:
                mock_info = MagicMock(spec=ModuleTypeInfo)
                mock_load.return_value = mock_info

                result = await discover_services_via_entry_points()
                assert len(result) == 1
                mock_load.assert_called_with(
                    "test_adapter",
                    apply_filter=True,
                    filter_by_platform=True,
                    skip_adapters=None,
                )

    @pytest.mark.asyncio
    async def test_dict_style_entry_points(self):
        """Dict-style entry points (older Python) are handled."""
        mock_ep = MagicMock()
        mock_ep.name = "test_adapter"

        with patch("importlib.metadata.entry_points") as mock_eps:
            # Return a dict-like structure (older Python style)
            mock_eps.return_value = {ADAPTER_ENTRY_POINT_GROUP: [mock_ep]}

            with patch(
                "ciris_engine.logic.adapters.api.routes._adapter_discovery.try_load_service_manifest"
            ) as mock_load:
                mock_load.return_value = None
                result = await discover_services_via_entry_points()
                assert result == []

    @pytest.mark.asyncio
    async def test_exception_handled(self):
        """Exceptions during discovery are handled gracefully."""
        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.side_effect = RuntimeError("Entry points failed")
            result = await discover_services_via_entry_points()
            assert result == []


class TestDiscoverAdapters:
    """Test discover_adapters function."""

    @pytest.mark.asyncio
    async def test_discovers_adapters_from_ciris_adapters(self):
        """Test that discover_adapters uses ciris_adapters package when available."""
        # This is an integration-style test that just verifies the function runs
        # The actual discovery behavior is tested via discover_services_from_directory
        result = await discover_adapters(filter_by_platform=False)
        # Should return a list (may be empty or have adapters depending on env)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_skip_adapters_parameter(self):
        """Test that skip_adapters parameter is passed through."""
        result = await discover_adapters(filter_by_platform=False, skip_adapters={"nonexistent_adapter"})
        assert isinstance(result, list)


class TestGetCliDependencyStatus:
    """Test get_cli_dependency_status function."""

    def test_no_cli_dependencies(self):
        """Adapter with no CLI dependencies."""
        adapter = MagicMock(spec=ModuleTypeInfo)
        adapter.cli_dependencies = []

        cli_deps, missing, available = get_cli_dependency_status(adapter)
        assert cli_deps == []
        assert missing == []
        assert available is True

    def test_none_cli_dependencies(self):
        """Adapter with None CLI dependencies."""
        adapter = MagicMock(spec=ModuleTypeInfo)
        adapter.cli_dependencies = None

        cli_deps, missing, available = get_cli_dependency_status(adapter)
        assert cli_deps == []
        assert missing == []
        assert available is True

    def test_all_deps_available(self):
        """All CLI dependencies are available."""
        adapter = MagicMock(spec=ModuleTypeInfo)
        adapter.cli_dependencies = ["git", "curl"]

        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: f"/usr/bin/{x}"
            cli_deps, missing, available = get_cli_dependency_status(adapter)

        assert cli_deps == ["git", "curl"]
        assert missing == []
        assert available is True

    def test_some_deps_missing(self):
        """Some CLI dependencies are missing."""
        adapter = MagicMock(spec=ModuleTypeInfo)
        adapter.cli_dependencies = ["git", "nonexistent"]

        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/git" if x == "git" else None
            cli_deps, missing, available = get_cli_dependency_status(adapter)

        assert cli_deps == ["git", "nonexistent"]
        assert missing == ["nonexistent"]
        assert available is False

    def test_all_deps_missing(self):
        """All CLI dependencies are missing."""
        adapter = MagicMock(spec=ModuleTypeInfo)
        adapter.cli_dependencies = ["tool1", "tool2"]

        with patch("shutil.which", return_value=None):
            cli_deps, missing, available = get_cli_dependency_status(adapter)

        assert cli_deps == ["tool1", "tool2"]
        assert missing == ["tool1", "tool2"]
        assert available is False
