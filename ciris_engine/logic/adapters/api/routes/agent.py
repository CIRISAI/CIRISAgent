"""
Agent interaction endpoints for CIRIS API v3.0 (Simplified).

Core endpoints for natural agent interaction.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ciris_engine.logic.adapters.base_observer import BillingServiceError, CreditCheckFailed, CreditDenied
from ciris_engine.schemas.api.agent import AgentLineage, MessageContext, ServiceAvailability
from ciris_engine.schemas.api.auth import ROLE_PERMISSIONS, AuthContext, Permission, UserRole
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.messages import IncomingMessage
from ciris_engine.schemas.services.credit_gate import CreditAccount, CreditContext
from ciris_engine.schemas.types import JSONDict

from ..constants import DESC_CURRENT_COGNITIVE_STATE, ERROR_MEMORY_SERVICE_NOT_AVAILABLE
from ..dependencies.auth import require_observer

logger = logging.getLogger(__name__)

# Minimum uptime in seconds before defaulting task count
MIN_UPTIME_FOR_DEFAULT_TASKS = 60

router = APIRouter(prefix="/agent", tags=["agent"])

# Request/Response schemas


class MessageRejectionReason(str, Enum):
    """Reasons why a message submission was rejected or not processed."""

    AGENT_OWN_MESSAGE = "AGENT_OWN_MESSAGE"  # Message from agent itself
    FILTERED_OUT = "FILTERED_OUT"  # Filtered by adaptive filter
    CREDIT_DENIED = "CREDIT_DENIED"  # Insufficient credits
    CREDIT_CHECK_FAILED = "CREDIT_CHECK_FAILED"  # Credit provider error
    PROCESSOR_PAUSED = "PROCESSOR_PAUSED"  # Agent processor paused
    RATE_LIMITED = "RATE_LIMITED"  # Rate limit exceeded
    CHANNEL_RESTRICTED = "CHANNEL_RESTRICTED"  # Channel access denied


class ImagePayload(BaseModel):
    """Image payload for multimodal requests."""

    data: str = Field(..., description="Base64-encoded image data or URL")
    media_type: str = Field(default="image/jpeg", description="MIME type (image/jpeg, image/png, etc)")
    filename: Optional[str] = Field(default=None, description="Optional filename")


class DocumentPayload(BaseModel):
    """Document payload for text extraction from files."""

    data: str = Field(..., description="Base64-encoded document data or URL")
    media_type: str = Field(
        default="application/pdf",
        description="MIME type (application/pdf, application/vnd.openxmlformats-officedocument.wordprocessingml.document)",
    )
    filename: Optional[str] = Field(default=None, description="Optional filename (helps determine document type)")


class InteractRequest(BaseModel):
    """Request to interact with the agent."""

    message: str = Field(..., description="Message to send to the agent")
    context: Optional[MessageContext] = Field(None, description="Optional context")
    images: Optional[List[ImagePayload]] = Field(default=None, description="Optional images for multimodal interaction")
    documents: Optional[List[DocumentPayload]] = Field(
        default=None, description="Optional documents (PDF, DOCX) for text extraction"
    )


class InteractResponse(BaseModel):
    """Response from agent interaction."""

    message_id: str = Field(..., description="Unique message ID")
    response: str = Field(..., description="Agent's response")
    state: str = Field(..., description="Agent's cognitive state after processing")
    processing_time_ms: int = Field(..., description="Time taken to process")


class MessageRequest(BaseModel):
    """Request to send a message to the agent (async pattern)."""

    message: str = Field(..., description="Message to send to the agent")
    context: Optional[MessageContext] = Field(None, description="Optional context")


class MessageSubmissionResponse(BaseModel):
    """Response from message submission (returns immediately with task ID or rejection reason)."""

    message_id: str = Field(..., description="Unique message ID for tracking")
    task_id: Optional[str] = Field(None, description="Task ID created (if accepted)")
    channel_id: str = Field(..., description="Channel where message was sent")
    submitted_at: str = Field(..., description="ISO timestamp of submission")
    accepted: bool = Field(..., description="Whether message was accepted for processing")
    rejection_reason: Optional[MessageRejectionReason] = Field(None, description="Reason if rejected")
    rejection_detail: Optional[str] = Field(None, description="Additional detail about rejection")


class ConversationMessage(BaseModel):
    """Message in conversation history."""

    id: str = Field(..., description="Message ID")
    author: str = Field(..., description="Message author")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(..., description="When sent")
    is_agent: bool = Field(..., description="Whether this was from the agent")
    message_type: Literal["user", "agent", "system", "error"] = Field(
        "user", description="Type of message (user, agent, system, error)"
    )


class ConversationHistory(BaseModel):
    """Conversation history."""

    messages: List[ConversationMessage] = Field(..., description="Message history")
    total_count: int = Field(..., description="Total messages")
    has_more: bool = Field(..., description="Whether more messages exist")


class AgentStatus(BaseModel):
    """Agent status and cognitive state."""

    # Core identity
    agent_id: str = Field(..., description="Agent identifier")
    name: str = Field(..., description="Agent name")

    # Version information
    version: str = Field(..., description="CIRIS version (e.g., 1.0.4-beta)")
    codename: str = Field(..., description="Release codename")
    code_hash: Optional[str] = Field(None, description="Code hash for exact version")

    # State information
    cognitive_state: str = Field(..., description=DESC_CURRENT_COGNITIVE_STATE)
    uptime_seconds: float = Field(..., description="Time since startup")

    # Activity metrics
    messages_processed: int = Field(..., description="Total messages processed")
    last_activity: Optional[datetime] = Field(None, description="Last activity timestamp")
    current_task: Optional[str] = Field(None, description="Current task description")

    # System state
    services_active: int = Field(..., description="Number of active services")
    memory_usage_mb: float = Field(..., description="Current memory usage in MB")
    multi_provider_services: Optional[JSONDict] = Field(None, description="Services with provider counts")


class AgentIdentity(BaseModel):
    """Agent identity and capabilities."""

    # Identity
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Agent name")
    purpose: str = Field(..., description="Agent's purpose")
    created_at: datetime = Field(..., description="When agent was created")
    lineage: AgentLineage = Field(..., description="Agent lineage information")
    variance_threshold: float = Field(..., description="Identity variance threshold")

    # Capabilities
    tools: List[str] = Field(..., description="Available tools")
    handlers: List[str] = Field(..., description="Active handlers")
    services: ServiceAvailability = Field(..., description="Service availability")
    permissions: List[str] = Field(..., description="Agent permissions")


class ChannelInfo(BaseModel):
    """Information about a communication channel."""

    channel_id: str = Field(..., description="Unique channel identifier")
    channel_type: str = Field(..., description="Type of channel (discord, api, cli)")
    display_name: str = Field(..., description="Human-readable channel name")
    is_active: bool = Field(..., description="Whether channel is currently active")
    created_at: Optional[datetime] = Field(None, description="When channel was created")
    last_activity: Optional[datetime] = Field(None, description="Last message in channel")
    message_count: int = Field(0, description="Total messages in channel")


class ChannelList(BaseModel):
    """List of active channels."""

    channels: List[ChannelInfo] = Field(..., description="List of channels")
    total_count: int = Field(..., description="Total number of channels")


# Message tracking for interact functionality
_message_responses: dict[str, str] = {}
_response_events: dict[str, asyncio.Event] = {}


async def store_message_response(message_id: str, response: str) -> None:
    """Store a response and notify waiting request."""
    import os

    occurrence_id = os.environ.get("AGENT_OCCURRENCE_ID", "default")
    logger.info(
        f"[STORE_RESPONSE] occurrence={occurrence_id}, message_id={message_id}, response_len={len(response)}, current_keys={list(_message_responses.keys())}"
    )
    _message_responses[message_id] = response
    event = _response_events.get(message_id)
    if event:
        logger.info(f"[STORE_RESPONSE] Event found for {message_id}, setting it")
        event.set()
    else:
        logger.warning(f"[STORE_RESPONSE] No event found for {message_id}!")


# Endpoints


def _check_send_messages_permission(auth: AuthContext, request: Request) -> None:
    """Check if user has SEND_MESSAGES permission and handle OAuth auto-request."""
    if auth.has_permission(Permission.SEND_MESSAGES):
        return

    # Get auth service to check permission request status
    auth_service = request.app.state.auth_service if hasattr(request.app.state, "auth_service") else None
    user = auth_service.get_user(auth.user_id) if auth_service else None

    # If user is an OAuth user without a permission request, automatically create one
    if user and user.auth_type == "oauth" and user.permission_requested_at is None:
        # Set permission request timestamp
        user.permission_requested_at = datetime.now(timezone.utc)
        # Store the updated user
        if auth_service is not None and hasattr(auth_service, "_users"):
            auth_service._users[user.wa_id] = user  # Access private attribute for permission tracking

        # Don't log potentially sensitive email addresses
        logger.info(f"Auto-created permission request for OAuth user ID: {user.wa_id}")

    # Build detailed error response
    error_detail = {
        "error": "insufficient_permissions",
        "message": "You do not have permission to send messages to this agent.",
        "discord_invite": "https://discord.gg/A3HVPMWd",
        "can_request_permissions": user.permission_requested_at is None if user else True,
        "permission_requested": user.permission_requested_at is not None if user else False,
        "requested_at": user.permission_requested_at.isoformat() if user and user.permission_requested_at else None,
    }

    raise HTTPException(status_code=403, detail=error_detail)


async def _create_interaction_message(
    auth: AuthContext, body: Union[InteractRequest, MessageRequest]
) -> Tuple[str, str, IncomingMessage]:
    """Create message ID, channel ID, and IncomingMessage for interaction."""
    from ciris_engine.logic.adapters.api.api_document import get_api_document_helper
    from ciris_engine.logic.adapters.api.api_vision import get_api_vision_helper

    message_id = str(uuid.uuid4())
    channel_id = f"api_{auth.user_id}"  # User-specific channel

    # Process images if provided (InteractRequest only)
    images = []
    if isinstance(body, InteractRequest) and body.images:
        vision_helper = get_api_vision_helper()
        for img_payload in body.images:
            image_content = vision_helper.process_image_payload(
                img_payload.data,
                img_payload.media_type,
                img_payload.filename,
            )
            if image_content:
                images.append(image_content)
        if images:
            logger.info(f"Processed {len(images)} images for multimodal interaction")

    # Process documents if provided (InteractRequest only)
    additional_content = ""
    if isinstance(body, InteractRequest) and body.documents:
        document_helper = get_api_document_helper()
        if document_helper.is_available():
            doc_payloads = [
                {"data": doc.data, "media_type": doc.media_type, "filename": doc.filename} for doc in body.documents
            ]
            document_text = await document_helper.process_document_list(doc_payloads)
            if document_text:
                additional_content = "\n\n[Document Analysis]\n" + document_text
                logger.info(f"Processed {len(body.documents)} documents for interaction")
        else:
            logger.warning("Document processing requested but not available (missing libraries)")

    # Combine message content with any extracted document text
    final_content = body.message + additional_content

    msg = IncomingMessage(
        message_id=message_id,
        author_id=auth.user_id,
        author_name=auth.user_id,
        content=final_content,
        channel_id=channel_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        images=images,
    )

    return message_id, channel_id, msg


async def _handle_consent_for_user(auth: AuthContext, channel_id: str, request: Request) -> str:
    """Handle consent checking and creation for user, return consent notice if applicable."""
    try:
        from ciris_engine.logic.services.governance.consent import ConsentNotFoundError, ConsentService
        from ciris_engine.schemas.consent.core import ConsentRequest, ConsentStream

        # Get consent manager
        if hasattr(request.app.state, "consent_manager") and request.app.state.consent_manager:
            consent_manager = request.app.state.consent_manager
        else:
            from ciris_engine.logic.services.lifecycle.time import TimeService

            time_service = TimeService()
            consent_manager = ConsentService(time_service=time_service)
            request.app.state.consent_manager = consent_manager

        # Check if user has consent
        try:
            consent_status = await consent_manager.get_consent(auth.user_id)
            return ""  # User already has consent
        except ConsentNotFoundError:
            # First interaction - create default TEMPORARY consent
            consent_req = ConsentRequest(
                user_id=auth.user_id,
                stream=ConsentStream.TEMPORARY,
                categories=[],
                reason="Default TEMPORARY consent on first interaction",
            )
            consent_status = await consent_manager.grant_consent(consent_req, channel_id=channel_id)

            # Return notice to add to response
            return "\n\n📝 Privacy Notice: We forget about you in 14 days unless you say otherwise. Visit /v1/consent to manage your data preferences."

    except Exception as e:
        logger.warning(f"Could not check consent for user {auth.user_id}: {e}")
        return ""


async def _track_air_interaction(
    auth: AuthContext, channel_id: str, message_content: str, request: Request
) -> Optional[str]:
    """
    Track interaction for AIR (Artificial Interaction Reminder) parasocial prevention.

    This monitors 1:1 API interactions for:
    - Time-based triggers (30 min continuous)
    - Message-based triggers (20+ messages in 30 min window)

    Returns reminder message if threshold exceeded, None otherwise.
    """
    try:
        # Get consent manager which hosts the AIR manager
        consent_manager = getattr(request.app.state, "consent_manager", None)
        if not consent_manager:
            return None

        # Track interaction and get potential reminder
        reminder: Optional[str] = await consent_manager.track_interaction(
            user_id=auth.user_id,
            channel_id=channel_id,
            channel_type="api",
            message_content=message_content,
        )

        if reminder:
            logger.info(f"[AIR] Reminder triggered for user {auth.user_id}")

        return reminder

    except Exception as e:
        logger.debug(f"AIR tracking error (non-fatal): {e}")
        return None


def _derive_credit_account(
    auth: AuthContext,
    request: Request,
) -> Tuple[CreditAccount, Dict[str, str]]:
    """Build credit account metadata for the current request."""

    auth_service = getattr(request.app.state, "auth_service", None)
    user = None
    if auth_service and hasattr(auth_service, "get_user"):
        try:
            user = auth_service.get_user(auth.user_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Unable to load user for credit gating: %s", exc)

    provider = "api"
    account_id = auth.user_id
    authority_id = None
    tenant_id = None

    if user:
        authority_id = getattr(user, "wa_id", None) or auth.user_id
        tenant_id = getattr(user, "wa_parent_id", None)

        oauth_provider = getattr(user, "oauth_provider", None)
        oauth_external_id = getattr(user, "oauth_external_id", None)
        if oauth_provider and oauth_external_id:
            provider = f"oauth:{oauth_provider}"
            account_id = oauth_external_id
        else:
            provider = "wa"
            account_id = getattr(user, "wa_id", None) or auth.user_id
    else:
        if auth.api_key_id:
            provider = "api-key"
            account_id = auth.api_key_id
        elif auth.role == UserRole.SERVICE_ACCOUNT:
            provider = "service-account"
            account_id = auth.user_id

    account = CreditAccount(
        provider=provider,
        account_id=account_id,
        authority_id=authority_id,
        tenant_id=tenant_id,
    )

    metadata: Dict[str, str] = {
        "role": auth.role.value,
    }

    # Extract email address for billing backend user management
    if user and hasattr(user, "oauth_email") and user.oauth_email:
        metadata["email"] = user.oauth_email

    # Extract marketing opt-in preference if available
    if user and hasattr(user, "marketing_opt_in"):
        metadata["marketing_opt_in"] = str(user.marketing_opt_in).lower()

    if auth.api_key_id:
        metadata["api_key_id"] = auth.api_key_id

    return account, metadata


def _attach_credit_metadata(
    msg: IncomingMessage,
    request: Request,
    auth: AuthContext,
    channel_id: str,
) -> IncomingMessage:
    """Attach credit envelope data to the message for downstream processing."""

    logger.debug(f"[CREDIT_ATTACH] Called for message {msg.message_id}")

    resource_monitor = getattr(request.app.state, "resource_monitor", None)
    logger.debug(f"[CREDIT_ATTACH] resource_monitor exists: {resource_monitor is not None}")

    if not resource_monitor:
        logger.critical(f"[CREDIT_ATTACH] NO RESOURCE MONITOR - credit metadata NOT attached to {msg.message_id}")
        return msg

    credit_provider = getattr(resource_monitor, "credit_provider", None)
    logger.debug(
        f"[CREDIT_ATTACH] credit_provider exists: {credit_provider is not None}, type={type(credit_provider).__name__ if credit_provider else 'None'}"
    )

    if not credit_provider:
        # Try lazy initialization - token may have been written after server start
        from ciris_engine.logic.adapters.api.routes.billing import _try_lazy_init_billing_provider

        credit_provider = _try_lazy_init_billing_provider(request, resource_monitor)
        if not credit_provider:
            logger.critical(f"[CREDIT_ATTACH] NO CREDIT PROVIDER - credit metadata NOT attached to {msg.message_id}")
            return msg
        logger.info(f"[CREDIT_ATTACH] Lazily initialized billing provider for {msg.message_id}")

    try:
        account, _ = _derive_credit_account(auth, request)
        logger.debug(f"[CREDIT_ATTACH] Derived credit account: {account.cache_key()}")

        runtime = getattr(request.app.state, "runtime", None)
        agent_identity = getattr(runtime, "agent_identity", None) if runtime else None
        agent_id = getattr(agent_identity, "agent_id", None)

        # Determine billing mode: Android uses "informational" (check only, billing via LLM usage)
        # Hosted sites use "transactional" (check+spend per interaction)
        from ciris_engine.logic.utils.path_resolution import is_android

        billing_mode = "informational" if is_android() else "transactional"

        logger.debug(
            f"[CREDIT_ATTACH] Creating CreditContext with agent_id={agent_id}, channel_id={channel_id}, user_role={auth.role.value}, billing_mode={billing_mode}"
        )

        credit_context = CreditContext(
            agent_id=agent_id,
            channel_id=channel_id,
            request_id=msg.message_id,
            user_role=auth.role.value,
            billing_mode=billing_mode,
        )

        logger.debug("[CREDIT_ATTACH] CreditContext created successfully")
        logger.debug(
            f"[CREDIT_ATTACH] Attaching credit metadata to message {msg.message_id}: account={account.cache_key()}"
        )

        updated_msg = msg.model_copy(
            update={
                "credit_account": account.model_dump(),
                "credit_context": credit_context.model_dump(),
            }
        )

        logger.debug(f"[CREDIT_ATTACH] Credit metadata SUCCESSFULLY attached to message {msg.message_id}")

        # CRITICAL: Also attach resource_monitor to message for observer access
        # The observer may be initialized before resource_monitor exists on runtime,
        # so we attach it per-message to ensure credit enforcement works
        updated_msg._resource_monitor = resource_monitor  # type: ignore[attr-defined]
        logger.debug(f"[CREDIT_ATTACH] resource_monitor attached to message {msg.message_id}")

        return updated_msg

    except Exception as e:
        logger.critical(
            f"[CREDIT_ATTACH] EXCEPTION for message {msg.message_id}: {type(e).__name__}: {e}", exc_info=True
        )
        # Return original message without metadata on error
        return msg


def _get_runtime_processor(request: Request) -> Any:
    """Get runtime processor if available and valid."""
    runtime = getattr(request.app.state, "runtime", None)
    if not (runtime and hasattr(runtime, "agent_processor") and runtime.agent_processor):
        return None
    return runtime.agent_processor


def _is_processor_paused(processor: Any) -> bool:
    """Check if processor is in paused state."""
    return hasattr(processor, "_is_paused") and processor._is_paused


async def _handle_paused_message(request: Request, msg: IncomingMessage) -> None:
    """Route message to queue when processor is paused."""
    if hasattr(request.app.state, "on_message"):
        await request.app.state.on_message(msg)
    else:
        raise HTTPException(status_code=503, detail="Message handler not configured")


def _get_processor_cognitive_state(processor: Any) -> str:
    """Get current cognitive state from processor with fallback."""
    try:
        if hasattr(processor, "get_current_state"):
            state = processor.get_current_state()
            return str(state) if state is not None else "WORK"
    except Exception:
        pass
    return "WORK"  # Default


def _create_paused_response(
    message_id: str, cognitive_state: str, processing_time: int
) -> SuccessResponse[InteractResponse]:
    """Create response for paused processor state."""
    return SuccessResponse(
        data=InteractResponse(
            message_id=message_id,
            response="Processor paused - task added to queue. Resume processing to continue.",
            state=cognitive_state,
            processing_time_ms=processing_time,
        )
    )


async def _check_processor_pause_status(
    request: Request, msg: IncomingMessage, message_id: str, start_time: datetime
) -> Optional[SuccessResponse[InteractResponse]]:
    """Check if processor is paused and handle accordingly. Returns response if paused, None if not paused."""
    try:
        processor = _get_runtime_processor(request)
        if not processor or not _is_processor_paused(processor):
            return None

        # Processor is paused - route message and prepare response
        await _handle_paused_message(request, msg)

        # Clean up response tracking since we're returning immediately
        _response_events.pop(message_id, None)

        # Calculate processing time and get state
        processing_time = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        cognitive_state = _get_processor_cognitive_state(processor)

        return _create_paused_response(message_id, cognitive_state, processing_time)

    except HTTPException:
        # Re-raise HTTP exceptions (like 503 for missing message handler)
        raise
    except Exception as e:
        logger.debug(f"Could not check pause state: {e}")

    return None


def _get_interaction_timeout(request: Request) -> float:
    """Get interaction timeout from config or return default."""
    timeout = 55.0  # default timeout for longer processing
    if hasattr(request.app.state, "api_config"):
        timeout = request.app.state.api_config.interaction_timeout
    return timeout


def _get_current_cognitive_state(request: Request) -> str:
    """Get current cognitive state from request runtime."""
    runtime = getattr(request.app.state, "runtime", None)
    return _get_cognitive_state(runtime)


def _cleanup_interaction_tracking(message_id: str) -> None:
    """Clean up interaction tracking for given message ID."""
    _response_events.pop(message_id, None)
    _message_responses.pop(message_id, None)


async def _inject_error_to_channel(request: Request, channel_id: str, content: str) -> None:
    """Inject an error message into channel history for user visibility."""
    try:
        comm_service = getattr(request.app.state, "communication_service", None)
        if comm_service and hasattr(comm_service, "send_system_message"):
            await comm_service.send_system_message(
                channel_id=channel_id,
                content=content,
                message_type="error",
            )
    except Exception as e:
        logger.warning(f"Could not inject error message to channel: {e}")


@router.post("/message", response_model=SuccessResponse[MessageSubmissionResponse])
async def submit_message(
    request: Request, body: MessageRequest, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[MessageSubmissionResponse]:
    """
    Submit a message to the agent (async pattern - returns immediately).

    This endpoint returns immediately with a task_id for tracking or rejection reason.
    Use GET /agent/history to poll for the agent's response.

    This is the recommended way to interact with the agent via API,
    as it doesn't block waiting for processing to complete.

    Requires: SEND_MESSAGES permission (ADMIN+ by default, or OBSERVER with explicit grant)
    """
    from ciris_engine.schemas.runtime.messages import MessageHandlingStatus

    # Check permissions
    _check_send_messages_permission(auth, request)

    # Create message and tracking
    message_id, channel_id, msg = await _create_interaction_message(auth, body)
    msg = _attach_credit_metadata(msg, request, auth, channel_id)

    # Handle consent for user
    await _handle_consent_for_user(auth, channel_id, request)

    # Track interaction for AIR (parasocial attachment prevention)
    # Note: For async pattern, reminder is logged but not returned (user polls for response)
    await _track_air_interaction(auth, channel_id, body.message, request)

    # Track submission time
    submitted_at = datetime.now(timezone.utc)

    # Check if processor is paused
    pause_response = await _check_processor_pause_status(request, msg, message_id, submitted_at)
    if pause_response:
        # Return rejection for paused processor
        response = MessageSubmissionResponse(
            message_id=message_id,
            task_id=None,
            channel_id=channel_id,
            submitted_at=submitted_at.isoformat(),
            accepted=False,
            rejection_reason=MessageRejectionReason.PROCESSOR_PAUSED,
            rejection_detail="Agent processor is paused",
        )
        return SuccessResponse(data=response)

    # Submit message and get result (with credit enforcement)
    try:
        if hasattr(request.app.state, "on_message"):
            result = await request.app.state.on_message(msg)
        else:
            raise HTTPException(status_code=503, detail="Message handler not configured")
    except CreditDenied as exc:
        await _inject_error_to_channel(request, channel_id, f"Message blocked: {exc.reason}")
        response = MessageSubmissionResponse(
            message_id=message_id,
            task_id=None,
            channel_id=channel_id,
            submitted_at=submitted_at.isoformat(),
            accepted=False,
            rejection_reason=MessageRejectionReason.CREDIT_DENIED,
            rejection_detail=exc.reason,
        )
        return SuccessResponse(data=response)
    except CreditCheckFailed as exc:
        await _inject_error_to_channel(
            request, channel_id, "Message blocked: Credit service temporarily unavailable. Please try again later."
        )
        response = MessageSubmissionResponse(
            message_id=message_id,
            task_id=None,
            channel_id=channel_id,
            submitted_at=submitted_at.isoformat(),
            accepted=False,
            rejection_reason=MessageRejectionReason.CREDIT_CHECK_FAILED,
            rejection_detail=str(exc),
        )
        return SuccessResponse(data=response)

    # Map MessageHandlingResult to MessageSubmissionResponse
    accepted = result.status in [MessageHandlingStatus.TASK_CREATED, MessageHandlingStatus.UPDATED_EXISTING_TASK]
    rejection_reason = None
    rejection_detail = None

    if not accepted:
        # Map status to rejection reason
        status_to_reason = {
            MessageHandlingStatus.AGENT_OWN_MESSAGE: MessageRejectionReason.AGENT_OWN_MESSAGE,
            MessageHandlingStatus.FILTERED_OUT: MessageRejectionReason.FILTERED_OUT,
            MessageHandlingStatus.CHANNEL_RESTRICTED: MessageRejectionReason.CHANNEL_RESTRICTED,
            MessageHandlingStatus.RATE_LIMITED: MessageRejectionReason.RATE_LIMITED,
        }
        rejection_reason = status_to_reason.get(result.status)
        rejection_detail = result.filter_reasoning if result.filtered else None
    elif result.status == MessageHandlingStatus.UPDATED_EXISTING_TASK:
        # Add detail that existing task was updated
        rejection_detail = "Existing task updated with new information"

    # Return result
    response = MessageSubmissionResponse(
        message_id=message_id,
        task_id=result.task_id,
        channel_id=channel_id,
        submitted_at=submitted_at.isoformat(),
        accepted=accepted,
        rejection_reason=rejection_reason,
        rejection_detail=rejection_detail,
    )

    return SuccessResponse(data=response)


@router.post("/interact", response_model=SuccessResponse[InteractResponse])
async def interact(
    request: Request, body: InteractRequest, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[InteractResponse]:
    """
    Send message and get response.

    This endpoint combines the old send/ask functionality into a single interaction.
    It sends the message and waits for the agent's response (with a reasonable timeout).

    Requires: SEND_MESSAGES permission (ADMIN+ by default, or OBSERVER with explicit grant)
    """
    # Check permissions
    _check_send_messages_permission(auth, request)

    # Create message and tracking
    message_id, channel_id, msg = await _create_interaction_message(auth, body)
    msg = _attach_credit_metadata(msg, request, auth, channel_id)

    event = asyncio.Event()
    _response_events[message_id] = event

    # Handle consent for user
    consent_notice = await _handle_consent_for_user(auth, channel_id, request)

    # Track interaction for AIR (parasocial attachment prevention)
    air_reminder = await _track_air_interaction(auth, channel_id, body.message, request)

    # Track timing
    start_time = datetime.now(timezone.utc)

    # Check if processor is paused
    pause_response = await _check_processor_pause_status(request, msg, message_id, start_time)
    if pause_response:
        return pause_response

    try:
        if hasattr(request.app.state, "on_message"):
            await request.app.state.on_message(msg)
        else:
            raise HTTPException(status_code=503, detail="Message handler not configured")
    except CreditDenied as exc:
        await _inject_error_to_channel(request, channel_id, f"Message blocked: {exc.reason}")
        _cleanup_interaction_tracking(message_id)
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credit",
                "message": "Interaction blocked by credit policy.",
                "reason": exc.reason,
            },
        ) from exc
    except CreditCheckFailed as exc:
        await _inject_error_to_channel(
            request, channel_id, "Message blocked: Credit service temporarily unavailable. Please try again later."
        )
        _cleanup_interaction_tracking(message_id)
        raise HTTPException(status_code=503, detail="Credit provider unavailable") from exc
    except BillingServiceError as exc:
        await _inject_error_to_channel(request, channel_id, f"Service error: {exc.message}")
        _cleanup_interaction_tracking(message_id)
        raise HTTPException(
            status_code=402,
            detail={
                "error": "billing_error",
                "message": "LLM billing service error. Please check your account or try again later.",
                "reason": exc.message,
            },
        ) from exc

    # Get timeout and wait for response
    timeout = _get_interaction_timeout(request)

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)

        # Get response
        import os

        occurrence_id = os.environ.get("AGENT_OCCURRENCE_ID", "default")
        logger.info(
            f"[RETRIEVE_RESPONSE] occurrence={occurrence_id}, message_id={message_id}, available_keys={list(_message_responses.keys())}"
        )
        response_content = _message_responses.get(message_id, "I'm processing your request. Please check back shortly.")
        logger.info(
            f"[RETRIEVE_RESPONSE] Retrieved content_len={len(response_content)}, content_preview={response_content[:100] if response_content else 'EMPTY'}"
        )

        # Add consent notice if this is first interaction
        if consent_notice:
            response_content += consent_notice

        # Add AIR reminder if triggered (parasocial attachment prevention)
        if air_reminder:
            response_content += "\n\n---\n" + air_reminder

        # Clean up and calculate timing
        _cleanup_interaction_tracking(message_id)
        processing_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        # Build response
        response = InteractResponse(
            message_id=message_id,
            response=response_content,
            state=_get_current_cognitive_state(request),
            processing_time_ms=processing_time_ms,
        )

        return SuccessResponse(data=response)

    except asyncio.TimeoutError:
        # Clean up
        _cleanup_interaction_tracking(message_id)

        # Return a timeout response rather than error
        response = InteractResponse(
            message_id=message_id,
            response="Still processing. Check back later. Agent response is not guaranteed.",
            state="WORK",
            processing_time_ms=int(timeout * 1000),  # Use actual timeout value
        )

        return SuccessResponse(data=response)


@router.get("/history", response_model=SuccessResponse[ConversationHistory])
async def get_history(
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="Maximum messages to return"),
    before: Optional[datetime] = Query(None, description="Get messages before this time"),
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[ConversationHistory]:
    """
    Conversation history.

    Get the conversation history for the current user.
    """
    # Build channels to query based on user role
    channels_to_query = _build_channels_to_query(auth, request)
    channel_id = f"api_{auth.user_id}"

    logger.info(f"History query for user {auth.user_id} with role {auth.role}, channels: {channels_to_query}")

    # Check for mock message history first
    message_history = getattr(request.app.state, "message_history", None)
    if message_history is not None:
        history = await _get_history_from_mock(message_history, channels_to_query, limit)
        return SuccessResponse(data=history)

    # Get communication service
    comm_service = getattr(request.app.state, "communication_service", None)
    if not comm_service:
        # Fallback: query from memory
        memory_service = getattr(request.app.state, "memory_service", None)
        if memory_service:
            history = await _get_history_from_memory(memory_service, channel_id, limit)
            return SuccessResponse(data=history)

    try:
        history = await _get_history_from_communication_service(comm_service, channels_to_query, limit, before)
        return SuccessResponse(data=history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_cognitive_state(runtime: Any) -> str:
    """Get the agent's cognitive state with proper None checking."""
    if runtime is None:
        logger.warning("Runtime is None")
        return "UNKNOWN"

    # State manager is on the agent processor, not directly on runtime
    if hasattr(runtime, "agent_processor") and runtime.agent_processor:
        if hasattr(runtime.agent_processor, "state_manager") and runtime.agent_processor.state_manager:
            if hasattr(runtime.agent_processor.state_manager, "current_state"):
                state = runtime.agent_processor.state_manager.current_state
                # Convert AgentState enum to string if necessary
                return str(state)
            else:
                logger.warning("Agent processor state_manager exists but has no current_state attribute")
        else:
            logger.warning("Agent processor has no state_manager or state_manager is None")
    else:
        logger.warning("Runtime has no agent_processor or agent_processor is None")
    return "UNKNOWN"  # Don't default to WORK - be explicit about unknown state


def _calculate_uptime(time_service: Any) -> float:
    """Calculate the agent's uptime in seconds."""
    if not time_service:
        return 0.0

    # Try to get uptime from time service status
    if hasattr(time_service, "get_status"):
        time_status = time_service.get_status()
        if hasattr(time_status, "uptime_seconds"):
            uptime = time_status.uptime_seconds
            return float(uptime) if uptime is not None else 0.0

    # Calculate uptime manually
    if hasattr(time_service, "_start_time") and hasattr(time_service, "now"):
        delta = time_service.now() - time_service._start_time
        return float(delta.total_seconds())

    return 0.0


def _count_wakeup_tasks(uptime: float) -> int:
    """Count completed WAKEUP tasks."""
    try:
        from ciris_engine.logic import persistence
        from ciris_engine.schemas.runtime.enums import TaskStatus

        completed_tasks = persistence.get_tasks_by_status(TaskStatus.COMPLETED)

        wakeup_prefixes = [
            "VERIFY_IDENTITY",
            "VALIDATE_INTEGRITY",
            "EVALUATE_RESILIENCE",
            "ACCEPT_INCOMPLETENESS",
            "EXPRESS_GRATITUDE",
        ]

        count = sum(1 for task in completed_tasks if any(task.task_id.startswith(prefix) for prefix in wakeup_prefixes))

        # If no wakeup tasks found but system has been running, assume standard cycle
        if count == 0 and uptime > MIN_UPTIME_FOR_DEFAULT_TASKS:
            return 5  # Standard wakeup cycle completes 5 tasks

        return count
    except Exception as e:
        logger.warning(f"Failed to count completed tasks: {e}")
        return 0


def _count_active_services(service_registry: Any) -> Tuple[int, JSONDict]:
    """Count active services and get multi-provider service details."""
    multi_provider_count = 0
    multi_provider_services: JSONDict = {}

    if service_registry:
        from ciris_engine.schemas.runtime.enums import ServiceType

        for service_type in list(ServiceType):
            providers = service_registry.get_services_by_type(service_type)
            count = len(providers)
            if count > 0:
                multi_provider_count += count
                multi_provider_services[service_type.value] = {"providers": count, "type": "multi-provider"}

    # CIRIS has AT LEAST 19 service types:
    # Multi-provider services can have multiple instances + 12 singleton services
    services_active = multi_provider_count + 12

    return services_active, multi_provider_services


def _get_admin_channels(auth: AuthContext, request: Request) -> List[str]:
    """Get additional admin channels for privileged users."""
    channels = []
    if auth.role in ["ADMIN", "AUTHORITY", "SYSTEM_ADMIN"]:
        # Get default API channel from config
        api_host = getattr(request.app.state, "api_host", "127.0.0.1")
        api_port = getattr(request.app.state, "api_port", "8080")
        default_channel = f"api_{api_host}_{api_port}"
        channels.append(default_channel)

        # Add common variations of the API channel
        channels.extend(
            [
                f"api_0.0.0.0_{api_port}",  # Bind address
                f"api_127.0.0.1_{api_port}",  # Localhost
                f"api_localhost_{api_port}",  # Hostname variant
            ]
        )
    return channels


def _build_channels_to_query(auth: AuthContext, request: Request) -> List[str]:
    """Build list of channels to query for conversation history."""
    channel_id = f"api_{auth.user_id}"
    channels_to_query = [channel_id]
    channels_to_query.extend(_get_admin_channels(auth, request))
    # Remove duplicates while preserving order
    seen = set()
    deduped = []
    for channel in channels_to_query:
        if channel not in seen:
            seen.add(channel)
            deduped.append(channel)
    return deduped


def _convert_timestamp(timestamp: Any) -> datetime:
    """Convert timestamp string or datetime to datetime object."""
    if isinstance(timestamp, str):
        try:
            return datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)
    elif isinstance(timestamp, datetime):
        return timestamp
    else:
        return datetime.now(timezone.utc)


def _create_conversation_message_from_mock(msg: JSONDict, is_response: bool = False) -> ConversationMessage:
    """Create ConversationMessage from mock message data."""
    if is_response:
        return ConversationMessage(
            id=f"{msg['message_id']}_response",
            author="Scout",
            content=msg["response"],
            timestamp=_convert_timestamp(msg["timestamp"]),
            is_agent=True,
        )
    else:
        return ConversationMessage(
            id=msg["message_id"],
            author=msg["author_id"],
            content=msg["content"],
            timestamp=_convert_timestamp(msg["timestamp"]),
            is_agent=False,
        )


def _expand_mock_messages(user_messages: List[JSONDict]) -> List[ConversationMessage]:
    """Expand mock messages into user message + response pairs."""
    all_messages = []
    for msg in user_messages:
        # Add user message
        all_messages.append(_create_conversation_message_from_mock(msg))
        # Add agent response if exists
        if msg.get("response"):
            all_messages.append(_create_conversation_message_from_mock(msg, is_response=True))
    return all_messages


def _apply_message_limit(messages: List[ConversationMessage], limit: int) -> List[ConversationMessage]:
    """Apply message limit, taking the last N messages."""
    if len(messages) > limit:
        return messages[-limit:]
    return messages


async def _get_history_from_mock(
    message_history: List[JSONDict], channels_to_query: List[str], limit: int
) -> ConversationHistory:
    """Process conversation history from mock data."""
    # Filter messages for requested channels
    user_messages = [m for m in message_history if m.get("channel_id") in channels_to_query]

    # Expand all messages (user + response pairs)
    all_messages = _expand_mock_messages(user_messages)

    # Apply limit
    limited_messages = _apply_message_limit(all_messages, limit)

    return ConversationHistory(
        messages=limited_messages,
        total_count=len(user_messages),
        has_more=len(user_messages) > len(limited_messages),
    )


async def _get_history_from_memory(memory_service: Any, channel_id: str, limit: int) -> ConversationHistory:
    """Query conversation history from memory service."""
    from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
    from ciris_engine.schemas.services.operations import MemoryQuery

    query = MemoryQuery(
        node_id=f"conversation_{channel_id}",
        scope=GraphScope.LOCAL,
        type=NodeType.CONVERSATION_SUMMARY,
        include_edges=True,
        depth=1,
    )

    nodes = await memory_service.recall(query)

    # Convert to conversation messages
    messages = []
    for node in nodes:
        attrs = node.attributes
        messages.append(
            ConversationMessage(
                id=attrs.get("message_id", node.id),
                author=attrs.get("author", "unknown"),
                content=attrs.get("content", ""),
                timestamp=datetime.fromisoformat(attrs.get("timestamp", node.created_at)),
                is_agent=attrs.get("is_agent", False),
            )
        )

    return ConversationHistory(messages=messages, total_count=len(messages), has_more=len(messages) == limit)


def _safe_convert_message_timestamp(msg: Any) -> datetime:
    """Safely convert message timestamp with fallback."""
    timestamp_val = msg.timestamp
    if isinstance(timestamp_val, datetime):
        return timestamp_val
    if timestamp_val:
        try:
            return datetime.fromisoformat(str(timestamp_val))
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)


def _determine_message_type(msg: Any, is_agent: bool) -> Literal["user", "agent", "system", "error"]:
    """Determine the message type from message attributes."""
    # Check for explicit message_type attribute first
    if hasattr(msg, "message_type"):
        explicit_type = str(msg.message_type).lower()
        if explicit_type in ("user", "agent", "system", "error"):
            return explicit_type  # type: ignore[return-value]

    # Infer from is_agent flag
    if is_agent:
        return "agent"

    # Check if author indicates system message
    author = str(msg.author_name or msg.author_id or "").lower()
    if author == "error":
        return "error"
    if author in ("system", "ciris_system"):
        return "system"

    return "user"


def _convert_service_message_to_conversation(msg: Any) -> ConversationMessage:
    """Convert communication service message to ConversationMessage."""
    is_agent = bool(getattr(msg, "is_agent_message", False) or getattr(msg, "is_bot", False))
    message_type = _determine_message_type(msg, is_agent)

    return ConversationMessage(
        id=str(msg.message_id or ""),
        author=str(msg.author_name or msg.author_id or ""),
        content=str(msg.content or ""),
        timestamp=_safe_convert_message_timestamp(msg),
        is_agent=is_agent,
        message_type=message_type,
    )


async def _fetch_messages_from_channels(comm_service: Any, channels_to_query: List[str], fetch_limit: int) -> List[Any]:
    """Fetch messages from all specified channels."""
    fetched_messages = []
    for channel in channels_to_query:
        try:
            logger.info(f"Fetching messages from channel: {channel}")
            if comm_service is None:
                logger.warning("Communication service is not available")
                continue
            channel_messages = await comm_service.fetch_messages(channel, limit=fetch_limit)
            logger.info(f"Retrieved {len(channel_messages)} messages from {channel}")
            fetched_messages.extend(channel_messages)
        except Exception as e:
            logger.warning(f"Failed to fetch from channel {channel}: {e}")
            continue
    return fetched_messages


def _sort_and_filter_messages(fetched_messages: List[Any], before: Optional[datetime]) -> List[Any]:
    """Sort messages by timestamp and apply time filter."""
    # Sort messages by timestamp (newest first)
    sorted_messages = sorted(
        fetched_messages,
        key=lambda m: _safe_convert_message_timestamp(m),
        reverse=True,
    )

    # Filter by time if specified
    if before:
        return [m for m in sorted_messages if _safe_convert_message_timestamp(m) < before]
    return sorted_messages


async def _get_history_from_communication_service(
    comm_service: Any, channels_to_query: List[str], limit: int, before: Optional[datetime]
) -> ConversationHistory:
    """Get conversation history from communication service."""
    # Fetch more messages to allow filtering
    fetch_limit = limit * 2 if before else limit

    # Fetch messages from all relevant channels
    fetched_messages = await _fetch_messages_from_channels(comm_service, channels_to_query, fetch_limit)

    # Sort and filter messages
    filtered_messages = _sort_and_filter_messages(fetched_messages, before)

    # Convert to conversation messages and apply final limit
    conv_messages = [_convert_service_message_to_conversation(msg) for msg in filtered_messages[:limit]]

    return ConversationHistory(
        messages=conv_messages,
        total_count=len(filtered_messages),
        has_more=len(filtered_messages) > limit,
    )


def _get_current_task_info(request: Request) -> Optional[str]:
    """Get current task information from task scheduler."""
    import inspect

    task_scheduler = getattr(request.app.state, "task_scheduler", None)
    if task_scheduler and hasattr(task_scheduler, "get_current_task"):
        task = task_scheduler.get_current_task()
        # If the result is a coroutine (from AsyncMock in tests), close it and ignore
        # since the real TaskSchedulerService doesn't have this method
        if inspect.iscoroutine(task):
            task.close()  # Properly close the coroutine to avoid warning
            return None
        return str(task) if task is not None else None
    return None


def _get_memory_usage(request: Request) -> float:
    """Get current memory usage from resource monitor."""
    resource_monitor = getattr(request.app.state, "resource_monitor", None)
    if resource_monitor and hasattr(resource_monitor, "snapshot"):
        return float(resource_monitor.snapshot.memory_mb)
    return 0.0


def _get_version_info() -> Tuple[str, str, Optional[str]]:
    """Get version information including codename and code hash."""
    from ciris_engine.constants import CIRIS_CODENAME, CIRIS_VERSION

    try:
        from version import __version__ as code_hash_val

        code_hash: Optional[str] = code_hash_val
    except ImportError:
        code_hash = None

    return CIRIS_VERSION, CIRIS_CODENAME, code_hash


async def _build_agent_status(
    request: Request, cognitive_state: str, uptime: float, messages_processed: int, runtime: Any
) -> AgentStatus:
    """Build AgentStatus object with all required information."""
    # Get current task (synchronous call, not awaitable)
    current_task = _get_current_task_info(request)

    # Get resource usage
    memory_usage_mb = _get_memory_usage(request)

    # Count services
    service_registry = getattr(request.app.state, "service_registry", None)
    services_active, multi_provider_services = _count_active_services(service_registry)

    # Get identity
    agent_id, agent_name = _get_agent_identity_info(runtime)

    # Get version information
    version, codename, code_hash = _get_version_info()

    return AgentStatus(
        agent_id=agent_id,
        name=agent_name,
        version=version,
        codename=codename,
        code_hash=code_hash,
        cognitive_state=cognitive_state,
        uptime_seconds=uptime,
        messages_processed=messages_processed,
        last_activity=datetime.now(timezone.utc),
        current_task=current_task,
        services_active=services_active,
        memory_usage_mb=memory_usage_mb,
        multi_provider_services=multi_provider_services,
    )


def _get_agent_identity_info(runtime: Any) -> Tuple[str, str]:
    """Get agent ID and name."""
    agent_id = "ciris_agent"
    agent_name = "CIRIS"

    if hasattr(runtime, "agent_identity") and runtime.agent_identity:
        agent_id = runtime.agent_identity.agent_id
        # Try to get name from various sources
        if hasattr(runtime.agent_identity, "name"):
            agent_name = runtime.agent_identity.name
        elif hasattr(runtime.agent_identity, "core_profile"):
            # Use first part of description or role as name
            agent_name = runtime.agent_identity.core_profile.description.split(".")[0]

    return agent_id, agent_name


@router.get("/status", response_model=SuccessResponse[AgentStatus])
async def get_status(request: Request, auth: AuthContext = Depends(require_observer)) -> SuccessResponse[AgentStatus]:
    """
    Agent status and cognitive state.

    Get comprehensive agent status including state, metrics, and current activity.
    """
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime:
        raise HTTPException(status_code=503, detail="Runtime not available")

    try:
        # Get basic state information
        cognitive_state = _get_cognitive_state(runtime)
        time_service = getattr(request.app.state, "time_service", None)
        uptime = _calculate_uptime(time_service)
        messages_processed = _count_wakeup_tasks(uptime)

        # Build comprehensive status
        status = await _build_agent_status(request, cognitive_state, uptime, messages_processed, runtime)
        return SuccessResponse(data=status)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/identity", response_model=SuccessResponse[AgentIdentity])
async def get_identity(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[AgentIdentity]:
    """
    Agent identity and capabilities.

    Get comprehensive agent identity including capabilities, tools, and permissions.
    """
    # Get memory service to query identity
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=ERROR_MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Query identity from graph
        from ciris_engine.schemas.services.graph_core import GraphScope
        from ciris_engine.schemas.services.operations import MemoryQuery

        query = MemoryQuery(node_id="agent/identity", scope=GraphScope.IDENTITY, include_edges=False)

        nodes = await memory_service.recall(query)

        # Get identity data
        identity_data = {}
        if nodes:
            identity_node = nodes[0]
            identity_data = identity_node.attributes
        else:
            # Fallback to runtime identity
            runtime = getattr(request.app.state, "runtime", None)
            if runtime and hasattr(runtime, "agent_identity"):
                identity = runtime.agent_identity
                identity_data = {
                    "agent_id": identity.agent_id,
                    "name": getattr(identity, "name", identity.core_profile.description.split(".")[0]),
                    "purpose": getattr(identity, "purpose", identity.core_profile.description),
                    "created_at": identity.identity_metadata.created_at.isoformat(),
                    "lineage": {
                        "model": identity.identity_metadata.model,
                        "version": identity.identity_metadata.version,
                        "parent_id": getattr(identity.identity_metadata, "parent_id", None),
                        "creation_context": getattr(identity.identity_metadata, "creation_context", "default"),
                        "adaptations": getattr(identity.identity_metadata, "adaptations", []),
                    },
                    "variance_threshold": 0.2,
                }

        # Get capabilities

        # Get tool service for available tools
        tool_service = getattr(request.app.state, "tool_service", None)
        tools = []
        if tool_service:
            tools = await tool_service.list_tools()

        # Get handlers (these are the core action handlers)
        handlers = [
            "observe",
            "speak",
            "tool",
            "reject",
            "ponder",
            "defer",
            "memorize",
            "recall",
            "forget",
            "task_complete",
        ]

        # Get service availability
        services = ServiceAvailability()
        service_registry = getattr(request.app.state, "service_registry", None)
        if service_registry:
            from ciris_engine.schemas.runtime.enums import ServiceType

            for service_type in ServiceType:
                providers = service_registry.get_services_by_type(service_type)
                count = len(providers)
                # Map to service categories
                if "graph" in service_type.value.lower() or service_type.value == "MEMORY":
                    services.graph += count
                elif service_type.value in ["LLM", "SECRETS"]:
                    services.core += count
                elif service_type.value in [
                    "TIME",
                    "SHUTDOWN",
                    "INITIALIZATION",
                    "VISIBILITY",
                    "AUTHENTICATION",
                    "RESOURCE_MONITOR",
                    "RUNTIME_CONTROL",
                ]:
                    services.infrastructure += count
                elif service_type.value == "WISE_AUTHORITY":
                    services.governance += count
                else:
                    services.special += count

        # Get permissions (agent's core capabilities)
        permissions = ["communicate", "use_tools", "access_memory", "observe_environment", "learn", "adapt"]

        # Build response
        lineage_data = identity_data.get("lineage", {})
        lineage = AgentLineage(
            model=lineage_data.get("model", "unknown"),
            version=lineage_data.get("version", "1.0"),
            parent_id=lineage_data.get("parent_id"),
            creation_context=lineage_data.get("creation_context", "default"),
            adaptations=lineage_data.get("adaptations", []),
        )

        response = AgentIdentity(
            agent_id=identity_data.get("agent_id", "ciris_agent"),
            name=identity_data.get("name", "CIRIS"),
            purpose=identity_data.get("purpose", "Autonomous AI agent"),
            created_at=datetime.fromisoformat(identity_data.get("created_at", datetime.now(timezone.utc).isoformat())),
            lineage=lineage,
            variance_threshold=identity_data.get("variance_threshold", 0.2),
            tools=tools,
            handlers=handlers,
            services=services,
            permissions=permissions,
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _convert_to_channel_info(ch: Any, adapter_type: str) -> ChannelInfo:
    """Convert adapter channel data to ChannelInfo format."""
    if hasattr(ch, "channel_id"):
        # Pydantic model format
        return ChannelInfo(
            channel_id=ch.channel_id,
            channel_type=getattr(ch, "channel_type", adapter_type),
            display_name=getattr(ch, "display_name", ch.channel_id),
            is_active=getattr(ch, "is_active", True),
            created_at=getattr(ch, "created_at", None),
            last_activity=getattr(ch, "last_activity", None),
            message_count=getattr(ch, "message_count", 0),
        )
    else:
        # Dict format (legacy)
        return ChannelInfo(
            channel_id=ch.get("channel_id", ""),
            channel_type=ch.get("channel_type", adapter_type),
            display_name=ch.get("display_name", ch.get("channel_id", "")),
            is_active=ch.get("is_active", True),
            created_at=ch.get("created_at"),
            last_activity=ch.get("last_activity"),
            message_count=ch.get("message_count", 0),
        )


async def _get_channels_from_adapter(adapter: Any, adapter_type: str) -> List[ChannelInfo]:
    """Get channels from a single adapter."""
    channels = []
    if hasattr(adapter, "get_active_channels"):
        try:
            adapter_channels = await adapter.get_active_channels()
            for ch in adapter_channels:
                channels.append(_convert_to_channel_info(ch, adapter_type))
        except Exception as e:
            logger.error(f"Error getting channels from adapter {adapter_type}: {e}")
    return channels


async def _get_channels_from_bootstrap_adapters(runtime: Any) -> List[ChannelInfo]:
    """Get channels from bootstrap adapters."""
    channels = []
    if runtime and hasattr(runtime, "adapters"):
        logger.info(f"Checking {len(runtime.adapters)} bootstrap adapters for channels")
        for adapter in runtime.adapters:
            adapter_type = adapter.__class__.__name__.lower().replace("platform", "")
            channels.extend(await _get_channels_from_adapter(adapter, adapter_type))
    return channels


def _get_control_service(runtime: Any, request: Request) -> Any:
    """Get the runtime control service from app state or registry."""
    # Try app state first
    control_service = getattr(request.app.state, "main_runtime_control_service", None)
    if control_service:
        return control_service

    # Fallback to service registry
    if not runtime or not hasattr(runtime, "service_registry") or not runtime.service_registry:
        return None

    from ciris_engine.schemas.runtime.enums import ServiceType

    providers = runtime.service_registry.get_services_by_type(ServiceType.RUNTIME_CONTROL)
    return providers[0] if providers else None


def _get_adapter_manager(control_service: Any) -> Any:
    """Get adapter manager from control service."""
    if not control_service:
        return None
    if not hasattr(control_service, "adapter_manager"):
        return None
    return control_service.adapter_manager


async def _collect_unique_channels(adapter_manager: Any) -> List[ChannelInfo]:
    """Collect unique channels from loaded adapters."""
    if not adapter_manager or not hasattr(adapter_manager, "loaded_adapters"):
        return []

    channels = []
    seen_channel_ids = set()

    for adapter_id, instance in adapter_manager.loaded_adapters.items():
        adapter_channels = await _get_channels_from_adapter(instance.adapter, instance.adapter_type)

        # Add only unique channels
        for ch in adapter_channels:
            if ch.channel_id not in seen_channel_ids:
                channels.append(ch)
                seen_channel_ids.add(ch.channel_id)

    return channels


async def _get_channels_from_dynamic_adapters(runtime: Any, request: Request) -> List[ChannelInfo]:
    """Get channels from dynamically loaded adapters."""
    control_service = _get_control_service(runtime, request)
    adapter_manager = _get_adapter_manager(control_service)
    return await _collect_unique_channels(adapter_manager)


def _add_default_api_channels(channels: List[ChannelInfo], request: Request, auth: AuthContext) -> None:
    """Add default API channels if not already present."""
    # Default API channel
    api_host = getattr(request.app.state, "api_host", "127.0.0.1")
    api_port = getattr(request.app.state, "api_port", "8080")
    api_channel_id = f"api_{api_host}_{api_port}"

    if not any(ch.channel_id == api_channel_id for ch in channels):
        channels.append(
            ChannelInfo(
                channel_id=api_channel_id,
                channel_type="api",
                display_name=f"API Channel ({api_host}:{api_port})",
                is_active=True,
                created_at=None,
                last_activity=datetime.now(timezone.utc),
                message_count=0,
            )
        )

    # User-specific API channel
    user_channel_id = f"api_{auth.user_id}"
    if not any(ch.channel_id == user_channel_id for ch in channels):
        channels.append(
            ChannelInfo(
                channel_id=user_channel_id,
                channel_type="api",
                display_name=f"API Channel ({auth.user_id})",
                is_active=True,
                created_at=None,
                last_activity=None,
                message_count=0,
            )
        )


@router.get("/channels", response_model=SuccessResponse[ChannelList])
async def get_channels(request: Request, auth: AuthContext = Depends(require_observer)) -> SuccessResponse[ChannelList]:
    """
    List active communication channels.

    Get all channels where the agent is currently active or has been active.
    """
    try:
        channels = []
        runtime = getattr(request.app.state, "runtime", None)

        # Get channels from bootstrap adapters
        channels.extend(await _get_channels_from_bootstrap_adapters(runtime))

        # Get channels from dynamically loaded adapters
        dynamic_channels = await _get_channels_from_dynamic_adapters(runtime, request)
        channels.extend(dynamic_channels)

        # Add default API channels
        _add_default_api_channels(channels, request, auth)

        # Sort channels by type and then by id
        channels.sort(key=lambda x: (x.channel_type, x.channel_id))

        channel_list = ChannelList(channels=channels, total_count=len(channels))
        return SuccessResponse(data=channel_list)

    except Exception as e:
        logger.error(f"Failed to get channels: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Helper function to notify interact responses
async def notify_interact_response(message_id: str, content: str) -> None:
    """Notify waiting interact requests of responses."""
    if message_id in _response_events:
        _message_responses[message_id] = content
        _response_events[message_id].set()


def _validate_websocket_authorization(websocket: WebSocket) -> Optional[str]:
    """Validate websocket authorization header and return API key."""
    authorization = websocket.headers.get("authorization")
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None
    return authorization[7:]  # Remove "Bearer " prefix


async def _authenticate_websocket_user(websocket: WebSocket, api_key: str) -> Optional[AuthContext]:
    """Authenticate websocket user and return auth context."""
    auth_service = getattr(websocket.app.state, "auth_service", None)
    if not auth_service:
        return None

    key_info = auth_service.validate_api_key(api_key)
    if not key_info:
        return None

    return AuthContext(
        user_id=key_info.user_id,
        role=key_info.role,
        permissions=ROLE_PERMISSIONS.get(key_info.role, set()),
        api_key_id=auth_service._get_key_id(api_key),
        authenticated_at=datetime.now(timezone.utc),
    )


async def _handle_websocket_subscription_action(
    websocket: WebSocket, data: JSONDict, subscribed_channels: set[str]
) -> None:
    """Handle websocket subscribe/unsubscribe actions."""
    action = data.get("action")
    channels_raw = data.get("channels", [])
    # Type narrow to list for set operations
    channels = channels_raw if isinstance(channels_raw, list) else []

    if action == "subscribe":
        subscribed_channels.update(channels)
    elif action == "unsubscribe":
        subscribed_channels.difference_update(channels)
    elif action == "ping":
        await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
        return

    # Send subscription update for subscribe/unsubscribe
    if action in ["subscribe", "unsubscribe"]:
        await websocket.send_json(
            {
                "type": "subscription_update",
                "channels": list(subscribed_channels),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


def _register_websocket_client(websocket: WebSocket, client_id: str) -> None:
    """Register websocket client with communication service."""
    comm_service = getattr(websocket.app.state, "communication_service", None)
    if comm_service and hasattr(comm_service, "register_websocket"):
        comm_service.register_websocket(client_id, websocket)


def _unregister_websocket_client(websocket: WebSocket, client_id: str) -> None:
    """Unregister websocket client from communication service."""
    comm_service = getattr(websocket.app.state, "communication_service", None)
    if comm_service and hasattr(comm_service, "unregister_websocket"):
        comm_service.unregister_websocket(client_id)


# WebSocket endpoint for streaming


@router.websocket("/stream")
async def websocket_stream(
    websocket: WebSocket,
) -> None:
    """
    WebSocket endpoint for real-time updates.

    Clients can subscribe to different channels:
    - messages: Agent messages and responses
    - telemetry: Real-time metrics
    - reasoning: Reasoning traces
    - logs: System logs
    """
    # Validate authorization
    api_key = _validate_websocket_authorization(websocket)
    if not api_key:
        await websocket.close(code=1008, reason="Missing or invalid authorization header")
        return

    # Authenticate user
    auth_context = await _authenticate_websocket_user(websocket, api_key)
    if not auth_context:
        await websocket.close(code=1008, reason="Authentication failed")
        return

    # Check minimum role requirement (OBSERVER)
    if not auth_context.role.has_permission(UserRole.OBSERVER):
        await websocket.close(code=1008, reason="Insufficient permissions")
        return

    await websocket.accept()
    client_id = f"ws_{id(websocket)}"

    # Register websocket client
    _register_websocket_client(websocket, client_id)

    subscribed_channels = set(["messages"])  # Default subscription

    try:
        while True:
            # Receive and process client messages
            data = await websocket.receive_json()
            await _handle_websocket_subscription_action(websocket, data, subscribed_channels)

    except WebSocketDisconnect:
        # Clean up on disconnect
        _unregister_websocket_client(websocket, client_id)
        logger.info(f"WebSocket client {client_id} disconnected")
