"""
Main agent processor that coordinates all processing activities.
Uses v1 schemas and integrates state management.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.utils.context_utils import build_dispatch_context
from ciris_engine.logic.utils.shutdown_manager import (
    get_global_shutdown_reason,
    is_global_shutdown_requested,
    request_global_shutdown,
)
from ciris_engine.schemas.processors.context import ProcessorContext
from ciris_engine.schemas.processors.state import StateTransitionRecord
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.core import AgentIdentityRoot
from ciris_engine.schemas.runtime.models import Thought, ThoughtStatus
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceResponseData,
    TraceContext,
)

if TYPE_CHECKING:
    from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher

from ciris_engine.logic.processors.states.dream_processor import DreamProcessor
from ciris_engine.logic.processors.states.play_processor import PlayProcessor
from ciris_engine.logic.processors.states.shutdown_processor import ShutdownProcessor
from ciris_engine.logic.processors.states.solitude_processor import SolitudeProcessor
from ciris_engine.logic.processors.states.wakeup_processor import WakeupProcessor
from ciris_engine.logic.processors.states.work_processor import WorkProcessor
from ciris_engine.logic.processors.support.state_manager import StateManager
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class AgentProcessor:
    """
    Main agent processor that orchestrates task processing, thought generation,
    and state management using v1 schemas.
    """

    def __init__(
        self,
        app_config: ConfigAccessor,
        agent_identity: AgentIdentityRoot,
        thought_processor: ThoughtProcessor,
        action_dispatcher: "ActionDispatcher",
        services: dict,
        startup_channel_id: str,
        time_service: TimeServiceProtocol,
        runtime: Optional[Any] = None,
    ) -> None:
        """Initialize the agent processor with v1 configuration."""
        # Allow empty string for startup_channel_id - will be resolved dynamically
        if startup_channel_id is None:
            raise ValueError("startup_channel_id cannot be None (empty string is allowed)")
        self.app_config = app_config
        self.agent_identity = agent_identity
        self.thought_processor = thought_processor
        self._action_dispatcher = action_dispatcher  # Store internally
        self.services = services
        self.startup_channel_id = startup_channel_id
        self.runtime = runtime  # Store runtime reference for preload tasks
        self._time_service = time_service  # Store injected time service

        # Initialize state manager - agent always starts in SHUTDOWN state
        time_service_from_services = (
            services.get("time_service") if isinstance(services, dict) else getattr(services, "time_service", None)
        )
        if not time_service_from_services:
            # Use the injected time service if not in services dict
            time_service_from_services = time_service
        self.state_manager = StateManager(time_service=time_service_from_services, initial_state=AgentState.SHUTDOWN)

        # Initialize specialized processors, passing the initial dispatcher
        self.wakeup_processor = WakeupProcessor(
            config_accessor=app_config,  # app_config is actually a ConfigAccessor
            thought_processor=thought_processor,
            action_dispatcher=self._action_dispatcher,  # Use internal dispatcher
            services=services,
            startup_channel_id=startup_channel_id,
            time_service=time_service,  # Use the injected time service directly
        )

        self.work_processor = WorkProcessor(
            config_accessor=app_config,  # app_config is actually a ConfigAccessor
            thought_processor=thought_processor,
            action_dispatcher=self._action_dispatcher,  # Use internal dispatcher
            services=services,
            startup_channel_id=startup_channel_id,
        )

        self.play_processor = PlayProcessor(
            config_accessor=app_config,  # app_config is actually a ConfigAccessor
            thought_processor=thought_processor,
            action_dispatcher=self._action_dispatcher,  # Use internal dispatcher
            services=services,
        )

        self.solitude_processor = SolitudeProcessor(
            config_accessor=app_config,  # app_config is actually a ConfigAccessor
            thought_processor=thought_processor,
            action_dispatcher=self._action_dispatcher,  # Use internal dispatcher
            services=services,
        )

        # Enhanced dream processor with self-configuration and memory consolidation
        self.dream_processor = DreamProcessor(
            config_accessor=app_config,  # app_config is actually a ConfigAccessor
            thought_processor=thought_processor,
            action_dispatcher=self._action_dispatcher,
            services=services,
            service_registry=services.get("service_registry"),
            identity_manager=services.get("identity_manager"),
            startup_channel_id=startup_channel_id,
            cirisnode_url="https://localhost:8001",  # Default since cirisnode config not in essential
        )

        # Shutdown processor for graceful shutdown negotiation
        self.shutdown_processor = ShutdownProcessor(
            config_accessor=app_config,  # app_config is actually a ConfigAccessor
            thought_processor=thought_processor,
            action_dispatcher=self._action_dispatcher,
            services=services,
            time_service=time_service,  # Use the injected time service directly
            runtime=runtime,
        )

        # Map states to processors
        self.state_processors = {
            AgentState.WAKEUP: self.wakeup_processor,
            AgentState.WORK: self.work_processor,
            AgentState.PLAY: self.play_processor,
            AgentState.SOLITUDE: self.solitude_processor,
            AgentState.SHUTDOWN: self.shutdown_processor,
            AgentState.DREAM: self.dream_processor,
        }

        # Processing control
        self.current_round_number = 0
        self._stop_event: Optional[asyncio.Event] = None
        self._processing_task: Optional[asyncio.Task] = None

        # Pause/resume control for single-stepping
        self._is_paused = False
        self._pause_event: Optional[asyncio.Event] = None
        self._pipeline_controller: Optional[Any] = None  # PipelineController when paused
        self._single_step_mode = False

        # Track processing time for thoughts
        self._thought_processing_callback: Optional[Any] = None  # Callback for thought timing

        logger.info("AgentProcessor initialized with v1 schemas and modular processors")

    def _load_preload_tasks(self) -> None:
        """Load preload tasks after successful WORK state transition."""
        try:
            if self.runtime and hasattr(self.runtime, "get_preload_tasks"):
                preload_tasks = self.runtime.get_preload_tasks()
                if preload_tasks:
                    logger.info(f"Loading {len(preload_tasks)} preload tasks after WORK state transition")
                    from ciris_engine.logic.processors.support.task_manager import TaskManager

                    time_service = (
                        self.services.get("time_service")
                        if isinstance(self.services, dict)
                        else getattr(self.services, "time_service", None)
                    )
                    tm = TaskManager(time_service=time_service)
                    for desc in preload_tasks:
                        try:
                            tm.create_task(
                                description=desc,
                                channel_id=self.startup_channel_id,
                                context={"channel_id": self.startup_channel_id},
                            )
                            logger.info(f"Created preload task: {desc}")
                        except Exception as e:
                            logger.error(f"Error creating preload task '{desc}': {e}", exc_info=True)
                else:
                    logger.debug("No preload tasks to load")
            else:
                logger.debug("Runtime does not support preload tasks")
        except Exception as e:
            logger.error(f"Error loading preload tasks: {e}", exc_info=True)

    def _ensure_stop_event(self) -> None:
        """Ensure stop event is created when needed in async context."""
        if self._stop_event is None:
            try:
                self._stop_event = asyncio.Event()
            except RuntimeError:
                logger.warning("Cannot create stop event outside of async context")

    @property
    def action_dispatcher(self) -> "ActionDispatcher":
        return self._action_dispatcher

    @action_dispatcher.setter
    def action_dispatcher(self, new_dispatcher: "ActionDispatcher") -> None:
        logger.info(f"AgentProcessor's action_dispatcher is being updated to: {new_dispatcher}")
        self._action_dispatcher = new_dispatcher
        # Propagate the new dispatcher to sub-processors
        # Ensure sub-processors have an 'action_dispatcher' attribute to be updated
        sub_processors_to_update = [
            getattr(self, "wakeup_processor", None),
            getattr(self, "work_processor", None),
            getattr(self, "play_processor", None),
            getattr(self, "solitude_processor", None),
        ]
        for sub_processor in sub_processors_to_update:
            if sub_processor and hasattr(sub_processor, "action_dispatcher"):
                logger.info(f"Updating action_dispatcher for {sub_processor.__class__.__name__}")
                sub_processor.action_dispatcher = new_dispatcher
            elif sub_processor:
                logger.warning(
                    f"{sub_processor.__class__.__name__} does not have an 'action_dispatcher' attribute to update."
                )
        logger.info("AgentProcessor's action_dispatcher updated and propagated if applicable.")

    async def start_processing(self, num_rounds: Optional[int] = None) -> None:
        """Start the main agent processing loop."""
        if self._processing_task is not None and not self._processing_task.done():
            logger.warning("Processing is already running")
            return

        self._ensure_stop_event()
        if self._stop_event is not None:
            self._stop_event.clear()
        logger.info(f"Starting agent processing (rounds: {num_rounds or 'infinite'})")

        # Transition from SHUTDOWN to WAKEUP state when starting processing
        if self.state_manager.get_state() == AgentState.SHUTDOWN:
            if not self.state_manager.transition_to(AgentState.WAKEUP):
                logger.error("Failed to transition from SHUTDOWN to WAKEUP state")
                return
        elif self.state_manager.get_state() != AgentState.WAKEUP:
            logger.warning(f"Unexpected state {self.state_manager.get_state()} when starting processing")
            if not self.state_manager.transition_to(AgentState.WAKEUP):
                logger.error(f"Failed to transition from {self.state_manager.get_state()} to WAKEUP state")
                return

        self.wakeup_processor.initialize()

        wakeup_complete = False
        wakeup_round = 0

        while (
            not wakeup_complete
            and not (self._stop_event is not None and self._stop_event.is_set())
            and (num_rounds is None or self.current_round_number < num_rounds)
        ):
            logger.info(f"Wakeup round {wakeup_round}")

            wakeup_result = await self.wakeup_processor.process(wakeup_round)
            wakeup_complete = wakeup_result.wakeup_complete

            # Check if wakeup failed (any task failed)
            if hasattr(wakeup_result, "errors") and wakeup_result.errors > 0:
                logger.error(f"Wakeup failed with {wakeup_result.errors} errors - transitioning to SHUTDOWN")
                if not self.state_manager.transition_to(AgentState.SHUTDOWN):
                    logger.error("Failed to transition to SHUTDOWN state after wakeup failure")
                await self.stop_processing()
                return

            if not wakeup_complete:
                _thoughts_processed = await self._process_pending_thoughts_async()

                logger.info(f"Wakeup round {wakeup_round}: {wakeup_result.thoughts_processed} thoughts processed")

                # Use shorter delay for mock LLM
                llm_service = self.services.get("llm_service")
                is_mock_llm = llm_service and type(llm_service).__name__ == "MockLLMService"
                round_delay = 0.1 if is_mock_llm else 5.0
                await asyncio.sleep(round_delay)
            else:
                logger.info("✓ Wakeup sequence completed successfully!")

            wakeup_round += 1
            self.current_round_number += 1

        if not wakeup_complete:
            logger.error(
                f"Wakeup did not complete within {num_rounds or 'infinite'} rounds - transitioning to SHUTDOWN"
            )
            # Transition to SHUTDOWN state since wakeup failed
            if not self.state_manager.transition_to(AgentState.SHUTDOWN):
                logger.error("Failed to transition to SHUTDOWN state after wakeup failure")
            await self.stop_processing()
            return

        logger.info("Attempting to transition from WAKEUP to WORK state...")
        if not self.state_manager.transition_to(AgentState.WORK):
            logger.error("Failed to transition to WORK state after wakeup")
            await self.stop_processing()
            return

        logger.info("Successfully transitioned to WORK state")
        self.state_manager.update_state_metadata("wakeup_complete", True)

        logger.info("Loading preload tasks...")
        self._load_preload_tasks()

        # Schedule first dream session
        logger.info("Scheduling initial dream session...")
        await self._schedule_initial_dream()

        if hasattr(self, "runtime") and self.runtime is not None and hasattr(self.runtime, "start_interactive_console"):
            print("[STATE] Initializing interactive console for user input...")
            try:
                await self.runtime.start_interactive_console()
            except Exception as e:
                logger.error(f"Error initializing interactive console: {e}")

        logger.info("Initializing work processor...")
        self.work_processor.initialize()
        logger.info("Work processor initialized successfully")

        logger.info("Creating processing loop task...")
        self._processing_task = asyncio.create_task(self._processing_loop(num_rounds))
        logger.info("Processing loop task created")

        try:
            await self._processing_task
        except asyncio.CancelledError:
            logger.info("Processing task was cancelled")
            raise
        except Exception as e:
            logger.error(f"Processing loop error: {e}", exc_info=True)
        finally:
            if self._stop_event is not None:
                self._stop_event.set()

    async def _process_pending_thoughts_async(self) -> int:
        """
        Process all pending thoughts asynchronously with comprehensive error handling.
        This is the key to non-blocking operation - it processes ALL thoughts,
        not just wakeup thoughts.
        """
        try:
            # Get current state to filter thoughts appropriately
            current_state = self.state_manager.get_state()

            pending_thoughts = persistence.get_pending_thoughts_for_active_tasks()

            # If in SHUTDOWN state, only process thoughts for shutdown tasks
            if current_state == AgentState.SHUTDOWN:
                shutdown_thoughts = [
                    t for t in pending_thoughts if t.source_task_id and t.source_task_id.startswith("shutdown_")
                ]
                pending_thoughts = shutdown_thoughts
                logger.info(f"In SHUTDOWN state - filtering to {len(shutdown_thoughts)} shutdown-related thoughts only")

            max_active = 10
            if hasattr(self.app_config, "workflow") and self.app_config.workflow:
                max_active = getattr(self.app_config.workflow, "max_active_thoughts", 10)

            limited_thoughts = pending_thoughts[:max_active]

            logger.info(
                f"Found {len(pending_thoughts)} PENDING thoughts, processing {len(limited_thoughts)} (max_active_thoughts: {max_active})"
            )

            if not limited_thoughts:
                return 0

            processed_count = 0
            failed_count = 0

            batch_size = 5

            for i in range(0, len(limited_thoughts), batch_size):
                try:
                    batch = limited_thoughts[i : i + batch_size]

                    # Pre-fetch all thoughts in the batch to avoid serialization
                    thought_ids = [t.thought_id for t in batch]
                    logger.info(f"[DEBUG TIMING] Pre-fetching {len(thought_ids)} thoughts in batch")
                    prefetched_thoughts = await persistence.async_get_thoughts_by_ids(thought_ids)
                    logger.info(f"[DEBUG TIMING] Pre-fetched {len(prefetched_thoughts)} thoughts")

                    # Pre-fetch batch context data (same for all thoughts)
                    logger.info("[DEBUG TIMING] Pre-fetching batch context data")
                    from ciris_engine.logic.context.batch_context import prefetch_batch_context

                    batch_context_data = await prefetch_batch_context(
                        memory_service=(
                            self.services.get("memory_service")
                            if isinstance(self.services, dict)
                            else getattr(self.services, "memory_service", None)
                        ),
                        secrets_service=(
                            self.services.get("secrets_service")
                            if isinstance(self.services, dict)
                            else getattr(self.services, "secrets_service", None)
                        ),
                        service_registry=(
                            self.services.get("service_registry")
                            if isinstance(self.services, dict)
                            else getattr(self.services, "service_registry", None)
                        ),
                        resource_monitor=(
                            self.services.get("resource_monitor")
                            if isinstance(self.services, dict)
                            else getattr(self.services, "resource_monitor", None)
                        ),
                        telemetry_service=(
                            self.services.get("telemetry_service")
                            if isinstance(self.services, dict)
                            else getattr(self.services, "telemetry_service", None)
                        ),
                        runtime=self.runtime,
                    )
                    logger.info("[DEBUG TIMING] Pre-fetched batch context data")

                    tasks: List[Any] = []
                    for thought in batch:
                        try:
                            persistence.update_thought_status(
                                thought_id=thought.thought_id, status=ThoughtStatus.PROCESSING
                            )

                            # Use prefetched thought if available
                            full_thought = prefetched_thoughts.get(thought.thought_id, thought)
                            task = self._process_single_thought(
                                full_thought, prefetched=True, batch_context=batch_context_data
                            )
                            tasks.append(task)
                        except Exception as e:
                            logger.error(
                                f"Error preparing thought {thought.thought_id} for processing: {e}", exc_info=True
                            )
                            failed_count += 1
                            continue

                    if not tasks:
                        continue

                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result, thought in zip(results, batch):
                        try:
                            if isinstance(result, Exception):
                                logger.error(f"Error processing thought {thought.thought_id}: {result}")
                                persistence.update_thought_status(
                                    thought_id=thought.thought_id,
                                    status=ThoughtStatus.FAILED,
                                    final_action={"error": str(result)},
                                )
                                failed_count += 1
                            else:
                                processed_count += 1
                        except Exception as e:
                            logger.error(f"Error handling result for thought {thought.thought_id}: {e}", exc_info=True)
                            failed_count += 1

                except Exception as e:
                    logger.error(f"Error processing thought batch {i//batch_size + 1}: {e}", exc_info=True)
                    failed_count += len(batch) if "batch" in locals() else batch_size

            if failed_count > 0:
                logger.warning(
                    f"Thought processing completed with {failed_count} failures out of {len(limited_thoughts)} attempts"
                )

            return processed_count

        except Exception as e:
            logger.error(f"CRITICAL: Error in _process_pending_thoughts_async: {e}", exc_info=True)
            return 0

    async def _process_single_thought(
        self, thought: Thought, prefetched: bool = False, batch_context: Optional[Any] = None
    ) -> bool:
        """Process a single thought and dispatch its action, with comprehensive error handling."""
        logger.info(
            f"[DEBUG TIMING] _process_single_thought START for thought {thought.thought_id} (prefetched={prefetched}, has_batch_context={batch_context is not None})"
        )
        start_time = self._time_service.now()
        trace_id = f"task_{thought.source_task_id or 'unknown'}_{thought.thought_id}"
        span_id = f"agent_processor_{thought.thought_id}"

        # Create TRACE_SPAN correlation for this thought processing
        trace_context = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,  # Add missing parent_span_id
            span_name="process_single_thought",
            span_kind="internal",
            baggage={
                "thought_id": thought.thought_id,
                "task_id": thought.source_task_id or "",
                "processor_state": self.state_manager.get_state().value,
            },
        )

        correlation = ServiceCorrelation(
            correlation_id=f"trace_{span_id}_{start_time.timestamp()}",
            correlation_type=CorrelationType.TRACE_SPAN,
            service_type="agent_processor",
            handler_name="AgentProcessor",
            action_type="process_thought",
            created_at=start_time,
            updated_at=start_time,
            timestamp=start_time,
            trace_context=trace_context,
            tags={
                "thought_id": thought.thought_id,
                "task_id": thought.source_task_id or "",
                "component_type": "agent_processor",
                "trace_depth": "1",
                "thought_type": thought.thought_type.value if thought.thought_type else "unknown",
                "processor_state": self.state_manager.get_state().value,
            },
            # Add missing required fields
            request_data=None,
            response_data=None,
            status=ServiceCorrelationStatus.PENDING,
            metric_data=None,
            log_data=None,
            retention_policy="raw",
            ttl_seconds=None,
            parent_correlation_id=None,
        )

        # Add correlation to track this processing
        persistence.add_correlation(correlation, self._time_service)

        try:
            # Create processing queue item
            item = ProcessingQueueItem.from_thought(thought)

            # Use the current state's processor for fallback-aware processing
            processor = self.state_processors.get(self.state_manager.get_state())
            if processor is None:
                logger.error(f"No processor found for state {self.state_manager.get_state()}")
                persistence.update_thought_status(
                    thought_id=thought.thought_id,
                    status=ThoughtStatus.FAILED,
                    final_action={"error": f"No processor for state {self.state_manager.get_state()}"},
                )
                # Update correlation with failure
                end_time = self._time_service.now()
                correlation.response_data = ServiceResponseData(
                    success=False,
                    error_message=f"No processor for state {self.state_manager.get_state()}",
                    execution_time_ms=(end_time - start_time).total_seconds() * 1000,
                    response_timestamp=end_time,
                    # Add missing required fields
                    result_summary=None,
                    result_type=None,
                    result_size=None,
                    error_type="ProcessorNotFound",
                    error_traceback=None,
                    tokens_used=None,
                    memory_bytes=None,
                )
                correlation.updated_at = end_time
                persistence.update_correlation(correlation.correlation_id, correlation, self._time_service)
                return False

            # Use fallback-aware process_thought_item
            try:
                logger.info(f"[DEBUG TIMING] Calling processor.process_thought_item for thought {thought.thought_id}")
                context = ProcessorContext(
                    origin="wakeup_async",
                    prefetched_thought=thought if prefetched else None,
                    batch_context=batch_context,
                )
                result = await processor.process_thought_item(item, context=context.model_dump())
            except Exception as e:
                logger.error(
                    f"Error in processor.process_thought_item for thought {thought.thought_id}: {e}", exc_info=True
                )
                persistence.update_thought_status(
                    thought_id=thought.thought_id,
                    status=ThoughtStatus.FAILED,
                    final_action={"error": f"Processor error: {e}"},
                )
                # Update correlation with failure
                end_time = self._time_service.now()
                correlation.response_data = ServiceResponseData(
                    success=False,
                    error_message=f"Processor error: {e}",
                    execution_time_ms=(end_time - start_time).total_seconds() * 1000,
                    response_timestamp=end_time,
                    # Add missing required fields
                    result_summary=None,
                    result_type=None,
                    result_size=None,
                    error_type=type(e).__name__,
                    error_traceback=None,
                    tokens_used=None,
                    memory_bytes=None,
                )
                correlation.updated_at = end_time
                persistence.update_correlation(correlation.correlation_id, correlation, self._time_service)
                return False

            if result:
                try:
                    # Get the task for context
                    task = persistence.get_task_by_id(thought.source_task_id)

                    # Extract conscience result if available
                    conscience_result = getattr(result, "_conscience_result", None)

                    dispatch_context = build_dispatch_context(
                        thought=thought,
                        time_service=self._time_service,
                        task=task,
                        app_config=self.app_config,
                        round_number=self.current_round_number,
                        conscience_result=conscience_result,
                        action_type=result.selected_action if result else None,
                    )
                    # Services should be accessed via service registry, not passed in context
                    # to avoid serialization issues during audit logging

                    await self.action_dispatcher.dispatch(
                        action_selection_result=result, thought=thought, dispatch_context=dispatch_context
                    )
                    return True
                except Exception as e:
                    logger.error(
                        f"Error in action_dispatcher.dispatch for thought {thought.thought_id}: {e}", exc_info=True
                    )
                    persistence.update_thought_status(
                        thought_id=thought.thought_id,
                        status=ThoughtStatus.FAILED,
                        final_action={"error": f"Dispatch error: {e}"},
                    )
                    # Update correlation with dispatch failure
                    end_time = self._time_service.now()
                    correlation.response_data = ServiceResponseData(
                        success=False,
                        error_message=f"Dispatch error: {e}",
                        execution_time_ms=(end_time - start_time).total_seconds() * 1000,
                        response_timestamp=end_time,
                        # Add missing required fields
                        result_summary=None,
                        result_type=None,
                        result_size=None,
                        error_type=type(e).__name__,
                        error_traceback=None,
                        tokens_used=None,
                        memory_bytes=None,
                    )
                    correlation.updated_at = end_time
                    persistence.update_correlation(correlation.correlation_id, correlation, self._time_service)
                    return False
            else:
                try:
                    # Check if the thought was already handled (e.g., TASK_COMPLETE)
                    updated_thought = await persistence.async_get_thought_by_id(thought.thought_id)
                    if updated_thought and updated_thought.status in [ThoughtStatus.COMPLETED, ThoughtStatus.FAILED]:
                        logger.debug(
                            f"Thought {thought.thought_id} was already handled with status {updated_thought.status.value}"
                        )
                        # Update correlation - thought was already handled
                        end_time = self._time_service.now()
                        correlation.response_data = ServiceResponseData(
                            success=True,
                            result_summary=f"Thought already handled with status {updated_thought.status.value}",
                            execution_time_ms=(end_time - start_time).total_seconds() * 1000,
                            response_timestamp=end_time,
                            # Add missing required fields
                            result_type="already_handled",
                            result_size=None,
                            error_type=None,
                            error_message=None,
                            error_traceback=None,
                            tokens_used=None,
                            memory_bytes=None,
                        )
                        correlation.updated_at = end_time
                        persistence.update_correlation(correlation.correlation_id, correlation, self._time_service)
                        return True
                    else:
                        logger.warning(f"No result from processing thought {thought.thought_id}")
                        persistence.update_thought_status(
                            thought_id=thought.thought_id,
                            status=ThoughtStatus.FAILED,
                            final_action={"error": "No processing result and thought not already handled"},
                        )
                        return False
                except Exception as e:
                    logger.error(f"Error checking thought status for {thought.thought_id}: {e}", exc_info=True)
                    return False
        except Exception as e:
            logger.error(f"CRITICAL: Unhandled error processing thought {thought.thought_id}: {e}", exc_info=True)
            try:
                persistence.update_thought_status(
                    thought_id=thought.thought_id,
                    status=ThoughtStatus.FAILED,
                    final_action={"error": f"Critical processing error: {e}"},
                )
            except Exception as update_error:
                logger.error(f"Failed to update thought status after critical error: {update_error}", exc_info=True)

            # Update correlation with critical error
            end_time = self._time_service.now()
            correlation.response_data = ServiceResponseData(
                success=False,
                error_message=f"Critical processing error: {e}",
                execution_time_ms=(end_time - start_time).total_seconds() * 1000,
                response_timestamp=end_time,
                # Add missing required fields
                result_summary=None,
                result_type=None,
                result_size=None,
                error_type="CriticalError",
                error_traceback=None,
                tokens_used=None,
                memory_bytes=None,
            )
            correlation.updated_at = end_time
            correlation.tags["task_status"] = "FAILED"
            try:
                persistence.update_correlation(correlation.correlation_id, correlation, self._time_service)
            except Exception as corr_error:
                logger.error(f"Failed to update correlation after critical error: {corr_error}")
            raise

    async def pause_processing(self) -> bool:
        """
        Pause the agent processor.
        Safe to call even if already paused.

        Returns:
            True if successfully paused or already paused
        """
        if self._is_paused:
            logger.info("AgentProcessor already paused")
            return True

        logger.info("Pausing AgentProcessor")
        self._is_paused = True

        # Create pause event if needed
        if self._pause_event is None:
            self._pause_event = asyncio.Event()

        # Create pipeline controller for single-stepping
        if self._pipeline_controller is None:
            from ciris_engine.protocols.pipeline_control import PipelineController

            self._pipeline_controller = PipelineController(is_paused=True)

        # Inject pipeline controller into thought processor
        if hasattr(self.thought_processor, "set_pipeline_controller"):
            self.thought_processor.set_pipeline_controller(self._pipeline_controller)

        return True

    async def resume_processing(self) -> bool:
        """
        Resume the agent processor from pause.

        Returns:
            True if successfully resumed
        """
        if not self._is_paused:
            logger.info("AgentProcessor not paused")
            return False

        logger.info("Resuming AgentProcessor")
        self._is_paused = False
        self._single_step_mode = False

        # Resume all paused thoughts in pipeline
        if self._pipeline_controller:
            self._pipeline_controller.resume_all()

        # Signal pause event to continue
        if self._pause_event:
            self._pause_event.set()

        return True

    def is_paused(self) -> bool:
        """Check if processor is paused."""
        return self._is_paused

    def set_thought_processing_callback(self, callback: Any) -> None:
        """Set callback for thought processing time tracking."""
        self._thought_processing_callback = callback

    async def single_step(self) -> dict:
        """
        Execute one step in the pipeline when paused.

        Drains pipeline in order:
        1. First process thoughts at later step points
        2. Then process thoughts at earlier step points
        3. Finally allow new thoughts to enter

        Returns:
            StepResult for the step executed
        """
        if not self._is_paused:
            return {"success": False, "error": "Cannot single-step unless paused"}

        if not self._pipeline_controller:
            return {"success": False, "error": "Pipeline controller not initialized"}

        start_time = self._time_service.now()

        # Enable single-step mode
        self._single_step_mode = True
        self._pipeline_controller._single_step_mode = True

        try:
            # Get next thought to process based on pipeline state
            thought_id = self._pipeline_controller.drain_pipeline_step()

            if thought_id:
                # Resume this specific thought
                logger.info(f"Single-stepping thought {thought_id}")
                self._pipeline_controller.resume_thought(thought_id)

                # Wait for it to hit the next step point
                # The thought will pause at the next step point automatically
                await asyncio.sleep(0.1)  # Give it time to process

                # Get the step result from pipeline controller
                pipeline_state = self._pipeline_controller.get_pipeline_state()

                # Find the thought and its current step
                for step_thoughts in pipeline_state.thoughts_by_step.values():
                    for thought in step_thoughts:
                        if thought.thought_id == thought_id:
                            return {
                                "success": True,
                                "thought_id": thought_id,
                                "current_step": thought.current_step.value,
                                "processing_time_ms": (self._time_service.now() - start_time).total_seconds() * 1000,
                                "pipeline_state": pipeline_state.dict(),
                            }

            # No thoughts in pipeline, try to get a new one
            from ciris_engine.logic import persistence
            from ciris_engine.schemas.runtime.models import ThoughtStatus

            pending_thoughts = persistence.get_thoughts_by_status(ThoughtStatus.PENDING, limit=1)

            if not pending_thoughts:
                return {
                    "success": True,
                    "message": "No thoughts to process",
                    "pipeline_empty": True,
                    "processing_time_ms": (self._time_service.now() - start_time).total_seconds() * 1000,
                }

            thought = pending_thoughts[0]

            # Process this thought - it will pause at first step point
            logger.info(f"Single-stepping new thought {thought.thought_id}")

            # Mark for single-step processing
            success = await self._process_single_thought(thought)

            # Track processing time
            processing_time_ms = (self._time_service.now() - start_time).total_seconds() * 1000
            if self._thought_processing_callback:
                self._thought_processing_callback(processing_time_ms)

            return {
                "success": success,
                "thought_id": thought.thought_id,
                "new_thought": True,
                "processing_time_ms": processing_time_ms,
                "current_state": self.state_manager.get_state().value,
            }

        except Exception as e:
            logger.error(f"Error in single_step: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "processing_time_ms": (self._time_service.now() - start_time).total_seconds() * 1000,
            }
        finally:
            # Disable single-step mode
            self._single_step_mode = False
            if self._pipeline_controller:
                self._pipeline_controller._single_step_mode = False

    async def stop_processing(self) -> None:
        """Stop the processing loop gracefully."""
        if self._processing_task is None or self._processing_task.done():
            logger.info("Processing loop is not running")
            return

        logger.info("Stopping processing loop...")
        if self._stop_event is not None:
            self._stop_event.set()

        if self.state_manager.get_state() == AgentState.DREAM and self.dream_processor:
            await self.dream_processor.stop_dreaming()

        for processor in self.state_processors.values():
            try:
                processor.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up {processor}: {e}")

        self.state_manager.transition_to(AgentState.SHUTDOWN)

        try:
            await asyncio.wait_for(self._processing_task, timeout=10.0)
            logger.info("Processing loop stopped")
        except asyncio.TimeoutError:
            logger.warning("Processing loop did not stop within timeout, cancelling")
            if self._processing_task is not None:
                self._processing_task.cancel()
                try:
                    await self._processing_task
                except asyncio.CancelledError:
                    logger.info("Processing task cancelled")
                    raise
        finally:
            self._processing_task = None

    async def _processing_loop(self, num_rounds: Optional[int] = None) -> None:
        """Main processing loop with state management and comprehensive exception handling."""
        logger.info(f"Processing loop started (num_rounds: {num_rounds})")
        round_count = 0
        consecutive_errors = 0
        max_consecutive_errors = 5

        try:
            logger.info("Entering main processing while loop...")
            while not (self._stop_event is not None and self._stop_event.is_set()):
                try:
                    if num_rounds is not None and round_count >= num_rounds:
                        logger.info(f"Reached target rounds ({num_rounds}), requesting graceful shutdown")
                        request_global_shutdown(f"Processing completed after {num_rounds} rounds")
                        break

                    # Update round number
                    # self.thought_processor.advance_round()  # Removed nonexistent method
                    self.current_round_number += 1

                    # Get current state
                    current_state = self.state_manager.get_state()

                    # Never transition away from SHUTDOWN state
                    if current_state == AgentState.SHUTDOWN:
                        logger.debug("In SHUTDOWN state, skipping transition checks")
                    else:
                        # Check if shutdown has been requested
                        if is_global_shutdown_requested():
                            shutdown_reason = get_global_shutdown_reason() or "Unknown reason"
                            logger.info(f"Global shutdown requested: {shutdown_reason}")
                            # Transition to shutdown state if not already there
                            if self.state_manager.can_transition_to(AgentState.SHUTDOWN):
                                await self._handle_state_transition(AgentState.SHUTDOWN)
                            else:
                                logger.error(f"Cannot transition from {current_state} to SHUTDOWN")
                                break
                        else:
                            # Check for automatic state transitions only if not shutting down
                            next_state = self.state_manager.should_auto_transition()
                            if next_state:
                                await self._handle_state_transition(next_state)

                    # Process based on current state
                    current_state = self.state_manager.get_state()
                    logger.info(f"Processing round {round_count}, current state: {current_state}")

                    # Get processor for current state
                    processor = self.state_processors.get(current_state)
                    logger.info(
                        f"Got processor for state {current_state}: {processor.__class__.__name__ if processor else 'None'}"
                    )

                    if processor and current_state != AgentState.SHUTDOWN:
                        # Use the appropriate processor (except for SHUTDOWN which has special handling)
                        try:
                            logger.info(
                                f"Calling {processor.__class__.__name__}.process(round={self.current_round_number})"
                            )
                            result = await processor.process(self.current_round_number)
                            logger.info(
                                f"Processor returned: {result.__class__.__name__ if hasattr(result, '__class__') else type(result)}"
                            )
                            round_count += 1
                            consecutive_errors = 0  # Reset error counter on success

                            # Check for state transition recommendations
                            if current_state == AgentState.WORK:
                                # Check for scheduled dream tasks
                                if await self._check_scheduled_dream():
                                    logger.info("Scheduled dream time has arrived")
                                    await self._handle_state_transition(AgentState.DREAM)

                            elif current_state == AgentState.SOLITUDE and processor == self.solitude_processor:
                                # Check if the result indicates we should exit solitude
                                # Result is now typed as SolitudeResult
                                if hasattr(result, "should_exit_solitude") and result.should_exit_solitude:
                                    exit_reason = getattr(result, "exit_reason", "Unknown reason")
                                    logger.info(f"Exiting solitude: {exit_reason}")
                                    await self._handle_state_transition(AgentState.WORK)

                        except Exception as e:
                            consecutive_errors += 1
                            logger.error(f"Error in {processor} for state {current_state}: {e}", exc_info=True)

                            if consecutive_errors >= max_consecutive_errors:
                                logger.error(
                                    f"Too many consecutive processing errors ({consecutive_errors}), requesting shutdown"
                                )
                                request_global_shutdown(f"Processing errors: {consecutive_errors} consecutive failures")
                                break

                            # Add backoff delay after errors
                            await asyncio.sleep(min(consecutive_errors * 2, 30))

                    elif current_state == AgentState.DREAM:
                        # Dream processing is handled by enhanced dream processor
                        if not self.dream_processor._dream_task or self.dream_processor._dream_task.done():
                            # Dream ended, transition back to WORK
                            logger.info("Dream processing complete, returning to WORK state")
                            await self._handle_state_transition(AgentState.WORK)
                        else:
                            await asyncio.sleep(5)  # Check periodically

                    elif current_state == AgentState.SHUTDOWN:
                        # Process shutdown state with negotiation
                        logger.info("In SHUTDOWN state, processing shutdown negotiation")
                        processor = self.state_processors.get(current_state)
                        logger.debug(f"Shutdown processor from state_processors: {processor}")
                        if processor:
                            try:
                                result = await processor.process(self.current_round_number)
                                round_count += 1
                                consecutive_errors = 0

                                # Check if shutdown is complete
                                logger.info(f"Shutdown check - result type: {type(result)}, result: {result}")

                                # Handle ShutdownResult object (not dict)
                                logger.debug(
                                    f"Result is object, checking for shutdown_ready: hasattr={hasattr(result, 'shutdown_ready')}"
                                )
                                if hasattr(result, "shutdown_ready"):
                                    logger.debug(f"result.shutdown_ready = {result.shutdown_ready}")
                                    if result.shutdown_ready:
                                        logger.info(
                                            "Shutdown negotiation complete (from result object), exiting processing loop"
                                        )
                                        break

                                # Check processor's shutdown_complete attribute directly
                                if hasattr(processor, "shutdown_complete"):
                                    logger.debug(f"processor.shutdown_complete = {processor.shutdown_complete}")
                                    if processor.shutdown_complete:
                                        logger.info(
                                            "Shutdown negotiation complete (processor.shutdown_complete is True), exiting processing loop"
                                        )
                                        break
                            except Exception as e:
                                consecutive_errors += 1
                                logger.error(f"Error in shutdown processor: {e}", exc_info=True)
                                break
                        else:
                            logger.error("No shutdown processor available")
                            break

                    else:
                        logger.warning(f"No processor for state: {current_state}")
                        await asyncio.sleep(1)

                    # Brief delay between rounds
                    # Get delay from config, using mock LLM delay if enabled
                    delay = 1.0
                    if hasattr(self.app_config, "workflow"):
                        mock_llm = getattr(self.app_config, "mock_llm", False)
                        if hasattr(self.app_config.workflow, "get_round_delay"):
                            delay = self.app_config.workflow.get_round_delay(mock_llm)
                        elif hasattr(self.app_config.workflow, "round_delay_seconds"):
                            delay = self.app_config.workflow.round_delay_seconds

                    # State-specific delays override config only if not using mock LLM
                    if not getattr(self.app_config, "mock_llm", False):
                        if current_state == AgentState.WORK:
                            delay = 3.0  # 3 second delay in work mode as requested
                        elif current_state == AgentState.SOLITUDE:
                            delay = 10.0  # Slower pace in solitude
                        elif current_state == AgentState.DREAM:
                            delay = 5.0  # Check dream state periodically

                    if delay > 0 and not (self._stop_event is not None and self._stop_event.is_set()):
                        try:
                            if self._stop_event is not None:
                                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                                break  # Stop event was set
                            else:
                                await asyncio.sleep(delay)
                        except asyncio.TimeoutError:
                            pass  # Continue processing

                except Exception as e:
                    consecutive_errors += 1
                    logger.error(
                        f"CRITICAL: Unhandled error in processing loop round {self.current_round_number}: {e}",
                        exc_info=True,
                    )

                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(
                            f"Processing loop has failed {consecutive_errors} consecutive times, requesting shutdown"
                        )
                        request_global_shutdown(
                            f"Critical processing loop failure: {consecutive_errors} consecutive errors"
                        )
                        break

                    # Emergency backoff after critical errors
                    await asyncio.sleep(min(consecutive_errors * 5, 60))

        except Exception as e:
            logger.error(f"FATAL: Catastrophic error in processing loop: {e}", exc_info=True)
            request_global_shutdown(f"Catastrophic processing loop error: {e}")
            raise
        finally:
            logger.info("Processing loop finished")

    async def _handle_state_transition(self, target_state: AgentState) -> None:
        """Handle transitioning to a new state."""
        current_state = self.state_manager.get_state()

        if not self.state_manager.transition_to(target_state):
            logger.error(f"Failed to transition from {current_state} to {target_state}")
            return

        if target_state == AgentState.SHUTDOWN:
            # Special handling for shutdown transition
            logger.info("Transitioning to SHUTDOWN - clearing non-shutdown thoughts from queue")
            # The shutdown processor will create its own thoughts
            # Any pending thoughts will be cleaned up on next startup

        elif target_state == AgentState.DREAM:
            logger.info("Entering DREAM state for self-reflection")
            # Start the enhanced dream processor
            if self.dream_processor:
                await self.dream_processor.start_dreaming(duration=30 * 60)  # 30 minutes default
            else:
                logger.error("Dream processor not available")

        elif target_state == AgentState.WORK and current_state == AgentState.DREAM:
            if self.dream_processor:
                await self.dream_processor.stop_dreaming()
                summary = self.dream_processor.get_dream_summary()
                logger.info(f"Dream summary: {summary}")
            else:
                logger.info("Dream processor not available, no cleanup needed")

        if target_state in self.state_processors:
            processor = self.state_processors[target_state]
            processor.initialize()

    async def process(self, round_number: int) -> dict:
        """Execute one round of processing based on current state."""
        current_state = self.state_manager.get_state()
        processor = self.state_processors.get(current_state)

        if processor:
            # Process and convert typed result to dict for backward compatibility
            typed_result = await processor.process(round_number)
            # Convert typed result to dict
            return (
                typed_result.model_dump()
                if hasattr(typed_result, "model_dump")
                else {"state": current_state.value, "round_number": round_number}
            )
        elif current_state == AgentState.DREAM:
            # Dream state handled separately
            return {"state": "dream", "round_number": round_number}
        else:
            return {"state": current_state.value, "round_number": round_number, "error": "No processor available"}

    def get_current_state(self) -> str:
        """Get current processing state.

        Returns:
            Current AgentState value as string
        """
        return self.state_manager.get_state().value

    def get_status(self) -> dict:
        """Get current processor status."""
        status: dict = {
            "state": self.state_manager.get_state().value,
            "state_duration": self.state_manager.get_state_duration(),
            "round_number": self.current_round_number,
            "is_processing": self._processing_task is not None and not self._processing_task.done(),
        }

        current_state = self.state_manager.get_state()

        if current_state == AgentState.WAKEUP:
            status["wakeup_status"] = self.wakeup_processor.get_status()

        elif current_state == AgentState.WORK:
            status["work_status"] = self.work_processor.get_status()

        elif current_state == AgentState.PLAY:
            status["play_status"] = self.play_processor.get_status()

        elif current_state == AgentState.SOLITUDE:
            status["solitude_status"] = self.solitude_processor.get_status()

        elif current_state == AgentState.DREAM:
            if self.dream_processor:
                status["dream_summary"] = self.dream_processor.get_dream_summary()
            else:
                status["dream_summary"] = {"state": "unavailable", "error": "Dream processor not available"}

        status["processor_metrics"] = {}
        for state, processor in self.state_processors.items():
            status["processor_metrics"][state.value] = processor.get_metrics()

        status["queue_status"] = self._get_detailed_queue_status()

        return status

    async def _schedule_initial_dream(self) -> None:
        """Schedule the first dream session 6 hours from startup."""
        try:
            from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

            memory_service = self.services.get("memory_service")
            if not memory_service:
                logger.warning("Cannot schedule initial dream - no memory service")
                return

            # Schedule 6 hours from now
            dream_time = self._time_service.now() + timedelta(hours=6)

            dream_task = GraphNode(
                id=f"dream_schedule_{int(dream_time.timestamp())}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={
                    "task_type": "scheduled_dream",
                    "scheduled_for": dream_time.isoformat(),
                    "duration_minutes": 30,
                    "priority": "health_maintenance",
                    "can_defer": True,
                    "defer_window_hours": 2,
                    "message": "Time for introspection and learning",
                    "is_initial": True,
                },
                # Add missing required fields
                updated_by="main_processor",
                updated_at=self._time_service.now(),
            )

            await memory_service.memorize(dream_task)

            logger.info(f"Scheduled initial dream session for {dream_time.isoformat()}")

        except Exception as e:
            logger.error(f"Failed to schedule initial dream: {e}")

    async def _check_scheduled_dream(self) -> bool:
        """Check if there's a scheduled dream task that's due."""
        try:
            # Import at function level to avoid circular imports
            from ciris_engine.schemas.services.graph_core import GraphScope
            from ciris_engine.schemas.services.operations import MemoryQuery

            memory_service = self.services.get("memory_service")
            if not memory_service:
                return False

            # Query for scheduled dream tasks
            query = MemoryQuery(
                node_id="dream_schedule_*", scope=GraphScope.LOCAL, type=None, include_edges=False, depth=1
            )

            dream_tasks = await memory_service.recall(query)

            now = self._time_service.now()

            for task in dream_tasks:
                # Handle both dict and GraphNodeAttributes
                attributes = task.attributes
                scheduled_for = (
                    attributes.get("scheduled_for")
                    if hasattr(attributes, "get")
                    else getattr(attributes, "scheduled_for", None)
                )
                if scheduled_for:
                    # Parse ISO format datetime
                    if isinstance(scheduled_for, str):
                        # Handle both 'Z' and '+00:00' formats
                        scheduled_str = scheduled_for
                        if scheduled_str.endswith("Z"):
                            scheduled_str = scheduled_str[:-1] + "+00:00"
                        scheduled_time = datetime.fromisoformat(scheduled_str)
                    else:
                        scheduled_time = scheduled_for

                    # Check if it's time (with 2 hour defer window)
                    # Handle both dict and GraphNodeAttributes
                    attributes = task.attributes
                    defer_hours = (
                        attributes.get("defer_window_hours", 2)
                        if hasattr(attributes, "get")
                        else getattr(attributes, "defer_window_hours", 2)
                    )
                    defer_window = timedelta(hours=defer_hours)

                    if now >= scheduled_time and now <= scheduled_time + defer_window:
                        # Check dream health - when was last dream?
                        if self.dream_processor and self.dream_processor.dream_metrics.get("end_time"):
                            last_dream = datetime.fromisoformat(self.dream_processor.dream_metrics["end_time"])
                            hours_since = (now - last_dream).total_seconds() / 3600

                            # Don't dream if we dreamed less than 4 hours ago
                            if hours_since < 4:
                                logger.debug(f"Skipping scheduled dream - last dream was {hours_since:.1f} hours ago")
                                return False

                        logger.info(f"Scheduled dream task {task.id} is due")
                        return True

            return False

        except Exception as e:
            logger.error(f"Error checking scheduled dreams: {e}")
            return False

    def _get_detailed_queue_status(self) -> dict:
        """Get detailed processing queue status information."""
        try:
            # Get thought counts by status
            from ciris_engine.logic import persistence
            from ciris_engine.schemas.runtime.models import ThoughtStatus

            pending_count = persistence.count_thoughts_by_status(ThoughtStatus.PENDING)
            processing_count = persistence.count_thoughts_by_status(ThoughtStatus.PROCESSING)
            completed_count = persistence.count_thoughts_by_status(ThoughtStatus.COMPLETED)
            failed_count = persistence.count_thoughts_by_status(ThoughtStatus.FAILED)

            # Get recent thought activity
            recent_thoughts = []
            try:
                # Get last 5 thoughts for activity overview
                from ciris_engine.logic.persistence.models.thoughts import get_recent_thoughts

                recent_data = get_recent_thoughts(limit=5)
                for thought_data in recent_data:
                    content_str = str(thought_data.content or "")
                    recent_thoughts.append(
                        {
                            "thought_id": thought_data.thought_id,
                            "thought_type": thought_data.thought_type or "unknown",
                            "status": thought_data.status or "unknown",
                            "created_at": getattr(thought_data, "created_at", "unknown"),
                            "content_preview": content_str[:100] + "..." if len(content_str) > 100 else content_str,
                        }
                    )
            except Exception as e:
                logger.warning(f"Could not fetch recent thoughts: {e}")
                recent_thoughts = []

            # Get task information
            task_info: dict = {}
            try:
                if hasattr(self, "work_processor") and self.work_processor:
                    task_info = {
                        "active_tasks": self.work_processor.task_manager.get_active_task_count(),
                        "pending_tasks": self.work_processor.task_manager.get_pending_task_count(),
                    }
            except Exception as e:
                logger.warning(f"Could not fetch task info: {e}")
                task_info = {"error": str(e)}

            return {
                "thought_counts": {
                    "pending": pending_count,
                    "processing": processing_count,
                    "completed": completed_count,
                    "failed": failed_count,
                    "total": pending_count + processing_count + completed_count + failed_count,
                },
                "recent_activity": recent_thoughts,
                "task_summary": task_info,
                "queue_health": {
                    "has_pending_work": pending_count > 0,
                    "has_processing_work": processing_count > 0,
                    "has_recent_failures": failed_count > 0,
                    "queue_utilization": (
                        "high"
                        if pending_count + processing_count > 10
                        else "medium" if pending_count + processing_count > 3 else "low"
                    ),
                },
            }
        except Exception as e:
            logger.error(f"Error getting detailed queue status: {e}", exc_info=True)
            return {
                "error": str(e),
                "thought_counts": {"error": "Could not fetch counts"},
                "recent_activity": [],
                "task_summary": {"error": "Could not fetch task info"},
                "queue_health": {"error": "Could not determine health"},
            }

    def get_state_history(self, limit: int = 10) -> List[StateTransitionRecord]:
        """
        Get recent state transition history.

        Args:
            limit: Maximum number of transitions to return

        Returns:
            List of state transitions with timestamps and reasons
        """
        all_transitions = self.state_manager.get_state_history()
        # Return the most recent transitions up to the limit
        return all_transitions[-limit:] if len(all_transitions) > limit else all_transitions

    def get_queue_status(self) -> Any:
        """
        Get current queue status with pending tasks and thoughts.

        Returns an object with pending_tasks and pending_thoughts attributes
        for use by the runtime control service.
        """
        # Use the centralized persistence function
        return persistence.get_queue_status()

    def get_metrics(self) -> dict:
        """Get all metrics including base, custom, and v1.4.3 specific."""
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        # Add v1.4.3 specific metrics
        # Calculate total thoughts processed by aggregating from all state processors
        total_thoughts = 0
        total_actions = 0

        for processor in self.state_processors.values():
            if hasattr(processor, "metrics"):
                processor_metrics = processor.get_metrics()
                total_thoughts += processor_metrics.items_processed
                total_actions += processor_metrics.additional_metrics.actions_dispatched

        # Get state transitions count from state manager history
        state_transitions = len(self.state_manager.get_state_history())

        # Get current state as integer (AgentState enum values map to ints)
        current_state_int = self.state_manager.get_state().value

        # Convert state string to integer mapping for the API
        state_mapping = {"wakeup": 0, "work": 1, "play": 2, "solitude": 3, "dream": 4, "shutdown": 5}
        current_state_value = state_mapping.get(current_state_int.lower(), 0)

        metrics.update(
            {
                "processor_thoughts_total": total_thoughts,
                "processor_actions_total": total_actions,
                "processor_state_transitions": state_transitions,
                "processor_current_state": current_state_value,
            }
        )

        return metrics
