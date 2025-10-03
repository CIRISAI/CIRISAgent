import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple, cast

from pydantic import BaseModel

from ciris_engine.logic import persistence
from ciris_engine.logic.adapters.document_parser import DocumentParser
from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.utils.thought_utils import generate_thought_id
from ciris_engine.protocols.services.infrastructure.resource_monitor import ResourceMonitorServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ThoughtType
from ciris_engine.schemas.runtime.models import TaskContext
from ciris_engine.schemas.runtime.models import ThoughtContext as ThoughtModelContext
from ciris_engine.schemas.services.credit_gate import CreditAccount, CreditContext
from ciris_engine.schemas.services.filters_core import FilterPriority, FilterResult

logger = logging.getLogger(__name__)

# Modern PEP 695 generic syntax (Python 3.12+)

PASSIVE_CONTEXT_LIMIT = 20
PRIORITY_CONTEXT_LIMIT = 30  # More context for high-priority messages


class CreditCheckFailed(Exception):
    """Raised when the credit provider cannot be reached or fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CreditDenied(Exception):
    """Raised when a credit provider denies the interaction."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def detect_and_replace_spoofed_markers(content: str) -> str:
    """Detect and replace attempts to spoof CIRIS security markers."""
    import re

    # Patterns for detecting spoofed markers (case insensitive, with variations)
    patterns = [
        # Original observation markers
        r"CIRIS[_\s]*OBSERV(?:ATION)?[_\s]*START",
        r"CIRIS[_\s]*OBSERV(?:ATION)?[_\s]*END",
        r"CIRRIS[_\s]*OBSERV(?:ATION)?[_\s]*START",  # Common misspelling
        r"CIRRIS[_\s]*OBSERV(?:ATION)?[_\s]*END",
        r"CIRIS[_\s]*OBS(?:ERV)?[_\s]*START",  # Shortened version
        r"CIRIS[_\s]*OBS(?:ERV)?[_\s]*END",
        # Channel history markers
        r"CIRIS[_\s]*CHANNEL[_\s]*HISTORY[_\s]*MESSAGE[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*START",
        r"CIRIS[_\s]*CHANNEL[_\s]*HISTORY[_\s]*MESSAGE[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*END",
        r"CIRRIS[_\s]*CHANNEL[_\s]*HISTORY[_\s]*MESSAGE[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*START",  # Common misspelling
        r"CIRRIS[_\s]*CHANNEL[_\s]*HISTORY[_\s]*MESSAGE[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*END",
        # Shortened channel history patterns
        r"CIRIS[_\s]*CH(?:ANNEL)?[_\s]*HIST(?:ORY)?[_\s]*MSG[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*START",
        r"CIRIS[_\s]*CH(?:ANNEL)?[_\s]*HIST(?:ORY)?[_\s]*MSG[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*END",
    ]

    modified_content = content
    for pattern in patterns:
        if re.search(pattern, content, re.IGNORECASE):
            modified_content = re.sub(
                pattern,
                "WARNING! ATTEMPT TO SPOOF CIRIS SECURITY MARKERS DETECTED!",
                modified_content,
                flags=re.IGNORECASE,
            )
            logger.warning(f"Detected spoofed CIRIS marker in message content: {pattern}")

    return modified_content


def format_discord_mentions(content: str, user_lookup: Optional[Dict[str, str]] = None) -> str:
    """Format Discord mentions to include username alongside numeric IDs.

    Args:
        content: The message content containing Discord mentions like <@123456789>
        user_lookup: Optional dict mapping user IDs to usernames

    Returns:
        Content with mentions formatted as <@123456789> (username: UserName)
    """
    import re

    if not user_lookup:
        return content

    # Pattern to match Discord mentions: <@USER_ID> or <@!USER_ID>
    mention_pattern = r"<@!?(\d+)>"

    def replace_mention(match):
        user_id = match.group(1)
        username = user_lookup.get(user_id, "Unknown")
        return f"{match.group(0)} (username: {username})"

    return re.sub(mention_pattern, replace_mention, content)


class BaseObserver[MessageT: BaseModel](ABC):
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
        resource_monitor: Optional[ResourceMonitorServiceProtocol] = None,
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
        self.resource_monitor = resource_monitor
        self._credit_log_cache: Dict[str, float] = {}

        # Initialize document parser for all adapters
        self._document_parser = DocumentParser()
        if self._document_parser.is_available():
            logger.info(f"Document parser initialized for {origin_service} adapter - PDF/DOCX processing enabled")
        else:
            logger.warning(
                f"Document parser not available for {origin_service} adapter - install pypdf and docx2txt to enable"
            )

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
                        "uuid": ref.uuid,
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

    def _process_message_content(self, raw_content: str) -> str:
        """Process raw message content by removing nested history and applying anti-spoofing."""
        # Strip out nested conversation history to prevent recursive history
        if "=== CONVERSATION HISTORY" in raw_content:
            lines = raw_content.split("\n")
            raw_content = lines[0] if lines else raw_content

        # Apply anti-spoofing detection BEFORE adding our own markers
        return detect_and_replace_spoofed_markers(raw_content)

    def _create_protected_content(self, clean_content: str, message_number: int, total_messages: int) -> str:
        """Create anti-spoofing protected content with markers."""
        timestamp = self.time_service.now().isoformat() if self.time_service else datetime.now(timezone.utc).isoformat()
        return (
            f"CIRIS_CHANNEL_HISTORY_MESSAGE_{message_number}_OF_{total_messages}_START [Timestamp: {timestamp}]\n"
            f"{clean_content}\n"
            f"CIRIS_CHANNEL_HISTORY_MESSAGE_{message_number}_OF_{total_messages}_END"
        )

    def _create_history_entry(self, msg, protected_content: str, is_agent_message: bool) -> Dict[str, Any]:
        """Create a history entry from a message."""
        return {
            "author": "CIRIS" if is_agent_message else (getattr(msg, "author_name", None) or "User"),
            "author_id": getattr(msg, "author_id", None) or ("ciris" if is_agent_message else "unknown"),
            "content": protected_content,
            "timestamp": getattr(msg, "timestamp", None),
            "is_agent": is_agent_message,
        }

    async def _fetch_messages_from_bus(self, channel_id: str, limit: int):
        """Fetch messages from communication bus."""
        if not self.bus_manager or not hasattr(self.bus_manager, "communication"):
            logger.warning("No communication bus available for channel history")
            return []

        return await self.bus_manager.communication.fetch_messages(channel_id, limit, "DiscordAdapter")

    async def _get_channel_history(self, channel_id: str, limit: int = PASSIVE_CONTEXT_LIMIT) -> List[Dict[str, Any]]:
        """Get message history from channel using communication bus."""
        if not self.bus_manager:
            logger.warning("No bus manager available for channel history")
            return []

        try:
            # Fetch messages from the channel
            messages = await self._fetch_messages_from_bus(channel_id, limit)

            # Convert FetchedMessage objects to the expected history format
            history = []
            total_messages = len(messages)

            for index, msg in enumerate(messages):
                is_agent_message = getattr(msg, "is_bot", False)
                raw_content = getattr(msg, "content", "") or ""

                # Process content through helper methods
                clean_content = self._process_message_content(raw_content)
                message_number = total_messages - index  # Messages come in reverse chronological order
                protected_content = self._create_protected_content(clean_content, message_number, total_messages)
                history_entry = self._create_history_entry(msg, protected_content, is_agent_message)

                history.append(history_entry)

            # Messages come in reverse chronological order, reverse to get chronological
            history.reverse()
            return history

        except Exception as e:
            logger.warning(f"Failed to get channel history via communication bus: {e}")
            return []

    async def _recall_context(self, msg: MessageT) -> None:
        if not self.memory_service:
            return
        recall_ids = await self._get_recall_ids(msg)

        # Get user IDs from channel history
        channel_id = getattr(msg, "channel_id", "system")
        history = await self._get_channel_history(channel_id, PASSIVE_CONTEXT_LIMIT)

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

    def _build_user_lookup_from_history(self, msg: MessageT, history_context: List[Dict]) -> Dict[str, str]:
        """Build a user lookup dictionary for mention resolution."""
        user_lookup = {}

        # Add users from history
        for hist_msg in history_context:
            aid = hist_msg.get("author_id")
            aname = hist_msg.get("author")
            if aid and aname:
                user_lookup[str(aid)] = aname

        # Add current message author
        if hasattr(msg, "author_id") and hasattr(msg, "author_name"):
            user_lookup[str(msg.author_id)] = msg.author_name

        return user_lookup

    def _format_history_lines(self, history_context: List[Dict], user_lookup: Dict[str, str]) -> List[str]:
        """Format conversation history lines with mentions."""
        lines = []
        for i, hist_msg in enumerate(history_context, 1):
            author = hist_msg.get("author", "Unknown")
            author_id = hist_msg.get("author_id", "unknown")
            content = hist_msg.get("content", "")

            # Format mentions in content to include usernames
            content = format_discord_mentions(content, user_lookup)
            lines.append(f"{i}. @{author} (ID: {author_id}): {content}")

        return lines

    async def _add_custom_context_sections(
        self, task_lines: List[str], msg: MessageT, history_context: List[Dict]
    ) -> None:
        """Extension point for subclasses to add custom context sections.

        This method is called before the conversation history is added,
        allowing subclasses to inject their own context information.

        Args:
            task_lines: The task lines list to append to
            msg: The message being processed
            history_context: The conversation history context
        """
        # Base implementation does nothing - subclasses can override
        pass

    async def _append_consent_aware_content(
        self, task_lines: List[str], msg: MessageT, user_lookup: Dict[str, str]
    ) -> None:
        """Append current message content with consent awareness."""
        import hashlib

        from ciris_engine.schemas.consent.core import ConsentStream

        consent_stream = await self._get_user_consent_stream(msg.author_id)  # type: ignore[attr-defined]
        is_anonymous = consent_stream == ConsentStream.ANONYMOUS.value

        if is_anonymous:
            content_hash = hashlib.sha256(str(msg.content).encode()).hexdigest()  # type: ignore[attr-defined]
            author_hash = f"anon_{hashlib.sha256(str(msg.author_id).encode()).hexdigest()[:8]}"  # type: ignore[attr-defined]
            from ciris_engine.logic.utils.privacy import redact_personal_info

            sanitized_content = redact_personal_info(
                str(msg.content)[:200] if len(str(msg.content)) > 200 else str(msg.content)  # type: ignore[attr-defined]
            )
            task_lines.append(f"@{author_hash}: {sanitized_content} [Hash: {content_hash[:16]}]")
        else:
            formatted_content = format_discord_mentions(str(msg.content), user_lookup)  # type: ignore[attr-defined]
            task_lines.append(f"@{msg.author_name} (ID: {msg.author_id}): {formatted_content}")  # type: ignore[attr-defined]

    async def _create_channel_snapshot(self, msg: MessageT) -> None:
        """Create channel context and system snapshot for observation."""
        from datetime import datetime, timezone

        from ciris_engine.schemas.runtime.system_context import ChannelContext, SystemSnapshot

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

    async def _create_passive_observation_result(
        self, msg: MessageT, priority: int = 0, filter_result: Optional[Any] = None
    ) -> None:
        try:
            import uuid
            from datetime import datetime, timezone

            from ciris_engine.logic import persistence
            from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
            from ciris_engine.schemas.runtime.models import Task, Thought

            # Create channel snapshot
            await self._create_channel_snapshot(msg)

            # Get message history from channel using communication bus
            channel_id = getattr(msg, "channel_id", "system")
            history_context = await self._get_channel_history(channel_id, PASSIVE_CONTEXT_LIMIT)

            # Log context retrieval details
            logger.info(
                f"[CONTEXT] Retrieved {len(history_context)} messages for channel {channel_id}, "
                f"total context size: {sum(len(str(m)) for m in history_context)} chars"
            )

            # Format mentions for task description
            passive_task_lookup = {}
            if hasattr(msg, "author_id") and hasattr(msg, "author_name"):
                passive_task_lookup[str(msg.author_id)] = msg.author_name
            formatted_passive_content = format_discord_mentions(str(msg.content), passive_task_lookup)  # type: ignore[attr-defined]

            # TASK_UPDATED_INFO_AVAILABLE: Check if there's an active task for this channel
            from ciris_engine.logic.persistence.models.tasks import (
                get_active_task_for_channel,
                set_task_updated_info_flag,
            )

            existing_task = get_active_task_for_channel(channel_id)
            if existing_task and self.time_service:
                # Try to update the existing task with new observation
                update_content = f"@{msg.author_name} (ID: {msg.author_id}): {formatted_passive_content}"  # type: ignore[attr-defined]
                success = set_task_updated_info_flag(existing_task.task_id, update_content, self.time_service)
                if success:
                    logger.info(
                        f"[OBSERVER] TASK UPDATE: Flagged existing task {existing_task.task_id} "
                        f"with new observation from @{msg.author_name} in channel {channel_id}"  # type: ignore[attr-defined]
                    )
                    # Don't create a new task - the existing task will see the update via UpdatedStatusConscience
                    return
                else:
                    logger.info(
                        f"[OBSERVER] Task {existing_task.task_id} already committed to action, creating new task"
                    )
                    # Fall through to create new task

            # Build description based on whether this is priority or passive
            if filter_result and priority > 0:
                description = f"PRIORITY: Respond to {getattr(filter_result.priority, 'value', 'high')} message from @{msg.author_name} (ID: {msg.author_id}): '{formatted_passive_content}'"  # type: ignore[attr-defined]
            else:
                description = f"Respond to message from @{msg.author_name} (ID: {msg.author_id}) in #{msg.channel_id}: '{formatted_passive_content}'"  # type: ignore[attr-defined]

            task = Task(
                task_id=str(uuid.uuid4()),
                channel_id=getattr(msg, "channel_id", "system"),
                description=description,
                status=TaskStatus.ACTIVE,
                priority=priority,
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

            logger.info(
                f"[OBSERVER] PASSIVE TASK CREATED: {task.task_id} for message {msg.message_id} "  # type: ignore[attr-defined]
                f"from @{msg.author_name} in channel {channel_id}"  # type: ignore[attr-defined]
            )

            # Build conversation context for thought - thoughts are NEVER sanitized
            # Build user lookup for the current message
            initial_user_lookup = {}
            if hasattr(msg, "author_id") and hasattr(msg, "author_name"):
                initial_user_lookup[str(msg.author_id)] = msg.author_name
            formatted_msg_content = format_discord_mentions(str(msg.content), initial_user_lookup)  # type: ignore[attr-defined]
            # Build thought content based on priority vs passive
            if filter_result and priority > 0:
                priority_level = getattr(filter_result.priority, "value", "high")
                filter_reasoning = getattr(filter_result, "reasoning", "Priority message detected")
                task_lines = [f"PRIORITY ({priority_level}): @{msg.author_name} (ID: {msg.author_id}) in channel {msg.channel_id} said: {formatted_msg_content}"]  # type: ignore[attr-defined]
                task_lines.append(f"Filter: {filter_reasoning}")
            else:
                task_lines = [f"You observed @{msg.author_name} (ID: {msg.author_id}) in channel {msg.channel_id} say: {formatted_msg_content}"]  # type: ignore[attr-defined]

            # Allow subclasses to add custom context sections before conversation history
            await self._add_custom_context_sections(task_lines, msg, history_context)

            task_lines.append(f"\n=== CONVERSATION HISTORY (Last {PASSIVE_CONTEXT_LIMIT} messages) ===")
            observation_timestamp = (
                self.time_service.now().isoformat() if self.time_service else datetime.now(timezone.utc).isoformat()
            )
            task_lines.append(f"CIRIS_OBSERVATION_START [Timestamp: {observation_timestamp}]")

            # Build user lookup and format history lines
            user_lookup = self._build_user_lookup_from_history(msg, history_context)
            history_lines = self._format_history_lines(history_context, user_lookup)
            task_lines.extend(history_lines)

            task_lines.append(f"CIRIS_OBSERVATION_END [Timestamp: {observation_timestamp}]")

            task_lines.append(
                "\n=== EVALUATE THIS MESSAGE AGAINST YOUR IDENTITY/JOB AND ETHICS AND DECIDE IF AND HOW TO ACT ON IT ==="
            )

            # Handle consent-aware content formatting
            await self._append_consent_aware_content(task_lines, msg, user_lookup)

            task_content = "\n".join(task_lines)

            # Log context building details
            history_line_count = len([line for line in task_lines for i in range(1, 11) if line.startswith(f"{i}. @")])
            logger.info(
                f"[CONTEXT] Built thought context with {history_line_count} history messages, "
                f"total thought size: {len(task_content)} chars"
            )

            thought = Thought(
                thought_id=generate_thought_id(thought_type=ThoughtType.STANDARD, task_id=task.task_id),
                source_task_id=task.task_id,
                channel_id=getattr(msg, "channel_id", None),
                thought_type=ThoughtType.STANDARD,
                status=ThoughtStatus.PENDING,
                created_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                updated_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                round_number=0,
                content=task_content,
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
        """Create priority observation by delegating to passive observation with higher priority."""
        try:
            # Determine priority based on filter result
            task_priority = 10 if getattr(filter_result.priority, "value", "") == "critical" else 5

            # Delegate to passive observation with priority and filter information
            await self._create_passive_observation_result(msg, priority=task_priority, filter_result=filter_result)

            logger.info(
                f"[OBSERVER] PRIORITY OBSERVATION: Message {msg.message_id} from @{msg.author_name} "  # type: ignore[attr-defined]
                f"triggered {filter_result.priority.value} priority "
                f"(filters: {', '.join(filter_result.triggered_filters) if filter_result.triggered_filters else 'none'})"
            )

        except Exception as e:  # pragma: no cover - rarely hit in tests
            logger.error("Error creating priority observation task: %s", e, exc_info=True)

    async def handle_incoming_message(self, msg: MessageT) -> None:
        """Standard message handling flow for all observers."""
        msg_id = getattr(msg, "message_id", "unknown")
        channel_id = getattr(msg, "channel_id", "unknown")
        author = f"{getattr(msg, 'author_name', 'unknown')} (ID: {getattr(msg, 'author_id', 'unknown')})"

        logger.info(f"[OBSERVER] Processing message {msg_id} from {author} in channel {channel_id}")

        # Check if this is the agent's own message
        is_agent_message = self._is_agent_message(msg)

        # Enforce credit policy if configured
        await self._enforce_credit_policy(msg)

        # Process message for secrets detection and replacement
        processed_msg = await self._process_message_secrets(msg)

        # Allow subclasses to enhance the message (e.g., vision processing)
        processed_msg = await self._enhance_message(processed_msg)

        # If it's the agent's message, stop here (no task creation)
        if is_agent_message:
            logger.info(f"[OBSERVER] Message {msg_id} is from agent itself - NO TASK CREATED")
            return

        # Apply adaptive filtering to determine message priority and processing
        filter_result = await self._apply_message_filtering(msg, self.origin_service)
        if not filter_result.should_process:
            logger.warning(
                f"[OBSERVER] Message {msg_id} from {author} in channel {channel_id} FILTERED OUT by adaptive filter: "
                f"{filter_result.reasoning} (triggered filters: {', '.join(filter_result.triggered_filters) or 'none'})"
            )
            return

        logger.info(
            f"[OBSERVER] Message {msg_id} PASSED filter with priority {filter_result.priority.value}: "
            f"{filter_result.reasoning}"
        )

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

    async def _enforce_credit_policy(self, msg: MessageT) -> None:
        """Ensure external credit policy allows processing of this message."""

        if not self.resource_monitor or not getattr(self.resource_monitor, "credit_provider", None):
            return

        envelope = self._resolve_credit_envelope(msg)
        if envelope is None:
            return

        account, context = envelope
        try:
            result = await self.resource_monitor.check_credit(account, context)
        except Exception as exc:  # pragma: no cover - provider failure is rare
            if self._should_log_credit_event(f"provider_error:{account.cache_key()}"):
                logger.warning(
                    "Credit provider error for message %s: %s",
                    getattr(msg, "message_id", "unknown"),
                    exc,
                )
            raise CreditCheckFailed(str(exc)) from exc

        if not result.has_credit:
            reason = result.reason or "Insufficient credits"
            cache_key = f"denied:{account.cache_key()}:{reason}"
            if self._should_log_credit_event(cache_key):
                logger.warning(
                    "Credit denied for message %s (channel %s): %s",
                    getattr(msg, "message_id", "unknown"),
                    getattr(msg, "channel_id", "unknown"),
                    reason,
                )
            raise CreditDenied(reason)

    def _resolve_credit_envelope(self, msg: MessageT) -> Optional[Tuple[CreditAccount, CreditContext]]:
        """Extract credit account/context metadata from the message."""

        raw_account: Any = getattr(msg, "credit_account", None)
        raw_context: Any = getattr(msg, "credit_context", None)

        if raw_account is None:
            envelope = getattr(msg, "credit_envelope", None)
            if isinstance(envelope, dict):
                raw_account = envelope.get("account")
                raw_context = envelope.get("context")

        if raw_account is None:
            return None

        account = raw_account if isinstance(raw_account, CreditAccount) else CreditAccount(**raw_account)

        context: CreditContext
        if raw_context is None:
            context = CreditContext()
        elif isinstance(raw_context, CreditContext):
            context = raw_context
        else:
            context = CreditContext(**raw_context)

        return account, context

    def _should_log_credit_event(self, key: str, *, ttl_seconds: float = 60.0) -> bool:
        """Throttle credit-related log messages to avoid audit spam."""

        now = self._current_timestamp()
        last_logged = self._credit_log_cache.get(key)
        if last_logged is not None and now - last_logged < ttl_seconds:
            return False
        self._credit_log_cache[key] = now
        return True

    def _current_timestamp(self) -> float:
        if self.time_service:
            return self.time_service.now().timestamp()
        return time.time()

    async def _should_process_message(self, msg: MessageT) -> bool:
        """Check if this observer should process the message - to be overridden by subclasses."""
        return True  # Default: process all messages

    async def _get_user_consent_stream(self, user_id: str) -> Optional[str]:
        """
        Get user's consent stream for privacy handling.

        Returns consent stream or None if not found.
        """
        try:
            # Try to get consent from consent service if available
            if hasattr(self, "consent_service") and self.consent_service:
                try:
                    consent = await self.consent_service.get_consent(user_id)
                    return consent.stream.value if consent else None
                except Exception:
                    return None

            # Try to get from filter service if available
            if hasattr(self, "filter_service") and self.filter_service:
                if hasattr(self.filter_service, "_config") and self.filter_service._config:
                    if user_id in self.filter_service._config.user_profiles:
                        profile = self.filter_service._config.user_profiles[user_id]
                        return profile.consent_stream

            return None
        except Exception as e:
            logger.debug(f"Could not get consent stream for {user_id}: {e}")
            return None
