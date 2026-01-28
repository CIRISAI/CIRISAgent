"""
Sag Tool Service for CIRIS.

Converted from Clawdbot skill: sag
ElevenLabs text-to-speech with mac-style say UX.

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


class SagToolService:
    """
    Sag tool service providing skill-based guidance.

    Original skill: sag
    Description: ElevenLabs text-to-speech with mac-style say UX.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("SagToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("SagToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("SagToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="sag",
            description="""ElevenLabs text-to-speech with mac-style say UX.""",
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
            when_to_use="""When you need to elevenlabs text-to-speech with mac-style say ux.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="sag"),
                ],
                env_vars=[
                    EnvVarRequirement(name="ELEVENLABS_API_KEY"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install sag (brew)",
                    formula="steipete/tap/sag",
                    provides_binaries=["sag"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Use `sag` for ElevenLabs TTS with local playback.",
                detailed_instructions="""# sag\n\nUse `sag` for ElevenLabs TTS with local playback.\n\nAPI key (required)\n- `ELEVENLABS_API_KEY` (preferred)\n- `SAG_API_KEY` also supported by the CLI\n\nQuick start\n- `sag \"Hello there\"`\n- `sag speak -v \"Roger\" \"Hello\"`\n- `sag voices`\n- `sag prompting` (model-specific tips)\n\nModel notes\n- Default: `eleven_v3` (expressive)\n- Stable: `eleven_multilingual_v2`\n- Fast: `eleven_flash_v2_5`\n\nPronunciation + delivery rules\n- First fix: respell (e.g. \"key-note\"), add hyphens, adjust casing.\n- Numbers/units/URLs: `--normalize auto` (or `off` if it harms names).\n- Language bias: `--lang en|de|fr|...` to guide normalization.\n- v3: SSML `<break>` not supported; use `[pause]`, `[short pause]`, `[long pause]`.\n- v2/v2.5: SSML `<break time=\"1.5s\" />` supported; `<phoneme>` not exposed in `sag`.\n\nv3 audio tags (put at the entrance of a line)\n- `[whispers]`, `[shouts]`, `[sings]`\n- `[laughs]`, `[starts laughing]`, `[sighs]`, `[exhales]`\n- `[sarcastic]`, `[curious]`, `[excited]`, `[crying]`, `[mischievously]`\n- Example: `sag \"[whispers] keep this quiet. [short pause] ok?\"`\n\nVoice defaults\n- `ELEVENLABS_VOICE_ID` or `SAG_VOICE_ID`\n\nConfirm voice + speaker before long output.\n\n## Chat voice responses\n\nWhen Peter asks for a \"voice\" reply (e.g., \"crazy scientist voice\", \"explain in voice\"), generate audio and send it:\n\n```bash\n# Generate audio file\nsag -v Clawd -o /tmp/voice-reply.mp3 \"Your message here\"\n\n# Then include in reply:\n# MEDIA:/tmp/voice-reply.mp3\n```\n\nVoice character tips:\n- Crazy scientist: Use `[excited]` tags, dramatic pauses `[short pause]`, vary intensity\n- Calm: Use `[whispers]` or slower pacing\n- Dramatic: Use `[sings]` or `[shouts]` sparingly\n\nDefault voice for Clawd: `lj2rcrvANS3gaWWnczSX` (or just `-v Clawd`)""",
                examples=[],
                gotchas=[],
                homepage="https://sag.sh",
            ),
            dma_guidance=ToolDMAGuidance(
                ethical_considerations="Requires API credentials - ensure proper authorization",
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "sag", "cli", "api"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["sag"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "sag":
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
        if tool_name != "sag":
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

        if tool_name != "sag":
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
