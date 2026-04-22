"""
Summarize Tool Service for CIRIS.

Converted from Clawdbot skill: summarize
Summarize or extract text/transcripts from URLs, podcasts, and local files (great fallback for “transcribe this YouTube/video”).

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


class SummarizeToolService:
    """
    Summarize tool service providing skill-based guidance.

    Original skill: summarize
    Description: Summarize or extract text/transcripts from URLs, podcasts, and local files (great fallback for “transcribe this YouTube/video”).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("SummarizeToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("SummarizeToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("SummarizeToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="summarize",
            description="""Summarize or extract text/transcripts from URLs, podcasts, and local files (great fallback for “transcribe this YouTube/video”).""",
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
            when_to_use="""When you need to summarize or extract text/transcripts from urls, podcasts, and local files (great fallback for “tran...""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="summarize"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install summarize (brew)",
                    formula="steipete/tap/summarize",
                    provides_binaries=["summarize"],
                    platforms=["darwin"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Fast CLI to summarize URLs, local files, and YouTube links.",
                detailed_instructions="""# Summarize\n\nFast CLI to summarize URLs, local files, and YouTube links.\n\n## When to use (trigger phrases)\n\nUse this skill immediately when the user asks any of:\n- “use summarize.sh”\n- “what’s this link/video about?”\n- “summarize this URL/article”\n- “transcribe this YouTube/video” (best-effort transcript extraction; no `yt-dlp` needed)\n\n## Quick start\n\n```bash\nsummarize \"https://example.com\" --model google/gemini-3-flash-preview\nsummarize \"/path/to/file.pdf\" --model google/gemini-3-flash-preview\nsummarize \"https://youtu.be/dQw4w9WgXcQ\" --youtube auto\n```\n\n## YouTube: summary vs transcript\n\nBest-effort transcript (URLs only):\n\n```bash\nsummarize \"https://youtu.be/dQw4w9WgXcQ\" --youtube auto --extract-only\n```\n\nIf the user asked for a transcript but it’s huge, return a tight summary first, then ask which section/time range to expand.\n\n## Model + keys\n\nSet the API key for your chosen provider:\n- OpenAI: `OPENAI_API_KEY`\n- Anthropic: `ANTHROPIC_API_KEY`\n- xAI: `XAI_API_KEY`\n- Google: `GEMINI_API_KEY` (aliases: `GOOGLE_GENERATIVE_AI_API_KEY`, `GOOGLE_API_KEY`)\n\nDefault model is `google/gemini-3-flash-preview` if none is set.\n\n## Useful flags\n\n- `--length short|medium|long|xl|xxl|<chars>`\n- `--max-output-tokens <count>`\n- `--extract-only` (URLs only)\n- `--json` (machine readable)\n- `--firecrawl auto|off|always` (fallback extraction)\n- `--youtube auto` (Apify fallback if `APIFY_API_TOKEN` set)\n\n## Config\n\nOptional config file: `~/.summarize/config.json`\n\n```json\n{ \"model\": \"openai/gpt-5.2\" }\n```\n\nOptional services:\n- `FIRECRAWL_API_KEY` for blocked sites\n- `APIFY_API_TOKEN` for YouTube fallback""",
                examples=[],
                gotchas=[],
                homepage="https://summarize.sh",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "summarize", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["summarize"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "summarize":
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
        if tool_name != "summarize":
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

        if tool_name != "summarize":
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
