"""
Memorize handler - clean implementation using BusManager
"""

import logging
from typing import Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
from ciris_engine.logic.infrastructure.handlers.helpers import create_follow_up_thought
from ciris_engine.logic.infrastructure.handlers.shared_helpers import (
    check_managed_attributes,
    create_config_node,
    extract_user_id_from_node,
    handle_user_consent,
    is_config_node,
    is_identity_node,
    is_user_node,
    validate_config_node,
)
from ciris_engine.logic.services.governance.consent import ConsentService
from ciris_engine.schemas.actions import MemorizeParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.graph_core import GraphNode
from ciris_engine.schemas.services.operations import MemoryOpStatus

logger = logging.getLogger(__name__)


class MemorizeHandler(BaseActionHandler):
    """Handler for MEMORIZE actions."""

    async def handle(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> Optional[str]:
        """Handle a memorize action."""
        thought_id = thought.thought_id

        # Validate parameters
        try:
            params: MemorizeParams = self._validate_and_convert_params(result.action_parameters, MemorizeParams)
        except Exception as e:
            await self._handle_error(HandlerActionType.MEMORIZE, dispatch_context, thought_id, e)
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=f"MEMORIZE action failed: {e}",
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

        assert isinstance(params, MemorizeParams)
        node = params.node

        # Handle user node validation (consent + managed attributes)
        if is_user_node(node):
            error = await self._validate_user_node(node, thought, result)
            if error:
                return error

        # Check identity node authorization
        if is_identity_node(node) and not dispatch_context.wa_authorized:
            self.logger.warning(
                f"WA authorization required for MEMORIZE to identity graph. Thought {thought_id} denied."
            )
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content="MEMORIZE action failed: WA authorization required for identity changes",
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

        # Handle CONFIG node transformation
        if is_config_node(node):
            node_or_error = self._handle_config_node(node, thought, result)
            if isinstance(node_or_error, str):
                return node_or_error
            node = node_or_error

        # Execute memorize operation
        return await self._execute_memorize(node, thought, result)

    async def _validate_user_node(
        self, node: GraphNode, thought: Thought, result: ActionSelectionDMAResult
    ) -> Optional[str]:
        """Validate user node: check consent and managed attributes.

        Returns error follow-up ID if validation fails, None if valid.
        """
        user_id = extract_user_id_from_node(node)

        # Check consent for user
        if user_id:
            consent_service = ConsentService(time_service=self.time_service)
            error_msg, _ = await handle_user_consent(user_id, node, consent_service, self.time_service)
            if error_msg:
                logger.warning(f"Blocked memorize for consent issue: user {user_id}")
                return self.complete_thought_and_create_followup(
                    thought=thought,
                    follow_up_content=error_msg,
                    action_result=result,
                    status=ThoughtStatus.FAILED,
                )

        # Check managed attributes
        managed_error = check_managed_attributes(node)
        if managed_error:
            logger.warning(f"Blocked memorize attempt on managed attribute for node '{node.id}'")
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=managed_error,
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

        return None

    def _handle_config_node(
        self, node: GraphNode, thought: Thought, result: ActionSelectionDMAResult
    ) -> GraphNode | str:
        """Handle CONFIG node transformation.

        Returns transformed GraphNode or error follow-up ID.
        """
        config_key, config_value, error_msg = validate_config_node(node)

        if error_msg:
            logger.warning(f"CONFIG node missing value: key={config_key}")
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=error_msg,
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

        try:
            transformed_node = create_config_node(node, config_key, config_value)
            logger.info(f"Created proper ConfigNode for key={config_key}, value={config_value}")
            return transformed_node
        except Exception as e:
            error_msg = (
                f"MEMORIZE CONFIG FAILED: Error creating ConfigNode for '{config_key}'\n\n"
                f"Error: {e}\n\n"
                "This typically happens when:\n"
                "1. The value type is not supported (must be: bool, int, float, string, list, or dict)\n"
                "2. The value format is invalid\n"
                "3. The key contains invalid characters\n\n"
                f"Attempted to set: key='{config_key}', value='{config_value}' (type: {type(config_value).__name__})\n\n"
                "Please ensure your value is properly formatted and try again."
            )
            logger.error(f"Failed to create ConfigNode: {e}")
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=error_msg,
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

    async def _execute_memorize(
        self, node: GraphNode, thought: Thought, result: ActionSelectionDMAResult
    ) -> Optional[str]:
        """Execute the memorize operation through the bus."""
        thought_id = thought.thought_id

        try:
            memory_result = await self.bus_manager.memory.memorize(node=node, handler_name=self.__class__.__name__)
            success = memory_result.status == MemoryOpStatus.SUCCESS

            # Build follow-up content
            if success:
                content_preview = self._extract_content_preview(node)
                follow_up_content = (
                    f"MEMORIZE COMPLETE - stored {node.type.value} '{node.id}'{content_preview}. "
                    "Information successfully saved to memory graph."
                )
            else:
                follow_up_content = (
                    f"Failed to memorize node '{node.id}': "
                    f"{memory_result.reason or memory_result.error or 'Unknown error'}"
                )

            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=follow_up_content,
                action_result=result,
                status=ThoughtStatus.COMPLETED if success else ThoughtStatus.FAILED,
            )

        except Exception as e:
            await self._handle_error(HandlerActionType.MEMORIZE, None, thought_id, e)

            persistence.update_thought_status(
                thought_id=thought_id,
                status=ThoughtStatus.FAILED,
                occurrence_id=thought.agent_occurrence_id,
                final_action=result,
            )

            follow_up = create_follow_up_thought(
                parent=thought, time_service=self.time_service, content=f"MEMORIZE action failed with error: {e}"
            )
            persistence.add_thought(follow_up)

            raise FollowUpCreationError from e

    def _extract_content_preview(self, node: GraphNode) -> str:
        """Extract a content preview from node attributes for success message."""
        if not hasattr(node, "attributes") or not node.attributes:
            return ""

        # Try known attribute names for preview
        preview_attrs = ["content", "name", "value"]

        if isinstance(node.attributes, dict):
            for attr in preview_attrs:
                if attr in node.attributes:
                    val = node.attributes[attr]
                    if val is not None:
                        val_str = str(val)
                        return f": {val_str[:100]}" if attr == "content" else f": {val_str}"
        else:
            for attr in preview_attrs:
                if hasattr(node.attributes, attr):
                    val = getattr(node.attributes, attr)
                    if val is not None:
                        val_str = str(val)
                        return f": {val_str[:100]}" if attr == "content" else f": {val_str}"

        return ""
