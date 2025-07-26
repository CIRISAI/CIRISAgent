"""
API adapter for CIRIS v1.

Provides RESTful API and WebSocket interfaces to the CIRIS agent.
"""
import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, Callable, Awaitable
from datetime import datetime, timezone

import uvicorn
from uvicorn import Server
from fastapi import FastAPI

from ciris_engine.logic import persistence
from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.runtime.messages import IncomingMessage
from ciris_engine.schemas.telemetry.core import ServiceCorrelation, ServiceCorrelationStatus
from ciris_engine.schemas.telemetry.core import ServiceRequestData, ServiceResponseData
from ciris_engine.logic.persistence.models.correlations import (
    get_active_channels_by_adapter,
    is_admin_channel
)
from .app import create_app
from .config import APIAdapterConfig
from .api_runtime_control import APIRuntimeControlService
from .api_observer import APIObserver
from .api_communication import APICommunicationService
from .api_tools import APIToolService
from .services.auth_service import APIAuthService
from .service_configuration import ApiServiceConfiguration

logger = logging.getLogger(__name__)


class ApiPlatform(Service):
    """API adapter platform for CIRIS v1."""
    
    config: APIAdapterConfig  # type: ignore[assignment]
    
    def __init__(self, runtime: Any, **kwargs: Any) -> None:
        """Initialize API adapter."""
        super().__init__(config=kwargs.get('adapter_config'))
        self.runtime = runtime
        
        # Start with default configuration
        self.config = APIAdapterConfig()
        
        # Load environment variables first (provides defaults)
        self.config.load_env_vars()
        
        # Then apply user-provided configuration (takes precedence)
        if "adapter_config" in kwargs and kwargs["adapter_config"] is not None:
            if isinstance(kwargs["adapter_config"], APIAdapterConfig):
                self.config = kwargs["adapter_config"]
                # Still load env vars to allow env overrides
                self.config.load_env_vars()
            elif isinstance(kwargs["adapter_config"], dict):
                # Merge user config over env-loaded config
                self.config = APIAdapterConfig(**kwargs["adapter_config"])
                # Load env vars after to allow env overrides
                self.config.load_env_vars()
            # If adapter_config is provided but not dict/APIAdapterConfig, keep env-loaded config
        
        # Create FastAPI app - services will be injected later in start()
        self.app: FastAPI = create_app(runtime, self.config)
        self._server: Server | None = None
        self._server_task: asyncio.Task[Any] | None = None
        
        # Message observer for handling incoming messages (will be created in start())
        self.message_observer: APIObserver | None = None
        
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
        
        # Debug logging
        logger.info(f"[DEBUG] adapter_config in kwargs: {'adapter_config' in kwargs}")
        if 'adapter_config' in kwargs and kwargs['adapter_config'] is not None:
            logger.info(f"[DEBUG] adapter_config type: {type(kwargs['adapter_config'])}")
            if hasattr(kwargs['adapter_config'], 'host'):
                logger.info(f"[DEBUG] adapter_config.host: {kwargs['adapter_config'].host}")
        
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
        logger.info("Injecting services into FastAPI app state...")
        
        # Store adapter config for routes to access
        self.app.state.api_config = self.config
        logger.info(f"Injected API config with interaction_timeout={self.config.interaction_timeout}s")
        
        # Get service mappings from declarative configuration
        service_mappings = ApiServiceConfiguration.get_current_mappings_as_tuples()
        
        # Inject services using mapping
        for runtime_attr, app_attrs, handler_name in service_mappings:
            # Convert handler name to actual method if provided
            handler = getattr(self, handler_name) if handler_name else None
            self._inject_service(runtime_attr, app_attrs, handler)
        
        # Inject adapter-created services using configuration
        for adapter_service in ApiServiceConfiguration.ADAPTER_CREATED_SERVICES:
            service = getattr(self, adapter_service.attr_name)
            setattr(self.app.state, adapter_service.app_state_name, service)
            logger.info(f"Injected {adapter_service.app_state_name} ({adapter_service.description})")
        
        # Set up message handling
        self._setup_message_handling()
    
    def _inject_service(self, runtime_attr: str, app_state_name: str, handler: Callable[[Any], None] | None = None) -> None:
        """Inject a single service from runtime to app state."""
        runtime = self.runtime
        if hasattr(runtime, runtime_attr) and getattr(runtime, runtime_attr) is not None:
            service = getattr(runtime, runtime_attr)
            setattr(self.app.state, app_state_name, service)
            
            # Call special handler if provided
            if handler:
                handler(service)
            
            logger.info(f"Injected {runtime_attr}")
    
    def _handle_auth_service(self, auth_service: Any) -> None:
        """Special handler for authentication service."""
        # Initialize APIAuthService with the authentication service for persistence
        self.app.state.auth_service = APIAuthService(auth_service)
        logger.info("Initialized APIAuthService with authentication service for persistence")
    
    def _setup_message_handling(self) -> None:
        """Set up message handling and correlation tracking."""
        # Store message ID to channel mapping for response routing
        self.app.state.message_channel_map = {}
        
        # Create and assign message handler
        self.app.state.on_message = self._create_message_handler()
        logger.info("Set up message handler via observer pattern with correlation tracking")
    
    def _create_message_handler(self) -> Callable[[IncomingMessage], Awaitable[None]]:
        """Create the message handler function."""
        async def handle_message_via_observer(msg: IncomingMessage) -> None:
            """Handle incoming messages by creating passive observations."""
            try:
                logger.info(f"handle_message_via_observer called for message {msg.message_id}")
                if self.message_observer:
                    # Store the message ID to channel mapping
                    self.app.state.message_channel_map[msg.channel_id] = msg.message_id
                    
                    # Create correlation
                    await self._create_message_correlation(msg)
                    
                    # Pass to observer for task creation
                    await self.message_observer.handle_incoming_message(msg)
                    logger.info(f"Message {msg.message_id} passed to observer")
                else:
                    logger.error("Message observer not available")
            except Exception as e:
                logger.error(f"Error in handle_message_via_observer: {e}", exc_info=True)
        
        return handle_message_via_observer
    
    async def _create_message_correlation(self, msg: Any) -> None:
        """Create an observe correlation for incoming message."""
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

    async def start(self) -> None:
        """Start the API server."""
        logger.info(f"[DEBUG] At start() - config.host: {self.config.host}, config.port: {self.config.port}")
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
    
    def get_channel_list(self) -> List[ChannelContext]:
        """
        Get list of available API channels from correlations.
        
        Returns:
            List of ChannelContext objects for API channels.
        """
        from datetime import datetime
        
        # Get active channels from last 30 days
        channels_data = get_active_channels_by_adapter("api", since_days=30)
        
        # Convert to ChannelContext objects
        channels = []
        for data in channels_data:
            # Determine allowed actions based on admin status
            is_admin = is_admin_channel(data["channel_id"])
            allowed_actions = ["speak", "observe", "memorize", "recall", "tool"]
            if is_admin:
                allowed_actions.extend(["wa_defer", "runtime_control"])
            
            channel = ChannelContext(
                channel_id=data["channel_id"],
                channel_type="api",
                created_at=data.get("last_activity", datetime.now()),
                channel_name=data["channel_id"],  # API channels use ID as name
                is_private=False,  # API channels are not private
                participants=[],  # Could track user IDs if needed
                is_active=data.get("is_active", True),
                last_activity=data.get("last_activity"),
                message_count=data.get("message_count", 0),
                allowed_actions=allowed_actions,
                moderation_level="standard"
            )
            channels.append(channel)
        
        return channels
    
    def is_healthy(self) -> bool:
        """Check if the API server is healthy and running."""
        has_server = self._server is not None and self._server_task is not None
        if not has_server:
            return False
        
        # Check if the server task is still running
        return not self._server_task.done()
    
    async def run_lifecycle(self, agent_run_task: asyncio.Task[Any]) -> None:
        """Run the adapter lifecycle - API runs until agent stops."""
        logger.info("API adapter running lifecycle")
        
        try:
            # Wait for either the agent task or server task to complete
            while not agent_run_task.done():
                # Check if server is still running
                if not self._server_task or not self._server_task.done():
                    await asyncio.sleep(0.1)
                    continue
                    
                # Server stopped unexpectedly
                exc = self._server_task.exception()
                if exc:
                    logger.error(f"API server stopped with error: {exc}")
                    raise exc
                
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