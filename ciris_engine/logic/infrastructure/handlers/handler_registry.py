"""
Central registry for all action handlers, mapping HandlerActionType to handler instances.
Ensures modular, v1-schema-compliant, and clean handler wiring for ActionDispatcher.
"""

from typing import Any, Callable, Optional

from ciris_engine.logic.handlers.control.defer_handler import DeferHandler
from ciris_engine.logic.handlers.control.ponder_handler import PonderHandler
from ciris_engine.logic.handlers.control.reject_handler import RejectHandler
from ciris_engine.logic.handlers.external.observe_handler import ObserveHandler
from ciris_engine.logic.handlers.external.speak_handler import SpeakHandler
from ciris_engine.logic.handlers.external.tool_handler import ToolHandler
from ciris_engine.logic.handlers.memory.forget_handler import ForgetHandler
from ciris_engine.logic.handlers.memory.memorize_handler import MemorizeHandler
from ciris_engine.logic.handlers.memory.recall_handler import RecallHandler
from ciris_engine.logic.handlers.terminal.task_complete_handler import TaskCompleteHandler
from ciris_engine.schemas.runtime.enums import HandlerActionType

from .action_dispatcher import ActionDispatcher
from .base_handler import ActionHandlerDependencies


def build_action_dispatcher(
    bus_manager: Any,
    time_service: Any,
    max_rounds: int = 5,
    shutdown_callback: Optional[Callable[[], None]] = None,
    telemetry_service: Optional[Any] = None,
    secrets_service: Optional[Any] = None,
    audit_service: Optional[Any] = None,
) -> ActionDispatcher:
    """
    Instantiates all handlers and returns a ready-to-use ActionDispatcher.
    Uses service_registry for all service dependencies.
    """
    deps = ActionHandlerDependencies(
        bus_manager=bus_manager,
        time_service=time_service,
        shutdown_callback=shutdown_callback,
        secrets_service=secrets_service,
    )
    handlers = {
        HandlerActionType.MEMORIZE: MemorizeHandler(deps),
        HandlerActionType.SPEAK: SpeakHandler(deps),
        HandlerActionType.OBSERVE: ObserveHandler(deps),
        HandlerActionType.DEFER: DeferHandler(deps),
        HandlerActionType.REJECT: RejectHandler(deps),
        HandlerActionType.TASK_COMPLETE: TaskCompleteHandler(deps),
        HandlerActionType.TOOL: ToolHandler(deps),
        HandlerActionType.RECALL: RecallHandler(deps),
        HandlerActionType.FORGET: ForgetHandler(deps),
        HandlerActionType.PONDER: PonderHandler(deps, max_rounds=max_rounds),
    }
    dispatcher = ActionDispatcher(
        handlers, telemetry_service=telemetry_service, time_service=time_service, audit_service=audit_service
    )

    return dispatcher
