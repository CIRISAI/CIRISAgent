import asyncio
import logging
import secrets
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Service(ABC):
    """Abstract base class for pluggable services within the CIRIS Engine."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        """
        Initialize the service.

        Args:
            config: Optional configuration dictionary specific to the service.
        """
        super().__init__()  # Properly initialize the ABC for Python 3.12 compatibility
        self.config = config or {}
        self.service_name = self.__class__.__name__  # Default name
        logger.info(f"Initializing service: {self.service_name}")

    @abstractmethod
    async def start(self) -> None:
        """Starts the service and any background tasks it manages."""
        logger.info(f"Starting service: {self.service_name}")

    @abstractmethod
    async def stop(self) -> None:
        """Stops the service and cleans up resources."""
        logger.info(f"Stopping service: {self.service_name}")

    async def retry_with_backoff(
        self,
        operation: Callable[..., T],
        *args: Any,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_multiplier: float = 2.0,
        jitter_range: float = 0.25,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
        non_retryable_exceptions: tuple[type[Exception], ...] = (),
        **kwargs: Any,
    ) -> T:
        """
        Retry an operation with exponential backoff and jitter.

        Args:
            operation: The async or sync function to retry
            *args, **kwargs: Arguments to pass to the operation
            max_retries: Maximum number of retry attempts (default: 3)
            base_delay: Starting delay in seconds (default: 1.0)
            max_delay: Maximum delay cap in seconds (default: 60.0)
            backoff_multiplier: Exponential backoff multiplier (default: 2.0)
            jitter_range: Jitter as percentage of delay (±25% default)
            retryable_exceptions: Tuple of exceptions that should trigger retries
            non_retryable_exceptions: Tuple of exceptions that should never retry

        Returns:
            The result of the operation

        Raises:
            The last exception if all retries fail
        """
        last_exception = None

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                if attempt > 0:
                    # Calculate exponential backoff with jitter
                    delay = min(base_delay * (backoff_multiplier ** (attempt - 1)), max_delay)
                    # Add jitter (±jitter_range% of delay) to avoid thundering herd
                    rand_fraction = secrets.randbits(53) / float(1 << 53)
                    jitter = delay * jitter_range * (2 * rand_fraction - 1)
                    final_delay = max(0.1, delay + jitter)

                    logger.info(
                        f"{self.service_name}: Retrying operation (attempt {attempt + 1}/{max_retries + 1}) "
                        f"after {final_delay:.2f}s delay"
                    )
                    await asyncio.sleep(final_delay)

                # Handle both async and sync operations
                # Note: Cannot avoid cast here - mypy can't infer T from operation signature
                if asyncio.iscoroutinefunction(operation):
                    result = await operation(*args, **kwargs)
                else:
                    result = operation(*args, **kwargs)
                return cast(T, result)

            except non_retryable_exceptions as e:
                logger.error(f"{self.service_name}: Non-retryable error, failing immediately: {e}")
                raise

            except retryable_exceptions as e:
                last_exception = e
                if attempt < max_retries:
                    logger.warning(f"{self.service_name}: Retryable error on attempt {attempt + 1}: {e}")
                else:
                    logger.error(f"{self.service_name}: All {max_retries + 1} attempts failed. Last error: {e}")

        # If we get here, all retries failed
        raise last_exception if last_exception else RuntimeError(f"{self.service_name}: All retry attempts failed")

    def get_retry_config(self, operation_type: str = "default") -> dict[str, Any]:
        """
        Get retry configuration from service config.

        Args:
            operation_type: Type of operation (e.g., "api_call", "database", "network")

        Returns:
            Dictionary with retry configuration parameters
        """
        retry_config = self.config.get("retry", {})
        operation_config = retry_config.get(operation_type, {})

        # Default retry configuration
        defaults = {
            "max_retries": 3,
            "base_delay": 1.0,
            "max_delay": 60.0,
            "backoff_multiplier": 2.0,
            "jitter_range": 0.25,
        }

        # Merge defaults with config
        result = {**defaults, **retry_config.get("global", {}), **operation_config}
        return result

    # Note: get_status() is NOT defined in base class
    # Each service protocol defines its own typed status return
    # This follows "No Untyped Dicts, No Bypass Patterns, No Exceptions" philosophy

    def __repr__(self) -> str:
        return f"<{self.service_name}>"
