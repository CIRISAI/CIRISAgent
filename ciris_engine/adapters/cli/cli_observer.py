import asyncio
import logging
from typing import Callable, Awaitable, Dict, Any, Optional

from ciris_engine.schemas.foundational_schemas_v1 import IncomingMessage
from ciris_engine.sinks.multi_service_sink import MultiServiceActionSink
from ciris_engine.secrets.service import SecretsService
from ciris_engine.adapters.base_observer import BaseObserver


logger = logging.getLogger(__name__)

PASSIVE_CONTEXT_LIMIT = 10

class CLIObserver(BaseObserver[IncomingMessage]):
    """
    Observer that converts CLI input events into observation payloads.
    Includes adaptive filtering for message prioritization.
    """

    def __init__(
        self,
        on_observe: Callable[[Dict[str, Any]], Awaitable[None]],
        memory_service: Optional[Any] = None,
        agent_id: Optional[str] = None,
        multi_service_sink: Optional[MultiServiceActionSink] = None,
        filter_service: Optional[Any] = None,
        secrets_service: Optional[SecretsService] = None,
        *,
        interactive: bool = True,
        config: Optional[Any] = None,
    ) -> None:
        super().__init__(
            on_observe,
            memory_service,
            agent_id,
            multi_service_sink,
            filter_service,
            secrets_service,
            origin_service="cli",
        )
        self.interactive = interactive
        self.config = config
        self._input_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the observer and optional input loop."""
        logger.info("CLIObserver started")
        if self.interactive and self._input_task is None:
            self._input_task = asyncio.create_task(self._input_loop())

    async def stop(self) -> None:
        """Stop the observer and background input loop."""
        if self._input_task:
            self._stop_event.set()
            try:
                await asyncio.wait_for(self._input_task, timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("Input task did not complete within timeout, cancelling")
                self._input_task.cancel()
                try:
                    await self._input_task
                except asyncio.CancelledError:
                    pass
            self._input_task = None
            self._stop_event.clear()
        logger.info("CLIObserver stopped")

    async def _input_loop(self) -> None:
        """Read lines from stdin and handle them as messages."""
        try:
            while not self._stop_event.is_set():
                try:
                    line = await asyncio.to_thread(input, ">>> ")
                except asyncio.CancelledError:
                    logger.debug("Input loop cancelled")
                    break
                    
                if not line:
                    continue
                if line.lower() in {"exit", "quit", "bye"}:
                    self._stop_event.set()
                    break

                # Get channel ID from config or default to "cli"
                channel_id = "cli"
                if self.config and hasattr(self.config, 'get_home_channel_id'):
                    channel_id = self.config.get_home_channel_id()
                    
                msg = IncomingMessage(
                    message_id=f"cli_{asyncio.get_event_loop().time()}",
                    content=line,
                    author_id="local_user",
                    author_name="User",
                    channel_id=channel_id,
                )
                await self.handle_incoming_message(msg)
        except asyncio.CancelledError:
            logger.debug("Input loop task cancelled")
            raise

    async def _get_recall_ids(self, msg: IncomingMessage) -> set[str]:
        import socket
        return {f"channel/{socket.gethostname()}"}

    def _is_cli_channel(self, channel_id: str) -> bool:
        """Check if a channel ID belongs to this CLI observer instance."""
        if channel_id == "cli":
            return True
        
        if self.config and hasattr(self.config, 'get_home_channel_id'):
            config_channel = self.config.get_home_channel_id()
            if config_channel and channel_id == config_channel:
                return True
        
        import socket
        hostname_channel = socket.gethostname()
        if channel_id == hostname_channel or channel_id == f"channel/{hostname_channel}":
            return True
        
        import getpass
        user_hostname = f"{getpass.getuser()}@{socket.gethostname()}"
        if channel_id == user_hostname:
            return True
            
        return False

    async def handle_incoming_message(self, msg: IncomingMessage) -> None:
        if not isinstance(msg, IncomingMessage):
            logger.warning("CLIObserver received non-IncomingMessage")  # type: ignore[unreachable]
            return
        
        is_agent_message = self.agent_id and msg.author_id == self.agent_id
        
        processed_msg = await self._process_message_secrets(msg)
        
        self._history.append(processed_msg)
        
        if is_agent_message:
            logger.debug("Added agent's own message %s to history (no task created)", msg.message_id)
            return
        
        filter_result = await self._apply_message_filtering(msg, "cli")
        if not filter_result.should_process:
            logger.debug(f"Message {msg.message_id} filtered out: {filter_result.reasoning}")
            return
        
        processed_msg._filter_priority = filter_result.priority  # type: ignore[attr-defined]
        processed_msg._filter_context = filter_result.context_hints  # type: ignore[attr-defined]
        processed_msg._filter_reasoning = filter_result.reasoning  # type: ignore[attr-defined]
        
        if filter_result.priority.value in ['critical', 'high']:
            logger.info(f"Processing {filter_result.priority.value} priority message {msg.message_id}: {filter_result.reasoning}")
            await self._handle_priority_observation(processed_msg, filter_result)
        else:
            await self._handle_passive_observation(processed_msg)
            
        await self._recall_context(processed_msg)


    async def _handle_priority_observation(self, msg: IncomingMessage, filter_result) -> None:
        """Handle high-priority messages with immediate processing"""
        # The CLI observer should handle any CLI-related channel, not just "cli"
        # This could be "cli", "user@hostname", or any channel ID this CLI instance is responsible for
        
        if self._is_cli_channel(msg.channel_id) and not self._is_agent_message(msg):
            # Create high-priority observation with enhanced context
            await self._create_priority_observation_result(msg, filter_result)
        else:
            logger.debug("Ignoring priority message from channel %s, author %s for CLI observer", msg.channel_id, msg.author_name)

    async def _handle_passive_observation(self, msg: IncomingMessage) -> None:
        """Handle passive observation routing based on channel ID and author filtering"""
        
        logger.debug(f"CLI Message channel_id: {msg.channel_id}")
        
        if self._is_cli_channel(msg.channel_id) and not self._is_agent_message(msg):
            await self._create_passive_observation_result(msg)
        else:
            logger.debug("Ignoring passive message from channel %s, author %s for CLI observer", msg.channel_id, msg.author_name)

