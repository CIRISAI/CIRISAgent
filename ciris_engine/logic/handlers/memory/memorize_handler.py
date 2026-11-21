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
    approved_amendment_text,
    as_identity_amendment,
    check_managed_attributes,
    create_config_node,
    extract_user_id_from_node,
    handle_user_consent,
    has_model_supplied_amendment_provenance,
    is_config_node,
    is_identity_amendment_candidate,
    is_identity_node,
    is_reviewed_amendment_write,
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
    sha256_hex,
)
from ciris_engine.schemas.actions import DreamConsolidationParams, MemorizeParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought, WAAuthorization
from ciris_engine.schemas.services.authority.deferral_rows import (
    REASON_MODEL_PROVENANCE,
    REASON_NO_APPROVED_TEXT,
    REASON_NO_REQUEST_ROW,
    REASON_NO_RESPONSE_ROW,
    REASON_RESPONSE_ALREADY_USED,
    REASON_ROWS_UNAVAILABLE,
    REASON_AMENDMENT_DIGEST_MISMATCH,
    DeferralRowRefusalKind,
)
from ciris_engine.schemas.services.graph_core import GraphNode
from ciris_engine.schemas.services.operations import MemoryOpStatus

logger = logging.getLogger(__name__)

#: The notice an identity-scope MEMORIZE gets when its approval named no exact text (#1366 F1).
#: Beside a reason id (an enum value), so it is not localized either.
NO_APPROVED_TEXT_NOTICE = "the Wise Authority approved no exact amendment text; re-approval with amendment_text is required"

#: An identity-scope write that is not the engine-bound, conscience-reviewed approved text (#1366).
REASON_NOT_REVIEWED = "identity_amendment.not_conscience_reviewed"


def _dispatch_channel_id(dispatch_context: DispatchContext) -> Optional[str]:
    """The channel this act happens in, or ``None`` when the dispatch names none."""
    channel = getattr(dispatch_context, "channel_context", None)
    channel_id = getattr(channel, "channel_id", None)
    return channel_id if isinstance(channel_id, str) and channel_id else None


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
        # approval, and the ENGINE writes that record (#1366 F2): a draft that
        # is already an identity_amendment node, or names amendment provenance
        # itself, is refused, with or without an approval in this task.
        authorization = dispatch_context.wa_authorization
        if has_model_supplied_amendment_provenance(node):
            self.logger.warning(
                f"MEMORIZE draft supplies identity-amendment provenance itself (type={node.type.value}, "
                f"id={node.id!r}). Thought {thought_id} denied: only the engine writes that record."
            )
            if authorization is None:
                return self._refuse_amendment(thought, result, REASON_MODEL_PROVENANCE, name_reason=False)
            return self._refuse_amendment(thought, result, REASON_MODEL_PROVENANCE, name_reason=True)
        if authorization is not None and is_identity_amendment_candidate(node):
            approved = approved_amendment_text(authorization)
            if approved is not None and not is_reviewed_amendment_write(node, approved):
                # The write the consciences review is the one the engine binds before they run (#1366):
                # the approved bytes with their M-1 justification. Anything else did not pass that review.
                self.logger.warning(
                    f"Identity amendment for deferral {authorization.deferral_id} refused: the write is not the "
                    f"conscience-reviewed approved text with its M-1 justification. Thought {thought_id}."
                )
                return self._refuse_amendment(thought, result, REASON_NOT_REVIEWED, name_reason=True)
            amended = self._approved_amendment(node, authorization, thought)
            if amended is None:
                return self._refuse_amendment(
                    thought, result, f"{REASON_NO_APPROVED_TEXT} ({NO_APPROVED_TEXT_NOTICE})", name_reason=True
                )
            signed = await self._sign_identity_amendment(amended, authorization, thought, result)
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

    def _approved_amendment(
        self, node: GraphNode, authorization: WAAuthorization, thought: Thought
    ) -> Optional[GraphNode]:
        """The amendment this identity-scope write lands as: the WA's approved bytes, or None (#1366 F1).

        None when the approval names no exact text (or text that does not hash
        to its signed digest). Eric, 2026-11-18: no legacy grace, a
        guidance-only approval lands no amendment; the WA re-approves with the
        exact text.

        The draft reaching here is the one the engine bound before conscience
        execution (``bind_approved_amendment``): the approved bytes with their
        M-1 justification, which the consciences reviewed (#1366). A memorize
        second pass rewording them (RATCHET Market 4: 8 of 80 rewritten) is
        overwritten by that binding before review, so it can neither block nor
        alter what was approved; the caller refuses any draft that skipped it.
        """
        approved = approved_amendment_text(authorization)
        if approved is None:
            self.logger.warning(
                f"Identity-scope MEMORIZE in the guidance task of deferral {authorization.deferral_id} lands NO "
                f"amendment: the approval names no exact amendment text. Re-approval with amendment_text is "
                f"required. Thought {thought.thought_id}."
            )
            return None
        drafted = amendment_text(node.attributes)
        if drafted != approved:
            self.logger.warning(
                f"Identity amendment for deferral {authorization.deferral_id}: the draft's text "
                f"(sha256 {sha256_hex(drafted)[:16]}, {len(drafted)} chars) differs from the approved text "
                f"(sha256 {sha256_hex(approved)[:16]}); writing the approved text. Thought {thought.thought_id}."
            )
        amended = as_identity_amendment(node, authorization, approved)
        self.logger.info(
            f"WA-approved identity amendment {amended.id} (wa={authorization.wa_id}, deferral={authorization.deferral_id})"
        )
        return amended

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
        - the approval carries no signed response row, or not the request row
          it answers: refused, because where the node authors rows an approval
          is the WA's own signed answer to this agent's own deferral;
        - the node refuses (``identity_amendment_unauthorized``, bad input) or
          does not answer: refused. An outage is not a verdict, but an
          amendment without its row is the unattested change this closes;
        - the approval already authorized an amendment
          (``deferral.response_already_used``): refused. One approval, one
          amendment; the agent is told the approval is spent, not that it
          lacks one, so it does not ask the Wise Authority again for a change
          that has already been applied.
        """
        thought_id = thought.thought_id
        if not rows_available():
            # No legacy grace (#1366 F1): an amendment without its signed row
            # could never verify, so it is not written.
            self.logger.warning(
                f"Identity amendment {node.id} refused: this node has no deferral rows to sign it. Thought {thought_id}."
            )
            return self._refuse_amendment(thought, result, REASON_ROWS_UNAVAILABLE, name_reason=True)
        response_id = authorization.response_attestation_id
        request_id = authorization.request_attestation_id
        if not response_id or not request_id:
            missing = REASON_NO_RESPONSE_ROW if not response_id else REASON_NO_REQUEST_ROW
            self.logger.warning(
                f"Identity amendment {node.id} refused: the approval of deferral {authorization.deferral_id} "
                f"carries no signed row to cite ({missing}). Thought {thought_id}."
            )
            return self._refuse_amendment(thought, result, missing, name_reason=False)
        approved = approved_amendment_text(authorization)
        if approved is None:  # _approved_amendment already refused this; never sign other bytes
            return self._refuse_amendment(thought, result, REASON_NO_APPROVED_TEXT, name_reason=True)
        # The link this amendment follows (rc21 section 3): the verified profile chain's head.
        from ciris_engine.logic.context.identity_profile import chain_head_row_id, note_chain_link

        await self._refresh_unverified_profile()
        prev, no_head = chain_head_row_id()
        if prev is None:
            self.logger.warning(
                f"Identity amendment {node.id} NOT recorded: no chain head to follow ({no_head}). Thought {thought_id}."
            )
            return self._refuse_amendment(thought, result, no_head, name_reason=True)
        try:
            amendment_id = await emit_identity_amendment(approved, response_id, request_id, prev)
        except DeferralRowsUnavailable:
            return self._refuse_amendment(thought, result, REASON_ROWS_UNAVAILABLE, name_reason=True)
        except DeferralRowRefused as refused:
            refusal = refused.refusal
            self.logger.warning(
                f"Identity amendment {node.id} refused: the node would not sign it ({refusal.reason_id}, "
                f"{refusal.kind.value}): {refusal.text}. Thought {thought_id}."
            )
            return self._refuse_amendment(
                thought,
                result,
                refusal.reason_id,
                name_reason=refusal.kind is DeferralRowRefusalKind.OUTAGE
                or refusal.reason_id in (REASON_RESPONSE_ALREADY_USED, REASON_AMENDMENT_DIGEST_MISMATCH),
            )
        attributes = serialize_attributes_to_json(node.attributes)
        provenance = attributes.get("wa_amendment")
        provenance = dict(provenance) if isinstance(provenance, dict) else {}
        provenance["amendment_attestation_id"] = amendment_id
        provenance["response_attestation_id"] = authorization.response_attestation_id
        provenance["request_attestation_id"] = authorization.request_attestation_id
        attributes["wa_amendment"] = provenance
        note_chain_link(amendment_id)
        self.logger.info(f"Identity amendment {node.id}: signed row {amendment_id} (prev {prev})")
        return node.model_copy(update={"attributes": attributes})

    async def _refresh_unverified_profile(self) -> None:
        """Re-check the identity profile before reading its chain head, unless the last check was VERIFIED.

        The head comes from the newest profile check, and a check runs on each context build. A base link the
        Wise Authority approved after this thought's context was built would otherwise leave the head reading
        the stale unanchored check, and the approved amendment would be refused for having no head (RATCHET runs
        44776804283, 44780287540: the base link landed 0.3 s after the boot check). A VERIFIED check is kept: the
        appended head (``note_chain_link``) already tracks links written since. Best effort.
        """
        from ciris_engine.logic.context.identity_profile import latest_identity_profile
        from ciris_engine.schemas.infrastructure.identity_variance import IdentityProfileStatus

        cached = latest_identity_profile()
        if cached is not None and cached.status is IdentityProfileStatus.VERIFIED:
            return
        try:
            from ciris_engine.logic.context.system_snapshot_helpers import _extract_agent_identity

            memory: Any = self.bus_manager.memory  # the bus answers recall() as the context builders' service does
            await _extract_agent_identity(memory)
        except Exception as exc:  # noqa: BLE001 - the cached check stands; chain_head_row_id says why
            self.logger.warning(f"identity profile re-check before an amendment failed ({type(exc).__name__})")

    def _refuse_amendment(
        self, thought: Thought, result: ActionSelectionDMAResult, reason_id: str, *, name_reason: bool
    ) -> str:
        """The FAILED follow-up for an identity amendment the node did not sign.

        ``name_reason`` (an outage, or a spent approval) names the node's reason
        id; anything else says WA authorization is required, which is the truth
        of a missing or unauthorized approval.
        """
        if name_reason:
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
        if not is_identity_node(node) and not is_config_node(node):
            # The room it was learned in, stamped by the engine, never the draft (CC 1.13.3.4): recalled only there.
            from ciris_engine.logic.context.room_audience import stamp_room

            node = stamp_room(node, _dispatch_channel_id(dispatch_context))

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
                outcome=f"MEMORIZE action failed with error: {e}"[:400],
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
