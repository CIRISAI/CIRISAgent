"""
Observability decorators for CIRIS services.

Provides AOP-style decorators for debugging, tracing, and performance monitoring
that integrate with CIRIS's existing telemetry infrastructure.
"""

import asyncio
import functools
import inspect
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, TypeVar, Union
from uuid import uuid4

from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
    TraceContext,
)

logger = logging.getLogger(__name__)

# Type variable for decorated functions
F = TypeVar("F", bound=Callable[..., Any])

# Semaphore to limit concurrent telemetry tasks
TELEMETRY_TASK_SEMAPHORE = asyncio.Semaphore(100)


def _prepare_log_context(
    func: Callable, self: Any, args: Any, kwargs: Any, service_name: str, message_template: Optional[str]
) -> Dict[str, Any]:
    """Extract common logging context preparation logic."""
    if message_template:
        # Bind arguments to parameter names
        sig = inspect.signature(func)
        bound_args = sig.bind(self, *args, **kwargs)
        bound_args.apply_defaults()

        # Format message with parameters
        format_dict = dict(bound_args.arguments)
        format_dict.pop("self", None)

        # Add special variables
        format_dict["method_name"] = func.__name__
        format_dict["service_name"] = service_name

        try:
            log_message = f"[{service_name.upper()} DEBUG] {message_template.format(**format_dict)}"
        except KeyError as e:
            log_message = f"[{service_name.upper()} DEBUG] {func.__name__} called (template error: {e})"
    else:
        # Default message
        log_message = f"[{service_name.upper()} DEBUG] {func.__name__} called"

    return {"log_message": log_message, "method_name": func.__name__, "service_name": service_name}


def _log_execution_result(
    logger_instance: Any,
    service_name: str,
    method_name: str,
    start_time: float,
    result: Any,
    include_result: bool,
    log_level: str = "DEBUG",
) -> None:
    """Log execution result with timing."""
    if include_result:
        elapsed_ms = (time.time() - start_time) * 1000
        result_str = str(result)[:200] if result is not None else "None"
        log_method = getattr(logger_instance, log_level.lower(), logger_instance.debug)
        log_method(
            f"[{service_name.upper()} DEBUG] {method_name} completed in {elapsed_ms:.2f}ms, " f"result: {result_str}"
        )


def _log_execution_error(
    logger_instance: Any, service_name: str, method_name: str, start_time: float, error: Exception
) -> None:
    """Log execution error with timing."""
    elapsed_ms = (time.time() - start_time) * 1000
    logger_instance.error(f"[{service_name.upper()} DEBUG] {method_name} failed after {elapsed_ms:.2f}ms: {error}")


def _get_debug_env_var(service_name: str) -> bool:
    """Check if debug mode is enabled for a service."""
    env_var = f"CIRIS_{service_name.upper()}_DEBUG"
    return os.getenv(env_var, "").lower() in ("true", "1", "yes")


def _extract_service_name(instance: Any) -> str:
    """Extract service name from instance."""
    # Try common patterns
    if hasattr(instance, "service_name"):
        return instance.service_name
    elif hasattr(instance, "__class__"):
        class_name = instance.__class__.__name__
        # Remove common suffixes
        for suffix in ["Service", "Handler", "Manager"]:
            if class_name.endswith(suffix):
                return class_name[: -len(suffix)]
        return class_name
    return "unknown"


def trace_span(
    span_name: Optional[str] = None, span_kind: str = "internal", capture_args: bool = True
) -> Callable[[F], F]:
    """
    Create a trace span for the decorated method.

    Integrates with CIRIS's correlation_id and trace_context system.

    Args:
        span_name: Optional custom span name (defaults to method name)
        span_kind: Type of span (internal, client, server)
        capture_args: Whether to capture method arguments in span
    """

    def decorator(func: F) -> F:
        actual_span_name = span_name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            # Generate span ID
            span_id = str(uuid4())

            # Try to get correlation context from self or kwargs
            correlation_id = None
            trace_context = None

            if hasattr(self, "correlation_id"):
                correlation_id = self.correlation_id
            elif "correlation_id" in kwargs:
                correlation_id = kwargs["correlation_id"]
            else:
                correlation_id = str(uuid4())

            if hasattr(self, "trace_context"):
                trace_context = self.trace_context
            elif "trace_context" in kwargs:
                trace_context = kwargs["trace_context"]

            # Create trace context for this span
            if trace_context and isinstance(trace_context, dict):
                parent_span_id = trace_context.get("span_id")
                trace_id = trace_context.get("trace_id", str(uuid4()))
            else:
                parent_span_id = None
                trace_id = str(uuid4())

            new_trace_context = TraceContext(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                span_name=actual_span_name,
                span_kind=span_kind,
            )

            # Capture request data
            request_data = None
            if capture_args:
                # Convert args to string representation for storage
                params = {}
                sig = inspect.signature(func)
                bound_args = sig.bind(self, *args, **kwargs)
                bound_args.apply_defaults()

                for param_name, param_value in bound_args.arguments.items():
                    if param_name != "self":
                        params[param_name] = str(param_value)[:200]  # Limit length

                request_data = ServiceRequestData(
                    service_type=_extract_service_name(self),
                    method_name=actual_span_name,
                    parameters=params,
                    request_timestamp=datetime.now(timezone.utc),
                )

            # Create correlation record
            correlation = ServiceCorrelation(
                correlation_id=correlation_id,
                correlation_type=CorrelationType.TRACE_SPAN,
                service_type=_extract_service_name(self),
                handler_name=self.__class__.__name__,
                action_type=actual_span_name,
                request_data=request_data,
                trace_context=new_trace_context,
                status=ServiceCorrelationStatus.PENDING,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                timestamp=datetime.now(timezone.utc),
            )

            start_time = time.time()
            try:
                # Execute the actual method
                result = await func(self, *args, **kwargs)

                # Update correlation with success
                correlation.status = ServiceCorrelationStatus.COMPLETED
                correlation.response_data = ServiceResponseData(
                    success=True,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    response_timestamp=datetime.now(timezone.utc),
                )

                return result
            except Exception as e:
                # Update correlation with failure
                correlation.status = ServiceCorrelationStatus.FAILED
                correlation.response_data = ServiceResponseData(
                    success=False,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    execution_time_ms=(time.time() - start_time) * 1000,
                    response_timestamp=datetime.now(timezone.utc),
                )
                raise
            finally:
                # Store correlation if we have access to telemetry
                if hasattr(self, "_telemetry_service"):
                    try:

                        async def bounded_store_correlation(telemetry_service, correlation):
                            async with TELEMETRY_TASK_SEMAPHORE:
                                await telemetry_service._store_correlation(correlation)

                        # Store asynchronously with bounded concurrency
                        task = asyncio.create_task(bounded_store_correlation(self._telemetry_service, correlation))
                        # Fire and forget - we don't await the task
                        task.add_done_callback(lambda t: None)  # Suppress warnings
                    except Exception:
                        pass  # Don't fail the method if telemetry fails

        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            # For sync methods, we can't create correlations but we can log
            logger.debug(f"Trace span: {actual_span_name} (sync method, correlation disabled)")
            return func(self, *args, **kwargs)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore

    return decorator


def debug_log(
    message_template: Optional[str] = None,
    log_level: str = "DEBUG",
    include_result: bool = False,
    service_name_override: Optional[str] = None,
) -> Callable[[F], F]:
    """
    Add debug logging to a method, respecting CIRIS_*_DEBUG environment variables.

    Args:
        message_template: Optional template for log message (can use {param_name} placeholders)
        log_level: Log level to use (DEBUG, INFO, WARNING, ERROR)
        include_result: Whether to log the method's return value
        service_name_override: Override service name detection
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            service_name = service_name_override or _extract_service_name(self)

            # Check if debug mode is enabled
            if not _get_debug_env_var(service_name):
                # Debug mode not enabled, just execute the method
                return await func(self, *args, **kwargs)

            # Get logger
            method_logger = getattr(self, "_logger", logger)

            # Prepare log context
            context = _prepare_log_context(func, self, args, kwargs, service_name, message_template)

            # Log the call
            log_method = getattr(method_logger, log_level.lower(), method_logger.debug)
            log_method(context["log_message"])

            # Execute the method
            start_time = time.time()
            try:
                result = await func(self, *args, **kwargs)
                _log_execution_result(
                    method_logger, service_name, func.__name__, start_time, result, include_result, log_level
                )
                return result
            except Exception as e:
                _log_execution_error(method_logger, service_name, func.__name__, start_time, e)
                raise

        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            service_name = service_name_override or _extract_service_name(self)

            # Check if debug mode is enabled
            if not _get_debug_env_var(service_name):
                # Debug mode not enabled, just execute the method
                return func(self, *args, **kwargs)

            # Get logger
            method_logger = getattr(self, "_logger", logger)

            # Prepare log context - reuse common function
            context = _prepare_log_context(func, self, args, kwargs, service_name, message_template)

            # Log the call
            log_method = getattr(method_logger, log_level.lower(), method_logger.debug)
            log_method(context["log_message"])

            # Execute the method
            start_time = time.time()
            try:
                result = func(self, *args, **kwargs)
                _log_execution_result(
                    method_logger, service_name, func.__name__, start_time, result, include_result, log_level
                )
                return result
            except Exception as e:
                _log_execution_error(method_logger, service_name, func.__name__, start_time, e)
                raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore

    return decorator


def measure_performance(
    metric_name: Optional[str] = None,
    path_type: Optional[str] = None,  # hot, cold, critical
    record_distribution: bool = False,
) -> Callable[[F], F]:
    """
    Measure method performance and record metrics.

    Args:
        metric_name: Custom metric name (defaults to method name)
        path_type: Type of code path (hot, cold, critical)
        record_distribution: Whether to record timing distribution
    """

    def decorator(func: F) -> F:
        actual_metric_name = metric_name or f"{func.__name__}_duration_ms"

        @functools.wraps(func)
        async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            start_time = time.time()

            try:
                result = await func(self, *args, **kwargs)
                success = True
                return result
            except Exception:
                success = False
                raise
            finally:
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000

                # Try to record metric if telemetry service is available
                if hasattr(self, "_telemetry_service") and self._telemetry_service:
                    try:
                        service_name = _extract_service_name(self)

                        # Record the metric
                        await self._telemetry_service.record_metric(
                            metric_name=f"{service_name}.{actual_metric_name}",
                            value=duration_ms,
                            tags={"method": func.__name__, "success": str(success), "service": service_name},
                            path_type=path_type,
                            source_module=func.__module__,
                        )

                        # Record success/failure count
                        status_metric = f"{service_name}.{func.__name__}_{'success' if success else 'failure'}"
                        await self._telemetry_service.record_metric(
                            metric_name=status_metric,
                            value=1.0,
                            tags={"service": service_name},
                            path_type=path_type,
                            source_module=func.__module__,
                        )
                    except Exception:
                        pass  # Don't fail the method if metrics fail

        @functools.wraps(func)
        def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            # For sync methods, we can still measure but may not be able to record
            start_time = time.time()

            try:
                result = func(self, *args, **kwargs)
                success = True
                return result
            except Exception:
                success = False
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000

                # Log performance for sync methods
                service_name = _extract_service_name(self)
                logger.debug(f"{service_name}.{func.__name__} took {duration_ms:.2f}ms " f"(success={success})")

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore

    return decorator


# Convenience combined decorator
def observable(
    trace: bool = True,
    debug: bool = True,
    measure: bool = True,
    debug_message: Optional[str] = None,
    path_type: Optional[str] = None,
) -> Callable[[F], F]:
    """
    Convenience decorator that combines tracing, debugging, and measurement.

    Args:
        trace: Whether to create trace spans
        debug: Whether to add debug logging
        measure: Whether to measure performance
        debug_message: Optional debug message template
        path_type: Type of code path for metrics
    """

    def decorator(func: F) -> F:
        # Apply decorators in order
        if measure:
            func = measure_performance(path_type=path_type)(func)
        if debug:
            func = debug_log(message_template=debug_message)(func)
        if trace:
            func = trace_span()(func)
        return func

    return decorator
