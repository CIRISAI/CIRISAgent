"""Custom exception types for thought processor."""

from typing import Any


class ProcessorError(Exception):
    """Base exception for processor errors."""

    def __init__(self, message: str, context: dict[str, Any]):
        super().__init__(message)
        self.context = context
        self.message = message


class ActionSelectionRetryFailed(ProcessorError):
    """Raised when action selection retry fails."""

    def __init__(self, thought_id: str, error_details: str):
        super().__init__(
            f"Action selection retry failed for thought {thought_id}",
            {"thought_id": thought_id, "error_details": error_details},
        )
        self.thought_id = thought_id


class ConscienceCheckFailed(ProcessorError):
    """Raised when a conscience check encounters an error."""

    def __init__(self, conscience_name: str, error: Exception):
        super().__init__(
            f"Conscience '{conscience_name}' failed: {error}",
            {"conscience_name": conscience_name, "original_error": str(error)},
        )
        self.conscience_name = conscience_name
        self.original_error = error


class DMAExecutionFailed(ProcessorError):
    """Raised when DMA execution fails."""

    def __init__(self, dma_name: str, error: Exception):
        super().__init__(
            f"DMA '{dma_name}' execution failed: {error}",
            {"dma_name": dma_name, "original_error": str(error)},
        )
        self.dma_name = dma_name
        self.original_error = error


class ContextBuildingFailed(ProcessorError):
    """Raised when context building fails."""

    def __init__(self, thought_id: str, error: Exception):
        super().__init__(
            f"Failed to build context for thought {thought_id}: {error}",
            {"thought_id": thought_id, "original_error": str(error)},
        )
        self.thought_id = thought_id
        self.original_error = error
