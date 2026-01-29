"""
Trello Tool Service for CIRIS.

Converted from Clawdbot skill: trello
Manage Trello boards, lists, and cards via the Trello REST API.

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


class TrelloToolService:
    """
    Trello tool service providing skill-based guidance.

    Original skill: trello
    Description: Manage Trello boards, lists, and cards via the Trello REST API.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("TrelloToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("TrelloToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("TrelloToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="trello",
            description="""Manage Trello boards, lists, and cards via the Trello REST API.""",
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
            when_to_use="""When you need to manage trello boards, lists, and cards via the trello rest api.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="jq"),
                ],
                env_vars=[
                    EnvVarRequirement(name="TRELLO_API_KEY"),
                    EnvVarRequirement(name="TRELLO_TOKEN"),
                ],
            ),
            install_steps=[],
            documentation=ToolDocumentation(
                quick_start="Manage Trello boards, lists, and cards directly from Moltbot.",
                detailed_instructions="""# Trello Skill\n\nManage Trello boards, lists, and cards directly from Moltbot.\n\n## Setup\n\n1. Get your API key: https://trello.com/app-key\n2. Generate a token (click \"Token\" link on that page)\n3. Set environment variables:\n   ```bash\n   export TRELLO_API_KEY=\"your-api-key\"\n   export TRELLO_TOKEN=\"your-token\"\n   ```\n\n## Usage\n\nAll commands use curl to hit the Trello REST API.\n\n### List boards\n```bash\ncurl -s \"https://api.trello.com/1/members/me/boards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\" | jq '.[] | {name, id}'\n```\n\n### List lists in a board\n```bash\ncurl -s \"https://api.trello.com/1/boards/{boardId}/lists?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\" | jq '.[] | {name, id}'\n```\n\n### List cards in a list\n```bash\ncurl -s \"https://api.trello.com/1/lists/{listId}/cards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\" | jq '.[] | {name, id, desc}'\n```\n\n### Create a card\n```bash\ncurl -s -X POST \"https://api.trello.com/1/cards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\" \\\n  -d \"idList={listId}\" \\\n  -d \"name=Card Title\" \\\n  -d \"desc=Card description\"\n```\n\n### Move a card to another list\n```bash\ncurl -s -X PUT \"https://api.trello.com/1/cards/{cardId}?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\" \\\n  -d \"idList={newListId}\"\n```\n\n### Add a comment to a card\n```bash\ncurl -s -X POST \"https://api.trello.com/1/cards/{cardId}/actions/comments?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\" \\\n  -d \"text=Your comment here\"\n```\n\n### Archive a card\n```bash\ncurl -s -X PUT \"https://api.trello.com/1/cards/{cardId}?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\" \\\n  -d \"closed=true\"\n```\n\n## Notes\n\n- Board/List/Card IDs can be found in the Trello URL or via the list commands\n- The API key and token provide full access to your Trello account - keep them secret!\n- Rate limits: 300 requests per 10 seconds per API key; 100 requests per 10 seconds per token; `/1/members` endpoints are limited to 100 requests per 900 seconds\n\n## Examples\n\n```bash\n# Get all boards\ncurl -s \"https://api.trello.com/1/members/me/boards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN&fields=name,id\" | jq\n\n# Find a specific board by name\ncurl -s \"https://api.trello.com/1/members/me/boards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\" | jq '.[] | select(.name | contains(\"Work\"))'\n\n# Get all cards on a board\ncurl -s \"https://api.trello.com/1/boards/{boardId}/cards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN\" | jq '.[] | {name, list: .idList}'\n```""",
                examples=[],
                gotchas=[],
                homepage="https://developer.atlassian.com/cloud/trello/rest/",
            ),
            dma_guidance=ToolDMAGuidance(
                ethical_considerations="Requires API credentials - ensure proper authorization",
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "trello", "cli", "api"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["trello"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "trello":
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
        if tool_name != "trello":
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

        if tool_name != "trello":
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
