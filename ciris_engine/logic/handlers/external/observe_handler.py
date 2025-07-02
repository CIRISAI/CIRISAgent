import logging
from typing import List, Optional

from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.actions import ObserveParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import (
    ThoughtStatus, HandlerActionType,
)
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.messages import FetchedMessage
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.graph_core import GraphScope
from ciris_engine.schemas.services.graph_core import NodeType
from ciris_engine.logic.utils.channel_utils import extract_channel_id
from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.helpers import create_follow_up_thought
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError

PASSIVE_OBSERVE_LIMIT = 10
ACTIVE_OBSERVE_LIMIT = 50

logger = logging.getLogger(__name__)

class ObserveHandler(BaseActionHandler):

    async def _recall_from_messages(
        self,
        channel_id: Optional[str],
        messages: List[FetchedMessage],
    ) -> None:
        recall_ids = set()
        if channel_id:
            recall_ids.add(f"channel/{channel_id}")
        for msg in messages or []:
            aid = msg.author_id if hasattr(msg, 'author_id') else getattr(msg, 'author_id', None)
            if aid:
                recall_ids.add(f"user/{aid}")
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

                    from ciris_engine.schemas.services.operations import MemoryQuery
                    query = MemoryQuery(
                        node_id=rid,
                        scope=scope,
                        type=node_type,
                        include_edges=False,
                        depth=1
                    )
                    await self.bus_manager.memory.recall(
                        recall_query=query,
                        handler_name=self.__class__.__name__
                    )
                except Exception:
                    continue

    async def handle(
        self,
        result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext,
    ) -> Optional[str]:
        raw_params = result.action_parameters
        thought_id = thought.thought_id

        logger.info(f"ObserveHandler: Starting handle for thought {thought_id}")
        logger.debug(f"ObserveHandler: Parameters: {raw_params}")
        logger.debug(f"ObserveHandler: Dispatch context fields: {list(dispatch_context.__class__.model_fields.keys())}")

        await self._audit_log(
            HandlerActionType.OBSERVE,
            dispatch_context,
            outcome="start",
        )

        final_status = ThoughtStatus.COMPLETED
        action_performed = False
        follow_up_info = f"OBSERVE action for thought {thought_id}"

        try:
            params: ObserveParams = await self._validate_and_convert_params(raw_params, ObserveParams)
            assert isinstance(params, ObserveParams)  # Type assertion after validation
        except Exception as e:
            await self._handle_error(HandlerActionType.OBSERVE, dispatch_context, thought_id, e)
            # Mark thought as failed and create error follow-up
            return await self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=f"OBSERVE action failed: {e}",
                action_result=result
            )
            follow_up_text = f"OBSERVE action failed for thought {thought_id}. Reason: {e}"
            try:
                fu = create_follow_up_thought(parent=thought, time_service=self.time_service, content=follow_up_text)
                context_data = fu.context.model_dump() if fu.context else {}
                context_data.update({
                    "action_performed": HandlerActionType.OBSERVE.value,
                    "error_details": str(e),
                    "action_params": result.action_parameters,
                })
                from ciris_engine.schemas.runtime.system_context import ThoughtState
                fu.context = ThoughtState.model_validate(context_data)
                persistence.add_thought(fu)
            except Exception as fe:
                await self._handle_error(HandlerActionType.OBSERVE, dispatch_context, thought_id, fe)
                raise FollowUpCreationError from fe
            return

        if not params.active:
            logger.debug(f"Passive observation for thought {thought_id} - no action needed")
            persistence.update_thought_status(
                thought_id=thought_id,
                status=ThoughtStatus.COMPLETED,
                final_action=result,
            )
            return

        # Get channel context from params or dispatch
        channel_context: Optional[ChannelContext] = params.channel_context or dispatch_context.channel_context

        # Fallback to thought context if needed
        if not channel_context and thought.context and hasattr(thought.context, 'system_snapshot'):
            channel_context = thought.context.system_snapshot.channel_context

        # Update params with the resolved channel context
        if channel_context:
            params.channel_context = channel_context

        # Extract channel ID for legacy API usage
        channel_id = extract_channel_id(channel_context)
        if channel_id and isinstance(channel_id, str) and channel_id.startswith("@"):
            channel_id = None

        # Use bus manager instead of getting services directly
        logger.debug("ObserveHandler: Using bus manager for communication and memory operations")

        try:
            logger.info(f"ObserveHandler: Performing active observation for channel {channel_id}")
            if not channel_id:
                raise RuntimeError(f"No channel_id ({channel_id})")
            messages = await self.bus_manager.communication.fetch_messages(
                channel_id=str(channel_id).lstrip("#"),
                limit=ACTIVE_OBSERVE_LIMIT,
                handler_name=self.__class__.__name__
            )
            if messages is None:
                raise RuntimeError("Failed to fetch messages via multi-service sink")
            await self._recall_from_messages(channel_id, messages)
            action_performed = True
            follow_up_info = f"Fetched {len(messages)} messages from {channel_id}"
            logger.info(f"ObserveHandler: Active observation complete - {follow_up_info}")
        except Exception as e:
            logger.exception(f"ObserveHandler error for {thought_id}: {e}")
            final_status = ThoughtStatus.FAILED
            follow_up_info = str(e)

        follow_up_text = (
            f"CIRIS_FOLLOW_UP_THOUGHT: OBSERVE action completed. Info: {follow_up_info}"
            if action_performed
            else f"CIRIS_FOLLOW_UP_THOUGHT: OBSERVE action failed: {follow_up_info}"
        )
        
        # Use centralized method to complete thought and create follow-up
        follow_up_id = await self.complete_thought_and_create_followup(
            thought=thought,
            follow_up_content=follow_up_text,
            action_result=result
        )
        
        if not follow_up_id:
            logger.critical(f"Failed to create follow-up for {thought_id}")
            await self._audit_log(
                HandlerActionType.OBSERVE,
                dispatch_context,
                outcome="failed_followup",
            )
            raise FollowUpCreationError("Failed to create follow-up thought")
