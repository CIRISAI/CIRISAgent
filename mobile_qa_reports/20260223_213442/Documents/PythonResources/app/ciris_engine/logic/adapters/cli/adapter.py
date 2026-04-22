import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.adapters.runtime_context import AdapterStartupContext
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import IncomingMessage

from .cli_adapter import CLIAdapter
from .cli_observer import CLIObserver
from .config import CLIAdapterConfig

logger = logging.getLogger(__name__)


class CliPlatform(Service):
    config: CLIAdapterConfig  # type: ignore[assignment]

    def __init__(self, runtime: Any, context: Optional["AdapterStartupContext"] = None, **kwargs: Any) -> None:
        # Initialize the parent Service class
        from ciris_engine.schemas.adapters.runtime_context import AdapterStartupContext

        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime

        # Generate stable adapter_id for observer persistence
        import os
        import socket

        # This adapter_id is used by AuthenticationService to find/create observer certificates
        self.adapter_id = f"cli_{os.getenv('USER', 'unknown')}@{socket.gethostname()}"
        logger.info(f"CLI adapter initialized with adapter_id: {self.adapter_id}")

        if "adapter_config" in kwargs and kwargs["adapter_config"] is not None:
            # Ensure config is a CLIAdapterConfig instance
            if isinstance(kwargs["adapter_config"], CLIAdapterConfig):
                self.config = kwargs["adapter_config"]
            elif isinstance(kwargs["adapter_config"], dict):
                self.config = CLIAdapterConfig(**kwargs["adapter_config"])
            else:
                self.config = CLIAdapterConfig()

            # ALWAYS load environment variables to fill in any missing values
            self.config.load_env_vars()
            logger.info(
                f"CLI adapter using provided config with env vars loaded: interactive={self.config.interactive}"
            )
        else:
            self.config = CLIAdapterConfig()
            if "interactive" in kwargs:
                self.config.interactive = bool(kwargs["interactive"])

            template = getattr(runtime, "template", None)
            if template and hasattr(template, "cli_config") and template.cli_config:
                try:
                    config_dict = template.cli_config.model_dump() if hasattr(template.cli_config, "model_dump") else {}
                    for key, value in config_dict.items():
                        if hasattr(self.config, key):
                            setattr(self.config, key, value)
                            logger.debug(f"CliPlatform: Set config {key} = {value} from template")
                except Exception as e:
                    logger.debug(f"CliPlatform: Could not load config from template: {e}")

            self.config.load_env_vars()

        self.cli_adapter = CLIAdapter(
            runtime=runtime,
            interactive=self.config.interactive,
            on_message=self._handle_incoming_message,
            bus_manager=getattr(runtime, "bus_manager", None),
            config=self.config,
        )
        logger.info(f"CliPlatform created CLIAdapter instance: {id(self.cli_adapter)}")

        # CLI observer will be created in start() when services are available
        self.cli_observer: Optional[CLIObserver] = None
        self.on_observe = self._handle_incoming_message
        self.bus_manager = getattr(runtime, "bus_manager", None)
        self.observer_wa_id = None  # Will be set by auth service if available

    async def _handle_incoming_message(self, msg: IncomingMessage) -> None:
        """Handle incoming messages from the CLI adapter by routing through observer."""
        logger.debug(f"CliPlatform: Received message: {msg.message_id}")

        if not self.cli_observer:
            logger.warning("CliPlatform: CLIObserver not available.")
            return

        # msg is already typed as IncomingMessage
        try:
            await self.cli_observer.handle_incoming_message(msg)
            logger.debug("CliPlatform: Message sent to CLIObserver")
        except Exception as e:
            logger.error(f"CliPlatform: Error handling message: {e}", exc_info=True)

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Register CLI services."""
        logger.info(f"CliPlatform get_services_to_register: registering cli_adapter instance {id(self.cli_adapter)}")
        registrations = [
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.cli_adapter,  # The actual service instance
                priority=Priority.LOW,
                handlers=["SpeakHandler", "ObserveHandler"],  # Specific handlers
                capabilities=["send_message", "fetch_messages"],
            ),
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.cli_adapter,  # CLI adapter handles tools too
                priority=Priority.LOW,
                handlers=["ToolHandler"],
                capabilities=["execute_tool", "get_available_tools", "get_tool_result", "validate_parameters"],
            ),
            AdapterServiceRegistration(
                service_type=ServiceType.WISE_AUTHORITY,
                provider=self.cli_adapter,  # CLI adapter can handle WA too
                priority=Priority.LOW,
                handlers=["DeferHandler", "SpeakHandler"],
                capabilities=["fetch_guidance", "send_deferral"],
            ),
        ]
        logger.info(f"CliPlatform: Registering {len(registrations)} services for adapter: {self.adapter_id}")
        return registrations

    async def start(self) -> None:
        """Start the CLI adapter and observer."""
        logger.info("CliPlatform: Starting...")

        # Create CLI observer now that services are available
        if not self.cli_observer:
            logger.info("Creating CLI observer with available services")
            # Get services from runtime's service_initializer
            service_initializer = getattr(self.runtime, "service_initializer", None)
            if service_initializer:
                self.cli_observer = CLIObserver(
                    on_observe=self.on_observe,  # type: ignore[arg-type]
                    bus_manager=self.bus_manager,
                    memory_service=getattr(service_initializer, "memory_service", None),
                    agent_id=getattr(self.runtime, "agent_id", None),
                    filter_service=getattr(service_initializer, "filter_service", None),
                    secrets_service=getattr(service_initializer, "secrets_service", None),
                    time_service=getattr(service_initializer, "time_service", None),
                    interactive=self.config.interactive,
                    config=self.config,
                )
                logger.info(
                    f"Created CLI observer with secrets_service: {service_initializer.secrets_service is not None}"
                )
            else:
                logger.error("No service_initializer available - cannot create CLI observer")
                raise RuntimeError("Service initializer not available")

        await self.cli_adapter.start()
        if self.cli_observer:
            await self.cli_observer.start()
        logger.info("CliPlatform: Started.")

    async def run_lifecycle(self, agent_run_task: asyncio.Task[Any]) -> None:
        """Run the CLI platform lifecycle."""
        logger.info("CliPlatform: Running lifecycle.")

        # Create tasks to monitor
        tasks = [agent_run_task]

        # If we have an observer, monitor its stop event
        if self.cli_observer and hasattr(self.cli_observer, "_stop_event"):
            stop_event_task = asyncio.create_task(self.cli_observer._stop_event.wait(), name="CLIObserverStopEvent")
            tasks.append(stop_event_task)

        try:
            # Wait for either agent task to complete or observer to signal stop
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            # Check what completed
            for task in done:
                if task.get_name() == "CLIObserverStopEvent":
                    logger.info("CliPlatform: Observer signaled stop (non-interactive mode)")
                    # Request global shutdown
                    from ciris_engine.logic.utils.shutdown_manager import request_global_shutdown

                    request_global_shutdown("CLI non-interactive mode completed")
                elif task == agent_run_task:
                    logger.info("CliPlatform: Agent run task completed")

            # Cancel any remaining tasks
            for task in pending:
                if not task.done():
                    task.cancel()

        except asyncio.CancelledError:
            logger.info("CliPlatform: Lifecycle was cancelled.")
            raise
        except Exception as e:
            logger.error(f"CliPlatform: Lifecycle error: {e}", exc_info=True)
        finally:
            logger.info("CliPlatform: Lifecycle ending.")

    async def stop(self) -> None:
        """Stop the CLI adapter and observer."""
        logger.info("CliPlatform: Stopping...")
        if self.cli_observer:
            await self.cli_observer.stop()
        await self.cli_adapter.stop()
        logger.info("CliPlatform: Stopped.")
