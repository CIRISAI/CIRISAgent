import logging
from typing import Dict, Any, List, Optional


from ciris_engine.schemas.agent_core_schemas_v1 import Thought
from ciris_engine.schemas.action_params_v1 import ObserveParams
from ciris_engine.schemas.dma_results_v1 import ActionSelectionResult
from ciris_engine.schemas.foundational_schemas_v1 import (
    ThoughtStatus,
    HandlerActionType,
    FetchedMessage,
    DispatchContext,
)
from ciris_engine.schemas.context_schemas_v1 import ChannelContext
from ciris_engine.schemas.graph_schemas_v1 import GraphScope, GraphNode, NodeType
from ciris_engine.utils.channel_utils import extract_channel_id, create_channel_context
from ciris_engine import persistence
from .base_handler import BaseActionHandler
from .helpers import create_follow_up_thought
from .exceptions import FollowUpCreationError

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
                    
                    from ciris_engine.schemas.memory_schemas_v1 import MemoryQuery
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
        result: ActionSelectionResult,
        thought: Thought,
        dispatch_context: DispatchContext,
    ) -> None:
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
            params = await self._validate_and_convert_params(raw_params, ObserveParams)
            assert isinstance(params, ObserveParams)  # Type assertion after validation
        except Exception as e:
            await self._handle_error(HandlerActionType.OBSERVE, dispatch_context, thought_id, e)
            persistence.update_thought_status(
                thought_id=thought_id,
                status=ThoughtStatus.FAILED,
                final_action=result,
            )
            follow_up_text = f"OBSERVE action failed for thought {thought_id}. Reason: {e}"
            try:
                fu = create_follow_up_thought(parent=thought, content=follow_up_text)
                context_data = fu.context.model_dump() if fu.context else {}
                context_data.update({
                    "action_performed": HandlerActionType.OBSERVE.value,
                    "error_details": str(e),
                    "action_params": result.action_parameters,
                })
                from ciris_engine.schemas.context_schemas_v1 import ThoughtContext
                fu.context = ThoughtContext.model_validate(context_data)
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
        logger.debug(f"ObserveHandler: Using bus manager for communication and memory operations")

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

        persistence.update_thought_status(
            thought_id=thought_id,
            status=final_status,
            final_action=result,
        )

        follow_up_text = (
            f"CIRIS_FOLLOW_UP_THOUGHT: OBSERVE action completed. Info: {follow_up_info}"
            if action_performed
            else f"CIRIS_FOLLOW_UP_THOUGHT: OBSERVE action failed: {follow_up_info}"
        )
        try:
            logger.info(f"ObserveHandler: Creating follow-up thought for {thought_id}")
            new_follow_up = create_follow_up_thought(parent=thought, content=follow_up_text)
            context_data = new_follow_up.context.model_dump() if new_follow_up.context else {}
            ctx = {
                "action_performed": HandlerActionType.OBSERVE.value,
                "action_params": params,
            }
            if final_status == ThoughtStatus.FAILED:
                ctx["error_details"] = follow_up_info
            context_data.update(ctx)
            from ciris_engine.schemas.context_schemas_v1 import ThoughtContext
            new_follow_up.context = ThoughtContext.model_validate(context_data)
            persistence.add_thought(new_follow_up)
            logger.info(f"ObserveHandler: Follow-up thought created for {thought_id}")

        except Exception as e:
            logger.critical(
                "Failed to create follow-up for %s: %s", thought_id, e, exc_info=e
            )
            await self._audit_log(
                HandlerActionType.OBSERVE,
                dispatch_context,
                outcome="failed_followup",
            )
            raise FollowUpCreationError from e

