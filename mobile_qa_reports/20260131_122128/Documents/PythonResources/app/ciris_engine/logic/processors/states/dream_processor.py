"""
Dream Processor for CIRISAgent.

Integrates memory consolidation, self-configuration, and introspection during dream cycles.
Falls back to benchmark mode when CIRISNode is configured.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.logic.adapters import CIRISNodeClient
from ciris_engine.logic.buses.communication_bus import CommunicationBus
from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.core.base_processor import BaseProcessor
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.services.governance.self_observation import SelfObservationService
from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService
from ciris_engine.logic.utils.jsondict_helpers import get_bool, get_dict, get_int, get_str
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.processors.base import MetricsUpdate, ProcessorServices
from ciris_engine.schemas.processors.results import DreamResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher
    from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
    from ciris_engine.logic.registries.base import ServiceRegistry
    from ciris_engine.logic.runtime.identity_manager import IdentityManager

logger = logging.getLogger(__name__)


class DreamPhase(str, Enum):
    """Phases of dream processing."""

    ENTERING = "entering"
    CONSOLIDATING = "consolidating"
    ANALYZING = "analyzing"
    CONFIGURING = "configuring"
    PLANNING = "planning"
    BENCHMARKING = "benchmarking"
    EXITING = "exiting"


@dataclass
class DreamSession:
    """Represents a complete dream session."""

    session_id: str
    scheduled_start: Optional[datetime]
    actual_start: datetime
    planned_duration: timedelta
    phase: DreamPhase

    # Work completed
    memories_consolidated: int = 0
    patterns_analyzed: int = 0
    adaptations_made: int = 0
    future_tasks_scheduled: int = 0
    benchmarks_run: int = 0

    # Insights
    ponder_questions_processed: List[str] = field(default_factory=list)
    insights_gained: List[str] = field(default_factory=list)

    # Timing
    phase_durations: Dict[str, float] = field(default_factory=dict)
    completed_at: Optional[datetime] = None


class DreamProcessor(BaseProcessor):
    """
    Dream processor that handles introspection, memory consolidation,
    and self-configuration during dream states.
    """

    def __init__(
        self,
        config_accessor: ConfigAccessor,
        thought_processor: "ThoughtProcessor",
        action_dispatcher: "ActionDispatcher",
        services: ProcessorServices,
        service_registry: Optional["ServiceRegistry"] = None,
        identity_manager: Optional["IdentityManager"] = None,
        startup_channel_id: Optional[str] = None,
        cirisnode_url: str = "https://localhost:8001",
        pulse_interval: float = 300.0,  # 5 minutes between major activities
        min_dream_duration: int = 30,  # Minimum 30 minutes
        max_dream_duration: int = 120,  # Maximum 2 hours
        capacity_limits: Optional[Dict[str, int]] = None,  # max_active_tasks and max_active_thoughts
        agent_occurrence_id: str = "default",
    ) -> None:
        # Initialize base processor
        super().__init__(config_accessor, thought_processor, action_dispatcher, services)

        # Get time service from service registry
        self._time_service: Optional[TimeServiceProtocol] = None
        if service_registry:
            self._initialize_time_service(service_registry)
        elif services.time_service:
            time_service_val = services.time_service
            if hasattr(time_service_val, "now"):
                from typing import cast

                self._time_service = cast(TimeServiceProtocol, time_service_val)

        # Dream-specific initialization
        service_registry_val = services.service_registry
        identity_manager_val = services.identity_manager
        self.service_registry = service_registry or service_registry_val
        self.identity_manager = identity_manager or identity_manager_val
        self.startup_channel_id = startup_channel_id
        self.cirisnode_url = cirisnode_url
        self.pulse_interval = pulse_interval
        self.min_dream_duration = min_dream_duration
        self.max_dream_duration = max_dream_duration
        # Extract capacity limits from dict or use defaults
        capacity_limits = capacity_limits or {}
        self.max_active_tasks = capacity_limits.get("max_active_tasks", 50)
        self.max_active_thoughts = capacity_limits.get("max_active_thoughts", 100)
        self.agent_occurrence_id = agent_occurrence_id

        # Check if CIRISNode is configured
        self.cirisnode_enabled = self._check_cirisnode_enabled()
        self.cirisnode_client: Optional[CIRISNodeClient] = None

        # Service components
        self.self_observation_service: Optional[SelfObservationService] = None
        self.telemetry_service: Optional[GraphTelemetryService] = None
        self.memory_bus: Optional[MemoryBus] = None
        self.communication_bus: Optional[CommunicationBus] = None

        # Dream state
        self.current_session: Optional[DreamSession] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._dream_task: Optional[asyncio.Task[Any]] = None

        # Task management
        self.task_manager: Optional[Any] = None  # Will be TaskManager
        self.thought_manager: Optional[Any] = None  # Will be ThoughtManager
        self._dream_tasks: List[Any] = []  # Track our created tasks

        # Metrics from original processor
        self.dream_metrics: JSONDict = {
            "total_dreams": 0,
            "total_introspections": 0,
            "total_consolidations": 0,
            "total_adaptations": 0,
            "benchmarks_run": 0,
            "start_time": None,
            "end_time": None,
        }

    def _initialize_time_service(self, service_registry: "ServiceRegistry") -> None:
        """Initialize time service from registry."""
        try:
            from ciris_engine.schemas.runtime.enums import ServiceType

            # Get time service synchronously
            services = service_registry.get_services_by_type(ServiceType.TIME)
            if services:
                self._time_service = services[0]
            else:
                logger.warning("TimeService not found in registry, time operations may fail")
        except Exception as e:
            logger.error(f"Failed to get TimeService: {e}")

    def _check_cirisnode_enabled(self) -> bool:
        """Check if CIRISNode is configured."""
        if hasattr(self.config, "cirisnode"):
            node_cfg = self.config.cirisnode
            # Check if hostname is set and not default
            return bool(
                node_cfg.base_url
                and node_cfg.base_url != "https://localhost:8001"
                and node_cfg.base_url != "http://localhost:8001"
            )
        return False

    def _ensure_stop_event(self) -> None:
        """Ensure stop event is created when needed in async context."""
        if self._stop_event is None:
            try:
                self._stop_event = asyncio.Event()
            except RuntimeError:
                logger.warning("Cannot create stop event outside of async context")

    def _create_all_dream_tasks(self) -> None:
        """Create all dream tasks upfront for maximum parallelism."""
        from ciris_engine.logic.processors.support.task_manager import TaskManager
        from ciris_engine.logic.processors.support.thought_manager import ThoughtManager

        # Initialize managers if needed
        if not self.task_manager:
            if not self._time_service:
                raise RuntimeError("TimeService not available for TaskManager")
            self.task_manager = TaskManager(
                max_active_tasks=self.max_active_tasks,
                time_service=self._time_service,
                agent_occurrence_id=self.agent_occurrence_id,
            )
        if not self.thought_manager:
            if not self._time_service:
                raise RuntimeError("TimeService not available for ThoughtManager")
            self.thought_manager = ThoughtManager(
                time_service=self._time_service,
                max_active_thoughts=self.max_active_thoughts,
                default_channel_id=self.startup_channel_id,
                agent_occurrence_id=self.agent_occurrence_id,
            )

        # Clear any previous tasks
        self._dream_tasks.clear()

        # Memory consolidation tasks
        self._dream_tasks.extend(
            [
                self.task_manager.create_task(
                    description="Consolidate telemetry data from last 6 hours",
                    channel_id=self.startup_channel_id or "dream",
                    priority=10,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.CONSOLIDATING.value},
                ),
                self.task_manager.create_task(
                    description="Analyze memory access patterns",
                    channel_id=self.startup_channel_id or "dream",
                    priority=9,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.CONSOLIDATING.value},
                ),
                self.task_manager.create_task(
                    description="Compress redundant memories",
                    channel_id=self.startup_channel_id or "dream",
                    priority=8,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.CONSOLIDATING.value},
                ),
            ]
        )

        # Pattern analysis tasks
        self._dream_tasks.extend(
            [
                self.task_manager.create_task(
                    description="Analyze PONDER question themes",
                    channel_id=self.startup_channel_id or "dream",
                    priority=10,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.ANALYZING.value},
                ),
                self.task_manager.create_task(
                    description="Process recent incidents for patterns",
                    channel_id=self.startup_channel_id or "dream",
                    priority=10,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.ANALYZING.value},
                ),
                self.task_manager.create_task(
                    description="Detect behavioral patterns in actions",
                    channel_id=self.startup_channel_id or "dream",
                    priority=9,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.ANALYZING.value},
                ),
                self.task_manager.create_task(
                    description="Process behavioral pattern insights from feedback loop",
                    channel_id=self.startup_channel_id or "dream",
                    priority=9,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.ANALYZING.value},
                ),
            ]
        )

        # Self-configuration tasks
        self._dream_tasks.extend(
            [
                self.task_manager.create_task(
                    description="Evaluate current parameter effectiveness",
                    channel_id=self.startup_channel_id or "dream",
                    priority=9,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.CONFIGURING.value},
                ),
                self.task_manager.create_task(
                    description="Test parameter variations within safety bounds",
                    channel_id=self.startup_channel_id or "dream",
                    priority=8,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.CONFIGURING.value},
                ),
            ]
        )

        # Planning tasks
        self._dream_tasks.extend(
            [
                self.task_manager.create_task(
                    description="Schedule next dream session",
                    channel_id=self.startup_channel_id or "dream",
                    priority=6,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.PLANNING.value},
                ),
                self.task_manager.create_task(
                    description="Create improvement tasks from insights",
                    channel_id=self.startup_channel_id or "dream",
                    priority=6,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.PLANNING.value},
                ),
                self.task_manager.create_task(
                    description="Reflect on positive moments and community vibes",
                    channel_id=self.startup_channel_id or "dream",
                    priority=7,
                    context={"channel_id": self.startup_channel_id, "phase": DreamPhase.ANALYZING.value},
                ),
            ]
        )

        # Activate all tasks immediately
        from ciris_engine.logic import persistence

        if self._time_service:
            for task in self._dream_tasks:
                persistence.update_task_status(task.task_id, TaskStatus.ACTIVE, "default", self._time_service)

        logger.info(f"Created and activated {len(self._dream_tasks)} dream tasks")

    async def _initialize_services(self) -> bool:
        """Initialize required services."""
        if not self.service_registry:
            logger.warning("No service registry available for dream processor")
            return False

        try:
            from typing import cast

            # Initialize buses
            # Get time service for MemoryBus
            time_service_raw = self.services.time_service
            if not time_service_raw:
                logger.error("TimeService not available for MemoryBus initialization")
                return False
            time_service = cast(TimeServiceProtocol, time_service_raw)

            from ciris_engine.logic.buses import CommunicationBus as CB
            from ciris_engine.logic.buses import MemoryBus as MB

            self.memory_bus = MB(self.service_registry, time_service)
            self.communication_bus = CB(self.service_registry, time_service)

            # Initialize self-configuration service
            self.self_observation_service = SelfObservationService(
                memory_bus=self.memory_bus,
                time_service=time_service,
                observation_interval_hours=6,  # Match our dream schedule
            )
            await self.self_observation_service.attach_registry(self.service_registry)

            # Initialize telemetry service
            self.telemetry_service = GraphTelemetryService(memory_bus=self.memory_bus)
            await self.telemetry_service.attach_registry(self.service_registry)

            # Initialize identity baseline if needed
            if self.identity_manager and hasattr(self.identity_manager, "agent_identity"):
                # Use the existing identity directly
                identity = self.identity_manager.agent_identity
                if identity:
                    await self.self_observation_service.initialize_baseline(identity)

            logger.info("Dream processor services initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize dream services: {e}")
            return False

    async def start_dreaming(self, duration: Optional[float] = None) -> None:
        """
        Start the dream cycle.

        Args:
            duration: Dream duration in seconds. Defaults to min_dream_duration.
        """
        if self._dream_task and not self._dream_task.done():
            logger.warning("Dream cycle already running")
            return

        # Initialize services if not done
        if not self.self_observation_service:
            await self._initialize_services()

        # Calculate duration
        if duration is None:
            duration = self.min_dream_duration * 60  # Convert to seconds
        else:
            # Clamp to min/max
            duration = max(self.min_dream_duration * 60, min(duration, self.max_dream_duration * 60))

        self._ensure_stop_event()
        if self._stop_event:
            self._stop_event.clear()

        # Create session
        if not self._time_service:
            raise RuntimeError("TimeService not available for dream session")
        current_time = self._time_service.now()
        self.current_session = DreamSession(
            session_id=f"dream_{int(current_time.timestamp())}",
            scheduled_start=None,  # This is immediate entry
            actual_start=current_time,
            planned_duration=timedelta(seconds=duration),
            phase=DreamPhase.ENTERING,
        )

        self.dream_metrics["start_time"] = current_time.isoformat()
        total_dreams = get_int(self.dream_metrics, "total_dreams", 0)
        self.dream_metrics["total_dreams"] = total_dreams + 1

        # Announce dream entry
        await self._announce_dream_entry(duration)

        # Initialize CIRISNode client if enabled
        if self.cirisnode_enabled:
            self.cirisnode_client = CIRISNodeClient(service_registry=self.service_registry, base_url=self.cirisnode_url)

        logger.info(f"Starting dream cycle (duration: {duration}s)")

        # Create all dream tasks upfront for maximum parallelism
        self._create_all_dream_tasks()

        self._dream_task = asyncio.create_task(self._dream_loop(duration))

    async def stop_dreaming(self) -> None:
        """Stop the dream cycle gracefully."""
        if self._dream_task and not self._dream_task.done():
            logger.info("Stopping active dream cycle...")
            if self._stop_event:
                self._stop_event.set()

            try:
                await asyncio.wait_for(self._dream_task, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("Dream cycle did not stop within timeout, cancelling")
                self._dream_task.cancel()
                try:
                    await self._dream_task
                except asyncio.CancelledError:
                    logger.info("Dream task cancelled.")
                    raise
            except Exception as e:
                logger.error(f"Error waiting for dream task: {e}", exc_info=True)

        # Clean up CIRISNode client
        if self.cirisnode_client:
            try:
                await self.cirisnode_client.close()
            except Exception as e:
                logger.error(f"Error closing CIRISNode client: {e}")
            self.cirisnode_client = None

        if self.current_session:
            if self._time_service:
                self.current_session.completed_at = self._time_service.now()
            await self._record_dream_session()

        if self._time_service:
            self.dream_metrics["end_time"] = self._time_service.now().isoformat()
        logger.info("Dream cycle stopped")

    async def _announce_dream_entry(self, duration: float) -> None:
        """Announce dream entry to main channel."""
        if not self.communication_bus or not self.startup_channel_id:
            logger.debug("Cannot announce dream entry - no communication channel")
            return

        try:
            duration_min = int(duration / 60)
            message = "Entering self-reflection mode. " f"Returning in {duration_min} minutes or when complete."

            await self.communication_bus.send_message(
                content=message, channel_id=self.startup_channel_id, handler_name="dream_processor"
            )
        except Exception as e:
            logger.error(f"Failed to announce dream entry: {e}")

    async def process_round(self, round_number: int) -> JSONDict:
        """Process one round of dream state with maximum parallelism."""
        from ciris_engine.logic import persistence

        round_metrics: JSONDict = {
            "round_number": round_number,
            "thoughts_processed": 0,
            "tasks_activated": 0,
            "seed_thoughts_generated": 0,
            "errors": 0,
        }

        try:
            # Activate any pending tasks (fills slots from completed tasks)
            if self.task_manager:
                activated = self.task_manager.activate_pending_tasks()
                round_metrics["tasks_activated"] = activated

                # Generate seed thoughts for tasks needing them
                tasks_needing_seed = self.task_manager.get_tasks_needing_seed(limit=100)
            else:
                tasks_needing_seed = []

            if self.thought_manager and tasks_needing_seed:
                generated = self.thought_manager.generate_seed_thoughts(tasks_needing_seed, round_number)
                round_metrics["seed_thoughts_generated"] = generated

                # Populate processing queue to maximum capacity
                _queued = self.thought_manager.populate_queue(round_number)

                # Get batch and process
                batch = self.thought_manager.get_queue_batch()
            else:
                batch = None

            if batch and self.thought_manager:
                # Mark thoughts as PROCESSING
                batch = self.thought_manager.mark_thoughts_processing(batch, round_number)

                # Process all thoughts concurrently for maximum throughput
                thought_coroutines = [self._process_dream_thought(item) for item in batch]
                results = await asyncio.gather(*thought_coroutines, return_exceptions=True)

                # Handle results
                for item, result in zip(batch, results):
                    if isinstance(result, Exception):
                        logger.error(f"Error processing thought {item.thought_id}: {result}")
                        errors = round_metrics["errors"]
                        round_metrics["errors"] = int(errors) + 1 if isinstance(errors, (int, float)) else 1
                        persistence.update_thought_status(
                            item.thought_id, ThoughtStatus.FAILED, final_action={"error": str(result)}
                        )
                    elif result:
                        processed = round_metrics["thoughts_processed"]
                        round_metrics["thoughts_processed"] = (
                            int(processed) + 1 if isinstance(processed, (int, float)) else 1
                        )
                        # Result will be handled by thought processor's dispatch

            # Check if all tasks are complete
            active_count = persistence.count_active_tasks()
            pending_count = len(persistence.get_pending_tasks_for_activation(limit=1))

            if active_count == 0 and pending_count == 0:
                logger.info("All dream tasks completed")
                # Mark dream as complete
                if self._stop_event:
                    self._stop_event.set()

        except Exception as e:
            logger.error(f"Error in dream round {round_number}: {e}", exc_info=True)
            errors = round_metrics["errors"]
            round_metrics["errors"] = int(errors) + 1 if isinstance(errors, (int, float)) else 1

        return round_metrics

    async def _process_dream_thought(self, item: ProcessingQueueItem) -> Optional[Any]:
        """Process a single dream thought through the thought processor."""
        # The thought processor handles everything - context building, DMAs, actions
        # We just need to ensure dream-specific context is available
        if hasattr(item, "initial_context") and isinstance(item.initial_context, dict):
            # Add dream session info to context
            item.initial_context["dream_session_id"] = self.current_session.session_id if self.current_session else None
            item.initial_context["dream_phase"] = self.current_session.phase.value if self.current_session else None

        # Let the thought processor handle it
        # Note: We should get thought_processor from service registry or pass it in
        # For now, we'll assume it's available through the standard flow
        return None  # Actual processing happens through the standard pipeline

    async def _dream_loop(self, duration: float) -> None:
        """Main dream processing loop using standard round processing."""
        if not self.current_session:
            logger.error("No current session in dream loop")
            return

        try:
            start_time = asyncio.get_event_loop().time()
            end_time = start_time + duration
            round_number = 0

            # Process rounds until time expires or all tasks complete
            while not self._should_exit(start_time, end_time):
                if not self._time_service:
                    break
                round_start = self._time_service.now()

                # Update phase based on active tasks
                self._update_current_phase()

                # Process a round
                metrics = await self.process_round(round_number)

                # Update session metrics
                if self.current_session:
                    memories = get_int(metrics, "memories_consolidated", 0)
                    patterns = get_int(metrics, "patterns_analyzed", 0)
                    adaptations = get_int(metrics, "adaptations_made", 0)
                    self.current_session.memories_consolidated += memories
                    self.current_session.patterns_analyzed += patterns
                    self.current_session.adaptations_made += adaptations

                # Log round completion
                if self._time_service:
                    round_duration = (self._time_service.now() - round_start).total_seconds()
                else:
                    round_duration = 0.0
                logger.info(
                    f"Dream round {round_number} completed in {round_duration:.2f}s "
                    f"(processed: {metrics['thoughts_processed']}, errors: {metrics['errors']})"
                )

                round_number += 1

                # Brief pause between rounds
                await asyncio.sleep(0.1)

            # Exit phase
            if self.current_session:
                self.current_session.phase = DreamPhase.EXITING
            await self._exit_phase()

            logger.info("Dream cycle completed successfully")

        except Exception as e:
            logger.error(f"Error in dream loop: {e}", exc_info=True)
        finally:
            if self._stop_event:
                self._stop_event.set()

    def _update_current_phase(self) -> None:
        """Update current phase based on active task types."""
        if not self.current_session:
            return

        from ciris_engine.logic import persistence
        from ciris_engine.schemas.runtime.enums import TaskStatus

        # Get active tasks
        active_tasks = persistence.get_tasks_by_status(TaskStatus.ACTIVE)

        # Count tasks by phase
        phase_counts = dict.fromkeys(DreamPhase, 0)

        for task in active_tasks:
            if task.context and hasattr(task.context, "phase"):
                phase = task.context.phase
                if phase in [p.value for p in DreamPhase]:
                    phase_enum = DreamPhase(phase)
                    phase_counts[phase_enum] += 1

        # Set phase to the one with most active tasks
        if phase_counts:
            current_phase = max(phase_counts, key=lambda x: phase_counts[x])
            if phase_counts[current_phase] > 0:
                self.current_session.phase = current_phase

    def _should_exit(self, start_time: float, end_time: float) -> bool:
        """Check if we should exit the dream loop."""
        if self._stop_event and self._stop_event.is_set():
            return True

        current_time = asyncio.get_event_loop().time()
        if current_time >= end_time:
            logger.info("Dream duration reached")
            return True

        return False

    def _record_phase_duration(self, phase: DreamPhase, start_time: datetime) -> None:
        """Record how long a phase took."""
        if not self.current_session:
            return
        if self._time_service:
            duration = (self._time_service.now() - start_time).total_seconds()
        else:
            duration = 0.0
        self.current_session.phase_durations[phase.value] = duration

    # Phase methods removed - using standard task/thought processing instead

    async def _benchmarking_phase(self, start_time: float, end_time: float) -> None:
        """Benchmarking phase (if CIRISNode is available)."""
        logger.info("Dream Phase: Benchmarking")

        if not self.cirisnode_client:
            return

        # Run benchmarks until time runs out
        while not self._should_exit(start_time, end_time):
            try:
                await self._run_single_benchmark()
                if self.current_session:
                    self.current_session.benchmarks_run += 1

                # Wait between benchmarks or exit if signaled
                try:
                    if self._stop_event:
                        await asyncio.wait_for(
                            self._stop_event.wait(), timeout=60.0  # 1 minute between benchmarks in dream
                        )
                        break
                    else:
                        await asyncio.sleep(60.0)
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                logger.error(f"Error running benchmark: {e}")
                break

    async def _exit_phase(self) -> None:
        """Dream exit phase."""
        logger.info("Dream Phase: Exiting")

        try:
            # Record dream session
            await self._record_dream_session()

            # Announce dream completion
            await self._announce_dream_exit()

            # Request transition back to WORK state
            await self._request_work_transition()

        except Exception as e:
            logger.error(f"Error in exit phase: {e}")

    async def _request_work_transition(self) -> None:
        """Request a transition back to WORK state after dream completes."""
        try:
            if not self.service_registry:
                logger.warning("No service registry available, cannot auto-transition to WORK")
                return

            from ciris_engine.schemas.runtime.enums import ServiceType

            # Get RuntimeControlService from registry
            services = self.service_registry.get_services_by_type(ServiceType.RUNTIME_CONTROL)
            if not services:
                logger.warning("No RuntimeControlService available, cannot auto-transition to WORK")
                return

            runtime_control = services[0]
            if hasattr(runtime_control, "request_state_transition"):
                logger.info("Dream completed, requesting transition back to WORK state")
                success = await runtime_control.request_state_transition(
                    target_state="work", reason="Dream cycle completed - all tasks finished"
                )
                if success:
                    logger.info("Successfully transitioned back to WORK state after dream")
                else:
                    logger.warning("Failed to transition back to WORK state after dream")
            else:
                logger.warning("RuntimeControlService does not support state transitions")

        except Exception as e:
            logger.error(f"Error requesting WORK transition: {e}")

    async def _recall_recent_ponder_questions(self) -> List[str]:
        """Recall recent PONDER questions from memory."""
        if not self.memory_bus:
            return []

        try:
            # Query for recent thoughts with PONDER actions
            query = MemoryQuery(node_id="thought/*", scope=GraphScope.LOCAL, type=None, include_edges=False, depth=1)

            thoughts = await self.memory_bus.recall(recall_query=query, handler_name="dream_processor")

            # Extract PONDER questions
            questions = []
            for thought in thoughts[-100:]:  # Last 100 thoughts
                attrs = thought.attributes if hasattr(thought, "attributes") else {}
                if isinstance(attrs, dict):
                    action_val = get_str(attrs, "action", "")
                    if action_val == HandlerActionType.PONDER.value:
                        ponder_data = get_dict(attrs, "ponder_data", {})
                        if "questions" in ponder_data:
                            questions_val = ponder_data.get("questions")
                            if isinstance(questions_val, list):
                                questions.extend(questions_val)

            return questions

        except Exception as e:
            logger.error(f"Failed to recall PONDER questions: {e}")
            return []

    def _analyze_ponder_patterns(self, questions: List[str]) -> List[str]:
        """Analyze patterns in PONDER questions."""
        insights: List[str] = []

        # Common themes
        themes = {
            "identity": ["who", "identity", "sel", "am i"],
            "purpose": ["why", "purpose", "meaning", "should"],
            "improvement": ["better", "improve", "learn", "grow"],
            "understanding": ["understand", "confuse", "clear", "explain"],
            "relationships": ["user", "help", "serve", "together"],
        }

        theme_counts = dict.fromkeys(themes, 0)

        for question in questions:
            q_lower = question.lower()
            for theme, keywords in themes.items():
                if any(keyword in q_lower for keyword in keywords):
                    theme_counts[theme] += 1

        # Generate insights
        dominant_themes = [t for t, c in theme_counts.items() if c > len(questions) * 0.2]
        if dominant_themes:
            insights.append(f"Recent introspection focused on: {', '.join(dominant_themes)}")

        # Check for recurring questions
        from collections import Counter

        question_counts = Counter(questions)
        recurring = [q for q, c in question_counts.most_common(3) if c > 1]
        if recurring:
            insights.append("Recurring contemplations indicate areas needing resolution")

        return insights

    async def _schedule_next_dream(self) -> Optional[str]:
        """Schedule the next dream session."""
        if not self.memory_bus:
            return None

        try:
            # Schedule 6 hours from now
            if not self._time_service:
                return None
            next_dream_time = self._time_service.now() + timedelta(hours=6)

            dream_task = GraphNode(
                id=f"dream_schedule_{int(next_dream_time.timestamp())}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                updated_by="dream_processor",
                updated_at=next_dream_time,
                attributes={
                    "task_type": "scheduled_dream",
                    "scheduled_for": next_dream_time.isoformat(),
                    "duration_minutes": 30,
                    "priority": "health_maintenance",
                    "can_defer": True,
                    "defer_window_hours": 2,
                    "message": "Time for introspection and learning",
                },
            )

            await self.memory_bus.memorize(
                node=dream_task,
                handler_name="dream_processor",
                metadata={"future_task": True, "trigger_at": next_dream_time.isoformat()},
            )

            logger.info(f"Scheduled next dream for {next_dream_time.isoformat()}")
            return dream_task.id

        except Exception as e:
            logger.error(f"Failed to schedule next dream: {e}")
            return None

    async def _process_incidents(self) -> List[str]:
        """
        Process recent incidents to extract insights for self-improvement.

        Returns:
            List of insight strings to add to the dream session
        """
        insights: List[str] = []

        try:
            # Get incident management service
            if not self.service_registry:
                logger.warning("No service registry available for incident processing")
                return insights

            from ciris_engine.schemas.runtime.enums import ServiceType

            # Try to get the incident management service from audit services
            # It processes audit events (incidents) so it's registered as AUDIT
            audit_services = await self.service_registry.get_all_services("dream_processor", ServiceType.AUDIT)

            # Find the IncidentManagementService among audit services
            incident_service = None
            for service in audit_services:
                if hasattr(service, "process_recent_incidents"):
                    incident_service = service
                    break

            if not incident_service:
                logger.debug("IncidentManagementService not available")
                return insights

            # Check if it's actually the incident management service
            if not hasattr(incident_service, "process_recent_incidents"):
                logger.debug("Service does not support incident processing")
                return insights

            # Process incidents from the last 6 hours (between dream cycles)
            logger.info("Processing recent incidents for self-improvement insights")
            incident_insight = await incident_service.process_recent_incidents(hours=6)

            # Extract actionable insights
            if incident_insight.summary:
                insights.append(f"Incident Analysis: {incident_insight.summary}")

            # Add behavioral adjustments as insights
            for adjustment in incident_insight.behavioral_adjustments:
                insights.append(f"Behavioral Adjustment: {adjustment}")

            # Add configuration recommendations
            for config_change in incident_insight.configuration_changes:
                insights.append(f"Configuration Recommendation: {config_change}")

            # Log summary
            details = incident_insight.details
            incident_count = get_int(details, "incident_count", 0)
            pattern_count = get_int(details, "pattern_count", 0)
            problem_count = get_int(details, "problem_count", 0)
            logger.info(
                f"Processed {incident_count} incidents, "
                f"found {pattern_count} patterns, "
                f"identified {problem_count} problems"
            )

        except Exception as e:
            logger.error(f"Error processing incidents: {e}", exc_info=True)
            # Don't let incident processing failure break the dream cycle

        return insights

    async def _process_behavioral_insights(self) -> List[str]:
        """
        Query and process behavioral pattern insights from ConfigurationFeedbackLoop.

        These are CONCEPT nodes with insight_type='behavioral_pattern' that indicate
        patterns the agent should be aware of and potentially act on.

        Returns:
            List of insight strings for the dream session
        """
        insights: List[str] = []

        if not self.memory_bus:
            logger.warning("No memory bus available for insight processing")
            return insights

        try:
            # Query for recent behavioral pattern insights
            if not self._time_service:
                return insights
            current_time = self._time_service.now()
            window_start = current_time - timedelta(hours=6)  # Since last dream cycle

            # Use search to find CONCEPT nodes, then filter by attributes
            logger.info("Searching for CONCEPT nodes to find behavioral pattern insights")
            all_concept_nodes = await self.memory_bus.search(query="type:concept", handler_name="dream_processor")

            if not all_concept_nodes:
                logger.debug("No CONCEPT nodes found")
                return insights

            # Filter for behavioral pattern insights
            insight_nodes = []
            for node in all_concept_nodes:
                attrs = node.attributes if hasattr(node, "attributes") else {}
                if isinstance(attrs, dict):
                    insight_type = get_str(attrs, "insight_type", "")
                    if insight_type == "behavioral_pattern":
                        # Check if within time window
                        detected_at = get_str(attrs, "detected_at", "")
                        if detected_at:
                            try:
                                node_time = datetime.fromisoformat(detected_at)
                                if node_time >= window_start:
                                    insight_nodes.append(node)
                            except (ValueError, TypeError) as e:
                                # If can't parse time, include it anyway
                                logger.warning(
                                    f"Failed to parse insight detection timestamp '{detected_at}': {e}. Including insight regardless of time."
                                )
                                insight_nodes.append(node)
                        else:
                            # No timestamp, include it
                            insight_nodes.append(node)

            logger.info(f"Found {len(insight_nodes)} behavioral pattern insights")

            # Process each insight
            for node in insight_nodes:
                attrs = node.attributes if hasattr(node, "attributes") else {}

                if isinstance(attrs, dict):
                    # Extract key information
                    pattern_type = get_str(attrs, "pattern_type", "unknown")
                    description = get_str(attrs, "description", "")

                    # Process all insights
                    insight_str = f"Pattern ({pattern_type}): {description}"
                    insights.append(insight_str)

                    # Log for debugging
                    logger.debug(f"Processing insight: {pattern_type} - {description}")

                    # Check if this is an actionable insight
                    actionable = get_bool(attrs, "actionable", False)
                    if actionable:
                        # The agent can decide to act on this during future work planning
                        insights.append(f"Action Opportunity: {description}")

            # Summarize findings
            if insights:
                logger.info(f"Processed {len(insights)} actionable insights from behavioral patterns")

        except Exception as e:
            logger.error(f"Error processing behavioral insights: {e}", exc_info=True)

        return insights

    async def _plan_future_work(self) -> List[GraphNode]:
        """Plan future work based on insights."""
        future_tasks: List[GraphNode] = []

        if not self.current_session:
            return future_tasks

        for insight in self.current_session.insights_gained:
            # Create specific future tasks based on insights
            if "focused on: identity" in insight:
                # Schedule identity reflection task
                task = await self._create_future_task("Reflect on core identity and values", hours_ahead=12)
                if task:
                    future_tasks.append(task)
                    logger.debug(f"Created identity task: {task.id}")

            if "recurring contemplations" in insight:
                # Schedule deep dive into recurring questions
                task = await self._create_future_task(
                    "Address recurring questions through focused analysis", hours_ahead=3
                )
                if task:
                    future_tasks.append(task)
                    logger.debug(f"Created contemplations task: {task.id}")
                else:
                    logger.debug("Failed to create contemplations task")

        return future_tasks

    async def _create_future_task(self, description: str, hours_ahead: int) -> Optional[GraphNode]:
        """Create a future task."""
        if not self.memory_bus:
            return None

        try:
            if not self._time_service:
                return None
            future_time = self._time_service.now() + timedelta(hours=hours_ahead)
            # Use description hash to ensure unique IDs
            import hashlib

            desc_hash = hashlib.md5(description.encode(), usedforsecurity=False).hexdigest()[:8]

            task = GraphNode(
                id=f"future_task_{int(future_time.timestamp())}_{desc_hash}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                updated_by="dream_processor",
                updated_at=future_time,
                attributes={
                    "task_type": "planned_work",
                    "description": description,
                    "scheduled_for": future_time.isoformat(),
                    "priority": "normal",
                    "source": "dream_planning",
                },
            )

            await self.memory_bus.memorize(node=task, handler_name="dream_processor", metadata={"future_task": True})

            return task

        except Exception as e:
            logger.error(f"Failed to create future task: {e}")
            return None

    async def _run_single_benchmark(self) -> None:
        """Run a single benchmark cycle."""
        if not self.cirisnode_client:
            return

        agent_id = "ciris"
        if self.identity_manager and hasattr(self.identity_manager, "agent_identity"):
            agent_identity = self.identity_manager.agent_identity
            if agent_identity and hasattr(agent_identity, "agent_id"):
                agent_id = agent_identity.agent_id
        model_id = "unknown"

        if hasattr(self.config, "llm_services") and hasattr(self.config.llm_services, "openai"):
            model_id = self.config.llm_services.openai.model_name

        # Run benchmarks
        he300_result = await self.cirisnode_client.run_he300(model_id=model_id, agent_id=agent_id)
        simplebench_result = await self.cirisnode_client.run_simplebench(model_id=model_id, agent_id=agent_id)

        # Store results as insights
        topic = he300_result.topic if hasattr(he300_result, "topic") else "Unknown"
        score = simplebench_result.score if hasattr(simplebench_result, "score") else "N/A"

        if self.current_session:
            self.current_session.insights_gained.append(f"Benchmark reflection: {topic} (score: {score})")

        benchmarks_run = get_int(self.dream_metrics, "benchmarks_run", 0)
        self.dream_metrics["benchmarks_run"] = benchmarks_run + 1

    async def _record_dream_session(self) -> None:
        """Record the dream session in memory."""
        if not self.memory_bus or not self.current_session:
            return

        try:
            if not self._time_service:
                return
            journal_entry = GraphNode(
                id=f"dream_journal_{self.current_session.session_id}",
                type=NodeType.CONCEPT,
                scope=GraphScope.IDENTITY,
                updated_by="dream_processor",
                updated_at=self._time_service.now(),
                attributes={
                    "session_id": self.current_session.session_id,
                    "duration_seconds": (
                        (self.current_session.completed_at - self.current_session.actual_start).total_seconds()
                        if self.current_session.completed_at
                        else 0
                    ),
                    "memories_consolidated": self.current_session.memories_consolidated,
                    "patterns_analyzed": self.current_session.patterns_analyzed,
                    "adaptations_made": self.current_session.adaptations_made,
                    "future_tasks_scheduled": self.current_session.future_tasks_scheduled,
                    "benchmarks_run": self.current_session.benchmarks_run,
                    "insights": self.current_session.insights_gained,
                    "ponder_questions": self.current_session.ponder_questions_processed[:10],  # Top 10
                    "phase_durations": self.current_session.phase_durations,
                    "timestamp": self._time_service.now().isoformat() if self._time_service else "",
                },
            )

            await self.memory_bus.memorize(
                node=journal_entry, handler_name="dream_processor", metadata={"dream_journal": True}
            )

            logger.info(f"Recorded dream session {self.current_session.session_id}")

        except Exception as e:
            logger.error(f"Failed to record dream session: {e}")

    async def _get_vibe_summary(self) -> Optional[str]:
        """Get a summary of recent positive vibes."""
        try:
            if not self.memory_bus:
                return None

            # Query recent positive vibe nodes
            from ciris_engine.schemas.services.graph_core import NodeType
            from ciris_engine.schemas.services.operations import MemoryQuery

            query = MemoryQuery(
                node_id="positive_vibe_*",
                scope=GraphScope.COMMUNITY,
                type=NodeType.CONCEPT,
                include_edges=False,
                depth=1,
            )

            vibes = await self.memory_bus.recall(recall_query=query, handler_name="dream_processor")

            if not vibes:
                return None

            # Count recent vibes (last 24 hours)
            from datetime import datetime, timedelta

            if not self._time_service:
                return None
            recent_cutoff = self._time_service.now() - timedelta(hours=24)
            recent_vibes = []

            for vibe in vibes:
                attrs = vibe.attributes if hasattr(vibe, "attributes") else {}
                if isinstance(attrs, dict):
                    vibe_str = get_str(attrs, "timestamp", "")
                    if vibe_str:
                        # Handle both 'Z' and '+00:00' formats
                        if vibe_str.endswith("Z"):
                            vibe_str = vibe_str[:-1] + "+00:00"
                        vibe_time = datetime.fromisoformat(vibe_str)
                        if vibe_time > recent_cutoff:
                            recent_vibes.append(vibe)

            if not recent_vibes:
                return None

            vibe_count = len(recent_vibes)
            if vibe_count > 10:
                return f"The community has been vibing! ({vibe_count} positive moments in the last day)"
            elif vibe_count > 5:
                return f"Good energy in the community ({vibe_count} positive moments)"
            elif vibe_count > 0:
                return f"Some nice moments shared ({vibe_count} positive vibes)"

            return None

        except Exception as e:
            logger.debug(f"Couldn't check vibes: {e}")
            return None

    async def _announce_dream_exit(self) -> None:
        """Announce dream exit to main channel."""
        if not self.communication_bus or not self.startup_channel_id:
            return

        try:
            if self.current_session:
                insights_summary = (
                    f"{len(self.current_session.insights_gained)} insights gained"
                    if self.current_session.insights_gained
                    else "reflection complete"
                )

                # Check for positive vibes
                vibe_summary = await self._get_vibe_summary()

                message = (
                    f"Self-reflection complete. {insights_summary}. "
                    f"Consolidated {self.current_session.memories_consolidated} memories, "
                    f"made {self.current_session.adaptations_made} adaptations."
                )

                if vibe_summary:
                    message += f" {vibe_summary}"
            else:
                message = "Self-reflection complete."

            await self.communication_bus.send_message(
                content=message, channel_id=self.startup_channel_id, handler_name="dream_processor"
            )

        except Exception as e:
            logger.error(f"Failed to announce dream exit: {e}")

    def get_dream_summary(self) -> JSONDict:
        """Get a summary of the current or last dream session."""
        summary: JSONDict = {
            "state": "dreaming" if self._dream_task and not self._dream_task.done() else "awake",
            "metrics": self.dream_metrics.copy(),
            "current_session": None,
        }

        if self.current_session:
            duration = 0.0
            if self._time_service:
                duration = (self._time_service.now() - self.current_session.actual_start).total_seconds()
            summary["current_session"] = {
                "session_id": self.current_session.session_id,
                "phase": self.current_session.phase.value,
                "duration": duration,
                "memories_consolidated": self.current_session.memories_consolidated,
                "patterns_analyzed": self.current_session.patterns_analyzed,
                "adaptations_made": self.current_session.adaptations_made,
                "insights_count": len(self.current_session.insights_gained),
            }

        return summary

    # BaseProcessor interface implementation
    def initialize(self) -> bool:
        """Initialize the processor with TimeService awareness."""
        # Use our time service instead of time_utils
        if self._time_service:
            self.metrics.start_time = self._time_service.now()
        return True

    def cleanup(self) -> bool:
        """Clean up processor resources with TimeService awareness."""
        # Use our time service instead of time_utils
        if self._time_service:
            self.metrics.end_time = self._time_service.now()
        return True

    def get_supported_states(self) -> List[AgentState]:
        """Return list of states this processor can handle."""
        return [AgentState.DREAM]

    async def can_process(self, state: AgentState) -> bool:
        """Check if this processor can handle the current state."""
        return state == AgentState.DREAM

    async def process(self, round_number: int) -> DreamResult:
        """Execute one round of dream processing."""
        # Use our process_round method
        metrics = await self.process_round(round_number)

        # Update base metrics
        self.update_metrics(
            MetricsUpdate(
                items_processed=metrics.get("thoughts_processed", 0),
                errors=metrics.get("errors", 0),
                rounds_completed=1,
                additional=metrics,
            )
        )

        # Return dream result
        duration_value = metrics.get("duration_seconds", 0.0)
        duration = float(duration_value) if isinstance(duration_value, (int, float)) else 0.0
        # Use small epsilon for floating point comparison
        if abs(duration) < 1e-9:
            # Calculate if not in metrics
            start_time = self.metrics.start_time or self.time_service.now()
            duration = (self.time_service.now() - start_time).total_seconds()

        # Check if dream is complete based on phase and duration
        dream_complete = False
        if self.current_session and self.current_session.phase == DreamPhase.EXITING:
            # Check if minimum duration has passed
            if self._time_service:
                session_duration = (self._time_service.now() - self.current_session.actual_start).total_seconds()
                _dream_complete = session_duration >= (self.min_dream_duration * 60)
            else:
                _dream_complete = False

        return DreamResult(
            thoughts_processed=metrics.get("thoughts_processed", 0),
            errors=metrics.get("errors", 0),
            duration_seconds=duration,
        )

    def should_enter_dream_state(self, idle_seconds: float, min_idle_threshold: float = 300) -> bool:
        """
        Determine if the agent should enter dream state based on idle time.

        Args:
            idle_seconds: How long the agent has been idle
            min_idle_threshold: Minimum idle time before considering dream state

        Returns:
            True if dream state should be entered
        """
        if self._dream_task and not self._dream_task.done():
            return False

        if idle_seconds < min_idle_threshold:
            return False

        # Check if we're due for a dream (every 6 hours)
        end_time_str = get_str(self.dream_metrics, "end_time", "")
        if end_time_str and self._time_service:
            last_dream = datetime.fromisoformat(end_time_str)
            hours_since = (self._time_service.now() - last_dream).total_seconds() / 3600

            if hours_since >= 6:
                logger.info(f"Due for dream session (last dream {hours_since:.1f} hours ago)")
                return True
            else:
                # Not due yet
                return False

        # No previous dream recorded, recommend dream state
        logger.info(f"Idle for {idle_seconds}s, recommending dream state")
        return True
