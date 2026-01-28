"""
Obsidian Tool Service for CIRIS.

Converted from Clawdbot skill: obsidian
Work with Obsidian vaults (plain Markdown notes) and automate via obsidian-cli.

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


class ObsidianToolService:
    """
    Obsidian tool service providing skill-based guidance.

    Original skill: obsidian
    Description: Work with Obsidian vaults (plain Markdown notes) and automate via obsidian-cli.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("ObsidianToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("ObsidianToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("ObsidianToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="obsidian",
            description="""Work with Obsidian vaults (plain Markdown notes) and automate via obsidian-cli.""",
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
            when_to_use="""When you need to work with obsidian vaults (plain markdown notes) and automate via obsidian-cli.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="obsidian-cli"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install obsidian-cli (brew)",
                    formula="yakitrak/yakitrak/obsidian-cli",
                    provides_binaries=["obsidian-cli"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Obsidian vault = a normal folder on disk.",
                detailed_instructions="""# Obsidian\n\nObsidian vault = a normal folder on disk.\n\nVault structure (typical)\n- Notes: `*.md` (plain text Markdown; edit with any editor)\n- Config: `.obsidian/` (workspace + plugin settings; usually don’t touch from scripts)\n- Canvases: `*.canvas` (JSON)\n- Attachments: whatever folder you chose in Obsidian settings (images/PDFs/etc.)\n\n## Find the active vault(s)\n\nObsidian desktop tracks vaults here (source of truth):\n- `~/Library/Application Support/obsidian/obsidian.json`\n\n`obsidian-cli` resolves vaults from that file; vault name is typically the **folder name** (path suffix).\n\nFast “what vault is active / where are the notes?”\n- If you’ve already set a default: `obsidian-cli print-default --path-only`\n- Otherwise, read `~/Library/Application Support/obsidian/obsidian.json` and use the vault entry with `\"open\": true`.\n\nNotes\n- Multiple vaults common (iCloud vs `~/Documents`, work/personal, etc.). Don’t guess; read config.\n- Avoid writing hardcoded vault paths into scripts; prefer reading the config or using `print-default`.\n\n## obsidian-cli quick start\n\nPick a default vault (once):\n- `obsidian-cli set-default \"<vault-folder-name>\"`\n- `obsidian-cli print-default` / `obsidian-cli print-default --path-only`\n\nSearch\n- `obsidian-cli search \"query\"` (note names)\n- `obsidian-cli search-content \"query\"` (inside notes; shows snippets + lines)\n\nCreate\n- `obsidian-cli create \"Folder/New note\" --content \"...\" --open`\n- Requires Obsidian URI handler (`obsidian://…`) working (Obsidian installed).\n- Avoid creating notes under “hidden” dot-folders (e.g. `.something/...`) via URI; Obsidian may refuse.\n\nMove/rename (safe refactor)\n- `obsidian-cli move \"old/path/note\" \"new/path/note\"`\n- Updates `[[wikilinks]]` and common Markdown links across the vault (this is the main win vs `mv`).\n\nDelete\n- `obsidian-cli delete \"path/note\"`\n\nPrefer direct edits when appropriate: open the `.md` file and change it; Obsidian will pick it up.""",
                examples=[],
                gotchas=[],
                homepage="https://help.obsidian.md",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "obsidian", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["obsidian"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "obsidian":
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
        if tool_name != "obsidian":
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

        if tool_name != "obsidian":
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
