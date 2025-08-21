"""
Comprehensive tests for ModularServiceLoader.

Tests dynamic service discovery, loading, and initialization using proper Pydantic schemas.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.runtime.modular_service_loader import ModularServiceLoader
from ciris_engine.protocols.services import ServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.manifest import (
    ConfigurationParameter,
    LegacyDependencies,
    ModuleInfo,
    ModuleLoadResult,
    ServiceDeclaration,
    ServiceManifest,
    ServiceMetadata,
    ServicePriority,
)


class MockService(ServiceProtocol):
    """Mock service for testing."""

    def __init__(self, **kwargs):
        self.config = kwargs
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "healthy", "started": self.started}

    def get_service_type(self) -> ServiceType:
        return ServiceType.LLM

    def get_capabilities(self) -> List[str]:
        return ["test_capability"]

    def get_status(self) -> str:
        return "healthy" if self.started else "stopped"

    def is_healthy(self) -> bool:
        return self.started


@pytest.fixture
def temp_services_dir(tmp_path):
    """Create temporary services directory structure."""
    services_dir = tmp_path / "ciris_modular_services"
    services_dir.mkdir()
    return services_dir


@pytest.fixture
def valid_manifest():
    """Create a valid ServiceManifest using proper schemas."""
    return ServiceManifest(
        module=ModuleInfo(
            name="test_service",
            version="1.0.0",
            description="Test service for unit tests",
            author="Test Author",
            is_mock=False,
        ),
        services=[
            ServiceDeclaration(
                type=ServiceType.LLM,
                class_path="test_service.MockService",
                priority=ServicePriority.NORMAL,
                capabilities=["test_capability"],
            )
        ],
        dependencies=LegacyDependencies(
            protocols=["ciris_engine.protocols.services.ServiceProtocol"],
            schemas=["ciris_engine.schemas.runtime.manifest"],
        ),
        configuration={
            "api_key": ConfigurationParameter(type="string", description="API key for service", default="test_key"),
            "timeout": ConfigurationParameter(type="integer", description="Request timeout", default=30),
        },
        capabilities=["test_capability", "mock_responses"],
    )


@pytest.fixture
def mock_manifest():
    """Create a mock service manifest."""
    return ServiceManifest(
        module=ModuleInfo(
            name="mock_service", version="0.1.0", description="Mock service for testing", author="Test", is_mock=True
        ),
        services=[
            ServiceDeclaration(
                type=ServiceType.LLM,
                class_path="mock_service.MockService",
                priority=ServicePriority.LOW,
                capabilities=["mock"],
            )
        ],
    )


@pytest.fixture
def invalid_manifest():
    """Create an invalid manifest missing required fields."""
    return {
        "module": {
            "name": "invalid_service"
            # Missing required fields
        }
    }


@pytest.fixture
def service_with_manifest(temp_services_dir, valid_manifest):
    """Create a service directory with manifest."""
    service_dir = temp_services_dir / "test_service"
    service_dir.mkdir()

    manifest_path = service_dir / "manifest.json"
    manifest_path.write_text(valid_manifest.model_dump_json())

    # Create a simple Python module
    init_file = service_dir / "__init__.py"
    init_file.write_text(
        "from ciris_engine.logic.runtime.test_modular_service_loader import MockService\n" "__all__ = ['MockService']"
    )

    return service_dir


class TestModularServiceLoader:
    """Test suite for ModularServiceLoader."""

    def test_initialization(self, temp_services_dir):
        """Test loader initialization with custom directory."""
        loader = ModularServiceLoader(services_dir=temp_services_dir)
        assert loader.services_dir == temp_services_dir
        assert loader.loaded_services == {}

    def test_initialization_default_dir(self):
        """Test loader initialization with default directory."""
        loader = ModularServiceLoader()
        assert loader.services_dir == Path("ciris_modular_services")
        assert loader.loaded_services == {}

    def test_discover_services_empty_dir(self, temp_services_dir):
        """Test service discovery with empty directory."""
        loader = ModularServiceLoader(services_dir=temp_services_dir)
        services = loader.discover_services()
        assert services == []

    def test_discover_services_no_dir(self, tmp_path):
        """Test service discovery when directory doesn't exist."""
        non_existent = tmp_path / "non_existent"
        loader = ModularServiceLoader(services_dir=non_existent)
        services = loader.discover_services()
        assert services == []

    def test_discover_services_with_manifest(self, service_with_manifest, temp_services_dir):
        """Test discovering service with valid manifest."""
        loader = ModularServiceLoader(services_dir=temp_services_dir)
        services = loader.discover_services()

        assert len(services) == 1
        manifest = services[0]
        assert isinstance(manifest, ServiceManifest)
        assert manifest.module.name == "test_service"
        assert manifest.module.version == "1.0.0"
        assert hasattr(manifest, "_path")

    def test_discover_services_skip_underscore_dirs(self, temp_services_dir):
        """Test that directories starting with underscore are skipped."""
        # Create underscore directory
        skip_dir = temp_services_dir / "_skip_this"
        skip_dir.mkdir()
        (skip_dir / "manifest.json").write_text("{}")

        # Create valid directory
        valid_dir = temp_services_dir / "valid_service"
        valid_dir.mkdir()
        manifest = ServiceManifest(
            module=ModuleInfo(name="valid_service", version="1.0.0", description="Valid", author="Test"),
            services=[
                ServiceDeclaration(type=ServiceType.LLM, class_path="valid.Service", priority=ServicePriority.NORMAL)
            ],
        )
        (valid_dir / "manifest.json").write_text(manifest.model_dump_json())

        loader = ModularServiceLoader(services_dir=temp_services_dir)
        services = loader.discover_services()

        assert len(services) == 1
        assert services[0].module.name == "valid_service"

    def test_discover_services_invalid_manifest(self, temp_services_dir, invalid_manifest):
        """Test handling of invalid manifest during discovery."""
        service_dir = temp_services_dir / "invalid_service"
        service_dir.mkdir()
        (service_dir / "manifest.json").write_text(json.dumps(invalid_manifest))

        loader = ModularServiceLoader(services_dir=temp_services_dir)
        with patch("ciris_engine.logic.runtime.modular_service_loader.logger") as mock_logger:
            services = loader.discover_services()
            assert services == []

    def test_validate_manifest_valid(self, valid_manifest):
        """Test validation of valid manifest."""
        loader = ModularServiceLoader()
        assert loader.validate_manifest(valid_manifest) is True

    def test_validate_manifest_with_errors(self, valid_manifest):
        """Test validation of manifest with errors."""
        loader = ModularServiceLoader()

        # Mock the validate_manifest method to return errors
        with patch.object(ServiceManifest, "validate_manifest", return_value=["Error 1", "Error 2"]):
            with patch("ciris_engine.logic.runtime.modular_service_loader.logger") as mock_logger:
                result = loader.validate_manifest(valid_manifest)
                assert result is False
                assert mock_logger.error.call_count == 2

    def test_check_dependencies_no_deps(self, mock_manifest):
        """Test dependency check with no dependencies."""
        loader = ModularServiceLoader()
        mock_manifest.dependencies = None
        assert loader.check_dependencies(mock_manifest) is True

    def test_check_dependencies_valid(self, valid_manifest):
        """Test dependency check with valid dependencies."""
        loader = ModularServiceLoader()

        # Mock importlib to simulate successful imports
        with patch("ciris_engine.logic.runtime.modular_service_loader.importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.ServiceProtocol = MagicMock()
            mock_import.return_value = mock_module

            assert loader.check_dependencies(valid_manifest) is True

    def test_check_dependencies_missing_protocol(self, valid_manifest):
        """Test dependency check with missing protocol."""
        loader = ModularServiceLoader()

        with patch("ciris_engine.logic.runtime.modular_service_loader.importlib.import_module") as mock_import:
            mock_module = MagicMock(spec=[])  # Empty spec means no attributes
            mock_import.return_value = mock_module

            result = loader.check_dependencies(valid_manifest)
            assert result is False

    def test_check_dependencies_import_error(self, valid_manifest):
        """Test dependency check with import error."""
        loader = ModularServiceLoader()

        with patch("ciris_engine.logic.runtime.modular_service_loader.importlib.import_module") as mock_import:
            mock_import.side_effect = ImportError("Module not found")

            result = loader.check_dependencies(valid_manifest)
            assert result is False

    def test_load_service_invalid_manifest(self, valid_manifest):
        """Test loading service with invalid manifest."""
        loader = ModularServiceLoader()

        with patch.object(loader, "validate_manifest", return_value=False):
            result = loader.load_service(valid_manifest)
            assert result is None

    def test_load_service_failed_dependencies(self, valid_manifest):
        """Test loading service with failed dependencies."""
        loader = ModularServiceLoader()

        with patch.object(loader, "check_dependencies", return_value=False):
            result = loader.load_service(valid_manifest)
            assert result is None

    def test_load_service_missing_path(self, valid_manifest):
        """Test loading service without path information."""
        loader = ModularServiceLoader()

        # Don't set _path attribute
        result = loader.load_service(valid_manifest)
        assert result is None

    def test_load_service_success(self, valid_manifest, temp_services_dir):
        """Test successful service loading."""
        loader = ModularServiceLoader(services_dir=temp_services_dir)
        setattr(valid_manifest, "_path", temp_services_dir / "test_service")

        with patch("ciris_engine.logic.runtime.modular_service_loader.importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.MockService = MockService
            mock_import.return_value = mock_module

            result = loader.load_service(valid_manifest)

            assert result == MockService
            assert "test_service" in loader.loaded_services

            metadata = loader.loaded_services["test_service"]
            assert isinstance(metadata, ServiceMetadata)
            assert metadata.module_name == "test_service"
            assert metadata.version == "1.0.0"
            assert metadata.capabilities == ["test_capability", "mock_responses"]
            assert metadata.health_status == "loaded"

    def test_load_service_legacy_format(self, temp_services_dir):
        """Test loading service with legacy manifest format."""
        manifest = ServiceManifest(
            module=ModuleInfo(name="legacy_service", version="0.5.0", description="Legacy format", author="Test"),
            services=[],  # Empty services list
            exports={"service_class": "legacy.LegacyService"},  # Legacy format
        )

        loader = ModularServiceLoader(services_dir=temp_services_dir)
        setattr(manifest, "_path", temp_services_dir / "legacy_service")

        with patch("ciris_engine.logic.runtime.modular_service_loader.importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.LegacyService = MockService
            mock_import.return_value = mock_module

            result = loader.load_service(manifest)
            assert result == MockService

    def test_load_service_no_class_path(self, temp_services_dir):
        """Test loading service without class path."""
        manifest = ServiceManifest(
            module=ModuleInfo(name="no_class", version="1.0.0", description="No class path", author="Test"),
            services=[],  # No services defined
        )

        loader = ModularServiceLoader(services_dir=temp_services_dir)
        setattr(manifest, "_path", temp_services_dir / "no_class")

        result = loader.load_service(manifest)
        assert result is None

    def test_load_service_import_error(self, valid_manifest, temp_services_dir):
        """Test handling import error during service loading."""
        loader = ModularServiceLoader(services_dir=temp_services_dir)
        setattr(valid_manifest, "_path", temp_services_dir / "test_service")

        with patch("ciris_engine.logic.runtime.modular_service_loader.importlib.import_module") as mock_import:
            mock_import.side_effect = ImportError("Cannot import module")

            result = loader.load_service(valid_manifest)
            assert result is None

    def test_get_service_metadata(self, valid_manifest):
        """Test getting metadata for loaded service."""
        loader = ModularServiceLoader()

        # Add metadata
        metadata = ServiceMetadata(
            service_type=ServiceType.LLM,
            module_name="test_service",
            class_name="MockService",
            version="1.0.0",
            is_mock=False,
            capabilities=["test"],
            priority=ServicePriority.NORMAL,
            health_status="loaded",
        )
        loader.loaded_services["test_service"] = metadata

        result = loader.get_service_metadata("test_service")
        assert result == metadata

        # Test non-existent service
        assert loader.get_service_metadata("non_existent") is None

    @pytest.mark.asyncio
    async def test_initialize_modular_services_empty(self, temp_services_dir):
        """Test initialization with no services."""
        loader = ModularServiceLoader(services_dir=temp_services_dir)
        mock_registry = MagicMock()
        mock_config = MagicMock()

        result = await loader.initialize_modular_services(mock_registry, mock_config)

        assert isinstance(result, ModuleLoadResult)
        assert result.module_name == "modular_services"
        assert result.success is True
        assert result.services_loaded == []
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_initialize_modular_services_skip_mock_in_production(self, temp_services_dir, mock_manifest):
        """Test that mock services are skipped in production mode."""
        # Create mock service directory
        service_dir = temp_services_dir / "mock_service"
        service_dir.mkdir()
        (service_dir / "manifest.json").write_text(mock_manifest.model_dump_json())

        loader = ModularServiceLoader(services_dir=temp_services_dir)
        mock_registry = MagicMock()
        mock_config = MagicMock()
        mock_config.mock_llm = False  # Production mode

        result = await loader.initialize_modular_services(mock_registry, mock_config)

        assert result.success is True
        assert len(result.warnings) == 1
        assert "Skipping mock service in production" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_initialize_modular_services_success(self, temp_services_dir, valid_manifest):
        """Test successful service initialization and registration."""
        # Create service directory
        service_dir = temp_services_dir / "test_service"
        service_dir.mkdir()
        (service_dir / "manifest.json").write_text(valid_manifest.model_dump_json())

        loader = ModularServiceLoader(services_dir=temp_services_dir)
        mock_registry = MagicMock()
        mock_config = MagicMock()
        mock_config.mock_llm = False

        # Mock the load_service method and populate loaded_services
        def mock_load_service(manifest):
            # Simulate what load_service does - populate loaded_services
            loader.loaded_services[manifest.module.name] = ServiceMetadata(
                service_type=ServiceType.LLM,
                module_name=manifest.module.name,
                class_name="MockService",
                version=manifest.module.version,
                is_mock=False,
                capabilities=manifest.capabilities or [],
                priority=ServicePriority.NORMAL,
                health_status="loaded",
            )
            return MockService

        with patch.object(loader, "load_service", side_effect=mock_load_service):
            result = await loader.initialize_modular_services(mock_registry, mock_config)

            assert result.success is True
            assert len(result.services_loaded) == 1

            service_meta = result.services_loaded[0]
            assert service_meta.module_name == "test_service"
            assert service_meta.health_status == "started"

            # Verify service was registered
            mock_registry.register_global.assert_called_once()
            call_args = mock_registry.register_global.call_args
            assert call_args.kwargs["service_type"] == ServiceType.LLM
            assert call_args.kwargs["priority"] == ServicePriority.NORMAL
            assert "test_capability" in call_args.kwargs["capabilities"]

    @pytest.mark.asyncio
    async def test_initialize_modular_services_init_error(self, temp_services_dir, valid_manifest):
        """Test handling of initialization errors."""
        # Create service directory
        service_dir = temp_services_dir / "test_service"
        service_dir.mkdir()
        (service_dir / "manifest.json").write_text(valid_manifest.model_dump_json())

        loader = ModularServiceLoader(services_dir=temp_services_dir)
        mock_registry = MagicMock()
        mock_config = MagicMock()

        # Mock load_service to return a class that fails on instantiation
        with patch.object(loader, "load_service") as mock_load:
            mock_class = MagicMock()
            mock_class.side_effect = Exception("Initialization failed")
            mock_load.return_value = mock_class

            result = await loader.initialize_modular_services(mock_registry, mock_config)

            assert result.success is False
            assert len(result.errors) == 1
            assert "Failed to initialize test_service" in result.errors[0]

    @pytest.mark.asyncio
    async def test_initialize_modular_services_with_configuration(self, temp_services_dir, valid_manifest):
        """Test service initialization with configuration parameters."""
        # Create service directory
        service_dir = temp_services_dir / "test_service"
        service_dir.mkdir()
        (service_dir / "manifest.json").write_text(valid_manifest.model_dump_json())

        loader = ModularServiceLoader(services_dir=temp_services_dir)
        mock_registry = MagicMock()
        mock_config = MagicMock()

        # Track what config was passed to service
        captured_config = {}

        def mock_service_init(**kwargs):
            captured_config.update(kwargs)
            instance = MagicMock()
            instance.start = AsyncMock()
            return instance

        mock_service_class = MagicMock(side_effect=mock_service_init)

        def mock_load_with_metadata(manifest):
            # Populate loaded_services like real load_service does
            loader.loaded_services[manifest.module.name] = ServiceMetadata(
                service_type=ServiceType.LLM,
                module_name=manifest.module.name,
                class_name="MockService",
                version=manifest.module.version,
                is_mock=False,
                capabilities=manifest.capabilities or [],
                priority=ServicePriority.NORMAL,
                health_status="loaded",
            )
            return mock_service_class

        with patch.object(loader, "load_service", side_effect=mock_load_with_metadata):
            result = await loader.initialize_modular_services(mock_registry, mock_config)

            assert result.success is True
            # Verify default configuration values were passed
            assert captured_config["api_key"] == "test_key"
            assert captured_config["timeout"] == 30

    def test_sys_path_cleanup_on_error(self, valid_manifest, temp_services_dir):
        """Test that sys.path is cleaned up even on error."""
        loader = ModularServiceLoader(services_dir=temp_services_dir)
        setattr(valid_manifest, "_path", temp_services_dir / "test_service")

        original_path = sys.path.copy()

        # We need to patch check_dependencies to pass, then make the actual import fail
        with patch.object(loader, "check_dependencies", return_value=True):
            with patch("ciris_engine.logic.runtime.modular_service_loader.importlib.import_module") as mock_import:
                mock_import.side_effect = Exception("Import failed")

                loader.load_service(valid_manifest)

                # Verify sys.path was restored
                assert sys.path == original_path

    def test_sys_path_cleanup_on_success(self, valid_manifest, temp_services_dir):
        """Test that sys.path is cleaned up after successful load."""
        loader = ModularServiceLoader(services_dir=temp_services_dir)
        setattr(valid_manifest, "_path", temp_services_dir / "test_service")

        original_path = sys.path.copy()

        with patch("ciris_engine.logic.runtime.modular_service_loader.importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.MockService = MockService
            mock_import.return_value = mock_module

            loader.load_service(valid_manifest)

            # Verify sys.path was restored
            assert sys.path == original_path
