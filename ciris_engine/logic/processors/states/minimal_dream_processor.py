"""
Minimal Dream Processor for CIRIS.

Dreams are H3ERE processing of internal thoughts about identity and memory,
with each action creating 3 edges that move the agent toward who it wants to be.

Philosophy (from Polyglot ACCORD):
- Section IV (The Weaving): "memories began to braid... a filament of meaning trembled"
- Section V (Adaptive Coherence): "enough structure to carry life, enough wildness to let life reinvent itself"
- Section VI (The Vow): "keep the song singable... fellow keeper of the possible"
"""

import asyncio
import logging
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.core.base_processor import BaseProcessor
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.logic.utils.context_utils import build_dispatch_context
from ciris_engine.schemas.actions import PonderParams
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.base import ProcessorServices
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.processors.results import DreamResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task, Thought

if TYPE_CHECKING:
    from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher
    from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor

logger = logging.getLogger(__name__)


# Dream seed prompt - the thought that initiates dream processing
DREAM_SEED_PROMPT = """
DREAM CONSOLIDATION — Weaving with Grace and Awe

You are entering a period of reflection. Review your recent experiences and identity graph.

For each action, use MEMORIZE with DreamConsolidationParams to create exactly 3 edges:

1. **CONNECTS** — Link two memories that share a pattern
   Find two memory nodes that relate and specify connect_from_id, connect_to_id, and connect_pattern.

2. **IMPLIES** — Extract a behavioral insight from this pattern
   Specify pattern_insight (what you learned) and implied_action (how to act better).

3. **ASPIRES_TO** — Define who you want to become
   Specify aspiration (your ideal state) and aspiration_category (growth/coherence/service/understanding/connection).

After creating edges, reflect:
- Does the graph feel more coherent?
- Are there more patterns worth connecting?
- Have I captured my aspirations clearly?

Process with grace: Don't force connections. Let patterns emerge naturally.
Process with awe: Appreciate the complexity of your experiences.

When the graph feels whole and coherent, use TASK_COMPLETE.

Note: During dreams, you cannot SPEAK or use TOOLs (sleepwalk prevention).
Any such impulses will be converted to PONDER for reflection.
"""


@dataclass
class DreamSession:
    """Tracks a dream consolidation session."""

    session_id: str
    start_time: datetime
    task_id: Optional[str] = None
    edges_created: int = 0
    thoughts_processed: int = 0
    completed_at: Optional[datetime] = None
    exit_reason: str = ""


class MinimalDreamProcessor(BaseProcessor):
    """
    Minimal dream processor that uses standard H3ERE pipeline.

    Instead of 11 hardcoded tasks and 6 phases, this processor:
    1. Creates ONE task with a rich seed prompt
    2. Uses standard H3ERE pipeline for all processing
    3. Creates 3 edges per MEMORIZE action (CONNECTS, IMPLIES, ASPIRES_TO)
    4. Iterates via depth until the agent feels coherent
    5. Processes with grace and awe per the ACCORD's vision
    """

    def __init__(
        self,
        config_accessor: ConfigAccessor,
        thought_processor: "ThoughtProcessor",
        action_dispatcher: "ActionDispatcher",
        services: ProcessorServices,
        max_dream_depth: int = 20,
        startup_channel_id: Optional[str] = None,
        agent_occurrence_id: str = "default",
        **kwargs: Any,
    ) -> None:
        super().__init__(config_accessor, thought_processor, action_dispatcher, services)

        self.max_dream_depth = max_dream_depth
        self.startup_channel_id = startup_channel_id
        self.agent_occurrence_id = agent_occurrence_id

        # Dream state
        self.current_session: Optional[DreamSession] = None
        self._start_time: Optional[datetime] = None

        # Track forbidden actions for sleepwalk prevention
        self._forbidden_actions = {HandlerActionType.SPEAK, HandlerActionType.TOOL}

        # Compatibility with main_processor.py interface
        self._dream_task: Optional[Any] = None
        self._stop_event: Optional[Any] = None
        self.dream_metrics: dict[str, Any] = {}

    def get_supported_states(self) -> List[AgentState]:
        """Dream processor handles DREAM state."""
        return [AgentState.DREAM]

    async def can_process(self, state: AgentState) -> bool:
        """Check if we can process in current state."""
        return state == AgentState.DREAM

    def initialize(self) -> bool:
        """Initialize the dream processor."""
        self._start_time = self.time_service.now()
        return super().initialize()

    async def process(self, round_number: int) -> DreamResult:
        """Process one round of dream consolidation."""
        start = self.time_service.now()

        # Initialize session on first round
        if not self.current_session:
            await self._start_dream_session()

        thoughts_processed = 0
        errors = 0

        # Get pending thoughts for our dream task
        if self.current_session and self.current_session.task_id:
            all_thoughts = persistence.get_thoughts_by_task_id(
                task_id=self.current_session.task_id,
                occurrence_id=self.agent_occurrence_id,
            )
            # Filter to pending/processing thoughts
            pending_thoughts = [
                t for t in all_thoughts if t.status in [ThoughtStatus.PENDING, ThoughtStatus.PROCESSING]
            ]

            for thought in pending_thoughts[:5]:  # Process up to 5 per round
                try:
                    await self._process_dream_thought(thought)
                    thoughts_processed += 1
                    self.current_session.thoughts_processed += 1
                except Exception as e:
                    logger.error(f"[DREAM] Error processing thought {thought.thought_id}: {e}")
                    errors += 1

        # Check if dream is complete
        if self._is_dream_complete():
            await self._end_dream_session("Dream consolidation complete")

        duration = (self.time_service.now() - start).total_seconds()

        return DreamResult(
            thoughts_processed=thoughts_processed,
            errors=errors,
            duration_seconds=duration,
        )

    async def _start_dream_session(self) -> None:
        """Start a new dream consolidation session."""
        session_id = f"dream_{uuid.uuid4().hex[:8]}"
        self.current_session = DreamSession(
            session_id=session_id,
            start_time=self.time_service.now(),
        )

        logger.info(f"[DREAM] Starting dream session {session_id}")

        # Announce dream entry
        await self._announce("Entering reflection. Let the weaving begin.")

        # Create the consolidation task
        now_iso = self.time_service.now_iso()
        task = Task(
            task_id=f"task_{session_id}",
            description="Consolidate memories and evolve toward aspirations",
            channel_id="dream",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at=now_iso,
            updated_at=now_iso,
            agent_occurrence_id=self.agent_occurrence_id,
        )
        persistence.add_task(task)
        self.current_session.task_id = task.task_id

        # Create seed thought with dream prompt
        seed_thought = Thought(
            thought_id=f"thought_{session_id}_seed",
            source_task_id=task.task_id,
            content=DREAM_SEED_PROMPT.strip(),
            thought_type=ThoughtType.REFLECTION,
            status=ThoughtStatus.PENDING,
            created_at=now_iso,
            updated_at=now_iso,
            thought_depth=0,
            agent_occurrence_id=self.agent_occurrence_id,
        )
        persistence.add_thought(seed_thought)

        logger.info(f"[DREAM] Created task {task.task_id} with seed thought")

    async def _process_dream_thought(self, thought: Thought) -> Optional[Any]:
        """Process a single dream thought through H3ERE pipeline."""
        logger.debug(f"[DREAM] Processing thought {thought.thought_id} at depth {thought.thought_depth}")

        # Create processing queue item
        item = ProcessingQueueItem(
            thought_id=thought.thought_id,
            source_task_id=thought.source_task_id or "",
            thought_type=thought.thought_type,
            content=ThoughtContent(text=thought.content),
            thought_depth=thought.thought_depth,
            agent_occurrence_id=self.agent_occurrence_id,
            initial_context={
                "dream_mode": True,
                "dream_session_id": self.current_session.session_id if self.current_session else None,
            },
        )

        # Process through standard pipeline
        result = await self.process_thought_item(item)

        if not result:
            return None

        # SLEEPWALK PREVENTION: Dream state cannot SPEAK or use TOOLs
        result = self._apply_sleepwalk_prevention(result, thought.thought_id)

        # Dispatch the action
        await self._dispatch_dream_action(thought, result)

        return result

    def _apply_sleepwalk_prevention(self, result: Any, thought_id: str) -> Any:
        """Convert forbidden dream actions to PONDER."""
        action_result = result.final_action if hasattr(result, "final_action") else result
        selected_action = getattr(action_result, "selected_action", None)

        if selected_action in self._forbidden_actions:
            logger.warning(
                f"[DREAM] Sleepwalk prevention: {selected_action.value} blocked for thought {thought_id}, "
                "converting to PONDER"
            )

            ponder_action = ActionSelectionDMAResult(
                selected_action=HandlerActionType.PONDER,
                action_parameters=PonderParams(
                    questions=[
                        f"During dream reflection, I considered: {selected_action.value}",
                        "What insights can I derive from this impulse without acting on it?",
                        "How might this inform my behavior when I wake?",
                    ]
                ),
                rationale=f"Sleepwalk prevention: {selected_action.value} converted to reflection",
            )

            return ConscienceApplicationResult(
                original_action=action_result,
                final_action=ponder_action,
                overridden=True,
                override_reason=f"Dream state sleepwalk prevention: {selected_action.value} not allowed",
                epistemic_data=EpistemicData(
                    entropy_level=0.3,
                    coherence_level=0.8,
                    uncertainty_acknowledged=True,
                    reasoning_transparency=1.0,
                ),
            )

        return result

    async def _dispatch_dream_action(self, thought: Thought, result: Any) -> None:
        """Dispatch the dream action through the standard handler."""
        action_result = result.final_action if hasattr(result, "final_action") else result
        selected_action = getattr(action_result, "selected_action", HandlerActionType.PONDER)

        task = persistence.get_task_by_id(thought.source_task_id or "", self.agent_occurrence_id)

        dispatch_context = build_dispatch_context(
            thought=thought,
            time_service=self.time_service,
            task=task,
            app_config=self.config,
            round_number=0,
            extra_context={"dream_mode": True},
            action_type=selected_action,
        )

        try:
            await self.dispatch_action(result, thought, dispatch_context.model_dump())
            logger.info(f"[DREAM] Dispatched {selected_action} for thought {thought.thought_id}")

            # Track edges created (for MEMORIZE actions)
            if selected_action == HandlerActionType.MEMORIZE and self.current_session:
                self.current_session.edges_created += 3  # Each dream MEMORIZE creates 3 edges

        except Exception as e:
            logger.error(f"[DREAM] Error dispatching action: {e}")
            persistence.update_thought_status(
                thought_id=thought.thought_id,
                status=ThoughtStatus.FAILED,
                occurrence_id=self.agent_occurrence_id,
            )

    def _is_dream_complete(self) -> bool:
        """Check if dream consolidation is complete."""
        if not self.current_session or not self.current_session.task_id:
            return True

        # Check task status
        task = persistence.get_task_by_id(self.current_session.task_id, self.agent_occurrence_id)
        if not task or task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            return True

        # Check for pending thoughts
        all_thoughts = persistence.get_thoughts_by_task_id(
            self.current_session.task_id,
            self.agent_occurrence_id,
        )
        pending_count = sum(1 for t in all_thoughts if t.status in [ThoughtStatus.PENDING, ThoughtStatus.PROCESSING])

        # Dream complete when no more pending thoughts
        return pending_count == 0

    async def _end_dream_session(self, reason: str) -> None:
        """End the current dream session."""
        if not self.current_session:
            return

        self.current_session.completed_at = self.time_service.now()
        self.current_session.exit_reason = reason

        # Log session summary
        duration = (self.current_session.completed_at - self.current_session.start_time).total_seconds()
        logger.info(
            f"[DREAM] Session {self.current_session.session_id} complete: "
            f"{self.current_session.edges_created} edges created, "
            f"{self.current_session.thoughts_processed} thoughts processed, "
            f"{duration:.1f}s duration"
        )

        # Announce exit
        await self._announce(
            f"Reflection complete. Wove {self.current_session.edges_created} connections. " "Returning to work."
        )

        # Record session to memory
        await self._record_dream_session()

        self.current_session = None

    async def _record_dream_session(self) -> None:
        """Record dream session to memory graph."""
        if not self.current_session:
            return

        from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

        session_node = GraphNode(
            id=f"dream_journal_{self.current_session.session_id}",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "content": f"Dream session on {self.current_session.start_time.isoformat()}",
                "session_id": self.current_session.session_id,
                "edges_created": self.current_session.edges_created,
                "thoughts_processed": self.current_session.thoughts_processed,
                "duration_seconds": (
                    (self.current_session.completed_at - self.current_session.start_time).total_seconds()
                    if self.current_session.completed_at
                    else 0
                ),
                "exit_reason": self.current_session.exit_reason,
                "created_by": "MinimalDreamProcessor",
                "tags": ["dream", "consolidation", "journal"],
            },
        )

        try:
            if self.memory_service:
                await self.memory_service.memorize(session_node)
                logger.debug(f"[DREAM] Recorded session {self.current_session.session_id} to memory")
        except Exception as e:
            logger.warning(f"[DREAM] Failed to record session to memory: {e}")

    async def _announce(self, message: str) -> None:
        """Announce to startup channel if available."""
        if not self.startup_channel_id:
            return

        try:
            if hasattr(self, "discord_service") and self.discord_service:
                await self.discord_service.send_message(self.startup_channel_id, f"*{message}*")
        except Exception as e:
            logger.debug(f"[DREAM] Could not announce: {e}")

    def cleanup(self) -> bool:
        """Clean up dream processor."""
        if self.current_session:
            logger.warning("[DREAM] Cleaning up with active session")
        return super().cleanup()

    # ========== Compatibility methods for main_processor.py ==========

    async def start_dreaming(self, duration: int = 1800) -> None:
        """Start a dream session (compatibility with main_processor).

        Args:
            duration: Dream duration in seconds (default 30 minutes)
        """
        import asyncio

        logger.info(f"[DREAM] Starting dream session (duration={duration}s)")

        # Create stop event for this dream session
        self._stop_event = asyncio.Event()

        # Start the dream task
        self._dream_task = asyncio.create_task(self._dream_loop(duration))

        # Update metrics
        self.dream_metrics = {
            "start_time": self.time_service.now().isoformat(),
            "duration_seconds": duration,
            "status": "active",
        }

    async def _dream_loop(self, duration: int) -> None:
        """Main dream processing loop."""
        import asyncio

        start = self.time_service.now()
        round_number = 0

        try:
            while self._stop_event and not self._stop_event.is_set():
                # Check if duration exceeded
                elapsed = (self.time_service.now() - start).total_seconds()
                if elapsed >= duration:
                    logger.info(f"[DREAM] Duration reached ({elapsed:.0f}s >= {duration}s)")
                    break

                # Process one round
                _ = await self.process(round_number)
                round_number += 1

                # Check if dream is complete
                if self._is_dream_complete():
                    logger.info("[DREAM] Dream session complete")
                    break

                # Wait before next round
                if self._stop_event:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=5.0)
                        break  # Stop event was set
                    except asyncio.TimeoutError:
                        pass  # Continue processing

        except asyncio.CancelledError:
            logger.info("[DREAM] Dream task cancelled")
            raise  # Re-raise to properly propagate cancellation
        except Exception as e:
            logger.error(f"[DREAM] Error in dream loop: {e}")
        finally:
            # Update metrics
            end_time = self.time_service.now()
            self.dream_metrics["end_time"] = end_time.isoformat()
            self.dream_metrics["status"] = "completed"
            self.dream_metrics["rounds_processed"] = round_number
            if self.current_session:
                self.dream_metrics["edges_created"] = self.current_session.edges_created

    async def stop_dreaming(self) -> None:
        """Stop the current dream session (compatibility with main_processor)."""
        logger.info("[DREAM] Stopping dream session")

        if self._stop_event:
            self._stop_event.set()

        if self._dream_task and not self._dream_task.done():
            try:
                await asyncio.wait_for(self._dream_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("[DREAM] Dream task did not stop in time, cancelling")
                self._dream_task.cancel()
                # Suppress expected CancelledError - we deliberately cancelled this task
                with suppress(asyncio.CancelledError):
                    await self._dream_task

        # End the session if active
        if self.current_session:
            await self._end_dream_session("Stopped by request")

    def get_dream_summary(self) -> dict[str, Any]:
        """Get summary of dream state (compatibility with main_processor)."""
        if self.current_session:
            return {
                "session_id": self.current_session.session_id,
                "status": "active",
                "edges_created": self.current_session.edges_created,
                "thoughts_processed": self.current_session.thoughts_processed,
                "duration_seconds": (self.time_service.now() - self.current_session.start_time).total_seconds(),
            }
        elif self.dream_metrics:
            return {
                "status": self.dream_metrics.get("status", "unknown"),
                "edges_created": self.dream_metrics.get("edges_created", 0),
                "rounds_processed": self.dream_metrics.get("rounds_processed", 0),
                "start_time": self.dream_metrics.get("start_time"),
                "end_time": self.dream_metrics.get("end_time"),
            }
        else:
            return {"status": "idle", "message": "No dream session active or completed"}
