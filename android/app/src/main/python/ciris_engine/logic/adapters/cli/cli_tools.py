import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiofiles

from ciris_engine.logic import persistence
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.logic.utils.jsondict_helpers import get_str
from ciris_engine.protocols.services import ToolService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.cli_tools import (
    ListFilesParams,
    ListFilesResult,
    ReadFileParams,
    ReadFileResult,
    SearchMatch,
    SearchTextParams,
    SearchTextResult,
    ShellCommandParams,
    ShellCommandResult,
    WriteFileParams,
    WriteFileResult,
)
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.telemetry.core import ServiceCorrelation, ServiceCorrelationStatus
from ciris_engine.schemas.types import JSONDict


class CLIToolService(BaseService, ToolService):
    """Simple ToolService providing local filesystem browsing."""

    def __init__(self, time_service: TimeServiceProtocol) -> None:
        # Initialize BaseService with proper arguments
        super().__init__(time_service=time_service, service_name="CLIToolService")
        # ToolService is a Protocol, no need to call its __init__
        self._results: Dict[str, ToolExecutionResult] = {}
        self._tools = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "shell_command": self._shell_command,
            "search_text": self._search_text,
        }
        # Track tool executions
        self._tool_executions = 0
        self._tool_failures = 0

    async def start(self) -> None:
        """Start the CLI tool service."""
        await BaseService.start(self)

    async def stop(self) -> None:
        """Stop the CLI tool service."""
        await BaseService.stop(self)

    async def execute_tool(self, tool_name: str, parameters: JSONDict) -> ToolExecutionResult:
        # Track request for telemetry
        self._track_request()
        self._tool_executions += 1

        correlation_id = get_str(parameters, "correlation_id", str(uuid.uuid4()))
        now = datetime.now(timezone.utc)
        corr = ServiceCorrelation(
            correlation_id=correlation_id,
            service_type="cli",
            handler_name="CLIToolService",
            action_type=tool_name,
            created_at=now,
            updated_at=now,
            timestamp=now,
            status=ServiceCorrelationStatus.PENDING,
        )
        persistence.add_correlation(corr)

        # Assert time_service is available
        assert self._time_service is not None
        start_time = self._time_service.timestamp()

        # Declare result type explicitly to allow mixed types (str error, float execution_time_ms)
        result: JSONDict
        success: bool
        error_msg: Optional[str]

        if tool_name not in self._tools:
            # Unknown tool - track as failure
            # Note: _tool_executions already incremented above
            self._tool_failures += 1
            result = {"error": f"Unknown tool: {tool_name}"}
            success = False
            error_msg = f"Unknown tool: {tool_name}"
        else:
            try:
                result = await self._tools[tool_name](parameters)
                # FAIL FAST: Result MUST be a dict (until we have proper typed tool results)
                if not isinstance(result, dict):
                    raise TypeError(
                        f"Tool {tool_name} returned non-dict result: {type(result).__name__}. "
                        "Tools MUST return typed dict results!"
                    )
                success = result.get("error") is None
                error_value = result.get("error")
                error_msg = str(error_value) if error_value is not None else None
            except Exception as e:
                # Track error for telemetry
                self._track_error(e)
                self._tool_failures += 1
                result = {"error": str(e)}
                success = False
                error_msg = str(e)

        execution_time_ms = (self._time_service.timestamp() - start_time) * 1000  # milliseconds

        # Add execution time to result data
        if result is None:
            result = {}
        if isinstance(result, dict):
            result["_execution_time_ms"] = execution_time_ms

        tool_result = ToolExecutionResult(
            tool_name=tool_name,
            status=ToolExecutionStatus.COMPLETED if success else ToolExecutionStatus.FAILED,
            success=success,
            data=result,
            error=error_msg,
            correlation_id=correlation_id,
        )

        if correlation_id:
            self._results[correlation_id] = tool_result
            # Update the correlation we created earlier
            corr.status = ServiceCorrelationStatus.COMPLETED
            corr.updated_at = datetime.now(timezone.utc)
            persistence.update_correlation(correlation_id, corr, self._time_service)
        return tool_result

    async def _list_files(self, params: JSONDict) -> JSONDict:
        """List files using typed parameters."""
        # Parse parameters
        list_params = ListFilesParams.model_validate(params)

        try:
            files = sorted(os.listdir(list_params.path))
            result = ListFilesResult(files=files, path=list_params.path)
            return result.model_dump()
        except Exception as e:
            result = ListFilesResult(files=[], path=list_params.path, error=str(e))
            return result.model_dump()

    async def _read_file(self, params: JSONDict) -> JSONDict:
        """Read file contents using typed parameters."""
        try:
            # Parse and validate parameters
            read_params = ReadFileParams.model_validate(params)

            async with aiofiles.open(read_params.path, "r") as f:
                content = await f.read()
                result = ReadFileResult(content=content, path=read_params.path)
                return result.model_dump()
        except ValueError:
            # Parameter validation error
            result = ReadFileResult(error="path parameter required")
            return result.model_dump()
        except Exception as e:
            result = ReadFileResult(error=str(e))
            return result.model_dump()

    async def _write_file(self, params: JSONDict) -> JSONDict:
        """Write file using typed parameters."""
        try:
            # Parse and validate parameters
            write_params = WriteFileParams.model_validate(params)

            await asyncio.to_thread(self._write_file_sync, write_params.path, write_params.content)
            result = WriteFileResult(status="written", path=write_params.path)
            return result.model_dump()
        except ValueError:
            # Parameter validation error
            result = WriteFileResult(error="path parameter required")
            return result.model_dump()
        except Exception as e:
            result = WriteFileResult(error=str(e))
            return result.model_dump()

    def _write_file_sync(self, path: str, content: str) -> None:
        with open(path, "w") as f:
            f.write(content)

    async def _shell_command(self, params: JSONDict) -> JSONDict:
        """Execute shell command using typed parameters."""
        try:
            # Parse and validate parameters
            shell_params = ShellCommandParams.model_validate(params)

            proc = await asyncio.create_subprocess_shell(
                shell_params.command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            result = ShellCommandResult(stdout=stdout.decode(), stderr=stderr.decode(), returncode=proc.returncode)
            return result.model_dump()
        except ValueError:
            # Parameter validation error
            result = ShellCommandResult(error="command parameter required")
            return result.model_dump()
        except Exception as e:
            result = ShellCommandResult(error=str(e))
            return result.model_dump()

    async def _search_text(self, params: JSONDict) -> JSONDict:
        """Search text in file using typed parameters."""
        try:
            # Parse and validate parameters
            search_params = SearchTextParams.model_validate(params)

            matches: List[SearchMatch] = []
            lines = await asyncio.to_thread(self._read_lines_sync, search_params.path)
            for idx, line in enumerate(lines, 1):
                if search_params.pattern in line:
                    matches.append(SearchMatch(line=idx, text=line.strip()))

            result = SearchTextResult(matches=matches)
            return result.model_dump()
        except ValueError:
            # Parameter validation error
            result = SearchTextResult(error="pattern and path required")
            return result.model_dump()
        except Exception as e:
            result = SearchTextResult(error=str(e))
            return result.model_dump()

    def _read_lines_sync(self, path: str) -> List[str]:
        with open(path, "r") as f:
            return f.readlines()

    async def get_available_tools(self) -> List[str]:
        return list(self._tools.keys())

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        for _ in range(int(timeout * 10)):
            if correlation_id in self._results:
                return self._results.pop(correlation_id)
            await asyncio.sleep(0.1)
        return None

    async def validate_parameters(self, tool_name: str, parameters: JSONDict) -> bool:
        return tool_name in self._tools

    async def list_tools(self) -> List[str]:
        """List available tools - required by ToolServiceProtocol."""
        return list(self._tools.keys())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool - required by ToolServiceProtocol."""
        # Define schemas for each tool
        schemas = {
            "list_files": ToolParameterSchema(
                type="object",
                properties={
                    "path": {"type": "string", "description": "Directory path to list files from", "default": "."}
                },
                required=[],
            ),
            "read_file": ToolParameterSchema(
                type="object",
                properties={"path": {"type": "string", "description": "File path to read"}},
                required=["path"],
            ),
            "write_file": ToolParameterSchema(
                type="object",
                properties={
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write to file"},
                },
                required=["path", "content"],
            ),
            "shell_command": ToolParameterSchema(
                type="object",
                properties={"command": {"type": "string", "description": "Shell command to execute"}},
                required=["command"],
            ),
            "search_text": ToolParameterSchema(
                type="object",
                properties={
                    "path": {"type": "string", "description": "Directory path to search in"},
                    "pattern": {"type": "string", "description": "Text pattern to search for"},
                },
                required=["path", "pattern"],
            ),
        }
        return schemas.get(tool_name)

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool."""
        if tool_name not in self._tools:
            return None

        # Tool information for each built-in tool
        tool_infos = {
            "list_files": ToolInfo(
                name="list_files",
                description="List files in a directory",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "path": {"type": "string", "description": "Directory path to list files from", "default": "."}
                    },
                    required=[],
                ),
                category="filesystem",
                cost=0.0,
                when_to_use="Use when you need to see what files are in a directory",
            ),
            "read_file": ToolInfo(
                name="read_file",
                description="Read the contents of a file",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={"path": {"type": "string", "description": "File path to read"}},
                    required=["path"],
                ),
                category="filesystem",
                cost=0.0,
                when_to_use="Use when you need to read file contents",
            ),
            "write_file": ToolInfo(
                name="write_file",
                description="Write content to a file",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "path": {"type": "string", "description": "File path to write"},
                        "content": {"type": "string", "description": "Content to write to file"},
                    },
                    required=["path", "content"],
                ),
                category="filesystem",
                cost=0.0,
                when_to_use="Use when you need to create or modify a file",
            ),
            "shell_command": ToolInfo(
                name="shell_command",
                description="Execute a shell command",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={"command": {"type": "string", "description": "Shell command to execute"}},
                    required=["command"],
                ),
                category="system",
                cost=0.0,
                when_to_use="Use when you need to run system commands",
            ),
            "search_text": ToolInfo(
                name="search_text",
                description="Search for text patterns in files",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "path": {"type": "string", "description": "Directory path to search in"},
                        "pattern": {"type": "string", "description": "Text pattern to search for"},
                    },
                    required=["path", "pattern"],
                ),
                category="filesystem",
                cost=0.0,
                when_to_use="Use when you need to find specific text in files",
            ),
        }

        return tool_infos.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get detailed information about all available tools."""
        tool_infos = []
        for tool_name in self._tools.keys():
            tool_info = await self.get_tool_info(tool_name)
            if tool_info:
                tool_infos.append(tool_info)
        return tool_infos

    async def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        return True

    def get_service_type(self) -> ServiceType:
        """Get the type of this service."""
        return ServiceType.ADAPTER

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="CLIToolService",
            actions=["execute_tool", "get_available_tools", "get_tool_schema", "get_tool_result"],
            version="1.0.0",
            dependencies=[],
            metadata=None,
        )

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect CLI tool service specific metrics."""
        return {
            "tools_count": float(len(self._tools)),
            "tool_executions_total": float(self._tool_executions),
            "tool_failures_total": float(self._tool_failures),
            "tool_success_rate": float(self._tool_executions - self._tool_failures) / max(1, self._tool_executions),
            "results_cached": float(len(self._results)),
        }

    def _get_actions(self) -> List[str]:
        """Get the list of actions this service supports."""
        return [
            "execute_tool",
            "get_available_tools",
            "get_tool_result",
            "validate_parameters",
            "get_tool_info",
            "get_all_tool_info",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are satisfied."""
        # CLIToolService has no hard dependencies
        return True
