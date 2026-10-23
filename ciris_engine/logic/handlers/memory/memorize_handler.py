"""
Memorize handler - clean implementation using BusManager
"""

import logging
from typing import Any, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
from ciris_engine.logic.infrastructure.handlers.helpers import create_follow_up_thought
from ciris_engine.logic.infrastructure.handlers.shared_helpers import (
    amendment_text,
    as_identity_amendment,
    check_managed_attributes,
    create_config_node,
    extract_user_id_from_node,
    handle_user_consent,
    is_config_node,
    is_identity_amendment_candidate,
    is_identity_node,
    is_user_node,
    serialize_attributes_to_json,
    validate_config_node,
)
from ciris_engine.logic.services.governance.consent import ConsentService
from ciris_engine.logic.services.governance.wise_authority.deferral_rows import (
    DeferralRowRefused,
    DeferralRowsUnavailable,
    emit_identity_amendment,
    rows_available,
)
from ciris_engine.schemas.actions import DreamConsolidationParams, MemorizeParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought, WAAuthorization
from ciris_engine.schemas.services.authority.deferral_rows import REASON_NO_RESPONSE_ROW, DeferralRowRefusalKind
from ciris_engine.schemas.services.graph_core import GraphNode, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus

logger = logging.getLogger(__name__)


class MemorizeHandler(BaseActionHandler):
    """Handler for MEMORIZE actions."""

    async def handle(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> Optional[str]:
        """Handle a memorize action.

        Dispatches on PARAMETER TYPE: ``DreamConsolidationParams`` routes to
        :class:`DreamMemorizeHandler`, everything else is handled here.
        """
        thought_id = thought.thought_id

        # #998 — route dream consolidation to the handler written for it.
        #
        # DreamMemorizeHandler creates the three edges that ARE the dream's
        # work — CONNECTS (links two memories by pattern), IMPLIES (extracts a
        # behavioural insight), ASPIRES_TO (links identity to an aspiration).
        # It was defined, complete, and registered NOWHERE: it appeared exactly
        # once repo-wide, its own class statement. handler_registry.py maps
        # MEMORIZE to this class alone, so every dream consolidation has been
        # handled as an ordinary memorize since the handler was written.
        #
        # The dream processor meanwhile announced "Wove N connections" and
        # published an `edges_created` metric off a hardcoded `+= 3`. The claim
        # was made; the edges were never created. Registering by parameter type
        # rather than adding a second MEMORIZE registry slot keeps one action ->
        # one entry point, which is what the dispatcher assumes.
        if isinstance(result.action_parameters, DreamConsolidationParams):
            self.logger.info("MEMORIZE carries DreamConsolidationParams — routing to DreamMemorizeHandler")
            from ciris_engine.logic.handlers.memory.dream_memorize_handler import DreamMemorizeHandler

            return await DreamMemorizeHandler(self.dependencies).handle(result, thought, dispatch_context)

        # Validate parameters
        try:
            params: MemorizeParams = self._validate_and_convert_params(result.action_parameters, MemorizeParams)
        except Exception as e:
            await self._handle_error(HandlerActionType.MEMORIZE, dispatch_context, thought_id, e)
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=self._localized_followup(
                    "memorize_action_failed_with_reason",
                    default=f"MEMORIZE action failed: {e}",
                    reason=str(e),
                ),
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
                follow_up_content=self._localized_followup(
                    "memorize_wa_required",
                    default="MEMORIZE action failed: WA authorization required for identity changes",
                ),
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

        # An identity amendment exists only as the record of a verified WA
        # approval: nothing else may mint one, or the identity loader would
        # present unapproved text as approved.
        authorization = dispatch_context.wa_authorization
        if node.type == NodeType.IDENTITY_AMENDMENT and authorization is None:
            self.logger.warning(f"MEMORIZE of an identity amendment without a verified WA approval. Thought {thought_id} denied.")
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=self._localized_followup(
                    "memorize_wa_required",
                    default="MEMORIZE action failed: WA authorization required for identity changes",
                ),
                action_result=result,
                status=ThoughtStatus.FAILED,
            )
        if authorization is not None and is_identity_amendment_candidate(node):
            node = as_identity_amendment(node, authorization)
            self.logger.info(
                f"WA-approved identity amendment {node.id} (wa={authorization.wa_id}, deferral={authorization.deferral_id})"
            )
        if authorization is not None and node.type == NodeType.IDENTITY_AMENDMENT:
            signed = await self._sign_identity_amendment(node, authorization, thought, result)
            if isinstance(signed, str):
                return signed
            node = signed

        # Handle CONFIG node transformation
        if is_config_node(node):
            node_or_error = self._handle_config_node(node, thought, result)
            if isinstance(node_or_error, str):
                return node_or_error
            node = node_or_error

        # Execute memorize operation
        return await self._execute_memorize(node, thought, result, dispatch_context)

    async def _sign_identity_amendment(
        self,
        node: GraphNode,
        authorization: WAAuthorization,
        thought: Thought,
        result: ActionSelectionDMAResult,
    ) -> GraphNode | str:
        """Have the node sign ``identity_amendment:v1`` BEFORE the amendment is written (CIRISAgent#1316).

        Returns the node to write, carrying the row's id, or the follow-up id of
        a refusal. Refused BEFORE the write, so an amendment the node will not
        sign never stands locally and there is nothing to roll back:

        - the node has no deferral rows (server < 0.5.234): written as before;
        - the approval carries no signed response row: refused, because where
          the node authors rows an approval is the WA's own signed answer;
        - the node refuses (``identity_amendment_unauthorized``, bad input) or
          does not answer: refused. An outage is not a verdict, but an
          amendment without its row is the unattested change this closes.
        """
        thought_id = thought.thought_id
        if not rows_available():
            return node
        if not authorization.response_attestation_id:
            self.logger.warning(
                f"Identity amendment {node.id} refused: the approval of deferral {authorization.deferral_id} "
                f"carries no signed Wise Authority response row ({REASON_NO_RESPONSE_ROW}). Thought {thought_id}."
            )
            return self._refuse_amendment(thought, result, REASON_NO_RESPONSE_ROW, outage=False)
        try:
            amendment_id = await emit_identity_amendment(amendment_text(node.attributes), authorization.response_attestation_id)
        except DeferralRowsUnavailable:
            return node
        except DeferralRowRefused as refused:
            refusal = refused.refusal
            self.logger.warning(
                f"Identity amendment {node.id} refused: the node would not sign it ({refusal.reason_id}, "
                f"{refusal.kind.value}): {refusal.text}. Thought {thought_id}."
            )
            return self._refuse_amendment(
                thought, result, refusal.reason_id, outage=refusal.kind is DeferralRowRefusalKind.OUTAGE
            )
        attributes = serialize_attributes_to_json(node.attributes)
        provenance = attributes.get("wa_amendment")
        provenance = dict(provenance) if isinstance(provenance, dict) else {}
        provenance["amendment_attestation_id"] = amendment_id
        provenance["response_attestation_id"] = authorization.response_attestation_id
        attributes["wa_amendment"] = provenance
        self.logger.info(f"Identity amendment {node.id}: signed row {amendment_id}")
        return node.model_copy(update={"attributes": attributes})

    def _refuse_amendment(
        self, thought: Thought, result: ActionSelectionDMAResult, reason_id: str, *, outage: bool
    ) -> str:
        """The FAILED follow-up for an identity amendment the node did not sign."""
        if outage:
            content = self._localized_followup(
                "memorize_action_failed_with_reason",
                default=f"MEMORIZE action failed: {reason_id}",
                reason=reason_id,
            )
        else:
            content = self._localized_followup(
                "memorize_wa_required",
                default="MEMORIZE action failed: WA authorization required for identity changes",
            )
        return (
            self.complete_thought_and_create_followup(
                thought=thought, follow_up_content=content, action_result=result, status=ThoughtStatus.FAILED
            )
            or ""
        )

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

        # Check managed attributes against what is STORED, so a managed field
        # carried through unchanged by a recall-modify-write-back does not read
        # as an attempt to modify it. Best-effort: if the lookup fails we fall
        # back to the presence check, which is the conservative direction.
        existing = await self._fetch_existing_node(node)
        managed_error = check_managed_attributes(node, existing)
        if managed_error:
            # Name the attribute. The old line said only "a managed attribute",
            # so diagnosing a block meant reading the follow-up sent to the agent.
            first_line = managed_error.split("\n", 1)[0]
            logger.warning(f"Blocked memorize on node '{node.id}': {first_line}")
            return self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=managed_error,
                action_result=result,
                status=ThoughtStatus.FAILED,
            )

        return None

    async def _fetch_existing_node(self, node: GraphNode) -> Optional[GraphNode]:
        """The currently-stored version of `node`, or None.

        Used to tell "carried this managed attribute through unchanged" apart
        from "tried to change it". Best-effort by design: a recall failure must
        not block a memorize, so on any error we return None and the caller
        falls back to the stricter presence check.
        """
        try:
            from ciris_engine.schemas.services.operations import MemoryQuery

            found = await self.bus_manager.memory.recall(
                recall_query=MemoryQuery(node_id=node.id, scope=node.scope, type=node.type),
                handler_name=self.__class__.__name__,
            )
            return found[0] if found else None
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Could not fetch existing node '{node.id}' for managed-attribute diff: {e}")
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
            follow_up_id = self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=error_msg,
                action_result=result,
                status=ThoughtStatus.FAILED,
            )
            return follow_up_id or ""  # Return empty string if None (should not happen)

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
            follow_up_id = self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=error_msg,
                action_result=result,
                status=ThoughtStatus.FAILED,
            )
            return follow_up_id or ""  # Return empty string if None (should not happen)

    async def _execute_memorize(
        self, node: GraphNode, thought: Thought, result: ActionSelectionDMAResult, dispatch_context: DispatchContext
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
            await self._handle_error(HandlerActionType.MEMORIZE, dispatch_context, thought_id, e)

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

        for attr in ("content", "name", "value"):
            val = self._get_node_attr_value(node.attributes, attr)
            if val is not None:
                return self._format_preview_value(attr, str(val))

        return ""

    def _get_node_attr_value(self, attributes: Any, attr_name: str) -> Any:
        """Get attribute value from dict or object attributes."""
        if isinstance(attributes, dict):
            return attributes.get(attr_name)
        return getattr(attributes, attr_name, None)

    def _format_preview_value(self, attr_name: str, val_str: str) -> str:
        """Format preview value, truncating content attributes."""
        if attr_name == "content":
            return f": {val_str[:100]}"
        return f": {val_str}"
