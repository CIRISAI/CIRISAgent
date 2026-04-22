"""
Schemas for CLI adapter operations.

Provides typed schemas for logic/adapters/cli/cli_adapter.py.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class CLIMessage(BaseModel):
    """A message received from or sent to CLI."""

    channel_id: str = Field(..., description="Channel identifier")
    content: str = Field(..., description="Message content")
    timestamp: str = Field(..., description="ISO timestamp")
    message_type: str = Field("user", description="Type: user, system, error")


class CLIToolParameters(BaseModel):
    """Base parameters for CLI tool execution."""

    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracking")


class ListFilesToolParams(CLIToolParameters):
    """Parameters for list_files tool."""

    path: str = Field(".", description="Directory path to list")


class ListFilesToolResult(BaseModel):
    """Result from list_files tool."""

    success: bool = Field(..., description="Whether the operation succeeded")
    files: List[str] = Field(default_factory=list, description="List of files")
    count: int = Field(..., description="Number of files")
    error: Optional[str] = Field(None, description="Error message if failed")


class ReadFileToolParams(CLIToolParameters):
    """Parameters for read_file tool."""

    path: str = Field(..., description="File path to read")
    encoding: str = Field("utf-8", description="File encoding")


class ReadFileToolResult(BaseModel):
    """Result from read_file tool."""

    success: bool = Field(..., description="Whether the operation succeeded")
    content: Optional[str] = Field(None, description="File content")
    size: Optional[int] = Field(None, description="File size in bytes")
    error: Optional[str] = Field(None, description="Error message if failed")


class SystemInfoToolResult(BaseModel):
    """Result from system_info tool."""

    success: bool = Field(..., description="Whether the operation succeeded")
    platform: str = Field(..., description="Operating system platform")
    python_version: str = Field(..., description="Python version")
    cpu_count: int = Field(..., description="Number of CPUs")
    memory_mb: int = Field(..., description="Total memory in MB")
    error: Optional[str] = Field(None, description="Error message if failed")


class CLIGuidanceRequest(BaseModel):
    """Guidance request displayed to CLI user."""

    question: str = Field(..., description="Question for the user")
    task_id: str = Field(..., description="Related task ID")
    ethical_considerations: List[str] = Field(default_factory=list, description="Ethical considerations")
    timeout_seconds: float = Field(300.0, description="Timeout for user response")


class CLIDeferralDisplay(BaseModel):
    """Deferral information displayed to CLI user."""

    thought_id: str = Field(..., description="Deferred thought ID")
    task_id: str = Field(..., description="Related task ID")
    reason: str = Field(..., description="Reason for deferral")
    defer_until: Optional[str] = Field(None, description="When to reconsider")
    additional_info: JSONDict = Field(default_factory=dict, description="Additional metadata")


class CLICorrelationData(BaseModel):
    """Data stored in correlations for CLI operations."""

    action: str = Field(..., description="Action performed")
    request: JSONDict = Field(default_factory=dict, description="Request data")
    response: JSONDict = Field(default_factory=dict, description="Response data")
    success: bool = Field(True, description="Whether operation succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
