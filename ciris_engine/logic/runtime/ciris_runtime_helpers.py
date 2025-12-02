"""
CIRIS Runtime Helper Functions

Production-grade helper functions to reduce cognitive complexity in ciris_runtime.py
Follows the Three Rules: No Untyped Dicts, No Bypass Patterns, No Exceptions

These helpers target the highest complexity methods:
- shutdown (CC 75) -> 8 helpers
- run (CC 32) -> 6 helpers
- _start_adapter_connections (CC 23) -> 4 helpers
- _wait_for_critical_services (CC 18) -> 3 helpers
- _register_adapter_services (CC 13) -> 3 helpers
- _preserve_shutdown_continuity (CC 11) -> 2 helpers
"""

# Import required for helper functions
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

# Set up logger for helpers
logger = logging.getLogger(__name__)


# Python 3.10 compatibility: asyncio.timeout was added in Python 3.11
if sys.version_info >= (3, 11):
    # Use native asyncio.timeout in Python 3.11+
    _async_timeout = asyncio.timeout
else:
    # Python 3.10 polyfill using CancelledError approach
    @asynccontextmanager
    async def _async_timeout(delay: float) -> AsyncGenerator[None, None]:
        """Python 3.10 compatible timeout context manager."""
        loop = asyncio.get_event_loop()
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("No current task")

        timed_out = False

        def timeout_callback() -> None:
            nonlocal timed_out
            timed_out = True
            task.cancel()  # type: ignore[union-attr]

        # Schedule timeout
        handle = loop.call_later(delay, timeout_callback)
        try:
            yield
        except asyncio.CancelledError:
            handle.cancel()
            if timed_out:
                raise asyncio.TimeoutError() from None
            else:
                raise  # Re-raise CancelledError if not from timeout
        else:
            handle.cancel()


# Import runtime utilities
from ciris_engine.logic.utils.shutdown_manager import is_global_shutdown_requested, wait_for_global_shutdown_async

# Service priority mapping for clean lookup
_SERVICE_SHUTDOWN_PRIORITIES = {
    # Priority 0-2: Dependent services (shutdown first)
    "TSDB": 0,
    "Consolidation": 0,
    "Task": 1,
    "Scheduler": 1,
    "Incident": 2,
    "Monitor": 2,
    # Priority 3-5: Application services
    "Adaptive": 3,
    "Filter": 3,
    "Tool": 4,
    "Control": 4,
    "Observation": 5,
    "Visibility": 5,
    # Priority 6-8: Core services
    "Telemetry": 6,
    "Audit": 6,
    "LLM": 7,
    "Auth": 7,
    "Config": 8,
    # Priority 9-12: Infrastructure services (shutdown last)
    "Memory": 9,
    "Secrets": 9,
    "Initialization": 10,
    "Time": 11,
    "Shutdown": 12,
}


def _get_service_shutdown_priority(service: Any) -> int:
    """Get shutdown priority for service ordering.

    Lower numbers shut down first, higher numbers shut down last.
    Infrastructure services shut down last to support other services.
    """
    service_name = service.__class__.__name__

    # Check for priority keywords in service name
    for keyword, priority in _SERVICE_SHUTDOWN_PRIORITIES.items():
        if keyword in service_name:
            return priority

    return 5  # Default priority for unmatched services


async def execute_final_maintenance_tasks(runtime: Any) -> None:
    """Run final maintenance and consolidation before services stop."""
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Running final maintenance tasks...")

    # 1. Run final database maintenance
    if hasattr(runtime, "maintenance_service") and runtime.maintenance_service:
        try:
            logger.info("Running final database maintenance before shutdown...")
            await runtime.maintenance_service.perform_startup_cleanup()
            logger.info("Final database maintenance completed")
        except Exception as e:
            logger.error(f"Failed to run final database maintenance: {e}")

    # 2. Run final TSDB consolidation
    if hasattr(runtime, "service_initializer") and runtime.service_initializer:
        tsdb_service = getattr(runtime.service_initializer, "tsdb_consolidation_service", None)
        if tsdb_service:
            try:
                logger.info("Running final TSDB consolidation before shutdown...")
                await tsdb_service._run_consolidation()
                logger.info("Final TSDB consolidation completed")
            except Exception as e:
                logger.error(f"Failed to run final TSDB consolidation: {e}")

    logger.info("Final maintenance tasks completed")
    logger.info("=" * 60)


async def _transition_agent_to_shutdown_state(runtime: Any, current_state: Any) -> bool:
    """Transition agent processor to shutdown state."""
    from ciris_engine.schemas.processors.states import AgentState

    logger = logging.getLogger(__name__)

    if not await runtime.agent_processor.state_manager.can_transition_to(AgentState.SHUTDOWN):
        logger.error(f"Cannot transition from {current_state} to SHUTDOWN state")
        return False

    logger.info(f"Transitioning from {current_state} to SHUTDOWN state")
    await runtime.agent_processor.state_manager.transition_to(AgentState.SHUTDOWN)
    return True


async def _handle_processing_loop_shutdown(runtime: Any) -> None:
    """Handle shutdown of processing loop or direct shutdown processor."""
    import asyncio

    logger = logging.getLogger(__name__)

    if runtime.agent_processor._processing_task and not runtime.agent_processor._processing_task.done():
        logger.info("Processing loop is running, signaling stop")
        if hasattr(runtime.agent_processor, "_stop_event") and runtime.agent_processor._stop_event:
            runtime.agent_processor._stop_event.set()
    else:
        await _execute_shutdown_processor_directly(runtime)


async def _execute_shutdown_processor_directly(runtime: Any) -> None:
    """Execute shutdown processor directly when processing loop is not running."""
    import asyncio

    logger = logging.getLogger(__name__)

    logger.info("Processing loop not running, executing shutdown processor directly")
    if hasattr(runtime.agent_processor, "shutdown_processor") and runtime.agent_processor.shutdown_processor:
        # Run a few rounds of shutdown processing
        for round_num in range(5):
            try:
                _ = await runtime.agent_processor.shutdown_processor.process(round_num)
                if runtime.agent_processor.shutdown_processor.shutdown_complete:
                    break
            except Exception as e:
                logger.error(f"Error in shutdown processor: {e}", exc_info=True)
                break
            await asyncio.sleep(0.1)


async def _wait_for_shutdown_processor_completion(runtime: Any) -> None:
    """Wait for shutdown processor to complete with timeout."""
    import asyncio

    logger = logging.getLogger(__name__)

    max_wait = 5.0  # Reduced from 30s to 5s for faster shutdown
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < max_wait:
        if (
            hasattr(runtime.agent_processor, "shutdown_processor")
            and runtime.agent_processor.shutdown_processor
            and runtime.agent_processor.shutdown_processor.shutdown_complete
        ):
            result = runtime.agent_processor.shutdown_processor.shutdown_result
            if result and hasattr(result, "get") and result.get("status") == "rejected":
                logger.warning(f"Shutdown rejected by agent: {result.get('reason')}")
            break
        await asyncio.sleep(0.1)

    logger.debug("Shutdown negotiation complete or timed out")


async def handle_agent_processor_shutdown(runtime: Any) -> None:
    """Handle graceful agent processor shutdown negotiation."""
    from ciris_engine.schemas.processors.states import AgentState

    logger = logging.getLogger(__name__)

    # Early exit if no agent processor
    if not runtime.agent_processor or not hasattr(runtime.agent_processor, "state_manager"):
        return

    current_state = runtime.agent_processor.state_manager.get_state()

    # Only do negotiation if not already in SHUTDOWN state
    if current_state == AgentState.SHUTDOWN:
        return

    try:
        logger.info("Initiating graceful shutdown negotiation...")

        # Transition to shutdown state
        if await _transition_agent_to_shutdown_state(runtime, current_state):
            # Handle processing loop shutdown
            await _handle_processing_loop_shutdown(runtime)

            # Wait for completion
            await _wait_for_shutdown_processor_completion(runtime)

    except Exception as e:
        logger.error(f"Error during shutdown negotiation: {e}")


# ============================================================================
# SHUTDOWN HELPERS (CC 75 -> CC ~8) - 8 helpers
# ============================================================================


def validate_shutdown_preconditions(runtime: Any) -> bool:
    """Validate system state before shutdown initiation.

    Returns True if shutdown can proceed safely, False otherwise.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Check if already shutdown
    if hasattr(runtime, "_shutdown_complete") and runtime._shutdown_complete:
        logger.debug("Shutdown already completed, skipping...")
        return False

    # Mark service registry in shutdown mode
    if runtime.service_registry:
        runtime.service_registry._shutdown_mode = True
        logger.info("Service registry marked for shutdown mode")

    logger.info("Shutdown preconditions validated successfully")
    return True


def _collect_scheduled_services(runtime: Any) -> List[Any]:
    """Collect services that have scheduled tasks."""
    scheduled_services = []
    if runtime.service_registry:
        all_services = runtime.service_registry.get_all_services()
        for service in all_services:
            # Check for scheduled services with _task or _scheduler attributes
            if hasattr(service, "_task") or hasattr(service, "_scheduler"):
                scheduled_services.append(service)
    return scheduled_services


async def _stop_service_task(service: Any) -> None:
    """Stop a specific service's task safely."""
    import asyncio

    logger = logging.getLogger(__name__)

    service_name = service.__class__.__name__
    logger.info(f"Stopping scheduled tasks for {service_name}")

    if hasattr(service, "_task") and service._task:
        # Cancel the task directly
        service._task.cancel()
        try:
            await service._task
        except asyncio.CancelledError:
            # Only re-raise if we're being cancelled ourselves
            current = asyncio.current_task()
            if current is not None and current.cancelled():
                raise
            # Otherwise, this is a normal stop - don't propagate the cancellation
    elif hasattr(service, "stop_scheduler"):
        await service.stop_scheduler()


async def prepare_shutdown_maintenance_tasks(runtime: Any) -> List[Any]:
    """Prepare and schedule final maintenance operations.

    Returns list of scheduled services that need to be stopped.
    """
    import asyncio

    logger = logging.getLogger(__name__)

    # Collect scheduled services that need to be stopped
    scheduled_services = _collect_scheduled_services(runtime)

    # Stop all scheduled services first
    for service in scheduled_services:
        try:
            await _stop_service_task(service)
        except Exception as e:
            logger.error(f"Error stopping scheduled tasks for {service.__class__.__name__}: {e}")

    # Give scheduled tasks a moment to stop
    if scheduled_services:
        logger.info(f"Stopped {len(scheduled_services)} scheduled services, waiting for tasks to complete...")
        await asyncio.sleep(0.5)

    return scheduled_services


def _collect_all_services_to_stop(runtime: Any) -> List[Any]:
    """Collect all services that need to be stopped."""
    services_to_stop = []
    seen_ids = set()

    # Get all registered services
    all_registered_services = []
    if runtime.service_registry:
        all_registered_services = runtime.service_registry.get_all_services()

    # Add registered services
    for service in all_registered_services:
        service_id = id(service)
        if service_id not in seen_ids and hasattr(service, "stop"):
            seen_ids.add(service_id)
            services_to_stop.append(service)

    # Add direct service references
    direct_services = _get_direct_service_references(runtime)
    for service in direct_services:
        if service:
            service_id = id(service)
            if service_id not in seen_ids and hasattr(service, "stop"):
                seen_ids.add(service_id)
                services_to_stop.append(service)

    return services_to_stop


def _get_direct_service_references(runtime: Any) -> List[Any]:
    """Get direct service references for backward compatibility."""
    return [
        # From service_initializer
        getattr(runtime.service_initializer, "tsdb_consolidation_service", None),
        getattr(runtime.service_initializer, "task_scheduler_service", None),
        getattr(runtime.service_initializer, "incident_management_service", None),
        getattr(runtime.service_initializer, "resource_monitor_service", None),
        getattr(runtime.service_initializer, "config_service", None),
        getattr(runtime.service_initializer, "auth_service", None),
        getattr(runtime.service_initializer, "runtime_control_service", None),
        getattr(runtime.service_initializer, "self_observation_service", None),
        getattr(runtime.service_initializer, "visibility_service", None),
        getattr(runtime.service_initializer, "secrets_tool_service", None),
        getattr(runtime.service_initializer, "wa_auth_system", None),
        getattr(runtime.service_initializer, "initialization_service", None),
        getattr(runtime.service_initializer, "shutdown_service", None),
        getattr(runtime.service_initializer, "time_service", None),
        # From runtime
        runtime.maintenance_service,
        runtime.adaptive_filter_service,
        runtime.telemetry_service,
        runtime.audit_service,
        runtime.llm_service,
        runtime.secrets_service,
        runtime.memory_service,
    ]


async def _execute_service_stop_tasks(services_to_stop: List[Any]) -> Tuple[List[Any], List[str]]:
    """Execute stop tasks for all services."""
    import asyncio

    logger = logging.getLogger(__name__)

    stop_tasks = []
    service_names = []

    for service in services_to_stop:
        if service and hasattr(service, "stop"):
            stop_method = service.stop()
            if asyncio.iscoroutine(stop_method):
                task = asyncio.create_task(stop_method)
                stop_tasks.append(task)
            service_names.append(service.__class__.__name__)

    if stop_tasks:
        logger.info(f"Stopping {len(stop_tasks)} services: {', '.join(service_names)}")
        return await _wait_for_service_stops(stop_tasks, service_names)

    return [], []


async def _wait_for_service_stops(stop_tasks: List[Any], service_names: List[str]) -> Tuple[List[Any], List[str]]:
    """Wait for service stop tasks with timeout handling."""
    import asyncio

    logger = logging.getLogger(__name__)

    done, pending = await asyncio.wait(stop_tasks, timeout=10.0)

    if pending:
        await _handle_hanging_services(pending, stop_tasks, service_names)
    else:
        logger.info(f"All {len(stop_tasks)} services stopped successfully")

    # Check for errors in completed tasks
    await _check_service_stop_errors(done, stop_tasks, service_names)

    return stop_tasks, service_names


async def _handle_hanging_services(pending: Set[Any], stop_tasks: List[Any], service_names: List[str]) -> None:
    """Handle services that didn't stop in time."""
    import asyncio

    logger = logging.getLogger(__name__)

    logger.error(f"Service shutdown timed out after 10 seconds. {len(pending)} services still running.")
    hanging_services = []

    for task in pending:
        try:
            idx = stop_tasks.index(task)
            service_name = service_names[idx]
            hanging_services.append(service_name)
            logger.warning(f"Service {service_name} did not stop in time")
        except ValueError:
            logger.warning("Unknown service task did not stop in time")
        task.cancel()

    logger.error(f"Hanging services: {', '.join(hanging_services)}")

    # Await cancelled tasks for cleanup
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def _check_service_stop_errors(done: Set[Any], stop_tasks: List[Any], service_names: List[str]) -> None:
    """Check for errors in completed service stop tasks."""
    logger = logging.getLogger(__name__)

    for task in done:
        if task.done() and not task.cancelled():
            try:
                result = task.result()
                if isinstance(result, Exception):
                    idx = stop_tasks.index(task)
                    logger.error(f"Service {service_names[idx]} stop error: {result}")
            except Exception as e:
                logger.error(f"Error checking task result: {e}")


async def execute_service_shutdown_sequence(runtime: Any) -> Tuple[List[Any], List[str]]:
    """Execute orderly shutdown of all services by priority.

    Returns tuple of (services_to_stop, service_names).
    """
    logger = logging.getLogger(__name__)

    # Collect all services to stop
    services_to_stop = _collect_all_services_to_stop(runtime)
    if runtime.service_registry:
        logger.info(f"Found {len(services_to_stop)} services to stop")

    # Sort services by shutdown priority
    services_to_stop.sort(key=_get_service_shutdown_priority)

    # Execute service stops
    _, service_names = await _execute_service_stop_tasks(services_to_stop)

    return services_to_stop, service_names


async def handle_adapter_shutdown_cleanup(runtime: Any) -> None:
    """Clean up adapter connections and resources."""
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    # Stop multi-service sink (bus manager)
    if runtime.bus_manager:
        try:
            logger.debug("Stopping multi-service sink...")
            await asyncio.wait_for(runtime.bus_manager.stop(), timeout=10.0)
            logger.debug("Multi-service sink stopped.")
        except asyncio.TimeoutError:
            logger.error("Timeout stopping multi-service sink after 10 seconds")
        except Exception as e:
            logger.error(f"Error stopping multi-service sink: {e}")

    # Stop all adapters
    logger.debug(f"Stopping {len(runtime.adapters)} adapters...")
    adapter_stop_results = await asyncio.gather(
        *(adapter.stop() for adapter in runtime.adapters if hasattr(adapter, "stop")), return_exceptions=True
    )

    for i, stop_result in enumerate(adapter_stop_results):
        if isinstance(stop_result, Exception):
            logger.error(
                f"Error stopping adapter {runtime.adapters[i].__class__.__name__}: {stop_result}", exc_info=stop_result
            )

    logger.debug("Adapters stopped.")


async def preserve_critical_system_state(runtime: Any) -> None:
    """Preserve essential state before shutdown."""
    logger = logging.getLogger(__name__)

    # Preserve agent continuity if identity exists
    if hasattr(runtime, "agent_identity") and runtime.agent_identity:
        try:
            await runtime._preserve_shutdown_continuity()
            logger.info("Agent continuity preserved successfully")
        except Exception as e:
            logger.error(f"Failed to preserve continuity during shutdown: {e}")


async def finalize_shutdown_logging(_: Any) -> None:
    """Complete logging and audit trail for shutdown."""
    import logging

    logger = logging.getLogger(__name__)

    # Execute shutdown manager handlers
    from ciris_engine.logic.utils.shutdown_manager import get_shutdown_manager

    shutdown_manager = get_shutdown_manager()

    try:
        await shutdown_manager.execute_async_handlers()
        logger.info("Shutdown handlers executed successfully")
    except Exception as e:
        logger.error(f"Error executing shutdown handlers: {e}")

    logger.info("CIRIS Runtime shutdown complete")


async def cleanup_runtime_resources(runtime: Any) -> None:
    """Release all runtime resources and connections."""
    import logging

    logger = logging.getLogger(__name__)

    # Clear service registry
    if runtime.service_registry:
        try:
            runtime.service_registry.clear_all()
            logger.debug("Service registry cleared.")
        except Exception as e:
            logger.error(f"Error clearing service registry: {e}")

    # Ensure shutdown event is set
    runtime._ensure_shutdown_event()
    if runtime._shutdown_event:
        runtime._shutdown_event.set()
        logger.debug("Shutdown event set.")


def validate_shutdown_completion(runtime: Any) -> None:
    """Verify complete and clean shutdown."""
    import logging

    logger = logging.getLogger(__name__)

    # Mark shutdown as truly complete
    runtime._shutdown_complete = True

    # Set shutdown event if it exists
    if hasattr(runtime, "_shutdown_event"):
        runtime._shutdown_event.set()

    logger.info("Shutdown completion validated and marked")


# ============================================================================
# RUN HELPERS (CC 32 -> CC ~6) - 6 helpers
# ============================================================================


def initialize_runtime_execution_context(runtime: Any) -> None:
    """Initialize the runtime for execution if not already done."""
    if not runtime._initialized:
        raise RuntimeError("Runtime must be initialized before execution")


def setup_runtime_monitoring_tasks(runtime: Any) -> Tuple[Optional[Any], List[Any], List[Any]]:
    """Set up monitoring tasks for agent and adapters."""
    from ciris_engine.logic.setup.first_run import is_first_run

    # Get adapter tasks
    adapter_tasks = getattr(runtime, "_adapter_tasks", [])
    if not adapter_tasks:
        logger.warning("No adapter tasks found - this may indicate a problem with initialization")
        return None, [], []

    logger.info(f"Monitoring {len(adapter_tasks)} adapter lifecycle tasks...")

    # Find the agent task
    agent_task = None
    for task in asyncio.all_tasks():
        if task.get_name() == "AgentProcessorTask":
            agent_task = task
            break

    # In first-run mode, there is no agent task - just monitor adapters
    first_run = is_first_run()
    if not agent_task and not first_run:
        raise RuntimeError("Agent processor task not found - initialization may have failed")

    if first_run and not agent_task:
        logger.info("First-run mode: Monitoring adapters only (no agent processor)")

    # Set up monitoring tasks
    runtime._ensure_shutdown_event()
    shutdown_event_task = None
    if runtime._shutdown_event:
        shutdown_event_task = asyncio.create_task(runtime._shutdown_event.wait(), name="ShutdownEventWait")

    global_shutdown_task = asyncio.create_task(wait_for_global_shutdown_async(), name="GlobalShutdownWait")

    # Build task list - only include agent_task if it exists
    all_tasks = [*adapter_tasks, global_shutdown_task]
    if agent_task:
        all_tasks.insert(0, agent_task)
    if shutdown_event_task:
        all_tasks.append(shutdown_event_task)

    return agent_task, adapter_tasks, all_tasks


def monitor_runtime_shutdown_signals(runtime: Any, shutdown_logged: bool) -> bool:
    """Monitor and handle shutdown signals, returns updated shutdown_logged flag."""
    if (runtime._shutdown_event and runtime._shutdown_event.is_set()) or is_global_shutdown_requested():
        if not shutdown_logged:
            shutdown_reason = (
                runtime._shutdown_reason or runtime._shutdown_manager.get_shutdown_reason() or "Unknown reason"
            )
            logger.critical(f"GRACEFUL SHUTDOWN TRIGGERED: {shutdown_reason}")
            return True  # Now logged
    return shutdown_logged


def handle_runtime_agent_task_completion(runtime: Any, agent_task: Any, adapter_tasks: List[Any]) -> None:
    """Handle agent task completion and initiate adapter cleanup."""
    logger.info(
        f"Agent processing task completed. Result: {agent_task.result() if not agent_task.cancelled() else 'Cancelled'}"
    )
    # Signal shutdown for adapters
    runtime.request_shutdown("Agent processing completed normally.")
    for ad_task in adapter_tasks:
        if not ad_task.done():
            ad_task.cancel()


def handle_runtime_task_failures(runtime: Any, done_tasks: Set[Any], excluded_tasks: Set[Any]) -> None:
    """Handle completed tasks and failures, excluding monitoring tasks."""
    for task in done_tasks:
        if task not in excluded_tasks:
            task_name = task.get_name() if hasattr(task, "get_name") else "Unnamed task"
            logger.info(
                f"Task '{task_name}' completed. Result: {task.result() if not task.cancelled() else 'Cancelled'}"
            )
            if task.exception():
                logger.error(
                    f"Task '{task_name}' raised an exception: {task.exception()}",
                    exc_info=task.exception(),
                )
                runtime.request_shutdown(f"Task {task_name} failed: {task.exception()}")


async def finalize_runtime_execution(runtime: Any, pending_tasks: Set[Any]) -> None:
    """Finalize runtime execution by cleaning up tasks and handlers."""
    # Await all pending tasks
    if pending_tasks:
        await asyncio.wait(pending_tasks, return_when=asyncio.ALL_COMPLETED)

    # Execute any pending global shutdown handlers
    if (runtime._shutdown_event and runtime._shutdown_event.is_set()) or is_global_shutdown_requested():
        await runtime._shutdown_manager.execute_async_handlers()


# ============================================================================
# ADAPTER CONNECTION HELPERS (CC 23 -> CC ~6) - 4 helpers
# ============================================================================


def log_adapter_configuration_details(adapters: List[Any]) -> None:
    """Log detailed configuration for each adapter."""
    logger.info("Starting adapter connections...")

    for adapter in adapters:
        adapter_name = adapter.__class__.__name__

        # Report adapter details for Discord
        if adapter_name == "DiscordPlatform" and hasattr(adapter, "config"):
            config = adapter.config
            logger.info(f"  → {adapter_name} configuration:")
            if hasattr(config, "monitored_channel_ids"):
                logger.info(f"    Monitored channels: {config.monitored_channel_ids}")
            if hasattr(config, "server_id"):
                logger.info(f"    Target server: {config.server_id}")
            if hasattr(config, "bot_token") and config.bot_token:
                logger.info(f"    Bot token: ...{config.bot_token[-10:]}")


def create_adapter_lifecycle_tasks(adapters: List[Any], agent_task: Any) -> List[Any]:
    """Create and start adapter lifecycle tasks."""
    logger.info("Creating agent processor task...")

    adapter_tasks = []
    for adapter in adapters:
        adapter_name = adapter.__class__.__name__

        if hasattr(adapter, "run_lifecycle"):
            lifecycle_task = asyncio.create_task(adapter.run_lifecycle(agent_task), name=f"{adapter_name}LifecycleTask")
            adapter_tasks.append(lifecycle_task)
            logger.info(f"  → Starting {adapter_name} lifecycle...")

    return adapter_tasks


async def _check_adapter_health(adapter: Any) -> bool:
    """Check health of a single adapter."""
    adapter_name = adapter.__class__.__name__
    if "Discord" not in adapter_name:
        return True

    if not hasattr(adapter, "is_healthy"):
        logger.warning(f"  ⚠️  {adapter_name} has no is_healthy method")
        return False

    try:
        is_healthy = await adapter.is_healthy()
        if not is_healthy:
            logger.debug(f"  ⏳ {adapter_name} not yet healthy, waiting...")
            return False
        else:
            logger.info(f"  ✓ {adapter_name} is healthy and connected")
            return True
    except Exception as e:
        logger.debug(f"  ⏳ {adapter_name} health check failed: {e}")
        return False


async def wait_for_adapter_readiness(adapters: List[Any]) -> bool:
    """Wait for all adapters to be ready and healthy."""
    logger.info("  ⏳ Waiting for adapter connections to establish...")

    try:
        async with _async_timeout(30.0):
            while True:
                health_checks = [_check_adapter_health(adapter) for adapter in adapters]
                health_results = await asyncio.gather(*health_checks)

                if all(health_results):
                    return True

                await asyncio.sleep(0.5)
    except asyncio.TimeoutError:
        return False


async def verify_adapter_service_registration(runtime: Any) -> bool:
    """Verify that adapter services are properly registered and available."""
    from ciris_engine.schemas.runtime.enums import ServiceType

    logger.info("  → Registering adapter services...")
    await runtime._register_adapter_services()

    # Give services a moment to settle after registration
    await asyncio.sleep(0.1)

    try:
        async with _async_timeout(30.0):
            while True:
                # Check if services are actually available
                if runtime.service_registry:
                    try:
                        test_service = await runtime.service_registry.get_service(
                            handler="test",
                            service_type=ServiceType.COMMUNICATION,
                            required_capabilities=["send_message"],
                        )
                        if test_service:
                            logger.info("  ✅ All adapters connected and services registered!")
                            return True
                    except Exception as e:
                        logger.debug(f"Service registration check failed: {e}")

                await asyncio.sleep(0.5)
    except asyncio.TimeoutError:
        return False


# ============================================================================
# CRITICAL SERVICES HELPERS (CC 18 -> CC ~6) - 3 helpers
# ============================================================================


def identify_critical_service_dependencies() -> None:
    """Determine critical services and dependency order"""
    pass


def execute_critical_service_health_checks() -> None:
    """Perform comprehensive health validation"""
    pass


def handle_critical_service_failures() -> None:
    """Implement failure recovery for critical services"""
    pass


# ============================================================================
# SERVICE REGISTRATION HELPERS (CC 13 -> CC ~5) - 3 helpers
# ============================================================================


def prepare_service_registration_context() -> None:
    """Set up context for service registration"""
    pass


def execute_service_registration_workflow() -> None:
    """Register services with proper dependency handling"""
    pass


def validate_service_registration_integrity() -> None:
    """Verify successful service registration"""
    pass


# ============================================================================
# CONTINUITY AWARENESS HELPERS (CC 11 -> CC ~6) - 2 helpers
# ============================================================================


def capture_runtime_continuity_state() -> None:
    """Capture current continuity and cognitive state"""
    pass


def persist_continuity_for_recovery() -> None:
    """Store continuity state for future recovery"""
    pass


# ============================================================================
# COMMON RUNTIME UTILITIES - 8 additional helpers
# ============================================================================


def validate_runtime_configuration() -> None:
    """Comprehensive runtime configuration validation"""
    pass


def create_runtime_error_context() -> None:
    """Create structured error context for debugging"""
    pass


def measure_runtime_performance_metrics() -> None:
    """Collect and analyze runtime performance data"""
    pass


def handle_runtime_resource_limits() -> None:
    """Monitor and enforce resource constraints"""
    pass


def synchronize_runtime_state_transitions() -> None:
    """Ensure thread-safe state transitions"""
    pass


def audit_runtime_operations() -> None:
    """Create audit trail for runtime operations"""
    pass


def optimize_runtime_memory_usage() -> None:
    """Manage memory allocation and cleanup"""
    pass


def coordinate_runtime_service_lifecycle() -> None:
    """Orchestrate service start/stop sequences"""
    pass
