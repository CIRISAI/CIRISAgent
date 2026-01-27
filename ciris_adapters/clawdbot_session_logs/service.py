"""
SessionLogs Tool Service for CIRIS.

Converted from Clawdbot skill: session-logs
Search and analyze your own session logs (older/parent conversations) using jq.

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


class SessionLogsToolService:
    """
    SessionLogs tool service providing skill-based guidance.

    Original skill: session-logs
    Description: Search and analyze your own session logs (older/parent conversations) using jq.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("SessionLogsToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("SessionLogsToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("SessionLogsToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="session_logs",
            description="""Search and analyze your own session logs (older/parent conversations) using jq.""",
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
            when_to_use="""When you need to search and analyze your own session logs (older/parent conversations) using jq.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="jq"),
                    BinaryRequirement(name="rg"),
                ],
            ),
            install_steps=[],
            documentation=ToolDocumentation(
                quick_start="Search your complete conversation history stored in session JSONL files. Use this when a user references older/parent conversations or asks what was said before.",
                detailed_instructions="""# session-logs\n\nSearch your complete conversation history stored in session JSONL files. Use this when a user references older/parent conversations or asks what was said before.\n\n## Trigger\n\nUse this skill when the user asks about prior chats, parent conversations, or historical context that isn’t in memory files.\n\n## Location\n\nSession logs live at: `~/.clawdbot/agents/<agentId>/sessions/` (use the `agent=<id>` value from the system prompt Runtime line).\n\n- **`sessions.json`** - Index mapping session keys to session IDs\n- **`<session-id>.jsonl`** - Full conversation transcript per session\n\n## Structure\n\nEach `.jsonl` file contains messages with:\n- `type`: \"session\" (metadata) or \"message\"\n- `timestamp`: ISO timestamp\n- `message.role`: \"user\", \"assistant\", or \"toolResult\"\n- `message.content[]`: Text, thinking, or tool calls (filter `type==\"text\"` for human-readable content)\n- `message.usage.cost.total`: Cost per response\n\n## Common Queries\n\n### List all sessions by date and size\n```bash\nfor f in ~/.clawdbot/agents/<agentId>/sessions/*.jsonl; do\n  date=$(head -1 \"$f\" | jq -r '.timestamp' | cut -dT -f1)\n  size=$(ls -lh \"$f\" | awk '{print $5}')\n  echo \"$date $size $(basename $f)\"\ndone | sort -r\n```\n\n### Find sessions from a specific day\n```bash\nfor f in ~/.clawdbot/agents/<agentId>/sessions/*.jsonl; do\n  head -1 \"$f\" | jq -r '.timestamp' | grep -q \"2026-01-06\" && echo \"$f\"\ndone\n```\n\n### Extract user messages from a session\n```bash\njq -r 'select(.message.role == \"user\") | .message.content[]? | select(.type == \"text\") | .text' <session>.jsonl\n```\n\n### Search for keyword in assistant responses\n```bash\njq -r 'select(.message.role == \"assistant\") | .message.content[]? | select(.type == \"text\") | .text' <session>.jsonl | rg -i \"keyword\"\n```\n\n### Get total cost for a session\n```bash\njq -s '[.[] | .message.usage.cost.total // 0] | add' <session>.jsonl\n```\n\n### Daily cost summary\n```bash\nfor f in ~/.clawdbot/agents/<agentId>/sessions/*.jsonl; do\n  date=$(head -1 \"$f\" | jq -r '.timestamp' | cut -dT -f1)\n  cost=$(jq -s '[.[] | .message.usage.cost.total // 0] | add' \"$f\")\n  echo \"$date $cost\"\ndone | awk '{a[$1]+=$2} END {for(d in a) print d, \"$\"a[d]}' | sort -r\n```\n\n### Count messages and tokens in a session\n```bash\njq -s '{\n  messages: length,\n  user: [.[] | select(.message.role == \"user\")] | length,\n  assistant: [.[] | select(.message.role == \"assistant\")] | length,\n  first: .[0].timestamp,\n  last: .[-1].timestamp\n}' <session>.jsonl\n```\n\n### Tool usage breakdown\n```bash\njq -r '.message.content[]? | select(.type == \"toolCall\") | .name' <session>.jsonl | sort | uniq -c | sort -rn\n```\n\n### Search across ALL sessions for a phrase\n```bash\nrg -l \"phrase\" ~/.clawdbot/agents/<agentId>/sessions/*.jsonl\n```\n\n## Tips\n\n- Sessions are append-only JSONL (one JSON object per line)\n- Large sessions can be several MB - use `head`/`tail` for sampling\n- The `sessions.json` index maps chat providers (discord, whatsapp, etc.) to session IDs\n- Deleted sessions have `.deleted.<timestamp>` suffix\n\n## Fast text-only hint (low noise)\n\n```bash\njq -r 'select(.type==\"message\") | .message.content[]? | select(.type==\"text\") | .text' ~/.clawdbot/agents/<agentId>/sessions/<id>.jsonl | rg 'keyword'\n```""",
                examples=[],
                gotchas=[],
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "session_logs", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["session_logs"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "session_logs":
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
        if tool_name != "session_logs":
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

        if tool_name != "session_logs":
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
        binaries = ["'jq'", "'rg'"]
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
