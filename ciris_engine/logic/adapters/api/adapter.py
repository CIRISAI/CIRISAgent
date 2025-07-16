"""
API adapter for CIRIS v1.

Provides RESTful API and WebSocket interfaces to the CIRIS agent.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import uvicorn
from uvicorn import Server
from fastapi import FastAPI

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.enums import ServiceType
from .app import create_app
from .config import APIAdapterConfig
from .api_runtime_control import APIRuntimeControlService
from .api_observer import APIObserver
from .api_communication import APICommunicationService
from .api_tools import APIToolService
from .services.auth_service import APIAuthService

logger = logging.getLogger(__name__)


class ApiPlatform(Service):
    """API adapter platform for CIRIS v1."""
    
    config: APIAdapterConfig  # type: ignore[assignment]
    
    def __init__(self, runtime: Any, **kwargs: Any) -> None:
        """Initialize API adapter."""
        super().__init__(config=kwargs.get('adapter_config'))
        self.runtime = runtime
        
        # Parse configuration
        if "adapter_config" in kwargs and kwargs["adapter_config"] is not None:
            if isinstance(kwargs["adapter_config"], APIAdapterConfig):
                self.config = kwargs["adapter_config"]
            elif isinstance(kwargs["adapter_config"], dict):
                self.config = APIAdapterConfig(**kwargs["adapter_config"])
            else:
                self.config = APIAdapterConfig()
        else:
            self.config = APIAdapterConfig()
        
        # Load environment variables
        self.config.load_env_vars()
        
        # Create FastAPI app - services will be injected later in start()
        self.app: FastAPI = create_app(runtime, self.config)
        self._server: Optional[Server] = None
        self._server_task: Optional[asyncio.Task[Any]] = None
        
        # Message observer for handling incoming messages (will be created in start())
        self.message_observer: Optional[APIObserver] = None
        
        # Communication service for API responses
        self.communication = APICommunicationService(config=self.config)
        # Pass time service if available
        if hasattr(runtime, 'time_service'):
            self.communication._time_service = runtime.time_service
        # Pass app state reference for message tracking
        self.communication._app_state = self.app.state  # type: ignore[attr-defined]
        
        # Runtime control service
        self.runtime_control = APIRuntimeControlService(runtime)
        
        # Tool service
        self.tool_service = APIToolService(
            time_service=getattr(runtime, 'time_service', None)
        )
        
        logger.info(
            f"API adapter initialized - host: {self.config.host}, "
            f"port: {self.config.port}"
        )
    
    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        registrations = []
        
        # Register communication service with all capabilities
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.communication,
                priority=Priority.CRITICAL,
                capabilities=['send_message', 'fetch_messages']
            )
        )
        
        # Register runtime control service
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.RUNTIME_CONTROL,
                provider=self.runtime_control,
                priority=Priority.CRITICAL,
                capabilities=['pause_processing', 'resume_processing', 'request_state_transition', 'get_runtime_status']
            )
        )
        
        # Register tool service
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.CRITICAL,
                capabilities=['execute_tool', 'get_available_tools', 'get_tool_result', 'validate_parameters', 'get_tool_info', 'get_all_tool_info']
            )
        )
        
        return registrations
    
    def _inject_services(self) -> None:
        """Inject services into FastAPI app state after initialization."""
        runtime = self.runtime
        logger.info("Injecting services into FastAPI app state...")
        
        # Store adapter config for routes to access
        self.app.state.api_config = self.config
        logger.info(f"Injected API config with interaction_timeout={self.config.interaction_timeout}s")
        
        # Store commonly accessed services
        if hasattr(runtime, 'memory_service') and runtime.memory_service is not None:
            self.app.state.memory_service = runtime.memory_service
            logger.info("Injected memory_service")
        if hasattr(runtime, 'time_service') and runtime.time_service is not None:
            self.app.state.time_service = runtime.time_service
            logger.info("Injected time_service")
        if hasattr(runtime, 'telemetry_service') and runtime.telemetry_service is not None:
            self.app.state.telemetry_service = runtime.telemetry_service
            logger.info("Injected telemetry_service")
        if hasattr(runtime, 'audit_service') and runtime.audit_service is not None:
            self.app.state.audit_service = runtime.audit_service
            logger.info("Injected audit_service")
        if hasattr(runtime, 'config_service') and runtime.config_service is not None:
            self.app.state.config_service = runtime.config_service
            logger.info("Injected config_service")
        if hasattr(runtime, 'wa_auth_system') and runtime.wa_auth_system is not None:
            self.app.state.wise_authority_service = runtime.wa_auth_system
            self.app.state.wa_service = runtime.wa_auth_system
            logger.info("Injected wise_authority_service")
        if hasattr(runtime, 'resource_monitor') and runtime.resource_monitor is not None:
            self.app.state.resource_monitor = runtime.resource_monitor
            logger.info("Injected resource_monitor")
        if hasattr(runtime, 'task_scheduler') and runtime.task_scheduler is not None:
            self.app.state.task_scheduler = runtime.task_scheduler
            logger.info("Injected task_scheduler")
        if hasattr(runtime, 'authentication_service') and runtime.authentication_service is not None:
            self.app.state.authentication_service = runtime.authentication_service
            logger.info("Injected authentication_service")
            
            # Re-initialize APIAuthService with the authentication service for persistence
            self.app.state.auth_service = APIAuthService(runtime.authentication_service)
            logger.info("Re-initialized APIAuthService with authentication service for persistence")
        if hasattr(runtime, 'incident_management_service') and runtime.incident_management_service is not None:
            self.app.state.incident_management_service = runtime.incident_management_service
            logger.info("Injected incident_management_service")
        if hasattr(runtime, 'service_registry') and runtime.service_registry is not None:
            self.app.state.service_registry = runtime.service_registry
            logger.info("Injected service_registry")
        
        # Inject both runtime control services
        # Main runtime control service for adapter/tool management
        if hasattr(runtime, 'runtime_control_service') and runtime.runtime_control_service is not None:
            self.app.state.main_runtime_control_service = runtime.runtime_control_service
            logger.info("Injected main runtime_control_service from runtime")
        
        # API's runtime control service (which accepts reason parameter for pause/resume)
        self.app.state.runtime_control_service = self.runtime_control
        logger.info("Injected API runtime_control_service")
        
        # Inject communication service created by adapter
        self.app.state.communication_service = self.communication
        logger.info("Injected communication_service")
        
        # Store message ID to channel mapping for response routing
        self.app.state.message_channel_map = {}
        
        # Set up message handler to use the message observer and create correlations
        async def handle_message_via_observer(msg: Any) -> None:
            """Handle incoming messages by creating passive observations."""
            try:
                logger.info(f"handle_message_via_observer called for message {msg.message_id}")
                if self.message_observer:
                    # Store the message ID to channel mapping
                    self.app.state.message_channel_map[msg.channel_id] = msg.message_id
                    # Create an "observe" correlation for this incoming message
                    from ciris_engine.logic import persistence
                    from ciris_engine.schemas.telemetry.core import ServiceCorrelation, ServiceCorrelationStatus
                    from ciris_engine.schemas.telemetry.core import ServiceRequestData, ServiceResponseData
                    import uuid
                    from datetime import datetime, timezone
                    
                    correlation_id = str(uuid.uuid4())
                    now = datetime.now(timezone.utc)
                    
                    # Create correlation for the incoming message
                    correlation = ServiceCorrelation(
                        correlation_id=correlation_id,
                        service_type="api",
                        handler_name="APIAdapter",
                        action_type="observe",
                        request_data=ServiceRequestData(
                            service_type="api",
                            method_name="observe",
                            channel_id=msg.channel_id,
                            parameters={
                                "content": msg.content,
                                "author_id": msg.author_id,
                                "author_name": msg.author_name,
                                "message_id": msg.message_id
                            },
                            request_timestamp=now
                        ),
                        response_data=ServiceResponseData(
                            success=True,
                            result_summary="Message observed",
                            execution_time_ms=0,
                            response_timestamp=now
                        ),
                        status=ServiceCorrelationStatus.COMPLETED,
                        created_at=now,
                        updated_at=now,
                        timestamp=now
                    )
                    
                    # Get time service if available
                    time_service = getattr(self.runtime, 'time_service', None)
                    persistence.add_correlation(correlation, time_service)
                    logger.debug(f"Created observe correlation for message {msg.message_id}")
                    
                    # Pass to observer for task creation
                    await self.message_observer.handle_incoming_message(msg)
                    logger.info(f"Message {msg.message_id} passed to observer")
                else:
                    logger.error("Message observer not available")
            except Exception as e:
                logger.error(f"Error in handle_message_via_observer: {e}", exc_info=True)
        
        self.app.state.on_message = handle_message_via_observer
        logger.info("Set up message handler via observer pattern with correlation tracking")
        if hasattr(runtime, 'agent_processor') and runtime.agent_processor is not None:
            self.app.state.agent_processor = runtime.agent_processor
            logger.info("Injected agent_processor")
        if hasattr(runtime, 'message_handler') and runtime.message_handler is not None:
            self.app.state.message_handler = runtime.message_handler
            logger.info("Injected message_handler")
        
        # Inject missing services
        if hasattr(runtime, 'shutdown_service') and runtime.shutdown_service is not None:
            self.app.state.shutdown_service = runtime.shutdown_service
            logger.info("Injected shutdown_service")
        if hasattr(runtime, 'initialization_service') and runtime.initialization_service is not None:
            self.app.state.initialization_service = runtime.initialization_service
            logger.info("Injected initialization_service")
        if hasattr(runtime, 'tsdb_consolidation_service') and runtime.tsdb_consolidation_service is not None:
            self.app.state.tsdb_service = runtime.tsdb_consolidation_service
            logger.info("Injected tsdb_service")
        if hasattr(runtime, 'secrets_service') and runtime.secrets_service is not None:
            self.app.state.secrets_service = runtime.secrets_service
            logger.info("Injected secrets_service")
        if hasattr(runtime, 'adaptive_filter_service') and runtime.adaptive_filter_service is not None:
            self.app.state.adaptive_filter = runtime.adaptive_filter_service
            logger.info("Injected adaptive_filter")
        
        # Check for visibility and self_config services
        if hasattr(runtime, 'visibility_service') and runtime.visibility_service is not None:
            self.app.state.visibility_service = runtime.visibility_service
            logger.info("Injected visibility_service")
        if hasattr(runtime, 'self_observation_service') and runtime.self_observation_service is not None:
            self.app.state.self_observation_service = runtime.self_observation_service
            logger.info("Injected self_observation_service")
        
        # Inject missing services
        if hasattr(runtime, 'database_maintenance') and runtime.database_maintenance is not None:
            self.app.state.database_maintenance = runtime.database_maintenance
            logger.info("Injected database_maintenance")
        if hasattr(runtime, 'database_maintenance_service') and runtime.database_maintenance_service is not None:
            self.app.state.database_maintenance_service = runtime.database_maintenance_service
            logger.info("Injected database_maintenance_service")
        if hasattr(runtime, 'secrets_tool') and runtime.secrets_tool is not None:
            self.app.state.secrets_tool = runtime.secrets_tool
            logger.info("Injected secrets_tool")
        if hasattr(runtime, 'secrets_tool_service') and runtime.secrets_tool_service is not None:
            self.app.state.secrets_tool_service = runtime.secrets_tool_service
            logger.info("Injected secrets_tool_service")
        if hasattr(runtime, 'llm_service') and runtime.llm_service is not None:
            self.app.state.llm_service = runtime.llm_service
            logger.info("Injected llm_service")

    async def start(self) -> None:
        """Start the API server."""
        await super().start()
        
        # Start the communication service
        await self.communication.start()
        logger.info("Started API communication service")
        
        # Start the tool service
        await self.tool_service.start()
        logger.info("Started API tool service")
        
        # Create message observer for handling incoming messages
        self.message_observer = APIObserver(
            on_observe=lambda _: asyncio.sleep(0),
            bus_manager=getattr(self.runtime, 'bus_manager', None),
            memory_service=getattr(self.runtime, 'memory_service', None),
            agent_id=getattr(self.runtime, 'agent_id', None),
            filter_service=getattr(self.runtime, 'adaptive_filter_service', None),
            secrets_service=getattr(self.runtime, 'secrets_service', None),
            time_service=getattr(self.runtime, 'time_service', None),
            origin_service="api"
        )
        await self.message_observer.start()
        logger.info("Started API message observer")
        
        # Inject services now that they're initialized
        self._inject_services()
        
        # Start runtime control service now that services are available
        await self.runtime_control.start()
        logger.info("Started API runtime control service")
        
        
        # Configure uvicorn
        config = uvicorn.Config(
            self.app,
            host=self.config.host,
            port=self.config.port,
            log_level="info",
            access_log=True
        )
        
        # Create and start server
        self._server = uvicorn.Server(config)
        assert self._server is not None
        self._server_task = asyncio.create_task(self._server.serve())
        
        logger.info(
            f"API server starting on http://{self.config.host}:{self.config.port}"
        )
        
        # Wait a moment for server to start
        await asyncio.sleep(1)
    
    async def stop(self) -> None:
        """Stop the API server."""
        logger.info("Stopping API server...")
        
        # Stop runtime control service
        await self.runtime_control.stop()
        
        # Stop communication service
        await self.communication.stop()
        
        # Stop tool service
        await self.tool_service.stop()
        
        
        # Stop server
        if self._server:
            self._server.should_exit = True
            if self._server_task:
                await self._server_task
        
        await super().stop()
    
    def get_channel_list(self) -> List[Dict[str, Any]]:
        """
        Get list of available API channels from correlations.
        
        Returns:
            List of channel information dicts with:
            - channel_id: str
            - channel_name: Optional[str]
            - channel_type: str (always "api")
            - is_active: bool
            - last_activity: Optional[datetime]
            - is_admin: bool (whether channel belongs to admin user)
        """
        from ciris_engine.logic.persistence.models.correlations import (
            get_active_channels_by_adapter,
            is_admin_channel
        )
        
        # Get active channels from last 30 days
        channels = get_active_channels_by_adapter("api", since_days=30)
        
        # Enhance with admin status
        for channel in channels:
            channel["channel_name"] = channel["channel_id"]  # API channels use ID as name
            channel["is_admin"] = is_admin_channel(channel["channel_id"])
        
        return channels
    
    def is_healthy(self) -> bool:
        """Check if the API server is healthy and running."""
        if self._server is None or self._server_task is None:
            return False
        
        # Check if the server task is still running
        return not self._server_task.done()
    
    async def run_lifecycle(self, agent_run_task: asyncio.Task) -> None:
        """Run the adapter lifecycle - API runs until agent stops."""
        logger.info("API adapter running lifecycle")
        
        try:
            # Wait for either the agent task or server task to complete
            while not agent_run_task.done():
                # Check if server is still running
                if self._server_task and self._server_task.done():
                    # Server stopped unexpectedly
                    exc = self._server_task.exception()
                    if exc:
                        logger.error(f"API server stopped with error: {exc}")
                        raise exc
                    else:
                        logger.warning("API server stopped unexpectedly")
                        break
                
                # Wait for a short time before checking again
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("API adapter lifecycle cancelled")
            raise
        except Exception as e:
            logger.error(f"API adapter lifecycle error: {e}")
            raise
        finally:
            logger.info("API adapter lifecycle ending")