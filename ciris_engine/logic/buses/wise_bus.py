"""
Wise Authority message bus - handles all WA service operations
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from ciris_engine.logic.utils.jsondict_helpers import get_int, get_str
from ciris_engine.protocols.services import WiseAuthorityService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.infrastructure.base import BusMetrics
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority_core import GuidanceRequest, GuidanceResponse
from ciris_engine.schemas.services.context import DeferralContext, GuidanceContext
from ciris_engine.schemas.types import JSONDict

from .base_bus import BaseBus, BusMessage
from .prohibitions import (
    COMMUNITY_MODERATION_CAPABILITIES,
    PROHIBITED_CAPABILITIES,
    ProhibitionSeverity,
    get_capability_category,
    get_prohibition_severity,
)

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

logger = logging.getLogger(__name__)


class WiseBus(BaseBus[WiseAuthorityService]):
    """
    Message bus for all wise authority operations.

    Handles:
    - send_deferral
    - fetch_guidance
    - Comprehensive capability prohibition with tier-based access
    """

    # Import prohibited capabilities from the prohibitions module
    PROHIBITED_CAPABILITIES = PROHIBITED_CAPABILITIES

    def __init__(
        self,
        service_registry: "ServiceRegistry",
        time_service: TimeServiceProtocol,
        telemetry_service: Optional[Any] = None,
    ):
        super().__init__(service_type=ServiceType.WISE_AUTHORITY, service_registry=service_registry)
        self._time_service = time_service
        self._start_time = time_service.now() if time_service else None
        self._agent_tier: Optional[int] = None  # Cached agent tier

        # Metrics tracking
        self._requests_count = 0
        self._deferrals_count = 0
        self._guidance_count = 0

    async def _get_tier_from_config(self) -> Optional[int]:
        """Try to get agent tier from configuration service."""
        try:
            from ciris_engine.schemas.runtime.enums import ServiceType

            config_services = self.service_registry.get_services_by_type(ServiceType.CONFIG)
            if not config_services:
                return None

            config_service = config_services[0]
            if not hasattr(config_service, "get_value"):
                return None

            tier = await config_service.get_value("agent_tier")
            if tier:
                return int(tier)
        except Exception as e:
            logger.debug(f"Could not get tier from config: {e}")
        return None

    async def _get_tier_from_memory(self) -> Optional[int]:
        """Try to get agent tier from memory/identity."""
        try:
            from ciris_engine.schemas.runtime.enums import ServiceType

            memory_services = self.service_registry.get_services_by_type(ServiceType.MEMORY)
            if not memory_services:
                return None

            memory_service = memory_services[0]

            # Try to search for tier information in identity nodes
            if hasattr(memory_service, "search_memories"):
                results = await memory_service.search_memories("agent_tier stewardship tier", scope="identity", limit=5)

                # Check if this is a Tier 4/5 agent
                for result in results:
                    content_str = str(result.content).lower()
                    if any(marker in content_str for marker in ["stewardship", "tier_4", "tier_5"]):
                        return 4  # Default stewardship tier

        except Exception as e:
            logger.debug(f"Could not get tier from memory: {e}")
        return None

    async def get_agent_tier(self) -> int:
        """
        Get the agent's tier level from configuration or identity.

        Tier levels:
        - 1-3: Standard agents (no community moderation)
        - 4-5: Stewardship agents (trusted with community moderation)

        Returns:
            Agent tier level (1-5), defaults to 1 if not found
        """
        if self._agent_tier is not None:
            return self._agent_tier

        # Try to get tier from config service
        tier = await self._get_tier_from_config()
        if tier:
            self._agent_tier = tier
            logger.info(f"Agent tier detected from config: {self._agent_tier}")
            return self._agent_tier

        # Try to get tier from memory/identity
        tier = await self._get_tier_from_memory()
        if tier:
            self._agent_tier = tier
            logger.info(f"Agent identified as Tier {self._agent_tier} (stewardship)")
            return self._agent_tier

        # Default to tier 1 (standard agent)
        self._agent_tier = 1
        logger.info(f"Using default agent tier: {self._agent_tier}")
        return self._agent_tier

    async def send_deferral(self, context: DeferralContext, handler_name: str) -> bool:
        """Send a deferral to ALL wise authority services (broadcast)"""
        # Get ALL services with send_deferral capability
        # Since we want to broadcast to all WA services, we need to get them all
        from ciris_engine.schemas.runtime.enums import ServiceType

        all_wa_services = self.service_registry.get_services_by_type(ServiceType.WISE_AUTHORITY)
        logger.info(f"Found {len(all_wa_services)} total WiseAuthority services")

        # Filter for services with send_deferral capability
        services = []
        for service in all_wa_services:
            logger.debug(f"Checking service {service.__class__.__name__} for send_deferral capability")
            # Check if service has get_capabilities method
            if hasattr(service, "get_capabilities"):
                caps = service.get_capabilities()
                logger.debug(f"Service {service.__class__.__name__} has capabilities: {caps.actions}")
                if "send_deferral" in caps.actions:
                    services.append(service)
                    logger.info(f"Adding service {service.__class__.__name__} to deferral broadcast list")
            else:
                logger.warning(f"Service {service.__class__.__name__} has no get_capabilities method")

        if not services:
            logger.info(f"No wise authority service available for {handler_name}")
            return False

        # Track if any service successfully received the deferral
        any_success = False

        try:
            # Convert DeferralContext to DeferralRequest
            from ciris_engine.schemas.services.authority_core import DeferralRequest

            # Handle defer_until - it may be None
            defer_until = None
            if context.defer_until:
                # If it's already a datetime, use it directly
                if hasattr(context.defer_until, "isoformat"):
                    defer_until = context.defer_until
                else:
                    # Try to parse as string
                    from datetime import datetime

                    try:
                        # Handle both 'Z' and '+00:00' formats
                        defer_str = str(context.defer_until)
                        if defer_str.endswith("Z"):
                            defer_str = defer_str[:-1] + "+00:00"
                        defer_until = datetime.fromisoformat(defer_str)
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"Failed to parse defer_until date '{context.defer_until}': {type(e).__name__}: {str(e)} - Task will be deferred to default time"
                        )
                        defer_until = self._time_service.now()
            else:
                # Default to now + 1 hour if not specified
                from datetime import timedelta

                defer_until = self._time_service.now() + timedelta(hours=1)

            deferral_request = DeferralRequest(
                task_id=context.task_id,
                thought_id=context.thought_id,
                reason=context.reason,
                defer_until=defer_until,
                context=context.metadata,  # Map metadata to context
            )

            # Broadcast to ALL registered WA services
            logger.info(f"Broadcasting deferral to {len(services)} wise authority service(s)")
            for service in services:
                try:
                    result = await service.send_deferral(deferral_request)
                    if result:
                        any_success = True
                        logger.debug(f"Successfully sent deferral to WA service: {service.__class__.__name__}")
                except Exception as e:
                    logger.warning(f"Failed to send deferral to WA service {service.__class__.__name__}: {e}")
                    continue

            # Track deferral count if any service received it
            if any_success:
                self._deferrals_count += 1

            return any_success
        except Exception as e:
            logger.error(f"Failed to prepare deferral request: {e}", exc_info=True)
            return False

    async def fetch_guidance(self, context: GuidanceContext, handler_name: str) -> Optional[str]:
        """Fetch guidance from wise authority"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["fetch_guidance"])

        if not service:
            logger.debug(f"No wise authority service available for {handler_name}")
            return None

        try:
            result = await service.fetch_guidance(context)
            if result is not None:
                self._guidance_count += 1
            return str(result) if result is not None else None
        except Exception as e:
            logger.error(f"Failed to fetch guidance: {e}", exc_info=True)
            return None

    async def request_review(self, review_type: str, review_data: JSONDict, handler_name: str) -> bool:
        """Request a review from wise authority (e.g., for identity variance)"""
        # Create a deferral context for the review
        context = DeferralContext(
            thought_id=f"review_{review_type}_{handler_name}",
            task_id=f"review_task_{review_type}",
            reason=f"Review requested: {review_type}",
            defer_until=None,
            priority=None,
            metadata={"review_data": str(review_data), "handler_name": handler_name},
        )

        return await self.send_deferral(context, handler_name)

    def _validate_capability(self, capability: Optional[str], agent_tier: int = 1) -> None:
        """
        Validate capability against prohibited domains with tier-based access.

        Args:
            capability: The capability to validate
            agent_tier: Agent tier level (1-5, with 4-5 having stewardship)

        Raises:
            ValueError: If capability is prohibited for the agent's tier
        """
        if not capability:
            return

        # Get the category of this capability
        category = get_capability_category(capability)
        if not category:
            # Not a prohibited capability
            return

        # Check if it's a community moderation capability
        if category.startswith("COMMUNITY_"):
            # Community moderation is only for Tier 4-5 agents
            if agent_tier < 4:
                raise ValueError(
                    f"TIER RESTRICTED: Community moderation capability '{capability}' "
                    f"requires Tier 4-5 agent (current tier: {agent_tier}). "
                    f"This capability is reserved for agents with stewardship responsibilities."
                )
            # Tier 4-5 can use community moderation
            return

        # Get the severity of this prohibition
        severity = get_prohibition_severity(category)

        if severity == ProhibitionSeverity.REQUIRES_SEPARATE_MODULE:
            # These require separate licensed systems
            raise ValueError(
                f"PROHIBITED: {category} capabilities blocked. "
                f"Capability '{capability}' requires separate licensed system. "
                f"Implementation must be in isolated repository with proper liability controls."
            )
        elif severity == ProhibitionSeverity.NEVER_ALLOWED:
            # These are absolutely prohibited
            raise ValueError(
                f"ABSOLUTELY PROHIBITED: {category} capabilities are never allowed. "
                f"Capability '{capability}' violates core safety principles. "
                f"This capability cannot be implemented in any CIRIS system."
            )
        # TIER_RESTRICTED already handled above for community moderation

    async def _get_matching_services(self, request: GuidanceRequest) -> List[Any]:
        """Get services matching the request capability."""
        required_caps = []
        if hasattr(request, "capability") and request.capability:
            required_caps = [request.capability]

        # Try to get multiple services if capability routing is supported
        try:
            services_result = self.service_registry.get_services(
                service_type=ServiceType.WISE_AUTHORITY,
                required_capabilities=required_caps,
                limit=5,  # Prevent unbounded fan-out
            )
            # Handle both sync and async returns
            if hasattr(services_result, "__await__"):
                services = await services_result
            else:
                services = services_result
        except Exception as e:
            logger.debug(f"Multi-provider lookup failed, falling back to single provider: {e}")
            services = []

        # Fallback to single service if multi-provider not available
        if not services:
            service = await self.get_service(handler_name="request_guidance", required_capabilities=["fetch_guidance"])
            if service:
                services = [service]

        return services  # type: ignore[no-any-return]

    def _create_guidance_task(self, svc: Any, request: GuidanceRequest) -> Optional[asyncio.Task[Any]]:
        """Create an appropriate guidance task for the service."""
        if hasattr(svc, "get_guidance"):
            return asyncio.create_task(svc.get_guidance(request))
        elif hasattr(svc, "fetch_guidance"):
            # Convert to GuidanceContext for backward compatibility
            context = GuidanceContext(
                thought_id=f"guidance_{id(request)}",
                task_id=f"task_{id(request)}",
                question=request.context,
                ethical_considerations=[],
                domain_context={"urgency": request.urgency} if request.urgency else {},
            )
            return asyncio.create_task(self._fetch_guidance_compat(svc, context, request.options))
        return None

    async def _collect_guidance_responses(
        self, tasks: List[asyncio.Task[Any]], timeout: float
    ) -> List[GuidanceResponse]:
        """Collect responses from guidance tasks with timeout."""
        if not tasks:
            return []

        # Wait for responses with timeout
        done, pending = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.ALL_COMPLETED)

        # Cancel timed-out tasks
        for task in pending:
            task.cancel()

        # Collect successful responses
        responses = []
        for task in done:
            try:
                resp = task.result()
                if resp:
                    responses.append(resp)
            except Exception as e:
                logger.warning(f"Provider failed: {e}")

        return responses

    async def request_guidance(
        self, request: GuidanceRequest, timeout: float = 5.0, agent_tier: Optional[int] = None
    ) -> GuidanceResponse:
        """
        Request guidance from capability-matching providers with comprehensive prohibitions.

        Args:
            request: Guidance request with optional capability field
            timeout: Maximum time to wait for responses (default 5 seconds)
            agent_tier: Agent tier level (1-5), auto-detected if not provided

        Returns:
            GuidanceResponse with aggregated advice from providers

        Raises:
            ValueError: If capability is prohibited for the agent's tier
            RuntimeError: If no WiseAuthority service is available
        """
        # Track request count
        self._requests_count += 1

        # Auto-detect agent tier if not provided
        if agent_tier is None:
            agent_tier = await self.get_agent_tier()

        # CRITICAL: Validate capability against comprehensive prohibitions
        if hasattr(request, "capability"):
            self._validate_capability(request.capability, agent_tier)

        # Get matching services
        services = await self._get_matching_services(request)
        if not services:
            raise RuntimeError("No WiseAuthority service available")

        # Create tasks for all services
        tasks = []
        for svc in services:
            task = self._create_guidance_task(svc, request)
            if task:
                tasks.append(task)

        # Handle case where no compatible methods found
        if not tasks:
            return GuidanceResponse(
                reasoning="No compatible guidance methods available",
                wa_id="wisebus",
                signature="none",
                custom_guidance="Service lacks guidance capabilities",
            )

        # Collect responses
        responses = await self._collect_guidance_responses(tasks, timeout)

        # Arbitrate responses
        return self._arbitrate_responses(responses, request)

    async def _fetch_guidance_compat(
        self, service: WiseAuthorityService, context: GuidanceContext, options: Optional[List[str]] = None
    ) -> GuidanceResponse:
        """Convert fetch_guidance response to GuidanceResponse for compatibility."""
        try:
            result = await service.fetch_guidance(context)
            if result:
                return GuidanceResponse(
                    selected_option=options[0] if options else None,
                    custom_guidance=str(result),
                    reasoning="Legacy guidance response",
                    wa_id="legacy",
                    signature="compat",
                )
        except Exception as e:
            logger.debug(f"Compatibility fetch failed: {e}")
        # Return empty response instead of None to match return type
        return GuidanceResponse(
            reasoning="fetch_guidance unavailable",
            wa_id="error",
            signature="none",
            custom_guidance="Service unavailable",
        )

    def _arbitrate_responses(self, responses: List[GuidanceResponse], request: GuidanceRequest) -> GuidanceResponse:
        """
        Confidence-based arbitration for multiple responses.
        Selects response with highest confidence from WisdomAdvice.
        """
        if not responses:
            return GuidanceResponse(
                reasoning="No guidance available",
                wa_id="wisebus",
                signature="none",
                custom_guidance="No providers responded",
            )

        # If only one response, use it
        if len(responses) == 1:
            return responses[0]

        # Calculate confidence for each response
        response_confidences = []
        for resp in responses:
            # Get max confidence from advice if available
            max_confidence = 0.0
            if resp.advice:
                for advice in resp.advice:
                    if advice.confidence is not None:
                        max_confidence = max(max_confidence, advice.confidence)
            response_confidences.append((resp, max_confidence))

        # Sort by confidence (highest first)
        response_confidences.sort(key=lambda x: x[1], reverse=True)

        # Select best response
        best_response, best_confidence = response_confidences[0]

        # Aggregate all advice from all providers for transparency
        all_advice = []
        for resp in responses:
            if resp.advice:
                all_advice.extend(resp.advice)

        # Update best response with aggregated advice and note about selection
        best_response.advice = all_advice
        best_response.reasoning = (
            f"{best_response.reasoning} "
            f"(selected with {best_confidence:.2f} confidence from {len(responses)} providers)"
        )

        return best_response

    def _is_capability_allowed(self, capability: str) -> bool:
        """Check if a capability is allowed (not prohibited)."""
        capability_lower = capability.lower()

        # PROHIBITED_CAPABILITIES is a dict of categories, each containing a set of capabilities
        for category, capabilities_set in PROHIBITED_CAPABILITIES.items():
            for prohibited_cap in capabilities_set:
                if capability_lower == prohibited_cap.lower() or prohibited_cap.lower() in capability_lower:
                    return False
        return True

    def _collect_metrics(self) -> Dict[str, float]:
        """Collect base metrics for the wise bus."""
        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        return {
            "wise_guidance_requests": float(self._requests_count),
            "wise_guidance_deferrals": float(self._deferrals_count),
            "wise_guidance_responses": float(self._guidance_count),
            "wise_uptime_seconds": uptime_seconds,
        }

    def get_metrics(self) -> BusMetrics:
        """Get all wise bus metrics as typed BusMetrics schema."""
        # Count active authorities (WiseAuthority services)
        all_wa_services = self.service_registry.get_services_by_type(ServiceType.WISE_AUTHORITY)

        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        # Map to BusMetrics schema
        return BusMetrics(
            messages_sent=self._requests_count,  # Guidance requests sent
            messages_received=self._guidance_count,  # Guidance responses received
            messages_dropped=0,  # Not tracked yet
            average_latency_ms=0.0,  # Not tracked yet
            active_subscriptions=len(all_wa_services),
            queue_depth=self.get_queue_size(),
            errors_last_hour=self._requests_count - self._guidance_count,  # Failed requests
            busiest_service=None,  # Could track which authority gets most requests
            additional_metrics={
                "wise_guidance_requests": self._requests_count,
                "wise_guidance_deferrals": self._deferrals_count,
                "wise_guidance_responses": self._guidance_count,
                "wise_uptime_seconds": uptime_seconds,
            },
        )

    async def _process_message(self, message: BusMessage) -> None:
        """Process a wise authority message - currently all WA operations are synchronous"""
        logger.warning(f"Wise authority operations should be synchronous, got queued message: {type(message)}")

    def _count_capability_categories(self) -> tuple[Dict[str, int], int, Dict[str, int], int]:
        """Count prohibited and community capabilities by category."""
        prohibited_counts = {
            category.lower(): len(capabilities) for category, capabilities in PROHIBITED_CAPABILITIES.items()
        }
        total_prohibited = sum(prohibited_counts.values())

        community_counts = {
            category.lower(): len(capabilities) for category, capabilities in COMMUNITY_MODERATION_CAPABILITIES.items()
        }
        total_community = sum(community_counts.values())

        return prohibited_counts, total_prohibited, community_counts, total_community

    def _create_telemetry_base(
        self,
        prohibited_counts: Dict[str, int],
        total_prohibited: int,
        community_counts: Dict[str, int],
        total_community: int,
    ) -> JSONDict:
        """Create base telemetry dictionary."""
        return {
            "service_name": "wise_bus",
            "prohibited_capabilities": prohibited_counts,
            "total_prohibited": total_prohibited,
            "community_capabilities": community_counts,
            "total_community": total_community,
        }

    async def collect_telemetry(self) -> JSONDict:
        """
        Collect telemetry from all wise authority providers in parallel.

        Returns aggregated metrics including:
        - failed_count: Total deferrals failed across providers
        - processed_count: Total guidance requests processed
        - provider_count: Number of active providers
        - prohibited_capabilities: Count by category
        - community_capabilities: Count of community moderation capabilities
        """
        all_wa_services = self.service_registry.get_services_by_type(ServiceType.WISE_AUTHORITY)

        # Count capabilities by category
        prohibited_counts, total_prohibited, community_counts, total_community = self._count_capability_categories()
        base_telemetry = self._create_telemetry_base(
            prohibited_counts, total_prohibited, community_counts, total_community
        )

        if not all_wa_services:
            return {
                **base_telemetry,
                "healthy": False,
                "failed_count": 0,
                "processed_count": 0,
                "provider_count": 0,
                "error": "No wise authority services available",
            }

        # Create tasks to collect telemetry from all providers
        tasks = [
            asyncio.create_task(service.get_telemetry())
            for service in all_wa_services
            if hasattr(service, "get_telemetry")
        ]

        # Initialize aggregated telemetry
        aggregated = {
            **base_telemetry,
            "healthy": True,
            "failed_count": 0,
            "processed_count": 0,
            "provider_count": len(all_wa_services),
            "providers": [],
        }

        if not tasks:
            return aggregated

        # Collect and aggregate provider telemetry
        done, pending = await asyncio.wait(tasks, timeout=2.0, return_when=asyncio.ALL_COMPLETED)

        # Cancel timed-out tasks
        for task in pending:
            task.cancel()

        # Aggregate results from completed tasks
        self._aggregate_provider_telemetry(aggregated, done)

        return aggregated

    def _aggregate_provider_telemetry(self, aggregated: JSONDict, completed_tasks: Set[Any]) -> None:
        """Aggregate telemetry from completed provider tasks."""
        for task in completed_tasks:
            try:
                telemetry = task.result()
                if not telemetry:
                    continue

                service_name = get_str(telemetry, "service_name", "unknown")
                providers_list = aggregated["providers"]
                if isinstance(providers_list, list):
                    providers_list.append(service_name)

                failed_count = aggregated["failed_count"]
                if isinstance(failed_count, int):
                    aggregated["failed_count"] = failed_count + get_int(telemetry, "failed_count", 0)

                processed_count = aggregated["processed_count"]
                if isinstance(processed_count, int):
                    aggregated["processed_count"] = processed_count + get_int(telemetry, "processed_count", 0)
            except Exception as e:
                logger.warning(f"Failed to collect telemetry from provider: {e}")
