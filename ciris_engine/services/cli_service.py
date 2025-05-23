import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from .base import Service
from ciris_engine.core.action_dispatcher import ActionDispatcher
from ciris_engine.core.agent_core_schemas import (
    ActionSelectionPDMAResult,
    HandlerActionType,
    SpeakParams,
    DeferParams,
    RejectParams,
)
from ciris_engine.core.agent_core_schemas import Task
from ciris_engine.core.foundational_schemas import TaskStatus, ThoughtStatus
from ciris_engine.core import persistence

logger = logging.getLogger(__name__)


class CLIService(Service):
    """Simple interactive CLI service for local benchmarking."""

    def __init__(self, action_dispatcher: ActionDispatcher):
        super().__init__()
        self.action_dispatcher = action_dispatcher
        self.action_dispatcher.register_service_handler("cli", self._handle_cli_action)
        self._running = False

    async def start(self):
        await super().start()
        self._running = True
        logger.info("CLIService started. Type 'exit' to quit.")
        await self._input_loop()

    async def stop(self):
        self._running = False
        await super().stop()
        logger.info("CLIService stopped.")

    async def _input_loop(self):
        while self._running:
            user_input = await asyncio.to_thread(input, ">>> ")
            if user_input.strip().lower() in {"exit", "quit"}:
                self._running = False
                break
            await self._create_task(user_input)

    async def _create_task(self, content: str):
        now_iso = datetime.now(timezone.utc).isoformat()
        new_task_id = f"cli_{uuid.uuid4().hex[:8]}"
        task = Task(
            task_id=new_task_id,
            description=content,
            status=TaskStatus.PENDING,
            priority=1,
            created_at=now_iso,
            updated_at=now_iso,
            context={"origin_service": "cli", "content": content},
        )
        persistence.add_task(task)
        logger.info(f"CLIService: Added task {new_task_id}")

    async def _handle_cli_action(self, result: ActionSelectionPDMAResult, dispatch_context: Dict[str, Any]):
        action_type = result.selected_handler_action
        params = result.action_parameters
        if action_type == HandlerActionType.SPEAK and isinstance(params, SpeakParams):
            print(params.content)
        elif action_type == HandlerActionType.DEFER and isinstance(params, DeferParams):
            print(f"DEFERRED: {params.reason}")
        elif action_type == HandlerActionType.REJECT and isinstance(params, RejectParams):
            print(f"REJECTED: {params.reason}")
        else:
            logger.info(f"Unhandled action {action_type} in CLIService")

        thought_id = dispatch_context.get("thought_id")
        if thought_id:
            persistence.update_thought_status(
                thought_id=thought_id,
                new_status=ThoughtStatus.COMPLETED,
                final_action_result=result.model_dump(),
            )

