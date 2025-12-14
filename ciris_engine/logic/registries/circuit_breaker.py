"""
Circuit Breaker Pattern Implementation

Provides fault tolerance by monitoring service failures and temporarily
disabling failing services to prevent cascading failures.
"""

import logging
import threading
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
    recovery_timeout: float = 10.0  # Reduced from 60s for faster mobile recovery
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

        # Thread synchronization for time calculations
        self._lock = threading.Lock()

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
        self.consecutive_failures += 1

        # Only update failure_count and last_failure_time when NOT already OPEN
        # This prevents resetting the recovery timer while the circuit breaker is open
        if self.state != CircuitState.OPEN:
            self.failure_count += 1
            self.last_failure_time = time.time()

        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to_open()
        elif self.state == CircuitState.HALF_OPEN:
            self._transition_to_open()

    def force_open(self, custom_timeout: Optional[float] = None, reason: str = "forced") -> None:
        """Force the circuit breaker open immediately, bypassing failure threshold.

        This is used for critical errors like billing/auth failures where we want
        to immediately stop making requests without waiting for failure_threshold.

        Args:
            custom_timeout: Optional longer timeout for recovery (e.g., 300 for billing errors).
                           If provided, overrides config.recovery_timeout until reset.
            reason: Reason for forcing open (for logging)
        """
        self.total_calls += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.failure_count = self.config.failure_threshold  # Ensure threshold is met
        self.last_failure_time = time.time()

        # Store original timeout and set custom timeout if provided
        if custom_timeout is not None:
            if not hasattr(self, "_original_recovery_timeout"):
                self._original_recovery_timeout = self.config.recovery_timeout
            self.config.recovery_timeout = custom_timeout
            logger.warning(
                f"Circuit breaker '{self.name}' recovery timeout extended to {custom_timeout}s "
                f"(was {self._original_recovery_timeout}s) due to: {reason}"
            )

        self._transition_to_open()
        logger.warning(f"Circuit breaker '{self.name}' FORCE OPENED: {reason}")

    def _transition_to_open(self) -> None:
        """Transition to OPEN state (service disabled)"""
        with self._lock:
            self.state = CircuitState.OPEN
            self.success_count = 0
            self.state_transitions += 1
            self.total_trips += 1  # Count trip events
            self.last_open_time = time.time()
        logger.warning(f"Circuit breaker '{self.name}' opened due to {self.failure_count} failures")

    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state (testing recovery)"""
        with self._lock:
            # Track time spent in open state (thread-safe)
            if self.last_open_time:
                current_time = time.time()
                open_duration = current_time - self.last_open_time
                # Ensure no negative durations due to race conditions
                if open_duration >= 0:
                    self.time_in_open_state += open_duration
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
        last_failure_age = 0.0
        if self.last_failure_time:
            last_failure_age = time.time() - self.last_failure_time

        # Calculate current time in open state if currently open (thread-safe)
        current_open_duration = 0.0
        with self._lock:
            if self.state == CircuitState.OPEN and self.last_open_time:
                open_duration = time.time() - self.last_open_time
                # Ensure no negative durations
                current_open_duration = max(0.0, open_duration)

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
        """Get all circuit breaker metrics including detailed stats."""
        # Get detailed stats
        stats = self.get_stats()

        # Convert state to numeric: 0=closed, 1=open, 0.5=half-open
        state_value = 0.0
        if self.state == CircuitState.OPEN:
            state_value = 1.0
        elif self.state == CircuitState.HALF_OPEN:
            state_value = 0.5

        # Build metrics with service name prefix
        prefix = f"cb_{self.name}"

        return {
            f"{prefix}_state": state_value,
            f"{prefix}_total_calls": float(stats["call_count"]),
            f"{prefix}_total_failures": float(stats["total_failures"]),
            f"{prefix}_total_successes": float(stats["total_successes"]),
            f"{prefix}_success_rate": float(stats["success_rate"]),
            f"{prefix}_consecutive_failures": float(stats["consecutive_failures"]),
            f"{prefix}_recovery_attempts": float(stats["recovery_attempts"]),
            f"{prefix}_state_transitions": float(stats["state_transitions"]),
            f"{prefix}_time_in_open_state_sec": float(stats["time_in_open_state"]),
            f"{prefix}_last_failure_age_sec": float(stats["last_failure_age"]),
            # Also include v1.4.3 metrics without prefix
            "circuit_breaker_trips": float(self.total_trips),
            "circuit_breaker_resets": float(self.total_resets),
            "circuit_breaker_state": state_value,
            "circuit_breaker_failures": float(self.total_failures),
        }
