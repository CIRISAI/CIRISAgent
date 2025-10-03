import asyncio
import logging
from typing import Any, Dict, List, Optional

import discord  # Ensure discord.py is available

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.adapters.discord.discord_adapter import DiscordAdapter
from ciris_engine.logic.adapters.discord.discord_observer import DiscordObserver
from ciris_engine.logic.adapters.discord.discord_tool_service import DiscordToolService
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.adapters.discord import DiscordChannelInfo
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import DiscordMessage

from .config import DiscordAdapterConfig

# from ciris_engine.logic.adapters.discord.discord_tools import register_discord_tools

logger = logging.getLogger(__name__)


class DiscordPlatform(Service):
    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        from ciris_engine.schemas.adapters.runtime_context import AdapterStartupContext

        self.runtime = runtime
        self.context = context
        self.config: DiscordAdapterConfig  # type: ignore[assignment]

        if "adapter_config" in kwargs and kwargs["adapter_config"] is not None:
            # Ensure adapter_config is a DiscordAdapterConfig instance
            adapter_config = kwargs["adapter_config"]
            if isinstance(adapter_config, DiscordAdapterConfig):
                self.config = adapter_config
            elif isinstance(adapter_config, dict):
                self.config = DiscordAdapterConfig(**adapter_config)
            else:
                logger.warning(f"Invalid adapter_config type: {type(adapter_config)}. Creating default config.")
                self.config = DiscordAdapterConfig()

            # ALWAYS load environment variables to fill in any missing values
            logger.info(
                f"DEBUG: Before load_env_vars in adapter_config branch, monitored_channel_ids = {self.config.monitored_channel_ids}"
            )
            self.config.load_env_vars()
            logger.info(
                f"Discord adapter using provided config with env vars loaded: channels={self.config.monitored_channel_ids}"
            )
        else:
            # Check if config values are passed directly as kwargs (from API load_adapter)
            if "bot_token" in kwargs or "channel_id" in kwargs or "server_id" in kwargs:
                # Create config from direct kwargs
                config_dict = {}
                if "bot_token" in kwargs:
                    config_dict["bot_token"] = kwargs["bot_token"]
                if "channel_id" in kwargs:
                    config_dict["monitored_channel_ids"] = [kwargs["channel_id"]]
                    config_dict["home_channel_id"] = kwargs["channel_id"]
                if "server_id" in kwargs:
                    config_dict["server_id"] = kwargs["server_id"]
                # Add other config fields if present
                for key in ["deferral_channel_id", "admin_user_ids"]:
                    if key in kwargs:
                        config_dict[key] = kwargs[key]

                self.config = DiscordAdapterConfig(**config_dict)
                logger.info(
                    f"Discord adapter created config from direct kwargs: bot_token={'***' if self.config.bot_token else 'None'}, channels={self.config.monitored_channel_ids}"
                )
            else:
                self.config = DiscordAdapterConfig()
                if "discord_bot_token" in kwargs:
                    self.config.bot_token = kwargs["discord_bot_token"]

            template = getattr(runtime, "template", None)
            if template and hasattr(template, "discord_config") and template.discord_config:
                try:
                    config_dict = (
                        template.discord_config.model_dump() if hasattr(template.discord_config, "model_dump") else {}
                    )
                    for key, value in config_dict.items():
                        if hasattr(self.config, key):
                            setattr(self.config, key, value)
                            logger.debug(f"DiscordPlatform: Set config {key} = {value} from template")
                except Exception as e:
                    logger.debug(f"DiscordPlatform: Could not load config from template: {e}")

            self.config.load_env_vars()
            logger.info(
                f"DEBUG: After load_env_vars in else branch, monitored_channel_ids = {self.config.monitored_channel_ids}"
            )

        if not self.config.bot_token:
            logger.error("DiscordPlatform: 'bot_token' not found in config. This is required.")
            raise ValueError("DiscordPlatform requires 'bot_token' in configuration.")

        self.token = self.config.bot_token
        intents = self.config.get_intents()

        # Create a custom client class to handle events properly
        class CIRISDiscordClient(discord.Client):
            def __init__(self, platform: "DiscordPlatform", *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                self.platform = platform

            async def on_ready(self) -> None:
                """Called when the client is ready."""
                logger.info("Discord client on_ready event")
                # Let the connection manager know
                if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
                    conn_mgr = self.platform.discord_adapter._connection_manager
                    if conn_mgr and hasattr(conn_mgr, "_handle_connected"):
                        await conn_mgr._handle_connected()

                # Fetch and monitor threads in monitored channels
                await self._fetch_threads_in_monitored_channels()

            async def _fetch_threads_in_monitored_channels(self) -> None:
                """Fetch all threads in monitored channels and add them to monitoring."""
                if not (hasattr(self.platform, "config") and self.platform.config):
                    return

                logger.info("Fetching threads in monitored channels...")
                threads_added = 0

                for channel_id in self.platform.config.monitored_channel_ids:
                    try:
                        channel = self.get_channel(int(channel_id))
                        if channel and isinstance(channel, discord.TextChannel):
                            # Get active threads in this channel
                            for thread in channel.threads:
                                thread_id = str(thread.id)
                                # Add to observer if it exists and not already monitored
                                if hasattr(self.platform, "discord_observer") and self.platform.discord_observer:
                                    if thread_id not in self.platform.discord_observer.monitored_channel_ids:
                                        self.platform.discord_observer.monitored_channel_ids.append(thread_id)
                                        threads_added += 1
                                        logger.debug(f"Added thread {thread_id} to monitoring")
                    except Exception as e:
                        logger.warning(f"Could not fetch threads for channel {channel_id}: {e}")

                if threads_added > 0:
                    logger.info(f"Added {threads_added} threads to monitoring")

            async def on_disconnect(self) -> None:
                """Called when the client disconnects."""
                logger.warning("Discord client on_disconnect event")
                # Let the connection manager know
                if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
                    conn_mgr = self.platform.discord_adapter._connection_manager
                    if conn_mgr and hasattr(conn_mgr, "_handle_disconnected"):
                        await conn_mgr._handle_disconnected(None)

            async def on_message(self, message: discord.Message) -> None:
                """Called when a message is received."""
                # Let the channel manager handle it
                if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
                    channel_mgr = self.platform.discord_adapter._channel_manager
                    if channel_mgr and hasattr(channel_mgr, "on_message"):
                        await channel_mgr.on_message(message)

            async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
                """Called when a reaction is added."""
                # Let the discord adapter handle it
                if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
                    await self.platform.discord_adapter.on_raw_reaction_add(payload)

            async def on_thread_create(self, thread: discord.Thread) -> None:
                """Called when a thread is created."""
                logger.info(f"Thread created: {thread.name} (ID: {thread.id}) in parent {thread.parent_id}")
                # Check if parent channel is monitored
                if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
                    if hasattr(self.platform, "discord_observer") and self.platform.discord_observer:
                        observer = self.platform.discord_observer
                        if hasattr(self.platform, "config") and self.platform.config:
                            parent_id = str(thread.parent_id)
                            if parent_id in self.platform.config.monitored_channel_ids:
                                # Add thread to monitored channels
                                thread_id = str(thread.id)
                                if thread_id not in observer.monitored_channel_ids:
                                    observer.monitored_channel_ids.append(thread_id)
                                    logger.info(
                                        f"Added thread {thread_id} to monitored channels (parent {parent_id} is monitored)"
                                    )

                                    # Thread correlation persistence would require ServiceCorrelation,
                                    # not CorrelationRequestData. This needs proper implementation
                                    # with correlation_id, service_type, handler_name, etc.
                                    # For now, in-memory tracking is sufficient for Discord threads.

            async def on_thread_join(self, thread: discord.Thread) -> None:
                """Called when the bot joins a thread."""
                logger.info(f"Bot joined thread: {thread.name} (ID: {thread.id})")
                # Use same logic as on_thread_create
                await self.on_thread_create(thread)

            async def on_thread_delete(self, thread: discord.Thread) -> None:
                """Called when a thread is deleted."""
                logger.info(f"Thread deleted: {thread.name} (ID: {thread.id})")
                # Remove from monitored channels if present
                if hasattr(self.platform, "discord_observer") and self.platform.discord_observer:
                    observer = self.platform.discord_observer
                    thread_id = str(thread.id)
                    if thread_id in observer.monitored_channel_ids:
                        observer.monitored_channel_ids.remove(thread_id)
                        logger.info(f"Removed deleted thread {thread_id} from monitored channels")

        # Create Discord client without explicit loop (discord.py will manage it)
        self.client = CIRISDiscordClient(platform=self, intents=intents)

        # Generate adapter_id - will be updated with actual guild_id when bot connects
        # The adapter_id is used by AuthenticationService for observer persistence
        self.adapter_id = "discord_pending"

        # Get time_service from runtime
        time_service = getattr(self.runtime, "time_service", None)

        # Get bus_manager from runtime
        bus_manager = getattr(self.runtime, "bus_manager", None)

        # Create tool service for Discord tools
        self.tool_service = DiscordToolService(client=self.client, time_service=time_service)

        self.discord_adapter = DiscordAdapter(
            token=self.token,
            bot=self.client,
            on_message=self._handle_discord_message_event,  # type: ignore[arg-type]
            time_service=time_service,
            bus_manager=bus_manager,
            config=self.config,
        )

        if hasattr(self.discord_adapter, "attach_to_client"):
            self.discord_adapter.attach_to_client(self.client)
        else:
            logger.warning("DiscordPlatform: DiscordAdapter may not have 'attach_to_client' method.")

        kwargs_channel_ids = kwargs.get("discord_monitored_channel_ids", [])
        kwargs_channel_id = kwargs.get("discord_monitored_channel_id")

        if kwargs_channel_ids:
            self.config.monitored_channel_ids.extend(kwargs_channel_ids)
        if kwargs_channel_id and kwargs_channel_id not in self.config.monitored_channel_ids:
            self.config.monitored_channel_ids.append(kwargs_channel_id)
            if not self.config.home_channel_id:
                self.config.home_channel_id = kwargs_channel_id

        if not self.config.monitored_channel_ids:
            logger.warning(
                "DiscordPlatform: No channel configuration found. Please provide channel IDs via constructor kwargs or environment variables."
            )

        if self.config.monitored_channel_ids:
            logger.info(
                f"DiscordPlatform: Using {len(self.config.monitored_channel_ids)} channels: {self.config.monitored_channel_ids}"
            )

        # Initialize observer as None - will be created in start() when services are ready
        self.discord_observer: Optional[DiscordObserver] = None

        # Tool registry removed - tools are handled through ToolBus
        # self.tool_registry = ToolRegistry()
        # register_discord_tools(self.tool_registry, self.client)

        # if hasattr(self.discord_adapter, 'tool_registry'):
        #     self.discord_adapter.tool_registry = self.tool_registry

        self._discord_client_task: Optional[asyncio.Task[Any]] = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10

    def get_channel_info(self) -> Dict[str, str]:
        """Provide guild info for authentication."""
        # Get first guild if connected
        try:
            if self.client and hasattr(self.client, "guilds") and self.client.guilds:
                guild_id = str(self.client.guilds[0].id)
                # Update adapter_id with actual guild for observer persistence
                self.adapter_id = f"discord_{guild_id}"
                logger.info(f"Discord adapter updated with guild-specific adapter_id: {self.adapter_id}")
                return {"guild_id": guild_id}
        except (AttributeError, IndexError, TypeError) as e:
            logger.debug(f"Could not get guild info: {e}")
        return {"guild_id": "unknown"}

    async def _handle_discord_message_event(self, msg: DiscordMessage) -> None:
        logger.debug(f"DiscordPlatform: Received message from DiscordAdapter: {msg.message_id if msg else 'None'}")
        if not self.discord_observer:
            logger.warning("DiscordPlatform: DiscordObserver not available.")
            return
        # msg is already typed as DiscordMessage
        await self.discord_observer.handle_incoming_message(msg)

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Register Discord services."""
        comm_handlers = ["SpeakHandler", "ObserveHandler", "ToolHandler"]
        wa_handlers = ["DeferHandler", "SpeakHandler"]

        registrations = [
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.discord_adapter,
                priority=Priority.NORMAL,
                handlers=comm_handlers,
                capabilities=["send_message", "fetch_messages"],
            ),
            AdapterServiceRegistration(
                service_type=ServiceType.WISE_AUTHORITY,
                provider=self.discord_adapter,
                priority=Priority.NORMAL,
                handlers=wa_handlers,
                capabilities=["fetch_guidance", "send_deferral"],
            ),
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                handlers=["ToolHandler"],
                capabilities=[
                    "execute_tool",
                    "get_available_tools",
                    "get_tool_result",
                    "validate_parameters",
                    "get_tool_info",
                    "get_all_tool_info",
                ],
            ),
        ]
        logger.info(f"DiscordPlatform: Registering {len(registrations)} services for adapter: {self.adapter_id}")
        return registrations

    async def start(self) -> None:
        logger.info("DiscordPlatform: Starting internal components...")

        # Create observer now that services are available
        secrets_service = getattr(self.runtime, "secrets_service", None)
        if not secrets_service:
            logger.error("CRITICAL: secrets_service not available at start time!")
        else:
            logger.info("Found secrets_service from runtime")

        # Get time_service from runtime
        time_service = getattr(self.runtime, "time_service", None)

        logger.info(
            f"DEBUG: About to create DiscordObserver with monitored_channel_ids = {self.config.monitored_channel_ids}"
        )
        self.discord_observer = DiscordObserver(
            monitored_channel_ids=self.config.monitored_channel_ids,
            deferral_channel_id=self.config.deferral_channel_id,
            wa_user_ids=self.config.admin_user_ids,
            memory_service=getattr(self.runtime, "memory_service", None),
            agent_id=getattr(self.runtime, "agent_id", None),
            bus_manager=getattr(self.runtime, "bus_manager", None),
            filter_service=getattr(self.runtime, "adaptive_filter_service", None),
            secrets_service=secrets_service,
            communication_service=self.discord_adapter,
            time_service=time_service,
        )

        # Secrets tools are now registered globally by SecretsToolService

        if hasattr(self.discord_observer, "start"):
            if self.discord_observer:
                await self.discord_observer.start()
        if self.tool_service and hasattr(self.tool_service, "start"):
            await self.tool_service.start()
        if hasattr(self.discord_adapter, "start"):
            await self.discord_adapter.start()
        logger.info(
            "DiscordPlatform: Internal components started. Discord client connection deferred to run_lifecycle."
        )

    async def _wait_for_discord_reconnect(self) -> None:
        """Wait for Discord.py to reconnect automatically."""
        logger.info("Waiting for Discord.py to handle reconnection...")

        # Discord.py handles reconnection internally when using start() with reconnect=True
        # We just need to wait for the client to be ready again
        max_wait = 300  # 5 minutes max
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < max_wait:
            if self.client and not self.client.is_closed() and self.client.is_ready():
                logger.info(f"Discord client reconnected! Logged in as: {self.client.user}")
                self._reconnect_attempts = 0  # Reset on successful reconnection
                return

            await asyncio.sleep(1.0)

        raise TimeoutError("Discord client failed to reconnect within timeout")

    def _build_error_context(self, current_agent_task: asyncio.Task[Any]) -> Dict[str, Any]:
        """Build rich error context for troubleshooting Discord issues."""
        return {
            "task_exists": self._discord_client_task is not None,
            "task_done": self._discord_client_task.done() if self._discord_client_task else None,
            "task_cancelled": self._discord_client_task.cancelled() if self._discord_client_task else None,
            "task_exception": (
                str(self._discord_client_task.exception())
                if self._discord_client_task and self._discord_client_task.done()
                else None
            ),
            "client_closed": self.client.is_closed() if self.client else None,
            "client_user": str(self.client.user) if self.client and hasattr(self.client, "user") else None,
            "reconnect_attempts": self._reconnect_attempts,
            "agent_task_name": current_agent_task.get_name(),
            "agent_task_done": current_agent_task.done(),
        }

    async def _recreate_discord_task(self, context: Dict[str, Any]) -> bool:
        """
        Recreate Discord client task when it dies unexpectedly.

        Returns:
            True if recreation succeeded, False if should continue with backoff
        """
        try:
            # If client is closed, we rely on recreating the task with client.start()
            # Full client recreation is not needed since discord.py handles reconnection internally
            if self.client and self.client.is_closed():
                logger.warning("Discord client is closed - will recreate task with client.start()")

            self._discord_client_task = asyncio.create_task(
                self.client.start(self.token, reconnect=True), name="DiscordClientTask"
            )
            logger.info(f"Discord client task recreated successfully. Context: {context}")
            return True

        except Exception as recreate_error:
            logger.error(f"Failed to recreate Discord client task: {recreate_error}. Context: {context}", exc_info=True)

            # Exponential backoff to avoid tight loop
            backoff_time = min(5.0 * (2 ** min(self._reconnect_attempts, 6)), 60.0)
            logger.info(f"Waiting {backoff_time:.1f}s before retry (attempt {self._reconnect_attempts + 1})")
            await asyncio.sleep(backoff_time)
            return False

    def _check_task_health(self, current_agent_task: asyncio.Task[Any]) -> bool:
        """
        Check if Discord task needs recreation.

        Returns:
            True if task is healthy, False if needs recreation
        """
        if not self._discord_client_task or self._discord_client_task.done():
            context = self._build_error_context(current_agent_task)

            if not self._discord_client_task:
                logger.warning(f"Discord client task is None - recreating. Context: {context}")
            else:
                logger.warning(f"Discord client task died unexpectedly - recreating. Context: {context}")

            return False
        return True

    def _handle_timeout_scenario(self) -> bool:
        """
        Handle timeout when no tasks complete within expected timeframe.

        Returns:
            True to continue monitoring, False to force task recreation
        """
        # Check if Discord client is still responsive first
        if self.client and not self.client.is_closed():
            logger.debug("No tasks completed within 30s timeout - Discord client appears healthy, continuing...")
            return True
        else:
            logger.warning(
                "No tasks completed within 30s timeout - Discord client appears closed/unresponsive, will recreate task on next iteration"
            )
            if self._discord_client_task and not self._discord_client_task.done():
                self._discord_client_task.cancel()
            self._discord_client_task = None  # Force recreation
            return False

    async def _handle_discord_task_failure(self, exc: Exception, current_agent_task: asyncio.Task[Any]) -> bool:
        """
        Handle Discord task failure with structured error classification and circuit breaker.

        Returns:
            True to continue monitoring, False to break from monitoring loop
        """
        task_name = (
            self._discord_client_task.get_name()
            if self._discord_client_task and hasattr(self._discord_client_task, "get_name")
            else "DiscordClientTask"
        )

        # Rich error context for troubleshooting Discord SDK issues
        error_context = {
            "task_name": task_name,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "client_closed": self.client.is_closed() if self.client else None,
            "client_user": str(self.client.user) if self.client and hasattr(self.client, "user") else None,
            "reconnect_attempts": self._reconnect_attempts,
            "token_suffix": self.token[-10:] if self.token else None,
            "agent_task_name": current_agent_task.get_name(),
            "agent_task_done": current_agent_task.done(),
            "task_cancelled": self._discord_client_task.cancelled() if self._discord_client_task else None,
        }

        logger.error(f"Discord task failed with rich context: {error_context}", exc_info=exc)

        # Use DiscordErrorClassifier to determine retry strategy
        from .discord_error_classifier import DiscordErrorClassifier

        classification = DiscordErrorClassifier.classify_error(exc, self._reconnect_attempts)
        DiscordErrorClassifier.log_error_classification(classification, self._reconnect_attempts + 1)

        if not classification.should_retry:
            logger.error(f"Discord client encountered non-retryable error: {classification.description}")
            return False

        # Handle retry with circuit breaker
        if self._reconnect_attempts >= classification.max_retries:
            logger.error(
                f"Exceeded maximum reconnect attempts ({classification.max_retries}). "
                f"Context: {error_context}. Entering circuit breaker mode (longer delays)."
            )
            # Don't give up entirely - use circuit breaker pattern with longer delays
            circuit_breaker_delay = min(300.0, 60.0 * (self._reconnect_attempts - classification.max_retries + 1))
            logger.warning(f"Circuit breaker: waiting {circuit_breaker_delay:.1f}s before next attempt")
            await asyncio.sleep(circuit_breaker_delay)

            # Reset attempts periodically to allow recovery
            if self._reconnect_attempts > classification.max_retries + 5:
                logger.info("Resetting reconnect attempts after extended circuit breaker period")
                self._reconnect_attempts = classification.max_retries // 2

        self._reconnect_attempts += 1

        # Wait with classifier-determined delay
        logger.info(f"Waiting {classification.retry_delay:.1f} seconds before checking connection status...")
        await asyncio.sleep(classification.retry_delay)

        # Discord.py with reconnect=True will handle reconnection internally
        # We just need to create a new task to wait for it
        self._discord_client_task = asyncio.create_task(self._wait_for_discord_reconnect(), name="DiscordReconnectWait")

        return True

    async def _handle_top_level_exception(self, exc: Exception, agent_run_task: asyncio.Task[Any]) -> None:
        """Handle top-level exceptions in run_lifecycle with recovery attempts."""
        logger.error(f"DiscordPlatform: Unexpected error in run_lifecycle: {exc}", exc_info=True)
        error_type = type(exc).__name__

        # Even top-level errors might be transient - try one more time
        if self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            logger.warning(f"Attempting to recover from lifecycle error ({error_type}). Restarting lifecycle...")

            # Wait before retrying
            await asyncio.sleep(10.0)

            # Recursively call run_lifecycle to retry
            try:
                await self.run_lifecycle(agent_run_task)
                return  # If successful, exit
            except Exception as retry_exc:
                logger.error(f"Failed to recover from lifecycle error: {retry_exc}")

        # If we get here, we've failed to recover
        if not agent_run_task.done():
            agent_run_task.cancel()

    async def _cleanup_discord_resources(self) -> None:
        """Clean up Discord client and task resources."""
        logger.info("DiscordPlatform: Lifecycle ending. Cleaning up Discord connection.")

        # Cancel Discord client task if it's still running
        if self._discord_client_task and not self._discord_client_task.done():
            logger.info("DiscordPlatform: Cancelling Discord client task")
            self._discord_client_task.cancel()
            try:
                await self._discord_client_task
            except asyncio.CancelledError:
                # Only re-raise if we're being cancelled ourselves
                current = asyncio.current_task()
                if current and current.cancelled():
                    raise
                # Otherwise, this is a normal stop - don't propagate the cancellation
            except Exception as e:
                logger.error(f"Error while cancelling Discord client task: {e}")

        # Close the client if it's still open
        if self.client and not self.client.is_closed():
            logger.info("DiscordPlatform: Closing Discord client")
            try:
                await self.client.close()
            except Exception as e:
                logger.error(f"Error while closing Discord client: {e}")

        logger.info("DiscordPlatform: Discord lifecycle complete")

    def _validate_lifecycle_preconditions(self, agent_run_task: asyncio.Task[Any]) -> None:
        """Validate preconditions before running lifecycle."""
        if not self.client:
            raise RuntimeError("Discord client not initialized - check adapter configuration")
        if not self.token:
            raise RuntimeError("Discord token not provided - check environment variables")
        if not agent_run_task:
            raise ValueError("Agent task is None - caller must provide valid task")
        if agent_run_task.done():
            raise ValueError(f"Agent task is already done (cancelled={agent_run_task.cancelled()})")
        if agent_run_task.get_name() == "AgentPlaceholderTask":
            raise ValueError(
                "Placeholder tasks are no longer supported. "
                "Pass the real agent task directly to run_lifecycle. "
                "This eliminates race conditions and simplifies the codebase."
            )

    async def _connect_to_discord(self) -> bool:
        """
        Start Discord client and wait for ready state.

        Returns:
            True if connection successful, False otherwise
        """
        logger.info(f"DiscordPlatform: Starting Discord client with token ending in ...{self.token[-10:]}")
        self._discord_client_task = asyncio.create_task(
            self.client.start(self.token, reconnect=True), name="DiscordClientTask"
        )
        logger.info("DiscordPlatform: Discord client start initiated.")

        # Give the client time to initialize
        await asyncio.sleep(3.0)

        # Wait for Discord client to be ready
        logger.info("DiscordPlatform: Waiting for Discord client to be ready...")
        ready = await self.discord_adapter.wait_until_ready(timeout=30.0)

        if not ready:
            logger.error("DiscordPlatform: Discord client failed to become ready within timeout")
            return False

        logger.info(f"DiscordPlatform: Discord client ready! Logged in as: {self.client.user}")
        self._reconnect_attempts = 0
        return True

    async def _handle_agent_task_completion(self, current_agent_task: asyncio.Task[Any]) -> None:
        """Handle normal shutdown when agent task completes."""
        if self._discord_client_task and not self._discord_client_task.done():
            self._discord_client_task.cancel()
            try:
                await self._discord_client_task
            except asyncio.CancelledError:
                raise

    async def _process_monitoring_iteration(self, current_agent_task: asyncio.Task[Any]) -> tuple[bool, bool]:
        """
        Process one iteration of the monitoring loop.

        Returns:
            (should_continue, should_break) tuple
        """
        # Check if Discord task needs recreation
        if not self._check_task_health(current_agent_task):
            context = self._build_error_context(current_agent_task)
            recreation_success = await self._recreate_discord_task(context)
            if not recreation_success:
                return (True, False)  # Continue without breaking

        # Wait for either task to complete
        done, pending = await asyncio.wait(
            [current_agent_task, self._discord_client_task], return_when=asyncio.FIRST_COMPLETED, timeout=30.0
        )

        # Agent task completed - normal shutdown
        if current_agent_task in done:
            await self._handle_agent_task_completion(current_agent_task)
            return (False, True)  # Break from loop

        # Handle timeout
        if not done:
            self._handle_timeout_scenario()
            return (True, False)  # Continue

        # Handle Discord task failure
        if self._discord_client_task in done and self._discord_client_task.exception():
            exc = self._discord_client_task.exception()
            if exc and isinstance(exc, Exception):
                should_continue = await self._handle_discord_task_failure(exc, current_agent_task)
                return (should_continue, not should_continue)
            return (False, True)  # Break on non-exception error

        return (True, False)  # Continue by default

    async def _run_monitoring_loop(self, current_agent_task: asyncio.Task[Any]) -> None:
        """Run the main monitoring loop for Discord and agent tasks."""
        while not current_agent_task.done():
            should_continue, should_break = await self._process_monitoring_iteration(current_agent_task)

            if should_break:
                break
            if should_continue:
                continue

    async def _handle_login_failure(self, error: discord.LoginFailure, agent_run_task: asyncio.Task[Any]) -> None:
        """Handle Discord login failures."""
        logger.error(f"DiscordPlatform: Discord login failed: {error}. Check token and intents.", exc_info=True)
        if hasattr(self.runtime, "request_shutdown"):
            self.runtime.request_shutdown("Discord login failure")
        if not agent_run_task.done():
            agent_run_task.cancel()

    async def run_lifecycle(self, agent_run_task: asyncio.Task[Any]) -> None:
        """Run Discord lifecycle with simplified best practices."""
        logger.info("DiscordPlatform: Running lifecycle - attempting to start Discord client.")

        # Validate preconditions
        self._validate_lifecycle_preconditions(agent_run_task)

        logger.info(f"Managing lifecycle for agent task '{agent_run_task.get_name()}'")

        # Store the real agent task
        current_agent_task = agent_run_task
        self._current_agent_task = current_agent_task

        try:
            # Connect to Discord
            connected = await self._connect_to_discord()
            if not connected:
                if not current_agent_task.done():
                    current_agent_task.cancel()
                return

            # Run monitoring loop
            await self._run_monitoring_loop(current_agent_task)

        except discord.LoginFailure as e:
            await self._handle_login_failure(e, agent_run_task)
        except Exception as e:
            await self._handle_top_level_exception(e, agent_run_task)
        finally:
            await self._cleanup_discord_resources()

    async def stop(self) -> None:
        logger.info("DiscordPlatform: Stopping...")

        # Stop observer, tool service and adapter first
        if hasattr(self.discord_observer, "stop"):
            if self.discord_observer:
                await self.discord_observer.stop()
        if hasattr(self.tool_service, "stop"):
            await self.tool_service.stop()
        if hasattr(self.discord_adapter, "stop"):
            await self.discord_adapter.stop()

        # Close the Discord client before cancelling the task
        if self.client and not self.client.is_closed():
            logger.info("DiscordPlatform: Closing Discord client connection.")
            try:
                await self.client.close()
                logger.info("DiscordPlatform: Discord client connection closed.")
            except Exception as e:
                logger.error(f"DiscordPlatform: Error while closing Discord client: {e}", exc_info=True)

        # Then cancel the task
        if self._discord_client_task and not self._discord_client_task.done():
            logger.info("DiscordPlatform: Cancelling active Discord client task.")
            self._discord_client_task.cancel()
            try:
                await self._discord_client_task
            except asyncio.CancelledError:
                logger.info("DiscordPlatform: Discord client task successfully cancelled.")
                # Only re-raise if our current task is being cancelled
                current_task = asyncio.current_task()
                if current_task and current_task.cancelled():
                    raise
                # Otherwise, we're in normal shutdown - don't propagate the cancellation

        logger.info("DiscordPlatform: Stopped.")

    async def is_healthy(self) -> bool:  # NOSONAR: Protocol requires async signature
        """Check if the Discord adapter is healthy"""
        try:
            # Check if Discord client is connected and ready
            if not self.client:
                return False

            if self.client.is_closed():
                return False

            # If client exists and is not closed, we're healthy
            # The client.is_ready() check happens during connection
            # and we log "Discord client ready!" when it's true
            return True
        except Exception as e:
            logger.warning(f"Discord health check failed: {e}")
            return False

    async def get_active_channels(self) -> List[DiscordChannelInfo]:  # NOSONAR: Protocol requires async signature
        """Get list of active Discord channels."""
        logger.info("[DISCORD_PLATFORM] get_active_channels called on wrapper")
        if hasattr(self.discord_adapter, "get_active_channels"):
            logger.info("[DISCORD_PLATFORM] Calling discord_adapter.get_active_channels")
            result = self.discord_adapter.get_active_channels()
            logger.info(f"[DISCORD_PLATFORM] Got {len(result)} channels from adapter")
            return result
        logger.warning("[DISCORD_PLATFORM] discord_adapter doesn't have get_active_channels")
        return []
