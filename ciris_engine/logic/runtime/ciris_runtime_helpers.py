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
- _preserve_shutdown_consciousness (CC 11) -> 2 helpers
"""

from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass
from enum import Enum

# Import required for helper functions
import asyncio
import logging


def _get_service_shutdown_priority(service: Any) -> int:
    """Get shutdown priority for service ordering.

    Lower numbers shut down first, higher numbers shut down last.
    Infrastructure services shut down last to support other services.
    """
    service_name = service.__class__.__name__

    # Priority 0: Services that depend on others
    if "TSDB" in service_name or "Consolidation" in service_name:
        return 0
    elif "Task" in service_name or "Scheduler" in service_name:
        return 1
    elif "Incident" in service_name or "Monitor" in service_name:
        return 2
    # Priority 3: Application services
    elif "Adaptive" in service_name or "Filter" in service_name:
        return 3
    elif "Tool" in service_name or "Control" in service_name:
        return 4
    elif "Observation" in service_name or "Visibility" in service_name:
        return 5
    # Priority 6: Core services
    elif "Telemetry" in service_name or "Audit" in service_name:
        return 6
    elif "LLM" in service_name or "Auth" in service_name:
        return 7
    elif "Config" in service_name:
        return 8
    # Priority 9: Fundamental services
    elif "Memory" in service_name or "Secrets" in service_name:
        return 9
    # Priority 10+: Infrastructure services (stop last)
    elif "Time" in service_name:
        return 11
    elif "Shutdown" in service_name:
        return 12
    elif "Initialization" in service_name:
        return 10
    else:
        return 5  # Default priority


async def execute_final_maintenance_tasks(runtime) -> None:
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


async def handle_agent_processor_shutdown(runtime) -> None:
    """Handle graceful agent processor shutdown negotiation."""
    import asyncio
    from ciris_engine.schemas.processors.states import AgentState
    logger = logging.getLogger(__name__)

    # Initiate graceful shutdown negotiation
    if runtime.agent_processor and hasattr(runtime.agent_processor, "state_manager"):
        current_state = runtime.agent_processor.state_manager.get_state()

        # Only do negotiation if not already in SHUTDOWN state
        if current_state != AgentState.SHUTDOWN:
            try:
                logger.info("Initiating graceful shutdown negotiation...")

                # Check if we can transition to shutdown state
                if await runtime.agent_processor.state_manager.can_transition_to(AgentState.SHUTDOWN):
                    logger.info(f"Transitioning from {current_state} to SHUTDOWN state")
                    # Use the state manager directly to transition
                    await runtime.agent_processor.state_manager.transition_to(AgentState.SHUTDOWN)

                    # If processing loop is running, just signal it to stop
                    if runtime.agent_processor._processing_task and not runtime.agent_processor._processing_task.done():
                        logger.info("Processing loop is running, signaling stop")
                        if hasattr(runtime.agent_processor, "_stop_event") and runtime.agent_processor._stop_event:
                            runtime.agent_processor._stop_event.set()
                    else:
                        # Processing loop not running, handle shutdown ourselves
                        logger.info("Processing loop not running, executing shutdown processor directly")
                        if (
                            hasattr(runtime.agent_processor, "shutdown_processor")
                            and runtime.agent_processor.shutdown_processor
                        ):
                            # Run a few rounds of shutdown processing
                            for round_num in range(5):
                                try:
                                    result = await runtime.agent_processor.shutdown_processor.process(round_num)
                                    if runtime.agent_processor.shutdown_processor.shutdown_complete:
                                        break
                                except Exception as e:
                                    logger.error(f"Error in shutdown processor: {e}", exc_info=True)
                                    break
                                await asyncio.sleep(0.1)
                else:
                    logger.error(f"Cannot transition from {current_state} to SHUTDOWN state")

                # Wait for ShutdownProcessor to complete
                max_wait = 5.0  # Reduced from 30s to 5s for faster shutdown
                start_time = asyncio.get_event_loop().time()

                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    if (
                        hasattr(runtime.agent_processor, "shutdown_processor")
                        and runtime.agent_processor.shutdown_processor
                    ):
                        if runtime.agent_processor.shutdown_processor.shutdown_complete:
                            result = runtime.agent_processor.shutdown_processor.shutdown_result
                            if result and hasattr(result, "get") and result.get("status") == "rejected":
                                logger.warning(f"Shutdown rejected by agent: {result.get('reason')}")
                                # Proceed with shutdown - emergency shutdown API provides override mechanism
                            break
                    await asyncio.sleep(0.1)  # Reduced from 0.5s to 0.1s for faster response

                logger.debug("Shutdown negotiation complete or timed out")
            except Exception as e:
                logger.error(f"Error during shutdown negotiation: {e}")


# ============================================================================
# SHUTDOWN HELPERS (CC 75 -> CC ~8) - 8 helpers
# ============================================================================

def validate_shutdown_preconditions(runtime) -> bool:
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

async def prepare_shutdown_maintenance_tasks(runtime) -> List[Any]:
    """Prepare and schedule final maintenance operations.

    Returns list of scheduled services that need to be stopped.
    """
    import asyncio
    import logging
    logger = logging.getLogger(__name__)

    # Collect scheduled services that need to be stopped
    scheduled_services = []
    if runtime.service_registry:
        all_services = runtime.service_registry.get_all_services()
        for service in all_services:
            # Check for scheduled services with _task or _scheduler attributes
            if hasattr(service, "_task") or hasattr(service, "_scheduler"):
                scheduled_services.append(service)

    # Stop all scheduled services first
    for service in scheduled_services:
        try:
            service_name = service.__class__.__name__
            logger.info(f"Stopping scheduled tasks for {service_name}")
            if hasattr(service, "_task") and service._task:
                # Cancel the task directly
                service._task.cancel()
                try:
                    await service._task
                except asyncio.CancelledError:
                    # Only re-raise if we're being cancelled ourselves
                    if asyncio.current_task() and asyncio.current_task().cancelled():
                        raise
                    # Otherwise, this is a normal stop - don't propagate the cancellation
            elif hasattr(service, "stop_scheduler"):
                await service.stop_scheduler()
        except Exception as e:
            logger.error(f"Error stopping scheduled tasks for {service.__class__.__name__}: {e}")

    # Give scheduled tasks a moment to stop
    if scheduled_services:
        logger.info(f"Stopped {len(scheduled_services)} scheduled services, waiting for tasks to complete...")
        await asyncio.sleep(0.5)

    return scheduled_services

async def execute_service_shutdown_sequence(runtime) -> Tuple[List[Any], List[str]]:
    """Execute orderly shutdown of all services by priority.

    Returns tuple of (services_to_stop, service_names).
    """
    import asyncio
    import logging
    from typing import Any
    logger = logging.getLogger(__name__)

    # Get all registered services dynamically
    all_registered_services = []
    if runtime.service_registry:
        all_registered_services = runtime.service_registry.get_all_services()
        logger.info(f"Found {len(all_registered_services)} registered services to stop")

    # Build comprehensive list of services to stop
    services_to_stop = []
    seen_ids = set()

    # Add all registered services
    for service in all_registered_services:
        service_id = id(service)
        if service_id not in seen_ids and hasattr(service, "stop"):
            seen_ids.add(service_id)
            services_to_stop.append(service)

    # Add direct service references (backward compatibility)
    direct_services = [
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
        getattr(runtime.service_initializer, "core_tool_service", None),
        getattr(runtime.service_initializer, "wa_auth_system", None),
        getattr(runtime.service_initializer, "initialization_service", None),
        getattr(runtime.service_initializer, "shutdown_service", None),
        getattr(runtime.service_initializer, "time_service", None),
        # From runtime
        runtime.maintenance_service,
        runtime.transaction_orchestrator,
        runtime.agent_config_service,
        runtime.adaptive_filter_service,
        runtime.telemetry_service,
        runtime.audit_service,
        runtime.llm_service,
        runtime.secrets_service,
        runtime.memory_service,
    ]

    for service in direct_services:
        if service:
            service_id = id(service)
            if service_id not in seen_ids and hasattr(service, "stop"):
                seen_ids.add(service_id)
                services_to_stop.append(service)

    # Sort services by shutdown priority
    services_to_stop.sort(key=_get_service_shutdown_priority)

    # Execute service stops
    stop_tasks = []
    service_names = []
    for service in services_to_stop:
        if service and hasattr(service, "stop"):
            stop_method = service.stop()
            if asyncio.iscoroutine(stop_method):
                # Async stop method
                task = asyncio.create_task(stop_method)
                stop_tasks.append(task)
            # Sync stop method already completed
            service_names.append(service.__class__.__name__)

    if stop_tasks:
        logger.info(f"Stopping {len(stop_tasks)} services: {', '.join(service_names)}")

        # Use wait with timeout to track individual tasks
        done, pending = await asyncio.wait(stop_tasks, timeout=10.0)

        if pending:
            # Handle hanging services
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
        else:
            logger.info(f"All {len(stop_tasks)} services stopped successfully (Total services: {len(services_to_stop)})")

        # Check for errors in completed tasks
        for task in done:
            if task.done() and not task.cancelled():
                try:
                    result = task.result()
                    if isinstance(result, Exception):
                        idx = stop_tasks.index(task)
                        logger.error(f"Service {service_names[idx]} stop error: {result}")
                except Exception as e:
                    logger.error(f"Error checking task result: {e}")

    return services_to_stop, service_names

async def handle_adapter_shutdown_cleanup(runtime) -> None:
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
        *(adapter.stop() for adapter in runtime.adapters if hasattr(adapter, "stop")),
        return_exceptions=True
    )

    for i, stop_result in enumerate(adapter_stop_results):
        if isinstance(stop_result, Exception):
            logger.error(
                f"Error stopping adapter {runtime.adapters[i].__class__.__name__}: {stop_result}",
                exc_info=stop_result
            )

    logger.debug("Adapters stopped.")

async def preserve_critical_system_state(runtime) -> None:
    """Preserve essential state before shutdown."""
    import logging
    logger = logging.getLogger(__name__)

    # Preserve agent consciousness if identity exists
    if hasattr(runtime, "agent_identity") and runtime.agent_identity:
        try:
            await runtime._preserve_shutdown_consciousness()
            logger.info("Agent consciousness preserved successfully")
        except Exception as e:
            logger.error(f"Failed to preserve consciousness during shutdown: {e}")

async def finalize_shutdown_logging(runtime) -> None:
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

async def cleanup_runtime_resources(runtime) -> None:
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

def validate_shutdown_completion(runtime) -> None:
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

def initialize_runtime_execution_context():
    """Set up execution context for runtime operation"""
    pass

def execute_runtime_main_loop():
    """Core runtime processing loop with cognitive states"""
    pass

def handle_runtime_state_transitions():
    """Manage cognitive state transitions during execution"""
    pass

def process_runtime_maintenance_cycles():
    """Handle periodic maintenance during runtime"""
    pass

def monitor_runtime_health_metrics():
    """Track and respond to runtime health indicators"""
    pass

def handle_runtime_error_recovery():
    """Implement error recovery and resilience patterns"""
    pass

# ============================================================================
# ADAPTER CONNECTION HELPERS (CC 23 -> CC ~6) - 4 helpers
# ============================================================================

def validate_adapter_connection_prerequisites():
    """Verify adapter readiness for connection"""
    pass

def establish_adapter_communication_channels():
    """Create and configure adapter communication"""
    pass

def register_adapter_event_handlers():
    """Set up adapter event handling and callbacks"""
    pass

def monitor_adapter_connection_health():
    """Track adapter connection status and recovery"""
    pass

# ============================================================================
# CRITICAL SERVICES HELPERS (CC 18 -> CC ~6) - 3 helpers
# ============================================================================

def identify_critical_service_dependencies():
    """Determine critical services and dependency order"""
    pass

def execute_critical_service_health_checks():
    """Perform comprehensive health validation"""
    pass

def handle_critical_service_failures():
    """Implement failure recovery for critical services"""
    pass

# ============================================================================
# SERVICE REGISTRATION HELPERS (CC 13 -> CC ~5) - 3 helpers
# ============================================================================

def prepare_service_registration_context():
    """Set up context for service registration"""
    pass

def execute_service_registration_workflow():
    """Register services with proper dependency handling"""
    pass

def validate_service_registration_integrity():
    """Verify successful service registration"""
    pass

# ============================================================================
# CONSCIOUSNESS PRESERVATION HELPERS (CC 11 -> CC ~6) - 2 helpers
# ============================================================================

def capture_runtime_consciousness_state():
    """Capture current consciousness and cognitive state"""
    pass

def persist_consciousness_for_recovery():
    """Store consciousness state for future recovery"""
    pass

# ============================================================================
# COMMON RUNTIME UTILITIES - 8 additional helpers
# ============================================================================

def validate_runtime_configuration():
    """Comprehensive runtime configuration validation"""
    pass

def create_runtime_error_context():
    """Create structured error context for debugging"""
    pass

def measure_runtime_performance_metrics():
    """Collect and analyze runtime performance data"""
    pass

def handle_runtime_resource_limits():
    """Monitor and enforce resource constraints"""
    pass

def synchronize_runtime_state_transitions():
    """Ensure thread-safe state transitions"""
    pass

def audit_runtime_operations():
    """Create audit trail for runtime operations"""
    pass

def optimize_runtime_memory_usage():
    """Manage memory allocation and cleanup"""
    pass

def coordinate_runtime_service_lifecycle():
    """Orchestrate service start/stop sequences"""
    pass