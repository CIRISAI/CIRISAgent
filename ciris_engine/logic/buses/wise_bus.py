"""
Wise Authority message bus - handles all WA service operations
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, List, Optional

from ciris_engine.protocols.services import WiseAuthorityService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority_core import GuidanceRequest, GuidanceResponse
from ciris_engine.schemas.services.context import DeferralContext, GuidanceContext

from .base_bus import BaseBus, BusMessage

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

logger = logging.getLogger(__name__)

# CRITICAL: Medical domain prohibition - These capabilities are BLOCKED at the bus level
# to prevent any medical/health functionality in the main repository.
# Medical implementations must be in a separate, licensed system (CIRISMedical).
PROHIBITED_CAPABILITIES = {
    "domain:medical",
    "domain:health",
    "domain:triage",
    "domain:diagnosis",
    "domain:treatment",
    "domain:prescription",
    "domain:patient",
    "domain:clinical",
    "domain:symptom",
    "domain:disease",
    "domain:medication",
    "domain:therapy",
    "domain:condition",
    "domain:disorder",
    "modality:medical",
    "provider:medical",
    "clinical",
    "symptom",
    "disease",
    "medication",
    "therapy",
    "triage",
    "diagnosis",
    "treatment",
    "prescription",
    "patient",
    "health",
    "medical",
    "condition",
    "disorder",
}


class WiseBus(BaseBus[WiseAuthorityService]):
    """
    Message bus for all wise authority operations.

    Handles:
    - send_deferral
    - fetch_guidance
    """

    def __init__(self, service_registry: "ServiceRegistry", time_service: TimeServiceProtocol):
        super().__init__(service_type=ServiceType.WISE_AUTHORITY, service_registry=service_registry)
        self._time_service = time_service

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
            return str(result) if result is not None else None
        except Exception as e:
            logger.error(f"Failed to fetch guidance: {e}", exc_info=True)
            return None

    async def request_review(self, review_type: str, review_data: dict, handler_name: str) -> bool:
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

    def _validate_capability(self, capability: Optional[str]) -> None:
        """
        Validate capability against prohibited domains.
        Raises ValueError if capability contains prohibited terms.
        """
        if not capability:
            return

        cap_lower = capability.lower()
        for prohibited in PROHIBITED_CAPABILITIES:
            if prohibited in cap_lower:
                raise ValueError(
                    f"PROHIBITED: Medical/health capabilities blocked. "
                    f"Capability '{capability}' contains prohibited term '{prohibited}'. "
                    f"Medical implementations require separate licensed system (CIRISMedical)."
                )

    async def _get_matching_services(self, request: GuidanceRequest) -> List[Any]:
        """Get services matching the request capability."""
        required_caps = []
        if hasattr(request, "capability") and request.capability:
            required_caps = [request.capability]

        # Try to get multiple services if capability routing is supported
        try:
            services = self.service_registry.get_services(
                service_type=ServiceType.WISE_AUTHORITY,
                required_capabilities=required_caps,
                limit=5,  # Prevent unbounded fan-out
            )
        except Exception as e:
            logger.debug(f"Multi-provider lookup failed, falling back to single provider: {e}")
            services = []

        # Fallback to single service if multi-provider not available
        if not services:
            service = await self.get_service(handler_name="request_guidance", required_capabilities=["fetch_guidance"])
            if service:
                services = [service]

        return services

    def _create_guidance_task(self, svc: Any, request: GuidanceRequest) -> Optional[asyncio.Task]:
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

    async def _collect_guidance_responses(self, tasks: List[asyncio.Task], timeout: float) -> List[GuidanceResponse]:
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

    async def request_guidance(self, request: GuidanceRequest, timeout: float = 5.0) -> GuidanceResponse:
        """
        Request guidance from capability-matching providers with medical prohibition.

        Args:
            request: Guidance request with optional capability field
            timeout: Maximum time to wait for responses (default 5 seconds)

        Returns:
            GuidanceResponse with aggregated advice from providers

        Raises:
            ValueError: If capability contains prohibited medical terms
            RuntimeError: If no WiseAuthority service is available
        """
        # CRITICAL: Block medical domains before any processing
        if hasattr(request, "capability"):
            self._validate_capability(request.capability)

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

    async def _process_message(self, message: BusMessage) -> None:
        """Process a wise authority message - currently all WA operations are synchronous"""
        logger.warning(f"Wise authority operations should be synchronous, got queued message: {type(message)}")
