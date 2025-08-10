import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Awaitable, Callable, List, Optional, Union

import discord
from discord.errors import ConnectionClosed, HTTPException

from ciris_engine.logic import persistence
from ciris_engine.logic.adapters.base import Service
from ciris_engine.protocols.services import CommunicationService, WiseAuthorityService
from ciris_engine.schemas.adapters.discord import (
    DiscordApprovalData,
    DiscordChannelInfo,
    DiscordGuidanceData,
    DiscordMessageData,
)
from ciris_engine.schemas.adapters.tools import ToolExecutionResult
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import IncomingMessage
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.authority_core import (
    DeferralApprovalContext,
    DeferralRequest,
    DeferralResponse,
    GuidanceRequest,
    GuidanceResponse,
    WAPermission,
)
from ciris_engine.schemas.services.context import DeferralContext, GuidanceContext
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.discord_nodes import DiscordApprovalNode, DiscordDeferralNode
from ciris_engine.schemas.services.graph_core import GraphNodeAttributes, GraphScope
from ciris_engine.schemas.telemetry.core import (
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
)

from .config import DiscordAdapterConfig
from .constants import ACTION_OBSERVE
from .discord_audit import DiscordAuditLogger
from .discord_channel_manager import DiscordChannelManager
from .discord_connection_manager import DiscordConnectionManager
from .discord_embed_formatter import DiscordEmbedFormatter
from .discord_error_handler import DiscordErrorHandler
from .discord_guidance_handler import DiscordGuidanceHandler
from .discord_message_handler import DiscordMessageHandler
from .discord_rate_limiter import DiscordRateLimiter
from .discord_reaction_handler import ApprovalRequest, ApprovalStatus, DiscordReactionHandler
from .discord_tool_handler import DiscordToolHandler

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
    from ciris_engine.schemas.adapters.registration import AdapterServiceRegistration

logger = logging.getLogger(__name__)


class DiscordAdapter(Service, CommunicationService, WiseAuthorityService):
    """
    Discord adapter implementing CommunicationService and WiseAuthorityService protocols.
    Coordinates specialized handlers for different aspects of Discord functionality.
    """

    def __init__(
        self,
        token: str,
        bot: Optional[discord.Client] = None,
        on_message: Optional[Callable[[IncomingMessage], Awaitable[None]]] = None,
        time_service: Optional["TimeServiceProtocol"] = None,
        bus_manager: Optional[Any] = None,
        config: Optional[DiscordAdapterConfig] = None,
    ) -> None:
        retry_config = {
            "retry": {
                "global": {
                    "max_retries": 3,
                    "base_delay": 2.0,
                    "max_delay": 30.0,
                },
                "discord_api": {
                    "retryable_exceptions": (HTTPException, ConnectionClosed, asyncio.TimeoutError),
                },
            }
        }
        super().__init__(config=retry_config)

        self.token = token
        self._time_service = time_service
        self.bus_manager = bus_manager
        self.discord_config = config or DiscordAdapterConfig()

        # Ensure we have a time service
        if self._time_service is None:
            from ciris_engine.logic.services.lifecycle.time import TimeService

            self._time_service = TimeService()

        self._channel_manager = DiscordChannelManager(token, bot, on_message)
        self._message_handler = DiscordMessageHandler(bot)
        self._guidance_handler = DiscordGuidanceHandler(
            bot, self._time_service, self.bus_manager.memory if self.bus_manager else None
        )
        self._reaction_handler = DiscordReactionHandler(bot, self._time_service)
        self._audit_logger = DiscordAuditLogger(self._time_service)
        self._connection_manager = DiscordConnectionManager(token, bot, self._time_service)
        self._error_handler = DiscordErrorHandler()
        self._rate_limiter = DiscordRateLimiter()
        self._embed_formatter = DiscordEmbedFormatter()
        self._tool_handler = DiscordToolHandler(None, bot, self._time_service)
        self._start_time: Optional[datetime] = None
        self._approval_timeout_task: Optional[asyncio.Task] = None

        # Set up connection callbacks
        self._setup_connection_callbacks()

    async def _retry_discord_operation(
        self,
        operation: Callable[..., Awaitable[Any]],
        *args: Any,
        operation_name: str,
        config_key: str = "discord_api",
        **kwargs: Any,
    ) -> Any:
        """Wrapper for retry_with_backoff that handles Discord-specific configuration."""
        # Apply rate limiting before the operation
        endpoint = kwargs.get("endpoint", operation_name)
        await self._rate_limiter.acquire(endpoint)

        try:
            # Get retry config from base class config (which is a dict)
            retry_cfg = (
                self.config.get("retry", {}).get(config_key, {})
                if hasattr(self, "config") and isinstance(self.config, dict)
                else {}
            )
            result = await self.retry_with_backoff(
                operation,
                *args,
                max_retries=retry_cfg.get("max_retries", 3),
                base_delay=retry_cfg.get("base_delay", 2.0),
                max_delay=retry_cfg.get("max_delay", 30.0),
                # Include all connection-related errors as retryable
                retryable_exceptions=retry_cfg.get(
                    "retryable_exceptions",
                    (
                        HTTPException,  # Discord API errors
                        ConnectionClosed,  # WebSocket closed
                        asyncio.TimeoutError,  # Timeout errors
                        RuntimeError,  # Session closed errors
                        OSError,  # SSL and network errors
                        ConnectionError,  # Base connection errors
                        ConnectionResetError,  # Connection reset by peer
                        ConnectionAbortedError,  # Connection aborted
                    ),
                ),
                **kwargs,
            )
            return result
        except Exception as e:
            # Handle errors with the error handler
            if isinstance(e, (HTTPException, ConnectionClosed)):
                error_info = self._error_handler.handle_channel_error(
                    kwargs.get("channel_id", "unknown"), e, operation_name
                )
                # Re-raise if not retryable
                if not error_info.get("can_retry", False):
                    raise
            raise

    async def _emit_telemetry(
        self, metric_name: str, value: float = 1.0, tags: Optional[dict[str, Union[str, float, int, bool]]] = None
    ) -> None:
        """Emit telemetry as TSDBGraphNode through memory bus."""
        if not self.bus_manager or not self.bus_manager.memory:
            return  # No bus manager, can't emit telemetry

        try:
            # If value is in tags, extract it
            if tags and "value" in tags:
                value = float(tags.pop("value"))
            elif tags and "execution_time" in tags:
                value = float(tags["execution_time"])
            elif tags and "success" in tags:
                # For boolean success, use 1.0 for true, 0.0 for false
                value = 1.0 if tags["success"] else 0.0

            # Convert all tag values to strings as required by memorize_metric
            string_tags = {k: str(v) for k, v in (tags or {}).items()}

            # Use memorize_metric instead of creating GraphNode directly
            await self.bus_manager.memory.memorize_metric(
                metric_name=metric_name, value=value, tags=string_tags, scope="local", handler_name="adapter.discord"
            )
        except Exception as e:
            logger.debug(f"Failed to emit telemetry {metric_name}: {e}")

    async def send_message(self, channel_id: str, content: str) -> bool:
        """Implementation of CommunicationService.send_message"""
        # Check if client exists, but let retry logic handle connection state
        if not self._client:
            logger.warning(f"Discord client not initialized, cannot send message to channel {channel_id}")
            return False

        correlation_id = str(uuid.uuid4())
        time_service = self._time_service
        if time_service is None:
            logger.error("Time service not initialized")
            raise RuntimeError("Time service not initialized")
        start_time = time_service.now()

        try:
            # The retry logic will handle connection issues and wait for reconnection
            await self._retry_discord_operation(
                self._message_handler.send_message_to_channel,
                channel_id,
                content,
                operation_name="send_message",
                config_key="discord_api",
            )

            end_time = time_service.now()
            execution_time_ms = (end_time - start_time).total_seconds() * 1000

            # result contains the return value from send_message_to_channel
            persistence.add_correlation(
                ServiceCorrelation(
                    correlation_id=correlation_id,
                    service_type="discord",
                    handler_name="DiscordAdapter",
                    action_type="speak",
                    request_data=ServiceRequestData(
                        service_type="discord",
                        method_name="send_message",
                        channel_id=channel_id,
                        parameters={"content": content},
                        request_timestamp=start_time,
                    ),
                    response_data=ServiceResponseData(
                        success=True,
                        result_summary="Message sent successfully",
                        execution_time_ms=execution_time_ms,
                        response_timestamp=end_time,
                    ),
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=start_time,
                    updated_at=end_time,
                    timestamp=start_time,
                ),
                time_service,
            )

            # Emit telemetry for message sent
            await self._emit_telemetry(
                "discord.message.sent",
                1.0,
                {"adapter_type": "discord", "channel_id": channel_id, "execution_time": str(execution_time_ms)},
            )

            # Audit log the operation
            await self._audit_logger.log_message_sent(
                channel_id=channel_id,
                author_id="discord_adapter",
                message_content=content,
                correlation_id=correlation_id,
            )

            return True
        except (HTTPException, ConnectionClosed, asyncio.TimeoutError, RuntimeError, OSError, ConnectionError) as e:
            # These are retryable exceptions - let them propagate so retry logic can handle them
            # But first log the error for debugging
            error_info = self._error_handler.handle_message_error(e, content, channel_id)
            logger.error(f"Failed to send message via Discord: {error_info}")
            # Re-raise the exception so retry logic can handle it
            raise
        except Exception as e:
            # Handle non-retryable errors
            error_info = self._error_handler.handle_message_error(e, content, channel_id)
            logger.error(f"Failed to send message via Discord (non-retryable): {error_info}")
            return False

    async def fetch_messages(
        self, channel_id: str, *, limit: int = 50, before: Optional[datetime] = None
    ) -> List[DiscordMessageData]:
        """Implementation of CommunicationService.fetch_messages - fetches from correlations"""
        from ciris_engine.logic.persistence import get_correlations_by_channel

        try:
            # Get correlations for this channel
            correlations = get_correlations_by_channel(channel_id=channel_id, limit=limit)

            messages = []
            for corr in correlations:
                # Extract message data from correlation
                if corr.action_type == "speak" and corr.request_data:
                    # This is an outgoing message from the agent
                    content = ""
                    if hasattr(corr.request_data, "parameters") and corr.request_data.parameters:
                        content = corr.request_data.parameters.get("content", "")

                    messages.append(
                        DiscordMessageData(
                            id=corr.correlation_id,
                            author_id="ciris",
                            author_name="CIRIS",
                            content=content,
                            timestamp=(
                                (corr.timestamp or corr.created_at).isoformat()
                                if corr.timestamp or corr.created_at
                                else None
                            ),
                            channel_id=channel_id,
                            is_bot=True,
                        )
                    )
                elif corr.action_type == ACTION_OBSERVE and corr.request_data:
                    # This is an incoming message from a user
                    content = ""
                    author_id = "unknown"
                    author_name = "User"

                    if hasattr(corr.request_data, "parameters") and corr.request_data.parameters:
                        params = corr.request_data.parameters
                        content = params.get("content", "")
                        author_id = params.get("author_id", "unknown")
                        author_name = params.get("author_name", "User")

                    messages.append(
                        DiscordMessageData(
                            id=corr.correlation_id,
                            author_id=author_id,
                            author_name=author_name,
                            content=content,
                            timestamp=(
                                (corr.timestamp or corr.created_at).isoformat()
                                if corr.timestamp or corr.created_at
                                else None
                            ),
                            channel_id=channel_id,
                            is_bot=False,
                        )
                    )

            # Sort by timestamp
            messages.sort(key=lambda m: m.timestamp or "")

            return messages

        except Exception as e:
            logger.error(f"Failed to fetch messages from correlations for Discord channel {channel_id}: {e}")
            # Fall back to Discord API if correlation fetch fails
            if self._channel_manager.client:
                try:
                    messages_result = await self._retry_discord_operation(
                        self._message_handler.fetch_messages_from_channel,
                        channel_id,
                        limit,
                        operation_name="fetch_messages",
                        config_key="discord_api",
                    )
                    # Convert raw dicts to DiscordMessageData
                    if messages_result:
                        return [DiscordMessageData(**msg) if isinstance(msg, dict) else msg for msg in messages_result]
                    return []
                except Exception as e2:
                    logger.exception(f"Failed to fetch messages from Discord API: {e2}")
            return []

    # --- WiseAuthorityService ---
    async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]:
        """Send a guidance request to the configured guidance channel and wait for a response."""
        deferral_channel_id = self.discord_config.deferral_channel_id
        if not deferral_channel_id:
            logger.error("DiscordAdapter: Guidance channel not configured.")
            raise RuntimeError("Guidance channel not configured.")

        time_service = self._time_service
        if time_service is None:
            logger.error("Time service not initialized")
            return None
        start_time = time_service.now()

        try:
            correlation_id = str(uuid.uuid4())
            guidance_result = await self._retry_discord_operation(
                self._guidance_handler.fetch_guidance_from_channel,
                deferral_channel_id,
                context.model_dump(),
                operation_name="fetch_guidance",
                config_key="discord_api",
            )
            # guidance_result should be a dict from fetch_guidance_from_channel
            guidance = guidance_result if isinstance(guidance_result, dict) else {}

            end_time = time_service.now()
            execution_time_ms = (end_time - start_time).total_seconds() * 1000

            persistence.add_correlation(
                ServiceCorrelation(
                    correlation_id=correlation_id,
                    service_type="discord",
                    handler_name="DiscordAdapter",
                    action_type="fetch_guidance",
                    request_data=ServiceRequestData(
                        service_type="discord",
                        method_name="fetch_guidance",
                        channel_id=deferral_channel_id,
                        parameters={"context": str(context.model_dump())},
                        request_timestamp=start_time,
                    ),
                    response_data=ServiceResponseData(
                        success=True,
                        result_summary=f"Guidance received: {guidance.get('guidance', 'None')}",
                        execution_time_ms=execution_time_ms,
                        response_timestamp=end_time,
                    ),
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=start_time,
                    updated_at=end_time,
                    timestamp=start_time,
                ),
                time_service,
            )
            guidance_text = guidance.get("guidance")

            # Audit log the guidance request
            await self._audit_logger.log_guidance_request(
                channel_id=deferral_channel_id,
                requester_id="discord_adapter",
                context=context.model_dump(),
                guidance_received=guidance_text,
            )

            return guidance_text
        except Exception as e:
            logger.exception(f"Failed to fetch guidance from Discord: {e}")
            raise

    def check_authorization(self, wa_id: str, action: str, resource: Optional[str] = None) -> bool:
        """Check if a Discord user is authorized for an action."""
        # In Discord, authorization is based on roles:
        # - AUTHORITY role can do anything
        # - OBSERVER role can only observe
        # - No role = no permissions
        try:
            if not self._channel_manager.client:
                return False

            # Get user from all guilds the bot is in
            user = None
            for guild in self._channel_manager.client.guilds:
                member = guild.get_member(int(wa_id))
                if member:
                    user = member
                    break

            if not user:
                return False

            # Check roles
            role_names = [role.name.upper() for role in user.roles]

            # AUTHORITY can do anything
            if "AUTHORITY" in role_names:
                return True

            # OBSERVER can only observe/read
            if "OBSERVER" in role_names and action in ["read", "observe", "fetch"]:
                return True

            return False
        except Exception as e:
            logger.error(f"Error checking authorization for {wa_id}: {e}")
            return False

    async def request_approval(self, action: str, context: DeferralApprovalContext) -> bool:
        """Request approval for an action through the deferral channel."""
        deferral_channel_id = self.discord_config.deferral_channel_id
        if not deferral_channel_id:
            logger.error("DiscordAdapter: Deferral channel not configured.")
            return False

        try:
            # Create approval request embed
            approval_data = DiscordApprovalData(
                action=action,
                task_id=context.task_id,
                thought_id=context.thought_id,
                requester_id=context.requester_id,
                action_name=context.action_name,
                action_params=context.action_params or {},
                channel_id=context.channel_id,
            )
            embed = self._embed_formatter.format_approval_request(action, approval_data)

            # Get channel for sending embed
            channel = await self._channel_manager.resolve_channel(deferral_channel_id)
            if not channel:
                logger.error(f"Could not resolve deferral channel {deferral_channel_id}")
                return False

            # Send embed message
            sent_message = await channel.send(embed=embed)

            # Create approval result container
            approval_result = None

            def handle_approval(approval: ApprovalRequest) -> None:
                nonlocal approval_result
                approval_result = approval

            # Create approval request using the sent message
            approval_request = ApprovalRequest(
                message_id=sent_message.id,
                channel_id=int(deferral_channel_id),
                request_type="action_approval",
                context={
                    "action": action,
                    "task_id": context.task_id,
                    "thought_id": context.thought_id,
                    "requester_id": context.requester_id,
                },
                timeout_seconds=300,  # 5 minute timeout
            )

            # Add reactions
            await sent_message.add_reaction("✅")
            await sent_message.add_reaction("❌")

            # Register with reaction handler
            self._reaction_handler._pending_approvals[sent_message.id] = approval_request
            self._reaction_handler._approval_callbacks[sent_message.id] = handle_approval

            # Schedule timeout
            self._approval_timeout_task = asyncio.create_task(self._reaction_handler._handle_timeout(approval_request))

            if not approval_request:
                return False

            # Wait for approval resolution (up to timeout)
            max_wait = approval_request.timeout_seconds + 5
            time_service = self._time_service
            if time_service is None:
                logger.error("Time service not initialized")
                return False
            start_time = time_service.now()

            while approval_result is None:
                await asyncio.sleep(0.5)
                elapsed = (time_service.now() - start_time).total_seconds()
                if elapsed > max_wait:
                    logger.error("Approval request timed out")
                    return False

            # Store approval request in memory
            if approval_result and self.bus_manager and self.bus_manager.memory:
                try:
                    approval_node = DiscordApprovalNode(
                        id=f"discord_approval/{approval_request.message_id}",
                        scope=GraphScope.LOCAL,
                        attributes=GraphNodeAttributes(created_by="discord_adapter", tags=["discord", "approval"]),
                        approval_id=str(approval_request.message_id),
                        action=action,
                        request_type="action_approval",
                        channel_id=deferral_channel_id,
                        message_id=str(approval_request.message_id),
                        task_id=context.task_id,
                        thought_id=context.thought_id,
                        requester_id=context.requester_id,
                        status=approval_result.status.value,
                        resolved_at=approval_result.resolved_at,
                        resolver_id=approval_result.resolver_id,
                        resolver_name=approval_result.resolver_name,
                        context={"channel_id": context.channel_id} if context.channel_id else {},
                        action_params=context.action_params,
                        updated_at=time_service.now(),
                        updated_by="discord_adapter",
                    )

                    await self.bus_manager.memory.store(
                        node_id=str(approval_request.message_id),
                        node_type="DISCORD_APPROVAL",
                        attributes=approval_node.to_graph_node().attributes,
                        scope="local",
                        handler_name="discord_adapter",
                    )
                except Exception as e:
                    logger.error(f"Failed to store approval in memory: {e}")

            # Audit log the approval request
            await self._audit_logger.log_approval_request(
                channel_id=deferral_channel_id,
                requester_id=context.requester_id,
                action=action,
                approval_status=approval_result.status.value,
                approver_id=approval_result.resolver_id,
            )

            # Return true only if approved
            return approval_result.status == ApprovalStatus.APPROVED

        except Exception as e:
            logger.exception(f"Failed to request approval: {e}")
            return False

    async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse:
        """Get guidance using the structured request/response format."""
        # Convert GuidanceRequest to GuidanceContext for fetch_guidance
        # Generate IDs if not available
        context = GuidanceContext(
            thought_id=f"guidance_{uuid.uuid4().hex[:8]}",
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            question=request.context,  # GuidanceRequest.context is the question
            ethical_considerations=request.options if request.options else [],
            domain_context={"urgency": request.urgency} if request.urgency else {},
        )

        guidance = await self.fetch_guidance(context)

        return GuidanceResponse(
            selected_option=guidance if guidance in request.options else None,
            custom_guidance=guidance if guidance not in request.options else None,
            reasoning="Guidance provided by Discord WA channel",
            wa_id="discord_wa",
            signature=f"discord_{uuid.uuid4().hex[:8]}",
        )

    async def get_pending_deferrals(self, wa_id: Optional[str] = None) -> List[PendingDeferral]:
        """Get pending deferrals from the deferral channel."""
        if not self.bus_manager or not self.bus_manager.memory:
            logger.warning("No memory bus available for deferral tracking")
            return []

        try:
            # Query memory for pending deferrals
            query = {"node_type": "DISCORD_DEFERRAL", "status": "pending"}

            # Add WA filter if specified
            if wa_id:
                query["created_by"] = wa_id

            # Search memory
            nodes = await self.bus_manager.memory.search(query)

            # Convert to PendingDeferral objects
            pending = []
            for node in nodes:
                if isinstance(node.attributes, dict):
                    attrs = node.attributes
                else:
                    attrs = node.attributes.model_dump() if hasattr(node.attributes, "model_dump") else {}

                pending.append(
                    PendingDeferral(
                        deferral_id=attrs.get("deferral_id", node.id),
                        task_id=attrs.get("task_id", ""),
                        thought_id=attrs.get("thought_id", ""),
                        reason=attrs.get("reason", ""),
                        created_at=attrs.get(
                            "created_at", self._time_service.now() if self._time_service else datetime.now()
                        ),
                        deferred_by=attrs.get("created_by", "discord_agent"),
                        channel_id=attrs.get("channel_id"),
                        priority=attrs.get("priority", "normal"),
                    )
                )

            return pending

        except Exception as e:
            logger.error(f"Failed to get pending deferrals: {e}")
            return []

    async def resolve_deferral(self, deferral_id: str, response: DeferralResponse) -> bool:
        """Resolve a deferred decision."""
        deferral_channel_id = self.discord_config.deferral_channel_id
        if not deferral_channel_id:
            return False

        try:
            # Send resolution message
            message = "**DEFERRAL RESOLVED**\n"
            message += f"ID: {deferral_id}\n"
            message += f"Approved: {'Yes' if response.approved else 'No'}\n"
            if response.reason:
                message += f"Reason: {response.reason}\n"
            if response.modified_time:
                message += f"Modified Time: {response.modified_time.isoformat()}\n"
            message += f"WA ID: {response.wa_id}\n"

            return await self.send_message(deferral_channel_id, message)
        except Exception as e:
            logger.error(f"Failed to resolve deferral: {e}")
            return False

    async def grant_permission(self, wa_id: str, permission: str, resource: Optional[str] = None) -> bool:
        """Grant AUTHORITY or OBSERVER role to a Discord user."""
        if permission.upper() not in ["AUTHORITY", "OBSERVER"]:
            logger.error(f"Invalid permission: {permission}. Must be AUTHORITY or OBSERVER.")
            return False

        try:
            if not self._channel_manager.client:
                return False

            # Find user in guilds and grant role
            for guild in self._channel_manager.client.guilds:
                member = guild.get_member(int(wa_id))
                if member:
                    # Find or create role
                    role = discord.utils.get(guild.roles, name=permission.upper())
                    if not role:
                        # Create role if it doesn't exist
                        role = await guild.create_role(name=permission.upper())

                    # Grant role
                    await member.add_roles(role)
                    logger.info(f"Granted {permission} to user {wa_id} in guild {guild.name}")

                    # Audit log the permission change
                    await self._audit_logger.log_permission_change(
                        admin_id="discord_adapter",
                        target_id=wa_id,
                        permission=permission,
                        action="grant",
                        guild_id=str(guild.id),
                    )

                    return True

            logger.error(f"User {wa_id} not found in any guild")
            return False
        except Exception as e:
            logger.exception(f"Failed to grant permission: {e}")
            return False

    async def revoke_permission(self, wa_id: str, permission: str, resource: Optional[str] = None) -> bool:
        """Revoke AUTHORITY or OBSERVER role from a Discord user."""
        if permission.upper() not in ["AUTHORITY", "OBSERVER"]:
            logger.error(f"Invalid permission: {permission}. Must be AUTHORITY or OBSERVER.")
            return False

        try:
            if not self._channel_manager.client:
                return False

            # Find user in guilds and remove role
            for guild in self._channel_manager.client.guilds:
                member = guild.get_member(int(wa_id))
                if member:
                    role = discord.utils.get(guild.roles, name=permission.upper())
                    if role and role in member.roles:
                        await member.remove_roles(role)
                        logger.info(f"Revoked {permission} from user {wa_id} in guild {guild.name}")

                        # Audit log the permission change
                        await self._audit_logger.log_permission_change(
                            admin_id="discord_adapter",
                            target_id=wa_id,
                            permission=permission,
                            action="revoke",
                            guild_id=str(guild.id),
                        )

                        return True

            return False
        except Exception as e:
            logger.exception(f"Failed to revoke permission: {e}")
            return False

    def get_active_channels(self) -> List[DiscordChannelInfo]:
        """Get list of active Discord channels."""
        channels: List[DiscordChannelInfo] = []

        logger.info(
            f"[DISCORD] get_active_channels called, client ready: {self._channel_manager.client.is_ready() if self._channel_manager.client else False}"
        )

        if not self._channel_manager.client or not self._channel_manager.client.is_ready():
            logger.warning("[DISCORD] Client not ready, returning empty channels")
            return channels

        try:
            # Get all monitored channels
            logger.info(f"[DISCORD] Checking {len(self.discord_config.monitored_channel_ids)} monitored channels")
            for channel_id in self.discord_config.monitored_channel_ids:
                channel = self._channel_manager.client.get_channel(int(channel_id))
                logger.info(f"[DISCORD] Channel {channel_id}: {'found' if channel else 'not found'}")
                if channel:
                    channels.append(
                        DiscordChannelInfo(
                            channel_id=f"discord_{channel_id}",
                            channel_type="discord",
                            display_name=(
                                f"#{channel.name}" if hasattr(channel, "name") else f"Discord Channel {channel_id}"
                            ),
                            is_active=True,
                            created_at=(
                                channel.created_at.isoformat()
                                if hasattr(channel, "created_at") and channel.created_at
                                else None
                            ),
                            last_activity=None,  # Could track this if needed
                            message_count=0,  # Could track this if needed
                        )
                    )

            # Add deferral channel if configured
            if self.discord_config.deferral_channel_id:
                channel = self._channel_manager.client.get_channel(int(self.discord_config.deferral_channel_id))
                if channel and f"discord_{self.discord_config.deferral_channel_id}" not in [
                    ch.channel_id for ch in channels
                ]:
                    channels.append(
                        DiscordChannelInfo(
                            channel_id=f"discord_{self.discord_config.deferral_channel_id}",
                            channel_type="discord",
                            display_name=(
                                f"#{channel.name} (Deferrals)"
                                if hasattr(channel, "name")
                                else "Discord Deferral Channel"
                            ),
                            is_active=True,
                            created_at=(
                                channel.created_at.isoformat()
                                if hasattr(channel, "created_at") and channel.created_at
                                else None
                            ),
                            last_activity=None,
                            message_count=0,
                        )
                    )

        except Exception as e:
            logger.error(f"Error getting active channels: {e}", exc_info=True)

        logger.info(f"[DISCORD] Returning {len(channels)} channels")
        return channels

    async def execute_tool(
        self,
        tool_name: str,
        tool_args: Optional[dict[str, Union[str, int, float, bool, list, dict]]] = None,
        *,
        parameters: Optional[dict[str, Union[str, int, float, bool, list, dict]]] = None,
    ) -> ToolExecutionResult:
        """Execute a tool through the tool handler."""

        # Support both tool_args and parameters for compatibility
        args = tool_args or parameters or {}
        result = await self._tool_handler.execute_tool(tool_name, args)

        # Emit telemetry for tool execution
        await self._emit_telemetry(
            "discord.tool.executed",
            1.0,
            {
                "adapter_type": "discord",
                "tool_name": tool_name,
                "success": str(result.success),
                "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            },
        )

        return result

    def list_tools(self) -> List[str]:
        """List available tools through the tool handler."""
        return self._tool_handler.get_available_tools()

    def list_permissions(self, wa_id: str) -> List[WAPermission]:
        """List all permissions for a Discord user."""
        permissions: List[WAPermission] = []

        try:
            if not self._channel_manager.client:
                return permissions

            # Check all guilds
            for guild in self._channel_manager.client.guilds:
                member = guild.get_member(int(wa_id))
                if member:
                    for role in member.roles:
                        if role.name.upper() in ["AUTHORITY", "OBSERVER"]:
                            permissions.append(
                                WAPermission(
                                    permission_id=f"discord_{guild.id}_{role.name.upper()}_{wa_id}",
                                    wa_id=wa_id,
                                    permission_type="role",
                                    permission_name=role.name.upper(),
                                    resource=f"guild:{guild.id}",
                                    granted_at=self._time_service.now() if self._time_service else datetime.now(),
                                    granted_by="discord_adapter",
                                )
                            )

            return permissions
        except Exception as e:
            logger.error(f"Failed to list permissions: {e}")
            return []

    async def send_deferral(self, deferral: DeferralRequest) -> str:
        """Send a decision deferral to human WAs - returns deferral ID."""
        deferral_channel_id = self.discord_config.deferral_channel_id
        if not deferral_channel_id:
            logger.error("DiscordAdapter: Deferral channel not configured.")
            logger.error(f"  - Current config: {self.discord_config}")
            logger.error(f"  - Monitored channels: {self.discord_config.monitored_channel_ids}")
            logger.error(f"  - Admin user IDs: {self.discord_config.admin_user_ids}")
            raise RuntimeError("Deferral channel not configured.")

        logger.info(f"Sending deferral to channel {deferral_channel_id}")
        logger.info(f"  - Task ID: {deferral.task_id}")
        logger.info(f"  - Thought ID: {deferral.thought_id}")
        logger.info(f"  - Reason: {deferral.reason}")

        time_service = self._time_service
        if time_service is None:
            logger.error("Time service not initialized")
            raise RuntimeError("Time service not initialized")
        start_time = time_service.now()

        try:
            correlation_id = str(uuid.uuid4())

            # Create deferral data for embed formatter
            deferral_data = DiscordGuidanceData(
                deferral_id=correlation_id,
                task_id=deferral.task_id,
                thought_id=deferral.thought_id,
                reason=deferral.reason,
                defer_until=deferral.defer_until,
                context=deferral.context or {},
            )

            # Create rich embed
            embed = self._embed_formatter.format_deferral_request(deferral_data)

            # Send the embed with a plain text notification
            message_text = (
                f"**DEFERRAL REQUEST (ID: {correlation_id})**\n"
                f"Task ID: {deferral.task_id}\n"
                f"Thought ID: {deferral.thought_id}\n"
                f"Reason: {deferral.reason}"
            )
            if deferral.defer_until:
                message_text += f"\nDefer Until: {deferral.defer_until}"
            if deferral.context:
                context_str = ", ".join(f"{k}: {v}" for k, v in deferral.context.items())
                message_text += f"\nContext: {context_str}"

            # Get the Discord client from channel manager
            client = self._channel_manager.client
            if not client:
                raise RuntimeError("Discord client not available")

            # Get the channel
            channel = client.get_channel(int(deferral_channel_id))
            if not channel:
                raise RuntimeError(f"Deferral channel {deferral_channel_id} not found")

            # Check if channel supports sending messages
            if not isinstance(
                channel,
                (discord.TextChannel, discord.DMChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel),
            ):
                raise RuntimeError(f"Channel {deferral_channel_id} does not support sending messages")

            # Split the message if needed using the message handler's method
            chunks = self._message_handler._split_message(message_text, max_length=1900)

            # Send the first chunk with the embed
            if chunks:
                sent_message = await channel.send(content=chunks[0], embed=embed)

                # Send additional chunks if any (without embed)
                for i in range(1, len(chunks)):
                    continuation = f"*(Continued from deferral {correlation_id})*\n\n{chunks[i]}"
                    await channel.send(content=continuation)
                    await asyncio.sleep(0.5)  # Small delay between messages
            else:
                # Fallback if no chunks
                sent_message = await channel.send(content="**DEFERRAL REQUEST** (content too long)", embed=embed)

            # Add reaction UI for WAs to respond
            await sent_message.add_reaction("✅")  # Approve
            await sent_message.add_reaction("❌")  # Deny
            await sent_message.add_reaction("🔄")  # Request more info

            # Store message ID for tracking responses
            if hasattr(self._reaction_handler, "track_deferral"):
                await self._reaction_handler.track_deferral(
                    message_id=str(sent_message.id),
                    deferral_id=correlation_id,
                    task_id=deferral.task_id,
                    thought_id=deferral.thought_id,
                )

            # Store deferral in memory graph
            if self.bus_manager and self.bus_manager.memory:
                try:
                    deferral_node = DiscordDeferralNode(
                        id=f"discord_deferral/{correlation_id}",
                        scope=GraphScope.LOCAL,
                        attributes=GraphNodeAttributes(created_by="discord_adapter", tags=["discord", "deferral"]),
                        deferral_id=correlation_id,
                        task_id=deferral.task_id,
                        thought_id=deferral.thought_id,
                        reason=deferral.reason,
                        defer_until=deferral.defer_until,
                        channel_id=deferral_channel_id,
                        status="pending",
                        context=deferral.context,
                        updated_at=start_time,
                        updated_by="discord_adapter",
                    )

                    await self.bus_manager.memory.store(
                        node_id=correlation_id,
                        node_type="DISCORD_DEFERRAL",
                        attributes=deferral_node.to_graph_node().attributes,
                        scope="local",
                        handler_name="discord_adapter",
                    )
                except Exception as e:
                    logger.error(f"Failed to store deferral in memory: {e}")

            end_time = time_service.now()
            execution_time_ms = (end_time - start_time).total_seconds() * 1000

            persistence.add_correlation(
                ServiceCorrelation(
                    correlation_id=correlation_id,
                    service_type="discord",
                    handler_name="DiscordAdapter",
                    action_type="send_deferral",
                    request_data=ServiceRequestData(
                        service_type="discord",
                        method_name="send_deferral",
                        channel_id=deferral_channel_id,
                        parameters={
                            "reason": deferral.reason,
                            "task_id": deferral.task_id,
                            "thought_id": deferral.thought_id,
                        },
                        request_timestamp=start_time,
                    ),
                    response_data=ServiceResponseData(
                        success=True,
                        result_summary=f"Deferral sent to channel {deferral_channel_id}",
                        execution_time_ms=execution_time_ms,
                        response_timestamp=end_time,
                    ),
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=start_time,
                    updated_at=end_time,
                    timestamp=start_time,
                ),
                time_service,
            )

            return correlation_id
        except Exception as e:
            logger.exception(f"Failed to send deferral to Discord: {e}")
            raise

    # Legacy method for backward compatibility
    async def send_deferral_legacy(self, context: DeferralContext) -> bool:
        """Send a deferral report to the configured deferral channel (legacy)."""
        try:
            # Convert DeferralContext to DeferralRequest
            request = DeferralRequest(
                task_id=context.task_id,
                thought_id=context.thought_id,
                reason=context.reason,
                defer_until=context.defer_until
                or (self._time_service.now() if self._time_service else datetime.now()) + timedelta(hours=1),
                context=context.metadata,
            )
            await self.send_deferral(request)
            return True
        except Exception:
            return False

    def get_capabilities(self) -> ServiceCapabilities:
        """Return service capabilities in the proper format."""
        return ServiceCapabilities(
            service_name="DiscordAdapter",
            actions=[
                # Communication capabilities
                "send_message",
                "fetch_messages",
                # Tool capabilities
                "execute_tool",
                "list_tools",
                # WiseAuthority capabilities
                "fetch_guidance",
                "send_deferral",
                "check_authorization",
                "request_approval",
                "get_guidance",
                "get_pending_deferrals",
                "resolve_deferral",
                "grant_permission",
                "revoke_permission",
                "list_permissions",
            ],
            version="1.0.0",
            dependencies=["discord.py"],
        )

    def get_status(self) -> ServiceStatus:
        """Return current service status."""
        try:
            # Check if client is ready without blocking
            is_healthy = self._channel_manager.client is not None and not self._channel_manager.client.is_closed()
        except Exception as e:
            logger.warning(
                f"Discord health check failed: {type(e).__name__}: {str(e)} - Client state unknown, latency check failed"
            )
            is_healthy = False

        # Get actual latency from Discord client
        latency_ms = 0.0
        if self._message_handler and self._message_handler.client:
            # Discord.py provides latency in seconds, convert to milliseconds
            latency_seconds = self._message_handler.client.latency
            if latency_seconds is not None and latency_seconds >= 0:
                latency_ms = latency_seconds * 1000.0

        return ServiceStatus(
            service_name="DiscordAdapter",
            service_type="adapter",
            is_healthy=is_healthy,
            uptime_seconds=(
                float((self._time_service.now() - self._start_time).total_seconds())
                if self._start_time and self._time_service
                else 0.0
            ),
            metrics={"latency": latency_ms},
        )

    async def _send_output(self, channel_id: str, content: str) -> None:
        """Send output to a Discord channel with retry logic"""
        await self._retry_discord_operation(
            self._message_handler.send_message_to_channel,
            channel_id,
            content,
            operation_name="send_output",
            config_key="discord_api",
        )
        # result contains the return value from send_message_to_channel

    async def _on_message(self, message: discord.Message) -> None:
        """Handle incoming Discord messages."""
        await self._channel_manager.on_message(message)

        # Emit telemetry for message received
        await self._emit_telemetry(
            "discord.message.received",
            1.0,
            {"adapter_type": "discord", "channel_id": str(message.channel.id), "author_id": str(message.author.id)},
        )

        # Audit log the message received
        await self._audit_logger.log_message_received(
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
            author_name=message.author.name,
            message_id=str(message.id),
        )

    def attach_to_client(self, client: discord.Client) -> None:
        """Attach message handlers to a Discord client."""
        logger.info("DiscordAdapter.attach_to_client: Attaching to Discord client")
        self._channel_manager.set_client(client)
        self._message_handler.set_client(client)
        self._guidance_handler.set_client(client)
        self._reaction_handler.set_client(client)
        self._tool_handler.set_client(client)

        # Note: Event handlers are now managed by CIRISDiscordClient
        self._connection_manager.set_client(client)
        logger.info("DiscordAdapter.attach_to_client: All handlers attached")

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle raw reaction add events.

        Args:
            payload: Discord reaction event payload
        """
        # Don't process reactions from bots
        if payload.member and payload.member.bot:
            return

        await self._reaction_handler.handle_reaction(payload)

    async def start(self) -> None:
        """
        Start the Discord adapter.
        Note: This doesn't start the Discord client connection - that's handled by the runtime.
        """
        try:
            # Capture start time
            self._start_time = datetime.now()

            # Emit telemetry for adapter start
            await self._emit_telemetry("discord.adapter.starting", 1.0, {"adapter_type": "discord"})

            await super().start()

            # Set up audit service if available
            if self.bus_manager and hasattr(self.bus_manager, "audit"):
                # Try to get audit service from bus manager
                try:
                    audit_service = self.bus_manager.audit
                    if audit_service:
                        self._audit_logger.set_audit_service(audit_service)
                        logger.info("Discord adapter connected to audit service")
                except Exception as e:
                    logger.debug(f"Could not connect to audit service: {e}")

            client = self._channel_manager.client
            if client:
                logger.info("Discord adapter started with existing client (not yet connected)")
            else:
                logger.warning("Discord adapter started without client - attach_to_client() must be called separately")

            logger.info("Discord adapter started successfully")

            # Emit telemetry for successful start
            await self._emit_telemetry(
                "discord.adapter.started", 1.0, {"adapter_type": "discord", "has_client": str(client is not None)}
            )

            # Set up connection monitoring
            if client:
                logger.info("Discord adapter setting up connection monitoring")
                await self._connection_manager.connect()
                logger.info("Discord adapter will wait for platform to establish connection")
            else:
                logger.warning("No Discord client attached - connection will be established later")

        except Exception as e:
            logger.exception(f"Failed to start Discord adapter: {e}")
            raise

    async def wait_until_ready(self, timeout: float = 30.0) -> bool:
        """
        Wait until the Discord client is ready or timeout.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if ready, False if timeout
        """
        logger.info(f"Waiting for Discord adapter to be ready (timeout: {timeout}s)...")
        return await self._connection_manager.wait_until_ready(timeout)

    async def stop(self) -> None:
        """
        Stop the Discord adapter and clean up resources.
        """
        try:
            logger.info("Stopping Discord adapter...")

            # Emit telemetry for adapter stopping
            await self._emit_telemetry("discord.adapter.stopping", 1.0, {"adapter_type": "discord"})

            self._tool_handler.clear_tool_results()

            # Disconnect gracefully
            await self._connection_manager.disconnect()

            await super().stop()

            logger.info("Discord adapter stopped successfully")

            # Emit telemetry for successful stop
            await self._emit_telemetry("discord.adapter.stopped", 1.0, {"adapter_type": "discord"})
        except AttributeError as e:
            # Handle the '_MissingSentinel' error that occurs during shutdown
            if "'_MissingSentinel' object has no attribute 'create_task'" in str(e):
                logger.debug("Discord client already shut down, ignoring event loop error")
            else:
                logger.error(f"AttributeError stopping Discord adapter: {e}")
        except Exception as e:
            logger.error(f"Error stopping Discord adapter: {e}")

    async def is_healthy(self) -> bool:
        """Check if the Discord adapter is healthy"""
        try:
            result = self._connection_manager.is_connected()
            logger.debug(f"DiscordAdapter.is_healthy: connection_manager.is_connected() returned {result}")
            return result
        except Exception as e:
            logger.warning(f"DiscordAdapter.is_healthy: Exception checking health: {e}")
            return False

    def get_service_type(self) -> ServiceType:
        """Get the type of this service."""
        return ServiceType.ADAPTER

    def get_home_channel_id(self) -> Optional[str]:
        """Get the home channel ID for this Discord adapter.

        Returns:
            The formatted channel ID (e.g., 'discord_123456789')
            or None if no home channel is configured.
        """
        # Get the raw channel ID from config
        raw_channel_id = self.discord_config.get_home_channel_id()
        logger.debug(f"DiscordAdapter.get_home_channel_id: raw_channel_id = {raw_channel_id}")
        if not raw_channel_id:
            logger.warning("DiscordAdapter: No home channel ID found in config")
            return None

        # Format it with discord_ prefix
        # The guild ID will be added by the platform when available
        formatted_id = self.discord_config.get_formatted_startup_channel_id()
        logger.debug(f"DiscordAdapter.get_home_channel_id: formatted_id = {formatted_id}")
        return formatted_id

    def get_channel_list(self) -> List[ChannelContext]:
        """
        Get list of available Discord channels.

        Returns:
            List of ChannelContext objects for Discord channels.
        """
        channels: List[ChannelContext] = []

        # Add configured channels from config
        if self.discord_config:
            # Add monitored channels
            for channel_id in self.discord_config.monitored_channel_ids:
                # Determine allowed actions based on channel type
                allowed_actions = ["speak", "observe", "memorize", "recall"]
                if channel_id == self.discord_config.home_channel_id:
                    allowed_actions.append("wa_defer")  # Home channel can defer to WA
                if channel_id == self.discord_config.deferral_channel_id:
                    allowed_actions.append("wa_approve")  # Deferral channel for WA approvals

                channel_name = None
                # If bot is connected, get actual channel name
                if self._channel_manager and self._channel_manager.client and self._channel_manager.client.is_ready():
                    try:
                        discord_channel = self._channel_manager.client.get_channel(int(channel_id))
                        if discord_channel and hasattr(discord_channel, "name"):
                            channel_name = f"#{discord_channel.name}"
                    except Exception as e:
                        logger.debug(f"Could not get Discord channel info for {channel_id}: {e}")

                channel = ChannelContext(
                    channel_id=channel_id,
                    channel_type="discord",
                    created_at=datetime.now(),  # We don't have creation time, use now
                    channel_name=channel_name,
                    is_private=False,  # Discord channels are generally not private
                    participants=[],  # Could be populated from guild members if needed
                    is_active=True,
                    last_activity=None,  # Could be populated from correlations
                    message_count=0,  # Could be populated from correlations
                    allowed_actions=allowed_actions,
                    moderation_level="standard",
                )
                channels.append(channel)

            # Add deferral channel if not already in monitored
            if (
                self.discord_config.deferral_channel_id
                and self.discord_config.deferral_channel_id not in self.discord_config.monitored_channel_ids
            ):
                channel_name = None
                if self._channel_manager and self._channel_manager.client and self._channel_manager.client.is_ready():
                    try:
                        discord_channel = self._channel_manager.client.get_channel(
                            int(self.discord_config.deferral_channel_id)
                        )
                        if discord_channel and hasattr(discord_channel, "name"):
                            channel_name = f"#{discord_channel.name}"
                    except Exception as e:
                        logger.debug(f"Could not get Discord channel info for deferral channel: {e}")

                channels.append(
                    ChannelContext(
                        channel_id=self.discord_config.deferral_channel_id,
                        channel_type="discord",
                        created_at=datetime.now(),
                        channel_name=channel_name,
                        is_private=False,
                        participants=[],
                        is_active=True,
                        last_activity=None,
                        message_count=0,
                        allowed_actions=["wa_approve", "speak", "observe"],  # Deferral channel
                        moderation_level="strict",  # Higher moderation for deferral channel
                    )
                )

        return channels

    def _setup_connection_callbacks(self) -> None:
        """Set up callbacks for connection events."""

        async def on_connected() -> None:
            """Handle successful connection."""
            try:
                # Log connection event
                if self._connection_manager.client:
                    guild_count = len(self._connection_manager.client.guilds)
                    user_count = len(self._connection_manager.client.users)

                    await self._audit_logger.log_connection_event(
                        event_type="connected", guild_count=guild_count, user_count=user_count
                    )

                    await self._emit_telemetry(
                        "discord.connection.established",
                        1.0,
                        {"adapter_type": "discord", "guilds": str(guild_count), "users": str(user_count)},
                    )
            except Exception as e:
                logger.error(f"Error in connection callback: {e}")

        async def on_disconnected(error: Optional[Exception]) -> None:
            """Handle disconnection."""
            try:
                await self._audit_logger.log_connection_event(
                    event_type="disconnected", guild_count=0, user_count=0, error=str(error) if error else None
                )

                await self._emit_telemetry(
                    "discord.connection.lost",
                    1.0,
                    {"adapter_type": "discord", "error": str(error) if error else "clean_disconnect"},
                )
            except Exception as e:
                logger.error(f"Error in disconnection callback: {e}")

        async def on_reconnecting(attempt: int) -> None:
            """Handle reconnection attempts."""
            try:
                await self._emit_telemetry(
                    "discord.connection.reconnecting",
                    1.0,
                    {
                        "adapter_type": "discord",
                        "attempt": str(attempt),
                        "max_attempts": str(self._connection_manager.max_reconnect_attempts),
                    },
                )
            except Exception as e:
                logger.error(f"Error in reconnecting callback: {e}")

        async def on_failed(reason: str) -> None:
            """Handle connection failure."""
            try:
                await self._audit_logger.log_connection_event(
                    event_type="failed", guild_count=0, user_count=0, error=reason
                )

                await self._emit_telemetry(
                    "discord.connection.failed", 1.0, {"adapter_type": "discord", "reason": reason}
                )
            except Exception as e:
                logger.error(f"Error in failure callback: {e}")

        # Set callbacks
        self._connection_manager.on_connected = on_connected
        self._connection_manager.on_disconnected = on_disconnected
        self._connection_manager.on_reconnecting = on_reconnecting
        self._connection_manager.on_failed = on_failed

    @property
    def _client(self) -> Optional[discord.Client]:
        """Get the Discord client instance."""
        return self._channel_manager.client

    def get_services_to_register(self) -> List["AdapterServiceRegistration"]:
        """Register Discord services for communication, tools, and wise authority."""
        from ciris_engine.logic.registries.base import Priority
        from ciris_engine.schemas.adapters.registration import AdapterServiceRegistration
        from ciris_engine.schemas.runtime.enums import ServiceType

        registrations = [
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self,  # The Discord adapter itself is the provider
                priority=Priority.HIGH,
                handlers=["SpeakHandler", "ObserveHandler"],  # Specific handlers
                capabilities=["send_message", "fetch_messages"],
            ),
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self,  # Discord adapter handles tools too
                priority=Priority.NORMAL,  # Lower priority than CLI for tools
                handlers=["ToolHandler"],
                capabilities=["execute_tool", "get_available_tools", "get_tool_result", "validate_parameters"],
            ),
            AdapterServiceRegistration(
                service_type=ServiceType.WISE_AUTHORITY,
                provider=self,  # Discord adapter can handle WA
                priority=Priority.HIGH,
                handlers=["DeferralHandler", "GuidanceHandler"],
                capabilities=[
                    "send_deferral",
                    "check_deferral",
                    "fetch_guidance",
                    "request_permission",
                    "check_permission",
                    "list_permissions",
                ],
            ),
        ]

        return registrations
