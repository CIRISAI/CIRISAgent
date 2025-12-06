"""
Memorize handler - clean implementation using BusManager
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
from ciris_engine.logic.infrastructure.handlers.helpers import create_follow_up_thought
from ciris_engine.logic.services.governance.consent import ConsentNotFoundError, ConsentService
from ciris_engine.schemas.actions import MemorizeParams
from ciris_engine.schemas.consent.core import ConsentRequest, ConsentStream
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
        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

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
            # System-managed timestamps
            "last_seen": "System-managed timestamp updated automatically when user activity is detected. Use OBSERVE action instead.",
            "last_interaction": "System-managed timestamp updated automatically when user interacts. Use OBSERVE action instead.",
            "created_at": "System-managed timestamp set once when user is first encountered. Cannot be modified.",
            "first_seen": "System-managed timestamp set once when user is first encountered. Cannot be modified.",
            # System-managed access control
            "trust_level": "Managed by the Adaptive Filter service based on user behavior patterns. Cannot be directly modified.",
            "is_wa": "Managed by the Authentication service. Wise Authority status requires proper authorization flow.",
            "permissions": "Managed by the Authorization service. Permission changes require administrative access.",
            "restrictions": "Managed by the Authorization service. Restriction changes require administrative access.",
            # User privacy & preference settings (user-only modification via API)
            "marketing_opt_in": "User consent for marketing communications. Only modifiable by user via settings API. Use DEFER to request user permission changes.",
            "marketing_opt_in_source": "Source of marketing consent (e.g., 'oauth_login', 'settings_page'). System-managed tracking field. Cannot be modified directly.",
            "location": "User's location preference. Only modifiable by user via settings API. Use OBSERVE to see current value.",
            "interaction_preferences": "User's custom interaction preferences and prompt. Only modifiable by user via settings API. Use OBSERVE to see current value.",
            "user_preferred_name": "User's preferred display name. Only modifiable by user via settings API. Use OBSERVE to see current value.",
            # OAuth identity fields (authentication system managed)
            "oauth_provider": "OAuth provider identity (e.g., 'google', 'github'). Managed by authentication system during OAuth flow. Use OBSERVE to see details.",
            "oauth_email": "Email address from OAuth provider. Managed by authentication system. Use OBSERVE to see email.",
            "oauth_external_id": "External user ID from OAuth provider. Managed by authentication system during OAuth flow. Cannot be modified.",
            "oauth_name": "Full name from OAuth provider. Managed by authentication system during OAuth flow. Use OBSERVE to see name.",
            "oauth_picture": "Profile picture URL from OAuth provider. Managed by authentication system during OAuth flow. Use OBSERVE to see picture URL.",
            "oauth_links": "Linked OAuth identities for this user. Managed by authentication system. Use OBSERVE to see linked accounts.",
        }

        # Check if this is a user node and validate attributes
        if node.type == NodeType.USER or node.id.startswith("user/"):
            # Extract user_id from node id (format: user/{uid} or user_{uid})
            user_id = None
            if node.id.startswith("user/"):
                user_id = node.id[5:]  # Remove "user/" prefix
            elif node.id.startswith("user_"):
                user_id = node.id[5:]  # Remove "user_" prefix

            if user_id:
                # Check consent status for this user (if service is available)
                try:
                    consent_service = ConsentService(time_service=self.time_service)
                    consent_status = await consent_service.get_consent(user_id)

                    # Check if TEMPORARY consent has expired
                    if consent_status.stream == ConsentStream.TEMPORARY:
                        if consent_status.expires_at and datetime.now(timezone.utc) > consent_status.expires_at:
                            # Consent expired - start decay protocol
                            await consent_service.revoke_consent(user_id, "TEMPORARY consent expired (14 days)")

                            error_msg = (
                                f"MEMORIZE BLOCKED: User consent expired. "
                                f"User {user_id}'s TEMPORARY consent expired on {consent_status.expires_at}. "
                                f"Decay protocol initiated. User data will be anonymized over 90 days."
                            )
                            logger.warning(f"Blocked memorize for expired consent: user {user_id}")

                            return self.complete_thought_and_create_followup(
                                thought=thought,
                                follow_up_content=error_msg,
                                action_result=result,
                                status=ThoughtStatus.FAILED,
                            )

                    # Add consent metadata to node attributes
                    if hasattr(node, "attributes"):
                        if isinstance(node.attributes, dict):
                            node.attributes["consent_stream"] = consent_status.stream
                            node.attributes["consent_expires_at"] = (
                                consent_status.expires_at.isoformat() if consent_status.expires_at else None
                            )
                            node.attributes["consent_granted_at"] = consent_status.granted_at.isoformat()

                except ConsentNotFoundError:
                    # No consent exists - try to create default TEMPORARY consent
                    try:
                        now = datetime.now(timezone.utc)
                        consent_request = ConsentRequest(
                            user_id=user_id,
                            stream=ConsentStream.TEMPORARY,
                            categories=[],  # No categories for default TEMPORARY
                            reason="Default TEMPORARY consent on first interaction",
                        )
                        consent_status = await consent_service.grant_consent(consent_request, channel_id=None)

                        # Add consent metadata to node
                        if hasattr(node, "attributes"):
                            if isinstance(node.attributes, dict):
                                node.attributes["consent_stream"] = ConsentStream.TEMPORARY
                                node.attributes["consent_expires_at"] = (now + timedelta(days=14)).isoformat()
                                node.attributes["consent_granted_at"] = now.isoformat()
                                node.attributes["consent_notice"] = (
                                    "We forget about you in 14 days unless you say otherwise"
                                )

                        logger.info(f"Created default TEMPORARY consent for new user {user_id}")
                    except (RuntimeError, Exception) as grant_error:
                        # Can't grant consent either - service unavailable
                        logger.debug(f"Cannot grant consent: {grant_error}. Continuing without consent.")
                except (RuntimeError, Exception) as e:
                    # Consent service not available (e.g., in tests or minimal configurations)
                    # Log but continue - consent is not mandatory for memorization
                    logger.debug(f"Consent service not available: {e}. Continuing without consent check.")

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

                        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

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

            # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

            # Use centralized method with FAILED status
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content="MEMORIZE action failed: WA authorization required for identity changes",
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

        # Special handling for CONFIG nodes
        if node.type == NodeType.CONFIG and scope == GraphScope.LOCAL:
            # CONFIG nodes need special structure for the config service
            # Extract key and value from node attributes or id

            # Try to parse key from node id (e.g., "filter/caps_threshold" -> "filter.caps_threshold")
            config_key = node.id.replace("/", ".")

            # Check if attributes contain the required data
            node_attrs = node.attributes if hasattr(node, "attributes") else {}
            if isinstance(node_attrs, dict):
                config_value = node_attrs.get("value")
            else:
                # For non-dict attributes, try to extract value
                config_value = getattr(node_attrs, "value", None) if node_attrs else None

            # Validate we have the minimum required data
            if config_value is None:
                # Provide detailed error message with examples
                error_msg = (
                    f"MEMORIZE CONFIG FAILED: Missing required 'value' field for configuration '{config_key}'\n\n"
                    "CONFIG nodes require both a key and a value. The key was extracted from the node ID, "
                    "but no value was provided in the attributes.\n\n"
                    "To set a configuration value, include it in the node attributes. Examples:\n\n"
                    "For numeric values:\n"
                    "  $memorize filter/spam_threshold CONFIG LOCAL value=0.8\n"
                    "  $memorize filter/trust_decay CONFIG LOCAL value=0.05\n\n"
                    "For boolean values:\n"
                    "  $memorize filter/enabled CONFIG LOCAL value=true\n"
                    "  $memorize filter/debug_mode CONFIG LOCAL value=false\n\n"
                    "For string values:\n"
                    "  $memorize filter/mode CONFIG LOCAL value=strict\n"
                    "  $memorize agent/name CONFIG LOCAL value='CIRIS Agent'\n\n"
                    "For list values:\n"
                    "  $memorize filter/keywords CONFIG LOCAL value=['spam','scam','phishing']\n\n"
                    "Note: The mock LLM currently only supports simple node creation. "
                    "For actual configuration updates, you may need to use the config service directly."
                )

                logger.warning(f"CONFIG node missing value: key={config_key}")

                return self.complete_thought_and_create_followup(
                    thought=thought,
                    follow_up_content=error_msg,
                    action_result=result,
                    status=ThoughtStatus.FAILED,
                )

            # Try to create a proper ConfigNode
            try:
                from ciris_engine.schemas.services.nodes import ConfigNode, ConfigValue

                # Determine value type and create ConfigValue
                config_val = ConfigValue()
                if isinstance(config_value, bool):
                    config_val.bool_value = config_value
                elif isinstance(config_value, int):
                    config_val.int_value = config_value
                elif isinstance(config_value, float):
                    config_val.float_value = config_value
                elif isinstance(config_value, list):
                    config_val.list_value = config_value
                elif isinstance(config_value, dict):
                    config_val.dict_value = config_value
                else:
                    # Default to string
                    config_val.string_value = str(config_value)

                # Create ConfigNode with proper structure
                config_node = ConfigNode(
                    id=node.id,  # Use the original node id
                    type=NodeType.CONFIG,
                    scope=scope,  # Use the original scope (LOCAL)
                    attributes={},  # Will be populated by to_graph_node()
                    key=config_key,
                    value=config_val,
                    version=1,  # Start at version 1
                    updated_by="agent",  # Default to agent
                )

                # Convert to GraphNode for storage
                node = config_node.to_graph_node()

                logger.info(f"Created proper ConfigNode for key={config_key}, value={config_value}")

            except Exception as e:
                # Provide detailed error about what went wrong
                error_msg = (
                    f"MEMORIZE CONFIG FAILED: Error creating ConfigNode for '{config_key}'\n\n"
                    f"Error: {str(e)}\n\n"
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
                            content_val = node.attributes["content"]
                            content_str = str(content_val) if content_val is not None else ""
                            content_preview = f": {content_str[:100]}" if content_str else ""
                        elif "name" in node.attributes:
                            content_preview = f": {node.attributes['name']}"
                        elif "value" in node.attributes:
                            content_preview = f": {node.attributes['value']}"
                    else:
                        # For GraphNodeAttributes, check if it has these as actual attributes
                        if hasattr(node.attributes, "content"):
                            content_val = node.attributes.content
                            content_str = str(content_val) if content_val is not None else ""
                            content_preview = f": {content_str[:100]}" if content_str else ""
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
            # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

            return follow_up_id

        except Exception as e:
            await self._handle_error(HandlerActionType.MEMORIZE, dispatch_context, thought_id, e)

            persistence.update_thought_status(
                thought_id=thought_id,
                status=ThoughtStatus.FAILED,
                occurrence_id=thought.agent_occurrence_id,
                final_action=result,
            )

            # Create error follow-up
            follow_up = create_follow_up_thought(
                parent=thought, time_service=self.time_service, content=f"MEMORIZE action failed with error: {e}"
            )
            persistence.add_thought(follow_up)

            raise FollowUpCreationError from e
