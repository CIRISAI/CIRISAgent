"""
LLM message bus - handles all LLM service operations with redundancy and distribution
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type, Union, cast

from ciris_engine.logic.utils.jsondict_helpers import get_float, get_int
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry
    from ciris_engine.schemas.services.llm import LLMMessage

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from ciris_engine.protocols.services import LLMService
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.protocols.services.runtime.llm import MessageDict
from ciris_engine.schemas.infrastructure.base import BusMetrics
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.services.capabilities import LLMCapabilities

from .base_bus import BaseBus, BusMessage

logger = logging.getLogger(__name__)


class DistributionStrategy(str, Enum):
    """Strategy for distributing requests among services at the same priority"""

    ROUND_ROBIN = "round_robin"
    LATENCY_BASED = "latency_based"
    RANDOM = "random"
    LEAST_LOADED = "least_loaded"


@dataclass
class ServiceMetrics:
    """Metrics for a single LLM service instance"""

    total_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    last_request_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    consecutive_failures: int = 0

    @property
    def average_latency_ms(self) -> float:
        """Calculate average latency"""
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate"""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests


class LLMBusMessage(BusMessage):
    """Bus message for LLM generation"""

    messages: List[MessageDict]
    response_model: Type[BaseModel]
    max_tokens: int = 4096
    temperature: float = 0.0
    # For async responses
    future: Optional[asyncio.Future[Any]] = None


class LLMBus(BaseBus[LLMService]):
    """
    Message bus for all LLM operations with redundancy and distribution.

    Features:
    - Multiple redundant LLM providers
    - Priority-based selection
    - Distribution strategies (round-robin, latency-based)
    - Circuit breakers per service
    - Automatic failover
    - Metrics tracking
    """

    def __init__(
        self,
        service_registry: "ServiceRegistry",
        time_service: TimeServiceProtocol,
        telemetry_service: Optional[TelemetryServiceProtocol] = None,
        distribution_strategy: DistributionStrategy = DistributionStrategy.LATENCY_BASED,
        circuit_breaker_config: Optional[JSONDict] = None,
    ):
        super().__init__(service_type=ServiceType.LLM, service_registry=service_registry)

        self._time_service = time_service
        self._start_time = time_service.now() if time_service else None
        self.distribution_strategy = distribution_strategy
        self.circuit_breaker_config = circuit_breaker_config or {}
        self.telemetry_service = telemetry_service

        # Service metrics and circuit breakers
        self.service_metrics: dict[str, ServiceMetrics] = defaultdict(ServiceMetrics)
        self.circuit_breakers: dict[str, CircuitBreaker] = {}

        # Track services that have had full error logs to reduce log verbosity
        self._services_with_full_error_logged: set[str] = set()

        # Round-robin state
        self.round_robin_index: dict[int, int] = defaultdict(int)  # priority -> index

        logger.info(f"LLMBus initialized with {distribution_strategy} distribution strategy")

    def _normalize_messages(self, messages: Union[List[JSONDict], List["LLMMessage"]]) -> List[JSONDict]:
        """Normalize messages to dict format for LLM providers.

        Args:
            messages: List of message dictionaries or LLMMessage objects

        Returns:
            List of normalized message dictionaries
        """
        from ciris_engine.schemas.services.llm import LLMMessage

        normalized_messages: List[JSONDict] = []
        for msg in messages:
            if isinstance(msg, LLMMessage):
                # Use exclude_none=True to avoid sending name: None to providers
                # Some providers (e.g., Together AI) reject null values for optional fields
                msg_dict = msg.model_dump(exclude_none=True)
                normalized_messages.append(msg_dict)
            else:
                # Only strip the optional "name" field if it's None
                # IMPORTANT: Don't strip required fields like "content" even if None
                # (tool-call assistant messages require "content": None to be present)
                msg_copy = dict(msg)
                if "name" in msg_copy and msg_copy["name"] is None:
                    del msg_copy["name"]
                normalized_messages.append(msg_copy)
        return normalized_messages

    async def call_llm_structured(
        self,
        messages: Union[List[JSONDict], List["LLMMessage"]],
        response_model: Type[BaseModel],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        handler_name: str = "default",
        domain: Optional[str] = None,  # NEW: Domain-aware routing
        thought_id: Optional[str] = None,  # NEW: For resource tracking per thought
        task_id: Optional[str] = None,  # For ciris.ai billing - all calls with same task_id share 1 credit
    ) -> Tuple[BaseModel, ResourceUsage]:
        """
        Generate structured output using LLM with optional domain routing.

        This method handles:
        - Domain-aware service filtering (e.g., medical, legal, financial)
        - Service discovery by priority
        - Distribution based on strategy
        - Circuit breaker checks
        - Automatic failover
        - Metrics collection

        Args:
            messages: List of message dictionaries or LLMMessage objects
            response_model: Pydantic model for structured response
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            handler_name: Handler identifier for metrics
            domain: Optional domain for routing to specialized LLMs
        """
        # Normalize messages to dicts
        normalized_messages = self._normalize_messages(messages)
        start_time = self._time_service.timestamp()

        # Get all available LLM services, filtered by domain if specified
        services = await self._get_prioritized_services(handler_name, domain=domain)

        if not services:
            raise RuntimeError(f"No LLM services available for {handler_name}")

        # Group services by priority
        priority_groups = self._group_by_priority(services)

        # Try each priority group in order
        last_error = None
        for priority, service_group in sorted(priority_groups.items()):
            # Select service from this priority group based on strategy
            selected_service = await self._select_service(service_group, priority, handler_name)

            if not selected_service:
                continue

            service_name = f"{type(selected_service).__name__}_{id(selected_service)}"

            # Check circuit breaker
            if not self._check_circuit_breaker(service_name):
                logger.warning(f"Circuit breaker OPEN for {service_name}, skipping")
                continue

            try:
                # Make the LLM call
                logger.debug(f"Calling LLM service {service_name} for {handler_name}")

                result, usage = await selected_service.call_llm_structured(  # type: ignore[attr-defined]
                    messages=normalized_messages,
                    response_model=response_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    thought_id=thought_id,
                    task_id=task_id,
                )

                # Record success
                latency_ms = (self._time_service.timestamp() - start_time) * 1000
                self._record_success(service_name, latency_ms)

                # Record telemetry for resource usage
                await self._record_resource_telemetry(
                    service_name=service_name,
                    handler_name=handler_name,
                    usage=usage,
                    latency_ms=latency_ms,
                    thought_id=thought_id,
                )

                logger.debug(f"LLM call successful via {service_name} " f"(latency: {latency_ms:.2f}ms)")

                return result, usage

            except Exception as e:
                # Check for billing errors - these should not be retried
                from ciris_engine.logic.adapters.base_observer import BillingServiceError

                if isinstance(e, BillingServiceError):
                    logger.error(f"LLM billing error (not retrying): {e}")
                    raise  # Don't retry billing errors - surface to user immediately

                # Record failure
                self._record_failure(service_name)
                last_error = e

                # Log full stack trace only once per service to reduce log verbosity
                # Subsequent failures for the same service will be logged as warnings
                if service_name not in self._services_with_full_error_logged:
                    logger.error(f"LLM service {service_name} failed: {e}", exc_info=True)
                    self._services_with_full_error_logged.add(service_name)
                else:
                    logger.warning(f"LLM service {service_name} failed (repeated): {e}")

                # Continue to next service
                continue

        # All services failed
        raise RuntimeError(f"All LLM services failed for {handler_name}. " f"Last error: {last_error}")

    # Note: This method is not in the protocol but kept for internal use
    async def _generate_structured_sync(
        self,
        messages: List[JSONDict],
        response_model: Type[BaseModel],
        handler_name: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        domain: Optional[str] = None,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """
        Synchronous version of generate_structured with domain routing.

        This is what the handlers will call directly.
        """
        return await self.call_llm_structured(
            messages=messages,
            response_model=response_model,
            handler_name=handler_name,
            max_tokens=max_tokens,
            temperature=temperature,
            domain=domain,
        )

    def _check_service_capabilities(self, service: Any) -> bool:
        """Check if service has required LLM capabilities."""
        if not hasattr(service, "get_capabilities"):
            return True

        caps = service.get_capabilities()
        if hasattr(caps, "supports_operation_list"):
            return LLMCapabilities.CALL_LLM_STRUCTURED.value in caps.supports_operation_list
        elif hasattr(caps, "actions"):
            return LLMCapabilities.CALL_LLM_STRUCTURED.value in caps.actions
        return True

    def _get_service_priority_and_metadata(self, service: Any) -> Tuple[int, JSONDict]:
        """Get priority value and metadata for a service."""
        provider_info = self.service_registry.get_provider_info(service_type=ServiceType.LLM)
        priority_map = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3, "FALLBACK": 9}

        for providers in provider_info.get("services", {}).get(ServiceType.LLM, []):
            if providers["name"].endswith(str(id(service))):
                priority_value = priority_map.get(providers["priority"], 2)
                service_metadata = providers.get("metadata", {})
                return priority_value, service_metadata

        return 0, {}  # Default to highest priority, empty metadata

    def _should_include_service_for_domain(self, service_metadata: JSONDict, domain: Optional[str]) -> Tuple[bool, int]:
        """Check if service should be included based on domain and get priority adjustment.

        Returns:
            Tuple of (should_include, priority_adjustment)
        """
        if not domain:
            return True, 0

        service_domain = service_metadata.get("domain", "general")

        # Skip services that don't match domain and aren't general
        if service_domain != domain and service_domain != "general":
            logger.debug(f"Skipping service with domain {service_domain} (requested: {domain})")
            return False, 0

        # Boost priority for exact domain match
        if service_domain == domain:
            return True, -1

        return True, 0

    async def _get_prioritized_services(self, handler_name: str, domain: Optional[str] = None) -> List[Tuple[Any, int]]:
        """Get all available LLM services with their priorities, optionally filtered by domain.

        NOTE: This method does NOT filter by health/circuit breaker state. That check
        happens during service selection in call_llm_structured() to enable proper
        failover from services with open circuit breakers to lower-priority services.

        Args:
            handler_name: Handler identifier
            domain: Optional domain filter (e.g., 'medical', 'legal', 'financial')

        Returns:
            List of (service, priority) tuples
        """
        services = []
        all_llm_services = self.service_registry.get_services_by_type(ServiceType.LLM)

        for service in all_llm_services:
            # Check capabilities
            if not self._check_service_capabilities(service):
                continue

            # Get priority and metadata
            priority_value, service_metadata = self._get_service_priority_and_metadata(service)

            # Check domain filtering
            should_include, priority_adjustment = self._should_include_service_for_domain(service_metadata, domain)
            if not should_include:
                continue

            # Apply priority adjustment for domain matching
            priority_value = max(0, priority_value + priority_adjustment)
            services.append((service, priority_value))

        return services

    def _group_by_priority(self, services: List[Tuple[Any, int]]) -> dict[int, List[object]]:
        """Group services by priority"""
        groups: dict[int, List[object]] = defaultdict(list)
        for service, priority in services:
            groups[priority].append(service)
        return groups

    async def _select_service(self, services: List[object], priority: int, handler_name: str) -> Optional[object]:
        """Select a service from a priority group based on distribution strategy"""
        if not services:
            return None

        if len(services) == 1:
            return services[0]

        if self.distribution_strategy == DistributionStrategy.ROUND_ROBIN:
            # Round-robin selection
            index = self.round_robin_index[priority] % len(services)
            self.round_robin_index[priority] += 1
            return services[index]

        elif self.distribution_strategy == DistributionStrategy.LATENCY_BASED:
            # Select service with lowest average latency
            best_service = None
            best_latency = float("inf")

            for service in services:
                service_name = f"{type(service).__name__}_{id(service)}"
                metrics = self.service_metrics[service_name]

                # New services get a chance
                if metrics.total_requests == 0:
                    return service

                if metrics.average_latency_ms < best_latency:
                    best_latency = metrics.average_latency_ms
                    best_service = service

            return best_service or services[0]

        elif self.distribution_strategy == DistributionStrategy.RANDOM:
            # Random selection for load distribution (not cryptographic)
            import random

            return random.choice(services)

        else:  # DistributionStrategy.LEAST_LOADED
            # Select service with fewest active requests
            # This would require tracking active requests
            # For now, use the one with fewest total requests
            return min(services, key=lambda s: self.service_metrics[f"{type(s).__name__}_{id(s)}"].total_requests)

    def _check_circuit_breaker(self, service_name: str) -> bool:
        """Check if circuit breaker allows execution"""
        if service_name not in self.circuit_breakers:
            # Create CircuitBreakerConfig from the dict config - use jsondict_helpers for type safety
            config = CircuitBreakerConfig(
                failure_threshold=get_int(self.circuit_breaker_config, "failure_threshold", 5),
                recovery_timeout=get_float(self.circuit_breaker_config, "recovery_timeout", 60.0),
                success_threshold=get_int(self.circuit_breaker_config, "half_open_max_calls", 3),
                timeout_duration=get_float(self.circuit_breaker_config, "timeout_duration", 30.0),
            )
            self.circuit_breakers[service_name] = CircuitBreaker(name=service_name, config=config)

        return self.circuit_breakers[service_name].is_available()

    def _record_success(self, service_name: str, latency_ms: float) -> None:
        """Record successful call metrics"""
        metrics = self.service_metrics[service_name]
        metrics.total_requests += 1
        metrics.total_latency_ms += latency_ms
        metrics.last_request_time = self._time_service.now()
        metrics.consecutive_failures = 0

        if service_name in self.circuit_breakers:
            self.circuit_breakers[service_name].record_success()

    def _record_failure(self, service_name: str) -> None:
        """Record failed call metrics"""
        metrics = self.service_metrics[service_name]
        metrics.total_requests += 1
        metrics.failed_requests += 1
        metrics.last_failure_time = self._time_service.now()
        metrics.consecutive_failures += 1

        if service_name in self.circuit_breakers:
            self.circuit_breakers[service_name].record_failure()

    async def _record_resource_telemetry(
        self,
        service_name: str,
        handler_name: str,
        usage: ResourceUsage,
        latency_ms: float,
        thought_id: Optional[str] = None,
    ) -> None:
        """Record detailed telemetry for resource usage"""
        if not self.telemetry_service:
            return

        try:
            # Build base tags
            base_tags = {
                "service": service_name,
                "model": usage.model_used or "unknown",
                "handler": handler_name,
            }
            # Add thought_id if provided for per-thought resource tracking
            if thought_id:
                base_tags["thought_id"] = thought_id

            # Record token usage
            await self.telemetry_service.record_metric(
                metric_name="llm.tokens.total",
                value=float(usage.tokens_used),
                handler_name=handler_name,
                tags=base_tags,
            )

            # Record input/output tokens separately
            if usage.tokens_input > 0:
                await self.telemetry_service.record_metric(
                    metric_name="llm.tokens.input",
                    value=float(usage.tokens_input),
                    handler_name=handler_name,
                    tags=base_tags,
                )

            if usage.tokens_output > 0:
                await self.telemetry_service.record_metric(
                    metric_name="llm.tokens.output",
                    value=float(usage.tokens_output),
                    handler_name=handler_name,
                    tags=base_tags,
                )

            # Record cost
            if usage.cost_cents > 0:
                await self.telemetry_service.record_metric(
                    metric_name="llm.cost.cents",
                    value=usage.cost_cents,
                    handler_name=handler_name,
                    tags=base_tags,
                )

            # Record environmental impact
            if usage.carbon_grams > 0:
                await self.telemetry_service.record_metric(
                    metric_name="llm.environmental.carbon_grams",
                    value=usage.carbon_grams,
                    handler_name=handler_name,
                    tags=base_tags,
                )

            if usage.energy_kwh > 0:
                await self.telemetry_service.record_metric(
                    metric_name="llm.environmental.energy_kwh",
                    value=usage.energy_kwh,
                    handler_name=handler_name,
                    tags=base_tags,
                )

            # Record latency
            await self.telemetry_service.record_metric(
                metric_name="llm.latency.ms",
                value=latency_ms,
                handler_name=handler_name,
                tags=base_tags,
            )

        except Exception as e:
            logger.warning(f"Failed to record telemetry: {e}")

    def get_service_stats(self) -> JSONDict:
        """Get detailed statistics for all services"""
        stats: JSONDict = {}

        for service_name, metrics in self.service_metrics.items():
            circuit_breaker = self.circuit_breakers.get(service_name)

            stats[service_name] = {
                "total_requests": metrics.total_requests,
                "failed_requests": metrics.failed_requests,
                "failure_rate": f"{metrics.failure_rate * 100:.2f}%",
                "average_latency_ms": f"{metrics.average_latency_ms:.2f}",
                "consecutive_failures": metrics.consecutive_failures,
                "circuit_breaker_state": circuit_breaker.state.value if circuit_breaker else "none",
                "last_request": metrics.last_request_time.isoformat() if metrics.last_request_time else None,
                "last_failure": metrics.last_failure_time.isoformat() if metrics.last_failure_time else None,
            }

        return stats

    async def get_available_models(self, handler_name: str = "default") -> List[str]:
        """Get list of available LLM models"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["get_available_models"])

        if not service:
            logger.error(f"No LLM service available for {handler_name}")
            return []

        try:
            # Cast to Any to handle dynamic method access
            service_any = cast(Any, service)
            result: List[str] = await service_any.get_available_models()
            return result
        except Exception as e:
            logger.error(f"Error getting available models: {e}", exc_info=True)
            return []

    async def is_healthy(self, handler_name: str = "default") -> bool:
        """Check if LLM service is healthy"""
        service = await self.get_service(handler_name=handler_name)
        if not service:
            return False
        try:
            return await service.is_healthy()
        except Exception as e:
            logger.error(f"Failed to check health: {e}")
            return False

    async def get_capabilities(self, handler_name: str = "default") -> List[str]:
        """Get LLM service capabilities"""
        service = await self.get_service(handler_name=handler_name)
        if not service:
            return []
        try:
            capabilities = service.get_capabilities()
            return capabilities.supports_operation_list if hasattr(capabilities, "supports_operation_list") else []
        except Exception as e:
            logger.error(f"Failed to get capabilities: {e}")
            return []

    async def _process_message(self, message: BusMessage) -> None:
        """Process an LLM message from the queue"""
        if isinstance(message, LLMBusMessage):
            # For async processing, we would handle the request here
            # and set the result on the future
            # For now, LLM calls are synchronous
            logger.warning("Async LLM processing not yet implemented")
        else:
            logger.error(f"Unknown message type: {type(message)}")

    def get_stats(self) -> JSONDict:
        """Get bus statistics including service stats"""
        base_stats = super().get_stats()
        base_stats["service_stats"] = self.get_service_stats()
        base_stats["distribution_strategy"] = self.distribution_strategy.value
        return base_stats

    def _collect_metrics(self) -> dict[str, float]:
        """Collect base metrics for the LLM bus."""
        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        # Calculate aggregate metrics from service metrics
        total_requests = sum(m.total_requests for m in self.service_metrics.values())
        failed_requests = sum(m.failed_requests for m in self.service_metrics.values())
        total_latency = sum(m.total_latency_ms for m in self.service_metrics.values())
        avg_latency = total_latency / total_requests if total_requests > 0 else 0.0

        # Count circuit breakers open
        circuit_breakers_open = sum(1 for cb in self.circuit_breakers.values() if cb.state == CircuitState.OPEN)

        return {
            "llm_requests_total": float(total_requests),
            "llm_failed_requests": float(failed_requests),
            "llm_average_latency_ms": avg_latency,
            "llm_circuit_breakers_open": float(circuit_breakers_open),
            "llm_providers_available": float(len(self.service_metrics)),
            "llm_uptime_seconds": uptime_seconds,
        }

    def get_metrics(self) -> BusMetrics:
        """Get all LLM bus metrics as typed BusMetrics schema."""
        # Calculate aggregate metrics from service metrics
        total_requests = sum(m.total_requests for m in self.service_metrics.values())
        failed_requests = sum(m.failed_requests for m in self.service_metrics.values())
        total_latency = sum(m.total_latency_ms for m in self.service_metrics.values())
        avg_latency = total_latency / total_requests if total_requests > 0 else 0.0

        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        # Count circuit breakers open
        circuit_breakers_open = sum(1 for cb in self.circuit_breakers.values() if cb.state == CircuitState.OPEN)

        # Find busiest service (service with most requests)
        busiest_service = None
        max_requests = 0
        for service_name, metrics in self.service_metrics.items():
            if metrics.total_requests > max_requests:
                max_requests = metrics.total_requests
                busiest_service = service_name

        # Map to BusMetrics schema
        return BusMetrics(
            messages_sent=total_requests,  # Total LLM requests sent
            messages_received=total_requests,  # Same as sent (synchronous)
            messages_dropped=0,  # Not tracked yet
            average_latency_ms=avg_latency,
            active_subscriptions=len(self.service_metrics),  # Number of LLM services with metrics
            queue_depth=self.get_queue_size(),
            errors_last_hour=failed_requests,  # Total failed requests (not windowed yet)
            busiest_service=busiest_service,
            additional_metrics={
                "llm_requests_total": total_requests,
                "llm_failed_requests": failed_requests,
                "llm_circuit_breakers_open": circuit_breakers_open,
                "llm_providers_available": len(self.service_metrics),
                "llm_uptime_seconds": uptime_seconds,
            },
        )

    def _is_service_available_sync(self, service: object) -> bool:
        """Synchronous check if a service is available (for metrics collection)."""
        try:
            # Check if service has basic capabilities
            if not self._check_service_capabilities(service):
                return False

            # Check circuit breaker state
            service_name = f"{type(service).__name__}_{id(service)}"
            if not self._check_circuit_breaker(service_name):
                return False

            # Service is considered active if it passes basic checks
            return True
        except Exception:
            return False

    def clear_circuit_breakers(self) -> None:
        """Clear all circuit breakers - useful for testing.

        WARNING: This should ONLY be used in test environments to ensure
        clean state between test runs. Using this in production could
        hide real service failures.
        """
        logger.warning("Clearing all LLM circuit breakers - this should only happen in tests!")
        self.circuit_breakers.clear()
        # Also clear service metrics to ensure clean state
        self.service_metrics.clear()
