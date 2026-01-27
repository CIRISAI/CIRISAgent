"""
Blogwatcher Tool Service for CIRIS.

Converted from Clawdbot skill: blogwatcher
Monitor blogs and RSS/Atom feeds for updates using the blogwatcher CLI.

This service provides skill-based guidance for using external tools/CLIs.
The detailed instructions from the original SKILL.md are embedded in the
ToolInfo.documentation field for DMA-aware tool selection.
"""

import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ciris_engine.schemas.adapters.tools import (
    BinaryRequirement,
    ConfigRequirement,
    EnvVarRequirement,
    InstallStep,
    ToolDMAGuidance,
    ToolDocumentation,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolGotcha,
    ToolInfo,
    ToolParameterSchema,
    ToolRequirements,
    UsageExample,
)

logger = logging.getLogger(__name__)


class BlogwatcherToolService:
    """
    Blogwatcher tool service providing skill-based guidance.

    Original skill: blogwatcher
    Description: Monitor blogs and RSS/Atom feeds for updates using the blogwatcher CLI.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("BlogwatcherToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("BlogwatcherToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("BlogwatcherToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="blogwatcher",
            description="""Monitor blogs and RSS/Atom feeds for updates using the blogwatcher CLI.""",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "command": {
                        "type": "string",
                        "description": "The command to execute (will be validated against skill guidance)",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory for command execution (optional)",
                    },
                },
                required=["command"],
            ),
            category="skill",
            when_to_use="""When you need to monitor blogs and rss/atom feeds for updates using the blogwatcher cli.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="blogwatcher"),
                ],
            ),
            install_steps=[
                InstallStep(id="go", kind="go", label="Install blogwatcher (go)", provides_binaries=["blogwatcher"]),
            ],
            documentation=ToolDocumentation(
                quick_start="Track blog and RSS/Atom feed updates with the `blogwatcher` CLI.",
                detailed_instructions="""# blogwatcher\n\nTrack blog and RSS/Atom feed updates with the `blogwatcher` CLI.\n\nInstall\n- Go: `go install github.com/Hyaxia/blogwatcher/cmd/blogwatcher@latest`\n\nQuick start\n- `blogwatcher --help`\n\nCommon commands\n- Add a blog: `blogwatcher add \"My Blog\" https://example.com`\n- List blogs: `blogwatcher blogs`\n- Scan for updates: `blogwatcher scan`\n- List articles: `blogwatcher articles`\n- Mark an article read: `blogwatcher read 1`\n- Mark all articles read: `blogwatcher read-all`\n- Remove a blog: `blogwatcher remove \"My Blog\"`\n\nExample output\n```\n$ blogwatcher blogs\nTracked blogs (1):\n\n  xkcd\n    URL: https://xkcd.com\n```\n```\n$ blogwatcher scan\nScanning 1 blog(s)...\n\n  xkcd\n    Source: RSS | Found: 4 | New: 4\n\nFound 4 new article(s) total!\n```\n\nNotes\n- Use `blogwatcher <command> --help` to discover flags and options.""",
                examples=[],
                gotchas=[],
                homepage="https://github.com/Hyaxia/blogwatcher",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "blogwatcher", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["blogwatcher"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "blogwatcher":
            return self._build_tool_info()
        return None

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get info for all tools."""
        return [self._build_tool_info()]

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a tool."""
        tool_info = await self.get_tool_info(tool_name)
        return tool_info.parameters if tool_info else None

    async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate parameters for a tool."""
        if tool_name != "blogwatcher":
            return False
        return "command" in parameters

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of previously executed tool."""
        return None

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of available tools (legacy format)."""
        tool_info = self._build_tool_info()
        return [
            {
                "name": tool_info.name,
                "description": tool_info.description,
                "parameters": tool_info.parameters.model_dump() if tool_info.parameters else {},
            }
        ]

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """Execute the skill-based tool.

        Note: This is a guidance tool - it provides instructions for using
        external CLIs rather than executing them directly. The agent should
        use the bash tool to execute the actual commands.
        """
        self._call_count += 1
        correlation_id = str(uuid4())

        if tool_name != "blogwatcher":
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}",
                correlation_id=correlation_id,
            )

        try:
            command = parameters.get("command", "")

            # Check requirements
            requirements_met, missing = self._check_requirements()
            if not requirements_met:
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data={"missing_requirements": missing},
                    error=f"Missing requirements: {', '.join(missing)}",
                    correlation_id=correlation_id,
                )

            # Return guidance for executing the command
            tool_info = self._build_tool_info()
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={
                    "command": command,
                    "guidance": "Use bash tool to execute this command",
                    "skill_instructions": tool_info.documentation.quick_start if tool_info.documentation else None,
                    "requirements_met": requirements_met,
                },
                error=None,
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    def _check_requirements(self) -> tuple[bool, List[str]]:
        """Check if all requirements are met."""
        missing = []

        # Check binaries
        binaries = ["'blogwatcher'"]
        for binary in binaries:
            if not shutil.which(binary):
                missing.append(f"binary:{binary}")

        # Check any_binaries (at least one)
        any_binaries = []
        if any_binaries:
            found = any(shutil.which(b) for b in any_binaries)
            if not found:
                missing.append(f"any_binary:{','.join(any_binaries)}")

        # Check env vars
        env_vars = []
        for env_var in env_vars:
            if not os.environ.get(env_var):
                missing.append(f"env:{env_var}")

        return len(missing) == 0, missing
