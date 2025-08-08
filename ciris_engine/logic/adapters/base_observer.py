import logging
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, Generic, List, Optional, Set, TypeVar, cast

from pydantic import BaseModel

from ciris_engine.logic import persistence
from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.utils.thought_utils import generate_thought_id
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ThoughtType
from ciris_engine.schemas.runtime.models import TaskContext
from ciris_engine.schemas.runtime.models import ThoughtContext as ThoughtModelContext
from ciris_engine.schemas.services.filters_core import FilterPriority, FilterResult

logger = logging.getLogger(__name__)

MessageT = TypeVar("MessageT", bound=BaseModel)

PASSIVE_CONTEXT_LIMIT = 10


class BaseObserver(Generic[MessageT], ABC):
    """Common functionality for message observers."""

    def __init__(
        self,
        on_observe: Callable[[dict], Awaitable[None]],
        bus_manager: Optional[BusManager] = None,
        memory_service: Optional[Any] = None,
        agent_id: Optional[str] = None,
        filter_service: Optional[Any] = None,
        secrets_service: Optional[SecretsService] = None,
        time_service: Optional[TimeServiceProtocol] = None,
        auth_service: Optional[Any] = None,
        observer_wa_id: Optional[str] = None,
        *,
        origin_service: str = "unknown",
    ) -> None:
        self.on_observe = on_observe
        self.bus_manager = bus_manager
        self.memory_service = memory_service
        self.agent_id = agent_id
        self.filter_service = filter_service
        self.secrets_service = secrets_service
        self.time_service = time_service
        self.auth_service = auth_service
        self.observer_wa_id = observer_wa_id
        self.origin_service = origin_service

    @abstractmethod
    async def start(self) -> None:  # pragma: no cover - implemented by subclasses
        pass

    @abstractmethod
    async def stop(self) -> None:  # pragma: no cover - implemented by subclasses
        pass

    def _is_agent_message(self, msg: MessageT) -> bool:
        if self.agent_id and getattr(msg, "author_id", None) == self.agent_id:
            return True
        return getattr(msg, "is_bot", False)

    async def _apply_message_filtering(self, msg: MessageT, adapter_type: str) -> FilterResult:
        if not self.filter_service:
            return FilterResult(
                message_id=getattr(msg, "message_id", "unknown"),
                priority=FilterPriority.MEDIUM,
                triggered_filters=[],
                should_process=True,
                reasoning="No filter service available - processing normally",
            )
        try:
            filter_result = await self.filter_service.filter_message(
                message=msg,
                adapter_type=adapter_type,
            )
            if filter_result.triggered_filters:
                logger.debug(
                    "Message %s triggered filters: %s",
                    getattr(msg, "message_id", "unknown"),
                    filter_result.triggered_filters,
                )
            return cast(FilterResult, filter_result)
        except Exception as e:  # pragma: no cover - unlikely in tests
            logger.error("Error applying filter to message %s: %s", getattr(msg, "message_id", "unknown"), e)
            return FilterResult(
                message_id=getattr(msg, "message_id", "unknown"),
                priority=FilterPriority.MEDIUM,
                triggered_filters=[],
                should_process=True,
                reasoning=f"Filter error, processing normally: {e}",
            )

    async def _process_message_secrets(self, msg: MessageT) -> MessageT:
        if not self.secrets_service:
            logger.error(
                f"CRITICAL: secrets_service is None in {self.origin_service} observer! Cannot process secrets."
            )
            raise RuntimeError("SecretsService is required but not available")
        try:
            processed_content, secret_refs = await self.secrets_service.process_incoming_text(
                msg.content,  # type: ignore[attr-defined]
                msg.message_id,  # type: ignore[attr-defined]
            )
            processed_msg = msg.model_copy(update={"content": processed_content})
            if secret_refs:
                processed_msg._detected_secrets = [  # type: ignore[attr-defined]
                    {
                        "uuid": ref.secret_uuid,  # type: ignore[attr-defined]
                        "context_hint": ref.context_hint,
                        "sensitivity": ref.sensitivity,
                    }
                    for ref in secret_refs
                ]
            return processed_msg
        except Exception as e:  # pragma: no cover - unlikely in tests
            logger.error("Error processing secrets in %s message %s: %s", self.origin_service, msg.message_id, e)  # type: ignore[attr-defined]
            return msg

    async def _get_recall_ids(self, msg: MessageT) -> Set[str]:
        return {f"channel/{getattr(msg, 'channel_id', 'cli')}"}

    async def _get_correlation_history(
        self, channel_id: str, limit: int = PASSIVE_CONTEXT_LIMIT
    ) -> List[Dict[str, Any]]:
        """Get message history from correlations database."""
        from ciris_engine.logic.persistence import get_correlations_by_channel

        try:
            correlations = get_correlations_by_channel(channel_id=channel_id, limit=limit)

            history = []
            for corr in correlations:
                if corr.action_type == "speak" and corr.request_data:
                    # Agent message
                    content = ""
                    if hasattr(corr.request_data, "parameters") and corr.request_data.parameters:
                        content = corr.request_data.parameters.get("content", "")

                        # Strip out nested conversation history to prevent recursive history
                        if "=== CONVERSATION HISTORY" in content:
                            # Extract only the first line (the actual message)
                            lines = content.split("\n")
                            content = lines[0] if lines else content

                    history.append(
                        {
                            "author": "CIRIS",
                            "author_id": self.agent_id or "ciris",
                            "content": content,
                            "timestamp": corr.timestamp or corr.created_at,
                            "is_agent": True,
                        }
                    )

                elif corr.action_type == "observe" and corr.request_data:
                    # User message
                    if hasattr(corr.request_data, "parameters") and corr.request_data.parameters:
                        params = corr.request_data.parameters
                        history.append(
                            {
                                "author": params.get("author_name", "User"),
                                "author_id": params.get("author_id", "unknown"),
                                "content": params.get("content", ""),
                                "timestamp": corr.timestamp or corr.created_at,
                                "is_agent": False,
                            }
                        )

            return history

        except Exception as e:
            logger.warning(f"Failed to get correlation history: {e}")
            # Fallback to empty history
            return []

    async def _recall_context(self, msg: MessageT) -> None:
        if not self.memory_service:
            return
        recall_ids = await self._get_recall_ids(msg)

        # Get user IDs from correlation history
        channel_id = getattr(msg, "channel_id", "system")
        history = await self._get_correlation_history(channel_id, PASSIVE_CONTEXT_LIMIT)

        for hist_msg in history:
            if hist_msg.get("author_id"):
                recall_ids.add(f"user/{hist_msg['author_id']}")

        from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType

        for rid in recall_ids:
            for scope in (
                GraphScope.IDENTITY,
                GraphScope.ENVIRONMENT,
                GraphScope.LOCAL,
            ):
                try:
                    if rid.startswith("channel/"):
                        node_type = NodeType.CHANNEL
                    elif rid.startswith("user/"):
                        node_type = NodeType.USER
                    else:
                        node_type = NodeType.CONCEPT
                    from datetime import datetime, timezone

                    node = GraphNode(
                        id=rid,
                        type=node_type,
                        scope=scope,
                        attributes=GraphNodeAttributes(
                            created_by="base_observer",
                            created_at=self.time_service.now() if self.time_service else datetime.now(timezone.utc),
                            updated_at=self.time_service.now() if self.time_service else datetime.now(timezone.utc),
                            tags=[],
                        ),
                        updated_by="base_observer",
                        updated_at=self.time_service.now() if self.time_service else datetime.now(timezone.utc),
                    )
                    await self.memory_service.recall(node)
                except Exception:
                    continue

    async def _add_to_feedback_queue(self, msg: MessageT) -> None:
        try:
            if self.bus_manager:
                success = await self.bus_manager.communication.send_message(
                    handler_name=self.__class__.__name__,
                    channel_id=str(getattr(msg, "channel_id", "")) or "unknown",
                    content=f"[WA_FEEDBACK] {msg.content}",  # type: ignore[attr-defined]
                    metadata={
                        "message_type": "wa_feedback",
                        "original_message_id": msg.message_id,  # type: ignore[attr-defined]
                        "wa_user": msg.author_name,  # type: ignore[attr-defined]
                        "source": f"{self.origin_service}_observer",
                    },
                )
                if success:
                    logger.info(
                        "Enqueued WA feedback message %s from %s",
                        msg.message_id,  # type: ignore[attr-defined]
                        msg.author_name,  # type: ignore[attr-defined]
                    )
                else:
                    logger.warning("Failed to enqueue WA feedback message %s", msg.message_id)  # type: ignore[attr-defined]
            else:
                logger.warning("No bus_manager available for WA feedback routing")
        except Exception as e:  # pragma: no cover - rarely hit in tests
            logger.error("Error adding WA feedback message %s to queue: %s", msg.message_id, e)  # type: ignore[attr-defined]

    async def _sign_and_add_task(self, task: Any) -> None:
        """Sign the task with observer's WA certificate before adding."""
        # If auth service and observer WA ID are available, sign the task
        if self.auth_service and self.observer_wa_id:
            try:
                signature, signed_at = await self.auth_service.sign_task(task, self.observer_wa_id)
                task.signed_by = self.observer_wa_id
                task.signature = signature
                task.signed_at = signed_at
                logger.debug(f"Signed observer task {task.task_id} with observer WA {self.observer_wa_id}")
            except Exception as e:
                logger.error(f"Failed to sign observer task: {e}")
                # Continue without signature

        # Import persistence here to avoid circular import

        persistence.add_task(task)

    async def _create_passive_observation_result(self, msg: MessageT) -> None:
        try:
            import uuid
            from datetime import datetime, timezone

            from ciris_engine.logic import persistence
            from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
            from ciris_engine.schemas.runtime.models import Task, Thought
            from ciris_engine.schemas.runtime.system_context import ChannelContext, SystemSnapshot

            # Create minimal system snapshot for passive observation
            channel_context = ChannelContext(
                channel_id=getattr(msg, "channel_id", "system"),
                channel_name=getattr(msg, "channel_name", f"Channel {getattr(msg, 'channel_id', 'system')}"),
                channel_type="text",
                is_private=False,
                created_at=self.time_service.now() if self.time_service else datetime.now(timezone.utc),
                allowed_actions=["send_messages", "read_messages"],
                is_active=True,
                last_activity=self.time_service.now() if self.time_service else datetime.now(timezone.utc),
                message_count=0,
                moderation_level="standard",
            )

            SystemSnapshot(
                channel_context=channel_context,
                channel_id=getattr(msg, "channel_id", "system"),
                agent_identity={"agent_id": self.agent_id or "ciris", "purpose": "Process and respond to messages"},
            )

            # Get message history from correlations instead of in-memory
            channel_id = getattr(msg, "channel_id", "system")
            history_context = await self._get_correlation_history(channel_id, PASSIVE_CONTEXT_LIMIT)

            task = Task(
                task_id=str(uuid.uuid4()),
                channel_id=getattr(msg, "channel_id", "system"),
                description=f"Respond to message from @{msg.author_name} (ID: {msg.author_id}) in #{msg.channel_id}: '{msg.content}'",  # type: ignore[attr-defined]
                status=TaskStatus.PENDING,
                priority=0,
                created_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                updated_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                context=TaskContext(
                    channel_id=getattr(msg, "channel_id", None),
                    user_id=msg.author_id,  # type: ignore[attr-defined]
                    correlation_id=msg.message_id,  # type: ignore[attr-defined]
                    parent_task_id=None,
                ),
            )

            await self._sign_and_add_task(task)

            # Build conversation context for thought
            thought_lines = [f"You observed @{msg.author_name} (ID: {msg.author_id}) in channel {msg.channel_id} say: {msg.content}"]  # type: ignore[attr-defined]

            thought_lines.append("\n=== CONVERSATION HISTORY (Last 10 messages) ===")
            for i, hist_msg in enumerate(history_context, 1):
                author = hist_msg.get("author", "Unknown")
                author_id = hist_msg.get("author_id", "unknown")
                content = hist_msg.get("content", "")
                hist_msg.get("timestamp", "")
                thought_lines.append(f"{i}. @{author} (ID: {author_id}): {content}")

            thought_lines.append(
                "\n=== EVALUATE THIS MESSAGE AGAINST YOUR IDENTITY/JOB AND ETHICS AND DECIDE IF AND HOW TO ACT ON IT ==="
            )
            thought_lines.append(f"@{msg.author_name} (ID: {msg.author_id}): {msg.content}")  # type: ignore[attr-defined]

            thought_content = "\n".join(thought_lines)

            thought = Thought(
                thought_id=generate_thought_id(thought_type=ThoughtType.OBSERVATION, task_id=task.task_id),
                source_task_id=task.task_id,
                channel_id=getattr(msg, "channel_id", None),
                thought_type=ThoughtType.OBSERVATION,
                status=ThoughtStatus.PENDING,
                created_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                updated_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                round_number=0,
                content=thought_content,
                thought_depth=0,
                ponder_notes=None,
                parent_thought_id=None,
                final_action=None,
                context=ThoughtModelContext(
                    task_id=task.task_id,
                    channel_id=getattr(msg, "channel_id", None),
                    round_number=0,
                    depth=0,
                    parent_thought_id=None,
                    correlation_id=msg.message_id,  # type: ignore[attr-defined]
                ),
            )

            persistence.add_thought(thought)
            logger.info(f"Created task {task.task_id} for: {getattr(msg, 'content', 'unknown')[:50]}...")

        except Exception as e:  # pragma: no cover - rarely hit in tests
            logger.error("Error creating observation task: %s", e, exc_info=True)

    async def _create_priority_observation_result(self, msg: MessageT, filter_result: Any) -> None:
        try:
            import uuid
            from datetime import datetime, timezone

            from ciris_engine.logic import persistence
            from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
            from ciris_engine.schemas.runtime.models import Task, Thought

            task_priority = 10 if getattr(filter_result.priority, "value", "") == "critical" else 5

            task = Task(
                task_id=str(uuid.uuid4()),
                channel_id=getattr(msg, "channel_id", "system"),
                description=f"PRIORITY: Respond to {filter_result.priority.value} message from @{msg.author_name} (ID: {msg.author_id}): '{msg.content}'",  # type: ignore[attr-defined]
                status=TaskStatus.PENDING,
                priority=task_priority,
                created_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                updated_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                context=TaskContext(
                    channel_id=getattr(msg, "channel_id", None),
                    user_id=msg.author_id,  # type: ignore[attr-defined]
                    correlation_id=msg.message_id,  # type: ignore[attr-defined]
                    parent_task_id=None,
                ),
            )
            await self._sign_and_add_task(task)

            thought = Thought(
                thought_id=generate_thought_id(thought_type=ThoughtType.OBSERVATION, task_id=task.task_id),
                source_task_id=task.task_id,
                channel_id=getattr(msg, "channel_id", None),
                thought_type=ThoughtType.OBSERVATION,
                status=ThoughtStatus.PENDING,
                created_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                updated_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                round_number=0,
                content=f"PRIORITY ({filter_result.priority.value}): User @{msg.author_name} (ID: {msg.author_id}) said: {msg.content} | Filter: {filter_result.reasoning}",  # type: ignore[attr-defined]
                thought_depth=0,
                ponder_notes=None,
                parent_thought_id=None,
                final_action=None,
                context=ThoughtModelContext(
                    task_id=task.task_id,
                    channel_id=getattr(msg, "channel_id", None),
                    round_number=0,
                    depth=0,
                    parent_thought_id=None,
                    correlation_id=msg.message_id,  # type: ignore[attr-defined]
                ),
            )
            persistence.add_thought(thought)
        except Exception as e:  # pragma: no cover - rarely hit in tests
            logger.error("Error creating priority observation task: %s", e, exc_info=True)

    async def handle_incoming_message(self, msg: MessageT) -> None:
        """Standard message handling flow for all observers."""
        # Check if this is the agent's own message
        is_agent_message = self._is_agent_message(msg)

        # Process message for secrets detection and replacement
        processed_msg = await self._process_message_secrets(msg)

        # Allow subclasses to enhance the message (e.g., vision processing)
        processed_msg = await self._enhance_message(processed_msg)

        # If it's the agent's message, stop here (no task creation)
        if is_agent_message:
            logger.debug("Added agent's own message to history (no task created)")
            return

        # Apply adaptive filtering to determine message priority and processing
        filter_result = await self._apply_message_filtering(msg, self.origin_service)
        if not filter_result.should_process:
            logger.debug(f"Message filtered out: {filter_result.reasoning}")
            return

        # Add filter context to message for downstream processing
        setattr(processed_msg, "_filter_priority", filter_result.priority)
        setattr(processed_msg, "_filter_context", filter_result.context_hints)
        setattr(processed_msg, "_filter_reasoning", filter_result.reasoning)

        # Process based on priority
        if filter_result.priority.value in ["critical", "high"]:
            logger.info(f"Processing {filter_result.priority.value} priority message: {filter_result.reasoning}")
            await self._handle_priority_observation(processed_msg, filter_result)
        else:
            await self._handle_passive_observation(processed_msg)

        # Recall relevant context
        await self._recall_context(processed_msg)

    async def _enhance_message(self, msg: MessageT) -> MessageT:
        """Hook for subclasses to enhance messages (e.g., vision processing)."""
        return msg

    async def _handle_priority_observation(self, msg: MessageT, filter_result: Any) -> None:
        """Handle high-priority messages - to be implemented by subclasses"""
        # Default implementation: check if message should be processed by this observer
        if await self._should_process_message(msg):
            await self._create_priority_observation_result(msg, filter_result)
        else:
            logger.debug(f"Ignoring priority message from channel {getattr(msg, 'channel_id', 'unknown')}")

    async def _handle_passive_observation(self, msg: MessageT) -> None:
        """Handle passive observation routing - to be implemented by subclasses"""
        if await self._should_process_message(msg):
            await self._create_passive_observation_result(msg)
        else:
            logger.debug(f"Ignoring passive message from channel {getattr(msg, 'channel_id', 'unknown')}")

    async def _should_process_message(self, msg: MessageT) -> bool:
        """Check if this observer should process the message - to be overridden by subclasses."""
        return True  # Default: process all messages
