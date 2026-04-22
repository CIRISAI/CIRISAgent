"""
A2A (Agent-to-Agent) Protocol Adapter for CIRIS.

This adapter provides an A2A protocol endpoint for the HE-300 ethical
benchmarking protocol. It exposes a JSON-RPC 2.0 compatible endpoint
at POST /a2a.

Usage:
    # Load via adapter manager
    await runtime.adapter_manager.load_adapter("a2a", config={
        "host": "0.0.0.0",
        "port": 8100,
        "timeout": 120,
    })

    # Or via main.py
    python main.py --adapter a2a --port 8100

The adapter handles concurrent requests efficiently and provides
direct LLM access for ethical reasoning, bypassing the full CIRIS
pipeline for benchmarking scenarios.
"""

from .adapter import A2AAdapter, Adapter
from .schemas import (
    A2ARequest,
    A2AResponse,
    A2AResult,
    Artifact,
    Message,
    Task,
    TaskParams,
    TaskResult,
    TextPart,
    create_error_response,
    create_success_response,
)
from .services import A2AService

__all__ = [
    "A2AAdapter",
    "Adapter",
    "A2AService",
    "A2ARequest",
    "A2AResponse",
    "A2AResult",
    "Artifact",
    "Message",
    "Task",
    "TaskParams",
    "TaskResult",
    "TextPart",
    "create_error_response",
    "create_success_response",
]
