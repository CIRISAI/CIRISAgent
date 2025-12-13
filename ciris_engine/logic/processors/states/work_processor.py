"""
Work processor handling normal task and thought processing.
Enhanced with proper context building and service passing.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.logic.utils.jsondict_helpers import get_int
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
    from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher

from ciris_engine.logic import persistence
from ciris_engine.logic.processors.core.base_processor import BaseProcessor
from ciris_engine.logic.processors.support.task_manager import TaskManager
from ciris_engine.logic.processors.support.thought_manager import ThoughtManager

# ServiceProtocol import removed - processors aren't services
from ciris_engine.logic.utils.context_utils import build_dispatch_context
from ciris_engine.schemas.processors.results import WorkResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task

logger = logging.getLogger(__name__)


class WorkProcessor(BaseProcessor):
    """Handles the WORK state for normal task/thought processing."""

    def __init__(
        self,
        config_accessor: Any,  # ConfigAccessor
        thought_processor: "ThoughtProcessor",
        action_dispatcher: "ActionDispatcher",
        services: Any,  # JSONDict - using Any to avoid circular import issues
        startup_channel_id: Optional[str] = None,
        agent_occurrence_id: str = "default",
        **kwargs: Any,
    ) -> None:
        """Initialize work processor."""
        self.startup_channel_id = startup_channel_id
        self.agent_occurrence_id = agent_occurrence_id
        super().__init__(config_accessor, thought_processor, action_dispatcher, services, **kwargs)

        workflow_config = getattr(self.config, "workflow", None)
        if workflow_config:
            max_active_tasks = getattr(workflow_config, "max_active_tasks", 10)
            max_active_thoughts = getattr(workflow_config, "max_active_thoughts", 50)
        else:
            max_active_tasks = 10
            max_active_thoughts = 50

        # Direct attribute access for type safety
        time_service = services.time_service
        if not time_service:
            raise ValueError("time_service is required in services")

        from typing import cast

        from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

        self.time_service = cast(TimeServiceProtocol, time_service)
        self.task_manager = TaskManager(
            max_active_tasks=max_active_tasks,
            time_service=self.time_service,
            agent_occurrence_id=self.agent_occurrence_id,
        )
        self.thought_manager = ThoughtManager(
            time_service=self.time_service,
            max_active_thoughts=max_active_thoughts,
            default_channel_id=self.startup_channel_id,
            agent_occurrence_id=self.agent_occurrence_id,
        )
        self.last_activity_time = self.time_service.now()
        self.idle_rounds = 0

    def get_supported_states(self) -> List[AgentState]:
        """Work processor handles WORK and PLAY states."""
        return [AgentState.WORK, AgentState.PLAY]

    async def can_process(self, state: AgentState) -> bool:
        """Check if we can process the given state."""
        return state in self.get_supported_states()

    async def process(self, round_number: int) -> WorkResult:
        """Execute one round of work processing."""
        logger.debug(f"WorkProcessor.process called for round {round_number}")
        start_time = self.time_service.now()

        round_metrics: JSONDict = {
            "round_number": round_number,
            "tasks_activated": 0,
            "thoughts_generated": 0,
            "thoughts_processed": 0,
            "errors": 0,
            "was_idle": False,
        }

        try:
            # Phase 0: Ticket discovery (create tasks for incomplete tickets)
            logger.debug("Phase 0: Discovering incomplete tickets...")
            tickets_discovered = await self._discover_incomplete_tickets()
            logger.debug(f"Discovered {tickets_discovered} incomplete tickets")

            # Phase 1: Task activation
            logger.debug("Phase 1: Activating pending tasks...")
            activated = self.task_manager.activate_pending_tasks()
            logger.debug(f"Activated {activated} tasks")
            round_metrics["tasks_activated"] = activated

            # Phase 2: Seed thought generation
            logger.debug("Phase 2: Generating seed thoughts...")
            tasks_needing_seed = self.task_manager.get_tasks_needing_seed()
            logger.debug(f"Found {len(tasks_needing_seed)} tasks needing seed thoughts")
            generated = self.thought_manager.generate_seed_thoughts(tasks_needing_seed, round_number)
            logger.debug(f"Generated {generated} seed thoughts")
            round_metrics["thoughts_generated"] = generated

            # Phase 2.5: Recovery thought generation for tasks with updated info but no active thoughts
            logger.debug("Phase 2.5: Generating recovery thoughts...")
            tasks_needing_recovery = self.task_manager.get_tasks_needing_recovery()
            if tasks_needing_recovery:
                logger.info(f"[RECOVERY] Found {len(tasks_needing_recovery)} tasks needing recovery thoughts")
                recovery_generated = self.thought_manager.generate_recovery_thoughts(
                    tasks_needing_recovery, round_number
                )
                logger.debug(f"Generated {recovery_generated} recovery thoughts")
                # Add recovery thoughts to total (generated was set on line 121)
                round_metrics["thoughts_generated"] = generated + recovery_generated

            # Phase 3: Populate processing queue
            logger.debug("Phase 3: Populating processing queue...")
            queue_size = self.thought_manager.populate_queue(round_number)
            logger.debug(f"Queue size after population: {queue_size}")

            if queue_size > 0:
                # Phase 4: Process thought batch
                logger.debug("Phase 4: Processing thought batch...")
                batch = self.thought_manager.get_queue_batch()
                logger.debug(f"Got batch of {len(batch)} thoughts to process")
                processed = await self._process_batch(batch, round_number)
                logger.debug(f"Processed {processed} thoughts")
                round_metrics["thoughts_processed"] = processed

                # Update activity tracking
                self.last_activity_time = start_time
                self.idle_rounds = 0
                round_metrics["was_idle"] = False
            else:
                # Handle idle state - DISABLED
                round_metrics["was_idle"] = True
                # Idle mode disabled - no automatic transitions
                # self.idle_rounds += 1
                # await self._handle_idle_state(round_number)

            # Update metrics
            self.metrics.rounds_completed += 1

        except Exception as e:
            logger.error(f"Error in work round {round_number}: {e}", exc_info=True)
            errors = get_int(round_metrics, "errors", 0)
            round_metrics["errors"] = errors + 1
            self.metrics.errors += 1

        # Calculate round duration
        end_time = self.time_service.now()
        duration = (end_time - start_time).total_seconds()
        round_metrics["duration_seconds"] = duration

        # Only log at INFO level if work was actually done
        thoughts_processed = get_int(round_metrics, "thoughts_processed", 0)
        tasks_activated = get_int(round_metrics, "tasks_activated", 0)
        if thoughts_processed > 0 or tasks_activated > 0:
            logger.info(
                f"Work round {round_number}: completed "
                f"({round_metrics['thoughts_processed']} thoughts, {duration:.2f}s)"
            )
        else:
            logger.debug(f"Work round {round_number}: idle (no pending work)")

        return WorkResult(
            tasks_processed=round_metrics.get("tasks_activated", 0),
            thoughts_processed=round_metrics.get("thoughts_processed", 0),
            errors=round_metrics.get("errors", 0),
            duration_seconds=duration,
        )

    async def _process_batch(self, batch: List[Any], round_number: int) -> int:
        """Process a batch of thoughts."""
        if not batch:
            return 0

        logger.debug(f"Processing batch of {len(batch)} thoughts")

        batch = self.thought_manager.mark_thoughts_processing(batch, round_number)
        if not batch:
            logger.warning("No thoughts could be marked as PROCESSING")
            return 0

        processed_count = 0

        for item in batch:
            try:
                result = await self._process_single_thought(item)
                processed_count += 1

                if result is None:
                    logger.debug(f"Thought {item.thought_id} was re-queued")
                else:
                    await self._dispatch_thought_result(item, result)

            except Exception as e:
                logger.error(f"Error processing thought {item.thought_id}: {e}", exc_info=True)
                self._mark_thought_failed(item.thought_id, str(e))

        return processed_count

    async def _process_single_thought(self, item: Any) -> Any:
        """Process a single thought item."""
        return await self.process_thought_item(item)

    async def _dispatch_thought_result(self, item: Any, result: Any) -> None:
        """Dispatch the result of thought processing."""
        thought_id = item.thought_id

        # Extract action from ConscienceApplicationResult if needed
        action_result = result.final_action if hasattr(result, "final_action") else result
        selected_action = action_result.selected_action if hasattr(action_result, "selected_action") else "unknown"

        logger.debug(f"Dispatching action {selected_action} for thought {thought_id}")

        thought_obj = await persistence.async_get_thought_by_id(thought_id, self.agent_occurrence_id)
        if not thought_obj:
            logger.error(f"Could not retrieve thought {thought_id} for dispatch")
            return

        task = persistence.get_task_by_id(item.source_task_id, self.agent_occurrence_id)
        dispatch_context = build_dispatch_context(
            thought=thought_obj,
            time_service=self.time_service,
            task=task,
            app_config=self.config,
            round_number=getattr(item, "round_number", 0),
            extra_context=getattr(item, "initial_context", {}),
            action_type=selected_action if result else None,
        )

        try:
            await self.dispatch_action(result, thought_obj, dispatch_context.model_dump())
        except Exception as e:
            logger.error(f"Error dispatching action for thought {thought_id}: {e}")
            self._mark_thought_failed(thought_id, f"Dispatch failed: {str(e)}")

    def _handle_idle_state(self, round_number: int) -> None:
        """Handle idle state when no thoughts are pending."""
        logger.info(f"Round {round_number}: No thoughts to process (idle rounds: {self.idle_rounds})")

        # Create job thought if needed
        created_job = self.thought_manager.handle_idle_state(round_number)

        if created_job:
            logger.info("Created job thought for idle monitoring")
        else:
            logger.debug("No job thought needed")

    def _mark_thought_failed(self, thought_id: str, error: str) -> None:
        """Mark a thought as failed."""
        persistence.update_thought_status(
            thought_id=thought_id, status=ThoughtStatus.FAILED, final_action={"error": error}
        )

    def _should_skip_ticket_by_status(self, ticket_status: str) -> bool:
        """Check if ticket should be skipped based on status."""
        return ticket_status in ["blocked", "deferred", "completed", "failed", "cancelled"]

    def _attempt_claim_pending_ticket(self, ticket: Dict[str, Any], db_path: Optional[str]) -> bool:
        """Attempt to atomically claim a pending ticket.

        Args:
            ticket: Ticket dictionary
            db_path: Database path

        Returns:
            True if claim succeeded, False otherwise
        """
        from ciris_engine.logic.persistence.models.tickets import update_ticket_status

        ticket_id = ticket.get("ticket_id")
        if not ticket_id:
            return False

        # Only claim tickets with agent_occurrence_id="__shared__"
        if ticket.get("agent_occurrence_id") != "__shared__":
            logger.debug(f"Ticket {ticket_id} not shared, skipping claim attempt")
            return False

        # Skip tickets with certain statuses
        if self._should_skip_ticket_by_status(ticket.get("status", "")):
            logger.debug(f"Ticket {ticket_id} has status {ticket.get('status')}, skipping")
            return False

        # Atomic claiming: only update if ticket is still __shared__
        success = update_ticket_status(
            ticket_id,
            "assigned",
            notes=f"Claimed by occurrence {self.agent_occurrence_id}",
            agent_occurrence_id=self.agent_occurrence_id,
            require_current_occurrence_id="__shared__",
            db_path=db_path,
        )

        if not success:
            logger.debug(f"Failed to claim ticket {ticket_id} (already claimed by another occurrence)")
            return False

        return True

    def _create_seed_task_for_ticket(self, ticket: Dict[str, Any], db_path: Optional[str]) -> bool:
        """Create seed task for newly claimed ticket.

        Args:
            ticket: Ticket dictionary
            db_path: Database path

        Returns:
            True if task creation succeeded, False otherwise
        """
        import json

        from ciris_engine.logic.persistence.db.core import get_db_connection

        ticket_id = ticket.get("ticket_id")
        if not ticket_id:
            return False

        task_id = f"TICKET-{ticket_id}-{self.time_service.now().strftime('%Y%m%d%H%M%S')}"
        ticket_metadata = ticket.get("metadata", {})
        ticket_sop = ticket.get("sop", "UNKNOWN")
        current_stage = ticket_metadata.get("current_stage", "starting")

        task_context = {
            "ticket_id": ticket_id,
            "ticket_sop": ticket_sop,
            "ticket_type": ticket.get("ticket_type"),
            "ticket_status": "assigned",
            "ticket_metadata": ticket_metadata,
            "ticket_priority": ticket.get("priority", 5),
            "ticket_email": ticket.get("email"),
            "ticket_user_identifier": ticket.get("user_identifier"),
            "is_ticket_task": True,
        }

        # Create Task object
        now = self.time_service.now().isoformat()
        task = Task(
            task_id=task_id,
            channel_id=self.startup_channel_id or "ticket_processing",
            agent_occurrence_id=self.agent_occurrence_id,
            description=f"Process ticket {ticket_id} (SOP: {ticket_sop}, Stage: {current_stage})",
            status=TaskStatus.PENDING,
            priority=ticket.get("priority", 5),
            created_at=now,
            updated_at=now,
            context=None,
        )

        task_dict = task.model_dump(mode="json")
        task_dict["context"] = task_context

        sql = """
            INSERT INTO tasks (task_id, channel_id, agent_occurrence_id, description, status, priority,
                              created_at, updated_at, parent_task_id, context_json, outcome_json,
                              signed_by, signature, signed_at, updated_info_available, updated_info_content)
            VALUES (:task_id, :channel_id, :agent_occurrence_id, :description, :status, :priority,
                    :created_at, :updated_at, :parent_task_id, :context, :outcome,
                    :signed_by, :signature, :signed_at, :updated_info_available, :updated_info_content)
        """
        params = {
            **task_dict,
            "status": task.status.value,
            "context": json.dumps(task_context),
            "outcome": None,
            "signed_by": None,
            "signature": None,
            "signed_at": None,
            "parent_task_id": None,
            "updated_info_available": 0,
            "updated_info_content": None,
        }

        try:
            with get_db_connection(db_path=db_path) as conn:
                conn.execute(sql, params)
                conn.commit()
            logger.info(f"Claimed ticket {ticket_id} and created seed task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to create task {task_id}: {e}")
            return False

    def _should_process_ticket_for_continuation(self, ticket: Dict[str, Any]) -> bool:
        """Check if ticket should be processed for continuation task creation.

        Args:
            ticket: Ticket dictionary

        Returns:
            True if ticket should be processed, False otherwise
        """
        ticket_id = ticket.get("ticket_id")
        if not ticket_id:
            return False

        # Only process tickets assigned to this occurrence
        if ticket.get("agent_occurrence_id") != self.agent_occurrence_id:
            logger.debug(f"Ticket {ticket_id} assigned to different occurrence, skipping")
            return False

        # Skip if ticket has become BLOCKED or DEFERRED
        if self._should_skip_ticket_by_status(ticket.get("status", "")):
            logger.debug(f"Ticket {ticket_id} is {ticket.get('status')}, skipping task creation")
            return False

        return True

    def _has_existing_task_for_ticket(self, ticket_id: str, db_path: Optional[str]) -> bool:
        """Check if there's already a pending or active task for this ticket.

        Args:
            ticket_id: Ticket ID
            db_path: Database path

        Returns:
            True if task exists, False otherwise
        """
        from ciris_engine.logic.persistence.db import get_db_connection

        sql = (
            "SELECT COUNT(*) as count FROM tasks WHERE task_id LIKE ? AND agent_occurrence_id = ? AND status IN (?, ?)"
        )
        task_prefix = f"TICKET-{ticket_id}-%"

        try:
            with get_db_connection(db_path=db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    sql,
                    (task_prefix, self.agent_occurrence_id, TaskStatus.PENDING.value, TaskStatus.ACTIVE.value),
                )
                row = cursor.fetchone()
                # PostgreSQL returns RealDictRow (dict), SQLite returns tuple
                count = row["count"] if isinstance(row, dict) else row[0]
                has_task = bool(count > 0)

                if has_task:
                    logger.debug(f"Ticket {ticket_id} already has pending/active task, skipping")

                return has_task
        except Exception as e:
            logger.warning(f"Failed to check for existing tasks for ticket {ticket_id}: {e}")
            return False

    def _is_ticket_deferred(self, ticket_metadata: Dict[str, Any], ticket_id: str) -> bool:
        """Check if ticket is deferred.

        Args:
            ticket_metadata: Ticket metadata dictionary
            ticket_id: Ticket ID for logging

        Returns:
            True if ticket is deferred, False otherwise
        """
        from datetime import datetime, timezone

        # Check for deferral until specific time
        deferred_until_str = ticket_metadata.get("deferred_until")
        if deferred_until_str:
            try:
                # Ensure we have a string before calling fromisoformat
                if isinstance(deferred_until_str, str):
                    deferred_until = datetime.fromisoformat(deferred_until_str)
                    if deferred_until > datetime.now(timezone.utc):
                        logger.debug(f"Ticket {ticket_id} deferred until {deferred_until_str}, skipping")
                        return True
                else:
                    logger.warning(f"Invalid deferred_until type for ticket {ticket_id}: {type(deferred_until_str)}")
            except (ValueError, TypeError):
                logger.warning(f"Invalid deferred_until format for ticket {ticket_id}: {deferred_until_str}")

        # Check for awaiting human response
        if ticket_metadata.get("awaiting_human_response"):
            logger.debug(f"Ticket {ticket_id} awaiting human response, skipping")
            return True

        return False

    def _create_continuation_task_for_ticket(self, ticket: Dict[str, Any], db_path: Optional[str]) -> bool:
        """Create continuation task for active ticket.

        Args:
            ticket: Ticket dictionary
            db_path: Database path

        Returns:
            True if task creation succeeded, False otherwise
        """
        import json

        from ciris_engine.logic.persistence.db import get_db_connection

        ticket_id = ticket.get("ticket_id")
        if not ticket_id:
            return False

        ticket_metadata = ticket.get("metadata", {})
        ticket_sop = ticket.get("sop", "UNKNOWN")
        current_stage = ticket_metadata.get("current_stage", "unknown")
        ticket_status = ticket.get("status", "")

        continuation_task_id = f"TICKET-{ticket_id}-{self.time_service.now().strftime('%Y%m%d%H%M%S')}"
        ticket_channel_id = self.startup_channel_id or "ticket_processing"

        task_context = {
            "channel_id": ticket_channel_id,
            "ticket_id": ticket_id,
            "ticket_sop": ticket_sop,
            "ticket_type": ticket.get("ticket_type"),
            "ticket_status": ticket_status,
            "ticket_metadata": ticket_metadata,
            "ticket_priority": ticket.get("priority", 5),
            "ticket_email": ticket.get("email"),
            "ticket_user_identifier": ticket.get("user_identifier"),
            "is_ticket_task": True,
        }

        now = self.time_service.now().isoformat()
        task = Task(
            task_id=continuation_task_id,
            channel_id=ticket_channel_id,
            agent_occurrence_id=self.agent_occurrence_id,
            description=f"Continue ticket {ticket_id} (SOP: {ticket_sop}, Stage: {current_stage})",
            status=TaskStatus.PENDING,
            priority=ticket.get("priority", 5),
            created_at=now,
            updated_at=now,
            context=None,
        )

        task_dict = task.model_dump(mode="json")

        sql = """
            INSERT INTO tasks (task_id, channel_id, agent_occurrence_id, description, status, priority,
                              created_at, updated_at, parent_task_id, context_json, outcome_json,
                              signed_by, signature, signed_at, updated_info_available, updated_info_content)
            VALUES (:task_id, :channel_id, :agent_occurrence_id, :description, :status, :priority,
                    :created_at, :updated_at, :parent_task_id, :context, :outcome,
                    :signed_by, :signature, :signed_at, :updated_info_available, :updated_info_content)
        """
        params = {
            **task_dict,
            "status": task.status.value,
            "context": json.dumps(task_context),
            "outcome": json.dumps(task_dict.get("outcome")) if task_dict.get("outcome") is not None else None,
            "updated_info_available": 1 if task_dict.get("updated_info_available") else 0,
        }

        try:
            with get_db_connection(db_path=db_path) as conn:
                conn.execute(sql, params)
                conn.commit()
            logger.info(f"Created continuation task {continuation_task_id} for ticket {ticket_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to create continuation task {continuation_task_id}: {e}")
            return False

    async def _discover_incomplete_tickets(self) -> int:
        """Discover incomplete tickets and create tasks for them.

        Two-phase discovery for multi-occurrence coordination:
        1. Phase 1: Atomically claim PENDING tickets with agent_occurrence_id="__shared__"
        2. Phase 2: Create continuation tasks for ASSIGNED/IN_PROGRESS tickets

        Returns:
            Number of tasks created for tickets
        """
        from ciris_engine.logic.persistence.models.tickets import list_tickets

        tasks_created = 0
        db_path = getattr(self.config, "db_path", None)

        try:
            # Phase 1: Claim PENDING tickets with __shared__
            tasks_created += await self._process_pending_tickets(db_path)

            # Phase 2: Create continuation tasks for ASSIGNED/IN_PROGRESS tickets
            tasks_created += await self._process_active_tickets(db_path)

            if tasks_created > 0:
                logger.info(f"Ticket discovery: created {tasks_created} tasks (claimed + continued)")

        except Exception as e:
            logger.error(f"Error discovering incomplete tickets: {e}", exc_info=True)

        return tasks_created

    async def _process_pending_tickets(self, db_path: Optional[str]) -> int:
        """Process PENDING tickets and claim them atomically.

        Args:
            db_path: Database path

        Returns:
            Number of tasks created
        """
        from ciris_engine.logic.persistence.models.tickets import list_tickets

        tasks_created = 0
        pending_tickets = list_tickets(status="pending", db_path=db_path)

        for ticket in pending_tickets:
            # Attempt to claim the ticket
            if not self._attempt_claim_pending_ticket(ticket, db_path):
                continue

            # Create seed task for newly claimed ticket
            if self._create_seed_task_for_ticket(ticket, db_path):
                tasks_created += 1
            else:
                ticket_id = ticket.get("ticket_id", "unknown")
                logger.warning(f"Claimed ticket {ticket_id} but failed to create task")

        return tasks_created

    async def _process_active_tickets(self, db_path: Optional[str]) -> int:
        """Process ASSIGNED/IN_PROGRESS tickets and create continuation tasks.

        Args:
            db_path: Database path

        Returns:
            Number of tasks created
        """
        from ciris_engine.logic.persistence.models.tickets import list_tickets

        tasks_created = 0
        assigned_tickets = list_tickets(status="assigned", db_path=db_path)
        in_progress_tickets = list_tickets(status="in_progress", db_path=db_path)
        active_tickets = assigned_tickets + in_progress_tickets

        for ticket in active_tickets:
            ticket_id = ticket.get("ticket_id")
            if not ticket_id:
                continue

            # Check if ticket should be processed
            if not self._should_process_ticket_for_continuation(ticket):
                continue

            # Check for existing tasks
            if self._has_existing_task_for_ticket(ticket_id, db_path):
                continue

            # Check for deferral
            ticket_metadata = ticket.get("metadata", {})
            if self._is_ticket_deferred(ticket_metadata, ticket_id):
                continue

            # Create continuation task
            if self._create_continuation_task_for_ticket(ticket, db_path):
                tasks_created += 1
            else:
                logger.warning(f"Failed to create continuation task for ticket {ticket_id}")

        return tasks_created

    def get_idle_duration(self) -> float:
        """Get duration in seconds since last activity."""
        return (self.time_service.now() - self.last_activity_time).total_seconds()

    def should_transition_to_dream(self) -> bool:
        """
        Check if we should recommend transitioning to DREAM state.

        DISABLED: Idle mode transitions are disabled.

        Returns:
            Always returns False (idle mode disabled)
        """
        # Idle mode disabled - no automatic transitions
        return False

    # ServiceProtocol implementation
    async def start_processing(self, num_rounds: Optional[int] = None) -> None:
        """Start the work processing loop."""
        import asyncio

        round_num = 0
        self._running = True

        while self._running and (num_rounds is None or round_num < num_rounds):
            await self.process(round_num)
            round_num += 1

            if self.should_transition_to_dream():
                logger.info("Work processor recommends transitioning to DREAM state due to inactivity")
                break

            await asyncio.sleep(1)  # Brief pause between rounds

    def stop_processing(self) -> None:
        """Stop work processing and clean up resources."""
        self._running = False
        logger.info("Work processor stopped")

    def get_status(self) -> JSONDict:
        """Get current work processor status and metrics."""
        work_stats = {
            "last_activity": self.last_activity_time.isoformat(),
            "idle_duration_seconds": self.get_idle_duration(),
            "idle_rounds": self.idle_rounds,
            "active_tasks": self.task_manager.get_active_task_count(),
            "pending_tasks": self.task_manager.get_pending_task_count(),
            "pending_thoughts": self.thought_manager.get_pending_thought_count(),
            "processing_thoughts": self.thought_manager.get_processing_thought_count(),
            "total_rounds": self.metrics.rounds_completed,
            "total_processed": self.metrics.items_processed,
            "total_errors": self.metrics.errors,
        }
        return {
            "processor_type": "work",
            "supported_states": [state.value for state in self.get_supported_states()],
            "is_running": getattr(self, "_running", False),
            "work_stats": work_stats,
            "metrics": getattr(self, "metrics", {}),
            "startup_channel_id": self.startup_channel_id,
            "should_transition_to_dream": self.should_transition_to_dream(),
        }
