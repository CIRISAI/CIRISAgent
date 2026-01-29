"""Tests for SkillToolService base class."""

import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List

from ciris_adapters.skill_base import SkillToolService
from ciris_engine.schemas.adapters.tools import (
    ToolInfo,
    ToolParameterSchema,
    ToolRequirements,
    BinaryRequirement,
    ConfigRequirement,
    ToolExecutionStatus,
)

class MockSkillTool(SkillToolService):
    """Mock implementation of SkillToolService for testing."""

    def _build_tool_info(self) -> ToolInfo:
        return ToolInfo(
            name="mock_tool",
            description="A mock tool for testing",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "command": {"type": "string"},
                },
                required=["command"],
            ),
            requirements=ToolRequirements(
                binaries=[BinaryRequirement(name="ls")],
                config_keys=[ConfigRequirement(key="mock.token")],
            ),
        )

@pytest.mark.asyncio
async def test_skill_service_initialization():
    """Test service initialization."""
    service = MockSkillTool(config={"mock": {"token": "123"}})
    assert service.config["mock"]["token"] == "123"

@pytest.mark.asyncio
async def test_check_requirements_success():
    """Test requirement checking when all requirements are met."""
    service = MockSkillTool(config={"mock": {"token": "123"}})

    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/bin/ls"

        info = service._build_tool_info()
        met, missing = service._check_requirements(info)

        assert met is True
        assert len(missing) == 0

@pytest.mark.asyncio
async def test_check_requirements_missing_binary():
    """Test requirement checking when binary is missing."""
    service = MockSkillTool(config={"mock": {"token": "123"}})

    with patch("shutil.which") as mock_which:
        mock_which.return_value = None

        info = service._build_tool_info()
        met, missing = service._check_requirements(info)

        assert met is False
        assert "binary:ls" in missing

@pytest.mark.asyncio
async def test_check_requirements_missing_config():
    """Test requirement checking when config key is missing."""
    service = MockSkillTool(config={})  # Empty config

    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/bin/ls"

        info = service._build_tool_info()
        met, missing = service._check_requirements(info)

        assert met is False
        assert "config:mock.token" in missing

@pytest.mark.asyncio
async def test_execute_tool_success():
    """Test successful tool execution returning guidance."""
    service = MockSkillTool(config={"mock": {"token": "123"}})

    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/bin/ls"

        result = await service.execute_tool(
            tool_name="mock_tool",
            parameters={"command": "ls -la"}
        )

        assert result.success is True
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.data["command"] == "ls -la"
        assert result.data["guidance"] == "Use bash tool to execute this command"
        assert result.data["requirements_met"] is True

@pytest.mark.asyncio
async def test_execute_tool_missing_requirements():
    """Test execution failure due to missing requirements."""
    service = MockSkillTool(config={})  # Missing config

    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/bin/ls"

        result = await service.execute_tool(
            tool_name="mock_tool",
            parameters={"command": "ls -la"}
        )

        assert result.success is False
        assert result.status == ToolExecutionStatus.FAILED
        assert "Missing requirements" in result.error
        assert "config:mock.token" in result.data["missing_requirements"]
