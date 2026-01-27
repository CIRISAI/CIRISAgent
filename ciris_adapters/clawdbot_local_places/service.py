"""
LocalPlaces Tool Service for CIRIS.

Converted from Clawdbot skill: local-places
Search for places (restaurants, cafes, etc.) via Google Places API proxy on localhost.

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


class LocalPlacesToolService:
    """
    LocalPlaces tool service providing skill-based guidance.

    Original skill: local-places
    Description: Search for places (restaurants, cafes, etc.) via Google Places API proxy on localhost.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("LocalPlacesToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("LocalPlacesToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("LocalPlacesToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="local_places",
            description="""Search for places (restaurants, cafes, etc.) via Google Places API proxy on localhost.""",
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
            when_to_use="""When you need to search for places (restaurants, cafes, etc.) via google places api proxy on localhost.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="uv"),
                ],
                env_vars=[
                    EnvVarRequirement(name="GOOGLE_PLACES_API_KEY", secret=True),
                ],
            ),
            install_steps=[],
            documentation=ToolDocumentation(
                quick_start="*Find places, Go fast*",
                detailed_instructions="""# 📍 Local Places\n\n*Find places, Go fast*\n\nSearch for nearby places using a local Google Places API proxy. Two-step flow: resolve location first, then search.\n\n## Setup\n\n```bash\ncd {baseDir}\necho \"GOOGLE_PLACES_API_KEY=your-key\" > .env\nuv venv && uv pip install -e \".[dev]\"\nuv run --env-file .env uvicorn local_places.main:app --host 127.0.0.1 --port 8000\n```\n\nRequires `GOOGLE_PLACES_API_KEY` in `.env` or environment.\n\n## Quick Start\n\n1. **Check server:** `curl http://127.0.0.1:8000/ping`\n\n2. **Resolve location:**\n```bash\ncurl -X POST http://127.0.0.1:8000/locations/resolve \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"location_text\": \"Soho, London\", \"limit\": 5}'\n```\n\n3. **Search places:**\n```bash\ncurl -X POST http://127.0.0.1:8000/places/search \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\n    \"query\": \"coffee shop\",\n    \"location_bias\": {\"lat\": 51.5137, \"lng\": -0.1366, \"radius_m\": 1000},\n    \"filters\": {\"open_now\": true, \"min_rating\": 4.0},\n    \"limit\": 10\n  }'\n```\n\n4. **Get details:**\n```bash\ncurl http://127.0.0.1:8000/places/{place_id}\n```\n\n## Conversation Flow\n\n1. If user says \"near me\" or gives vague location → resolve it first\n2. If multiple results → show numbered list, ask user to pick\n3. Ask for preferences: type, open now, rating, price level\n4. Search with `location_bias` from chosen location\n5. Present results with name, rating, address, open status\n6. Offer to fetch details or refine search\n\n## Filter Constraints\n\n- `filters.types`: exactly ONE type (e.g., \"restaurant\", \"cafe\", \"gym\")\n- `filters.price_levels`: integers 0-4 (0=free, 4=very expensive)\n- `filters.min_rating`: 0-5 in 0.5 increments\n- `filters.open_now`: boolean\n- `limit`: 1-20 for search, 1-10 for resolve\n- `location_bias.radius_m`: must be > 0\n\n## Response Format\n\n```json\n{\n  \"results\": [\n    {\n      \"place_id\": \"ChIJ...\",\n      \"name\": \"Coffee Shop\",\n      \"address\": \"123 Main St\",\n      \"location\": {\"lat\": 51.5, \"lng\": -0.1},\n      \"rating\": 4.6,\n      \"price_level\": 2,\n      \"types\": [\"cafe\", \"food\"],\n      \"open_now\": true\n    }\n  ],\n  \"next_page_token\": \"...\"\n}\n```\n\nUse `next_page_token` as `page_token` in next request for more results.""",
                examples=[],
                gotchas=[],
                homepage="https://github.com/Hyaxia/local_places",
            ),
            dma_guidance=ToolDMAGuidance(
                ethical_considerations="Requires API credentials - ensure proper authorization",
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "local_places", "cli", "api"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["local_places"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "local_places":
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
        if tool_name != "local_places":
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

        if tool_name != "local_places":
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
        binaries = ["'uv'"]
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
        env_vars = ["'GOOGLE_PLACES_API_KEY'"]
        for env_var in env_vars:
            if not os.environ.get(env_var):
                missing.append(f"env:{env_var}")

        return len(missing) == 0, missing
