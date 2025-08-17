"""
Circuit Breaker Pattern Implementation

Provides fault tolerance by monitoring service failures and temporarily
disabling failing services to prevent cascading failures.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open and service is unavailable"""


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Service disabled due to failures
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 3
    timeout_duration: float = 30.0


class CircuitBreaker:
    """
    Circuit breaker implementation for service resilience.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service disabled, requests fail fast
    - HALF_OPEN: Testing recovery, limited requests allowed
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None

        # Additional metrics tracking
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        self.state_transitions = 0
        self.time_in_open_state = 0.0
        self.last_open_time: Optional[float] = None
        self.recovery_attempts = 0
        self.consecutive_failures = 0

        # v1.4.3 specific metrics
        self.total_trips = 0  # Count of transitions to OPEN state
        self.total_resets = 0  # Count of transitions to CLOSED state

        logger.debug(f"Circuit breaker '{name}' initialized")

    def is_available(self) -> bool:
        """Check if the service is available for requests"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if self.last_failure_time and time.time() - self.last_failure_time >= self.config.recovery_timeout:
                self._transition_to_half_open()
                return True
            return False

        # CircuitState.HALF_OPEN case
        # Allow limited requests in half-open state
        return True

    def check_and_raise(self) -> None:
        """Check if service is available, raise CircuitBreakerError if not"""
        if not self.is_available():
            raise CircuitBreakerError(f"Circuit breaker '{self.name}' is {self.state.value}, service unavailable")

    def record_success(self) -> None:
        """Record a successful operation"""
        self.total_calls += 1
        self.total_successes += 1
        self.consecutive_failures = 0  # Reset consecutive failures

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed operation"""
        self.total_calls += 1
        self.total_failures += 1
        self.failure_count += 1
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to_open()
        elif self.state == CircuitState.HALF_OPEN:
            self._transition_to_open()

    def _transition_to_open(self) -> None:
        """Transition to OPEN state (service disabled)"""
        self.state = CircuitState.OPEN
        self.success_count = 0
        self.state_transitions += 1
        self.total_trips += 1  # Count trip events
        self.last_open_time = time.time()
        logger.warning(f"Circuit breaker '{self.name}' opened due to {self.failure_count} failures")

    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state (testing recovery)"""
        # Track time spent in open state
        if self.last_open_time:
            self.time_in_open_state += time.time() - self.last_open_time
            self.last_open_time = None

        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        self.state_transitions += 1
        self.recovery_attempts += 1
        logger.info(f"Circuit breaker '{self.name}' transitioning to half-open for recovery testing")

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state (normal operation)"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.state_transitions += 1
        self.total_resets += 1  # Count reset events
        self.consecutive_failures = 0
        logger.info(f"Circuit breaker '{self.name}' closed - service recovered")

    def get_stats(self) -> dict[str, Any]:
        """Get current circuit breaker statistics"""
        # Calculate success rate
        success_rate = 1.0
        if self.total_calls > 0:
            success_rate = self.total_successes / self.total_calls

        # Calculate last failure age
        last_failure_age = 0
        if self.last_failure_time:
            last_failure_age = time.time() - self.last_failure_time

        # Calculate current time in open state if currently open
        current_open_duration = 0.0
        if self.state == CircuitState.OPEN and self.last_open_time:
            current_open_duration = time.time() - self.last_open_time

        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "call_count": self.total_calls,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "success_rate": success_rate,
            "consecutive_failures": self.consecutive_failures,
            "recovery_attempts": self.recovery_attempts,
            "state_transitions": self.state_transitions,
            "time_in_open_state": self.time_in_open_state + current_open_duration,
            "last_failure_age": last_failure_age,
        }

    def reset(self) -> None:
        """Reset circuit breaker to initial state"""
        if self.state != CircuitState.CLOSED:
            self.total_resets += 1  # Count manual reset as a reset event
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        logger.info(f"Circuit breaker '{self.name}' manually reset")

    def get_metrics(self) -> dict[str, float]:
        """Get circuit breaker metrics for v1.4.3 telemetry set."""
        # Convert state to numeric: 0=closed, 1=open, 2=half-open
        state_value = 0.0
        if self.state == CircuitState.OPEN:
            state_value = 1.0
        elif self.state == CircuitState.HALF_OPEN:
            state_value = 2.0

        return {
            "circuit_breaker_trips": float(self.total_trips),
            "circuit_breaker_resets": float(self.total_resets),
            "circuit_breaker_state": state_value,
            "circuit_breaker_failures": float(self.total_failures),
        }
