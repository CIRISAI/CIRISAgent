"""
LLM message bus - handles all LLM service operations with redundancy and distribution
"""

import logging
import time  # Only used as fallback in CircuitBreaker when time_service is None
import asyncio
from typing import Optional, List, Type, Tuple, Any, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

from pydantic import BaseModel

from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.services.capabilities import LLMCapabilities
from ciris_engine.protocols.services import LLMService
from ciris_engine.protocols.services.runtime.llm import MessageDict
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from .base_bus import BaseBus, BusMessage
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

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
    max_tokens: int = 1024
    temperature: float = 0.0
    # For async responses
    future: Optional[asyncio.Future] = None


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
        circuit_breaker_config: Optional[dict] = None
    ):
        super().__init__(
            service_type=ServiceType.LLM,
            service_registry=service_registry
        )

        self._time_service = time_service
        self.distribution_strategy = distribution_strategy
        self.circuit_breaker_config = circuit_breaker_config or {}
        self.telemetry_service = telemetry_service

        # Service metrics and circuit breakers
        self.service_metrics: dict[str, ServiceMetrics] = defaultdict(ServiceMetrics)
        self.circuit_breakers: dict[str, CircuitBreaker] = {}

        # Round-robin state
        self.round_robin_index: dict[int, int] = defaultdict(int)  # priority -> index

        logger.info(
            f"LLMBus initialized with {distribution_strategy} distribution strategy"
        )

    async def call_llm_structured(
        self,
        messages: List[dict],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
        handler_name: str = "default",
    ) -> Tuple[BaseModel, ResourceUsage]:
        """
        Generate structured output using LLM.

        This method handles:
        - Service discovery by priority
        - Distribution based on strategy
        - Circuit breaker checks
        - Automatic failover
        - Metrics collection
        """
        start_time = self._time_service.timestamp()

        # Get all available LLM services
        services = await self._get_prioritized_services(handler_name)

        if not services:
            raise RuntimeError(f"No LLM services available for {handler_name}")

        # Group services by priority
        priority_groups = self._group_by_priority(services)

        # Try each priority group in order
        last_error = None
        for priority, service_group in sorted(priority_groups.items()):
            # Select service from this priority group based on strategy
            selected_service = await self._select_service(
                service_group,
                priority,
                handler_name
            )

            if not selected_service:
                continue

            service_name = f"{type(selected_service).__name__}_{id(selected_service)}"

            # Check circuit breaker
            if not self._check_circuit_breaker(service_name):
                logger.warning(
                    f"Circuit breaker OPEN for {service_name}, skipping"
                )
                continue

            try:
                # Make the LLM call
                logger.debug(
                    f"Calling LLM service {service_name} for {handler_name}"
                )

                result, usage = await selected_service.call_llm_structured(  # type: ignore[attr-defined]
                    messages=messages,
                    response_model=response_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                # Record success
                latency_ms = (self._time_service.timestamp() - start_time) * 1000
                self._record_success(service_name, latency_ms)

                # Record telemetry for resource usage
                await self._record_resource_telemetry(
                    service_name=service_name,
                    handler_name=handler_name,
                    usage=usage,
                    latency_ms=latency_ms
                )

                logger.debug(
                    f"LLM call successful via {service_name} "
                    f"(latency: {latency_ms:.2f}ms)"
                )

                return result, usage

            except Exception as e:
                # Record failure
                self._record_failure(service_name)
                last_error = e

                logger.error(
                    f"LLM service {service_name} failed: {e}",
                    exc_info=True
                )

                # Continue to next service
                continue

        # All services failed
        raise RuntimeError(
            f"All LLM services failed for {handler_name}. "
            f"Last error: {last_error}"
        )

    # Note: This method is not in the protocol but kept for internal use
    async def _generate_structured_sync(
        self,
        messages: List[dict],
        response_model: Type[BaseModel],
        handler_name: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """
        Synchronous version of generate_structured.

        This is what the handlers will call directly.
        """
        return await self.call_llm_structured(
            messages=messages,
            response_model=response_model,
            handler_name=handler_name,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def _get_prioritized_services(
        self,
        handler_name: str
    ) -> List[Tuple[Any, int]]:
        """Get all available LLM services with their priorities"""
        services = []

        # Get all registered LLM services
        all_llm_services = self.service_registry.get_services_by_type(ServiceType.LLM)
        
        # For each service, check capabilities and health
        for service in all_llm_services:
            # Check if service has required capabilities
            has_capabilities = True
            if hasattr(service, 'get_capabilities'):
                caps = service.get_capabilities()
                if hasattr(caps, 'supports_operation_list'):
                    has_capabilities = LLMCapabilities.CALL_LLM_STRUCTURED.value in caps.supports_operation_list
                elif hasattr(caps, 'actions'):
                    has_capabilities = LLMCapabilities.CALL_LLM_STRUCTURED.value in caps.actions
            
            if has_capabilities and await self._is_service_healthy(service):
                # Get the provider info to determine priority
                provider_info = self.service_registry.get_provider_info(service_type=ServiceType.LLM)
                
                # Find this service's priority
                priority_value = 0  # Default to highest priority
                for providers in provider_info.get("services", {}).get(ServiceType.LLM, []):
                    if providers["name"].endswith(str(id(service))):
                        # Convert priority name to value
                        priority_map = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3, "FALLBACK": 9}
                        priority_value = priority_map.get(providers["priority"], 2)
                        break
                
                services.append((service, priority_value))

        return services

    def _group_by_priority(
        self,
        services: List[Tuple[Any, int]]
    ) -> dict[int, List[object]]:
        """Group services by priority"""
        groups: dict[int, List[object]] = defaultdict(list)
        for service, priority in services:
            groups[priority].append(service)
        return groups

    async def _select_service(
        self,
        services: List[object],
        priority: int,
        handler_name: str
    ) -> Optional[object]:
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
            best_latency = float('inf')

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
            return min(
                services,
                key=lambda s: self.service_metrics[f"{type(s).__name__}_{id(s)}"].total_requests
            )

    async def _is_service_healthy(self, service: object) -> bool:
        """Check if a service is healthy"""
        try:
            result = await service.is_healthy()  # type: ignore[attr-defined]
            return bool(result)
        except Exception:
            return False

    def _check_circuit_breaker(self, service_name: str) -> bool:
        """Check if circuit breaker allows execution"""
        if service_name not in self.circuit_breakers:
            # Create CircuitBreakerConfig from the dict config
            config = CircuitBreakerConfig(
                failure_threshold=self.circuit_breaker_config.get('failure_threshold', 5),
                recovery_timeout=self.circuit_breaker_config.get('recovery_timeout', 60.0),
                success_threshold=self.circuit_breaker_config.get('half_open_max_calls', 3),
                timeout_duration=self.circuit_breaker_config.get('timeout_duration', 30.0)
            )
            self.circuit_breakers[service_name] = CircuitBreaker(
                name=service_name,
                config=config
            )

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
        latency_ms: float
    ) -> None:
        """Record detailed telemetry for resource usage"""
        if not self.telemetry_service:
            return

        try:
            # Record token usage
            await self.telemetry_service.record_metric(
                metric_name="llm.tokens.total",
                value=float(usage.tokens_used),
                handler_name=handler_name,
                tags={
                    "service": service_name,
                    "model": usage.model_used or "unknown",
                    "handler": handler_name
                }
            )

            # Record input/output tokens separately
            if usage.tokens_input > 0:
                await self.telemetry_service.record_metric(
                    metric_name="llm.tokens.input",
                    value=float(usage.tokens_input),
                    handler_name=handler_name,
                    tags={"service": service_name, "model": usage.model_used or "unknown"}
                )

            if usage.tokens_output > 0:
                await self.telemetry_service.record_metric(
                    metric_name="llm.tokens.output",
                    value=float(usage.tokens_output),
                    handler_name=handler_name,
                    tags={"service": service_name, "model": usage.model_used or "unknown"}
                )

            # Record cost
            if usage.cost_cents > 0:
                await self.telemetry_service.record_metric(
                    metric_name="llm.cost.cents",
                    value=usage.cost_cents,
                    handler_name=handler_name,
                    tags={"service": service_name, "model": usage.model_used or "unknown"}
                )

            # Record environmental impact
            if usage.carbon_grams > 0:
                await self.telemetry_service.record_metric(
                    metric_name="llm.environmental.carbon_grams",
                    value=usage.carbon_grams,
                    handler_name=handler_name,
                    tags={"service": service_name, "model": usage.model_used or "unknown"}
                )

            if usage.energy_kwh > 0:
                await self.telemetry_service.record_metric(
                    metric_name="llm.environmental.energy_kwh",
                    value=usage.energy_kwh,
                    handler_name=handler_name,
                    tags={"service": service_name, "model": usage.model_used or "unknown"}
                )

            # Record latency
            await self.telemetry_service.record_metric(
                metric_name="llm.latency.ms",
                value=latency_ms,
                handler_name=handler_name,
                tags={"service": service_name, "model": usage.model_used or "unknown"}
            )

        except Exception as e:
            logger.warning(f"Failed to record telemetry: {e}")

    def get_service_stats(self) -> dict:
        """Get detailed statistics for all services"""
        stats = {}

        for service_name, metrics in self.service_metrics.items():
            circuit_breaker = self.circuit_breakers.get(service_name)

            stats[service_name] = {
                "total_requests": metrics.total_requests,
                "failed_requests": metrics.failed_requests,
                "failure_rate": f"{metrics.failure_rate * 100:.2f}%",
                "average_latency_ms": f"{metrics.average_latency_ms:.2f}",
                "consecutive_failures": metrics.consecutive_failures,
                "circuit_breaker_state": circuit_breaker.state if circuit_breaker else "none",
                "last_request": metrics.last_request_time.isoformat() if metrics.last_request_time else None,
                "last_failure": metrics.last_failure_time.isoformat() if metrics.last_failure_time else None
            }

        return stats

    async def get_available_models(self, handler_name: str = "default") -> List[str]:
        """Get list of available LLM models"""
        service = await self.get_service(
            handler_name=handler_name,
            required_capabilities=["get_available_models"]
        )

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
            return capabilities.supports_operation_list if hasattr(capabilities, 'supports_operation_list') else []
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

    def get_stats(self) -> dict:
        """Get bus statistics including service stats"""
        base_stats = super().get_stats()
        base_stats["service_stats"] = self.get_service_stats()
        base_stats["distribution_strategy"] = self.distribution_strategy.value
        return base_stats

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
