"""
Mcporter Tool Service for CIRIS.

Converted from Clawdbot skill: mcporter
Use the mcporter CLI to list, configure, auth, and call MCP servers/tools directly (HTTP or stdio), including ad-hoc servers, config edits, and CLI/type generation.

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


class McporterToolService:
    """
    Mcporter tool service providing skill-based guidance.

    Original skill: mcporter
    Description: Use the mcporter CLI to list, configure, auth, and call MCP servers/tools directly (HTTP or stdio), including ad-hoc servers, config edits, and CLI/type generation.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("McporterToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("McporterToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("McporterToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="mcporter",
            description="""Use the mcporter CLI to list, configure, auth, and call MCP servers/tools directly (HTTP or stdio), including ad-hoc servers, config edits, and CLI/type generation.""",
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
            when_to_use="""When you need to use the mcporter cli to list, configure, auth, and call mcp servers/tools directly (http or stdio), ...""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="mcporter"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="node",
                    kind="node",
                    label="Install mcporter (node)",
                    package="mcporter",
                    provides_binaries=["mcporter"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Use `mcporter` to work with MCP servers directly.",
                detailed_instructions="""# mcporter\n\nUse `mcporter` to work with MCP servers directly.\n\nQuick start\n- `mcporter list`\n- `mcporter list <server> --schema`\n- `mcporter call <server.tool> key=value`\n\nCall tools\n- Selector: `mcporter call linear.list_issues team=ENG limit:5`\n- Function syntax: `mcporter call \"linear.create_issue(title: \\\"Bug\\\")\"`\n- Full URL: `mcporter call https://api.example.com/mcp.fetch url:https://example.com`\n- Stdio: `mcporter call --stdio \"bun run ./server.ts\" scrape url=https://example.com`\n- JSON payload: `mcporter call <server.tool> --args '{\"limit\":5}'`\n\nAuth + config\n- OAuth: `mcporter auth <server | url> [--reset]`\n- Config: `mcporter config list|get|add|remove|import|login|logout`\n\nDaemon\n- `mcporter daemon start|status|stop|restart`\n\nCodegen\n- CLI: `mcporter generate-cli --server <name>` or `--command <url>`\n- Inspect: `mcporter inspect-cli <path> [--json]`\n- TS: `mcporter emit-ts <server> --mode client|types`\n\nNotes\n- Config default: `./config/mcporter.json` (override with `--config`).\n- Prefer `--output json` for machine-readable results.""",
                examples=[],
                gotchas=[],
                homepage="http://mcporter.dev",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "mcporter", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["mcporter"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "mcporter":
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
        if tool_name != "mcporter":
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

        if tool_name != "mcporter":
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
        binaries = ["'mcporter'"]
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
