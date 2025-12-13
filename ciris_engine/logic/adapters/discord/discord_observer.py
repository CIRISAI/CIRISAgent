import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.adapters.base_observer import BaseObserver
from ciris_engine.logic.adapters.discord.discord_vision_helper import DiscordVisionHelper
from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.utils.task_thought_factory import create_task, create_thought
from ciris_engine.schemas.runtime.enums import ThoughtType
from ciris_engine.schemas.runtime.messages import DiscordMessage
from ciris_engine.schemas.runtime.models import TaskContext
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

PASSIVE_CONTEXT_LIMIT = 20


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

        # Initialize vision helper (native multimodal is always available)
        self._vision_helper = DiscordVisionHelper()
        logger.info("Discord Vision Helper initialized - native multimodal image processing enabled")

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

    async def start(self) -> None:
        """Start the observer - no polling needed since we receive messages directly."""
        logger.info("DiscordObserver started - ready to receive messages directly from Discord adapter")

    async def stop(self) -> None:
        """Stop the observer - no background tasks to clean up."""
        logger.info("DiscordObserver stopped")

    def _extract_channel_id(self, full_channel_id: str) -> str:
        """Extract the raw channel ID from discord_channelid or discord_guildid_channelid format."""
        if full_channel_id.startswith("discord_"):
            parts = full_channel_id.split("_")
            if len(parts) == 2:
                # Format: discord_channelid
                return parts[1]
            elif len(parts) == 3:
                # Format: discord_guildid_channelid
                return parts[2]
        return full_channel_id  # Return as-is if not in expected format

    async def _should_process_message(self, msg: DiscordMessage) -> bool:
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

    def _detect_and_replace_spoofed_markers(self, content: str) -> str:
        """Detect and replace attempts to spoof CIRIS security markers."""
        from ciris_engine.logic.adapters.base_observer import detect_and_replace_spoofed_markers

        return detect_and_replace_spoofed_markers(content)

    async def _collect_message_attachments_with_reply(self, raw_message: Any) -> JSONDict:
        """Collect attachments from message and reply with priority rules.

        Priority rules:
        1. Reply message wins - if reply has image and 3 attachments, replied-to message only contributes text
        2. Maximum 1 image total across both messages
        3. Maximum 3 documents total across both messages
        4. Reply context (text) is always included if this is a reply

        Returns:
            dict with keys: images, documents, embeds, reply_context
        """
        result: JSONDict = {"images": [], "documents": [], "embeds": [], "reply_context": None}

        # Fetch referenced message and build reply context
        referenced_message = await self._fetch_referenced_message(raw_message)
        if referenced_message:
            reply_ctx = self._build_reply_context(referenced_message)
            result["reply_context"] = reply_ctx

        # Build message processing order (reply gets priority)
        messages_to_process = self._build_message_processing_order(raw_message, referenced_message)

        # Process attachments respecting limits
        self._process_message_attachments(messages_to_process, result)

        return result

    async def _fetch_referenced_message(self, raw_message: Any) -> Optional[Any]:
        """Fetch the referenced message if this is a reply."""
        if not hasattr(raw_message, "reference") or not raw_message.reference:
            return None

        try:
            # Use resolved message if available
            if hasattr(raw_message.reference, "resolved") and raw_message.reference.resolved:
                return raw_message.reference.resolved

            # Fallback: fetch manually if not resolved
            channel = raw_message.channel
            return await channel.fetch_message(raw_message.reference.message_id)

        except Exception as e:
            logger.warning(f"Failed to fetch referenced message: {e}")
            return None

    def _build_reply_context(self, referenced_message: Any) -> Optional[str]:
        """Build reply context string from referenced message."""
        if not referenced_message or not referenced_message.content:
            return None

        author_name = getattr(referenced_message.author, "display_name", "Unknown")
        return f"@{author_name}: {referenced_message.content}"

    def _build_message_processing_order(
        self, raw_message: Any, referenced_message: Optional[Any]
    ) -> List[Tuple[str, Any]]:
        """Build the order of messages to process (reply gets priority)."""
        messages_to_process: List[Tuple[str, Any]] = []

        # Reply message gets first priority
        if raw_message:
            messages_to_process.append(("reply", raw_message))

        # Original message gets second priority
        if referenced_message:
            messages_to_process.append(("original", referenced_message))

        return messages_to_process

    def _process_message_attachments(self, messages_to_process: List[Tuple[str, Any]], result: JSONDict) -> None:
        """Process attachments from messages respecting limits."""
        image_count = 0
        document_count = 0

        # Get lists with type safety
        images_list: List[Any] = result.get("images", []) if isinstance(result.get("images"), list) else []  # type: ignore[assignment]
        documents_list: List[Any] = result.get("documents", []) if isinstance(result.get("documents"), list) else []  # type: ignore[assignment]

        for message_type, message in messages_to_process:
            if not message:
                continue

            # Process image attachments (max 1 total)
            image_count += self._process_image_attachments(message, images_list, image_count)

            # Process document attachments (max 3 total)
            document_count += self._process_document_attachments(message, documents_list, document_count)

            # Process embeds (only from reply message to avoid duplication)
            if message_type == "reply" and hasattr(message, "embeds") and message.embeds:
                result["embeds"] = message.embeds

        # Update result with processed lists
        result["images"] = images_list
        result["documents"] = documents_list

    def _process_image_attachments(self, message: Any, images_list: List[Any], current_count: int) -> int:
        """Process image attachments from a message, return count of images added."""
        added_count = 0
        if not hasattr(message, "attachments") or not message.attachments or current_count >= 1:
            return added_count

        for attachment in message.attachments:
            if current_count + added_count >= 1:
                break
            if self._is_image_attachment(attachment):
                images_list.append(attachment)
                added_count += 1

        return added_count

    def _process_document_attachments(self, message: Any, documents_list: List[Any], current_count: int) -> int:
        """Process document attachments from a message, return count of documents added."""
        added_count = 0
        if not hasattr(message, "attachments") or not message.attachments or current_count >= 3:
            return added_count

        for attachment in message.attachments:
            if current_count + added_count >= 3:
                break
            # Use document parser's filtering if available
            if self._document_parser.is_available():
                if self._document_parser._is_document_attachment(attachment):
                    documents_list.append(attachment)
                    added_count += 1

        return added_count

    def _is_image_attachment(self, attachment: Any) -> bool:
        """Check if attachment is an image."""
        if not hasattr(attachment, "content_type") or not attachment.content_type:
            return False

        image_types = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/svg+xml", "image/bmp"]
        return attachment.content_type.lower() in image_types

    async def _enhance_message(self, msg: DiscordMessage) -> DiscordMessage:
        """Enhance Discord messages with vision processing, document parsing, reply context, and anti-spoofing protection."""
        # First, detect and replace any spoofed markers
        clean_content = self._detect_and_replace_spoofed_markers(msg.content)

        additional_content = ""
        collected_images: List[Any] = []  # ImageContent objects for native multimodal

        # Check if this message is a reply and process both messages with attachment limits
        if hasattr(msg, "raw_message") and msg.raw_message:
            try:
                # Detect reply and collect attachment/image data with priority rules
                attachments_data = await self._collect_message_attachments_with_reply(msg.raw_message)

                # Process images for native multimodal (convert to ImageContent)
                images_raw = attachments_data.get("images")
                if self._vision_helper.is_available() and images_raw and isinstance(images_raw, list):
                    # Convert Discord attachments to ImageContent for native multimodal
                    image_contents = await self._vision_helper.process_image_attachments_list(images_raw)
                    if image_contents:
                        collected_images.extend(image_contents)
                        logger.info(
                            f"[VISION] Converted {len(image_contents)} attachments to ImageContent for native multimodal"
                        )

                    # Process embeds for additional images
                    embeds_raw = attachments_data.get("embeds")
                    if embeds_raw and isinstance(embeds_raw, list):
                        embed_images = await self._vision_helper.process_embeds(embeds_raw)
                        if embed_images:
                            collected_images.extend(embed_images)
                            logger.info(f"[VISION] Converted {len(embed_images)} embed images to ImageContent")

                # Process document attachments if document parser is available
                documents_raw = attachments_data.get("documents")
                if self._document_parser.is_available() and documents_raw and isinstance(documents_raw, list):
                    document_text = await self._document_parser.process_attachments(documents_raw)

                    if document_text:
                        additional_content += "\n\n[Document Analysis]\n" + document_text

                # Add reply context if this is a reply
                if attachments_data.get("reply_context"):
                    additional_content += f"\n\n[Reply Context]\n{attachments_data['reply_context']}"

            except Exception as e:
                logger.error(f"Failed to process attachments in message {msg.message_id}: {e}")
                additional_content += f"\n\n[Attachment Processing Error: {str(e)}]"

        # Create enhanced message if we have additional content, cleaned content, or images
        if additional_content or clean_content != msg.content or collected_images:
            return DiscordMessage(
                message_id=msg.message_id,
                content=clean_content + additional_content,
                author_id=msg.author_id,
                author_name=msg.author_name,
                channel_id=msg.channel_id,
                is_bot=msg.is_bot,
                is_dm=msg.is_dm,
                raw_message=msg.raw_message,
                images=collected_images,  # Native multimodal images
            )

        return msg

    async def _handle_priority_observation(self, msg: DiscordMessage, filter_result: Any) -> None:
        """Handle high-priority messages with immediate processing"""
        monitored_channel_ids = self.monitored_channel_ids or []

        raw_channel_id = self._extract_channel_id(msg.channel_id) if msg.channel_id else ""

        # Log the routing decision
        logger.info(
            f"[DISCORD-PRIORITY] Routing message {msg.message_id} from @{msg.author_name} "
            f"(ID: {msg.author_id}) in channel {msg.channel_id}"
        )

        # First check if it's a monitored channel - create task regardless of author
        if raw_channel_id in monitored_channel_ids or msg.channel_id in monitored_channel_ids:
            logger.info(
                f"[DISCORD-PRIORITY] Channel {msg.channel_id} IS MONITORED - CREATING PRIORITY TASK "
                f"(priority: {filter_result.priority.value}, filters: {', '.join(filter_result.triggered_filters)})"
            )
            await self._create_priority_observation_result(msg, filter_result)
        # Then check if it's deferral channel AND author is WA
        elif (raw_channel_id == self.deferral_channel_id or msg.channel_id == self.deferral_channel_id) and (
            msg.author_id in self.wa_user_ids
        ):
            logger.info(
                f"[DISCORD-PRIORITY] Channel {msg.channel_id} is DEFERRAL channel and author {msg.author_name} "
                f"IS WA - routing to WA feedback queue"
            )
            await self._add_to_feedback_queue(msg)
        else:
            logger.warning(
                f"[DISCORD-PRIORITY] NO TASK CREATED for message {msg.message_id} from @{msg.author_name} "
                f"in channel {msg.channel_id} - REASON: Channel not monitored or not valid deferral"
            )
            logger.info(f"  - Raw channel ID: {raw_channel_id}")
            logger.info(f"  - Monitored channels: {monitored_channel_ids}")
            logger.info(
                f"  - Channel {msg.channel_id} monitored: {raw_channel_id in monitored_channel_ids or msg.channel_id in monitored_channel_ids}"
            )
            logger.info(f"  - Deferral channel: {self.deferral_channel_id}")
            logger.info(
                f"  - Is deferral channel: {msg.channel_id == self.deferral_channel_id or raw_channel_id == self.deferral_channel_id}"
            )
            if msg.channel_id == self.deferral_channel_id or raw_channel_id == self.deferral_channel_id:
                logger.info(
                    f"  - Author ID {msg.author_id} in WA list {self.wa_user_ids}: {msg.author_id in self.wa_user_ids}"
                )
                # Username matching removed for security - only numeric IDs are checked

    def _create_task_context_with_extras(self, msg: DiscordMessage) -> TaskContext:
        """Create a TaskContext from a Discord message."""
        return TaskContext(
            channel_id=msg.channel_id, user_id=msg.author_id, correlation_id=msg.message_id, parent_task_id=None
        )

    async def _handle_passive_observation(self, msg: DiscordMessage) -> None:
        """Handle passive observation - routes to WA feedback queue if appropriate."""
        monitored_channel_ids = self.monitored_channel_ids or []

        raw_channel_id = self._extract_channel_id(msg.channel_id) if msg.channel_id else ""

        # Log the routing decision
        logger.info(
            f"[DISCORD-PASSIVE] Routing message {msg.message_id} from @{msg.author_name} "
            f"(ID: {msg.author_id}) in channel {msg.channel_id}"
        )

        # First check if it's a monitored channel - create task regardless of author
        if raw_channel_id in monitored_channel_ids or msg.channel_id in monitored_channel_ids:
            logger.info(f"[DISCORD-PASSIVE] Channel {msg.channel_id} IS MONITORED - CREATING PASSIVE TASK")
            await self._create_passive_observation_result(msg)
        # Then check if it's deferral channel AND author is WA
        elif (raw_channel_id == self.deferral_channel_id or msg.channel_id == self.deferral_channel_id) and (
            msg.author_id in self.wa_user_ids
        ):
            logger.info(
                f"[DISCORD-PASSIVE] Channel {msg.channel_id} is DEFERRAL channel and author {msg.author_name} "
                f"IS WA - routing to WA feedback queue"
            )
            await self._add_to_feedback_queue(msg)
        else:
            logger.warning(
                f"[DISCORD-PASSIVE] NO TASK CREATED for message {msg.message_id} from @{msg.author_name} "
                f"in channel {msg.channel_id} - REASON: Channel not monitored or not valid deferral"
            )
            logger.info(f"  - Raw channel ID: {raw_channel_id}")
            logger.info(f"  - Monitored channels: {monitored_channel_ids}")
            logger.info(
                f"  - Channel {msg.channel_id} monitored: {raw_channel_id in monitored_channel_ids or msg.channel_id in monitored_channel_ids}"
            )
            logger.info(f"  - Deferral channel: {self.deferral_channel_id}")
            logger.info(
                f"  - Is deferral channel: {msg.channel_id == self.deferral_channel_id or raw_channel_id == self.deferral_channel_id}"
            )
            if msg.channel_id == self.deferral_channel_id or raw_channel_id == self.deferral_channel_id:
                logger.info(
                    f"  - Author ID {msg.author_id} in WA list {self.wa_user_ids}: {msg.author_id in self.wa_user_ids}"
                )
                # Username matching removed for security - only numeric IDs are checked

    async def _add_to_feedback_queue(self, msg: DiscordMessage) -> None:
        """Process guidance/feedback from WA in deferral channel."""
        try:
            # First validate that the user is a wise authority
            # Only check numeric IDs for security - usernames can be spoofed
            is_wise_authority = msg.author_id in self.wa_user_ids

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
                    if original_task and self.time_service and self.agent_id:
                        persistence.update_task_status(
                            original_task.task_id, TaskStatus.ACTIVE, self.agent_id, self.time_service
                        )
                        logger.info(f"Reactivated task {original_task.task_id} due to guidance")

                        # Extract deferral reason from the original thought's final_action
                        deferral_reason = "Unknown deferral reason"
                        if original_thought.final_action:
                            action_params = original_thought.final_action.action_params
                            if isinstance(action_params, dict) and "reason" in action_params:
                                reason_value = action_params["reason"]
                                deferral_reason = (
                                    str(reason_value) if reason_value is not None else "Unknown deferral reason"
                                )

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
                                agent_occurrence_id=self.agent_occurrence_id,  # FIXED: Now includes occurrence_id!
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

                        # Use factory to create guidance thought with proper occurrence_id
                        guidance_thought = create_thought(
                            source_task_id=original_task.task_id,
                            agent_occurrence_id=self.agent_occurrence_id,
                            correlation_id=guidance_context.correlation_id,
                            content=combined_content,
                            time_service=self.time_service,
                            thought_type=ThoughtType.GUIDANCE,
                            status=ThoughtStatus.PENDING,  # Must be PENDING to enter processing queue!
                            channel_id=msg.channel_id,
                            round_number=0,  # Reset to 0 for fresh processing after guidance
                            thought_depth=0,
                            parent_thought_id=referenced_thought_id,
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

            # If we get here, it's unsolicited guidance - create a new task using factory
            task = create_task(
                description=f"Guidance received from authorized WA {msg.author_name} (ID: {msg.author_id}) please act accordingly",
                channel_id=msg.channel_id or "system",
                agent_occurrence_id=self.agent_occurrence_id,
                correlation_id=msg.message_id,
                time_service=self.time_service,
                status=TaskStatus.PENDING,
                priority=8,  # High priority for guidance
                user_id=msg.author_id,
            )
            persistence.add_task(task)
            logger.info(
                f"Created unsolicited guidance task {task.task_id} - seed thought will be generated automatically"
            )

        except Exception as e:
            logger.error(f"Error processing guidance message {msg.message_id}: {e}", exc_info=True)

    async def _get_guild_moderators(self, guild_id: str) -> List[JSONDict]:
        """Get list of guild moderators using the Discord tool service."""
        try:
            if not self.communication_service:
                logger.warning("No communication service available to get guild moderators")
                return []

            # Try to get the Discord tool service from communication service
            if hasattr(self.communication_service, "_discord_tool_service"):
                tool_service = self.communication_service._discord_tool_service
                result = await tool_service._get_guild_moderators({"guild_id": guild_id})

                if result.get("success") and "data" in result:
                    moderators_raw = result["data"].get("moderators", [])
                    moderators: List[JSONDict] = [dict(mod) for mod in moderators_raw if isinstance(mod, dict)]
                    logger.info(f"Retrieved {len(moderators)} moderators from guild {guild_id}")
                    return moderators
                else:
                    logger.warning(f"Failed to get moderators: {result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"Error getting guild moderators: {e}")

        return []

    def _extract_guild_id_from_channel(self, channel_id: str) -> Optional[str]:
        """Extract guild ID from channel ID format (discord_guildid_channelid)."""
        if channel_id and channel_id.startswith("discord_"):
            parts = channel_id.split("_")
            if len(parts) == 3:  # Format: discord_guildid_channelid
                return parts[1]
        return None

    async def _add_custom_context_sections(
        self, task_lines: List[str], msg: DiscordMessage, history_context: List[JSONDict]
    ) -> None:
        """Add Discord-specific ACTIVE MODS section to context."""
        # Add ACTIVE MODS section for Discord
        channel_id = msg.channel_id if msg.channel_id else ""
        guild_id = self._extract_guild_id_from_channel(channel_id)
        if guild_id:
            moderators = await self._get_guild_moderators(guild_id)
            if moderators:
                task_lines.append("\n=== ACTIVE MODS ===")
                for mod in moderators:
                    nickname = mod.get("nickname") or mod.get("display_name") or mod.get("username")
                    task_lines.append(f"ID: {mod['user_id']} | Nick: {nickname}")
                task_lines.append("=== END ACTIVE MODS ===")
            else:
                task_lines.append("\n=== ACTIVE MODS ===")
                task_lines.append("No moderators available or unable to retrieve moderator list")
                task_lines.append("=== END ACTIVE MODS ===")
