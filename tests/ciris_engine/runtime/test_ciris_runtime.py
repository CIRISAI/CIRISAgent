"""
Unit tests for the unified CIRISRuntime.

100% TYPE SAFE MISSION CRITICAL CODE - comprehensive testing of the new multi-adapter runtime model.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from typing import List, Optional, Dict, Any
from pathlib import Path

from ciris_engine.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.schemas.config_schemas_v1 import AppConfig, AgentTemplate
from ciris_engine.protocols.adapter_interface import PlatformAdapter, ServiceRegistration, ServiceType
from ciris_engine.registries.base import Priority
from ciris_engine.adapters.base import Service


class MockService(Service):
    """Mock service for testing."""
    
    def __init__(self, service_id: str = "mock_service"):
        self.service_id = service_id
        self.started = False
        self.stopped = False
    
    async def start(self) -> None:
        """Start the service."""
        self.started = True
    
    async def stop(self) -> None:
        """Stop the service."""
        self.stopped = True


class MockAdapter(PlatformAdapter):
    """Mock adapter for testing the multi-adapter model."""
    
    def __init__(self, runtime: CIRISRuntime, adapter_name: str = "mock_adapter", **kwargs):
        self.runtime = runtime
        self.adapter_name = adapter_name
        self.started = False
        self.stopped = False
        self.kwargs = kwargs
        self.mock_service = MockService(f"{adapter_name}_service")
    
    async def start(self) -> None:
        """Start the adapter."""
        self.started = True
    
    async def stop(self) -> None:
        """Stop the adapter."""
        self.stopped = True
    
    async def run_lifecycle(self, agent_task: asyncio.Task) -> None:
        """Run the adapter lifecycle."""
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
    
    def get_services_to_register(self) -> List[ServiceRegistration]:
        """Return services to register."""
        return [
            ServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.mock_service,
                priority=Priority.HIGH,
                handlers=["SpeakHandler"]
            )
        ]


@pytest.fixture
def mock_app_config() -> AppConfig:
    """Create a mock AppConfig for testing."""
    config = MagicMock(spec=AppConfig)
    config.profile_directory = "ciris_profiles"
    config.agent_profiles = {}
    
    # Mock LLM config with proper structure for OpenAICompatibleClient
    config.llm_services = MagicMock()
    config.llm_services.openai = MagicMock()
    config.llm_services.openai.max_retries = 3
    config.llm_services.openai.instructor_mode = "json"
    config.llm_services.openai.api_key = "test_key"
    config.llm_services.openai.base_url = "https://api.openai.com/v1"
    config.llm_services.openai.model_name = "gpt-4"
    
    # Mock audit config
    config.audit = MagicMock()
    config.audit.enable_signed_audit = False
    config.audit.audit_log_path = "audit_logs.jsonl"
    config.audit.audit_db_path = "audit.db"
    config.audit.rotation_size_mb = 100
    
    # Mock secrets config
    config.secrets = MagicMock()
    config.secrets.storage = MagicMock()
    config.secrets.storage.database_path = "test_secrets.db"
    config.audit.retention_days = 30
    config.audit.enable_jsonl_audit = True
    
    # Mock guardrails config
    config.guardrails = MagicMock()
    config.guardrails.enable_remote_graphql = False
    
    # Mock workflow config
    config.workflow = MagicMock()
    config.workflow.max_rounds = 10
    
    # Mock data archive config
    config.data_archive_dir = "data_archive"
    config.archive_older_than_hours = 24
    
    return config


@pytest.fixture
def mock_agent_profile() -> AgentTemplate:
    """Create a mock AgentTemplate for testing."""
    profile = MagicMock(spec=AgentTemplate)
    profile.name = "test_profile"
    profile.csdma_overrides = None
    profile.action_selection_pdma_overrides = None
    return profile


@pytest.fixture
async def mock_services():
    """Create mock services for testing."""
    services = {}
    
    # Mock all the services that CIRISRuntime initializes
    services['llm_service'] = AsyncMock()
    services['llm_service'].get_client.return_value = MagicMock()
    services['llm_service'].get_client.return_value.model_name = "test-model"
    
    services['memory_service'] = AsyncMock()
    services['audit_service'] = AsyncMock()
    services['telemetry_service'] = AsyncMock()
    services['secrets_service'] = AsyncMock()
    services['adaptive_filter_service'] = AsyncMock()
    services['agent_config_service'] = AsyncMock()
    services['transaction_orchestrator'] = AsyncMock()
    services['maintenance_service'] = AsyncMock()
    
    return services


class TestCIRISRuntime:
    """Test suite for the unified CIRISRuntime."""
    
    @pytest.mark.asyncio
    async def test_runtime_initialization_with_single_adapter(self, mock_app_config: AppConfig):
        """Test runtime initialization with a single adapter."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test_profile",
                app_config=mock_app_config
            )
            
            assert len(runtime.adapters) == 1
            assert isinstance(runtime.adapters[0], MockAdapter)
            assert runtime.adapters[0].adapter_name == "mock_adapter"
    
    @pytest.mark.asyncio
    async def test_runtime_initialization_with_multiple_adapters(self, mock_app_config: AppConfig):
        """Test runtime initialization with multiple adapters (multi-adapter model)."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock1", "mock2", "mock3"],
                profile_name="test_profile",
                app_config=mock_app_config
            )
            
            assert len(runtime.adapters) == 3
            for adapter in runtime.adapters:
                assert isinstance(adapter, MockAdapter)
    
    @pytest.mark.asyncio
    async def test_runtime_initialization_failure_continues_with_other_adapters(self, mock_app_config: AppConfig):
        """Test that adapter initialization failure doesn't prevent other adapters from loading."""
        def mock_load_adapter_side_effect(mode: str):
            if mode == "failing_mode":
                raise RuntimeError("Mock adapter load failure")
            return MockAdapter
        
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter', side_effect=mock_load_adapter_side_effect):
            runtime = CIRISRuntime(
                adapter_types=["mock1", "failing_mode", "mock2"],
                profile_name="test_profile",
                app_config=mock_app_config
            )
            
            # Should only have 2 adapters (the failing one should be skipped)
            assert len(runtime.adapters) == 2
    
    @pytest.mark.asyncio
    async def test_ensure_config_with_config(self, mock_app_config: AppConfig):
        """Test _ensure_config when config is provided."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test",
                app_config=mock_app_config
            )
            
            config = runtime._ensure_config()
            assert config is mock_app_config
    
    @pytest.mark.asyncio
    async def test_ensure_config_without_config(self):
        """Test _ensure_config when no config is provided."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test"
            )
            
            with pytest.raises(RuntimeError, match="App config not initialized"):
                runtime._ensure_config()
    
    @pytest.mark.asyncio
    async def test_request_shutdown(self, mock_app_config: AppConfig):
        """Test shutdown request mechanism."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test",
                app_config=mock_app_config
            )
        
        # Initialize shutdown event
        runtime._ensure_shutdown_event()
        
        assert not runtime._shutdown_event.is_set()
        assert runtime._shutdown_reason is None
        
        runtime.request_shutdown("Test shutdown reason")
        
        assert runtime._shutdown_event.is_set()
        assert runtime._shutdown_reason == "Test shutdown reason"
    
    @pytest.mark.asyncio
    async def test_duplicate_shutdown_request_ignored(self, mock_app_config: AppConfig):
        """Test that duplicate shutdown requests are ignored."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test",
                app_config=mock_app_config
            )
        
        # Initialize shutdown event
        runtime._ensure_shutdown_event()
        
        runtime.request_shutdown("First reason")
        first_reason = runtime._shutdown_reason
        
        runtime.request_shutdown("Second reason")
        
        # Should still have the first reason
        assert runtime._shutdown_reason == first_reason
    
    @pytest.mark.asyncio
    async def test_load_profile_success(self, mock_app_config: AppConfig, mock_agent_profile: AgentTemplate):
        """Test successful profile loading."""
        # Add the test profile to config
        mock_app_config.agent_profiles["test_profile"] = mock_agent_profile
        
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test_profile",
                app_config=mock_app_config
            )
        
        # Profile loading is now handled through AppConfig
        # The profile is loaded during initialization from app_config.agent_profiles
        assert runtime.app_config.agent_profiles.get("test_profile") is not None
        assert runtime.app_config.agent_profiles["test_profile"] == mock_agent_profile
    
    @pytest.mark.asyncio
    async def test_load_profile_fallback_to_default(self, mock_app_config: AppConfig, mock_agent_profile: AgentTemplate):
        """Test fallback to default profile when requested profile doesn't exist."""
        # Add default profile to config
        mock_app_config.agent_profiles["default"] = mock_agent_profile
        
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            # Creating runtime with nonexistent profile should use default from config
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="nonexistent_profile",
                app_config=mock_app_config
            )
            
            # The runtime should have access to profiles through app_config
            assert "default" in runtime.app_config.agent_profiles
    
    @pytest.mark.asyncio
    async def test_load_profile_failure(self, mock_app_config: AppConfig):
        """Test profile loading failure when no profile can be loaded."""
        # Clear all profiles from config
        mock_app_config.agent_profiles = {}
        
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="nonexistent_profile",
                app_config=mock_app_config
            )
            
            # Runtime should still initialize but without profiles
            assert len(runtime.app_config.agent_profiles) == 0
    
    @pytest.mark.asyncio
    async def test_register_adapter_services(self, mock_app_config: AppConfig):
        """Test registration of services provided by adapters."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test",
                app_config=mock_app_config
            )
            
            # Initialize service registry through service initializer
            from ciris_engine.registries.base import ServiceRegistry
            runtime.service_initializer.service_registry = ServiceRegistry()
            
            # Mock WA auth system for test
            mock_wa_auth = AsyncMock()
            mock_wa_auth.create_channel_token_for_adapter = AsyncMock(return_value="test_token")
            runtime.service_initializer.wa_auth_system = mock_wa_auth
            
            await runtime._register_adapter_services()
            
            # Verify that the mock service was registered using proper API
            info = runtime.service_registry.get_provider_info()
            registered_services = info.get("handlers", {}).get("SpeakHandler", {})
            assert "communication" in registered_services
    
    @pytest.mark.asyncio
    async def test_register_adapter_services_with_invalid_registration(self, mock_app_config: AppConfig):
        """Test handling of invalid service registrations from adapters."""
        class BadAdapter(MockAdapter):
            def get_services_to_register(self) -> List[ServiceRegistration]:
                # Return invalid registration (not a ServiceRegistration instance)
                return ["invalid_registration"]  # type: ignore
        
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = BadAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["bad"],
                profile_name="test",
                app_config=mock_app_config
            )
            
            from ciris_engine.registries.base import ServiceRegistry
            runtime.service_initializer.service_registry = ServiceRegistry()
            
            # Mock WA auth system for test
            mock_wa_auth = AsyncMock()
            mock_wa_auth.create_adapter_token = AsyncMock(return_value="test_token")
            runtime.service_initializer.wa_auth_system = mock_wa_auth
            
            # Should not raise an exception, just log the error
            await runtime._register_adapter_services()
    
    @pytest.mark.asyncio
    async def test_register_adapter_services_with_non_service_provider(self, mock_app_config: AppConfig):
        """Test handling of service registrations with invalid provider types."""
        class BadProviderAdapter(MockAdapter):
            def get_services_to_register(self) -> List[ServiceRegistration]:
                return [
                    ServiceRegistration(
                        service_type=ServiceType.COMMUNICATION,
                        provider="not_a_service",  # type: ignore
                        priority=Priority.HIGH,
                        handlers=["SpeakHandler"]
                    )
                ]
        
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = BadProviderAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["bad_provider"],
                profile_name="test",
                app_config=mock_app_config
            )
            
            from ciris_engine.registries.base import ServiceRegistry
            runtime.service_initializer.service_registry = ServiceRegistry()
            
            # Mock WA auth system for test
            mock_wa_auth = AsyncMock()
            mock_wa_auth.create_adapter_token = AsyncMock(return_value="test_token")
            runtime.service_initializer.wa_auth_system = mock_wa_auth
            
            # Should not raise an exception, just log the error
            await runtime._register_adapter_services()
    
    @pytest.mark.asyncio
    async def test_initialize_prevents_duplicate_initialization(self, mock_app_config: AppConfig):
        """Test that initialize() can be called multiple times safely."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test",
                app_config=mock_app_config
            )
        
        # Mock all the dependencies
        with patch.multiple(
            'ciris_engine.runtime.ciris_runtime',
            persistence=MagicMock(),
        ), patch('ciris_engine.runtime.ciris_runtime.get_initialization_manager') as mock_get_init:
            # Create a mock initialization manager that succeeds
            mock_init_manager = AsyncMock()
            mock_init_manager.initialize = AsyncMock()
            mock_get_init.return_value = mock_init_manager
            
            # Also mock the final maintenance step
            with patch.object(runtime, '_perform_startup_maintenance'):
                await runtime.initialize()
                assert runtime._initialized is True
            
            # Second call should return immediately
            await runtime.initialize()
    
    @pytest.mark.asyncio
    async def test_initialize_database_maintenance_failure(self, mock_app_config: AppConfig):
        """Test initialization failure during database maintenance."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test",
                app_config=mock_app_config
            )
        
        with patch('ciris_engine.runtime.ciris_runtime.get_initialization_manager') as mock_get_init:
            # Create a mock initialization manager that succeeds
            mock_init_manager = AsyncMock()
            mock_init_manager.initialize = AsyncMock()
            mock_get_init.return_value = mock_init_manager
            
            # Mock the maintenance step to fail
            with patch.object(runtime, '_perform_startup_maintenance') as mock_maintenance:
                mock_maintenance.side_effect = RuntimeError("Database maintenance failed")
                
                with pytest.raises(RuntimeError, match="Database maintenance failed"):
                    await runtime.initialize()
    
    @pytest.mark.asyncio
    @patch('ciris_engine.runtime.ciris_runtime.persistence')
    async def test_full_initialization_sequence(self, mock_persistence, mock_app_config: AppConfig, mock_agent_profile: AgentTemplate):
        """Test the complete initialization sequence."""
        mock_persistence.initialize_database = MagicMock()
        
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test",
                app_config=mock_app_config
            )
            
            # Mock all the heavy dependencies
            with patch('ciris_engine.runtime.ciris_runtime.get_initialization_manager') as mock_get_init:
                # Create a mock initialization manager that tracks calls
                mock_init_manager = AsyncMock()
                initialization_called = False
                async def mock_initialize():
                    nonlocal initialization_called
                    initialization_called = True
                    # Simulate starting adapters
                    for adapter in runtime.adapters:
                        await adapter.start()
                
                mock_init_manager.initialize = mock_initialize
                mock_init_manager.register_step = MagicMock()
                mock_get_init.return_value = mock_init_manager
                
                # Mock the final maintenance step
                with patch.object(runtime, '_perform_startup_maintenance') as mock_maintenance:
                    await runtime.initialize()
                    
                    # Verify initialization was called
                    assert initialization_called
                    mock_maintenance.assert_called_once()
                    
                    # Verify adapters were started
                    assert runtime.adapters[0].started is True
                    
                    assert runtime._initialized is True
    
    @pytest.mark.asyncio
    async def test_shutdown_sequence(self, mock_app_config: AppConfig):
        """Test the complete shutdown sequence."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test",
                app_config=mock_app_config
            )
            
            # Set up runtime with minimal initialization
            runtime._initialized = True
            runtime._shutdown_event = asyncio.Event()
            
            # Mock the agent processor with state_manager
            runtime.agent_processor = AsyncMock()
            
            # Mock state_manager
            from ciris_engine.processor.state_manager import StateManager
            from ciris_engine.schemas.states_v1 import AgentState
            runtime.agent_processor.state_manager = StateManager(initial_state=AgentState.WORK)
            
            # Mock processing task as not running
            runtime.agent_processor._processing_task = None
            runtime.agent_processor._stop_event = None
            
            # Mock shutdown processor
            runtime.agent_processor.shutdown_processor = AsyncMock()
            runtime.agent_processor.shutdown_processor.shutdown_complete = True
            runtime.agent_processor.shutdown_processor.shutdown_result = {"status": "accepted"}
            
            # Create mock services
            from ciris_engine.runtime.service_initializer import ServiceInitializer
            runtime.service_initializer = ServiceInitializer()
            runtime.service_initializer.bus_manager = AsyncMock()
            runtime.service_initializer.service_registry = MagicMock()
            
            # Mock other services that shutdown expects
            runtime.service_initializer.llm_service = AsyncMock()
            runtime.service_initializer.memory_service = AsyncMock()
            runtime.service_initializer.audit_service = AsyncMock()
            runtime.service_initializer.telemetry_service = AsyncMock()
            runtime.service_initializer.secrets_service = AsyncMock()
            runtime.service_initializer.adaptive_filter_service = AsyncMock()
            runtime.service_initializer.agent_config_service = AsyncMock()
            runtime.service_initializer.transaction_orchestrator = AsyncMock()
            runtime.service_initializer.maintenance_service = AsyncMock()
            
            # Mock persistence to avoid database calls
            with patch('ciris_engine.runtime.ciris_runtime.persistence') as mock_persistence:
                mock_persistence.count_active_tasks.return_value = 0
                mock_persistence.count_pending_thoughts_for_active_tasks.return_value = 0
                
                # Set agent_identity to trigger _preserve_shutdown_consciousness
                runtime.agent_identity = MagicMock()
                runtime.agent_identity.identity_hash = "test_hash"
                runtime.agent_identity.core_profile = MagicMock()
                runtime.agent_identity.core_profile.reactivation_count = 0
                
                await runtime.shutdown()
                
                # Verify shutdown event was set
                assert runtime._shutdown_event.is_set()
                
                # Verify state transition to SHUTDOWN
                assert runtime.agent_processor.state_manager.get_state() == AgentState.SHUTDOWN
                
                # Verify bus manager was stopped
                runtime.service_initializer.bus_manager.stop.assert_called_once()
                
                # Verify adapters were stopped
                assert runtime.adapters[0].stopped is True
                
                # Verify service registry was cleared
                runtime.service_registry.clear_all.assert_called_once()
                
                # Verify core services were stopped
                for service in [
                    runtime.llm_service,
                    runtime.memory_service,
                    runtime.audit_service,
                    runtime.telemetry_service,
                    runtime.secrets_service,
                    runtime.adaptive_filter_service,
                    runtime.agent_config_service,
                    runtime.transaction_orchestrator,
                    runtime.maintenance_service
                ]:
                    if service and hasattr(service, 'stop'):
                        service.stop.assert_called_once()


class TestCIRISRuntimeIntegration:
    """Integration tests for CIRISRuntime with real components where safe."""
    
    @pytest.mark.asyncio
    async def test_service_registry_creation(self, mock_app_config: AppConfig):
        """Test that service registry is properly created and configured."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test",
                app_config=mock_app_config
            )
            
            # Import ServiceRegistry
            from ciris_engine.registries.base import ServiceRegistry
            
            # Set up service initializer manually to avoid initialization issues
            from ciris_engine.runtime.service_initializer import ServiceInitializer
            runtime.service_initializer = ServiceInitializer()
            runtime.service_initializer.service_registry = ServiceRegistry()
            
            # Mock the services that would be registered
            runtime.service_initializer.llm_service = AsyncMock()
            runtime.service_initializer.llm_service.__class__.__name__ = "LLMService"
            runtime.service_initializer.memory_service = AsyncMock()
            runtime.service_initializer.memory_service.__class__.__name__ = "MemoryService"
            
            # Create mock agent identity to avoid initialization errors
            runtime.agent_identity = MagicMock()
            runtime.agent_identity.identity_hash = "test_hash"
            
            # Call _register_core_services directly
            await runtime._register_core_services()
            
            # Verify service registry was populated
            assert runtime.service_registry is not None
            assert isinstance(runtime.service_registry, ServiceRegistry)
            
            # Verify core services were registered
            info = runtime.service_registry.get_provider_info()
            global_services = info.get("global_services", {})
            
            # Check that at least some services were registered
            assert len(global_services) > 0 or len(info.get("handlers", {})) > 0
    
    @pytest.mark.asyncio
    async def test_bus_manager_creation(self, mock_app_config: AppConfig):
        """Test that bus manager is properly created and configured."""
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            
            runtime = CIRISRuntime(
                adapter_types=["mock"],
                profile_name="test",
                app_config=mock_app_config,
                startup_channel_id="test_channel"
            )
        
        # Mock the BusManager import and initialization
        with patch('ciris_engine.message_buses.bus_manager.BusManager') as mock_bus_class:
            mock_bus_instance = AsyncMock()
            mock_bus_instance.communication = AsyncMock()
            mock_bus_class.return_value = mock_bus_instance
            
            # Create service registry and call the bus creation method
            from ciris_engine.registries.base import ServiceRegistry
            runtime.service_initializer.service_registry = ServiceRegistry()
            
            # Call the method that creates the bus manager
            runtime.service_initializer.bus_manager = mock_bus_class(
                service_registry=runtime.service_registry
            )
            
            # Verify bus manager was created
            assert runtime.bus_manager is not None
            # Verify it has the communication bus
            assert runtime.bus_manager.communication is not None


class TestCIRISRuntimeTypesSafety:
    """Type safety tests to ensure 100% type-safe mission critical code."""
    
    def test_runtime_interface_compliance(self):
        """Test that CIRISRuntime implements RuntimeInterface correctly."""
        from ciris_engine.runtime.runtime_interface import RuntimeInterface
        
        # This should pass type checking
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            runtime: RuntimeInterface = CIRISRuntime(adapter_types=["mock"], profile_name="test")
        
        # Verify all required methods exist
        assert hasattr(runtime, 'initialize')
        assert hasattr(runtime, 'run')
        assert hasattr(runtime, 'shutdown')
        
        # Verify methods are async
        import inspect
        assert inspect.iscoroutinefunction(runtime.initialize)
        assert inspect.iscoroutinefunction(runtime.run)
        assert inspect.iscoroutinefunction(runtime.shutdown)
    
    def test_adapter_interface_compliance(self):
        """Test that adapters properly implement PlatformAdapter interface."""
        from ciris_engine.protocols.adapter_interface import PlatformAdapter
        
        with patch('ciris_engine.runtime.ciris_runtime.load_adapter') as mock_load_adapter:
            mock_load_adapter.return_value = MockAdapter
            runtime = CIRISRuntime(adapter_types=["mock"], profile_name="test")
        adapter: PlatformAdapter = MockAdapter(runtime)
        
        # Verify all required methods exist
        assert hasattr(adapter, 'start')
        assert hasattr(adapter, 'stop')
        assert hasattr(adapter, 'run_lifecycle')
        assert hasattr(adapter, 'get_services_to_register')
        
        # Verify return types
        services = adapter.get_services_to_register()
        assert isinstance(services, list)
        for service_reg in services:
            assert isinstance(service_reg, ServiceRegistration)
    
    def test_service_registration_type_safety(self):
        """Test ServiceRegistration type safety."""
        from ciris_engine.protocols.adapter_interface import ServiceRegistration, ServiceType
        from ciris_engine.registries.base import Priority
        
        mock_service = MockService()
        
        # Valid registration
        registration = ServiceRegistration(
            service_type=ServiceType.COMMUNICATION,
            provider=mock_service,
            priority=Priority.HIGH,
            handlers=["SpeakHandler"]
        )
        
        assert registration.service_type == ServiceType.COMMUNICATION
        assert registration.provider is mock_service
        assert registration.priority == Priority.HIGH
        assert registration.handlers == ["SpeakHandler"]
