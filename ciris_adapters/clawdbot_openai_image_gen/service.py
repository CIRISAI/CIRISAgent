"""
OpenaiImageGen Tool Service for CIRIS.

Converted from Clawdbot skill: openai-image-gen
Batch-generate images via OpenAI Images API. Random prompt sampler + `index.html` gallery.

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


class OpenaiImageGenToolService:
    """
    OpenaiImageGen tool service providing skill-based guidance.

    Original skill: openai-image-gen
    Description: Batch-generate images via OpenAI Images API. Random prompt sampler + `index.html` gallery.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("OpenaiImageGenToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("OpenaiImageGenToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("OpenaiImageGenToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="openai_image_gen",
            description="""Batch-generate images via OpenAI Images API. Random prompt sampler + `index.html` gallery.""",
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
            when_to_use="""When you need to batch-generate images via openai images api. random prompt sampler + `index.html` gallery.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="python3"),
                ],
                env_vars=[
                    EnvVarRequirement(name="OPENAI_API_KEY", secret=True),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="python-brew",
                    kind="brew",
                    label="Install Python (brew)",
                    formula="python",
                    provides_binaries=["python3"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Generate a handful of “random but structured” prompts and render them via the OpenAI Images API.",
                detailed_instructions="""# OpenAI Image Gen\n\nGenerate a handful of “random but structured” prompts and render them via the OpenAI Images API.\n\n## Run\n\n```bash\npython3 {baseDir}/scripts/gen.py\nopen ~/Projects/tmp/openai-image-gen-*/index.html  # if ~/Projects/tmp exists; else ./tmp/...\n```\n\nUseful flags:\n\n```bash\n# GPT image models with various options\npython3 {baseDir}/scripts/gen.py --count 16 --model gpt-image-1\npython3 {baseDir}/scripts/gen.py --prompt \"ultra-detailed studio photo of a lobster astronaut\" --count 4\npython3 {baseDir}/scripts/gen.py --size 1536x1024 --quality high --out-dir ./out/images\npython3 {baseDir}/scripts/gen.py --model gpt-image-1.5 --background transparent --output-format webp\n\n# DALL-E 3 (note: count is automatically limited to 1)\npython3 {baseDir}/scripts/gen.py --model dall-e-3 --quality hd --size 1792x1024 --style vivid\npython3 {baseDir}/scripts/gen.py --model dall-e-3 --style natural --prompt \"serene mountain landscape\"\n\n# DALL-E 2\npython3 {baseDir}/scripts/gen.py --model dall-e-2 --size 512x512 --count 4\n```\n\n## Model-Specific Parameters\n\nDifferent models support different parameter values. The script automatically selects appropriate defaults based on the model.\n\n### Size\n\n- **GPT image models** (`gpt-image-1`, `gpt-image-1-mini`, `gpt-image-1.5`): `1024x1024`, `1536x1024` (landscape), `1024x1536` (portrait), or `auto`\n  - Default: `1024x1024`\n- **dall-e-3**: `1024x1024`, `1792x1024`, or `1024x1792`\n  - Default: `1024x1024`\n- **dall-e-2**: `256x256`, `512x512`, or `1024x1024`\n  - Default: `1024x1024`\n\n### Quality\n\n- **GPT image models**: `auto`, `high`, `medium`, or `low`\n  - Default: `high`\n- **dall-e-3**: `hd` or `standard`\n  - Default: `standard`\n- **dall-e-2**: `standard` only\n  - Default: `standard`\n\n### Other Notable Differences\n\n- **dall-e-3** only supports generating 1 image at a time (`n=1`). The script automatically limits count to 1 when using this model.\n- **GPT image models** support additional parameters:\n  - `--background`: `transparent`, `opaque`, or `auto` (default)\n  - `--output-format`: `png` (default), `jpeg`, or `webp`\n  - Note: `stream` and `moderation` are available via API but not yet implemented in this script\n- **dall-e-3** has a `--style` parameter: `vivid` (hyper-real, dramatic) or `natural` (more natural looking)\n\n## Output\n\n- `*.png`, `*.jpeg`, or `*.webp` images (output format depends on model + `--output-format`)\n- `prompts.json` (prompt → file mapping)\n- `index.html` (thumbnail gallery)""",
                examples=[],
                gotchas=[],
                homepage="https://platform.openai.com/docs/api-reference/images",
            ),
            dma_guidance=ToolDMAGuidance(
                ethical_considerations="Requires API credentials - ensure proper authorization",
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "openai_image_gen", "cli", "api"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["openai_image_gen"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "openai_image_gen":
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
        if tool_name != "openai_image_gen":
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

        if tool_name != "openai_image_gen":
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
        binaries = ["'python3'"]
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
        env_vars = ["'OPENAI_API_KEY'"]
        for env_var in env_vars:
            if not os.environ.get(env_var):
                missing.append(f"env:{env_var}")

        return len(missing) == 0, missing
