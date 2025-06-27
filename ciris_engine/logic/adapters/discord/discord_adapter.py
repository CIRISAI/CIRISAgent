import discord
from discord.errors import HTTPException, ConnectionClosed
import logging
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Awaitable, Callable, List, Optional, TYPE_CHECKING, Any, Dict

from ciris_engine.schemas.runtime.messages import FetchedMessage, IncomingMessage
from ciris_engine.protocols.services import CommunicationService, WiseAuthorityService, ToolService
from ciris_engine.schemas.telemetry.core import (
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
)
from ciris_engine.schemas.services.context import GuidanceContext, DeferralContext
from ciris_engine.schemas.runtime.tools import ToolInfo, ToolParameterSchema, ToolExecutionResult
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.authority_core import (
    DeferralRequest, DeferralResponse, GuidanceRequest, GuidanceResponse,
    DeferralApprovalContext, WAPermission
)
from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.discord_nodes import DiscordDeferralNode, DiscordApprovalNode, DiscordWANode
from ciris_engine.logic import persistence
from ciris_engine.logic.adapters.base import Service

from .discord_message_handler import DiscordMessageHandler
from .discord_guidance_handler import DiscordGuidanceHandler
from .discord_tool_handler import DiscordToolHandler
from .discord_channel_manager import DiscordChannelManager
from .discord_reaction_handler import DiscordReactionHandler, ApprovalRequest, ApprovalStatus
from .discord_audit import DiscordAuditLogger
from .discord_connection_manager import DiscordConnectionManager, ConnectionState
from .discord_error_handler import DiscordErrorHandler
from .discord_rate_limiter import DiscordRateLimiter
from .discord_embed_formatter import DiscordEmbedFormatter, EmbedType
from .discord_access_control import DiscordAccessControl
from .config import DiscordAdapterConfig

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)

class DiscordAdapter(Service, CommunicationService, WiseAuthorityService, ToolService):
    """
    Discord adapter implementing CommunicationService, WiseAuthorityService, and ToolService protocols.
    Coordinates specialized handlers for different aspects of Discord functionality.
    """
    def __init__(self, token: str,
                 tool_registry: Optional[Any] = None, bot: Optional[discord.Client] = None,
                 on_message: Optional[Callable[[IncomingMessage], Awaitable[None]]] = None,
                 time_service: Optional["TimeServiceProtocol"] = None,
                 bus_manager: Optional[Any] = None,
                 config: Optional[DiscordAdapterConfig] = None) -> None:
        retry_config = {
            "retry": {
                "global": {
                    "max_retries": 3,
                    "base_delay": 2.0,
                    "max_delay": 30.0,
                },
                "discord_api": {
                    "retryable_exceptions": (HTTPException, ConnectionClosed, asyncio.TimeoutError),
                }
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
        self._guidance_handler = DiscordGuidanceHandler(bot, self._time_service, 
                                                       self.bus_manager.memory if self.bus_manager else None)
        self._tool_handler = DiscordToolHandler(tool_registry, bot, self._time_service)
        self._reaction_handler = DiscordReactionHandler(bot, self._time_service)
        self._audit_logger = DiscordAuditLogger(self._time_service)
        self._connection_manager = DiscordConnectionManager(token, bot, self._time_service)
        self._error_handler = DiscordErrorHandler()
        self._rate_limiter = DiscordRateLimiter()
        self._embed_formatter = DiscordEmbedFormatter()
        self._access_control = DiscordAccessControl(bot)
        
        # Set up connection callbacks
        self._setup_connection_callbacks()
    
    async def _retry_discord_operation(self, operation: Callable, *args, operation_name: str, config_key: str = "discord_api", **kwargs):
        """Wrapper for retry_with_backoff that handles Discord-specific configuration."""
        # Apply rate limiting before the operation
        endpoint = kwargs.get('endpoint', operation_name)
        await self._rate_limiter.acquire(endpoint)
        
        try:
            # Get retry config from base class config (which is a dict)
            retry_cfg = self.config.get("retry", {}).get(config_key, {}) if hasattr(self, 'config') and isinstance(self.config, dict) else {}
            result = await self.retry_with_backoff(
                operation,
                *args,
                max_retries=retry_cfg.get("max_retries", 3),
                base_delay=retry_cfg.get("base_delay", 2.0),
                max_delay=retry_cfg.get("max_delay", 30.0),
                retryable_exceptions=retry_cfg.get("retryable_exceptions", (HTTPException, ConnectionClosed, asyncio.TimeoutError)),
                **kwargs
            )
            return result
        except Exception as e:
            # Handle errors with the error handler
            if isinstance(e, (HTTPException, ConnectionClosed)):
                error_info = await self._error_handler.handle_channel_error(
                    kwargs.get('channel_id', 'unknown'),
                    e,
                    operation_name
                )
                # Re-raise if not retryable
                if not error_info.get('can_retry', False):
                    raise
            raise

    async def _emit_telemetry(self, metric_name: str, value: float = 1.0, tags: Optional[dict] = None) -> None:
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
                metric_name=metric_name,
                value=value,
                tags=string_tags,
                scope="local",
                handler_name="adapter.discord"
            )
        except Exception as e:
            logger.debug(f"Failed to emit telemetry {metric_name}: {e}")

    async def send_message(self, channel_id: str, content: str) -> bool:
        """Implementation of CommunicationService.send_message"""
        # Check if Discord client is connected before attempting to send
        if not self._client or not self._connection_manager.is_connected():
            logger.warning(f"Discord adapter not connected, cannot send message to channel {channel_id}")
            return False
            
        correlation_id = str(uuid.uuid4())
        start_time = self._time_service.now()
        
        try:
            result = await self._retry_discord_operation(
                self._message_handler.send_message_to_channel,
                channel_id, content,
                operation_name="send_message",
                config_key="discord_api"
            )
            
            end_time = self._time_service.now()
            execution_time_ms = (end_time - start_time).total_seconds() * 1000
            
            # result contains the return value from send_message_to_channel
            persistence.add_correlation(
                ServiceCorrelation(
                    correlation_id=correlation_id,
                    service_type="discord",
                    handler_name="DiscordAdapter",
                    action_type="send_message",
                    request_data=ServiceRequestData(
                        service_type="discord",
                        method_name="send_message",
                        channel_id=channel_id,
                        parameters={"content": content},
                        request_timestamp=start_time
                    ),
                    response_data=ServiceResponseData(
                        success=True,
                        result_summary="Message sent successfully",
                        execution_time_ms=execution_time_ms,
                        response_timestamp=end_time
                    ),
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=start_time,
                    updated_at=end_time,
                    timestamp=start_time
                ),
                self._time_service
            )
            
            # Emit telemetry for message sent
            await self._emit_telemetry("discord.message.sent", {
                "adapter_type": "discord",
                "channel_id": channel_id,
                "execution_time": execution_time_ms
            })
            
            # Audit log the operation
            await self._audit_logger.log_message_sent(
                channel_id=channel_id,
                author_id="discord_adapter",
                message_content=content,
                correlation_id=correlation_id
            )
            
            return True
        except Exception as e:
            # Handle message errors
            error_info = await self._error_handler.handle_message_error(
                e, content, channel_id
            )
            logger.error(f"Failed to send message via Discord: {error_info}")
            return False

    async def fetch_messages(self, channel_id: str, limit: int = 100) -> List[FetchedMessage]:
        """Implementation of CommunicationService.fetch_messages"""
        # Early return if no client is available - no point in retrying
        if not self._channel_manager.client:
            logger.debug(f"Discord client not initialized, cannot fetch messages from channel {channel_id}")
            return []
            
        try:
            return await self._retry_discord_operation(
                self._message_handler.fetch_messages_from_channel,  # type: ignore[arg-type]
                channel_id, limit,
                operation_name="fetch_messages",
                config_key="discord_api"
            )
        except Exception as e:
            logger.exception(f"Failed to fetch messages from Discord channel {channel_id}: {e}")
            return []

    # --- WiseAuthorityService ---
    async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]:
        """Send a guidance request to the configured guidance channel and wait for a response."""
        deferral_channel_id = self.discord_config.deferral_channel_id
        if not deferral_channel_id:
            logger.error("DiscordAdapter: Guidance channel not configured.")
            raise RuntimeError("Guidance channel not configured.")

        start_time = self._time_service.now()
        
        try:
            correlation_id = str(uuid.uuid4())
            guidance_result = await self._retry_discord_operation(
                self._guidance_handler.fetch_guidance_from_channel,
                deferral_channel_id, context.model_dump(),
                operation_name="fetch_guidance",
                config_key="discord_api"
            )
            # Type assertion: retry_with_backoff should return dict from fetch_guidance_from_channel
            guidance: dict = guidance_result  # type: ignore
            
            end_time = self._time_service.now()
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
                        request_timestamp=start_time
                    ),
                    response_data=ServiceResponseData(
                        success=True,
                        result_summary=f"Guidance received: {guidance.get('guidance', 'None')}",
                        execution_time_ms=execution_time_ms,
                        response_timestamp=end_time
                    ),
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=start_time,
                    updated_at=end_time,
                    timestamp=start_time
                ),
                self._time_service
            )
            guidance_text = guidance.get("guidance")
            
            # Audit log the guidance request
            await self._audit_logger.log_guidance_request(
                channel_id=deferral_channel_id,
                requester_id="discord_adapter",
                context=context.model_dump(),
                guidance_received=guidance_text
            )
            
            return guidance_text
        except Exception as e:
            logger.exception(f"Failed to fetch guidance from Discord: {e}")
            raise
    
    async def check_authorization(self, wa_id: str, action: str, resource: Optional[str] = None) -> bool:
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
            embed = self._embed_formatter.format_approval_request(
                action,
                context.model_dump()
            )
            
            # Get channel for sending embed
            channel = await self._channel_manager.resolve_channel(deferral_channel_id)
            if not channel:
                logger.error(f"Could not resolve deferral channel {deferral_channel_id}")
                return False
            
            # Send embed message
            sent_message = await channel.send(embed=embed)
            
            # Create approval result container
            approval_result = None
            
            async def handle_approval(approval: ApprovalRequest):
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
                    "requester_id": context.requester_id
                },
                timeout_seconds=300  # 5 minute timeout
            )
            
            # Add reactions
            await sent_message.add_reaction("✅")
            await sent_message.add_reaction("❌")
            
            # Register with reaction handler
            self._reaction_handler._pending_approvals[sent_message.id] = approval_request
            self._reaction_handler._approval_callbacks[sent_message.id] = handle_approval
            
            # Schedule timeout
            asyncio.create_task(self._reaction_handler._handle_timeout(approval_request))
            
            if not approval_request:
                return False
            
            # Wait for approval resolution (up to timeout)
            max_wait = approval_request.timeout_seconds + 5
            start_time = self._time_service.now()
            
            while approval_result is None:
                await asyncio.sleep(0.5)
                elapsed = (self._time_service.now() - start_time).total_seconds()
                if elapsed > max_wait:
                    logger.error("Approval request timed out")
                    return False
            
            # Store approval request in memory
            if approval_result and self.bus_manager and self.bus_manager.memory:
                try:
                    approval_node = DiscordApprovalNode(
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
                        created_at=self._time_service.now(),
                        updated_at=self._time_service.now(),
                        created_by="discord_adapter",
                        updated_by="discord_adapter"
                    )
                    
                    await self.bus_manager.memory.store(
                        node_id=str(approval_request.message_id),
                        node_type="DISCORD_APPROVAL",
                        attributes=approval_node.to_graph_node().attributes,
                        scope="local",
                        handler_name="discord_adapter"
                    )
                except Exception as e:
                    logger.error(f"Failed to store approval in memory: {e}")
            
            # Audit log the approval request
            await self._audit_logger.log_approval_request(
                channel_id=deferral_channel_id,
                requester_id=context.requester_id,
                action=action,
                approval_status=approval_result.status.value,
                approver_id=approval_result.resolver_id
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
            domain_context={"urgency": request.urgency} if request.urgency else {}
        )
        
        guidance = await self.fetch_guidance(context)
        
        return GuidanceResponse(
            selected_option=guidance if guidance in request.options else None,
            custom_guidance=guidance if guidance not in request.options else None,
            reasoning="Guidance provided by Discord WA channel",
            wa_id="discord_wa",
            signature=f"discord_{uuid.uuid4().hex[:8]}"
        )
    
    async def get_pending_deferrals(self, wa_id: Optional[str] = None) -> List[PendingDeferral]:
        """Get pending deferrals from the deferral channel."""
        if not self.bus_manager or not self.bus_manager.memory:
            logger.warning("No memory bus available for deferral tracking")
            return []
        
        try:
            # Query memory for pending deferrals
            query = {
                "node_type": "DISCORD_DEFERRAL",
                "status": "pending"
            }
            
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
                    attrs = node.attributes.model_dump() if hasattr(node.attributes, 'model_dump') else {}
                
                pending.append(PendingDeferral(
                    deferral_id=attrs.get('deferral_id', node.id),
                    task_id=attrs.get('task_id', ''),
                    thought_id=attrs.get('thought_id', ''),
                    reason=attrs.get('reason', ''),
                    created_at=attrs.get('created_at', self._time_service.now()),
                    deferred_by=attrs.get('created_by', 'discord_agent'),
                    channel_id=attrs.get('channel_id'),
                    priority=attrs.get('priority', 'normal')
                ))
            
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
            message = f"**DEFERRAL RESOLVED**\n"
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
                        guild_id=str(guild.id)
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
                            guild_id=str(guild.id)
                        )
                        
                        return True
                        
            return False
        except Exception as e:
            logger.exception(f"Failed to revoke permission: {e}")
            return False
    
    async def list_permissions(self, wa_id: str) -> List[WAPermission]:
        """List all permissions for a Discord user."""
        permissions = []
        
        try:
            if not self._channel_manager.client:
                return permissions
                
            # Check all guilds
            for guild in self._channel_manager.client.guilds:
                member = guild.get_member(int(wa_id))
                if member:
                    for role in member.roles:
                        if role.name.upper() in ["AUTHORITY", "OBSERVER"]:
                            permissions.append(WAPermission(
                                wa_id=wa_id,
                                permission=role.name.upper(),
                                resource=f"guild:{guild.id}",
                                granted_at=self._time_service.now(),
                                granted_by="discord_adapter"
                            ))
                            
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
        
        start_time = self._time_service.now()
        
        try:
            correlation_id = str(uuid.uuid4())
            
            # Create deferral data for embed formatter
            deferral_data = {
                "deferral_id": correlation_id,
                "task_id": deferral.task_id,
                "thought_id": deferral.thought_id,
                "reason": deferral.reason,
                "defer_until": deferral.defer_until,
                "context": deferral.context
            }
            
            # Create rich embed
            embed = self._embed_formatter.format_deferral_request(deferral_data)
            
            # Send the embed with a plain text notification
            message_text = (
                f"@here **DEFERRAL REQUEST (ID: {correlation_id})**\n"
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
            
            # Send message with embed
            sent_message = await channel.send(content=message_text, embed=embed)
            
            # Add reaction UI for WAs to respond
            await sent_message.add_reaction("✅")  # Approve
            await sent_message.add_reaction("❌")  # Deny
            await sent_message.add_reaction("🔄")  # Request more info
            
            # Store message ID for tracking responses
            if hasattr(self._reaction_handler, 'track_deferral'):
                await self._reaction_handler.track_deferral(
                    message_id=str(sent_message.id),
                    deferral_id=correlation_id,
                    task_id=deferral.task_id,
                    thought_id=deferral.thought_id
                )
            
            # Store deferral in memory graph
            if self.bus_manager and self.bus_manager.memory:
                try:
                    deferral_node = DiscordDeferralNode(
                        deferral_id=correlation_id,
                        task_id=deferral.task_id,
                        thought_id=deferral.thought_id,
                        reason=deferral.reason,
                        defer_until=deferral.defer_until,
                        channel_id=deferral_channel_id,
                        status="pending",
                        context=deferral.context,
                        created_at=start_time,
                        updated_at=start_time,
                        created_by="discord_adapter",
                        updated_by="discord_adapter"
                    )
                    
                    await self.bus_manager.memory.store(
                        node_id=correlation_id,
                        node_type="DISCORD_DEFERRAL",
                        attributes=deferral_node.to_graph_node().attributes,
                        scope="local",
                        handler_name="discord_adapter"
                    )
                except Exception as e:
                    logger.error(f"Failed to store deferral in memory: {e}")
            
            end_time = self._time_service.now()
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
                        parameters={"reason": deferral.reason, "task_id": deferral.task_id, "thought_id": deferral.thought_id},
                        request_timestamp=start_time
                    ),
                    response_data=ServiceResponseData(
                        success=True,
                        result_summary=f"Deferral sent to channel {deferral_channel_id}",
                        execution_time_ms=execution_time_ms,
                        response_timestamp=end_time
                    ),
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=start_time,
                    updated_at=end_time,
                    timestamp=start_time
                ),
                self._time_service
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
                defer_until=context.defer_until or self._time_service.now() + timedelta(hours=1),
                context=context.metadata
            )
            deferral_id = await self.send_deferral(request)
            return True
        except Exception:
            return False

    # --- ToolService ---
    async def execute_tool(self, tool_name: str, parameters: dict) -> ToolExecutionResult:
        """Execute a registered Discord tool via the tool registry and store the result."""
        # The handler returns ToolExecutionResult
        # Note: execute_tool is already async, so we call it directly
        result = await self._tool_handler.execute_tool(tool_name, parameters)
        
        # Emit telemetry for tool execution
        await self._emit_telemetry("discord.tool.executed", {
            "adapter_type": "discord",
            "tool_name": tool_name,
            "success": result.success,
            "execution_time": result.execution_time
        })
        
        # Audit log the tool execution
        await self._audit_logger.log_tool_execution(
            user_id="discord_adapter",
            tool_name=tool_name,
            parameters=parameters,
            success=result.success,
            execution_time_ms=result.execution_time,
            error=result.error if not result.success else None
        )
        
        return result

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool."""
        return await self._tool_handler.get_tool_info(tool_name)
    
    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get detailed information about all available tools."""
        return await self._tool_handler.get_all_tool_info()
    
    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Fetch a tool result by correlation ID from the internal cache."""
        return await self._tool_handler.get_tool_result(correlation_id, int(timeout))
    
    async def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific tool."""
        tool_info = await self.get_tool_info(tool_name)
        if tool_info:
            return {
                "name": tool_info.name,
                "description": tool_info.description,
                "parameters": tool_info.parameters.model_dump() if tool_info.parameters else {}
            }
        return None
    
    async def list_tools(self) -> List[str]:
        """List available tool names (required by ToolServiceProtocol)."""
        return await self.get_available_tools()

    async def get_available_tools(self) -> List[str]:
        """Return names of registered Discord tools."""
        return await self._tool_handler.get_available_tools()

    async def validate_parameters(self, tool_name: str, parameters: dict) -> bool:
        """Basic parameter validation using tool registry schemas."""
        return await self._tool_handler.validate_tool_parameters(tool_name, parameters)

    def get_capabilities(self) -> ServiceCapabilities:
        """Return service capabilities in the proper format."""
        return ServiceCapabilities(
            service_name="DiscordAdapter",
            actions=[
                # Communication capabilities
                "send_message", "fetch_messages",
                # WiseAuthority capabilities
                "fetch_guidance", "send_deferral", "check_authorization",
                "request_approval", "get_guidance", "get_pending_deferrals",
                "resolve_deferral", "grant_permission", "revoke_permission",
                "list_permissions",
                # Tool capabilities
                "execute_tool", "get_available_tools", "get_tool_result",
                "validate_parameters", "get_tool_info", "get_all_tool_info",
                "get_tool_schema", "list_tools"
            ],
            version="1.0.0",
            dependencies=["discord.py"]
        )
    
    def get_status(self) -> ServiceStatus:
        """Return current service status."""
        try:
            # Check if client is ready without blocking
            is_healthy = self._channel_manager.client is not None and not self._channel_manager.client.is_closed()
        except:
            is_healthy = False
            
        return ServiceStatus(
            service_name="DiscordAdapter",
            service_type="adapter",
            is_healthy=is_healthy,
            uptime_seconds=3600,  # TODO: Track actual uptime
            metrics={
                "latency": 50  # TODO: Track actual latency
            }
        )

    async def _send_output(self, channel_id: str, content: str) -> None:
        """Send output to a Discord channel with retry logic"""
        result = await self._retry_discord_operation(
            self._message_handler.send_message_to_channel,
            channel_id, content,
            operation_name="send_output",
            config_key="discord_api"
        )
        # result contains the return value from send_message_to_channel

    async def _on_message(self, message: discord.Message) -> None:
        """Handle incoming Discord messages."""
        await self._channel_manager.on_message(message)
        
        # Emit telemetry for message received
        await self._emit_telemetry("discord.message.received", {
            "adapter_type": "discord",
            "channel_id": str(message.channel.id),
            "author_id": str(message.author.id)
        })
        
        # Audit log the message received
        await self._audit_logger.log_message_received(
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
            author_name=message.author.name,
            message_id=str(message.id)
        )

    def attach_to_client(self, client: discord.Client) -> None:
        """Attach message handlers to a Discord client."""
        self._channel_manager.set_client(client)
        self._message_handler.set_client(client)
        self._guidance_handler.set_client(client)
        self._tool_handler.set_client(client)
        self._reaction_handler.set_client(client)
        
        self._channel_manager.attach_to_client(client)
        self._connection_manager.set_client(client)
        
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
            # Emit telemetry for adapter start
            await self._emit_telemetry("discord.adapter.starting", {
                "adapter_type": "discord"
            })
            
            await super().start()
            
            # Set up audit service if available
            if self.bus_manager:
                # Try to get audit service from service registry if available
                try:
                    from ciris_engine.logic.services.identity import ServiceRegistry
                    registry = ServiceRegistry.get_instance()
                    audit_service = registry.get_service("audit")
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
            await self._emit_telemetry("discord.adapter.started", {
                "adapter_type": "discord",
                "has_client": client is not None
            })
            
            # Start connection manager if we have a client
            if client:
                await self._connection_manager.connect()
                
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
            await self._emit_telemetry("discord.adapter.stopping", {
                "adapter_type": "discord"
            })
            
            self._tool_handler.clear_tool_results()
            
            # Disconnect gracefully
            await self._connection_manager.disconnect()
            
            await super().stop()
            
            logger.info("Discord adapter stopped successfully")
            
            # Emit telemetry for successful stop
            await self._emit_telemetry("discord.adapter.stopped", {
                "adapter_type": "discord"
            })
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
            return self._connection_manager.is_connected()
        except Exception:
            return False
    
    def _setup_connection_callbacks(self) -> None:
        """Set up callbacks for connection events."""
        async def on_connected():
            """Handle successful connection."""
            try:
                # Log connection event
                if self._connection_manager.client:
                    guild_count = len(self._connection_manager.client.guilds)
                    user_count = len(self._connection_manager.client.users)
                    
                    await self._audit_logger.log_connection_event(
                        event_type="connected",
                        guild_count=guild_count,
                        user_count=user_count
                    )
                    
                    await self._emit_telemetry("discord.connection.established", {
                        "adapter_type": "discord",
                        "guilds": guild_count,
                        "users": user_count
                    })
            except Exception as e:
                logger.error(f"Error in connection callback: {e}")
        
        async def on_disconnected(error: Optional[Exception]):
            """Handle disconnection."""
            try:
                await self._audit_logger.log_connection_event(
                    event_type="disconnected",
                    guild_count=0,
                    user_count=0,
                    error=str(error) if error else None
                )
                
                await self._emit_telemetry("discord.connection.lost", {
                    "adapter_type": "discord",
                    "error": str(error) if error else "clean_disconnect"
                })
            except Exception as e:
                logger.error(f"Error in disconnection callback: {e}")
        
        async def on_reconnecting(attempt: int):
            """Handle reconnection attempts."""
            try:
                await self._emit_telemetry("discord.connection.reconnecting", {
                    "adapter_type": "discord",
                    "attempt": attempt,
                    "max_attempts": self._connection_manager.max_reconnect_attempts
                })
            except Exception as e:
                logger.error(f"Error in reconnecting callback: {e}")
        
        async def on_failed(reason: str):
            """Handle connection failure."""
            try:
                await self._audit_logger.log_connection_event(
                    event_type="failed",
                    guild_count=0,
                    user_count=0,
                    error=reason
                )
                
                await self._emit_telemetry("discord.connection.failed", {
                    "adapter_type": "discord",
                    "reason": reason
                })
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
    
    def get_services_to_register(self) -> List['AdapterServiceRegistration']:
        """Register Discord services for communication, tools, and wise authority."""
        from ciris_engine.schemas.adapters import AdapterServiceRegistration
        from ciris_engine.schemas.runtime.enums import ServiceType
        from ciris_engine.logic.registries.base import Priority
        
        registrations = [
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self,  # The Discord adapter itself is the provider
                priority=Priority.HIGH,
                handlers=["SpeakHandler", "ObserveHandler"],  # Specific handlers
                capabilities=["send_message", "fetch_messages"]
            ),
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self,  # Discord adapter handles tools too
                priority=Priority.NORMAL,  # Lower priority than CLI for tools
                handlers=["ToolHandler"],
                capabilities=["execute_tool", "get_available_tools", "get_tool_result", "validate_parameters"]
            ),
            AdapterServiceRegistration(
                service_type=ServiceType.WISE_AUTHORITY,
                provider=self,  # Discord adapter can handle WA
                priority=Priority.HIGH,
                handlers=["DeferralHandler", "GuidanceHandler"],
                capabilities=["send_deferral", "check_deferral", "fetch_guidance", "request_permission", "check_permission", "list_permissions"]
            )
        ]
        
        return registrations
