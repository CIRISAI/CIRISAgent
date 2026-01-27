"""
AppleReminders Tool Service for CIRIS.

Converted from Clawdbot skill: apple-reminders
Manage Apple Reminders via the `remindctl` CLI on macOS (list, add, edit, complete, delete). Supports lists, date filters, and JSON/plain output.

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


class AppleRemindersToolService:
    """
    AppleReminders tool service providing skill-based guidance.

    Original skill: apple-reminders
    Description: Manage Apple Reminders via the `remindctl` CLI on macOS (list, add, edit, complete, delete). Supports lists, date filters, and JSON/plain output.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("AppleRemindersToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("AppleRemindersToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("AppleRemindersToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="apple_reminders",
            description="""Manage Apple Reminders via the `remindctl` CLI on macOS (list, add, edit, complete, delete). Supports lists, date filters, and JSON/plain output.""",
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
            when_to_use="""When you need to manage apple reminders via the `remindctl` cli on macos (list, add, edit, complete, delete). support...""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="remindctl"),
                ],
                platforms=["darwin"],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install remindctl via Homebrew",
                    formula="steipete/tap/remindctl",
                    provides_binaries=["remindctl"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Use `remindctl` to manage Apple Reminders directly from the terminal. It supports list filtering, date-based views, and scripting output.",
                detailed_instructions="""# Apple Reminders CLI (remindctl)\n\nUse `remindctl` to manage Apple Reminders directly from the terminal. It supports list filtering, date-based views, and scripting output.\n\nSetup\n- Install (Homebrew): `brew install steipete/tap/remindctl`\n- From source: `pnpm install && pnpm build` (binary at `./bin/remindctl`)\n- macOS-only; grant Reminders permission when prompted.\n\nPermissions\n- Check status: `remindctl status`\n- Request access: `remindctl authorize`\n\nView Reminders\n- Default (today): `remindctl`\n- Today: `remindctl today`\n- Tomorrow: `remindctl tomorrow`\n- Week: `remindctl week`\n- Overdue: `remindctl overdue`\n- Upcoming: `remindctl upcoming`\n- Completed: `remindctl completed`\n- All: `remindctl all`\n- Specific date: `remindctl 2026-01-04`\n\nManage Lists\n- List all lists: `remindctl list`\n- Show list: `remindctl list Work`\n- Create list: `remindctl list Projects --create`\n- Rename list: `remindctl list Work --rename Office`\n- Delete list: `remindctl list Work --delete`\n\nCreate Reminders\n- Quick add: `remindctl add \"Buy milk\"`\n- With list + due: `remindctl add --title \"Call mom\" --list Personal --due tomorrow`\n\nEdit Reminders\n- Edit title/due: `remindctl edit 1 --title \"New title\" --due 2026-01-04`\n\nComplete Reminders\n- Complete by id: `remindctl complete 1 2 3`\n\nDelete Reminders\n- Delete by id: `remindctl delete 4A83 --force`\n\nOutput Formats\n- JSON (scripting): `remindctl today --json`\n- Plain TSV: `remindctl today --plain`\n- Counts only: `remindctl today --quiet`\n\nDate Formats\nAccepted by `--due` and date filters:\n- `today`, `tomorrow`, `yesterday`\n- `YYYY-MM-DD`\n- `YYYY-MM-DD HH:mm`\n- ISO 8601 (`2026-01-04T12:34:56Z`)\n\nNotes\n- macOS-only.\n- If access is denied, enable Terminal/remindctl in System Settings → Privacy & Security → Reminders.\n- If running over SSH, grant access on the Mac that runs the command.""",
                examples=[],
                gotchas=[],
                homepage="https://github.com/steipete/remindctl",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "apple_reminders", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["apple_reminders"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "apple_reminders":
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
        if tool_name != "apple_reminders":
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

        if tool_name != "apple_reminders":
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
        binaries = ["'remindctl'"]
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
