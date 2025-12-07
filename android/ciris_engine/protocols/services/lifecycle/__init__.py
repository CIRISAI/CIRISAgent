"""Lifecycle service protocols."""

from .initialization import InitializationServiceProtocol
from .scheduler import TaskSchedulerServiceProtocol
from .shutdown import ShutdownServiceProtocol
from .time import TimeServiceProtocol

__all__ = [
    "TimeServiceProtocol",
    "ShutdownServiceProtocol",
    "InitializationServiceProtocol",
    "TaskSchedulerServiceProtocol",
]
