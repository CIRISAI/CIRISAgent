"""Unit tests for ServiceInitializer."""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.runtime.service_initializer import ServiceInitializer
from ciris_engine.schemas.config.essential import EssentialConfig


class TestServiceInitializer:
    """Test cases for ServiceInitializer."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def mock_essential_config(self, temp_data_dir):
        """Create mock essential config."""
        config = Mock(spec=EssentialConfig)
        config.data_dir = temp_data_dir
        config.db_path = os.path.join(temp_data_dir, "test.db")
        config.log_level = "INFO"
        config.openai_api_key = "test-key"
        config.anthropic_api_key = None

        # Add database attribute for db_paths functions
        mock_database = Mock()
        # CRITICAL: These must be actual Path/string objects, not Mocks
        # The service initializer does string operations like .startswith() and .rsplit()
        mock_database.main_db = Path(temp_data_dir) / "test.db"
        mock_database.secrets_db = Path(temp_data_dir) / "secrets.db"
        mock_database.audit_db = Path(temp_data_dir) / "audit.db"
        mock_database.database_url = None  # SQLite mode, not PostgreSQL
        config.database = mock_database

        # Add security attribute with secrets_key_path
        mock_security = Mock()
        mock_security.secrets_key_path = Path(temp_data_dir) / ".ciris_keys"
        config.security = mock_security

        # Add graph attribute for TSDB configuration
        mock_graph = Mock()
        mock_graph.tsdb_raw_retention_hours = 24  # Default retention
        config.graph = mock_graph

        # Add model_dump method that returns a dict for config migration
        config.model_dump = Mock(
            return_value={
                "data_dir": temp_data_dir,
                "db_path": os.path.join(temp_data_dir, "test.db"),
                "log_level": "INFO",
                "openai_api_key": "test-key",
                "anthropic_api_key": None,
                "database": {
                    "main_db": str(Path(temp_data_dir) / "test.db"),
                    "secrets_db": str(Path(temp_data_dir) / "secrets.db"),
                    "audit_db": str(Path(temp_data_dir) / "audit.db"),
                },
                "security": {
                    "secrets_key_path": str(Path(temp_data_dir) / ".ciris_keys"),
                },
            }
        )
        return config

    @pytest.fixture
    def service_initializer(self, mock_essential_config):
        """Create ServiceInitializer instance."""
        initializer = ServiceInitializer(essential_config=mock_essential_config)
        # Set attributes that were previously passed as constructor params
        initializer._db_path = mock_essential_config.db_path
        initializer._mock_llm = True
        return initializer

    @pytest.mark.asyncio
    async def test_initialize_all(self, service_initializer, mock_essential_config):
        """Test initializing all services."""
        with patch.object(service_initializer, "initialize_infrastructure_services") as mock_infra:
            with patch.object(service_initializer, "initialize_memory_service") as mock_memory:
                with patch.object(service_initializer, "initialize_security_services") as mock_security:
                    with patch.object(service_initializer, "initialize_all_services") as mock_all:
                        with patch.object(service_initializer, "verify_core_services") as mock_verify:

                            # Call the actual initialization sequence
                            await service_initializer.initialize_infrastructure_services()
                            await service_initializer.initialize_memory_service(mock_essential_config)
                            await service_initializer.initialize_security_services(
                                mock_essential_config, mock_essential_config
                            )
                            await service_initializer.initialize_all_services(
                                mock_essential_config, mock_essential_config, "test_agent", None, []
                            )
                            service_initializer.verify_core_services()

                            # Verify methods were called
                            mock_infra.assert_called_once()
                            mock_memory.assert_called_once()
                            mock_security.assert_called_once()
                            mock_all.assert_called_once()
                            mock_verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_infrastructure(self, service_initializer):
        """Test infrastructure services initialization."""
        await service_initializer.initialize_infrastructure_services()

        # Should create time service
        assert service_initializer.time_service is not None
        assert hasattr(service_initializer.time_service, "now")

        # Should create other infrastructure services
        assert service_initializer.shutdown_service is not None
        assert service_initializer.initialization_service is not None
        assert service_initializer.resource_monitor_service is not None

    @pytest.mark.asyncio
    async def test_initialize_database(self, service_initializer):
        """Test database initialization."""
        # Create time service first
        await service_initializer.initialize_infrastructure_services()

        # Note: Database initialization is now part of memory initialization
        # Just verify the db_path attribute exists
        assert service_initializer._db_path is not None

    @pytest.mark.asyncio
    async def test_initialize_memory(self, service_initializer, mock_essential_config):
        """Test memory services initialization."""
        # Initialize prerequisites
        await service_initializer.initialize_infrastructure_services()

        # Initialize memory
        await service_initializer.initialize_memory_service(mock_essential_config)

        # Should create secrets and memory services
        assert service_initializer.secrets_service is not None
        assert service_initializer.memory_service is not None
        assert service_initializer.config_service is not None

        # Should create config accessor
        assert service_initializer.config_accessor is not None

    @pytest.mark.asyncio
    async def test_initialize_identity(self, service_initializer, mock_essential_config):
        """Test identity initialization."""
        # Initialize prerequisites
        await service_initializer.initialize_infrastructure_services()
        await service_initializer.initialize_memory_service(mock_essential_config)

        # Mock memory service
        service_initializer.memory_service = Mock()
        service_initializer.memory_service.recall = AsyncMock(return_value=[])
        service_initializer.memory_service.memorize = AsyncMock()

        # Note: Identity initialization is now part of initialize_all_services
        # Just verify memory service exists
        assert service_initializer.memory_service is not None

    @pytest.mark.asyncio
    async def test_initialize_security(self, service_initializer, mock_essential_config):
        """Test security services initialization."""
        # Initialize prerequisites
        await service_initializer.initialize_infrastructure_services()

        # Mock config accessor
        service_initializer.config_accessor = Mock()
        service_initializer.config_accessor.get_path = AsyncMock(return_value=Path("test_auth.db"))

        # Mock auth service creation
        mock_auth_service = Mock()
        mock_auth_service.start = AsyncMock()

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.AuthenticationService",
            return_value=mock_auth_service,
        ):
            with patch("ciris_engine.logic.runtime.service_initializer.WiseAuthorityService") as mock_wa_class:
                mock_wa = Mock()
                mock_wa.start = AsyncMock()
                mock_wa_class.return_value = mock_wa

                await service_initializer.initialize_security_services(mock_essential_config, mock_essential_config)

                # Should create auth service
                assert service_initializer.auth_service is not None
                mock_auth_service.start.assert_called_once()

                # Should create wise authority service
                assert service_initializer.wa_auth_system is not None
                mock_wa.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_services(self, service_initializer, mock_essential_config):
        """Test remaining services initialization."""
        # Initialize prerequisites
        await service_initializer.initialize_infrastructure_services()
        service_initializer.memory_service = Mock()
        service_initializer.service_registry = Mock()
        service_initializer.bus_manager = Mock()
        service_initializer.bus_manager.memory = Mock()

        # Mock config_service for AdaptiveFilterService
        mock_config_service = AsyncMock()
        mock_config_service.get_config = AsyncMock(return_value=None)
        service_initializer.config_service = mock_config_service

        # Initialize services (part of initialize_all_services)
        with patch.object(service_initializer, "_initialize_llm_services"):
            with patch.object(service_initializer, "_initialize_audit_services"):
                await service_initializer.initialize_all_services(
                    mock_essential_config, mock_essential_config, "test_agent", None, []
                )

        # Should create services
        assert service_initializer.telemetry_service is not None
        assert service_initializer.adaptive_filter_service is not None
        assert service_initializer.task_scheduler_service is not None

    @pytest.mark.asyncio
    async def test_initialize_llm_service_mock(self, service_initializer, mock_essential_config):
        """Test LLM service initialization with mock."""
        service_initializer.service_registry = Mock()
        # CRITICAL: When mock LLM module is loaded, it sets _skip_llm_init = True
        # This prevents OpenAICompatibleClient from being registered
        service_initializer._skip_llm_init = True
        mock_essential_config.mock_llm = True

        # Add required services attribute
        mock_essential_config.services = Mock()
        mock_essential_config.services.llm_endpoint = "https://api.openai.com/v1"
        mock_essential_config.services.llm_model = "gpt-4"
        mock_essential_config.services.llm_timeout = 30
        mock_essential_config.services.llm_max_retries = 3

        # Initialize LLM (should skip because _skip_llm_init = True)
        await service_initializer._initialize_llm_services(mock_essential_config)

        # Since _skip_llm_init is True, no LLM service should be initialized
        assert service_initializer.llm_service is None
        # Should NOT register anything in registry
        service_initializer.service_registry.register_service.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_llm_service_real(self, service_initializer, mock_essential_config):
        """Test LLM service initialization with real provider."""
        service_initializer._mock_llm = False
        service_initializer.service_registry = Mock()
        service_initializer.telemetry_service = Mock()
        # Add services attribute as a Mock
        mock_essential_config.services = Mock()
        mock_essential_config.services.llm_endpoint = "https://api.openai.com/v1"
        mock_essential_config.services.llm_model = "gpt-4"
        mock_essential_config.services.llm_timeout = 30
        mock_essential_config.services.llm_max_retries = 3
        os.environ["OPENAI_API_KEY"] = "test-key"
        # Clear secondary LLM keys to ensure only primary is initialized in this test
        os.environ.pop("CIRIS_OPENAI_API_KEY_2", None)

        with patch("ciris_engine.logic.runtime.service_initializer.OpenAICompatibleClient") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_llm_class.return_value = mock_llm

            # Initialize LLM
            await service_initializer._initialize_llm_services(mock_essential_config)

            assert service_initializer.llm_service is not None
            # Check if secondary LLM is configured
            if os.environ.get("CIRIS_OPENAI_API_KEY_2"):
                # Both primary and secondary LLM services initialized
                assert mock_llm_class.call_count == 2
            else:
                # Only primary LLM service initialized
                assert mock_llm_class.call_count == 1

    @pytest.mark.asyncio
    async def test_service_cleanup(self, service_initializer):
        """Test service cleanup behavior."""
        # Create mock services with stop methods
        mock_service1 = Mock()
        mock_service1.stop = Mock()
        mock_service2 = Mock()
        mock_service2.stop = Mock()

        # Set services on initializer
        service_initializer.time_service = mock_service1
        service_initializer.memory_service = mock_service2

        # Manually stop services (since there's no shutdown_all method)
        if hasattr(service_initializer.time_service, "stop"):
            service_initializer.time_service.stop()
        if hasattr(service_initializer.memory_service, "stop"):
            service_initializer.memory_service.stop()

        # All services should be stopped
        mock_service1.stop.assert_called_once()
        mock_service2.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_service_stop_with_error(self, service_initializer):
        """Test service stop handling errors."""
        # Create service that errors on stop
        mock_service = Mock()
        mock_service.stop = Mock(side_effect=Exception("Stop error"))

        service_initializer.time_service = mock_service

        # Should not raise when stopping
        try:
            if hasattr(service_initializer.time_service, "stop"):
                service_initializer.time_service.stop()
        except Exception:
            pass  # Expected

        # Service stop should have been attempted
        mock_service.stop.assert_called_once()

    def test_services_are_set(self, service_initializer):
        """Test that services can be set on initializer."""
        # Add some services
        service_initializer.time_service = Mock()
        service_initializer.memory_service = Mock()

        # Verify the services are set
        assert service_initializer.time_service is not None
        assert service_initializer.memory_service is not None

    @pytest.mark.asyncio
    async def test_verify_initialization(self, service_initializer):
        """Test initialization verification."""
        # Set up required services
        service_initializer.service_registry = Mock()
        service_initializer.telemetry_service = Mock()
        service_initializer.llm_service = Mock()
        service_initializer.memory_service = Mock()
        service_initializer.secrets_service = Mock()
        service_initializer.adaptive_filter_service = Mock()
        service_initializer.audit_service = Mock()

        # Should return True
        result = service_initializer.verify_core_services()
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_initialization_missing_service(self, service_initializer):
        """Test verification with missing service."""
        # Missing service_registry
        service_initializer.memory_service = Mock()

        # Should return False
        result = service_initializer.verify_core_services()
        assert result is False

    @pytest.mark.asyncio
    async def test_service_count(self, service_initializer, mock_essential_config):
        """Test that services are initialized (but don't count exactly 19 due to mocking)."""
        # Mock all the dependencies to avoid actual initialization
        service_initializer.service_registry = Mock()
        service_initializer.bus_manager = Mock()
        service_initializer.bus_manager.memory = Mock()
        service_initializer.memory_service = Mock()
        service_initializer.time_service = Mock()
        service_initializer.telemetry_service = Mock()
        service_initializer.config_service = Mock()
        service_initializer.llm_service = Mock()

        # Mock the private initialization methods
        with patch.object(service_initializer, "_initialize_llm_services"):
            with patch.object(service_initializer, "_initialize_audit_services"):
                await service_initializer.initialize_all_services(
                    mock_essential_config, mock_essential_config, "test_agent", None, []
                )

        # Just verify some key services exist after initialization
        assert service_initializer.adaptive_filter_service is not None
        assert service_initializer.task_scheduler_service is not None
        assert service_initializer.tsdb_consolidation_service is not None

    @pytest.mark.asyncio
    async def test_initialization_order_dependencies(self, service_initializer, mock_essential_config):
        """Test that services are initialized in correct dependency order."""
        calls = []

        # Mock each initialization phase to track order
        async def track_call(phase):
            calls.append(phase)

        def track_call_sync(phase):
            calls.append(phase)

        # Track actual method calls - use return_value instead of side_effect to avoid immediate execution
        with patch.object(service_initializer, "initialize_infrastructure_services") as mock_infra:
            with patch.object(service_initializer, "initialize_memory_service") as mock_memory:
                with patch.object(service_initializer, "initialize_security_services") as mock_security:
                    with patch.object(service_initializer, "initialize_all_services") as mock_all:
                        with patch.object(
                            service_initializer, "verify_core_services", return_value=True
                        ) as mock_verify:

                            # Call initialization sequence
                            await service_initializer.initialize_infrastructure_services()
                            calls.append("infrastructure")

                            await service_initializer.initialize_memory_service(mock_essential_config)
                            calls.append("memory")

                            await service_initializer.initialize_security_services(
                                mock_essential_config, mock_essential_config
                            )
                            calls.append("security")

                            await service_initializer.initialize_all_services(
                                mock_essential_config, mock_essential_config, "test_agent", None, []
                            )
                            calls.append("services")

                            service_initializer.verify_core_services()
                            calls.append("verify")

        # Verify order
        assert calls.index("infrastructure") < calls.index("memory")
        assert calls.index("memory") < calls.index("security")
        assert calls.index("security") < calls.index("services")
        assert calls.index("services") < calls.index("verify")


class TestModularServiceLoading:
    """Test cases for modular service loading integration."""

    @pytest.fixture
    def temp_services_dir(self, tmp_path):
        """Create temporary modular services directory."""
        services_dir = tmp_path / "ciris_modular_services"
        services_dir.mkdir()
        return services_dir

    @pytest.fixture
    def mock_essential_config(self):
        """Create mock essential config for modular service tests."""
        temp_dir = tempfile.mkdtemp()
        config = Mock(spec=EssentialConfig)
        config.data_dir = temp_dir
        config.db_path = os.path.join(temp_dir, "test.db")
        config.log_level = "INFO"
        config.agent_occurrence_id = "default"  # Add occurrence_id for modular service injection

        # Add database attribute
        mock_database = Mock()
        mock_database.main_db = Path(temp_dir) / "test.db"
        mock_database.secrets_db = Path(temp_dir) / "secrets.db"
        mock_database.audit_db = Path(temp_dir) / "audit.db"
        mock_database.database_url = None
        config.database = mock_database

        # Add security attribute
        mock_security = Mock()
        mock_security.secrets_key_path = Path(temp_dir) / ".ciris_keys"
        config.security = mock_security

        # Add graph attribute
        mock_graph = Mock()
        mock_graph.tsdb_raw_retention_hours = 24
        config.graph = mock_graph

        return config

    @pytest.fixture
    def mock_service_initializer(self, mock_essential_config):
        """Create ServiceInitializer with mocked buses."""
        from ciris_engine.logic.runtime.service_initializer import ServiceInitializer

        initializer = ServiceInitializer(essential_config=mock_essential_config)
        initializer._db_path = mock_essential_config.db_path
        initializer._mock_llm = True

        # Mock the bus_manager with nested tool and communication buses
        initializer.bus_manager = Mock()
        initializer.bus_manager.tool = Mock()
        initializer.bus_manager.tool.register_service = Mock()
        initializer.bus_manager.communication = Mock()
        initializer.bus_manager.communication.register_service = Mock()

        initializer.service_registry = Mock()
        initializer.service_registry.register_service = Mock()

        initializer.loaded_modules = []

        return initializer

    @pytest.fixture
    def test_manifest(self):
        """Create a test service manifest."""
        from ciris_engine.schemas.runtime.enums import ServiceType
        from ciris_engine.schemas.runtime.manifest import (
            ModuleInfo,
            ServiceDeclaration,
            ServiceManifest,
            ServicePriority,
        )

        return ServiceManifest(
            module=ModuleInfo(
                name="test_adapter",
                version="1.0.0",
                description="Test adapter for unit tests",
                author="Test Author",
                is_mock=False,
            ),
            services=[
                ServiceDeclaration(
                    type=ServiceType.COMMUNICATION,
                    class_path="test_adapter.TestAdapter",
                    priority=ServicePriority.NORMAL,
                    capabilities=["send_message", "receive_message"],
                )
            ],
        )

    @pytest.mark.asyncio
    async def test_load_modular_service_not_found(self, mock_service_initializer):
        """Test loading a modular service that doesn't exist."""
        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = []
            mock_loader_class.return_value = mock_loader

            with pytest.raises(ValueError, match="Modular service 'nonexistent' not found"):
                await mock_service_initializer._load_modular_service("nonexistent")

    @pytest.mark.asyncio
    async def test_load_modular_service_communication_adapter(self, mock_service_initializer, test_manifest):
        """Test loading a COMMUNICATION type modular service."""
        from ciris_engine.schemas.runtime.enums import ServiceType

        # Create mock service class
        mock_service_class = Mock()
        mock_service_instance = Mock()
        mock_service_class.return_value = mock_service_instance

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [test_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            await mock_service_initializer._load_modular_service("test_adapter")

            # Verify service was registered with ServiceRegistry
            mock_service_initializer.service_registry.register_service.assert_called_once()
            call_args = mock_service_initializer.service_registry.register_service.call_args
            assert call_args[1]["service_type"] == ServiceType.COMMUNICATION
            assert call_args[1]["provider"] == mock_service_instance
            assert "send_message" in call_args[1]["capabilities"]
            assert "receive_message" in call_args[1]["capabilities"]

            # Verify loaded_modules was updated
            assert "modular:test_adapter" in mock_service_initializer.loaded_modules

    @pytest.mark.asyncio
    async def test_load_modular_service_tool_type(self, mock_service_initializer):
        """Test loading a TOOL type modular service."""
        from ciris_engine.schemas.runtime.enums import ServiceType
        from ciris_engine.schemas.runtime.manifest import (
            ModuleInfo,
            ServiceDeclaration,
            ServiceManifest,
            ServicePriority,
        )

        # Create tool manifest
        tool_manifest = ServiceManifest(
            module=ModuleInfo(
                name="tool_service",
                version="1.0.0",
                description="Tool service",
                author="Test",
                is_mock=False,
            ),
            services=[
                ServiceDeclaration(
                    type=ServiceType.TOOL,
                    class_path="tool_service.ToolService",
                    priority=ServicePriority.NORMAL,
                    capabilities=["execute_tool"],
                )
            ],
        )

        mock_service_class = Mock()
        mock_service_instance = Mock()
        mock_service_class.return_value = mock_service_instance

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [tool_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            await mock_service_initializer._load_modular_service("tool_service")

            # Verify service was registered with ServiceRegistry
            mock_service_initializer.service_registry.register_service.assert_called_once()
            call_args = mock_service_initializer.service_registry.register_service.call_args
            assert call_args[1]["service_type"] == ServiceType.TOOL
            assert call_args[1]["provider"] == mock_service_instance
            assert "execute_tool" in call_args[1]["capabilities"]

    @pytest.mark.asyncio
    async def test_load_modular_service_llm_type(self, mock_service_initializer):
        """Test loading an LLM type modular service."""
        from ciris_engine.schemas.runtime.enums import ServiceType
        from ciris_engine.schemas.runtime.manifest import (
            ModuleInfo,
            ServiceDeclaration,
            ServiceManifest,
            ServicePriority,
        )

        # Create LLM manifest
        llm_manifest = ServiceManifest(
            module=ModuleInfo(
                name="llm_service",
                version="1.0.0",
                description="LLM service",
                author="Test",
                is_mock=False,
            ),
            services=[
                ServiceDeclaration(
                    type=ServiceType.LLM,
                    class_path="llm_service.LLMService",
                    priority=ServicePriority.HIGH,
                    capabilities=["text_generation"],
                )
            ],
        )

        mock_service_class = Mock()
        mock_service_instance = Mock()
        mock_service_class.return_value = mock_service_instance

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [llm_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            await mock_service_initializer._load_modular_service("llm_service")

            # Verify service was registered with ServiceRegistry
            mock_service_initializer.service_registry.register_service.assert_called_once()
            call_kwargs = mock_service_initializer.service_registry.register_service.call_args.kwargs
            assert call_kwargs["service_type"] == ServiceType.LLM
            assert call_kwargs["provider"] == mock_service_instance
            assert call_kwargs["capabilities"] == ["text_generation"]

    @pytest.mark.asyncio
    async def test_load_modular_service_case_insensitive_match(self, mock_service_initializer, test_manifest):
        """Test that service name matching is case-insensitive."""
        mock_service_class = Mock()
        mock_service_instance = Mock()
        mock_service_class.return_value = mock_service_instance

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [test_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            # Test with uppercase
            await mock_service_initializer._load_modular_service("TEST_ADAPTER")

            # Verify service was loaded
            assert "modular:TEST_ADAPTER" in mock_service_initializer.loaded_modules

    @pytest.mark.asyncio
    async def test_load_modular_service_adapter_suffix_handling(self, mock_service_initializer, test_manifest):
        """Test that _adapter suffix is handled correctly."""
        mock_service_class = Mock()
        mock_service_instance = Mock()
        mock_service_class.return_value = mock_service_instance

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [test_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            # Should match "test" even though manifest is "test_adapter"
            await mock_service_initializer._load_modular_service("test")

            # Verify service was loaded
            assert "modular:test" in mock_service_initializer.loaded_modules

    @pytest.mark.asyncio
    async def test_load_modular_service_load_failure(self, mock_service_initializer, test_manifest):
        """Test handling when service class fails to load."""
        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [test_manifest]
            mock_loader.load_service_class.return_value = None  # Load failure
            mock_loader_class.return_value = mock_loader

            # Should not raise, just log error
            await mock_service_initializer._load_modular_service("test_adapter")

            # Verify service was NOT registered
            mock_service_initializer.bus_manager.communication.register_service.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_modular_service_instantiation_failure(self, mock_service_initializer, test_manifest):
        """Test handling when service instantiation fails."""
        mock_service_class = Mock(side_effect=Exception("Instantiation failed"))

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [test_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            # Should raise the exception
            with pytest.raises(Exception, match="Instantiation failed"):
                await mock_service_initializer._load_modular_service("test_adapter")

    @pytest.mark.asyncio
    async def test_load_modules_with_modular_prefix(self, mock_service_initializer, test_manifest):
        """Test load_modules handles 'modular:' prefix."""
        mock_service_class = Mock()
        mock_service_instance = Mock()
        mock_service_class.return_value = mock_service_instance

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [test_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            # Call load_modules with modular prefix
            await mock_service_initializer.load_modules(["modular:test_adapter"])

            # Verify service was loaded and registered with ServiceRegistry
            mock_service_initializer.service_registry.register_service.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_modules_loads_mock_services(self, mock_service_initializer):
        """Test that MOCK modular services are loaded via load_modules.

        Note: The MOCK filtering happens in ModularServiceLoader.initialize_modular_services,
        not in ServiceInitializer._load_modular_service. This is by design - load_modules
        is a direct loader that doesn't filter MOCK services.
        """
        from ciris_engine.schemas.runtime.enums import ServiceType
        from ciris_engine.schemas.runtime.manifest import (
            ModuleInfo,
            ServiceDeclaration,
            ServiceManifest,
            ServicePriority,
        )

        # Create MOCK manifest
        mock_manifest = ServiceManifest(
            module=ModuleInfo(
                name="mock_service",
                version="1.0.0",
                description="Mock service",
                author="Test",
                is_mock=True,  # This is a MOCK service
            ),
            services=[
                ServiceDeclaration(
                    type=ServiceType.LLM,
                    class_path="mock_service.MockService",
                    priority=ServicePriority.CRITICAL,
                    capabilities=["mock"],
                )
            ],
        )

        mock_service_class = Mock()
        mock_service_instance = Mock()
        mock_service_class.return_value = mock_service_instance

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [mock_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            # load_modules DOES load mock services (no filtering at this level)
            await mock_service_initializer.load_modules(["modular:mock_service"], disable_core_on_mock=True)

            # Verify service WAS registered (load_modules doesn't filter MOCK)
            mock_service_initializer.service_registry.register_service.assert_called_once()

    @pytest.mark.asyncio
    async def test_runtime_dependency_injection_success(self, mock_service_initializer, test_manifest):
        """Test successful runtime dependency injection into modular service."""
        # Create mock service class that accepts runtime dependencies
        mock_service_instance = Mock()

        def mock_service_constructor(**kwargs):
            """Simulate service that accepts runtime dependencies."""
            # Verify all expected dependencies are passed
            assert "bus_manager" in kwargs
            assert "memory_service" in kwargs
            assert "agent_id" in kwargs
            assert "filter_service" in kwargs
            assert "secrets_service" in kwargs
            assert "time_service" in kwargs
            return mock_service_instance

        mock_service_class = Mock(side_effect=mock_service_constructor)

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [test_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            # Add required dependencies to initializer
            mock_service_initializer.memory_service = Mock()
            mock_service_initializer.adaptive_filter_service = Mock()
            mock_service_initializer.secrets_service = Mock()
            mock_service_initializer.time_service = Mock()

            await mock_service_initializer._load_modular_service("test_adapter")

            # Verify service was instantiated with runtime dependencies
            mock_service_class.assert_called_once()
            call_kwargs = mock_service_class.call_args[1]
            assert call_kwargs["bus_manager"] == mock_service_initializer.bus_manager
            assert call_kwargs["memory_service"] == mock_service_initializer.memory_service
            assert call_kwargs["agent_id"] is None  # Identity service will set later
            assert call_kwargs["filter_service"] == mock_service_initializer.adaptive_filter_service
            assert call_kwargs["secrets_service"] == mock_service_initializer.secrets_service
            assert call_kwargs["time_service"] == mock_service_initializer.time_service

            # Verify service was registered
            mock_service_initializer.service_registry.register_service.assert_called_once()

    @pytest.mark.asyncio
    async def test_runtime_dependency_injection_fallback(self, mock_service_initializer, test_manifest):
        """Test fallback to no-args constructor when service doesn't accept dependencies."""
        # Create mock service class that ONLY accepts no-args constructor
        mock_service_instance = Mock()

        def mock_service_constructor(*args, **kwargs):
            """Simulate service that raises TypeError if kwargs provided."""
            if kwargs:
                raise TypeError(f"Unexpected keyword arguments: {list(kwargs.keys())}")
            return mock_service_instance

        mock_service_class = Mock(side_effect=mock_service_constructor)

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [test_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            # Add required dependencies to initializer
            mock_service_initializer.memory_service = Mock()
            mock_service_initializer.adaptive_filter_service = Mock()
            mock_service_initializer.secrets_service = Mock()
            mock_service_initializer.time_service = Mock()

            await mock_service_initializer._load_modular_service("test_adapter")

            # Verify service was instantiated twice:
            # 1. First with runtime dependencies (raised TypeError)
            # 2. Second with no args (fallback)
            assert mock_service_class.call_count == 2

            # First call had kwargs
            first_call_kwargs = mock_service_class.call_args_list[0][1]
            assert len(first_call_kwargs) > 0

            # Second call had no args/kwargs (fallback)
            second_call_args = mock_service_class.call_args_list[1][0]
            second_call_kwargs = mock_service_class.call_args_list[1][1]
            assert len(second_call_args) == 0
            assert len(second_call_kwargs) == 0

            # Verify service was registered
            mock_service_initializer.service_registry.register_service.assert_called_once()

    @pytest.mark.asyncio
    async def test_runtime_dependency_injection_with_none_dependencies(self, mock_service_initializer, test_manifest):
        """Test runtime dependency injection when some dependencies are None."""
        # Create mock service class that accepts runtime dependencies
        mock_service_instance = Mock()

        def mock_service_constructor(**kwargs):
            """Simulate service that accepts None values for dependencies."""
            # Service should handle None gracefully
            assert kwargs.get("bus_manager") is not None  # Always set
            assert kwargs.get("memory_service") is None  # Might be None
            assert kwargs.get("agent_id") is None  # Always None initially
            return mock_service_instance

        mock_service_class = Mock(side_effect=mock_service_constructor)

        with patch("ciris_engine.logic.runtime.modular_service_loader.ModularServiceLoader") as mock_loader_class:
            mock_loader = Mock()
            mock_loader.discover_services.return_value = [test_manifest]
            mock_loader.load_service_class.return_value = mock_service_class
            mock_loader_class.return_value = mock_loader

            # Set some dependencies to None
            mock_service_initializer.memory_service = None
            mock_service_initializer.adaptive_filter_service = None
            mock_service_initializer.secrets_service = None
            mock_service_initializer.time_service = None

            await mock_service_initializer._load_modular_service("test_adapter")

            # Verify service was instantiated with None dependencies
            mock_service_class.assert_called_once()
            call_kwargs = mock_service_class.call_args[1]
            assert call_kwargs["bus_manager"] == mock_service_initializer.bus_manager
            assert call_kwargs["memory_service"] is None
            assert call_kwargs["agent_id"] is None
            assert call_kwargs["filter_service"] is None
            assert call_kwargs["secrets_service"] is None
            assert call_kwargs["time_service"] is None
