"""
Memorize handler - clean implementation using BusManager
"""

import logging
from typing import Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
from ciris_engine.logic.infrastructure.handlers.helpers import create_follow_up_thought
from ciris_engine.schemas.actions import MemorizeParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus

logger = logging.getLogger(__name__)


class MemorizeHandler(BaseActionHandler):
    """Handler for MEMORIZE actions."""

    async def handle(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> Optional[str]:
        """Handle a memorize action."""
        thought_id = thought.thought_id

        # Start audit logging
        await self._audit_log(HandlerActionType.MEMORIZE, dispatch_context, outcome="start")

        # Validate parameters
        try:
            params: MemorizeParams = self._validate_and_convert_params(result.action_parameters, MemorizeParams)
        except Exception as e:
            await self._handle_error(HandlerActionType.MEMORIZE, dispatch_context, thought_id, e)
            # Use centralized method to mark failed and create follow-up
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=f"MEMORIZE action failed: {e}",
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

        # Extract node from params - params is MemorizeParams
        assert isinstance(params, MemorizeParams)
        node = params.node
        scope = node.scope

        # Define managed user attributes that should not be modified by memorize operations
        MANAGED_USER_ATTRIBUTES = {
            "last_seen": "System-managed timestamp updated automatically when user activity is detected. Use OBSERVE action instead.",
            "last_interaction": "System-managed timestamp updated automatically when user interacts. Use OBSERVE action instead.",
            "created_at": "System-managed timestamp set once when user is first encountered. Cannot be modified.",
            "first_seen": "System-managed timestamp set once when user is first encountered. Cannot be modified.",
            "trust_level": "Managed by the Adaptive Filter service based on user behavior patterns. Cannot be directly modified.",
            "is_wa": "Managed by the Authentication service. Wise Authority status requires proper authorization flow.",
            "permissions": "Managed by the Authorization service. Permission changes require administrative access.",
            "restrictions": "Managed by the Authorization service. Restriction changes require administrative access.",
        }

        # Check if this is a user node and validate attributes
        if node.type == NodeType.USER or node.id.startswith("user/"):
            if hasattr(node, "attributes") and node.attributes:
                # Handle both dict and GraphNodeAttributes types
                if isinstance(node.attributes, dict):
                    attrs_to_check = node.attributes
                elif hasattr(node.attributes, "__dict__"):
                    attrs_to_check = node.attributes.__dict__
                else:
                    attrs_to_check = {}

                # Check for any managed attributes
                for attr_name, rationale in MANAGED_USER_ATTRIBUTES.items():
                    if attr_name in attrs_to_check:
                        error_msg = (
                            f"MEMORIZE BLOCKED: Attempt to modify managed user attribute '{attr_name}'. "
                            f"\n\nRationale: {rationale}"
                            f"\n\nAttempted operation: Set '{attr_name}' to '{attrs_to_check[attr_name]}' for user node '{node.id}'."
                            f"\n\nGuidance: If this information needs correction, please use DEFER action to request "
                            f"Wise Authority assistance. They can help determine the proper way to update this information "
                            f"through the appropriate system channels."
                        )

                        logger.warning(
                            f"Blocked memorize attempt on managed attribute '{attr_name}' for node '{node.id}'"
                        )

                        await self._audit_log(
                            HandlerActionType.MEMORIZE,
                            dispatch_context,
                            outcome="blocked_managed_attribute",
                            additional_info={"attribute": attr_name, "node_id": node.id},
                        )

                        return self.complete_thought_and_create_followup(
                            thought=thought,
                            follow_up_content=error_msg,
                            action_result=result,
                            status=ThoughtStatus.FAILED,
                        )

        # Check if this is an identity node that requires WA authorization
        is_identity_node = (
            scope == GraphScope.IDENTITY or node.id.startswith("agent/identity") or node.type == NodeType.AGENT
        )

        if is_identity_node and not dispatch_context.wa_authorized:
            self.logger.warning(
                "WA authorization required for MEMORIZE to identity graph. " f"Thought {thought_id} denied."
            )

            await self._audit_log(HandlerActionType.MEMORIZE, dispatch_context, outcome="failed_wa_required")

            # Use centralized method with FAILED status
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content="MEMORIZE action failed: WA authorization required for identity changes",
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

        # Perform the memory operation through the bus
        try:
            memory_result = await self.bus_manager.memory.memorize(node=node, handler_name=self.__class__.__name__)

            success = memory_result.status == MemoryOpStatus.SUCCESS
            final_status = ThoughtStatus.COMPLETED if success else ThoughtStatus.FAILED

            # Create appropriate follow-up
            if success:
                # Extract meaningful content from the node
                content_preview = ""
                if hasattr(node, "attributes") and node.attributes:
                    # Handle both dict and GraphNodeAttributes types
                    if isinstance(node.attributes, dict):
                        if "content" in node.attributes:
                            content_preview = f": {node.attributes['content'][:100]}"
                        elif "name" in node.attributes:
                            content_preview = f": {node.attributes['name']}"
                        elif "value" in node.attributes:
                            content_preview = f": {node.attributes['value']}"
                    else:
                        # For GraphNodeAttributes, check if it has these as actual attributes
                        if hasattr(node.attributes, "content"):
                            content_preview = f": {node.attributes.content[:100]}"
                        elif hasattr(node.attributes, "name"):
                            content_preview = f": {node.attributes.name}"
                        elif hasattr(node.attributes, "value"):
                            content_preview = f": {node.attributes.value}"

                follow_up_content = (
                    f"MEMORIZE COMPLETE - stored {node.type.value} '{node.id}'{content_preview}. "
                    "Information successfully saved to memory graph."
                )
            else:
                follow_up_content = (
                    f"Failed to memorize node '{node.id}': "
                    f"{memory_result.reason or memory_result.error or 'Unknown error'}"
                )

            # Use centralized method to complete thought and create follow-up
            follow_up_id = self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=follow_up_content,
                action_result=result,
                status=ThoughtStatus.COMPLETED if success else ThoughtStatus.FAILED,
            )

            # Final audit log
            await self._audit_log(
                HandlerActionType.MEMORIZE, dispatch_context, outcome="success" if success else "failed"
            )

            return follow_up_id

        except Exception as e:
            await self._handle_error(HandlerActionType.MEMORIZE, dispatch_context, thought_id, e)

            persistence.update_thought_status(
                thought_id=thought_id,
                status=ThoughtStatus.FAILED,
                final_action=result,
            )

            # Create error follow-up
            follow_up = create_follow_up_thought(
                parent=thought, time_service=self.time_service, content=f"MEMORIZE action failed with error: {e}"
            )
            persistence.add_thought(follow_up)

            raise FollowUpCreationError from e
