import logging
from typing import List, Optional, Union

from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
from ciris_engine.logic.utils.channel_utils import extract_channel_id
from ciris_engine.schemas.actions import ObserveParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.messages import FetchedMessage
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery

PASSIVE_OBSERVE_LIMIT = 10
ACTIVE_OBSERVE_LIMIT = 50

logger = logging.getLogger(__name__)


class ObserveHandler(BaseActionHandler):
    async def handle(
        self,
        result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext,
    ) -> Optional[str]:
        thought_id = thought.thought_id

        logger.info(f"ObserveHandler: Starting handle for thought {thought_id}")
        logger.debug(f"ObserveHandler: Parameters: {result.action_parameters}")

        # Validate parameters
        params_or_error = await self._validate_observe_params(result, thought, dispatch_context)
        if isinstance(params_or_error, str):
            return params_or_error  # Error follow-up ID
        params = params_or_error

        # Force active observation
        params.active = True

        # Resolve channel ID
        channel_id = self._resolve_channel_id(params, thought, dispatch_context)

        # Perform observation
        success, follow_up_info = await self._fetch_and_recall_messages(channel_id, thought_id)

        # Create follow-up thought
        return self._complete_observe_action(thought, result, success, follow_up_info)

    async def _validate_observe_params(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> Union[ObserveParams, str]:
        """Validate and convert observe parameters. Returns ObserveParams on success, follow_up_id on failure."""
        try:
            params = self._validate_and_convert_params(result.action_parameters, ObserveParams)
            return params
        except Exception as e:
            await self._handle_error(HandlerActionType.OBSERVE, dispatch_context, thought.thought_id, e)
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=f"OBSERVE action failed: {e}",
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

    def _resolve_channel_id(
        self, params: ObserveParams, thought: Thought, dispatch_context: DispatchContext
    ) -> Optional[str]:
        """Resolve channel ID from params, context, or thought."""
        # First check params.channel_id
        if params.channel_id:
            return params.channel_id

        # Get channel context from params or dispatch
        channel_context: Optional[ChannelContext] = params.channel_context or dispatch_context.channel_context

        # Fallback to thought context if needed
        if not channel_context and thought.context and hasattr(thought.context, "system_snapshot"):
            channel_context = thought.context.system_snapshot.channel_context

        # Update params with resolved channel context
        if channel_context:
            params.channel_context = channel_context

        # Extract channel ID
        channel_id = extract_channel_id(channel_context)

        # Filter out user mentions
        if channel_id and isinstance(channel_id, str) and channel_id.startswith("@"):
            channel_id = None

        return channel_id

    async def _fetch_and_recall_messages(self, channel_id: Optional[str], thought_id: str) -> tuple[bool, str]:
        """Fetch messages and recall related nodes. Returns (success, follow_up_info)."""
        logger.debug("ObserveHandler: Using bus manager for communication and memory operations")

        try:
            logger.info(f"ObserveHandler: Performing active observation for channel {channel_id}")

            if not channel_id:
                raise RuntimeError(f"No channel_id ({channel_id})")

            messages = await self.bus_manager.communication.fetch_messages(
                channel_id=str(channel_id).lstrip("#"),
                limit=ACTIVE_OBSERVE_LIMIT,
                handler_name=self.__class__.__name__,
            )

            if messages is None:
                raise RuntimeError("Failed to fetch messages via multi-service sink")

            await self._recall_from_messages(channel_id, messages)

            follow_up_info = f"Fetched {len(messages)} messages from {channel_id}"
            logger.info(f"ObserveHandler: Active observation complete - {follow_up_info}")
            return True, follow_up_info

        except Exception as e:
            logger.exception(f"ObserveHandler error for {thought_id}: {e}")
            return False, str(e)

    async def _recall_from_messages(
        self,
        channel_id: Optional[str],
        messages: List[FetchedMessage],
    ) -> None:
        """Recall nodes related to channel and message authors."""
        recall_ids = self._build_recall_ids(channel_id, messages)

        for rid in recall_ids:
            await self._recall_node(rid)

    def _build_recall_ids(self, channel_id: Optional[str], messages: List[FetchedMessage]) -> set:
        """Build set of node IDs to recall."""
        recall_ids = set()

        if channel_id:
            recall_ids.add(f"channel/{channel_id}")

        for msg in messages or []:
            author_id = getattr(msg, "author_id", None)
            if author_id:
                recall_ids.add(f"user/{author_id}")

        return recall_ids

    async def _recall_node(self, node_id: str) -> None:
        """Recall a single node across all scopes."""
        node_type = self._get_node_type_from_id(node_id)

        for scope in (GraphScope.IDENTITY, GraphScope.ENVIRONMENT, GraphScope.LOCAL):
            try:
                query = MemoryQuery(node_id=node_id, scope=scope, type=node_type, include_edges=False, depth=1)
                await self.bus_manager.memory.recall(recall_query=query, handler_name=self.__class__.__name__)
            except Exception:
                continue

    def _get_node_type_from_id(self, node_id: str) -> NodeType:
        """Determine node type from ID prefix."""
        if node_id.startswith("channel/"):
            return NodeType.CHANNEL
        elif node_id.startswith("user/"):
            return NodeType.USER
        return NodeType.CONCEPT

    def _complete_observe_action(
        self, thought: Thought, result: ActionSelectionDMAResult, success: bool, follow_up_info: str
    ) -> str:
        """Complete the observe action and create follow-up thought."""
        if success:
            follow_up_text = f"CIRIS_FOLLOW_UP_THOUGHT: OBSERVE action completed. Info: {follow_up_info}"
            final_status = ThoughtStatus.COMPLETED
        else:
            follow_up_text = f"CIRIS_FOLLOW_UP_THOUGHT: OBSERVE action failed: {follow_up_info}"
            final_status = ThoughtStatus.FAILED

        follow_up_id = self.complete_thought_and_create_followup(
            thought=thought, follow_up_content=follow_up_text, action_result=result, status=final_status
        )

        if not follow_up_id:
            logger.critical(f"Failed to create follow-up for {thought.thought_id}")
            raise FollowUpCreationError("Failed to create follow-up thought")

        return follow_up_id
