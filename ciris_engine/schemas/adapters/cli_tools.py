"""
Schemas for CLI tool operations.

These replace all Dict[str, Any] usage in logic/adapters/cli/cli_tools.py.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class ToolParameters(BaseModel):
    """Base parameters for tool execution."""

    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracking")
    metadata: JSONDict = Field(default_factory=dict, description="Additional metadata")


class ListFilesParams(ToolParameters):
    """Parameters for list_files tool."""

    path: str = Field(".", description="Directory path to list")


class ListFilesResult(BaseModel):
    """Result from list_files tool."""

    files: List[str] = Field(..., description="List of files in directory")
    path: str = Field(..., description="Directory path that was listed")
    error: Optional[str] = Field(None, description="Error message if failed")


class ReadFileParams(ToolParameters):
    """Parameters for read_file tool."""

    path: str = Field(..., description="File path to read")


class ReadFileResult(BaseModel):
    """Result from read_file tool."""

    content: Optional[str] = Field(None, description="File content")
    path: Optional[str] = Field(None, description="File path that was read")
    error: Optional[str] = Field(None, description="Error message if failed")


class WriteFileParams(ToolParameters):
    """Parameters for write_file tool."""

    path: str = Field(..., description="File path to write")
    content: str = Field("", description="Content to write to file")


class WriteFileResult(BaseModel):
    """Result from write_file tool."""

    status: Optional[str] = Field(None, description="Write status")
    path: Optional[str] = Field(None, description="File path that was written")
    error: Optional[str] = Field(None, description="Error message if failed")


class ShellCommandParams(ToolParameters):
    """Parameters for shell_command tool."""

    command: str = Field(..., description="Shell command to execute")
    timeout: Optional[float] = Field(None, description="Command timeout in seconds")


class ShellCommandResult(BaseModel):
    """Result from shell_command tool."""

    stdout: Optional[str] = Field(None, description="Standard output")
    stderr: Optional[str] = Field(None, description="Standard error")
    returncode: Optional[int] = Field(None, description="Command return code")
    error: Optional[str] = Field(None, description="Error message if failed")


class SearchMatch(BaseModel):
    """A single search match."""

    line: int = Field(..., description="Line number")
    text: str = Field(..., description="Matching text")


class SearchTextParams(ToolParameters):
    """Parameters for search_text tool."""

    pattern: str = Field(..., description="Pattern to search for")
    path: str = Field(..., description="File path to search in")


class SearchTextResult(BaseModel):
    """Result from search_text tool."""

    matches: List[SearchMatch] = Field(default_factory=list, description="List of matches")
    error: Optional[str] = Field(None, description="Error message if failed")
