"""Infrastructure handlers module - exports base handler only."""

from .base_handler import ActionHandlerDependencies, BaseActionHandler

__all__ = [
    "BaseActionHandler",
    "ActionHandlerDependencies",
]
