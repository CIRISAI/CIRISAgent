"""
Notion Tool Service for CIRIS.

Converted from Clawdbot skill: notion
Notion API for creating and managing pages, databases, and blocks.

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


class NotionToolService:
    """
    Notion tool service providing skill-based guidance.

    Original skill: notion
    Description: Notion API for creating and managing pages, databases, and blocks.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("NotionToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("NotionToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("NotionToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="notion",
            description="""Notion API for creating and managing pages, databases, and blocks.""",
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
            when_to_use="""When you need to notion api for creating and managing pages, databases, and blocks.""",
            requirements=ToolRequirements(
                env_vars=[
                    EnvVarRequirement(name="NOTION_API_KEY", secret=True),
                ],
            ),
            install_steps=[],
            documentation=ToolDocumentation(
                quick_start="Use the Notion API to create/read/update pages, data sources (databases), and blocks.",
                detailed_instructions="""# notion\n\nUse the Notion API to create/read/update pages, data sources (databases), and blocks.\n\n## Setup\n\n1. Create an integration at https://notion.so/my-integrations\n2. Copy the API key (starts with `ntn_` or `secret_`)\n3. Store it:\n```bash\nmkdir -p ~/.config/notion\necho \"ntn_your_key_here\" > ~/.config/notion/api_key\n```\n4. Share target pages/databases with your integration (click \"...\" → \"Connect to\" → your integration name)\n\n## API Basics\n\nAll requests need:\n```bash\nNOTION_KEY=$(cat ~/.config/notion/api_key)\ncurl -X GET \"https://api.notion.com/v1/...\" \\\n  -H \"Authorization: Bearer $NOTION_KEY\" \\\n  -H \"Notion-Version: 2025-09-03\" \\\n  -H \"Content-Type: application/json\"\n```\n\n> **Note:** The `Notion-Version` header is required. This skill uses `2025-09-03` (latest). In this version, databases are called \"data sources\" in the API.\n\n## Common Operations\n\n**Search for pages and data sources:**\n```bash\ncurl -X POST \"https://api.notion.com/v1/search\" \\\n  -H \"Authorization: Bearer $NOTION_KEY\" \\\n  -H \"Notion-Version: 2025-09-03\" \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"query\": \"page title\"}'\n```\n\n**Get page:**\n```bash\ncurl \"https://api.notion.com/v1/pages/{page_id}\" \\\n  -H \"Authorization: Bearer $NOTION_KEY\" \\\n  -H \"Notion-Version: 2025-09-03\"\n```\n\n**Get page content (blocks):**\n```bash\ncurl \"https://api.notion.com/v1/blocks/{page_id}/children\" \\\n  -H \"Authorization: Bearer $NOTION_KEY\" \\\n  -H \"Notion-Version: 2025-09-03\"\n```\n\n**Create page in a data source:**\n```bash\ncurl -X POST \"https://api.notion.com/v1/pages\" \\\n  -H \"Authorization: Bearer $NOTION_KEY\" \\\n  -H \"Notion-Version: 2025-09-03\" \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\n    \"parent\": {\"database_id\": \"xxx\"},\n    \"properties\": {\n      \"Name\": {\"title\": [{\"text\": {\"content\": \"New Item\"}}]},\n      \"Status\": {\"select\": {\"name\": \"Todo\"}}\n    }\n  }'\n```\n\n**Query a data source (database):**\n```bash\ncurl -X POST \"https://api.notion.com/v1/data_sources/{data_source_id}/query\" \\\n  -H \"Authorization: Bearer $NOTION_KEY\" \\\n  -H \"Notion-Version: 2025-09-03\" \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\n    \"filter\": {\"property\": \"Status\", \"select\": {\"equals\": \"Active\"}},\n    \"sorts\": [{\"property\": \"Date\", \"direction\": \"descending\"}]\n  }'\n```\n\n**Create a data source (database):**\n```bash\ncurl -X POST \"https://api.notion.com/v1/data_sources\" \\\n  -H \"Authorization: Bearer $NOTION_KEY\" \\\n  -H \"Notion-Version: 2025-09-03\" \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\n    \"parent\": {\"page_id\": \"xxx\"},\n    \"title\": [{\"text\": {\"content\": \"My Database\"}}],\n    \"properties\": {\n      \"Name\": {\"title\": {}},\n      \"Status\": {\"select\": {\"options\": [{\"name\": \"Todo\"}, {\"name\": \"Done\"}]}},\n      \"Date\": {\"date\": {}}\n    }\n  }'\n```\n\n**Update page properties:**\n```bash\ncurl -X PATCH \"https://api.notion.com/v1/pages/{page_id}\" \\\n  -H \"Authorization: Bearer $NOTION_KEY\" \\\n  -H \"Notion-Version: 2025-09-03\" \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"properties\": {\"Status\": {\"select\": {\"name\": \"Done\"}}}}'\n```\n\n**Add blocks to page:**\n```bash\ncurl -X PATCH \"https://api.notion.com/v1/blocks/{page_id}/children\" \\\n  -H \"Authorization: Bearer $NOTION_KEY\" \\\n  -H \"Notion-Version: 2025-09-03\" \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\n    \"children\": [\n      {\"object\": \"block\", \"type\": \"paragraph\", \"paragraph\": {\"rich_text\": [{\"text\": {\"content\": \"Hello\"}}]}}\n    ]\n  }'\n```\n\n## Property Types\n\nCommon property formats for database items:\n- **Title:** `{\"title\": [{\"text\": {\"content\": \"...\"}}]}`\n- **Rich text:** `{\"rich_text\": [{\"text\": {\"content\": \"...\"}}]}`\n- **Select:** `{\"select\": {\"name\": \"Option\"}}`\n- **Multi-select:** `{\"multi_select\": [{\"name\": \"A\"}, {\"name\": \"B\"}]}`\n- **Date:** `{\"date\": {\"start\": \"2024-01-15\", \"end\": \"2024-01-16\"}}`\n- **Checkbox:** `{\"checkbox\": true}`\n- **Number:** `{\"number\": 42}`\n- **URL:** `{\"url\": \"https://...\"}`\n- **Email:** `{\"email\": \"a@b.com\"}`\n- **Relation:** `{\"relation\": [{\"id\": \"page_id\"}]}`\n\n## Key Differences in 2025-09-03\n\n- **Databases → Data Sources:** Use `/data_sources/` endpoints for queries and retrieval\n- **Two IDs:** Each database now has both a `database_id` and a `data_source_id`\n  - Use `database_id` when creating pages (`parent: {\"database_id\": \"...\"}`)\n  - Use `data_source_id` when querying (`POST /v1/data_sources/{id}/query`)\n- **Search results:** Databases return as `\"object\": \"data_source\"` with their `data_source_id`\n- **Parent in responses:** Pages show `parent.data_source_id` alongside `parent.database_id`\n- **Finding the data_source_id:** Search for the database, or call `GET /v1/data_sources/{data_source_id}`\n\n## Notes\n\n- Page/database IDs are UUIDs (with or without dashes)\n- The API cannot set database view filters — that's UI-only\n- Rate limit: ~3 requests/second average\n- Use `is_inline: true` when creating data sources to embed them in pages""",
                examples=[],
                gotchas=[],
                homepage="https://developers.notion.com",
            ),
            dma_guidance=ToolDMAGuidance(
                ethical_considerations="Requires API credentials - ensure proper authorization",
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "notion", "api"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["notion"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "notion":
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
        if tool_name != "notion":
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

        if tool_name != "notion":
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
        binaries = []
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
        env_vars = ["'NOTION_API_KEY'"]
        for env_var in env_vars:
            if not os.environ.get(env_var):
                missing.append(f"env:{env_var}")

        return len(missing) == 0, missing
