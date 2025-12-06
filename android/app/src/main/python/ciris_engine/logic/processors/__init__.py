"""
CIRISAgent processor module.
Provides state-aware task and thought processing using v1 schemas.
"""

from ciris_engine.logic.processors.core.base_processor import BaseProcessor
from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.logic.processors.states.dream_processor import DreamProcessor
from ciris_engine.logic.processors.states.play_processor import PlayProcessor
from ciris_engine.logic.processors.states.solitude_processor import SolitudeProcessor
from ciris_engine.logic.processors.states.wakeup_processor import WakeupProcessor
from ciris_engine.logic.processors.states.work_processor import WorkProcessor

from .support.state_manager import StateManager, StateTransition
from .support.task_manager import TaskManager
from .support.thought_manager import ThoughtManager

__all__ = [
    "AgentProcessor",
    "BaseProcessor",
    "WakeupProcessor",
    "WorkProcessor",
    "PlayProcessor",
    "DreamProcessor",
    "SolitudeProcessor",
    "StateManager",
    "StateTransition",
    "TaskManager",
    "ThoughtManager",
]
