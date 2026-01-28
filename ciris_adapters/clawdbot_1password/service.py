"""
Onepassword Tool Service for CIRIS.

Converted from Clawdbot skill: 1password
Set up and use 1Password CLI (op). Use when installing the CLI, enabling desktop app integration, signing in (single or multi-account), or reading/injecting/running secrets via op.

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


class OnepasswordToolService:
    """
    Onepassword tool service providing skill-based guidance.

    Original skill: 1password
    Description: Set up and use 1Password CLI (op). Use when installing the CLI, enabling desktop app integration, signing in (single or multi-account), or reading/injecting/running secrets via op.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("OnepasswordToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("OnepasswordToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("OnepasswordToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="1password",
            description="""Set up and use 1Password CLI (op). Use when installing the CLI, enabling desktop app integration, signing in (single or multi-account), or reading/injecting/running secrets via op.""",
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
            when_to_use="""When you need to set up and use 1password cli (op). use when installing the cli, enabling desktop app integration, si...""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="op"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install 1Password CLI (brew)",
                    formula="1password-cli",
                    provides_binaries=["op"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Follow the official CLI get-started steps. Don't guess install commands.",
                detailed_instructions="""# 1Password CLI\n\nFollow the official CLI get-started steps. Don't guess install commands.\n\n## References\n\n- `references/get-started.md` (install + app integration + sign-in flow)\n- `references/cli-examples.md` (real `op` examples)\n\n## Workflow\n\n1. Check OS + shell.\n2. Verify CLI present: `op --version`.\n3. Confirm desktop app integration is enabled (per get-started) and the app is unlocked.\n4. REQUIRED: create a fresh tmux session for all `op` commands (no direct `op` calls outside tmux).\n5. Sign in / authorize inside tmux: `op signin` (expect app prompt).\n6. Verify access inside tmux: `op whoami` (must succeed before any secret read).\n7. If multiple accounts: use `--account` or `OP_ACCOUNT`.\n\n## REQUIRED tmux session (T-Max)\n\nThe shell tool uses a fresh TTY per command. To avoid re-prompts and failures, always run `op` inside a dedicated tmux session with a fresh socket/session name.\n\nExample (see `tmux` skill for socket conventions, do not reuse old session names):\n\n```bash\nSOCKET_DIR=\"${CLAWDBOT_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/moltbot-tmux-sockets}\"\nmkdir -p \"$SOCKET_DIR\"\nSOCKET=\"$SOCKET_DIR/moltbot-op.sock\"\nSESSION=\"op-auth-$(date +%Y%m%d-%H%M%S)\"\n\ntmux -S \"$SOCKET\" new -d -s \"$SESSION\" -n shell\ntmux -S \"$SOCKET\" send-keys -t \"$SESSION\":0.0 -- \"op signin --account my.1password.com\" Enter\ntmux -S \"$SOCKET\" send-keys -t \"$SESSION\":0.0 -- \"op whoami\" Enter\ntmux -S \"$SOCKET\" send-keys -t \"$SESSION\":0.0 -- \"op vault list\" Enter\ntmux -S \"$SOCKET\" capture-pane -p -J -t \"$SESSION\":0.0 -S -200\ntmux -S \"$SOCKET\" kill-session -t \"$SESSION\"\n```\n\n## Guardrails\n\n- Never paste secrets into logs, chat, or code.\n- Prefer `op run` / `op inject` over writing secrets to disk.\n- If sign-in without app integration is needed, use `op account add`.\n- If a command returns \"account is not signed in\", re-run `op signin` inside tmux and authorize in the app.\n- Do not run `op` outside tmux; stop and ask if tmux is unavailable.""",
                examples=[],
                gotchas=[],
                homepage="https://developer.1password.com/docs/cli/get-started/",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "1password", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["1password"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "1password":
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
        if tool_name != "1password":
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

        if tool_name != "1password":
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
