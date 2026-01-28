"""
Gifgrep Tool Service for CIRIS.

Converted from Clawdbot skill: gifgrep
Search GIF providers with CLI/TUI, download results, and extract stills/sheets.

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


class GifgrepToolService:
    """
    Gifgrep tool service providing skill-based guidance.

    Original skill: gifgrep
    Description: Search GIF providers with CLI/TUI, download results, and extract stills/sheets.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("GifgrepToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("GifgrepToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("GifgrepToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="gifgrep",
            description="""Search GIF providers with CLI/TUI, download results, and extract stills/sheets.""",
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
            when_to_use="""When you need to search gif providers with cli/tui, download results, and extract stills/sheets.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="gifgrep"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install gifgrep (brew)",
                    formula="steipete/tap/gifgrep",
                    provides_binaries=["gifgrep"],
                ),
                InstallStep(id="go", kind="go", label="Install gifgrep (go)", provides_binaries=["gifgrep"]),
            ],
            documentation=ToolDocumentation(
                quick_start="Use `gifgrep` to search GIF providers (Tenor/Giphy), browse in a TUI, download results, and extract stills or sheets.",
                detailed_instructions="""# gifgrep\n\nUse `gifgrep` to search GIF providers (Tenor/Giphy), browse in a TUI, download results, and extract stills or sheets.\n\nGIF-Grab (gifgrep workflow)\n- Search → preview → download → extract (still/sheet) for fast review and sharing.\n\nQuick start\n- `gifgrep cats --max 5`\n- `gifgrep cats --format url | head -n 5`\n- `gifgrep search --json cats | jq '.[0].url'`\n- `gifgrep tui \"office handshake\"`\n- `gifgrep cats --download --max 1 --format url`\n\nTUI + previews\n- TUI: `gifgrep tui \"query\"`\n- CLI still previews: `--thumbs` (Kitty/Ghostty only; still frame)\n\nDownload + reveal\n- `--download` saves to `~/Downloads`\n- `--reveal` shows the last download in Finder\n\nStills + sheets\n- `gifgrep still ./clip.gif --at 1.5s -o still.png`\n- `gifgrep sheet ./clip.gif --frames 9 --cols 3 -o sheet.png`\n- Sheets = single PNG grid of sampled frames (great for quick review, docs, PRs, chat).\n- Tune: `--frames` (count), `--cols` (grid width), `--padding` (spacing).\n\nProviders\n- `--source auto|tenor|giphy`\n- `GIPHY_API_KEY` required for `--source giphy`\n- `TENOR_API_KEY` optional (Tenor demo key used if unset)\n\nOutput\n- `--json` prints an array of results (`id`, `title`, `url`, `preview_url`, `tags`, `width`, `height`)\n- `--format` for pipe-friendly fields (e.g., `url`)\n\nEnvironment tweaks\n- `GIFGREP_SOFTWARE_ANIM=1` to force software animation\n- `GIFGREP_CELL_ASPECT=0.5` to tweak preview geometry""",
                examples=[],
                gotchas=[],
                homepage="https://gifgrep.com",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "gifgrep", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["gifgrep"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "gifgrep":
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
        if tool_name != "gifgrep":
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

        if tool_name != "gifgrep":
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
