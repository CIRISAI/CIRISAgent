"""
Slack Tool Service for CIRIS.

Converted from Clawdbot skill: slack
Use when you need to control Slack from Moltbot via the slack tool, including reacting to messages or pinning/unpinning items in Slack channels or DMs.

This service provides skill-based guidance for using external tools/CLIs.
The detailed instructions from the original SKILL.md are embedded in the
ToolInfo.documentation field for DMA-aware tool selection.
"""

import logging
import os
import shutil
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


class SlackToolService:
    """
    Slack tool service providing skill-based guidance.

    Original skill: slack
    Description: Use when you need to control Slack from Moltbot via the slack tool, including reacting to messages or pinning/unpinning items in Slack channels or DMs.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("SlackToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("SlackToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("SlackToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="slack",
            description="""Use when you need to control Slack from Moltbot via the slack tool, including reacting to messages or pinning/unpinning items in Slack channels or DMs.""",
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
            when_to_use="""When you need to use when you need to control slack from moltbot via the slack tool, including reacting to messages o...""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="slack"),
                ],
                config_keys=[
                    ConfigRequirement(key="channels.slack"),
                ],
                platforms=["darwin", "linux", "win32"],  # Desktop OSes only
            ),
            install_steps=[],
            documentation=ToolDocumentation(
                quick_start="Use `slack` to react, manage pins, send/edit/delete messages, and fetch member info. The tool uses the bot token configured for Moltbot.",
                detailed_instructions="""# Slack Actions\n\n## Overview\n\nUse `slack` to react, manage pins, send/edit/delete messages, and fetch member info. The tool uses the bot token configured for Moltbot.\n\n## Inputs to collect\n\n- `channelId` and `messageId` (Slack message timestamp, e.g. `1712023032.1234`).\n- For reactions, an `emoji` (Unicode or `:name:`).\n- For message sends, a `to` target (`channel:<id>` or `user:<id>`) and `content`.\n\nMessage context lines include `slack message id` and `channel` fields you can reuse directly.\n\n## Actions\n\n### Action groups\n\n| Action group | Default | Notes |\n| --- | --- | --- |\n| reactions | enabled | React + list reactions |\n| messages | enabled | Read/send/edit/delete |\n| pins | enabled | Pin/unpin/list |\n| memberInfo | enabled | Member info |\n| emojiList | enabled | Custom emoji list |\n\n### React to a message\n\n```json\n{\n  \"action\": \"react\",\n  \"channelId\": \"C123\",\n  \"messageId\": \"1712023032.1234\",\n  \"emoji\": \"✅\"\n}\n```\n\n### List reactions\n\n```json\n{\n  \"action\": \"reactions\",\n  \"channelId\": \"C123\",\n  \"messageId\": \"1712023032.1234\"\n}\n```\n\n### Send a message\n\n```json\n{\n  \"action\": \"sendMessage\",\n  \"to\": \"channel:C123\",\n  \"content\": \"Hello from Moltbot\"\n}\n```\n\n### Edit a message\n\n```json\n{\n  \"action\": \"editMessage\",\n  \"channelId\": \"C123\",\n  \"messageId\": \"1712023032.1234\",\n  \"content\": \"Updated text\"\n}\n```\n\n### Delete a message\n\n```json\n{\n  \"action\": \"deleteMessage\",\n  \"channelId\": \"C123\",\n  \"messageId\": \"1712023032.1234\"\n}\n```\n\n### Read recent messages\n\n```json\n{\n  \"action\": \"readMessages\",\n  \"channelId\": \"C123\",\n  \"limit\": 20\n}\n```\n\n### Pin a message\n\n```json\n{\n  \"action\": \"pinMessage\",\n  \"channelId\": \"C123\",\n  \"messageId\": \"1712023032.1234\"\n}\n```\n\n### Unpin a message\n\n```json\n{\n  \"action\": \"unpinMessage\",\n  \"channelId\": \"C123\",\n  \"messageId\": \"1712023032.1234\"\n}\n```\n\n### List pinned items\n\n```json\n{\n  \"action\": \"listPins\",\n  \"channelId\": \"C123\"\n}\n```\n\n### Member info\n\n```json\n{\n  \"action\": \"memberInfo\",\n  \"userId\": \"U123\"\n}\n```\n\n### Emoji list\n\n```json\n{\n  \"action\": \"emojiList\"\n}\n```\n\n## Ideas to try\n\n- React with ✅ to mark completed tasks.\n- Pin key decisions or weekly status updates.""",
                examples=[],
                gotchas=[],
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "slack"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["slack"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "slack":
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
        if tool_name != "slack":
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

        if tool_name != "slack":
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

            # Check requirements using ToolInfo
            tool_info = self._build_tool_info()
            requirements_met, missing = self._check_requirements(tool_info)
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

    def _check_requirements(self, tool_info: ToolInfo) -> tuple[bool, List[str]]:
        """Check if all requirements are met using ToolInfo.requirements."""
        missing = []

        if not tool_info.requirements:
            return True, []

        req = tool_info.requirements

        # Check binaries
        for bin_req in req.binaries:
            if not shutil.which(bin_req.name):
                missing.append(f"binary:{bin_req.name}")

        # Check any_binaries (at least one)
        if req.any_binaries:
            found = any(shutil.which(b.name) for b in req.any_binaries)
            if not found:
                names = [b.name for b in req.any_binaries]
                missing.append(f"any_binary:{','.join(names)}")

        # Check env vars
        for env_req in req.env_vars:
            if not os.environ.get(env_req.name):
                missing.append(f"env:{env_req.name}")

        # Check config keys (skip for now - would need config service)
        # for config_req in req.config_keys:
        #     ...

        return len(missing) == 0, missing
