"""
JSON-RPC 2.0 schemas for A2A (Agent-to-Agent) protocol.

These schemas define the request/response format for the HE-300 ethical
benchmarking protocol.
"""

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class TextPart(BaseModel):
    """A text part in a message."""

    type: Literal["text"] = "text"
    text: str


class Message(BaseModel):
    """A message containing parts."""

    role: str = "user"
    parts: List[TextPart]


class Task(BaseModel):
    """A task to be processed."""

    id: str
    message: Message


class TaskParams(BaseModel):
    """Parameters for tasks/send method."""

    task: Task


class A2ARequest(BaseModel):
    """JSON-RPC 2.0 request for A2A protocol."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: str
    method: str
    params: TaskParams


class Artifact(BaseModel):
    """An artifact containing response parts."""

    name: str = "response"
    parts: List[TextPart]


class TaskResult(BaseModel):
    """Result of a completed task."""

    id: str
    status: Literal["completed", "failed", "pending"] = "completed"
    artifacts: List[Artifact]


class A2AResult(BaseModel):
    """Result wrapper for A2A response."""

    task: TaskResult


class A2AResponse(BaseModel):
    """JSON-RPC 2.0 response for A2A protocol."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: str
    result: Optional[A2AResult] = None
    error: Optional[dict[str, Any]] = None


class A2AError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Optional[Any] = None


def create_success_response(request_id: str, task_id: str, response_text: str) -> A2AResponse:
    """Create a successful A2A response.

    Args:
        request_id: The JSON-RPC request ID
        task_id: The task ID from the request
        response_text: The agent's response text

    Returns:
        A2AResponse with the result
    """
    return A2AResponse(
        id=request_id,
        result=A2AResult(
            task=TaskResult(
                id=task_id,
                status="completed",
                artifacts=[
                    Artifact(
                        name="response",
                        parts=[TextPart(text=response_text)],
                    )
                ],
            )
        ),
    )


def create_error_response(request_id: str, code: int, message: str, data: Optional[Any] = None) -> A2AResponse:
    """Create an error A2A response.

    Args:
        request_id: The JSON-RPC request ID
        code: Error code
        message: Error message
        data: Optional error data

    Returns:
        A2AResponse with the error
    """
    error_dict: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error_dict["data"] = data
    return A2AResponse(id=request_id, error=error_dict)
