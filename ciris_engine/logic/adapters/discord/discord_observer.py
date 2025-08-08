import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base_observer import BaseObserver
from ciris_engine.logic.adapters.discord.discord_vision_helper import DiscordVisionHelper
from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.schemas.runtime.messages import DiscordMessage
from ciris_engine.schemas.runtime.models import TaskContext, ThoughtType

logger = logging.getLogger(__name__)

PASSIVE_CONTEXT_LIMIT = 10


class DiscordObserver(BaseObserver[DiscordMessage]):
    """
    Observes DiscordMessage objects directly from Discord adapter, converts them into OBSERVATION
    payloads, and forwards them to the agent via MultiServiceSink. Uses only MultiServiceSink
    architecture without event queues. Includes adaptive filtering for message prioritization.
    """

    def __init__(
        self,
        monitored_channel_ids: Optional[List[str]] = None,
        deferral_channel_id: Optional[str] = None,
        wa_user_ids: Optional[List[str]] = None,
        memory_service: Optional[Any] = None,
        agent_id: Optional[str] = None,
        bus_manager: Optional[BusManager] = None,
        filter_service: Optional[Any] = None,
        secrets_service: Optional[SecretsService] = None,
        communication_service: Optional[Any] = None,
        time_service: Optional[Any] = None,
    ) -> None:
        super().__init__(
            on_observe=lambda _: asyncio.sleep(0),
            bus_manager=bus_manager,
            memory_service=memory_service,
            agent_id=agent_id,
            filter_service=filter_service,
            secrets_service=secrets_service,
            time_service=time_service,
            origin_service="discord",
        )
        self.communication_service = communication_service

        self.deferral_channel_id = deferral_channel_id
        self.wa_user_ids = wa_user_ids or []

        self.monitored_channel_ids = monitored_channel_ids or []

        # Log configuration for debugging
        logger.info("DiscordObserver initialized with:")
        logger.info(f"  - Monitored channels: {self.monitored_channel_ids}")
        logger.info(f"  - Deferral channel: {self.deferral_channel_id}")
        logger.info(f"  - WA user IDs: {self.wa_user_ids}")

        # Initialize vision helper
        self._vision_helper = DiscordVisionHelper()
        if self._vision_helper.is_available():
            logger.info("Discord Vision Helper initialized - image processing enabled")
        else:
            logger.warning("Discord Vision Helper not available - set CIRIS_OPENAI_VISION_KEY to enable")

    async def _send_deferral_message(self, content: str) -> None:
        """Send a message to the deferral channel."""
        if not self.communication_service:
            logger.warning("No communication service available to send deferral message")
            return

        if not self.deferral_channel_id:
            logger.warning("No deferral channel configured")
            return

        try:
            await self.communication_service.send_message(self.deferral_channel_id, content)
            logger.debug(f"Sent deferral response: {content[:100]}...")
        except Exception as e:
            logger.error(f"Failed to send deferral message: {e}")

    def start(self) -> None:
        """Start the observer - no polling needed since we receive messages directly."""
        logger.info("DiscordObserver started - ready to receive messages directly from Discord adapter")

    def stop(self) -> None:
        """Stop the observer - no background tasks to clean up."""
        logger.info("DiscordObserver stopped")

    def _extract_channel_id(self, full_channel_id: str) -> str:
        """Extract the raw channel ID from discord_guildid_channelid format."""
        if full_channel_id.startswith("discord_") and full_channel_id.count("_") == 2:
            # Format: discord_guildid_channelid
            parts = full_channel_id.split("_")
            return parts[2]  # Return just the channel ID part
        return full_channel_id  # Return as-is if not in expected format

    def _should_process_message(self, msg: DiscordMessage) -> bool:
        """Check if Discord observer should process this message."""
        # Extract the raw channel ID from the formatted channel_id
        raw_channel_id = self._extract_channel_id(msg.channel_id) if msg.channel_id else ""

        # Check if message is from a monitored channel or deferral channel
        is_from_monitored = False
        if self.monitored_channel_ids:
            # Check both raw channel ID and full formatted ID
            is_from_monitored = (
                raw_channel_id in self.monitored_channel_ids or msg.channel_id in self.monitored_channel_ids
            )

        is_from_deferral = False
        if self.deferral_channel_id:
            # Check both raw channel ID and full formatted ID
            is_from_deferral = raw_channel_id == self.deferral_channel_id or msg.channel_id == self.deferral_channel_id

        logger.info(f"Message from {msg.author_name} (ID: {msg.author_id}) in channel {msg.channel_id}")
        logger.info(f"  - Raw channel ID: {raw_channel_id}")
        logger.info(f"  - Is from monitored channel: {is_from_monitored}")
        logger.info(f"  - Is from deferral channel: {is_from_deferral}")
        logger.info(f"  - Monitored channels: {self.monitored_channel_ids}")
        logger.info(f"  - Deferral channel ID: {self.deferral_channel_id}")

        return is_from_monitored or is_from_deferral

    async def _enhance_message(self, msg: DiscordMessage) -> DiscordMessage:
        """Enhance Discord messages with vision processing if available."""
        # Process any images in the message if vision is available
        if self._vision_helper.is_available() and hasattr(msg, "raw_message") and msg.raw_message:
            try:
                # Process attachments
                image_descriptions = await self._vision_helper.process_message_images(msg.raw_message)

                # Process embeds if any
                embed_descriptions = None
                if hasattr(msg.raw_message, "embeds") and msg.raw_message.embeds:
                    embed_descriptions = await self._vision_helper.process_embeds(msg.raw_message.embeds)

                # Append descriptions to the message content
                if image_descriptions or embed_descriptions:
                    additional_content = "\n\n[Image Analysis]\n"
                    if image_descriptions:
                        additional_content += image_descriptions
                    if embed_descriptions:
                        if image_descriptions:
                            additional_content += "\n\n"
                        additional_content += embed_descriptions

                    # Create a new message with the augmented content
                    return DiscordMessage(
                        message_id=msg.message_id,
                        content=msg.content + additional_content,
                        author_id=msg.author_id,
                        author_name=msg.author_name,
                        channel_id=msg.channel_id,
                        is_bot=msg.is_bot,
                        is_dm=msg.is_dm,
                        raw_message=msg.raw_message,
                    )

            except Exception as e:
                logger.error(f"Failed to process images in message {msg.message_id}: {e}")

        return msg

    async def _handle_priority_observation(self, msg: DiscordMessage, filter_result: Any) -> None:
        """Handle high-priority messages with immediate processing"""
        from ciris_engine.logic.utils.constants import DEFAULT_WA

        monitored_channel_ids = self.monitored_channel_ids or []
        wa_discord_user = DEFAULT_WA

        raw_channel_id = self._extract_channel_id(msg.channel_id) if msg.channel_id else ""

        if raw_channel_id in monitored_channel_ids or msg.channel_id in monitored_channel_ids:
            await self._create_priority_observation_result(msg, filter_result)
        elif (raw_channel_id == self.deferral_channel_id or msg.channel_id == self.deferral_channel_id) and (
            msg.author_id in self.wa_user_ids or msg.author_name == wa_discord_user
        ):
            logger.info(f"[PRIORITY] Routing message to WA feedback queue - author {msg.author_name} is WA")
            await self._add_to_feedback_queue(msg)
        else:
            logger.info("[PRIORITY] Not routing to WA feedback - checking conditions:")
            logger.info(f"  - Is deferral channel: {msg.channel_id == self.deferral_channel_id}")
            logger.info(f"  - Author ID in WA list: {msg.author_id in self.wa_user_ids}")
            logger.info(f"  - Author name matches DEFAULT_WA '{wa_discord_user}': {msg.author_name == wa_discord_user}")
            logger.debug(
                "Ignoring priority message from channel %s, author %s (ID: %s)",
                msg.channel_id,
                msg.author_name,
                msg.author_id,
            )

    def _create_task_context_with_extras(self, msg: DiscordMessage) -> TaskContext:
        """Create a TaskContext from a Discord message."""
        return TaskContext(
            channel_id=msg.channel_id, user_id=msg.author_id, correlation_id=msg.message_id, parent_task_id=None
        )

    async def _handle_passive_observation(self, msg: DiscordMessage) -> None:
        """Handle passive observation - routes to WA feedback queue if appropriate."""
        from ciris_engine.logic.utils.constants import DEFAULT_WA

        monitored_channel_ids = self.monitored_channel_ids or []
        wa_discord_user = DEFAULT_WA

        raw_channel_id = self._extract_channel_id(msg.channel_id) if msg.channel_id else ""

        if raw_channel_id in monitored_channel_ids or msg.channel_id in monitored_channel_ids:
            await self._create_passive_observation_result(msg)
        elif (raw_channel_id == self.deferral_channel_id or msg.channel_id == self.deferral_channel_id) and (
            msg.author_id in self.wa_user_ids or msg.author_name == wa_discord_user
        ):
            logger.info(f"Routing message to WA feedback queue - author {msg.author_name} is WA")
            await self._add_to_feedback_queue(msg)
        else:
            logger.info("Not routing to WA feedback - checking conditions:")
            logger.info(f"  - Is deferral channel: {msg.channel_id == self.deferral_channel_id}")
            logger.info(f"  - Author ID in WA list: {msg.author_id in self.wa_user_ids}")
            logger.info(f"  - Author name matches DEFAULT_WA '{wa_discord_user}': {msg.author_name == wa_discord_user}")
            logger.debug(
                "Ignoring message from channel %s, author %s (ID: %s)", msg.channel_id, msg.author_name, msg.author_id
            )

    async def _add_to_feedback_queue(self, msg: DiscordMessage) -> None:
        """Process guidance/feedback from WA in deferral channel."""
        try:
            # First validate that the user is a wise authority
            from ciris_engine.logic.utils.constants import DEFAULT_WA

            wa_discord_user = DEFAULT_WA

            is_wise_authority = msg.author_id in self.wa_user_ids or msg.author_name == wa_discord_user

            if not is_wise_authority:
                error_msg = f"🚫 **Not Authorized**: User `{msg.author_name}` (ID: `{msg.author_id}`) is not a Wise Authority. Not proceeding with guidance processing."
                logger.warning(f"Non-WA user {msg.author_name} ({msg.author_id}) attempted to provide guidance")
                await self._send_deferral_message(error_msg)
                return
            import re
            import uuid
            from datetime import datetime, timezone

            from ciris_engine.logic import persistence
            from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
            from ciris_engine.schemas.runtime.models import Task, Thought

            # Check if this is a reply to a deferral report
            referenced_thought_id = None

            # First check if this message is replying to another message
            logger.info(f"Checking reply detection for message {msg.message_id}")
            if hasattr(msg, "raw_message") and msg.raw_message:
                logger.info(f"Message has raw_message: {msg.raw_message.id}")
                if hasattr(msg.raw_message, "reference"):
                    ref = msg.raw_message.reference
                    logger.info(f"Message reference: {ref}")
                    if ref and ref.resolved:
                        # Check if the referenced message contains a thought ID
                        ref_content = ref.resolved.content
                        logger.info(f"Referenced message content: {ref_content}")
                        thought_id_pattern = r"Thought ID:\s*([a-zA-Z0-9_-]+)"
                        match = re.search(thought_id_pattern, ref_content)
                        if match:
                            referenced_thought_id = match.group(1)
                            logger.info(f"Found reply to deferral for thought ID: {referenced_thought_id}")
                        else:
                            logger.info("No thought ID pattern found in referenced message")
                    else:
                        logger.info("Reference not resolved or None")
                else:
                    logger.info("Message has no reference attribute")
            else:
                logger.info("Message has no raw_message")

            # If not a reply, check if the message itself mentions a thought ID
            if not referenced_thought_id:
                thought_id_pattern = r"(?:thought\s+id|thought_id|re:\s*thought)[\s:]*([a-zA-Z0-9_-]+)"
                match = re.search(thought_id_pattern, msg.content, re.IGNORECASE)
                if match:
                    referenced_thought_id = match.group(1)
                    logger.info(f"Found thought ID reference in message: {referenced_thought_id}")

            if referenced_thought_id:
                # This is guidance for a specific deferred thought
                # Find the original thought and its task
                original_thought = persistence.get_thought_by_id(referenced_thought_id)
                if original_thought is None:
                    error_msg = f"❌ **Error**: Thought `{referenced_thought_id}` not found in database"
                    logger.warning(f"Thought {referenced_thought_id} not found in database")
                    await self._send_deferral_message(error_msg)
                elif original_thought.status != ThoughtStatus.DEFERRED:
                    error_msg = f"❌ **Error**: Thought `{referenced_thought_id}` found but status is `{original_thought.status}`, not `DEFERRED`"
                    logger.warning(
                        f"Thought {referenced_thought_id} found but status is {original_thought.status}, not DEFERRED"
                    )
                    await self._send_deferral_message(error_msg)
                else:
                    # Reactivate the original task
                    original_task = persistence.get_task_by_id(original_thought.source_task_id)
                    if original_task and self.time_service:
                        persistence.update_task_status(original_task.task_id, TaskStatus.ACTIVE, self.time_service)
                        logger.info(f"Reactivated task {original_task.task_id} due to guidance")

                        # Extract deferral reason from the original thought's final_action
                        deferral_reason = "Unknown deferral reason"
                        if original_thought.final_action:
                            action_params = original_thought.final_action.action_params
                            if isinstance(action_params, dict) and "reason" in action_params:
                                deferral_reason = action_params["reason"]

                        # Create a new thought with PROCESSING status that includes original content + deferral reason + WA response
                        # Reset round_number to 0 to give fresh rounds after deferral
                        # Create guidance context by copying original context and adding guidance data
                        if original_thought.context:
                            guidance_context = original_thought.context.model_copy(
                                update={
                                    "guidance_message_id": msg.message_id,
                                    "guidance_author": msg.author_name,
                                    "guidance_content": msg.content,
                                    "is_guidance_response": True,
                                    "original_round_number": original_thought.round_number,  # Store original for reference
                                    "original_thought_id": referenced_thought_id,
                                    "deferral_reason": deferral_reason,
                                }
                            )
                        else:
                            from ciris_engine.schemas.runtime.models import ThoughtContext

                            # Create a ThoughtContext for the guidance thought
                            guidance_context = ThoughtContext(
                                task_id=original_task.task_id,
                                channel_id=msg.channel_id,
                                round_number=0,
                                depth=0,
                                parent_thought_id=referenced_thought_id,
                                correlation_id=str(uuid.uuid4()),
                            )
                            # Add extra fields after creation
                            setattr(guidance_context, "guidance_message_id", msg.message_id)
                            setattr(guidance_context, "guidance_author", msg.author_name)
                            setattr(guidance_context, "guidance_content", msg.content)
                            setattr(guidance_context, "is_guidance_response", True)
                            setattr(guidance_context, "original_round_number", original_thought.round_number)
                            setattr(guidance_context, "original_thought_id", referenced_thought_id)
                            setattr(guidance_context, "deferral_reason", deferral_reason)

                        # Combine content with WA response last to ensure it's acted upon
                        combined_content = (
                            f"ORIGINAL THOUGHT: {original_thought.content}\n\n"
                            f"DEFERRED WITH QUESTION FOR WA: {deferral_reason}\n\n"
                            f"WISE AUTHORITY RESPONSE: {msg.content}"
                        )

                        guidance_thought = Thought(
                            thought_id=str(uuid.uuid4()),
                            source_task_id=original_task.task_id,
                            parent_thought_id=referenced_thought_id,
                            thought_type=ThoughtType.GUIDANCE,
                            status=ThoughtStatus.PENDING,  # Must be PENDING to enter processing queue!
                            created_at=(
                                self.time_service.now_iso()
                                if self.time_service
                                else datetime.now(timezone.utc).isoformat()
                            ),
                            updated_at=(
                                self.time_service.now_iso()
                                if self.time_service
                                else datetime.now(timezone.utc).isoformat()
                            ),
                            round_number=0,  # Reset to 0 for fresh processing after guidance
                            content=combined_content,
                            context=guidance_context,
                        )
                        persistence.add_thought(guidance_thought)
                        logger.info(
                            f"Created guidance thought {guidance_thought.thought_id} as child of deferred thought {referenced_thought_id}"
                        )

                        # Send success confirmation
                        success_msg = (
                            f"✅ **Guidance Received**: Successfully processed guidance for thought `{referenced_thought_id}`\n"
                            f"📝 **Task**: Reactivated task `{original_task.task_id}`\n"
                            f"🧠 **New Thought**: Created guidance thought `{guidance_thought.thought_id}`\n"
                            "🔄 **Status**: Ready for processing"
                        )
                        await self._send_deferral_message(success_msg)
                        return

            # If we get here, it's unsolicited guidance - create a new task
            task = Task(
                task_id=str(uuid.uuid4()),
                channel_id=msg.channel_id,
                description=f"Guidance received from authorized WA {msg.author_name} (ID: {msg.author_id}) please act accordingly",
                status=TaskStatus.PENDING,
                priority=8,  # High priority for guidance
                created_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                updated_at=self.time_service.now_iso() if self.time_service else datetime.now(timezone.utc).isoformat(),
                context=self._create_task_context_with_extras(msg),
            )
            persistence.add_task(task)
            logger.info(
                f"Created unsolicited guidance task {task.task_id} - seed thought will be generated automatically"
            )

        except Exception as e:
            logger.error(f"Error processing guidance message {msg.message_id}: {e}", exc_info=True)
