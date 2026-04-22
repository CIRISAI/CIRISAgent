"""
NanoBananaPro Tool Service for CIRIS.

Converted from Clawdbot skill: nano-banana-pro
Generate or edit images via Gemini 3 Pro Image (Nano Banana Pro).

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


class NanoBananaProToolService:
    """
    NanoBananaPro tool service providing skill-based guidance.

    Original skill: nano-banana-pro
    Description: Generate or edit images via Gemini 3 Pro Image (Nano Banana Pro).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("NanoBananaProToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("NanoBananaProToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("NanoBananaProToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="nano_banana_pro",
            description="""Generate or edit images via Gemini 3 Pro Image (Nano Banana Pro).""",
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
            when_to_use="""When you need to generate or edit images via gemini 3 pro image (nano banana pro).""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="uv"),
                ],
                env_vars=[
                    EnvVarRequirement(name="GEMINI_API_KEY"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="uv-brew",
                    kind="brew",
                    label="Install uv (brew)",
                    formula="uv",
                    provides_binaries=["uv"],
                    platforms=["darwin"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Use the bundled script to generate or edit images.",
                detailed_instructions="""# Nano Banana Pro (Gemini 3 Pro Image)\n\nUse the bundled script to generate or edit images.\n\nGenerate\n```bash\nuv run {baseDir}/scripts/generate_image.py --prompt \"your image description\" --filename \"output.png\" --resolution 1K\n```\n\nEdit (single image)\n```bash\nuv run {baseDir}/scripts/generate_image.py --prompt \"edit instructions\" --filename \"output.png\" -i \"/path/in.png\" --resolution 2K\n```\n\nMulti-image composition (up to 14 images)\n```bash\nuv run {baseDir}/scripts/generate_image.py --prompt \"combine these into one scene\" --filename \"output.png\" -i img1.png -i img2.png -i img3.png\n```\n\nAPI key\n- `GEMINI_API_KEY` env var\n- Or set `skills.\"nano-banana-pro\".apiKey` / `skills.\"nano-banana-pro\".env.GEMINI_API_KEY` in `~/.clawdbot/moltbot.json`\n\nNotes\n- Resolutions: `1K` (default), `2K`, `4K`.\n- Use timestamps in filenames: `yyyy-mm-dd-hh-mm-ss-name.png`.\n- The script prints a `MEDIA:` line for Moltbot to auto-attach on supported chat providers.\n- Do not read the image back; report the saved path only.""",
                examples=[],
                gotchas=[],
                homepage="https://ai.google.dev/",
            ),
            dma_guidance=ToolDMAGuidance(
                ethical_considerations="Requires API credentials - ensure proper authorization",
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "nano_banana_pro", "cli", "api"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["nano_banana_pro"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "nano_banana_pro":
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
        if tool_name != "nano_banana_pro":
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

        if tool_name != "nano_banana_pro":
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
