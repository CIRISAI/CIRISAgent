"""
Action schemas - shared across handlers, DMAs, and services.

These schemas define the parameters and results for all agent actions.
"""

# Import all action parameters
from .parameters import (  # External actions; Control actions; Memory actions; Terminal action
    DeferParams,
    ForgetParams,
    MemorizeParams,
    ObserveParams,
    PonderParams,
    RecallParams,
    RejectParams,
    SpeakParams,
    TaskCompleteParams,
    ToolParams,
)

# Make them available at package level
__all__ = [
    # External
    "ObserveParams",
    "SpeakParams",
    "ToolParams",
    # Control
    "PonderParams",
    "RejectParams",
    "DeferParams",
    # Memory
    "MemorizeParams",
    "RecallParams",
    "ForgetParams",
    # Terminal
    "TaskCompleteParams",
]
