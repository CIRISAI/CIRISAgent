"""
Comprehensive test suite for CLIToolService to improve coverage.

Tests all methods and edge cases in ciris_engine/logic/adapters/cli/cli_tools.py
"""

import asyncio
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.cli.cli_tools import CLIToolService
from ciris_engine.schemas.adapters.tools import ToolExecutionStatus
from ciris_engine.schemas.runtime.enums import ServiceType


# Mock persistence module to avoid database dependencies
@pytest.fixture(autouse=True)
def mock_persistence():
    """Mock persistence module to avoid database issues."""
    with patch('ciris_engine.logic.adapters.cli.cli_tools.persistence') as mock_persist:
        mock_persist.add_correlation = MagicMock()
        mock_persist.update_correlation = MagicMock()
        yield mock_persist


@pytest.fixture
async def time_service():
    """Create mock time service."""
    mock_time = MagicMock()
    mock_time.timestamp.return_value = 1234567890.0
    mock_time.now.return_value = datetime.now(timezone.utc)
    return mock_time


@pytest.fixture
async def cli_tool_service(time_service):
    """Create CLIToolService instance."""
    service = CLIToolService(time_service=time_service)
    await service.start()
    yield service
    await service.stop()


class TestCLIToolServiceLifecycle:
    """Test service lifecycle methods."""

    @pytest.mark.asyncio
    async def test_service_initialization(self, time_service):
        """Test service initialization."""
        service = CLIToolService(time_service=time_service)
        
        assert service._time_service == time_service
        assert service.service_name == "CLIToolService"
        assert len(service._tools) == 5  # 5 built-in tools
        assert service._tool_executions == 0
        assert service._tool_failures == 0

    @pytest.mark.asyncio
    async def test_service_start_stop(self, time_service):
        """Test service start and stop."""
        service = CLIToolService(time_service=time_service)
        
        # Start service
        await service.start()
        assert service._started is True
        
        # Stop service
        await service.stop()
        assert service._started is False

    @pytest.mark.asyncio
    async def test_service_type(self, cli_tool_service):
        """Test service type."""
        assert cli_tool_service.get_service_type() == ServiceType.ADAPTER

    @pytest.mark.asyncio
    async def test_service_capabilities(self, cli_tool_service):
        """Test service capabilities."""
        caps = cli_tool_service.get_capabilities()
        
        assert caps.service_name == "CLIToolService"
        assert "execute_tool" in caps.actions
        assert caps.version == "1.0.0"
        assert caps.metadata is not None
        assert caps.metadata.get("resource_limits", {}).get("max_concurrent_tools") == 10

    @pytest.mark.asyncio
    async def test_service_health(self, cli_tool_service):
        """Test service health check."""
        assert await cli_tool_service.is_healthy() is True

    @pytest.mark.asyncio
    async def test_check_dependencies(self, cli_tool_service):
        """Test dependency checking."""
        assert cli_tool_service._check_dependencies() is True


class TestToolExecution:
    """Test tool execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, cli_tool_service):
        """Test executing unknown tool."""
        result = await cli_tool_service.execute_tool("unknown_tool", {})
        
        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "Unknown tool" in result.error
        assert cli_tool_service._tool_executions == 1

    @pytest.mark.asyncio
    async def test_execute_tool_with_correlation_id(self, cli_tool_service):
        """Test tool execution with correlation ID."""
        correlation_id = str(uuid.uuid4())
        
        result = await cli_tool_service.execute_tool(
            "list_files",
            {"path": ".", "correlation_id": correlation_id}
        )
        
        assert result.correlation_id == correlation_id
        assert correlation_id in cli_tool_service._results

    @pytest.mark.asyncio
    async def test_execute_tool_exception_handling(self, cli_tool_service):
        """Test tool execution with exception."""
        # Mock a tool to raise exception
        async def failing_tool(params):
            raise ValueError("Test error")
        
        cli_tool_service._tools["test_fail"] = failing_tool
        
        result = await cli_tool_service.execute_tool("test_fail", {})
        
        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "Test error" in result.error
        assert cli_tool_service._tool_failures == 1

    @pytest.mark.asyncio
    async def test_execution_time_tracking(self, cli_tool_service):
        """Test execution time is tracked."""
        result = await cli_tool_service.execute_tool("list_files", {"path": "."})
        
        assert "_execution_time_ms" in result.data
        assert result.data["_execution_time_ms"] >= 0  # Can be 0 if very fast


class TestListFilesTool:
    """Test list_files tool functionality."""

    @pytest.mark.asyncio
    async def test_list_files_success(self, cli_tool_service):
        """Test successful file listing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            Path(tmpdir, "file1.txt").touch()
            Path(tmpdir, "file2.txt").touch()
            Path(tmpdir, "subdir").mkdir()
            
            result = await cli_tool_service.execute_tool("list_files", {"path": tmpdir})
            
            assert result.success is True
            assert "file1.txt" in result.data["files"]
            assert "file2.txt" in result.data["files"]
            assert "subdir" in result.data["files"]
            assert result.data["files"] == sorted(result.data["files"])  # Check sorting

    @pytest.mark.asyncio
    async def test_list_files_invalid_path(self, cli_tool_service):
        """Test list_files with invalid path."""
        result = await cli_tool_service.execute_tool(
            "list_files", 
            {"path": "/nonexistent/path/that/does/not/exist"}
        )
        
        assert result.success is False
        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_list_files_default_path(self, cli_tool_service):
        """Test list_files with default path."""
        result = await cli_tool_service.execute_tool("list_files", {})
        
        # Should use default path "."
        assert "path" in result.data


class TestReadFileTool:
    """Test read_file tool functionality."""

    @pytest.mark.asyncio
    async def test_read_file_success(self, cli_tool_service):
        """Test successful file reading."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test content\nLine 2")
            f.flush()
            
            try:
                result = await cli_tool_service.execute_tool("read_file", {"path": f.name})
                
                assert result.success is True
                assert result.data["content"] == "Test content\nLine 2"
                assert result.data["path"] == f.name
            finally:
                os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_read_file_missing_path(self, cli_tool_service):
        """Test read_file without path parameter."""
        result = await cli_tool_service.execute_tool("read_file", {})
        
        assert result.success is False
        assert "path parameter required" in result.data["error"]

    @pytest.mark.asyncio
    async def test_read_file_nonexistent(self, cli_tool_service):
        """Test read_file with nonexistent file."""
        result = await cli_tool_service.execute_tool(
            "read_file", 
            {"path": "/nonexistent/file.txt"}
        )
        
        assert result.success is False
        assert "error" in result.data


class TestWriteFileTool:
    """Test write_file tool functionality."""

    @pytest.mark.asyncio
    async def test_write_file_success(self, cli_tool_service):
        """Test successful file writing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            test_path = f.name
        
        try:
            result = await cli_tool_service.execute_tool(
                "write_file",
                {"path": test_path, "content": "New content"}
            )
            
            assert result.success is True
            assert result.data["status"] == "written"
            assert result.data["path"] == test_path
            
            # Verify content was written
            with open(test_path, 'r') as f:
                assert f.read() == "New content"
        finally:
            os.unlink(test_path)

    @pytest.mark.asyncio
    async def test_write_file_missing_params(self, cli_tool_service):
        """Test write_file with missing parameters."""
        # Missing 'path' parameter (required)
        result = await cli_tool_service.execute_tool("write_file", {"content": "test content"})
        
        # The validation error will be in result.error, not result.data
        assert result.success is False
        assert result.error is not None or "error" in result.data

    @pytest.mark.asyncio
    async def test_write_file_permission_error(self, cli_tool_service):
        """Test write_file with permission error."""
        result = await cli_tool_service.execute_tool(
            "write_file",
            {"path": "/root/protected.txt", "content": "test"}
        )
        
        assert result.success is False
        assert "error" in result.data


class TestShellCommandTool:
    """Test shell_command tool functionality."""

    @pytest.mark.asyncio
    async def test_shell_command_success(self, cli_tool_service):
        """Test successful shell command execution."""
        result = await cli_tool_service.execute_tool(
            "shell_command",
            {"command": "echo 'Hello World'"}
        )
        
        assert result.success is True
        assert "Hello World" in result.data["stdout"]
        assert result.data["returncode"] == 0

    @pytest.mark.asyncio
    async def test_shell_command_with_error(self, cli_tool_service):
        """Test shell command with stderr output."""
        result = await cli_tool_service.execute_tool(
            "shell_command",
            {"command": "ls /nonexistent 2>&1"}
        )
        
        assert result.data["returncode"] != 0

    @pytest.mark.asyncio
    async def test_shell_command_missing_param(self, cli_tool_service):
        """Test shell_command without command parameter."""
        result = await cli_tool_service.execute_tool("shell_command", {})
        
        assert result.success is False
        assert "command parameter required" in result.data["error"]


class TestSearchTextTool:
    """Test search_text tool functionality."""

    @pytest.mark.asyncio
    async def test_search_text_success(self, cli_tool_service):
        """Test successful text search."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Line 1: Hello\n")
            f.write("Line 2: World\n")
            f.write("Line 3: Hello World\n")
            f.flush()
            
            try:
                result = await cli_tool_service.execute_tool(
                    "search_text",
                    {"path": f.name, "pattern": "Hello"}
                )
                
                assert result.success is True
                assert len(result.data["matches"]) == 2
                assert result.data["matches"][0]["line"] == 1
                assert result.data["matches"][1]["line"] == 3
            finally:
                os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_search_text_no_matches(self, cli_tool_service):
        """Test search with no matches."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Line 1\nLine 2\n")
            f.flush()
            
            try:
                result = await cli_tool_service.execute_tool(
                    "search_text",
                    {"path": f.name, "pattern": "NotFound"}
                )
                
                assert result.success is True
                assert len(result.data["matches"]) == 0
            finally:
                os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_search_text_missing_params(self, cli_tool_service):
        """Test search_text with missing parameters."""
        result = await cli_tool_service.execute_tool("search_text", {"path": "/tmp/file.txt"})
        
        assert result.success is False
        assert "pattern and path required" in result.data["error"]


class TestToolManagement:
    """Test tool management methods."""

    @pytest.mark.asyncio
    async def test_get_available_tools(self, cli_tool_service):
        """Test getting available tools."""
        tools = await cli_tool_service.get_available_tools()
        
        assert "list_files" in tools
        assert "read_file" in tools
        assert "write_file" in tools
        assert "shell_command" in tools
        assert "search_text" in tools

    @pytest.mark.asyncio
    async def test_list_tools(self, cli_tool_service):
        """Test listing tools (protocol method)."""
        tools = await cli_tool_service.list_tools()
        
        assert len(tools) == 5
        assert "list_files" in tools

    @pytest.mark.asyncio
    async def test_validate_parameters(self, cli_tool_service):
        """Test parameter validation."""
        # Valid tool
        assert await cli_tool_service.validate_parameters("list_files", {}) is True
        
        # Invalid tool
        assert await cli_tool_service.validate_parameters("invalid_tool", {}) is False

    @pytest.mark.asyncio
    async def test_get_tool_result_found(self, cli_tool_service):
        """Test getting tool result by correlation ID."""
        correlation_id = str(uuid.uuid4())
        
        # Execute tool with correlation ID
        await cli_tool_service.execute_tool(
            "list_files",
            {"path": ".", "correlation_id": correlation_id}
        )
        
        # Get result
        result = await cli_tool_service.get_tool_result(correlation_id, timeout=1.0)
        
        assert result is not None
        assert result.correlation_id == correlation_id

    @pytest.mark.asyncio
    async def test_get_tool_result_timeout(self, cli_tool_service):
        """Test get_tool_result with timeout."""
        result = await cli_tool_service.get_tool_result("nonexistent_id", timeout=0.1)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_tool_schema(self, cli_tool_service):
        """Test getting tool schema."""
        schema = await cli_tool_service.get_tool_schema("list_files")
        
        assert schema is not None
        assert schema.type == "object"
        assert "path" in schema.properties
        
        # Test unknown tool
        schema = await cli_tool_service.get_tool_schema("unknown")
        assert schema is None

    @pytest.mark.asyncio
    async def test_get_tool_info(self, cli_tool_service):
        """Test getting tool info."""
        info = await cli_tool_service.get_tool_info("read_file")
        
        assert info is not None
        assert info.name == "read_file"
        assert info.category == "filesystem"
        assert info.cost == 0.0
        
        # Test unknown tool
        info = await cli_tool_service.get_tool_info("unknown")
        assert info is None

    @pytest.mark.asyncio
    async def test_get_all_tool_info(self, cli_tool_service):
        """Test getting info for all tools."""
        all_info = await cli_tool_service.get_all_tool_info()
        
        assert len(all_info) == 5
        tool_names = [info.name for info in all_info]
        assert "list_files" in tool_names
        assert "read_file" in tool_names


class TestMetricsCollection:
    """Test metrics collection."""

    @pytest.mark.asyncio
    async def test_collect_custom_metrics(self, time_service):
        """Test custom metrics collection."""
        # Create fresh instance to ensure clean state
        service = CLIToolService(time_service=time_service)
        await service.start()
        
        # Execute some tools to generate metrics
        await service.execute_tool("list_files", {"path": "."})
        await service.execute_tool("unknown_tool", {})
        
        metrics = service._collect_custom_metrics()
        
        assert metrics["tools_count"] == 5.0
        assert metrics["tool_executions_total"] == 2.0  # Exactly 2 since fresh instance
        assert metrics["tool_failures_total"] == 1.0  # Exactly 1 failure
        assert metrics["tool_success_rate"] == 0.5  # 1 success / 2 total
        assert "results_cached" in metrics
        
        await service.stop()


class TestServiceActions:
    """Test service actions."""

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
    async def test_execute_tool_with_none_result(self, cli_tool_service):
        """Test handling of None result from tool."""
        async def none_tool(params):
            return None
        
        cli_tool_service._tools["none_tool"] = none_tool
        
        result = await cli_tool_service.execute_tool("none_tool", {})
        
        # Should handle None gracefully
        assert "_execution_time_ms" in result.data

    @pytest.mark.asyncio
    async def test_execute_tool_with_non_dict_result(self, cli_tool_service):
        """Test handling of non-dict result from tool."""
        async def string_tool(params):
            return "string result"
        
        cli_tool_service._tools["string_tool"] = string_tool
        
        result = await cli_tool_service.execute_tool("string_tool", {})
        
        # Non-dict results are wrapped in a dict with "result" key
        assert result.data["result"] == "string result"
        assert "_execution_time_ms" in result.data
        assert result.success is True

    @pytest.mark.asyncio
    async def test_write_file_sync_method(self, cli_tool_service):
        """Test the synchronous write file helper."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            test_path = f.name
        
        try:
            cli_tool_service._write_file_sync(test_path, "Test content")
            
            with open(test_path, 'r') as f:
                assert f.read() == "Test content"
        finally:
            os.unlink(test_path)

    @pytest.mark.asyncio
    async def test_read_lines_sync_method(self, cli_tool_service):
        """Test the synchronous read lines helper."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3\n")
            f.flush()
            
            try:
                lines = cli_tool_service._read_lines_sync(f.name)
                assert len(lines) == 3
                assert lines[0] == "Line 1\n"
            finally:
                os.unlink(f.name)