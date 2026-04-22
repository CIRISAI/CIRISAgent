"""
Gog Tool Service for CIRIS.

Converted from Clawdbot skill: gog
Google Workspace CLI for Gmail, Calendar, Drive, Contacts, Sheets, and Docs.

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


class GogToolService:
    """
    Gog tool service providing skill-based guidance.

    Original skill: gog
    Description: Google Workspace CLI for Gmail, Calendar, Drive, Contacts, Sheets, and Docs.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service."""
        self.config = config or {}
        self._call_count = 0
        logger.info("GogToolService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("GogToolService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("GogToolService stopped")

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="gog",
            description="""Google Workspace CLI for Gmail, Calendar, Drive, Contacts, Sheets, and Docs.""",
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
            when_to_use="""When you need to google workspace cli for gmail, calendar, drive, contacts, sheets, and docs.""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="gog"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install gog (brew)",
                    formula="steipete/tap/gogcli",
                    provides_binaries=["gog"],
                    platforms=["darwin"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Use `gog` for Gmail/Calendar/Drive/Contacts/Sheets/Docs. Requires OAuth setup.",
                detailed_instructions="""# gog\n\nUse `gog` for Gmail/Calendar/Drive/Contacts/Sheets/Docs. Requires OAuth setup.\n\nSetup (once)\n- `gog auth credentials /path/to/client_secret.json`\n- `gog auth add you@gmail.com --services gmail,calendar,drive,contacts,docs,sheets`\n- `gog auth list`\n\nCommon commands\n- Gmail search: `gog gmail search 'newer_than:7d' --max 10`\n- Gmail messages search (per email, ignores threading): `gog gmail messages search \"in:inbox from:ryanair.com\" --max 20 --account you@example.com`\n- Gmail send (plain): `gog gmail send --to a@b.com --subject \"Hi\" --body \"Hello\"`\n- Gmail send (multi-line): `gog gmail send --to a@b.com --subject \"Hi\" --body-file ./message.txt`\n- Gmail send (stdin): `gog gmail send --to a@b.com --subject \"Hi\" --body-file -`\n- Gmail send (HTML): `gog gmail send --to a@b.com --subject \"Hi\" --body-html \"<p>Hello</p>\"`\n- Gmail draft: `gog gmail drafts create --to a@b.com --subject \"Hi\" --body-file ./message.txt`\n- Gmail send draft: `gog gmail drafts send <draftId>`\n- Gmail reply: `gog gmail send --to a@b.com --subject \"Re: Hi\" --body \"Reply\" --reply-to-message-id <msgId>`\n- Calendar list events: `gog calendar events <calendarId> --from <iso> --to <iso>`\n- Calendar create event: `gog calendar create <calendarId> --summary \"Title\" --from <iso> --to <iso>`\n- Calendar create with color: `gog calendar create <calendarId> --summary \"Title\" --from <iso> --to <iso> --event-color 7`\n- Calendar update event: `gog calendar update <calendarId> <eventId> --summary \"New Title\" --event-color 4`\n- Calendar show colors: `gog calendar colors`\n- Drive search: `gog drive search \"query\" --max 10`\n- Contacts: `gog contacts list --max 20`\n- Sheets get: `gog sheets get <sheetId> \"Tab!A1:D10\" --json`\n- Sheets update: `gog sheets update <sheetId> \"Tab!A1:B2\" --values-json '[[\"A\",\"B\"],[\"1\",\"2\"]]' --input USER_ENTERED`\n- Sheets append: `gog sheets append <sheetId> \"Tab!A:C\" --values-json '[[\"x\",\"y\",\"z\"]]' --insert INSERT_ROWS`\n- Sheets clear: `gog sheets clear <sheetId> \"Tab!A2:Z\"`\n- Sheets metadata: `gog sheets metadata <sheetId> --json`\n- Docs export: `gog docs export <docId> --format txt --out /tmp/doc.txt`\n- Docs cat: `gog docs cat <docId>`\n\nCalendar Colors\n- Use `gog calendar colors` to see all available event colors (IDs 1-11)\n- Add colors to events with `--event-color <id>` flag\n- Event color IDs (from `gog calendar colors` output):\n  - 1: #a4bdfc\n  - 2: #7ae7bf\n  - 3: #dbadff\n  - 4: #ff887c\n  - 5: #fbd75b\n  - 6: #ffb878\n  - 7: #46d6db\n  - 8: #e1e1e1\n  - 9: #5484ed\n  - 10: #51b749\n  - 11: #dc2127\n\nEmail Formatting\n- Prefer plain text. Use `--body-file` for multi-paragraph messages (or `--body-file -` for stdin).\n- Same `--body-file` pattern works for drafts and replies.\n- `--body` does not unescape `\\n`. If you need inline newlines, use a heredoc or `$'Line 1\\n\\nLine 2'`.\n- Use `--body-html` only when you need rich formatting.\n- HTML tags: `<p>` for paragraphs, `<br>` for line breaks, `<strong>` for bold, `<em>` for italic, `<a href=\"url\">` for links, `<ul>`/`<li>` for lists.\n- Example (plain text via stdin):\n  ```bash\n  gog gmail send --to recipient@example.com \\\n    --subject \"Meeting Follow-up\" \\\n    --body-file - <<'EOF'\n  Hi Name,\n\n  Thanks for meeting today. Next steps:\n  - Item one\n  - Item two\n\n  Best regards,\n  Your Name\n  EOF\n  ```\n- Example (HTML list):\n  ```bash\n  gog gmail send --to recipient@example.com \\\n    --subject \"Meeting Follow-up\" \\\n    --body-html \"<p>Hi Name,</p><p>Thanks for meeting today. Here are the next steps:</p><ul><li>Item one</li><li>Item two</li></ul><p>Best regards,<br>Your Name</p>\"\n  ```\n\nNotes\n- Set `GOG_ACCOUNT=you@gmail.com` to avoid repeating `--account`.\n- For scripting, prefer `--json` plus `--no-input`.\n- Sheets values can be passed via `--values-json` (recommended) or as inline rows.\n- Docs supports export/cat/copy. In-place edits require a Docs API client (not in gog).\n- Confirm before sending mail or creating events.\n- `gog gmail search` returns one row per thread; use `gog gmail messages search` when you need every individual email returned separately.""",
                examples=[],
                gotchas=[],
                homepage="https://gogcli.sh",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "gog", "cli"],
            version="1.0.0",
        )

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return ["gog"]

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        if tool_name == "gog":
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
        if tool_name != "gog":
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

        if tool_name != "gog":
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
