"""
Wacli Tool Service for CIRIS.

Converted from Clawdbot skill: wacli
Send WhatsApp messages to other people or search/sync WhatsApp history via the wacli CLI (not for normal user chats).

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


class WacliToolService:
    """
    Wacli tool service providing skill-based guidance.

    Original skill: wacli
    Description: Send WhatsApp messages to other people or search/sync WhatsApp history via the wacli CLI (not for normal user chats).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("WacliToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("WacliToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("WacliToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="wacli",
            description="""Send WhatsApp messages to other people or search/sync WhatsApp history via the wacli CLI (not for normal user chats).""",
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
            when_to_use="""When you need to send whatsapp messages to other people or search/sync whatsapp history via the wacli cli (not for no...""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="wacli"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install wacli (brew)",
                    formula="steipete/tap/wacli",
                    provides_binaries=["wacli"],
                ),
                InstallStep(id="go", kind="go", label="Install wacli (go)", provides_binaries=["wacli"]),
            ],
            documentation=ToolDocumentation(
                quick_start="Use `wacli` only when the user explicitly asks you to message someone else on WhatsApp or when they ask to sync/search WhatsApp history.",
                detailed_instructions="""# wacli\n\nUse `wacli` only when the user explicitly asks you to message someone else on WhatsApp or when they ask to sync/search WhatsApp history.\nDo NOT use `wacli` for normal user chats; Moltbot routes WhatsApp conversations automatically.\nIf the user is chatting with you on WhatsApp, you should not reach for this tool unless they ask you to contact a third party.\n\nSafety\n- Require explicit recipient + message text.\n- Confirm recipient + message before sending.\n- If anything is ambiguous, ask a clarifying question.\n\nAuth + sync\n- `wacli auth` (QR login + initial sync)\n- `wacli sync --follow` (continuous sync)\n- `wacli doctor`\n\nFind chats + messages\n- `wacli chats list --limit 20 --query \"name or number\"`\n- `wacli messages search \"query\" --limit 20 --chat <jid>`\n- `wacli messages search \"invoice\" --after 2025-01-01 --before 2025-12-31`\n\nHistory backfill\n- `wacli history backfill --chat <jid> --requests 2 --count 50`\n\nSend\n- Text: `wacli send text --to \"+14155551212\" --message \"Hello! Are you free at 3pm?\"`\n- Group: `wacli send text --to \"1234567890-123456789@g.us\" --message \"Running 5 min late.\"`\n- File: `wacli send file --to \"+14155551212\" --file /path/agenda.pdf --caption \"Agenda\"`\n\nNotes\n- Store dir: `~/.wacli` (override with `--store`).\n- Use `--json` for machine-readable output when parsing.\n- Backfill requires your phone online; results are best-effort.\n- WhatsApp CLI is not needed for routine user chats; it’s for messaging other people.\n- JIDs: direct chats look like `<number>@s.whatsapp.net`; groups look like `<id>@g.us` (use `wacli chats list` to find).""",
                examples=[],
                gotchas=[],
                homepage="https://wacli.sh",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "wacli", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["wacli"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "wacli":
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
        if tool_name != "wacli":
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

        if tool_name != "wacli":
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
        binaries = ["'wacli'"]
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
