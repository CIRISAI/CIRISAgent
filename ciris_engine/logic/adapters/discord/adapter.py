import asyncio
import logging
from typing import Any, List, Optional

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
    def __init__(self, runtime: Any, **kwargs: Any) -> None:
        self.runtime = runtime
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
                    config_dict = template.discord_config.dict() if hasattr(template.discord_config, "dict") else {}
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
            def __init__(self, platform: "DiscordPlatform", *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.platform = platform

            async def on_ready(self):
                """Called when the client is ready."""
                logger.info("Discord client on_ready event")
                # Let the connection manager know
                if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
                    conn_mgr = self.platform.discord_adapter._connection_manager
                    if conn_mgr and hasattr(conn_mgr, "_handle_connected"):
                        await conn_mgr._handle_connected()

            async def on_disconnect(self):
                """Called when the client disconnects."""
                logger.warning("Discord client on_disconnect event")
                # Let the connection manager know
                if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
                    conn_mgr = self.platform.discord_adapter._connection_manager
                    if conn_mgr and hasattr(conn_mgr, "_handle_disconnected"):
                        await conn_mgr._handle_disconnected(None)

            async def on_message(self, message: discord.Message):
                """Called when a message is received."""
                # Let the channel manager handle it
                if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
                    channel_mgr = self.platform.discord_adapter._channel_manager
                    if channel_mgr and hasattr(channel_mgr, "on_message"):
                        await channel_mgr.on_message(message)

            async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
                """Called when a reaction is added."""
                # Let the discord adapter handle it
                if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
                    await self.platform.discord_adapter.on_raw_reaction_add(payload)

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

        self._discord_client_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10

    def get_channel_info(self) -> dict:
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
                self.discord_observer.start()
        if self.tool_service and hasattr(self.tool_service, "start"):
            self.tool_service.start()
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

    async def run_lifecycle(self, agent_run_task: asyncio.Task) -> None:
        logger.info("DiscordPlatform: Running lifecycle - attempting to start Discord client.")
        if not self.client or not self.token:
            logger.error("DiscordPlatform: Discord client or token not properly initialized. Cannot start.")
            if not agent_run_task.done():
                agent_run_task.cancel()
            return

        # Store the initial agent task (might be placeholder)
        current_agent_task = agent_run_task
        is_placeholder = agent_run_task.get_name() == "AgentPlaceholderTask"

        # Keep a reference to prevent garbage collection
        self._current_agent_task = current_agent_task

        try:
            # Start Discord client with reconnect=True to enable automatic reconnection
            logger.info(f"DiscordPlatform: Starting Discord client with token ending in ...{self.token[-10:]}")
            self._discord_client_task = asyncio.create_task(
                self.client.start(self.token, reconnect=True), name="DiscordClientTask"
            )
            logger.info("DiscordPlatform: Discord client start initiated.")

            # Give the client more time to initialize before waiting
            await asyncio.sleep(3.0)

            # Wait for Discord client to be ready with timeout
            logger.info("DiscordPlatform: Waiting for Discord client to be ready...")
            ready = await self.discord_adapter.wait_until_ready(timeout=30.0)

            if not ready:
                logger.error("DiscordPlatform: Discord client failed to become ready within timeout")
                if not current_agent_task.done():
                    current_agent_task.cancel()
                return

            logger.info(f"DiscordPlatform: Discord client ready! Logged in as: {self.client.user}")

            # Reset reconnect attempts on successful connection
            self._reconnect_attempts = 0

            # If this is a placeholder task, we need to handle the transition specially
            transition_complete = asyncio.Event()
            real_agent_task_found = asyncio.Event()

            if is_placeholder:
                logger.info("DiscordPlatform: Setting up placeholder transition handler...")

                async def handle_placeholder_transition():
                    nonlocal current_agent_task
                    logger.info("DiscordPlatform: Waiting for transition from placeholder to real agent task...")
                    try:
                        # Wait for placeholder to complete
                        await current_agent_task
                        logger.info("DiscordPlatform: Placeholder completed, searching for real agent task")

                        # After placeholder completes, find the real agent task
                        # Add a small delay to ensure the real task is created
                        await asyncio.sleep(0.1)

                        found_real_task = False
                        for attempt in range(20):  # Try up to 20 times with delays (10 seconds total)
                            for task in asyncio.all_tasks():
                                if task.get_name() == "AgentProcessorTask" and not task.done():
                                    current_agent_task = task
                                    self._current_agent_task = current_agent_task
                                    logger.info(f"DiscordPlatform: Found real agent task on attempt {attempt + 1}")
                                    found_real_task = True
                                    real_agent_task_found.set()
                                    break
                            if found_real_task:
                                break
                            await asyncio.sleep(0.5)  # Wait before retrying

                        if not found_real_task:
                            logger.error(
                                "DiscordPlatform: Could not find AgentProcessorTask after placeholder completed"
                            )
                            # Set the event anyway to avoid hanging
                            real_agent_task_found.set()
                    except asyncio.CancelledError:
                        logger.info("DiscordPlatform: Placeholder transition task was cancelled")
                        real_agent_task_found.set()  # Ensure we don't hang
                        raise
                    except Exception as e:
                        logger.error(f"DiscordPlatform: Error during placeholder transition: {e}")
                        real_agent_task_found.set()  # Ensure we don't hang
                    finally:
                        transition_complete.set()

                # Create the transition handler task
                transition_task = asyncio.create_task(handle_placeholder_transition())
                transition_task.set_name("DiscordPlaceholderTransition")

                # Wait for the real task to be found before continuing
                logger.info("DiscordPlatform: Waiting for real agent task to be found...")
                await real_agent_task_found.wait()
                logger.info("DiscordPlatform: Continuing with lifecycle management")

            # Now wait for either the agent task or Discord client task to complete
            # Keep retrying Discord connection on transient errors
            while not current_agent_task.done():
                done, pending = await asyncio.wait(
                    [current_agent_task, self._discord_client_task], return_when=asyncio.FIRST_COMPLETED
                )

                # Check if agent task completed
                if current_agent_task in done:
                    # Agent is shutting down, cancel Discord task
                    if self._discord_client_task and not self._discord_client_task.done():
                        self._discord_client_task.cancel()
                        try:
                            await self._discord_client_task
                        except asyncio.CancelledError:
                            # Re-raise CancelledError to maintain cancellation chain
                            raise
                    break

                # Check if Discord task failed
                if self._discord_client_task in done and self._discord_client_task.exception():
                    exc = self._discord_client_task.exception()
                    task_name = (
                        self._discord_client_task.get_name()
                        if hasattr(self._discord_client_task, "get_name")
                        else "DiscordClientTask"
                    )
                    logger.error(f"DiscordPlatform: Task '{task_name}' exited with error: {exc}", exc_info=exc)

                    # Determine if we should retry this error
                    should_retry = False
                    exc_str = str(exc)

                    # Known transient errors that should always retry
                    known_transient = [
                        "Concurrent call to receive() is not allowed",
                        "WebSocket connection is closed.",
                        "Shard ID None has stopped responding to the gateway.",
                        "Session is closed",
                        "Cannot write to closing transport",
                        "Connection reset by peer",
                        "Connection refused",
                        "Network is unreachable",
                        "Temporary failure in name resolution",
                        "Connection timed out",
                        "Remote end closed connection",
                        "HTTP 502",
                        "HTTP 503",
                        "HTTP 504",  # Gateway errors
                        "CloudFlare",
                        "Cloudflare",  # CF errors
                        "rate limit",
                        "Rate limit",  # Rate limiting
                        "429",  # Too Many Requests
                        "SSL",
                        "TLS",
                        "certificate",  # SSL/TLS errors
                        "ECONNRESET",
                        "EPIPE",
                        "ETIMEDOUT",  # Socket errors
                        "getaddrinfo failed",  # DNS errors
                        "Name or service not known",
                    ]

                    # Check for known transient errors
                    if any(msg in exc_str for msg in known_transient):
                        should_retry = True

                    # Connection/network related exceptions should retry
                    elif isinstance(
                        exc,
                        (
                            RuntimeError,
                            discord.ConnectionClosed,
                            discord.HTTPException,
                            discord.GatewayNotFound,
                            ConnectionError,
                            ConnectionResetError,
                            ConnectionAbortedError,
                            ConnectionRefusedError,
                            TimeoutError,
                            OSError,
                        ),
                    ):
                        should_retry = True

                    # Check for aiohttp exceptions
                    elif exc.__class__.__module__.startswith("aiohttp"):
                        should_retry = True

                    # Login failures should NOT retry (bad token, etc)
                    elif isinstance(exc, (discord.LoginFailure, discord.Forbidden)):
                        should_retry = False

                    # Default: treat unknown errors as transient (fail open, not closed)
                    else:
                        logger.warning(f"Unknown error type {type(exc).__name__}: {exc}. Treating as transient.")
                        should_retry = True

                    if should_retry:
                        error_type = type(exc).__name__
                        logger.warning(
                            f"Discord client encountered error ({error_type}: {exc_str[:100]}...). Discord.py will handle reconnection automatically."
                        )

                        # Check if we've exceeded max reconnect attempts
                        if self._reconnect_attempts >= self._max_reconnect_attempts:
                            logger.error(
                                f"Exceeded maximum reconnect attempts ({self._max_reconnect_attempts}). Giving up."
                            )
                            break

                        self._reconnect_attempts += 1

                        # Wait with exponential backoff before checking again
                        wait_time = min(5.0 * (2 ** (self._reconnect_attempts - 1)), 60.0)  # Max 60 seconds
                        logger.info(f"Waiting {wait_time:.1f} seconds before checking connection status...")
                        await asyncio.sleep(wait_time)

                        # Discord.py with reconnect=True will handle reconnection internally
                        # We just need to create a new task to wait for it
                        self._discord_client_task = asyncio.create_task(
                            self._wait_for_discord_reconnect(), name="DiscordReconnectWait"
                        )

                        continue  # Continue the while loop with the new task
                    else:
                        # Non-transient error, don't retry
                        logger.error(f"Discord client encountered non-transient error: {exc}")
                        break

        except discord.LoginFailure as e:
            logger.error(f"DiscordPlatform: Discord login failed: {e}. Check token and intents.", exc_info=True)
            if hasattr(self.runtime, "request_shutdown"):
                self.runtime.request_shutdown("Discord login failure")
            if not agent_run_task.done():
                agent_run_task.cancel()
        except Exception as e:
            logger.error(f"DiscordPlatform: Unexpected error in run_lifecycle: {e}", exc_info=True)
            error_type = type(e).__name__

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
        finally:
            logger.info("DiscordPlatform: Lifecycle ending. Cleaning up Discord connection.")

            # Cancel Discord client task if it's still running
            if self._discord_client_task and not self._discord_client_task.done():
                logger.info("DiscordPlatform: Cancelling Discord client task")
                self._discord_client_task.cancel()
                try:
                    await self._discord_client_task
                except asyncio.CancelledError:
                    # Only re-raise if we're being cancelled ourselves
                    if asyncio.current_task() and asyncio.current_task().cancelled():
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

    async def stop(self) -> None:
        logger.info("DiscordPlatform: Stopping...")

        # Stop observer, tool service and adapter first
        if hasattr(self.discord_observer, "stop"):
            if self.discord_observer:
                self.discord_observer.stop()
        if hasattr(self.tool_service, "stop"):
            self.tool_service.stop()
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
