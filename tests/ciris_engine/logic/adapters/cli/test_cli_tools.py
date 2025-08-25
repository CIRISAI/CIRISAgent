"""
Comprehensive tests for CLIToolService.

Tests all tool functions, error handling, and service operations.
"""

import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiofiles
import pytest
from pydantic import ValidationError

from ciris_engine.logic.adapters.cli.cli_tools import CLIToolService
from ciris_engine.logic.services.lifecycle.time import TimeService
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
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.telemetry.core import ServiceCorrelation, ServiceCorrelationStatus


@pytest.fixture
def time_service():
    """Mock time service."""
    mock_time = MagicMock(spec=TimeService)
    mock_time.timestamp.return_value = 1234567890.0
    mock_time.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return mock_time


@pytest.fixture
async def cli_tool_service(time_service):
    """Create CLI tool service instance."""
    service = CLIToolService(time_service=time_service)
    await service.start()
    yield service
    await service.stop()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for file operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_file(temp_dir):
    """Create a temporary file with content."""
    file_path = Path(temp_dir) / "test_file.txt"
    file_path.write_text("Line 1\nLine 2 with pattern\nLine 3\nLine 4 with pattern\n")
    return str(file_path)


class TestCLIToolServiceBasics:
    """Test basic service functionality."""

    @pytest.mark.asyncio
    async def test_service_initialization(self, time_service):
        """Test service initializes correctly."""
        service = CLIToolService(time_service=time_service)

        assert service._time_service == time_service
        assert service._tool_executions == 0
        assert service._tool_failures == 0
        assert len(service._tools) == 5
        assert "list_files" in service._tools
        assert "read_file" in service._tools
        assert "write_file" in service._tools
        assert "shell_command" in service._tools
        assert "search_text" in service._tools

    @pytest.mark.asyncio
    async def test_service_start_stop(self, cli_tool_service):
        """Test service start and stop."""
        assert cli_tool_service._started
        await cli_tool_service.stop()
        assert not cli_tool_service._started

    @pytest.mark.asyncio
    async def test_get_service_type(self, cli_tool_service):
        """Test getting service type."""
        assert cli_tool_service.get_service_type() == ServiceType.ADAPTER

    @pytest.mark.asyncio
    async def test_get_capabilities(self, cli_tool_service):
        """Test getting service capabilities."""
        capabilities = cli_tool_service.get_capabilities()

        assert isinstance(capabilities, ServiceCapabilities)
        assert capabilities.service_name == "CLIToolService"
        assert "execute_tool" in capabilities.actions
        assert capabilities.version == "1.0.0"
        # resource_limits is in the dict, but ServiceCapabilities doesn't have it as an attribute
        # Check via model_dump instead
        cap_dict = capabilities.model_dump()
        if "resource_limits" in cap_dict:
            assert cap_dict["resource_limits"]["max_concurrent_tools"] == 10

    @pytest.mark.asyncio
    async def test_is_healthy(self, cli_tool_service):
        """Test service health check."""
        assert await cli_tool_service.is_healthy() is True

    @pytest.mark.asyncio
    async def test_check_dependencies(self, cli_tool_service):
        """Test dependency checking."""
        assert cli_tool_service._check_dependencies() is True


class TestToolListing:
    """Test tool listing and discovery."""

    @pytest.mark.asyncio
    async def test_get_available_tools(self, cli_tool_service):
        """Test getting list of available tools."""
        tools = await cli_tool_service.get_available_tools()

        assert len(tools) == 5
        assert "list_files" in tools
        assert "read_file" in tools
        assert "write_file" in tools
        assert "shell_command" in tools
        assert "search_text" in tools

    @pytest.mark.asyncio
    async def test_list_tools(self, cli_tool_service):
        """Test list_tools method (ToolServiceProtocol)."""
        tools = await cli_tool_service.list_tools()

        assert len(tools) == 5
        assert all(tool in tools for tool in ["list_files", "read_file", "write_file", "shell_command", "search_text"])

    @pytest.mark.asyncio
    async def test_get_tool_schema(self, cli_tool_service):
        """Test getting tool parameter schemas."""
        # Test list_files schema
        schema = await cli_tool_service.get_tool_schema("list_files")
        assert schema is not None
        assert schema.type == "object"
        assert "path" in schema.properties
        assert len(schema.required) == 0

        # Test read_file schema
        schema = await cli_tool_service.get_tool_schema("read_file")
        assert schema is not None
        assert "path" in schema.properties
        assert "path" in schema.required

        # Test write_file schema
        schema = await cli_tool_service.get_tool_schema("write_file")
        assert schema is not None
        assert "path" in schema.properties
        assert "content" in schema.properties
        assert set(schema.required) == {"path", "content"}

        # Test non-existent tool
        schema = await cli_tool_service.get_tool_schema("non_existent")
        assert schema is None

    @pytest.mark.asyncio
    async def test_get_tool_info(self, cli_tool_service):
        """Test getting detailed tool information."""
        # Test list_files info
        info = await cli_tool_service.get_tool_info("list_files")
        assert isinstance(info, ToolInfo)
        assert info.name == "list_files"
        assert info.category == "filesystem"
        assert info.cost == 0.0
        assert "directory" in info.description.lower()

        # Test shell_command info
        info = await cli_tool_service.get_tool_info("shell_command")
        assert info.category == "system"
        assert "command" in info.description.lower()

        # Test non-existent tool
        info = await cli_tool_service.get_tool_info("non_existent")
        assert info is None

    @pytest.mark.asyncio
    async def test_get_all_tool_info(self, cli_tool_service):
        """Test getting info for all tools."""
        all_info = await cli_tool_service.get_all_tool_info()

        assert len(all_info) == 5
        assert all(isinstance(info, ToolInfo) for info in all_info)

        tool_names = {info.name for info in all_info}
        assert tool_names == {"list_files", "read_file", "write_file", "shell_command", "search_text"}


class TestListFilesTool:
    """Test list_files tool functionality."""

    @pytest.mark.asyncio
    async def test_list_files_success(self, cli_tool_service, temp_dir):
        """Test successful file listing."""
        # Create test files
        Path(temp_dir, "file1.txt").touch()
        Path(temp_dir, "file2.txt").touch()
        Path(temp_dir, "subdir").mkdir()

        params = {"path": temp_dir}
        result = await cli_tool_service._list_files(params)

        assert result["files"] == ["file1.txt", "file2.txt", "subdir"]
        assert result["path"] == temp_dir
        assert "error" not in result or result["error"] is None

    @pytest.mark.asyncio
    async def test_list_files_default_path(self, cli_tool_service):
        """Test listing files with default path."""
        params = {}
        result = await cli_tool_service._list_files(params)

        assert "files" in result
        assert result["path"] == "."

    @pytest.mark.asyncio
    async def test_list_files_nonexistent_path(self, cli_tool_service):
        """Test listing files from non-existent directory."""
        params = {"path": "/nonexistent/directory"}
        result = await cli_tool_service._list_files(params)

        assert result["files"] == []
        assert "error" in result
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_list_files_via_execute_tool(self, cli_tool_service, temp_dir):
        """Test list_files through execute_tool."""
        Path(temp_dir, "test.txt").touch()

        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                result = await cli_tool_service.execute_tool("list_files", {"path": temp_dir})

        assert result.tool_name == "list_files"
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert "test.txt" in result.data["files"]


class TestReadFileTool:
    """Test read_file tool functionality."""

    @pytest.mark.asyncio
    async def test_read_file_success(self, cli_tool_service, temp_file):
        """Test successful file reading."""
        params = {"path": temp_file}
        result = await cli_tool_service._read_file(params)

        assert "Line 1" in result["content"]
        assert "Line 2 with pattern" in result["content"]
        assert result["path"] == temp_file
        assert "error" not in result or result["error"] is None

    @pytest.mark.asyncio
    async def test_read_file_nonexistent(self, cli_tool_service):
        """Test reading non-existent file."""
        params = {"path": "/nonexistent/file.txt"}
        result = await cli_tool_service._read_file(params)

        assert "error" in result
        assert result["error"] is not None
        assert "content" not in result or result["content"] is None

    @pytest.mark.asyncio
    async def test_read_file_missing_path(self, cli_tool_service):
        """Test reading file without path parameter."""
        params = {}
        result = await cli_tool_service._read_file(params)

        assert "error" in result
        assert "path parameter required" in result["error"]

    @pytest.mark.asyncio
    async def test_read_file_via_execute_tool(self, cli_tool_service, temp_file):
        """Test read_file through execute_tool."""
        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                result = await cli_tool_service.execute_tool("read_file", {"path": temp_file})

        assert result.tool_name == "read_file"
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert "Line 1" in result.data["content"]


class TestWriteFileTool:
    """Test write_file tool functionality."""

    @pytest.mark.asyncio
    async def test_write_file_success(self, cli_tool_service, temp_dir):
        """Test successful file writing."""
        file_path = str(Path(temp_dir) / "new_file.txt")
        content = "Test content\nLine 2"

        params = {"path": file_path, "content": content}
        result = await cli_tool_service._write_file(params)

        assert result["status"] == "written"
        assert result["path"] == file_path
        assert "error" not in result or result["error"] is None

        # Verify file was written
        assert Path(file_path).exists()
        assert Path(file_path).read_text() == content

    @pytest.mark.asyncio
    async def test_write_file_overwrite(self, cli_tool_service, temp_file):
        """Test overwriting existing file."""
        new_content = "Overwritten content"

        params = {"path": temp_file, "content": new_content}
        result = await cli_tool_service._write_file(params)

        assert result["status"] == "written"
        assert Path(temp_file).read_text() == new_content

    @pytest.mark.asyncio
    async def test_write_file_missing_params(self, cli_tool_service):
        """Test writing file with missing parameters."""
        # Missing content
        params = {"path": "/tmp/file.txt"}
        result = await cli_tool_service._write_file(params)
        assert "error" in result

        # Missing path
        params = {"content": "test"}
        result = await cli_tool_service._write_file(params)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_write_file_invalid_path(self, cli_tool_service):
        """Test writing to invalid path."""
        params = {"path": "/invalid/path/file.txt", "content": "test"}
        result = await cli_tool_service._write_file(params)

        assert "error" in result
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_write_file_via_execute_tool(self, cli_tool_service, temp_dir):
        """Test write_file through execute_tool."""
        file_path = str(Path(temp_dir) / "exec_test.txt")

        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                result = await cli_tool_service.execute_tool(
                    "write_file", {"path": file_path, "content": "Test via execute"}
                )

        assert result.tool_name == "write_file"
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert Path(file_path).read_text() == "Test via execute"


class TestShellCommandTool:
    """Test shell_command tool functionality."""

    @pytest.mark.asyncio
    async def test_shell_command_success(self, cli_tool_service):
        """Test successful shell command execution."""
        params = {"command": "echo 'Hello World'"}
        result = await cli_tool_service._shell_command(params)

        assert "Hello World" in result["stdout"]
        assert result["stderr"] == ""
        assert result["returncode"] == 0
        assert "error" not in result or result["error"] is None

    @pytest.mark.asyncio
    async def test_shell_command_with_stderr(self, cli_tool_service):
        """Test command that writes to stderr."""
        params = {"command": "echo 'Error' >&2"}
        result = await cli_tool_service._shell_command(params)

        assert result["stdout"] == ""
        assert "Error" in result["stderr"]
        assert result["returncode"] == 0

    @pytest.mark.asyncio
    async def test_shell_command_failure(self, cli_tool_service):
        """Test failed shell command."""
        params = {"command": "exit 1"}
        result = await cli_tool_service._shell_command(params)

        assert result["returncode"] == 1

    @pytest.mark.asyncio
    async def test_shell_command_missing_param(self, cli_tool_service):
        """Test shell command without command parameter."""
        params = {}
        result = await cli_tool_service._shell_command(params)

        assert "error" in result
        assert "command parameter required" in result["error"]

    @pytest.mark.asyncio
    async def test_shell_command_via_execute_tool(self, cli_tool_service):
        """Test shell_command through execute_tool."""
        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                result = await cli_tool_service.execute_tool("shell_command", {"command": "echo 'Test'"})

        assert result.tool_name == "shell_command"
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert "Test" in result.data["stdout"]


class TestSearchTextTool:
    """Test search_text tool functionality."""

    @pytest.mark.asyncio
    async def test_search_text_success(self, cli_tool_service, temp_file):
        """Test successful text search."""
        params = {"path": temp_file, "pattern": "pattern"}
        result = await cli_tool_service._search_text(params)

        assert len(result["matches"]) == 2
        assert result["matches"][0]["line"] == 2
        assert "Line 2 with pattern" in result["matches"][0]["text"]
        assert result["matches"][1]["line"] == 4
        assert "error" not in result or result["error"] is None

    @pytest.mark.asyncio
    async def test_search_text_no_matches(self, cli_tool_service, temp_file):
        """Test search with no matches."""
        params = {"path": temp_file, "pattern": "nonexistent"}
        result = await cli_tool_service._search_text(params)

        assert len(result["matches"]) == 0
        assert "error" not in result or result["error"] is None

    @pytest.mark.asyncio
    async def test_search_text_missing_params(self, cli_tool_service):
        """Test search with missing parameters."""
        # Missing pattern
        params = {"path": "/tmp/file.txt"}
        result = await cli_tool_service._search_text(params)
        assert "error" in result

        # Missing path
        params = {"pattern": "test"}
        result = await cli_tool_service._search_text(params)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_text_nonexistent_file(self, cli_tool_service):
        """Test search in non-existent file."""
        params = {"path": "/nonexistent/file.txt", "pattern": "test"}
        result = await cli_tool_service._search_text(params)

        assert "error" in result
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_search_text_via_execute_tool(self, cli_tool_service, temp_file):
        """Test search_text through execute_tool."""
        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                result = await cli_tool_service.execute_tool("search_text", {"path": temp_file, "pattern": "Line"})

        assert result.tool_name == "search_text"
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert len(result.data["matches"]) == 4  # All lines contain "Line"


class TestToolExecution:
    """Test tool execution framework."""

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, cli_tool_service):
        """Test executing unknown tool."""
        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                result = await cli_tool_service.execute_tool("unknown_tool", {})

        assert result.tool_name == "unknown_tool"
        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_tool_with_exception(self, cli_tool_service):
        """Test tool execution with exception."""

        async def failing_tool(params):
            raise RuntimeError("Tool failed")

        cli_tool_service._tools["failing_tool"] = failing_tool

        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                result = await cli_tool_service.execute_tool("failing_tool", {})

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "Tool failed" in result.error
        assert cli_tool_service._tool_failures == 1

    @pytest.mark.asyncio
    async def test_execute_tool_correlation_tracking(self, cli_tool_service, temp_dir):
        """Test correlation tracking during tool execution."""
        correlation_id = str(uuid.uuid4())

        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add:
            with patch("ciris_engine.logic.persistence.update_correlation") as mock_update:
                result = await cli_tool_service.execute_tool(
                    "list_files", {"path": temp_dir, "correlation_id": correlation_id}
                )

        assert result.correlation_id == correlation_id

        # Check correlation was added
        mock_add.assert_called_once()
        corr = mock_add.call_args[0][0]
        assert isinstance(corr, ServiceCorrelation)
        assert corr.correlation_id == correlation_id
        assert corr.action_type == "list_files"

        # Check correlation was updated
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool_metrics_tracking(self, cli_tool_service, temp_dir):
        """Test metrics tracking during tool execution."""
        initial_executions = cli_tool_service._tool_executions

        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                await cli_tool_service.execute_tool("list_files", {"path": temp_dir})

        assert cli_tool_service._tool_executions == initial_executions + 1

    @pytest.mark.asyncio
    async def test_execute_tool_execution_time(self, cli_tool_service, temp_dir):
        """Test execution time tracking."""
        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                result = await cli_tool_service.execute_tool("list_files", {"path": temp_dir})

        assert "_execution_time_ms" in result.data
        assert result.data["_execution_time_ms"] >= 0


class TestToolResults:
    """Test tool result management."""

    @pytest.mark.asyncio
    async def test_get_tool_result_success(self, cli_tool_service, temp_dir):
        """Test retrieving tool result."""
        correlation_id = str(uuid.uuid4())

        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                exec_result = await cli_tool_service.execute_tool(
                    "list_files", {"path": temp_dir, "correlation_id": correlation_id}
                )

        # Result should be stored
        assert correlation_id in cli_tool_service._results

        # Retrieve result
        retrieved = await cli_tool_service.get_tool_result(correlation_id, timeout=1.0)

        assert retrieved is not None
        assert retrieved.correlation_id == correlation_id
        assert retrieved.tool_name == "list_files"

        # Result should be removed after retrieval
        assert correlation_id not in cli_tool_service._results

    @pytest.mark.asyncio
    async def test_get_tool_result_timeout(self, cli_tool_service):
        """Test tool result retrieval timeout."""
        non_existent_id = str(uuid.uuid4())

        result = await cli_tool_service.get_tool_result(non_existent_id, timeout=0.1)

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_parameters(self, cli_tool_service):
        """Test parameter validation."""
        # Valid tool
        assert await cli_tool_service.validate_parameters("list_files", {}) is True
        assert await cli_tool_service.validate_parameters("read_file", {"path": "/tmp/file"}) is True

        # Invalid tool
        assert await cli_tool_service.validate_parameters("unknown_tool", {}) is False


class TestServiceMetrics:
    """Test service metrics collection."""

    @pytest.mark.asyncio
    async def test_collect_custom_metrics(self, cli_tool_service):
        """Test custom metrics collection."""
        metrics = cli_tool_service._collect_custom_metrics()

        assert "tools_count" in metrics
        assert metrics["tools_count"] == 5.0
        assert "tool_executions_total" in metrics
        assert "tool_failures_total" in metrics
        assert "tool_success_rate" in metrics
        assert "results_cached" in metrics

    @pytest.mark.asyncio
    async def test_metrics_after_executions(self, cli_tool_service, temp_dir):
        """Test metrics after tool executions."""
        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                # Successful execution
                await cli_tool_service.execute_tool("list_files", {"path": temp_dir})

                # Failed execution (unknown_tool MUST increment failures)
                await cli_tool_service.execute_tool("unknown_tool", {})

        metrics = cli_tool_service._collect_custom_metrics()

        assert metrics["tool_executions_total"] == 2.0
        # unknown_tool MUST increment failures (we fixed this!)
        assert metrics["tool_failures_total"] == 1.0
        assert metrics["tool_success_rate"] == 0.5  # 2 executions, 1 failure

    @pytest.mark.asyncio
    async def test_get_actions(self, cli_tool_service):
        """Test getting service actions."""
        actions = cli_tool_service._get_actions()

        assert "execute_tool" in actions
        assert "get_available_tools" in actions
        assert "get_tool_result" in actions
        assert "validate_parameters" in actions
        assert "get_tool_info" in actions
        assert "get_all_tool_info" in actions


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_result_handling(self, cli_tool_service):
        """Test handling of None/empty results."""

        async def empty_tool(params):
            return None

        cli_tool_service._tools["empty_tool"] = empty_tool

        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                result = await cli_tool_service.execute_tool("empty_tool", {})

        assert result.data is not None
        assert "_execution_time_ms" in result.data

    @pytest.mark.asyncio
    async def test_sync_file_operations(self, cli_tool_service, temp_dir):
        """Test synchronous file operation helpers."""
        # Test _write_file_sync
        file_path = str(Path(temp_dir) / "sync_test.txt")
        cli_tool_service._write_file_sync(file_path, "Sync content")
        assert Path(file_path).read_text() == "Sync content"

        # Test _read_lines_sync
        lines = cli_tool_service._read_lines_sync(file_path)
        assert lines == ["Sync content"]

    @pytest.mark.asyncio
    async def test_concurrent_tool_executions(self, cli_tool_service, temp_dir):
        """Test concurrent tool executions."""
        with patch("ciris_engine.logic.persistence.add_correlation"):
            with patch("ciris_engine.logic.persistence.update_correlation"):
                # Execute multiple tools concurrently
                tasks = [
                    cli_tool_service.execute_tool("list_files", {"path": temp_dir}),
                    cli_tool_service.execute_tool("list_files", {"path": "."}),
                    cli_tool_service.execute_tool("shell_command", {"command": "echo test"}),
                ]

                results = await asyncio.gather(*tasks)

        assert all(r.status == ToolExecutionStatus.COMPLETED for r in results)
        assert cli_tool_service._tool_executions == 3

    @pytest.mark.asyncio
    async def test_parameter_validation_errors(self, cli_tool_service):
        """Test Pydantic validation errors in tools."""
        # Invalid parameter type - Pydantic will raise ValidationError
        params = {"path": 123}  # Should be string

        # The function will raise ValidationError since it can't coerce int to path string
        with pytest.raises(ValidationError):
            await cli_tool_service._list_files(params)

    @pytest.mark.asyncio
    async def test_tool_info_completeness(self, cli_tool_service):
        """Test that all tool info is complete."""
        for tool_name in await cli_tool_service.get_available_tools():
            info = await cli_tool_service.get_tool_info(tool_name)
            assert info is not None
            assert info.name == tool_name
            assert info.description
            assert info.category in ["filesystem", "system"]
            assert info.parameters is not None
            assert info.when_to_use is not None
