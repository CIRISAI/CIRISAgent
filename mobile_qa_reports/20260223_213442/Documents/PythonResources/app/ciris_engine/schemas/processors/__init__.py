"""Package initialization."""

from .core import (
    ConscienceApplicationResult,
    DMAResults,
    ProcessedThoughtResult,
    ProcessingError,
    ThoughtProcessingMetrics,
)
from .error import ErrorContext, ErrorHandlingResult, ErrorSeverity
from .error import ProcessingError as ProcessorError
from .error import ProcessorConfig

__all__ = [
    "DMAResults",
    "ConscienceApplicationResult",
    "ProcessedThoughtResult",
    "ThoughtProcessingMetrics",
    "ProcessingError",
    # Error handling schemas
    "ErrorSeverity",
    "ErrorContext",
    "ProcessorError",
    "ErrorHandlingResult",
    "ProcessorConfig",
]
