"""
Himalaya Tool Service for CIRIS.

Converted from Clawdbot skill: himalaya
CLI to manage emails via IMAP/SMTP. Use `himalaya` to list, read, write, reply, forward, search, and organize emails from the terminal. Supports multiple accounts and message composition with MML (MIME Meta Language).

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


class HimalayaToolService:
    """
    Himalaya tool service providing skill-based guidance.

    Original skill: himalaya
    Description: CLI to manage emails via IMAP/SMTP. Use `himalaya` to list, read, write, reply, forward, search, and organize emails from the terminal. Supports multiple accounts and message composition with MML (MIME Meta Language).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("HimalayaToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("HimalayaToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("HimalayaToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="himalaya",
            description="""CLI to manage emails via IMAP/SMTP. Use `himalaya` to list, read, write, reply, forward, search, and organize emails from the terminal. Supports multiple accounts and message composition with MML (MIME Meta Language).""",
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
            when_to_use="""When you need to cli to manage emails via imap/smtp. use `himalaya` to list, read, write, reply, forward, search, and...""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="himalaya"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install Himalaya (brew)",
                    formula="himalaya",
                    provides_binaries=["himalaya"],
                    platforms=["darwin"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Himalaya is a CLI email client that lets you manage emails from the terminal using IMAP, SMTP, Notmuch, or Sendmail backends.",
                detailed_instructions="""# Himalaya Email CLI\n\nHimalaya is a CLI email client that lets you manage emails from the terminal using IMAP, SMTP, Notmuch, or Sendmail backends.\n\n## References\n\n- `references/configuration.md` (config file setup + IMAP/SMTP authentication)\n- `references/message-composition.md` (MML syntax for composing emails)\n\n## Prerequisites\n\n1. Himalaya CLI installed (`himalaya --version` to verify)\n2. A configuration file at `~/.config/himalaya/config.toml`\n3. IMAP/SMTP credentials configured (password stored securely)\n\n## Configuration Setup\n\nRun the interactive wizard to set up an account:\n```bash\nhimalaya account configure\n```\n\nOr create `~/.config/himalaya/config.toml` manually:\n```toml\n[accounts.personal]\nemail = \"you@example.com\"\ndisplay-name = \"Your Name\"\ndefault = true\n\nbackend.type = \"imap\"\nbackend.host = \"imap.example.com\"\nbackend.port = 993\nbackend.encryption.type = \"tls\"\nbackend.login = \"you@example.com\"\nbackend.auth.type = \"password\"\nbackend.auth.cmd = \"pass show email/imap\"  # or use keyring\n\nmessage.send.backend.type = \"smtp\"\nmessage.send.backend.host = \"smtp.example.com\"\nmessage.send.backend.port = 587\nmessage.send.backend.encryption.type = \"start-tls\"\nmessage.send.backend.login = \"you@example.com\"\nmessage.send.backend.auth.type = \"password\"\nmessage.send.backend.auth.cmd = \"pass show email/smtp\"\n```\n\n## Common Operations\n\n### List Folders\n\n```bash\nhimalaya folder list\n```\n\n### List Emails\n\nList emails in INBOX (default):\n```bash\nhimalaya envelope list\n```\n\nList emails in a specific folder:\n```bash\nhimalaya envelope list --folder \"Sent\"\n```\n\nList with pagination:\n```bash\nhimalaya envelope list --page 1 --page-size 20\n```\n\n### Search Emails\n\n```bash\nhimalaya envelope list from john@example.com subject meeting\n```\n\n### Read an Email\n\nRead email by ID (shows plain text):\n```bash\nhimalaya message read 42\n```\n\nExport raw MIME:\n```bash\nhimalaya message export 42 --full\n```\n\n### Reply to an Email\n\nInteractive reply (opens $EDITOR):\n```bash\nhimalaya message reply 42\n```\n\nReply-all:\n```bash\nhimalaya message reply 42 --all\n```\n\n### Forward an Email\n\n```bash\nhimalaya message forward 42\n```\n\n### Write a New Email\n\nInteractive compose (opens $EDITOR):\n```bash\nhimalaya message write\n```\n\nSend directly using template:\n```bash\ncat << 'EOF' | himalaya template send\nFrom: you@example.com\nTo: recipient@example.com\nSubject: Test Message\n\nHello from Himalaya!\nEOF\n```\n\nOr with headers flag:\n```bash\nhimalaya message write -H \"To:recipient@example.com\" -H \"Subject:Test\" \"Message body here\"\n```\n\n### Move/Copy Emails\n\nMove to folder:\n```bash\nhimalaya message move 42 \"Archive\"\n```\n\nCopy to folder:\n```bash\nhimalaya message copy 42 \"Important\"\n```\n\n### Delete an Email\n\n```bash\nhimalaya message delete 42\n```\n\n### Manage Flags\n\nAdd flag:\n```bash\nhimalaya flag add 42 --flag seen\n```\n\nRemove flag:\n```bash\nhimalaya flag remove 42 --flag seen\n```\n\n## Multiple Accounts\n\nList accounts:\n```bash\nhimalaya account list\n```\n\nUse a specific account:\n```bash\nhimalaya --account work envelope list\n```\n\n## Attachments\n\nSave attachments from a message:\n```bash\nhimalaya attachment download 42\n```\n\nSave to specific directory:\n```bash\nhimalaya attachment download 42 --dir ~/Downloads\n```\n\n## Output Formats\n\nMost commands support `--output` for structured output:\n```bash\nhimalaya envelope list --output json\nhimalaya envelope list --output plain\n```\n\n## Debugging\n\nEnable debug logging:\n```bash\nRUST_LOG=debug himalaya envelope list\n```\n\nFull trace with backtrace:\n```bash\nRUST_LOG=trace RUST_BACKTRACE=1 himalaya envelope list\n```\n\n## Tips\n\n- Use `himalaya --help` or `himalaya <command> --help` for detailed usage.\n- Message IDs are relative to the current folder; re-list after folder changes.\n- For composing rich emails with attachments, use MML syntax (see `references/message-composition.md`).\n- Store passwords securely using `pass`, system keyring, or a command that outputs the password.""",
                examples=[],
                gotchas=[],
                homepage="https://github.com/pimalaya/himalaya",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "himalaya", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["himalaya"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "himalaya":
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
        if tool_name != "himalaya":
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

        if tool_name != "himalaya":
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
