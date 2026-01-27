"""
ThingsMac Tool Service for CIRIS.

Converted from Clawdbot skill: things-mac
Manage Things 3 via the `things` CLI on macOS (add/update projects+todos via URL scheme; read/search/list from the local Things database). Use when a user asks Moltbot to add a task to Things, list inbox/today/upcoming, search tasks, or inspect projects/areas/tags.

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


class ThingsMacToolService:
    """
    ThingsMac tool service providing skill-based guidance.

    Original skill: things-mac
    Description: Manage Things 3 via the `things` CLI on macOS (add/update projects+todos via URL scheme; read/search/list from the local Things database). Use when a user asks Moltbot to add a task to Things, list inbox/today/upcoming, search tasks, or inspect projects/areas/tags.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("ThingsMacToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("ThingsMacToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("ThingsMacToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="things_mac",
            description="""Manage Things 3 via the `things` CLI on macOS (add/update projects+todos via URL scheme; read/search/list from the local Things database). Use when a user asks Moltbot to add a task to Things, list inbox/today/upcoming, search tasks, or inspect projects/areas/tags.""",
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
            when_to_use="""When you need to manage things 3 via the `things` cli on macos (add/update projects+todos via url scheme; read/search...""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="things"),
                ],
                platforms=["darwin"],
            ),
            install_steps=[
                InstallStep(id="go", kind="go", label="Install things3-cli (go)", provides_binaries=["things"]),
            ],
            documentation=ToolDocumentation(
                quick_start="Use `things` to read your local Things database (inbox/today/search/projects/areas/tags) and to add/update todos via the Things URL scheme.",
                detailed_instructions="""# Things 3 CLI\n\nUse `things` to read your local Things database (inbox/today/search/projects/areas/tags) and to add/update todos via the Things URL scheme.\n\nSetup\n- Install (recommended, Apple Silicon): `GOBIN=/opt/homebrew/bin go install github.com/ossianhempel/things3-cli/cmd/things@latest`\n- If DB reads fail: grant **Full Disk Access** to the calling app (Terminal for manual runs; `Moltbot.app` for gateway runs).\n- Optional: set `THINGSDB` (or pass `--db`) to point at your `ThingsData-*` folder.\n- Optional: set `THINGS_AUTH_TOKEN` to avoid passing `--auth-token` for update ops.\n\nRead-only (DB)\n- `things inbox --limit 50`\n- `things today`\n- `things upcoming`\n- `things search \"query\"`\n- `things projects` / `things areas` / `things tags`\n\nWrite (URL scheme)\n- Prefer safe preview: `things --dry-run add \"Title\"`\n- Add: `things add \"Title\" --notes \"...\" --when today --deadline 2026-01-02`\n- Bring Things to front: `things --foreground add \"Title\"`\n\nExamples: add a todo\n- Basic: `things add \"Buy milk\"`\n- With notes: `things add \"Buy milk\" --notes \"2% + bananas\"`\n- Into a project/area: `things add \"Book flights\" --list \"Travel\"`\n- Into a project heading: `things add \"Pack charger\" --list \"Travel\" --heading \"Before\"`\n- With tags: `things add \"Call dentist\" --tags \"health,phone\"`\n- Checklist: `things add \"Trip prep\" --checklist-item \"Passport\" --checklist-item \"Tickets\"`\n- From STDIN (multi-line => title + notes):\n  - `cat <<'EOF' | things add -`\n  - `Title line`\n  - `Notes line 1`\n  - `Notes line 2`\n  - `EOF`\n\nExamples: modify a todo (needs auth token)\n- First: get the ID (UUID column): `things search \"milk\" --limit 5`\n- Auth: set `THINGS_AUTH_TOKEN` or pass `--auth-token <TOKEN>`\n- Title: `things update --id <UUID> --auth-token <TOKEN> \"New title\"`\n- Notes replace: `things update --id <UUID> --auth-token <TOKEN> --notes \"New notes\"`\n- Notes append/prepend: `things update --id <UUID> --auth-token <TOKEN> --append-notes \"...\"` / `--prepend-notes \"...\"`\n- Move lists: `things update --id <UUID> --auth-token <TOKEN> --list \"Travel\" --heading \"Before\"`\n- Tags replace/add: `things update --id <UUID> --auth-token <TOKEN> --tags \"a,b\"` / `things update --id <UUID> --auth-token <TOKEN> --add-tags \"a,b\"`\n- Complete/cancel (soft-delete-ish): `things update --id <UUID> --auth-token <TOKEN> --completed` / `--canceled`\n- Safe preview: `things --dry-run update --id <UUID> --auth-token <TOKEN> --completed`\n\nDelete a todo?\n- Not supported by `things3-cli` right now (no “delete/move-to-trash” write command; `things trash` is read-only listing).\n- Options: use Things UI to delete/trash, or mark as `--completed` / `--canceled` via `things update`.\n\nNotes\n- macOS-only.\n- `--dry-run` prints the URL and does not open Things.""",
                examples=[],
                gotchas=[],
                homepage="https://github.com/ossianhempel/things3-cli",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "things_mac", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["things_mac"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "things_mac":
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
        if tool_name != "things_mac":
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

        if tool_name != "things_mac":
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
        binaries = ["'things'"]
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
