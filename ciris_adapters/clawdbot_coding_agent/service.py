"""
CodingAgent Tool Service for CIRIS.

Converted from Clawdbot skill: coding-agent
Run Codex CLI, Claude Code, OpenCode, or Pi Coding Agent via background process for programmatic control.

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


class CodingAgentToolService:
    """
    CodingAgent tool service providing skill-based guidance.

    Original skill: coding-agent
    Description: Run Codex CLI, Claude Code, OpenCode, or Pi Coding Agent via background process for programmatic control.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("CodingAgentToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("CodingAgentToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("CodingAgentToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="coding_agent",
            description="""Run Codex CLI, Claude Code, OpenCode, or Pi Coding Agent via background process for programmatic control.""",
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
            when_to_use="""When you need to run codex cli, claude code, opencode, or pi coding agent via background process for programmatic con...""",
            requirements=ToolRequirements(
                any_binaries=[
                    BinaryRequirement(name="claude"),
                    BinaryRequirement(name="codex"),
                    BinaryRequirement(name="opencode"),
                    BinaryRequirement(name="pi"),
                ],
            ),
            install_steps=[],
            documentation=ToolDocumentation(
                quick_start="Use **bash** (with optional background mode) for all coding agent work. Simple and effective.",
                detailed_instructions="""# Coding Agent (bash-first)\n\nUse **bash** (with optional background mode) for all coding agent work. Simple and effective.\n\n## ⚠️ PTY Mode Required!\n\nCoding agents (Codex, Claude Code, Pi) are **interactive terminal applications** that need a pseudo-terminal (PTY) to work correctly. Without PTY, you'll get broken output, missing colors, or the agent may hang.\n\n**Always use `pty:true`** when running coding agents:\n\n```bash\n# ✅ Correct - with PTY\nbash pty:true command:\"codex exec 'Your prompt'\"\n\n# ❌ Wrong - no PTY, agent may break\nbash command:\"codex exec 'Your prompt'\"\n```\n\n### Bash Tool Parameters\n\n| Parameter | Type | Description |\n|-----------|------|-------------|\n| `command` | string | The shell command to run |\n| `pty` | boolean | **Use for coding agents!** Allocates a pseudo-terminal for interactive CLIs |\n| `workdir` | string | Working directory (agent sees only this folder's context) |\n| `background` | boolean | Run in background, returns sessionId for monitoring |\n| `timeout` | number | Timeout in seconds (kills process on expiry) |\n| `elevated` | boolean | Run on host instead of sandbox (if allowed) |\n\n### Process Tool Actions (for background sessions)\n\n| Action | Description |\n|--------|-------------|\n| `list` | List all running/recent sessions |\n| `poll` | Check if session is still running |\n| `log` | Get session output (with optional offset/limit) |\n| `write` | Send raw data to stdin |\n| `submit` | Send data + newline (like typing and pressing Enter) |\n| `send-keys` | Send key tokens or hex bytes |\n| `paste` | Paste text (with optional bracketed mode) |\n| `kill` | Terminate the session |\n\n---\n\n## Quick Start: One-Shot Tasks\n\nFor quick prompts/chats, create a temp git repo and run:\n\n```bash\n# Quick chat (Codex needs a git repo!)\nSCRATCH=$(mktemp -d) && cd $SCRATCH && git init && codex exec \"Your prompt here\"\n\n# Or in a real project - with PTY!\nbash pty:true workdir:~/Projects/myproject command:\"codex exec 'Add error handling to the API calls'\"\n```\n\n**Why git init?** Codex refuses to run outside a trusted git directory. Creating a temp repo solves this for scratch work.\n\n---\n\n## The Pattern: workdir + background + pty\n\nFor longer tasks, use background mode with PTY:\n\n```bash\n# Start agent in target directory (with PTY!)\nbash pty:true workdir:~/project background:true command:\"codex exec --full-auto 'Build a snake game'\"\n# Returns sessionId for tracking\n\n# Monitor progress\nprocess action:log sessionId:XXX\n\n# Check if done\nprocess action:poll sessionId:XXX\n\n# Send input (if agent asks a question)\nprocess action:write sessionId:XXX data:\"y\"\n\n# Submit with Enter (like typing \"yes\" and pressing Enter)\nprocess action:submit sessionId:XXX data:\"yes\"\n\n# Kill if needed\nprocess action:kill sessionId:XXX\n```\n\n**Why workdir matters:** Agent wakes up in a focused directory, doesn't wander off reading unrelated files (like your soul.md 😅).\n\n---\n\n## Codex CLI\n\n**Model:** `gpt-5.2-codex` is the default (set in ~/.codex/config.toml)\n\n### Flags\n\n| Flag | Effect |\n|------|--------|\n| `exec \"prompt\"` | One-shot execution, exits when done |\n| `--full-auto` | Sandboxed but auto-approves in workspace |\n| `--yolo` | NO sandbox, NO approvals (fastest, most dangerous) |\n\n### Building/Creating\n```bash\n# Quick one-shot (auto-approves) - remember PTY!\nbash pty:true workdir:~/project command:\"codex exec --full-auto 'Build a dark mode toggle'\"\n\n# Background for longer work\nbash pty:true workdir:~/project background:true command:\"codex --yolo 'Refactor the auth module'\"\n```\n\n### Reviewing PRs\n\n**⚠️ CRITICAL: Never review PRs in Moltbot's own project folder!**\nClone to temp folder or use git worktree.\n\n```bash\n# Clone to temp for safe review\nREVIEW_DIR=$(mktemp -d)\ngit clone https://github.com/user/repo.git $REVIEW_DIR\ncd $REVIEW_DIR && gh pr checkout 130\nbash pty:true workdir:$REVIEW_DIR command:\"codex review --base origin/main\"\n# Clean up after: trash $REVIEW_DIR\n\n# Or use git worktree (keeps main intact)\ngit worktree add /tmp/pr-130-review pr-130-branch\nbash pty:true workdir:/tmp/pr-130-review command:\"codex review --base main\"\n```\n\n### Batch PR Reviews (parallel army!)\n```bash\n# Fetch all PR refs first\ngit fetch origin '+refs/pull/*/head:refs/remotes/origin/pr/*'\n\n# Deploy the army - one Codex per PR (all with PTY!)\nbash pty:true workdir:~/project background:true command:\"codex exec 'Review PR #86. git diff origin/main...origin/pr/86'\"\nbash pty:true workdir:~/project background:true command:\"codex exec 'Review PR #87. git diff origin/main...origin/pr/87'\"\n\n# Monitor all\nprocess action:list\n\n# Post results to GitHub\ngh pr comment <PR#> --body \"<review content>\"\n```\n\n---\n\n## Claude Code\n\n```bash\n# With PTY for proper terminal output\nbash pty:true workdir:~/project command:\"claude 'Your task'\"\n\n# Background\nbash pty:true workdir:~/project background:true command:\"claude 'Your task'\"\n```\n\n---\n\n## OpenCode\n\n```bash\nbash pty:true workdir:~/project command:\"opencode run 'Your task'\"\n```\n\n---\n\n## Pi Coding Agent\n\n```bash\n# Install: """,
                examples=[],
                gotchas=[],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Review warnings in documentation before use",
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "coding_agent"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["coding_agent"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "coding_agent":
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
        if tool_name != "coding_agent":
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

        if tool_name != "coding_agent":
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
        any_binaries = ["'claude'", "'codex'", "'opencode'", "'pi'"]
        if any_binaries:
            found = any(shutil.which(b) for b in any_binaries)
            if not found:
                missing.append(f"any_binary:{','.join(any_binaries)}")

        # Check env vars
        env_vars = []
        for env_var in env_vars:
            if not os.environ.get(env_var):
                missing.append(f"env:{env_var}")

        return len(missing) == 0, missing
